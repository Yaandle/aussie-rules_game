"""gameplay.py — the FULL GAME/SCENARIOS frame-by-frame update pipeline
and player actions (kick, handball, bounce, kick-aim).

Split out of game_state.py (see AUDIT.md's game_state.py decomposition)
— follows the same convention as mechanics.py/possession.py/
ai_control.py: every function takes the owning `game_state` object as
its first argument rather than being a GameState method. Calls into
outcomes.py for every possession/score/contest resolution; outcomes.py
never calls back in here.
"""

import math

import pygame

import ai_control
import controller
import mechanics
import outcomes
import possession
import settings
from game_phases import (CONTEST_DIRECTION_KEYS, MODE_AIMING_KICK,
                          MODE_IDLE, PHASE_END, PHASE_MENU, SCREEN_ROOT)

# ── Playing input ───────────────────────────────────────────────────

def handle_playing_input(game_state, event):
    if game_state.active_contest is not None:
        handle_contest_input(game_state, event)
        return
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_m:
            game_state.show_menu = not game_state.show_menu
            return
        if event.key == pygame.K_ESCAPE:
            if game_state.mode == MODE_AIMING_KICK:
                game_state.mode = MODE_IDLE
            else:
                game_state.show_menu = not game_state.show_menu
            return
        if game_state.show_menu:
            if event.key == pygame.K_BACKSPACE:   # quit to main menu
                game_state.phase = PHASE_MENU
                game_state.menu_screen = SCREEN_ROOT
                game_state.menu_index = 0
            return
        if event.key == pygame.K_TAB:
            switch_controlled_player(game_state)
        elif event.key in (pygame.K_1, pygame.K_q):
            attempt_handball(game_state)
        elif event.key in (pygame.K_2, pygame.K_k):
            if (game_state.carrier is not None and game_state.carrier.team == settings.YELLOW
                    and not game_state.ball.in_flight):
                enter_aim_mode(game_state)
        elif event.key in (pygame.K_3, pygame.K_SPACE):
            bounce(game_state)
        elif event.key == pygame.K_RETURN:
            # Controller-friendly kick confirm (the A button and the
            # right trigger both synthesize this — see controller.py's
            # _BUTTON_KEYS/_TRIGGER_KEYS) at wherever the aim cursor
            # currently sits; works for keyboard players too,
            # confirming at the current mouse position. Left trigger
            # is the controller's way into MODE_AIMING_KICK in the
            # first place (synthesizes K_2, same as the '2'/'K' keys —
            # see the K_2/K_k branch above), so the intended flow is
            # LT to aim, right stick or mouse to point, RT (or A, or
            # a click) to confirm.
            if game_state.mode == MODE_AIMING_KICK and game_state.aim_point is not None:
                attempt_kick(game_state, game_state.aim_point)

    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        if game_state.mode == MODE_AIMING_KICK and not game_state.show_menu:
            target = mouse_to_logical(game_state, event.pos)
            if target is not None:
                attempt_kick(game_state, target)


def handle_contest_input(game_state, event):
    """While a tackle/50-50 contest is live, arrow keys and numpad
    directions (see CONTEST_DIRECTION_KEYS) queue a press for
    outcomes.update_contest to consume next frame — a connected gamepad's
    D-pad arrives here too, already as synthetic KEYDOWN events (see
    controller.poll_events), so it needs no separate handling.
    Every other playing-input binding is suspended for the duration
    (see handle_playing_input) — the rest of the game is frozen anyway.
    """
    if event.type != pygame.KEYDOWN:
        return
    direction = CONTEST_DIRECTION_KEYS.get(event.key)
    if direction is not None:
        game_state._contest_direction_queue.append(direction)


def mouse_to_logical(game_state, screen_pos):
    """Unproject a window click through the diorama camera onto the
    field's ground plane. None when the click is above the horizon."""
    return game_state.camera.unproject(*screen_pos)


def enter_aim_mode(game_state):
    """Start a fresh kick-aim: the cursor resets to dead ahead of the
    carrier (their own projected screen position) instead of
    wherever it was left from a previous aim attempt, or wherever
    the mouse pointer happens to be sitting.

    Controller players in particular would otherwise see the
    reticle start somewhere arbitrary and unrelated to where they
    actually are on the field — the two are only reset together
    here, once, on entry; update_pressure_aim_and_camera's
    MODE_AIMING_KICK branch then moves the cursor from this point via
    the right stick or the mouse. Resetting _last_mouse_pos too means
    a stale mouse position left over from before this aim attempt
    can't cause an immediate jump the moment aiming starts.
    """
    game_state.mode = MODE_AIMING_KICK
    default = None
    carrier = game_state.carrier
    if carrier is not None:
        proj = game_state.camera.project(carrier.x, carrier.y, 0.0)
        if proj is not None:
            default = (proj[0], proj[1])
    if default is None:
        default = (settings.WINDOW_W / 2, settings.WINDOW_H / 2)
    game_state._aim_cursor[0], game_state._aim_cursor[1] = default
    game_state._last_mouse_pos = None
    game_state._aim_input_source = None


def apply_aim_assist(game_state, dt):
    """Controller-only: a gentle screen-space pull toward the nearest
    teammate once the cursor is close to them (settings.
    AIM_ASSIST_RADIUS), so lining up a pass doesn't need
    pixel-perfect stick control the way a mouse gets for free.

    Deliberately soft, not a lock-on: this blends the cursor a
    fraction of the way toward the target each frame (the fraction
    set by AIM_ASSIST_STRENGTH), on top of whatever the raw stick
    input already did this frame — it never overrides the stick, so
    holding it away from the pull always wins. Called only while
    game_state._aim_input_source == "controller" (see
    update_pressure_aim_and_camera) — mouse aiming is precise enough
    on its own and never gets this.
    """
    carrier = game_state.carrier
    target = None
    target_dist = settings.AIM_ASSIST_RADIUS
    for t in game_state.teammates:
        if t is carrier:
            continue
        proj = game_state.camera.project(t.x, t.y, 0.0)
        if proj is None:
            continue
        dist = math.hypot(proj[0] - game_state._aim_cursor[0],
                          proj[1] - game_state._aim_cursor[1])
        if dist < target_dist:
            target_dist = dist
            target = proj
    if target is None:
        return
    k = min(1.0, settings.AIM_ASSIST_STRENGTH * dt)
    game_state._aim_cursor[0] = max(0, min(settings.WINDOW_W,
        game_state._aim_cursor[0] + (target[0] - game_state._aim_cursor[0]) * k))
    game_state._aim_cursor[1] = max(0, min(settings.WINDOW_H,
        game_state._aim_cursor[1] + (target[1] - game_state._aim_cursor[1]) * k))


# ── Actions ─────────────────────────────────────────────────────────

def attempt_handball(game_state):
    """Handball to the nearest teammate in range; resolves via mechanics.

    Human (YELLOW) only — ai_control never calls this (its
    placeholder loop only runs/kicks, see its HOOK comment), so
    there's no AI path that needs this team-symmetric the way
    attempt_kick had to become.
    """
    carrier = game_state.carrier
    if carrier is None or carrier.team != settings.YELLOW or game_state.ball.in_flight:
        return
    receivers = [t for t in game_state.teammates
                 if t is not carrier
                 and t.distance_to(carrier.pos) <= settings.HANDBALL_RANGE]
    if not receivers:
        game_state._show_message("NO TARGET")
        return
    target = min(receivers, key=lambda t: t.distance_to(carrier.pos))
    pressure = mechanics.calculate_pressure(carrier, game_state.opponents)
    outcome = mechanics.resolve_handball(carrier, target, pressure)

    carrier.is_ball_carrier = False
    game_state.ball.start_flight(carrier.pos, target.pos)
    game_state._kick_in_flight_team = None   # a handball never draws the OOB check
    if outcome["success"]:
        game_state._pending_outcome = {"type": "possession", "player": target}
    else:
        # Dropped/spilled — a genuine loose ball at the target's feet
        # rather than an instant teleport to whichever opponent was
        # nearest (however far away that actually was); see
        # outcomes.apply_pending_outcome's "grounded" branch.
        game_state._pending_outcome = {"type": "grounded"}
    game_state.mode = MODE_IDLE


def attempt_kick(game_state, target_point):
    """Kick toward a target point: shot on goal or a field kick.

    Team-symmetric: works identically whichever team's player is
    carrying (see ai_control.decide_next_action, which calls this
    exact method for the AI's placeholder kick) — the attacking goal,
    "own"/"opposing" player lists, and possession/turnover outcome
    are all derived from carrier.team rather than assuming YELLOW.
    """
    carrier = game_state.carrier
    if carrier is None or game_state.ball.in_flight:
        return
    kick_distance = carrier.distance_to(target_point)
    if kick_distance > settings.KICK_MAX_RANGE:
        game_state._show_message("TOO FAR")
        return

    own_team = game_state.teammates if carrier.team == settings.YELLOW else game_state.opponents
    opposing_team = game_state.opponents if carrier.team == settings.YELLOW else game_state.teammates
    pressure = mechanics.calculate_pressure(carrier, opposing_team)
    goal = possession.attacking_goal(carrier.team)

    is_scoring_attempt = (game_state.mode_config.get("scoring_enabled", True)
                          and mechanics.is_scoring_attempt(carrier.pos, target_point, goal))
    # Out-of-bounds only ever applies to a genuine field kick — a shot
    # on goal necessarily aims at/near the boundary line by design
    # (GOAL_RIGHT/GOAL_LEFT sit exactly on the oval's edge — see
    # settings.py) and already has its own goal/behind/miss
    # resolution, so it's exempt (see advance_ball's OOB check).
    game_state._kick_in_flight_team = None if is_scoring_attempt else carrier.team

    if is_scoring_attempt:
        result = mechanics.resolve_scoring_attempt(carrier.pos, target_point, goal)
        game_state._pending_outcome = {"type": "score", "result": result, "team": carrier.team}
    else:
        outcome = mechanics.resolve_kick(carrier, target_point, opposing_team,
                                         own_team, pressure)
        candidates = outcome.get("candidates") or []
        if outcome["result"] == "grounded":
            # Inaccurate, or accurate but nobody was there to mark it:
            # a genuine loose ball — see outcomes.apply_pending_outcome's
            # "grounded" branch / outcomes.start_loose_ball. No winner
            # is decided here; it's whoever actually reaches the ball
            # once it's down (mechanics.resolve_kick's own docstring
            # explains why this isn't guessed at kick-time anymore).
            game_state._pending_outcome = {"type": "grounded"}
        elif (outcome["result"] == "contest"
                and game_state.mode_config.get("contests_enabled", True)
                and len(candidates) >= 2):
            # Defer the dice-roll to a live reaction contest instead
            # of resolving it instantly — the two players actually
            # closest to the drop (not just the first two in
            # resolve_kick's unsorted opponents-then-teammates list)
            # contest it.
            nearest_two = sorted(candidates,
                                 key=lambda p: p.distance_to(target_point))[:2]
            game_state._pending_outcome = {"type": "contest", "candidates": nearest_two}
        elif outcome["winner"].team == carrier.team:
            # is_mark flags a clean, uncontested mark specifically
            # (result == "mark") rather than any possession-type
            # outcome — a successful handball also resolves to
            # {"type": "possession", ...} (see attempt_handball) and
            # must never trigger stand-the-mark.
            game_state._pending_outcome = {"type": "possession",
                                     "player": outcome["winner"],
                                     "is_mark": outcome["result"] == "mark",
                                     "kick_distance": kick_distance}
        else:
            game_state._pending_outcome = {"type": "turnover",
                                     "player": outcome["winner"]}

    carrier.is_ball_carrier = False
    game_state.ball.start_flight(carrier.pos, target_point)
    game_state.mode = MODE_IDLE


def bounce(game_state):
    """Bounce the ball to legally continue running (resets the run meter).

    Human (YELLOW) only — the AI's placeholder loop doesn't play by
    the bounce rule yet (see ai_control.py's HOOK comment).
    """
    carrier = game_state.carrier
    if carrier is None or carrier.team != settings.YELLOW or game_state.ball.in_flight:
        return
    game_state.run_since_bounce = 0.0
    game_state.bounce_tick_timer = settings.BOUNCE_TICK_DURATION


# ── Update loop ─────────────────────────────────────────────────────

def update_playing(game_state, dt):
    """Advance timers, movement, AI, ball flight, and pending resolutions
    for one PHASE_PLAYING frame (see GameState.update, which handles the
    other phases and the show_menu/not-PHASE_PLAYING early-outs before
    calling this).

    A straight-line sequence of named steps — each one a self-
    contained concern (movement, defensive shape, tackle trigger,
    ball flight/outcomes, aim/camera, transient timers) — reads as a
    frame outline rather than one long block. Every step still runs in
    exactly the sequence it always has, and the two frame-ending early
    returns (a resolved tackle; time expiring) are unchanged.
    """
    # A live tackle/50-50 contest freezes the rest of the game (see
    # design note in possession.py's IN_CONTEST) — this is the one
    # branch point, simplest first pass rather than only freezing
    # the two participants.
    if game_state.active_contest is not None:
        outcomes.update_contest(game_state, dt)
        return

    # DEAD_BALL_KICKOUT only exists to mark the single frame the
    # kickout taker was just placed on — a kickout plays out exactly
    # like any other carry from here on (human input or
    # ai_control.decide_next_action), so it's promoted immediately.
    if game_state.possession_state == possession.DEAD_BALL_KICKOUT:
        game_state.possession_state = possession.HELD_PLAYER

    # Slow-motion decision mode: the whole world breathes slower
    # while a kick is being lined up. The camera keeps real time so
    # its follow and zoom stay smooth through the dilation.
    raw_dt = dt
    if game_state.mode == MODE_AIMING_KICK:
        dt *= settings.SLOWMO_FACTOR

    game_state.timer = max(0.0, game_state.timer - dt)
    if game_state.timer <= 0.0:
        time_expired(game_state)
        return

    # Refresh who the human is steering before reading input for this
    # frame (see update_controlled_player) — must happen before
    # update_movement below, otherwise input would always drive
    # last frame's controlled_player instead of this frame's.
    update_controlled_player(game_state)

    # Human carrier: keyboard/controller polling (update_movement
    # no-ops for a RED carrier). AI carrier: ai_control's placeholder
    # loop (no-ops for a YELLOW carrier) — see its HOOK comment for
    # where real decision-making eventually replaces this.
    update_movement(game_state, dt)
    ai_control.decide_next_action(game_state, dt)

    update_defenders_and_shape(game_state, dt)
    if game_state.possession_state == possession.LOOSE_BALL:
        update_loose_ball(game_state, dt)

    # Push apart any two players left standing closer than
    # PLAYER_MIN_SEPARATION after this frame's movement — nothing
    # above gives players a physical body of their own (every mover
    # only clamps against the field oval), so an attacker and their
    # marking defender in particular could otherwise end up on
    # almost the same spot, with one sprite fully hiding the other
    # until they happened to drift apart again. Deliberately smaller
    # than TACKLE_TRIGGER_RADIUS so it never blocks a real tackle
    # contest from triggering (see possession.find_tackle_trigger
    # below) — this only stops full visual overlap, not proximity.
    mechanics.separate_players(game_state.players, settings.PLAYER_MIN_SEPARATION)

    decay_contest_timers(game_state, dt)

    # A defender closing to tackle range resolves a tackle instantly
    # (see check_tackle_trigger / mechanics.resolve_tackle) —
    # ends this frame's update immediately, same as before, since a
    # resolved tackle can change who's carrying and everything below
    # (ball flight, pressure, aim) only means anything for whoever
    # this frame's actual carrier turns out to be.
    if check_tackle_trigger(game_state):
        return

    advance_ball(game_state, dt)
    update_pressure_aim_and_camera(game_state, raw_dt)
    decay_transient_timers(game_state, dt)


def update_defenders_and_shape(game_state, dt):
    """Closing defenders converge while someone holds the ball. In
    FULL GAME (not scenarios — see formations.py/GameState._load_layout
    comments) the rest of both sides also ease toward their kickoff
    formation shape, blended toward the ball, so a 16-a-side roster
    doesn't stand frozen off the ball. No-ops while nobody's
    carrying — a real, expected state now (see possession.LOOSE_BALL
    / update_loose_ball, called separately from update_playing and
    handling player convergence its own way while the ball's down).
    """
    carrier = game_state.carrier
    if carrier is None:
        return
    home = game_state._home_positions if game_state.game_mode == "full" else None
    # Whichever team ISN'T carrying closes in (this used to always
    # be RED chasing YELLOW — now that RED can carry too, the
    # chasing/resting sides swap with carrier.team so a human
    # defender actually converges on an AI carrier the same way
    # RED converges on the human, instead of RED harmlessly
    # "chasing" its own teammate).
    defending_team = game_state.opponents if carrier.team == settings.YELLOW else game_state.teammates
    carrying_teammates = game_state.teammates if carrier.team == settings.YELLOW else game_state.opponents
    # A defender currently standing the mark (see standing_mark /
    # outcomes.start_standing_mark) is frozen — excluded from the chase
    # entirely for the duration, same as a resting off-ball
    # teammate is excluded below. The human's controlled_player is
    # also excluded here whenever it's a defending-side player
    # (i.e. YELLOW is NOT carrying) — update_defenders drives both
    # the active chase step AND (via its own internal
    # update_off_ball call, see mechanics.py) the off-ball drift
    # for non-chasing defenders, so it must never touch whichever
    # defender the human is currently steering, or input and
    # auto-drift would fight over the same player every frame.
    standing_defender = game_state.standing_mark["defender"] if game_state.standing_mark else None
    excluded_defender = (game_state.controlled_player
                         if game_state.controlled_player in defending_team else None)
    chasing = [d for d in defending_team
              if d is not standing_defender and d is not excluded_defender]
    mechanics.update_defenders(chasing, carrier.pos, dt, home)
    if home is not None:
        resting = [t for t in carrying_teammates
                  if not t.is_ball_carrier and t is not game_state.controlled_player]
        mechanics.update_off_ball(resting, home, carrier.pos, dt)


def update_loose_ball(game_state, dt):
    """Nobody's carrying (see possession.LOOSE_BALL) — the nearest
    couple of players from EACH team sprint at the ball itself
    (mechanics.chase_loose_ball, not update_defenders: a loose ball
    is run onto, not shadowed at arm's length) instead of one side
    chasing a carrier. The human's controlled_player is excluded
    from YELLOW's automatic chase, same reasoning as
    update_defenders_and_shape's exclusion — running your own
    controlled player onto the ball is something the human does
    themselves via normal movement input, not something the AI does
    for them.

    Whoever actually gets within LOOSE_BALL_GATHER_RADIUS picks it
    up — instantly if only one player arrives, or via the same
    reaction contest a pack-marked kick already uses if two arrive
    together (a real 50/50), preferring one player per side when
    both are represented so it reads as a genuine contest rather
    than two teammates racing each other.
    """
    ball_pos = game_state.ball.pos
    chasing_yellow = [p for p in game_state.teammates if p is not game_state.controlled_player]
    mechanics.chase_loose_ball(chasing_yellow, ball_pos, dt,
                               settings.MAX_CHASERS, settings.LOOSE_BALL_CHASE_SPEED)
    mechanics.chase_loose_ball(game_state.opponents, ball_pos, dt,
                               settings.MAX_CHASERS, settings.LOOSE_BALL_CHASE_SPEED)

    gatherers = [p for p in game_state.players
                 if p.distance_to(ball_pos) <= settings.LOOSE_BALL_GATHER_RADIUS]
    if not gatherers:
        return
    if len(gatherers) == 1:
        winner = gatherers[0]
        outcomes.give_possession(game_state, winner)
        game_state._show_message("GATHERED")
        # Only a scenario turnover when the OPPONENT ends up with it —
        # YELLOW gathering their own loose ball back is scrappy, not
        # a turnover (matches every other register_turnover call
        # site, which only ever fires once the ball concretely ends
        # up with the non-human side).
        if winner.team != settings.YELLOW:
            outcomes.register_turnover(game_state)
        return
    yellow = [p for p in gatherers if p.team == settings.YELLOW]
    red = [p for p in gatherers if p.team == settings.RED]
    if yellow and red:
        pair = [min(yellow, key=lambda p: p.distance_to(ball_pos)),
               min(red, key=lambda p: p.distance_to(ball_pos))]
    else:
        pair = sorted(gatherers, key=lambda p: p.distance_to(ball_pos))[:2]
    if game_state.mode_config.get("contests_enabled", True):
        outcomes.start_contest(game_state, pair, "loose_ball")
    else:
        # Contests disabled: resolve the 50/50 instantly instead of
        # via the minigame — mirrors attempt_kick's own contests-
        # disabled fallback for a pack-marked kick, which registers
        # a turnover on the same instant-resolve-to-the-opponent
        # basis (see that branch's "turnover" pending-outcome type).
        winner = mechanics.resolve_contest(ball_pos, gatherers)
        outcomes.give_possession(game_state, winner)
        if winner.team != settings.YELLOW:
            outcomes.register_turnover(game_state)


def decay_contest_timers(game_state, dt):
    """Tick down cooldowns/timers gated on this frame's dt (already
    slow-mo'd while aiming a kick, same as every other timer here)."""
    game_state.contest_cooldown = max(0.0, game_state.contest_cooldown - dt)
    game_state.tackle_cooldown = max(0.0, game_state.tackle_cooldown - dt)
    if game_state.possession_state == possession.HELD_PLAYER:
        game_state.possession_held_timer += dt
    if game_state.standing_mark is not None:
        game_state.standing_mark["timer"] -= dt
        if game_state.standing_mark["timer"] <= 0.0:
            game_state.standing_mark = None


def check_tackle_trigger(game_state):
    """Resolve an instant tackle if one triggered this frame (see
    mechanics.resolve_tackle / possession.find_tackle_trigger /
    TACKLE_TRIGGER_RADIUS) rather than opening the reaction minigame —
    holding-the-ball is a match-rule judgment (how long the carrier's
    held it), not a race. Gated on tackle_cooldown so a just-resolved
    tackle's still-adjacent pairing (see outcomes.separate_after_contest)
    doesn't immediately re-trigger back to back.

    Returns True when a tackle resolved this frame — update_playing
    ends the frame immediately in that case.
    """
    if not (game_state.possession_state == possession.HELD_PLAYER
            and game_state.mode_config.get("contests_enabled", True)
            and game_state.tackle_cooldown <= 0.0):
        return False
    participants = possession.find_tackle_trigger(game_state)
    if participants is None:
        return False
    outcomes.resolve_tackle_now(game_state, participants)
    return True


def advance_ball(game_state, dt):
    """Step the ball's flight/bounce for one frame and apply
    whatever outcome that step resolves: out on the full, arrival
    (mark/turnover/contest/score/grounded loose ball), or a boundary
    ball-up."""
    game_state.ball.follow_carrier()
    game_state.ball.advance_bounce(dt)
    was_in_flight = game_state.ball.in_flight
    pre_step_pos = game_state.ball.pos
    arrived = game_state.ball.advance_flight(dt)
    # Out on the full: a kicked ball (never a handball, never a
    # scoring attempt — see attempt_kick/attempt_handball, which
    # only set _kick_in_flight_team for a genuine field kick) that
    # crosses the oval boundary before landing is a free kick to
    # whichever team didn't kick it, taken from the crossing point —
    # checked every frame it's airborne, not just on arrival, so a
    # kick that sails through the boundary well short of its aimed
    # target is still caught the moment it actually crosses, per the
    # real rule (out on the full is about crossing the line in the
    # air, not about where the kick was originally aimed).
    if (was_in_flight and game_state._kick_in_flight_team is not None
            and mechanics.is_out_of_bounds(game_state.ball.x, game_state.ball.y)):
        outcomes.resolve_out_on_the_full(game_state, pre_step_pos, game_state.ball.pos)
    elif arrived:
        if (game_state._kick_in_flight_team is not None
                and game_state._pending_outcome is not None
                and game_state._pending_outcome.get("type") != "score"
                and mechanics.is_out_of_bounds(*game_state.ball.pos)):
            # Landed outside the oval without ever crossing the line
            # mid-flight to trip the check above (a grounded kick
            # landing right on/past the edge, e.g. a missed shot that
            # drifts past the behind post and out) — neutral ball-up,
            # not a free kick, since the ball came down rather than
            # sailing over the line.
            game_state._pending_outcome = None
            game_state._show_message("BALL UP")
            outcomes.start_ruck_contest(game_state, game_state.ball.pos)
        else:
            outcomes.apply_pending_outcome(game_state)
        game_state._kick_in_flight_team = None


def update_pressure_aim_and_camera(game_state, raw_dt):
    """Recompute pressure on this frame's (possibly just-changed by
    advance_ball) carrier, drive the kick-aim cursor while aiming,
    and update the camera focus — grouped together since the
    camera's focus point depends on this same fresh carrier fetch.
    """
    carrier = game_state.carrier
    if carrier is not None:
        opposing = game_state.opponents if carrier.team == settings.YELLOW else game_state.teammates
        game_state.pressure = mechanics.calculate_pressure(carrier, opposing)
    else:
        game_state.pressure = 0.0
    if game_state.mode == MODE_AIMING_KICK:
        # The right stick (if pushed) nudges the cursor incrementally;
        # otherwise the mouse takes over, but only once it's actually
        # moved since last frame — snapping to wherever the OS pointer
        # happens to be sitting on *every* idle frame (the old
        # behavior) fought with the controller for control, since the
        # stick naturally recenters between pushes: the instant it did,
        # the cursor would jump to the physical mouse position, however
        # far away that happened to be, then jump again on the next
        # stick input. enter_aim_mode() resets both the cursor (to
        # dead ahead of the carrier) and _last_mouse_pos (to None) on
        # every fresh entry into this mode, so a stale mouse position
        # from before this aim attempt can't cause that same jump
        # right at the start either.
        rdx, rdy = controller.right_stick()
        mouse_pos = pygame.mouse.get_pos()
        mouse_moved = (game_state._last_mouse_pos is not None
                      and mouse_pos != game_state._last_mouse_pos)
        if rdx or rdy:
            game_state._aim_cursor[0] = max(0, min(settings.WINDOW_W,
                game_state._aim_cursor[0] + rdx * settings.AIM_CURSOR_SPEED * raw_dt))
            game_state._aim_cursor[1] = max(0, min(settings.WINDOW_H,
                game_state._aim_cursor[1] + rdy * settings.AIM_CURSOR_SPEED * raw_dt))
            game_state._aim_input_source = "controller"
        elif mouse_moved:
            game_state._aim_cursor[0], game_state._aim_cursor[1] = mouse_pos
            game_state._aim_input_source = "mouse"
        game_state._last_mouse_pos = mouse_pos
        # Soft aim assist only while the controller is the device
        # actually steering the cursor (see apply_aim_assist) —
        # mouse aiming stays exactly as precise/untouched as before.
        if game_state._aim_input_source == "controller":
            apply_aim_assist(game_state, raw_dt)
        game_state.aim_point = mouse_to_logical(game_state, tuple(game_state._aim_cursor))
    else:
        game_state.aim_point = None
        game_state._last_mouse_pos = None
        game_state._aim_input_source = None

    focus = (game_state.ball.pos if game_state.ball.in_flight
             else (carrier.pos if carrier else game_state.ball.pos))
    game_state.camera.update(raw_dt, focus, game_state.mode == MODE_AIMING_KICK)


def decay_transient_timers(game_state, dt):
    """Decay transient visual timers (real time, not slowed)."""
    if game_state.flash is not None:
        game_state.flash["timer"] -= dt
        if game_state.flash["timer"] <= 0.0:
            game_state.flash = None
    game_state.bounce_tick_timer = max(0.0, game_state.bounce_tick_timer - dt)
    if game_state.message_timer > 0.0:
        game_state.message_timer -= dt
        if game_state.message_timer <= 0.0:
            game_state.message = ""


def time_expired(game_state):
    """The clock hit zero: full time, or a failed scenario."""
    game_state.phase = PHASE_END
    game_state.result = "fulltime" if game_state.game_mode == "full" else "fail"


def update_movement(game_state, dt):
    """Poll held keys to move the controlled player; enforce the
    running-bounce rule against whoever is actually carrying.

    Human (YELLOW) controlled_player only — an AI (RED) carrier is
    driven by ai_control.decide_next_action instead (see
    update_playing), so this no-ops rather than reading keyboard/
    controller input into a RED player. controlled_player is the ball
    carrier whenever YELLOW holds it (unchanged behavior) or a chosen
    defender while YELLOW doesn't (see update_controlled_player /
    switch_controlled_player) — either way this is the one player
    keyboard/controller input drives this frame.
    """
    moved_player = game_state.controlled_player
    game_state.carrier_moving = False
    if moved_player is None or moved_player.team != settings.YELLOW:
        return
    keys = pygame.key.get_pressed()
    cdx, cdy = controller.direction()   # Xbox D-pad / left stick
    dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d] or cdx > 0) - \
         (keys[pygame.K_LEFT] or keys[pygame.K_a] or cdx < 0)
    dy = (keys[pygame.K_DOWN] or keys[pygame.K_s] or cdy > 0) - \
         (keys[pygame.K_UP] or keys[pygame.K_w] or cdy < 0)
    # FULL GAME runs at its own (slower) pace than SCENARIOS — see
    # settings.FULL_GAME_PLAYER_SPEED and entities.Player.move's speed
    # override. The character menu's Speed stat (character_state.py)
    # can move this live, but only once its SAVE action commits the
    # draft into applied_speed (see CharacterState._commit_save) — so
    # tweaking the slider mid-edit doesn't change gameplay until you
    # actually save it, matching the "ALL PLAYERS" apply mode.
    speed = None
    if game_state.game_mode == "full":
        speed = (game_state.character.applied_speed if game_state.character is not None
                 else settings.FULL_GAME_PLAYER_SPEED)
    moved = moved_player.move(dx, dy, dt, speed=speed)
    # carrier_moving/the bounce-rule only mean anything for the actual
    # ball carrier — moving a non-carrying defender around never
    # accrues run-since-bounce or triggers the "ran too far" turnover.
    if not moved_player.is_ball_carrier:
        return
    game_state.carrier_moving = moved > 0.0
    game_state.run_since_bounce += moved

    # Running too far past the bounce limit is a turnover.
    if game_state.run_since_bounce >= settings.BOUNCE_INTERVAL * 1.5:
        nearest = min(game_state.opponents, key=lambda o: o.distance_to(moved_player.pos))
        outcomes.give_possession(game_state, nearest)
        game_state._show_message("RAN TOO FAR - TURNOVER")
        game_state.mode = MODE_IDLE
        outcomes.register_turnover(game_state)


def update_controlled_player(game_state):
    """Keep game_state.controlled_player pointing at the right YELLOW
    player.

    While YELLOW holds the ball, it's always the carrier (today's
    unchanged behavior — regaining the ball, e.g. by gathering a mark
    or winning a contest, means they simply become the carrier and
    controlled_player already points at them via this branch, no
    special-casing needed). While YELLOW doesn't hold it, it stays
    exactly as the human left it (via switch_controlled_player)
    across frames — except on the single frame defense is first
    entered (tracked by _was_carrying), where it resets to the
    nearest teammate to the ball so a stale reference from a previous
    defensive spell, or None on the very first frame, doesn't linger.
    """
    carrier = game_state.carrier
    yellow_carrying = carrier is not None and carrier.team == settings.YELLOW
    if yellow_carrying:
        game_state.controlled_player = carrier
    else:
        entering_defense = game_state._was_carrying or game_state.controlled_player is None
        if entering_defense:
            ball_pos = game_state.ball.pos
            game_state.controlled_player = min(game_state.teammates,
                                         key=lambda t: t.distance_to(ball_pos))
    game_state._was_carrying = yellow_carrying


def switch_controlled_player(game_state):
    """Cycle control to another YELLOW teammate, nearest-next by
    distance to the ball. Only meaningful while YELLOW doesn't hold
    the ball — switching the human's own ball carrier away from
    themselves doesn't apply (matches the FIFA/NBA "play now" style
    this is modelled on: you always drive the ball carrier directly).
    """
    carrier = game_state.carrier
    if carrier is not None and carrier.team == settings.YELLOW:
        return
    teammates = game_state.teammates
    if len(teammates) < 2:
        return
    ball_pos = game_state.ball.pos
    ordered = sorted(teammates, key=lambda t: t.distance_to(ball_pos))
    if game_state.controlled_player not in ordered:
        game_state.controlled_player = ordered[0]
        return
    idx = ordered.index(game_state.controlled_player)
    game_state.controlled_player = ordered[(idx + 1) % len(ordered)]

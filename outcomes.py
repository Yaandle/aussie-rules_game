"""outcomes.py — possession/outcome resolution: what happens once a
kick lands, a tackle triggers, a contest resolves, or a score goes up.

Split out of game_state.py (see AUDIT.md's game_state.py decomposition)
— self-contained: touches possession/score/contest state only, never
menu or camera state. Follows the same convention as mechanics.py/
possession.py/ai_control.py/contest_minigame.py: every function takes
the owning `game_state` object as its first argument rather than being
a GameState method.
"""

import contest_minigame
import mechanics
import possession
import settings
from game_phases import MODE_IDLE, PHASE_END


def apply_pending_outcome(game_state):
    """The ball has landed — apply whatever mechanics decided at launch."""
    outcome, game_state._pending_outcome = game_state._pending_outcome, None
    if outcome is None:
        return

    if outcome["type"] == "possession":
        # A mark or a caught handball: the ball never actually touches
        # the ground, so no cosmetic bounce (see entities.Ball.
        # start_flight / give_to's reset) — it just goes straight to
        # the new carrier's hands, same as always.
        give_possession(game_state, outcome["player"])
        if outcome.get("is_mark") and outcome.get("kick_distance", 0.0) > settings.MARK_STAND_MIN_DISTANCE:
            start_standing_mark(game_state, outcome["player"])

    elif outcome["type"] == "turnover":
        # Only reachable now via a contested mark resolved instantly
        # instead of through the reaction minigame (mode_config's
        # "contests_enabled" off — see gameplay.attempt_kick) where the
        # opposing side won the roll: they caught/took it out of the
        # pack, same as a mark — not a drop, so no ground bounce
        # (compare the "possession" branch above, which doesn't
        # bounce for exactly the same reason: the ball never
        # actually touched the turf here either).
        give_possession(game_state, outcome["player"])
        game_state._show_message("TURNOVER")
        register_turnover(game_state)

    elif outcome["type"] == "contest":
        start_contest(game_state, outcome["candidates"], "loose_ball")

    elif outcome["type"] == "grounded":
        # An inaccurate kick, an accurate kick nobody was there to
        # mark, or a spilled handball — a genuine loose ball, not an
        # instant handoff to "whoever happened to be nearest, however
        # far away" (see start_loose_ball).
        start_loose_ball(game_state)

    elif outcome["type"] == "score":
        apply_score(game_state, outcome["result"], outcome["team"])


def apply_score(game_state, result, team):
    """Register a goal, behind, or miss for whichever team took the
    shot, and check scenario objectives.

    Team-symmetric: an AI (RED) shot updates the same score dict
    under "opp_goals"/"opp_behinds" instead of forking into a
    separate code path — see mode/HUD note below.
    """
    yellow_scored = team == settings.YELLOW
    if result == "goal":
        if yellow_scored:
            game_state.score["goals"] += 1
            game_state._show_message("GOAL - 6 POINTS")
        else:
            game_state.score["opp_goals"] = game_state.score.get("opp_goals", 0) + 1
            game_state._show_message("OPPONENT GOAL")
        game_state.flash = {"color": settings.YELLOW if yellow_scored else settings.RED,
                            "timer": settings.FLASH_DURATION}
    elif result == "behind":
        if yellow_scored:
            game_state.score["behinds"] += 1
            game_state._show_message("BEHIND - 1 POINT")
        else:
            game_state.score["opp_behinds"] = game_state.score.get("opp_behinds", 0) + 1
            game_state._show_message("OPPONENT BEHIND")
        game_state.flash = {"color": settings.BG, "timer": settings.FLASH_DURATION}

    # Scenario objectives are about the human's performance — an AI
    # score never completes or fails one (there's no "concede a
    # score" scenario objective in this pass; see levels.py).
    if game_state.game_mode == "scenario" and yellow_scored:
        objective = game_state.scenario["objective"]
        if objective == "comeback":
            # Not a one-score win — keep playing (fall through to the
            # normal post-score reset below) until the deficit is
            # actually overcome or the clock runs out (time_expired
            # already fails scenarios on timeout).
            target = game_state.scenario.get("away_score_start", 0)
            won = game_state.yellow_points >= target
        else:
            won = (result == "goal" if objective == "goal"
                   else result in ("goal", "behind"))
        if won:
            game_state.phase = PHASE_END
            game_state.result = "win"
            game_state.unlocked = max(game_state.unlocked, game_state.scenario_index + 2)
            return

    if result == "goal":
        reset_to_kickoff(game_state)
        # EXTEND: ruck contest at start of play / after a goal
    elif result == "behind":
        # The defending team kicks out from their goal square (see
        # possession.resolve_behind) instead of the plain center-
        # bounce reset a goal gets.
        possession.resolve_behind(game_state, team)
    else:  # miss → turnover where the ball landed
        defending_team = game_state.opponents if yellow_scored else game_state.teammates
        nearest = min(defending_team, key=lambda p: p.distance_to(game_state.ball.pos))
        give_possession(game_state, nearest)
        game_state._show_message("MISS - TURNOVER")
        register_turnover(game_state)


def register_turnover(game_state):
    """Scenario fail-on-turnover check.

    Possession itself is applied immediately by give_possession
    wherever this is called from — there's no passive delay-then-
    auto-return to the human anymore now that an AI (RED) carrier
    actually plays out its possession (see ai_control.py) instead
    of just holding the spot for TURNOVER_RESET_DELAY seconds.
    """
    if (game_state.game_mode == "scenario"
            and game_state.scenario.get("fail_on_turnover")):
        game_state.phase = PHASE_END
        game_state.result = "fail"


def give_possession(game_state, player):
    """Make the given player the new ball-carrier (either team)."""
    for p in game_state.players:
        p.is_ball_carrier = False
    player.is_ball_carrier = True
    game_state.ball.give_to(player)
    game_state.possession_state = possession.HELD_PLAYER
    game_state.run_since_bounce = 0.0
    game_state.possession_held_timer = 0.0


def start_loose_ball(game_state):
    """The ball has hit the ground with nobody there to mark it (see
    mechanics.resolve_kick's "grounded" result / a spilled handball)
    — clear possession entirely and set it bouncing/rolling at its
    current position (already the landing spot — see gameplay.advance_ball,
    which calls this only right after Ball.advance_flight just set
    x/y there) instead of handing it to "whoever's nearest, however
    far away." possession.LOOSE_BALL then drives gameplay.update_loose_ball
    every frame until someone actually reaches it.
    """
    for p in game_state.players:
        p.is_ball_carrier = False
    game_state.ball.possessed_by = None
    game_state.possession_state = possession.LOOSE_BALL
    game_state.ball.start_bounce(game_state.ball.flight_distance)
    game_state._show_message("LOOSE BALL")


def start_standing_mark(game_state, marker):
    """A mark taken from beyond MARK_STAND_MIN_DISTANCE freezes the
    nearest opponent to the marker at their current spot and shields
    the marker from a tackle trigger, both for MARK_HOLD_DURATION
    seconds (see settings.py). No-ops if the marker's team has no
    opponents on field (can't happen in practice, but keeps this
    symmetric/safe the way give_possession's callers already are)."""
    opposing = game_state.opponents if marker.team == settings.YELLOW else game_state.teammates
    if not opposing:
        game_state.standing_mark = None
        return
    defender = min(opposing, key=lambda o: o.distance_to(marker.pos))
    game_state.standing_mark = {
        "marker": marker,
        "defender": defender,
        "timer": settings.MARK_HOLD_DURATION,
    }


def resolve_out_on_the_full(game_state, pre_step_pos, out_pos):
    """A kicked ball just crossed the oval boundary mid-flight without
    landing/being marked/contested first — free kick to whichever
    team didn't kick it (see game_state._kick_in_flight_team, set only
    for a genuine field kick in gameplay.attempt_kick), taken from
    where it crossed (mechanics.boundary_crossing_point bisects this
    frame's travel segment for that point).

    Ends the ball's flight outright (whatever _pending_outcome was
    queued for its original landing spot is discarded — the kick
    never actually arrives now) and hands it to the nearest opponent
    of the kicking team at the crossing spot, same "nearest player
    takes the free kick" idea as resolve_behind's kickout.
    """
    kicking_team = game_state._kick_in_flight_team
    game_state._kick_in_flight_team = None
    game_state._pending_outcome = None
    crossing = mechanics.boundary_crossing_point(pre_step_pos, out_pos)
    receiving_team = game_state.opponents if kicking_team == settings.YELLOW else game_state.teammates
    if not receiving_team:
        return
    taker = min(receiving_team, key=lambda p: p.distance_to(crossing))
    taker.x, taker.y = mechanics.clamp_to_oval(*crossing)
    give_possession(game_state, taker)
    game_state._show_message("OUT ON THE FULL - FREE KICK")


def resolve_tackle_now(game_state, participants):
    """Resolve a tackle trigger instantly (see mechanics.resolve_tackle) —
    no reaction minigame, no possession_state detour through
    IN_CONTEST: the whole thing resolves and separates within this
    one call, same frame.

    `participants` is [carrier, defender] (see
    possession.find_tackle_trigger). Any in-progress kick-aim drops
    the same way a contest used to force it to: a tackle can land
    mid-aim, and who's carrying can change as a result, so a stale
    MODE_AIMING_KICK pointing at the old carrier/target must not
    survive into that.
    """
    carrier, defender = participants[0], participants[1]
    game_state.mode = MODE_IDLE
    result = mechanics.resolve_tackle(game_state.possession_held_timer)
    if result == "no_prior_opportunity":
        game_state._show_message("BALL UP")
        start_ruck_contest(game_state, carrier.pos)
    elif result == "broken":
        game_state._show_message("TACKLE BROKEN")
        # Carrier keeps the ball outright — no give_possession call
        # (that would also reset possession_held_timer, which should
        # keep counting: they're still the same carry, just shrugged
        # off a tackle partway through it).
    else:  # "holding_the_ball" — free kick to the tackler
        game_state._show_message("HOLDING THE BALL - FREE KICK")
        give_possession(game_state, defender)
    separate_after_contest(game_state, participants)
    game_state.tackle_cooldown = settings.POST_TACKLE_COOLDOWN


def start_contest(game_state, participants, kind):
    """Freeze play and begin a loose-ball/50-50/ruck reaction contest
    between exactly two players (see contest_minigame.py). Tackles no
    longer route through here — see resolve_tackle_now, which
    resolves a tackle instantly instead.

    Also drops any in-progress kick-aim: a contest can interrupt the
    human mid-aim, and whoever's carrying can change once it
    resolves — a stale MODE_AIMING_KICK left pointing at the old aim
    target/carrier must not survive into that.
    """
    game_state.active_contest = contest_minigame.start(participants, kind)
    game_state.possession_state = possession.IN_CONTEST
    game_state._contest_direction_queue = []
    game_state.mode = MODE_IDLE


def start_ruck_contest(game_state, spot):
    """A neutral ball-up: the nearest player from each team to `spot`
    contests it (see contest_minigame's "ruck" kind / field_render's
    "BALL UP!" label). Used for both a tackle with no prior
    opportunity (resolve_tackle_now) and the ball rolling out of
    bounds without going out on the full (gameplay.advance_ball's
    ball-up branch — see mechanics.is_out_of_bounds).

    Falls back to handing whichever team has a nearer player the
    ball outright if the other team has nobody at all on field (not
    possible with a full roster, but keeps this safe the way
    start_standing_mark already is for its own edge case).
    """
    nearest_yellow = min(game_state.teammates, key=lambda p: p.distance_to(spot),
                         default=None)
    nearest_red = min(game_state.opponents, key=lambda p: p.distance_to(spot),
                      default=None)
    if nearest_yellow is None:
        give_possession(game_state, nearest_red)
        return
    if nearest_red is None:
        give_possession(game_state, nearest_yellow)
        return
    game_state.ball.x, game_state.ball.y = spot
    game_state.ball.start_bounce(0.0)   # a short, low hop — the ball's already
                                          # down, this just reads as it settling
                                          # at the spot rather than a hard cut
    start_contest(game_state, [nearest_yellow, nearest_red], "ruck")


def update_contest(game_state, dt):
    """Advance the live contest one frame; apply its result once
    resolved (winner keeps/gains possession outright — see the
    design note in contest_minigame.py on loose_ball/ruck outcomes).
    Tackles no longer reach this path at all — see
    resolve_tackle_now, which resolves and separates instantly in
    one call instead of going through active_contest/IN_CONTEST.

    A resolved contest leaves its two participants standing right
    next to each other — without separating them, the very next
    frame's checks could see the same pair still in range and start
    something new immediately, forever. separate_after_contest
    pushes them apart and a short game_state.contest_cooldown holds off
    re-triggering, so the winner gets an actual window of play
    before another contest can start.
    """
    human_inputs, game_state._contest_direction_queue = game_state._contest_direction_queue, []
    contest_minigame.update(game_state.active_contest, dt, human_inputs)
    if game_state.active_contest.resolved:
        contest, game_state.active_contest = game_state.active_contest, None
        game_state.possession_state = possession.HELD_PLAYER
        if contest.winner is not None:
            give_possession(game_state, contest.winner)
        separate_after_contest(game_state, contest.participants)
        game_state.contest_cooldown = settings.CONTEST_COOLDOWN


def separate_after_contest(game_state, participants):
    """Push a resolved contest's two participants apart to just
    beyond TACKLE_TRIGGER_RADIUS (see update_contest) instead of
    leaving them standing on top of each other. Shares its actual
    push math with mechanics.separate_players via mechanics.push_apart
    (see that function's docstring)."""
    if len(participants) < 2:
        return
    a, b = participants[0], participants[1]
    target_gap = settings.TACKLE_TRIGGER_RADIUS * settings.POST_CONTEST_SEPARATION_MULT
    mechanics.push_apart(a, b, target_gap)


def reset_to_kickoff(game_state):
    """Return everyone to the current mode's opening layout after a score."""
    keep = (game_state.score, game_state.timer, game_state.flash,
            game_state.message, game_state.message_timer)
    game_state._load_layout(game_state._current_layout)
    (game_state.score, game_state.timer, game_state.flash,
     game_state.message, game_state.message_timer) = keep

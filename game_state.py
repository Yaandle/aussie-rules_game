"""game_state.py — owns all mutable game state and interprets input.

GameState runs a small phase machine:
  PHASE_MENU    — main menu / scenario select (render draws the menus)
  PHASE_PLAYING — a match or scenario in progress
  PHASE_END     — result overlay (win / fail / full time) with retry flow

It calls into mechanics.py for every probabilistic resolution and never
draws anything itself (render.py reads from it instead).
"""

import math

import pygame

import hero_levels
import levels
import mechanics
import settings
from character_state import CharacterState
from entities import Ball, Player
from goalkick_state import GoalKickState
from hero_camera import HeroCamera
from hero_state import HeroState

# Input modes (while playing)
MODE_IDLE = "idle"
MODE_AIMING_KICK = "aiming_kick"

# App phases
PHASE_MENU = "menu"
PHASE_PLAYING = "playing"
PHASE_END = "end"
PHASE_HERO = "hero"
PHASE_GOALKICK = "goalkick"
# The character customization menu — hotkey-triggered (K_c), reachable from
# PHASE_MENU or PHASE_PLAYING and never listed in ROOT_OPTIONS/SCREEN_ROOT;
# see GameState._open_character / _character_input / _update_character.
PHASE_CHARACTER = "character"

# Menu screens and options
SCREEN_ROOT = "root"
SCREEN_SCENARIOS = "scenarios"
SCREEN_HERO = "hero_select"
ROOT_OPTIONS = ("FULL GAME", "SCENARIOS", "AFL HERO", "GOAL KICKING", "QUIT")

# ── FULL GAME formation ──────────────────────────────────────────────
# Six standard AFL lines (16 on-field a side — interchange isn't modelled
# yet; trimmed from 18 by dropping one slot each from centre/followers
# below, part of the FULL GAME retune alongside settings.
# FULL_GAME_PLAYER_SPEED / MAIN_SPRITE_SCALE / FIELD_MARGIN_*). Each line
# is a "depth" — 0.0 at a team's own goal, 1.0 at the goal they're
# attacking — plus a tuple of lateral "slots": how far across the ground
# each player sits (-1..1, as a fraction of the oval's local half-width
# at that depth) and a small depth "nudge" so flanks sit in a shallow
# curve rather than a dead-straight rank. Purely a data table — neither
# _line_positions nor _build_team_formation hardcodes a slot count, so a
# designer can retune the whole formation (including its size) by editing
# the numbers below; nothing is randomized.
FORMATION_LINES = (
    # name,            depth,  slots: (lateral fraction, depth nudge)
    ("full_back",     0.06,  ((-0.62,  0.02), (0.0,  0.0), (0.62,  0.02))),
    ("half_back",     0.28,  ((-0.68,  0.02), (0.0,  0.0), (0.68,  0.02))),
    ("centre",        0.50,  ((-0.85,  0.0),  (0.85,  0.0))),
    ("followers",     0.50,  (( 0.06, -0.02), (-0.20, -0.035))),
    ("half_forward",  0.72,  ((-0.68, -0.02), (0.0,  0.0), (0.68, -0.02))),
    ("full_forward",  0.94,  ((-0.62, -0.02), (0.0,  0.0), (0.62, -0.02))),
)


def _line_positions(depth, slots, attack_positive):
    """World (x, y) for one formation line.

    `depth` runs 0 (own goal) -> 1 (attacking goal); a team attacking +x
    (YELLOW) reads it directly, a team attacking -x (RED) mirrors it
    (1 - depth) so both sides face off across the centre with the same
    shape. Lateral fractions are scaled by the oval's local half-width
    at that depth (narrower near the goals than at the centre), with a
    safety inset so nobody generates outside the boundary.
    """
    positions = []
    for lateral_frac, nudge in slots:
        d = depth + nudge
        x_frac = d if attack_positive else 1.0 - d
        x = settings.FIELD_LEFT + x_frac * settings.FIELD_W

        t = max(-0.999, min(0.999, (x - settings.FIELD_CX) / (settings.FIELD_W / 2)))
        half_width = (settings.FIELD_H / 2) * math.sqrt(1.0 - t * t)
        y = settings.FIELD_CY + lateral_frac * half_width * 0.82
        positions.append((x, y))
    return positions


def _build_team_formation(attack_positive):
    """All 16 on-field spots for one team, kickoff carrier first.

    The carrier ends up at index 0 of the returned list because
    _load_layout always hands the ball to players[0] — here that's the
    lead follower (the "rover" slot), standing in for winning the
    imaginary opening centre clearance, rather than a fixed fullback.
    """
    lines = {name: _line_positions(depth, slots, attack_positive)
             for name, depth, slots in FORMATION_LINES}
    carrier, *other_followers = lines["followers"]
    ordered = [carrier] + other_followers
    for name in ("full_back", "half_back", "centre", "half_forward", "full_forward"):
        ordered.extend(lines[name])
    return ordered


def _build_full_game_layout():
    """Programmatic 16-a-side FULL GAME kickoff layout (see
    FORMATION_LINES) — both teams share the same formation shape,
    mirrored front-to-back so they face off across the centre (YELLOW
    attacks +x, RED attacks -x; settings.GOAL_RIGHT / GOAL_LEFT)."""
    return {
        "yellow": _build_team_formation(attack_positive=True),
        "red": _build_team_formation(attack_positive=False),
    }


# Default kickoff layout for full game mode.
FULL_GAME_LAYOUT = _build_full_game_layout()

# EXTEND: multi-quarter match structure
# EXTEND: two controllable teams in full game mode
# EXTEND: interchange bench (currently on-field 16s only)


class GameState:
    """Single source of truth for menus, matches, and scenario missions."""

    def __init__(self):
        # Phase machine / menu state.
        self.phase = PHASE_MENU
        self.menu_screen = SCREEN_ROOT
        self.menu_index = 0
        self.unlocked = 1                # how many scenarios are playable
        self.hero = None                 # active HeroState (AFL Hero mode)
        self.hero_unlocked = 1           # how many hero levels are playable
        self.goalkick = None             # active GoalKickState (GOAL KICKING mode)
        self.character = None            # active CharacterState (CHARACTER MENU)
        self._pre_character_phase = None  # phase to restore on exit

        # Mode context.
        self.game_mode = None            # "full" | "scenario"
        self.scenario = None             # active levels.SCENARIOS entry
        self.scenario_index = 0
        self.result = None               # "win" | "fail" | "fulltime"

        # Gameplay state exists from the start so render can always read it.
        self._load_layout(FULL_GAME_LAYOUT)
        self.timer = settings.QUARTER_LENGTH
        self.score = {"goals": 0, "behinds": 0}

    # ── Setup / loading ─────────────────────────────────────────────

    def _load_layout(self, layout):
        """(Re)build players and ball from a layout dict; reset transient state."""
        self._current_layout = layout
        yellow = [Player(x, y, settings.YELLOW) for (x, y) in layout["yellow"]]
        red = [Player(x, y, settings.RED) for (x, y) in layout["red"]]
        self.players = yellow + red
        # Kickoff spot per player, used by the FULL GAME off-ball AI to
        # hold rough formation shape (see mechanics.update_off_ball).
        self._home_positions = {id(p): p.pos for p in self.players}
        carrier = self.players[0]
        carrier.is_ball_carrier = True
        self.ball = Ball(carrier.x, carrier.y)
        self.ball.give_to(carrier)
        # Both classic modes share AFL Hero's diorama presentation, but use
        # their own camera tuning (settings.MAIN_CAM_*) for a slightly more
        # vertical, more fixed "broadcast" feel that differs from Hero mode.
        self.camera = HeroCamera(
            carrier.pos,
            back=settings.MAIN_CAM_BACK,
            height=settings.MAIN_CAM_HEIGHT,
            focal=settings.MAIN_CAM_FOCAL,
            zoom_mult=settings.MAIN_CAM_ZOOM,
            lerp=settings.MAIN_CAM_LERP,
            horizon_y=settings.MAIN_HORIZON_Y,
        )

        self.mode = MODE_IDLE
        self.run_since_bounce = 0.0
        self.pressure = 0.0
        self.aim_point = None
        self.show_menu = False
        self.carrier_moving = False
        self._pending_outcome = None
        self._turnover_timer = 0.0
        self.flash = None
        self.bounce_tick_timer = 0.0
        self.message = ""
        self.message_timer = 0.0

    def start_full_game(self):
        """Begin a single free-play quarter."""
        self.game_mode = "full"
        self.scenario = None
        self.result = None
        self._load_layout(FULL_GAME_LAYOUT)
        self.timer = settings.QUARTER_LENGTH
        self.score = {"goals": 0, "behinds": 0}
        self.phase = PHASE_PLAYING

    def start_scenario(self, index):
        """Begin one designed football moment from levels.py."""
        self.game_mode = "scenario"
        self.scenario_index = index
        self.scenario = levels.SCENARIOS[index]
        self.result = None
        self._load_layout(self.scenario)
        self.timer = self.scenario["time_limit"]
        self.score = {"goals": 0, "behinds": 0}
        self.phase = PHASE_PLAYING
        # A one-off briefing so each scenario reads as a specific match
        # situation rather than an abstract puzzle — reuses the same HUD
        # message plate as every in-play event (see field_render's HUD),
        # just held onscreen longer since it's a full sentence.
        situation = self.scenario.get("situation")
        if situation:
            self._show_message(situation, duration=4.5)

    def start_hero(self, index):
        """Begin one AFL Hero level (swipe-based possession puzzle)."""
        self.hero = HeroState(index)
        self.phase = PHASE_HERO

    def start_goal_kicking(self):
        """Begin the GOAL KICKING practice range — freeform, no level
        list, so this jumps straight in like start_full_game does."""
        self.goalkick = GoalKickState()
        self.phase = PHASE_GOALKICK

    # ── CHARACTER MENU (K_c hotkey, not a ROOT_OPTIONS entry) ────────

    def _open_character(self):
        """Enter the character menu, remembering whichever phase was
        active so ESC / the hotkey again restores it instead of always
        dropping back to the root menu. Adjustments made on a previous
        visit (self.character) persist — this is a live attributes
        screen, not a level select, so there's nothing to reset."""
        if self.character is None:
            self.character = CharacterState()
        else:
            self.character.reset_transition_in()
        self._pre_character_phase = self.phase
        self.phase = PHASE_CHARACTER

    def _request_close_character(self):
        """Start the covering half of the pixel wipe; _update_character
        flips the phase back once it finishes (see CharacterState's
        transition_dir/exit_ready)."""
        if self.character is not None:
            self.character.request_exit(self._pre_character_phase or PHASE_MENU)

    def _character_input(self, event):
        if self.character is None:
            self.phase = PHASE_MENU
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            # On the main attributes screen, ESC closes the whole menu;
            # on any screen nested under it (roster / naming / the save
            # prompt), ESC steps back one level instead (see
            # CharacterState.back()).
            if self.character.screen == "attributes":
                self._request_close_character()
            else:
                self.character.back()
            return
        self.character.handle_input(event)

    # ── Convenience accessors ───────────────────────────────────────

    @property
    def teammates(self):
        return [p for p in self.players if p.team == settings.YELLOW]

    @property
    def opponents(self):
        return [p for p in self.players if p.team == settings.RED]

    @property
    def carrier(self):
        for p in self.players:
            if p.is_ball_carrier:
                return p
        return None

    @property
    def yellow_points(self):
        return self.score["goals"] * 6 + self.score["behinds"]

    @property
    def must_bounce(self):
        return self.run_since_bounce >= settings.BOUNCE_INTERVAL

    @property
    def game_over(self):
        return self.phase != PHASE_PLAYING

    @property
    def in_slowmo(self):
        """True while the slow-motion decision mode is active."""
        return self.phase == PHASE_PLAYING and self.mode == MODE_AIMING_KICK

    # ── Input dispatch ──────────────────────────────────────────────

    def handle_input(self, event):
        """Route one Pygame event to the active phase's handler.

        The CHARACTER MENU hotkey (K_c) is checked ahead of the normal
        phase dispatch so it's reachable from PHASE_MENU or mid-match
        (PHASE_PLAYING), the same way M already opens the controls
        overlay during a match. `C` doesn't collide with any existing
        binding (see _playing_input / GoalKickState.handle_input).
        """
        if event.type == pygame.KEYDOWN and event.key == pygame.K_c:
            # While typing a new saved player's name, "C" is a letter to
            # type, not the menu hotkey — let it fall through to the
            # normal PHASE_CHARACTER dispatch below instead of closing.
            naming = (self.phase == PHASE_CHARACTER and self.character is not None
                     and self.character.screen == "naming")
            if not naming:
                if self.phase == PHASE_CHARACTER:
                    self._request_close_character()
                    return
                if self.phase in (PHASE_MENU, PHASE_PLAYING):
                    self._open_character()
                    return

        if self.phase == PHASE_MENU:
            self._menu_input(event)
        elif self.phase == PHASE_CHARACTER:
            self._character_input(event)
        elif self.phase == PHASE_HERO:
            if self.hero is not None:
                self.hero.handle_input(event)
        elif self.phase == PHASE_GOALKICK:
            if self.goalkick is not None:
                self.goalkick.handle_input(event)
        elif self.phase == PHASE_END:
            self._end_input(event)
        else:
            self._playing_input(event)

    # ── Menu input ──────────────────────────────────────────────────

    def _menu_options(self):
        """The entries on the current menu screen."""
        if self.menu_screen == SCREEN_ROOT:
            return list(ROOT_OPTIONS)
        if self.menu_screen == SCREEN_HERO:
            return [lv["name"] for lv in hero_levels.HERO_LEVELS] + ["BACK"]
        return [s["name"] for s in levels.SCENARIOS] + ["BACK"]

    def _menu_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        options = self._menu_options()
        if event.key in (pygame.K_UP, pygame.K_w):
            self.menu_index = (self.menu_index - 1) % len(options)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.menu_index = (self.menu_index + 1) % len(options)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._menu_select()
        elif event.key == pygame.K_ESCAPE and self.menu_screen != SCREEN_ROOT:
            back_index = 2 if self.menu_screen == SCREEN_HERO else 1
            self.menu_screen = SCREEN_ROOT
            self.menu_index = back_index

    def _menu_select(self):
        if self.menu_screen == SCREEN_ROOT:
            if self.menu_index == 0:
                self.start_full_game()
            elif self.menu_index == 1:
                self.menu_screen = SCREEN_SCENARIOS
                self.menu_index = 0
            elif self.menu_index == 2:
                self.menu_screen = SCREEN_HERO
                self.menu_index = 0
            elif self.menu_index == 3:
                self.start_goal_kicking()
            else:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
        elif self.menu_screen == SCREEN_HERO:
            if self.menu_index >= len(hero_levels.HERO_LEVELS):   # BACK
                self.menu_screen = SCREEN_ROOT
                self.menu_index = 2
            elif self.menu_index < self.hero_unlocked:
                self.start_hero(self.menu_index)
        else:
            if self.menu_index >= len(levels.SCENARIOS):      # BACK entry
                self.menu_screen = SCREEN_ROOT
                self.menu_index = 1
            elif self.menu_index < self.unlocked:             # locked ones ignore
                self.start_scenario(self.menu_index)

    # ── End-screen input ────────────────────────────────────────────

    def _end_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_r:
            if self.game_mode == "scenario":
                self.start_scenario(self.scenario_index)
            else:
                self.start_full_game()
        elif event.key == pygame.K_RETURN:
            nxt = self.scenario_index + 1
            if (self.result == "win" and self.game_mode == "scenario"
                    and nxt < len(levels.SCENARIOS) and nxt < self.unlocked):
                self.start_scenario(nxt)
        elif event.key == pygame.K_ESCAPE:
            self.phase = PHASE_MENU
            self.menu_screen = SCREEN_ROOT
            self.menu_index = 0

    # ── Playing input ───────────────────────────────────────────────

    def _playing_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_m:
                self.show_menu = not self.show_menu
                return
            if event.key == pygame.K_ESCAPE:
                if self.mode == MODE_AIMING_KICK:
                    self.mode = MODE_IDLE
                else:
                    self.show_menu = not self.show_menu
                return
            if self.show_menu:
                if event.key == pygame.K_BACKSPACE:   # quit to main menu
                    self.phase = PHASE_MENU
                    self.menu_screen = SCREEN_ROOT
                    self.menu_index = 0
                return
            if event.key in (pygame.K_1, pygame.K_q):
                self._attempt_handball()
            elif event.key in (pygame.K_2, pygame.K_k):
                if self.carrier is not None and not self.ball.in_flight:
                    self.mode = MODE_AIMING_KICK
            elif event.key in (pygame.K_3, pygame.K_SPACE):
                self._bounce()

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.mode == MODE_AIMING_KICK and not self.show_menu:
                target = self._mouse_to_logical(event.pos)
                if target is not None:
                    self._attempt_kick(target)

    def _mouse_to_logical(self, screen_pos):
        """Unproject a window click through the diorama camera onto the
        field's ground plane. None when the click is above the horizon."""
        return self.camera.unproject(*screen_pos)

    # ── Actions ─────────────────────────────────────────────────────

    def _attempt_handball(self):
        """Handball to the nearest teammate in range; resolves via mechanics."""
        carrier = self.carrier
        if carrier is None or self.ball.in_flight:
            return
        receivers = [t for t in self.teammates
                     if t is not carrier
                     and t.distance_to(carrier.pos) <= settings.HANDBALL_RANGE]
        if not receivers:
            self._show_message("NO TARGET")
            return
        target = min(receivers, key=lambda t: t.distance_to(carrier.pos))
        pressure = mechanics.calculate_pressure(carrier, self.opponents)
        outcome = mechanics.resolve_handball(carrier, target, pressure)

        carrier.is_ball_carrier = False
        self.ball.start_flight(carrier.pos, target.pos)
        if outcome["success"]:
            self._pending_outcome = {"type": "possession", "player": target}
        else:
            spill = min(self.opponents, key=lambda o: o.distance_to(target.pos))
            self._pending_outcome = {"type": "turnover", "player": spill}
        self.mode = MODE_IDLE

    def _attempt_kick(self, target_point):
        """Kick toward a clicked point: shot on goal or a field kick."""
        carrier = self.carrier
        if carrier is None or self.ball.in_flight:
            return
        if carrier.distance_to(target_point) > settings.KICK_MAX_RANGE:
            self._show_message("TOO FAR")
            return

        pressure = mechanics.calculate_pressure(carrier, self.opponents)

        if mechanics.is_scoring_attempt(carrier.pos, target_point, settings.GOAL_RIGHT):
            result = mechanics.resolve_scoring_attempt(carrier.pos, target_point)
            self._pending_outcome = {"type": "score", "result": result}
        else:
            outcome = mechanics.resolve_kick(carrier, target_point, self.opponents,
                                             self.teammates, pressure)
            if outcome["winner"].team == settings.YELLOW:
                self._pending_outcome = {"type": "possession",
                                         "player": outcome["winner"]}
            else:
                self._pending_outcome = {"type": "turnover",
                                         "player": outcome["winner"]}

        carrier.is_ball_carrier = False
        self.ball.start_flight(carrier.pos, target_point)
        self.mode = MODE_IDLE

    def _bounce(self):
        """Bounce the ball to legally continue running (resets the run meter)."""
        if self.carrier is None or self.ball.in_flight:
            return
        self.run_since_bounce = 0.0
        self.bounce_tick_timer = settings.BOUNCE_TICK_DURATION

    # ── Update loop ─────────────────────────────────────────────────

    def update(self, dt):
        """Advance timers, movement, AI, ball flight, and pending resolutions."""
        if self.phase == PHASE_HERO:
            self._update_hero(dt)
            return
        if self.phase == PHASE_GOALKICK:
            self._update_goalkick(dt)
            return
        if self.phase == PHASE_CHARACTER:
            self._update_character(dt)
            return
        if self.phase != PHASE_PLAYING or self.show_menu:
            return

        # Slow-motion decision mode: the whole world breathes slower
        # while a kick is being lined up. The camera keeps real time so
        # its follow and zoom stay smooth through the dilation.
        raw_dt = dt
        if self.mode == MODE_AIMING_KICK:
            dt *= settings.SLOWMO_FACTOR

        self.timer = max(0.0, self.timer - dt)
        if self.timer <= 0.0:
            self._time_expired()
            return

        self._update_movement(dt)

        # Closing defenders converge while someone holds the ball. In
        # FULL GAME (not scenarios — see FORMATION_LINES/_load_layout
        # comments) the rest of both sides also ease toward their
        # kickoff formation shape, blended toward the ball, so a
        # 16-a-side roster doesn't stand frozen off the ball.
        carrier = self.carrier
        if carrier is not None:
            home = self._home_positions if self.game_mode == "full" else None
            mechanics.update_defenders(self.opponents, carrier.pos, dt, home)
            if home is not None:
                resting = [t for t in self.teammates if not t.is_ball_carrier]
                mechanics.update_off_ball(resting, home, carrier.pos, dt)

        self.ball.follow_carrier()
        if self.ball.advance_flight(dt):
            self._apply_pending_outcome()

        if self._turnover_timer > 0.0:
            self._turnover_timer -= dt
            if self._turnover_timer <= 0.0:
                self._reset_after_turnover()

        carrier = self.carrier
        self.pressure = (mechanics.calculate_pressure(carrier, self.opponents)
                         if carrier else 0.0)
        if self.mode == MODE_AIMING_KICK:
            self.aim_point = self._mouse_to_logical(pygame.mouse.get_pos())
        else:
            self.aim_point = None

        focus = (self.ball.pos if self.ball.in_flight
                 else (carrier.pos if carrier else self.ball.pos))
        self.camera.update(raw_dt, focus, self.mode == MODE_AIMING_KICK)

        # Decay transient visual timers (real time, not slowed).
        if self.flash is not None:
            self.flash["timer"] -= dt
            if self.flash["timer"] <= 0.0:
                self.flash = None
        self.bounce_tick_timer = max(0.0, self.bounce_tick_timer - dt)
        if self.message_timer > 0.0:
            self.message_timer -= dt
            if self.message_timer <= 0.0:
                self.message = ""

    def _update_hero(self, dt):
        """Drive the active Hero level; harvest unlocks and exit requests."""
        if self.hero is None:
            self.phase = PHASE_MENU
            return
        self.hero.update(dt)
        if self.hero.result == "win":
            self.hero_unlocked = max(self.hero_unlocked,
                                     self.hero.level_index + 2)
        request, self.hero.exit_request = self.hero.exit_request, None
        if request == "menu":
            self.phase = PHASE_MENU
            self.menu_screen = SCREEN_HERO
            self.menu_index = self.hero.level_index
        elif request == "next":
            nxt = self.hero.level_index + 1
            if nxt < len(hero_levels.HERO_LEVELS) and nxt < self.hero_unlocked:
                self.start_hero(nxt)

    def _update_goalkick(self, dt):
        """Drive the GOAL KICKING practice range; harvest exit requests.

        Freeform, no unlocks to track — unlike _update_hero there's
        nothing to do here but forward the update and watch for "menu".
        """
        if self.goalkick is None:
            self.phase = PHASE_MENU
            return
        self.goalkick.update(dt)
        request, self.goalkick.exit_request = self.goalkick.exit_request, None
        if request == "menu":
            self.phase = PHASE_MENU
            self.menu_screen = SCREEN_ROOT
            self.menu_index = 3

    def _update_character(self, dt):
        """Drive the character menu's transition timer; hand the phase
        back to wherever it was opened from once the covering wipe
        finishes (see CharacterState.request_exit / exit_ready)."""
        if self.character is None:
            self.phase = PHASE_MENU
            return
        self.character.update(dt)
        if self.character.exit_ready:
            self.phase = self.character.pending_exit_phase or PHASE_MENU
            self._pre_character_phase = None

    def _time_expired(self):
        """The clock hit zero: full time, or a failed scenario."""
        self.phase = PHASE_END
        self.result = "fulltime" if self.game_mode == "full" else "fail"

    def _update_movement(self, dt):
        """Poll held keys to move the carrier; enforce the running-bounce rule."""
        carrier = self.carrier
        self.carrier_moving = False
        if carrier is None:
            return
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - \
             (keys[pygame.K_LEFT] or keys[pygame.K_a])
        dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - \
             (keys[pygame.K_UP] or keys[pygame.K_w])
        # FULL GAME runs at its own (slower) pace than SCENARIOS — see
        # settings.FULL_GAME_PLAYER_SPEED and entities.Player.move's speed
        # override. The character menu's Speed stat (character_state.py)
        # can move this live, but only once its SAVE action commits the
        # draft into applied_speed (see CharacterState._commit_save) — so
        # tweaking the slider mid-edit doesn't change gameplay until you
        # actually save it, matching the "ALL PLAYERS" apply mode.
        speed = None
        if self.game_mode == "full":
            speed = (self.character.applied_speed if self.character is not None
                     else settings.FULL_GAME_PLAYER_SPEED)
        moved = carrier.move(dx, dy, dt, speed=speed)
        self.carrier_moving = moved > 0.0
        self.run_since_bounce += moved

        # Running too far past the bounce limit is a turnover.
        if self.run_since_bounce >= settings.BOUNCE_INTERVAL * 1.5:
            nearest = min(self.opponents, key=lambda o: o.distance_to(carrier.pos))
            carrier.is_ball_carrier = False
            self.ball.give_to(nearest)
            self._show_message("RAN TOO FAR - TURNOVER")
            self.run_since_bounce = 0.0
            self.mode = MODE_IDLE
            self._register_turnover()

    # ── Outcome application ─────────────────────────────────────────

    def _apply_pending_outcome(self):
        """The ball has landed — apply whatever mechanics decided at launch."""
        outcome, self._pending_outcome = self._pending_outcome, None
        if outcome is None:
            return

        if outcome["type"] == "possession":
            self._give_possession(outcome["player"])
            self.run_since_bounce = 0.0

        elif outcome["type"] == "turnover":
            self.ball.give_to(outcome["player"])
            self._show_message("TURNOVER")
            self._register_turnover()

        elif outcome["type"] == "score":
            self._apply_score(outcome["result"])

    def _apply_score(self, result):
        """Register a goal, behind, or miss; check scenario objectives."""
        if result == "goal":
            self.score["goals"] += 1
            self.flash = {"color": settings.YELLOW, "timer": settings.FLASH_DURATION}
            self._show_message("GOAL - 6 POINTS")
        elif result == "behind":
            self.score["behinds"] += 1
            self.flash = {"color": settings.BG, "timer": settings.FLASH_DURATION}
            self._show_message("BEHIND - 1 POINT")

        # Scenario objectives resolve before any restart.
        if self.game_mode == "scenario":
            objective = self.scenario["objective"]
            if objective == "comeback":
                # Not a one-score win — keep playing (fall through to the
                # normal post-score reset below) until the deficit is
                # actually overcome or the clock runs out (_time_expired
                # already fails scenarios on timeout).
                target = self.scenario.get("away_score_start", 0)
                won = self.yellow_points >= target
            else:
                won = (result == "goal" if objective == "goal"
                       else result in ("goal", "behind"))
            if won:
                self.phase = PHASE_END
                self.result = "win"
                self.unlocked = max(self.unlocked, self.scenario_index + 2)
                return

        if result in ("goal", "behind"):
            self._reset_to_kickoff()
            # EXTEND: ruck contest at start of play / after a goal
        else:  # miss → turnover where the ball landed
            nearest = min(self.opponents,
                          key=lambda o: o.distance_to(self.ball.pos))
            self.ball.give_to(nearest)
            self._show_message("MISS - TURNOVER")
            self._register_turnover()

    def _register_turnover(self):
        """Shared turnover handling: scenario fail check, then the reset timer."""
        if (self.game_mode == "scenario"
                and self.scenario.get("fail_on_turnover")):
            self.phase = PHASE_END
            self.result = "fail"
            return
        self._turnover_timer = settings.TURNOVER_RESET_DELAY

    def _give_possession(self, player):
        """Make the given YELLOW player the new ball-carrier."""
        for p in self.players:
            p.is_ball_carrier = False
        player.is_ball_carrier = True
        self.ball.give_to(player)

    def _reset_after_turnover(self):
        """RED's passive possession ends: restart with the nearest YELLOW player.

        A stand-in for real turnover play until RED can attack.
        """
        nearest = min(self.teammates,
                      key=lambda t: t.distance_to(self.ball.pos))
        self._give_possession(nearest)
        self.run_since_bounce = 0.0

    def _reset_to_kickoff(self):
        """Return everyone to the current mode's opening layout after a score."""
        keep = (self.score, self.timer, self.flash,
                self.message, self.message_timer)
        self._load_layout(self._current_layout)
        (self.score, self.timer, self.flash,
         self.message, self.message_timer) = keep

    # ── Small helpers ───────────────────────────────────────────────

    def _show_message(self, text, duration=2.0):
        """Show a HUD message for `duration` seconds (default matches
        every existing short event message; start_scenario passes a
        longer one for its scenario-briefing sentence)."""
        self.message = text
        self.message_timer = duration

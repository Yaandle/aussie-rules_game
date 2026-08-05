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

import ai_control
import contest_minigame
import controller
import hero_levels
import levels
import mechanics
import possession
import settings
from character_state import CharacterState
from entities import Ball, Player
from goalkick_state import GoalKickState
from hero_camera import HeroCamera
from hero_state import HeroState

# Input modes (while playing)
MODE_IDLE = "idle"
MODE_AIMING_KICK = "aiming_kick"

# Directional prompt keys read while a tackle/50-50 contest is live (see
# _contest_input) — arrow keys and numpad, per the contest's own spec;
# a connected gamepad's D-pad already arrives as synthetic K_UP/DOWN/
# LEFT/RIGHT KEYDOWN events (see controller.poll_events), so it needs no
# entry of its own here.
_CONTEST_DIRECTION_KEYS = {
    pygame.K_UP: "UP", pygame.K_KP8: "UP",
    pygame.K_DOWN: "DOWN", pygame.K_KP2: "DOWN",
    pygame.K_LEFT: "LEFT", pygame.K_KP4: "LEFT",
    pygame.K_RIGHT: "RIGHT", pygame.K_KP6: "RIGHT",
}

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

# ── Mode config (possession/contest toggles) ─────────────────────────
# FULL GAME always uses these defaults untouched; a scenario overrides
# individual keys via an optional "config" dict in its levels.py entry
# (see start_scenario) — this is the single place mode differences are
# expressed, so feature code (kickouts, contests, the AI decision loop)
# never has to branch on game_mode itself.
DEFAULT_MODE_CONFIG = {
    "starting_possession": "human",   # "human" | "ai" — who holds the ball on load
    "scoring_enabled": True,
    "contests_enabled": True,
    "ai_enabled": True,
}

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
        self.mode_config = dict(DEFAULT_MODE_CONFIG)  # see start_full_game/start_scenario

        # Gameplay state exists from the start so render can always read it.
        self._load_layout(FULL_GAME_LAYOUT)
        self.timer = settings.QUARTER_LENGTH
        self.score = {"goals": 0, "behinds": 0}

        # Kick-aim cursor: tracks the mouse by default; a controller's
        # right stick can nudge it independently (see update()) so kick
        # aiming works with either input with no mode-switching needed.
        # This starting value only matters before the very first aim
        # attempt — _enter_aim_mode() resets it fresh every time aim mode
        # is actually entered (see below).
        self._aim_cursor = [settings.WINDOW_W / 2, settings.WINDOW_H / 2]
        self._last_mouse_pos = None   # see update()'s MODE_AIMING_KICK branch
        self._aim_input_source = None  # "controller" | "mouse" | None — gates
                                        # aim assist to controller use only

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
        # Which side starts with it — "human" (default, unchanged
        # behavior) or "ai" for a scenario that wants to test getting
        # the ball back off the AI (see mode_config / levels.py's
        # "config" field).
        starting_pool = red if self.mode_config.get("starting_possession") == "ai" else yellow
        carrier = starting_pool[0]
        carrier.is_ball_carrier = True
        self.ball = Ball(carrier.x, carrier.y)
        self.ball.give_to(carrier)
        self.possession_state = possession.HELD_PLAYER
        self.active_contest = None
        self.ai_hold_timer = 0.0
        self.contest_cooldown = 0.0
        self._contest_direction_queue = []
        # A >MARK_STAND_MIN_DISTANCE mark freezes the nearest opponent in
        # place and protects the marker from a tackle trigger for
        # MARK_HOLD_DURATION seconds — see _start_standing_mark, decremented
        # once per frame in update() alongside contest_cooldown, and
        # consulted by both the defender-chase call site (update()) and
        # possession.find_tackle_trigger. None when no mark is being held.
        self.standing_mark = None
        # Who the human is currently steering — the ball carrier whenever
        # YELLOW holds it, or a chosen defender otherwise (see
        # _update_controlled_player / _switch_controlled_player). Reset
        # fresh on every load/kickoff so a stale reference from a previous
        # spell can't survive into the new one.
        self.controlled_player = None
        self._was_carrying = False
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
        self._last_mouse_pos = None
        self._aim_input_source = None
        self.show_menu = False
        self.carrier_moving = False
        self._pending_outcome = None
        self.flash = None
        self.bounce_tick_timer = 0.0
        self.message = ""
        self.message_timer = 0.0

    def start_full_game(self):
        """Begin a single free-play quarter."""
        self.game_mode = "full"
        self.scenario = None
        self.result = None
        self.mode_config = dict(DEFAULT_MODE_CONFIG)
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
        # A scenario's optional "config" dict overrides individual
        # DEFAULT_MODE_CONFIG keys (starting_possession/scoring_enabled/
        # contests_enabled/ai_enabled) — most scenarios omit it and get
        # exactly today's behavior.
        self.mode_config = {**DEFAULT_MODE_CONFIG, **self.scenario.get("config", {})}
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
        if self.active_contest is not None:
            self._contest_input(event)
            return
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
            if event.key == pygame.K_TAB:
                self._switch_controlled_player()
            elif event.key in (pygame.K_1, pygame.K_q):
                self._attempt_handball()
            elif event.key in (pygame.K_2, pygame.K_k):
                if (self.carrier is not None and self.carrier.team == settings.YELLOW
                        and not self.ball.in_flight):
                    self._enter_aim_mode()
            elif event.key in (pygame.K_3, pygame.K_SPACE):
                self._bounce()
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
                if self.mode == MODE_AIMING_KICK and self.aim_point is not None:
                    self._attempt_kick(self.aim_point)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.mode == MODE_AIMING_KICK and not self.show_menu:
                target = self._mouse_to_logical(event.pos)
                if target is not None:
                    self._attempt_kick(target)

    def _contest_input(self, event):
        """While a tackle/50-50 contest is live, arrow keys and numpad
        directions (see _CONTEST_DIRECTION_KEYS) queue a press for
        _update_contest to consume next frame — a connected gamepad's
        D-pad arrives here too, already as synthetic KEYDOWN events (see
        controller.poll_events), so it needs no separate handling.
        Every other playing-input binding is suspended for the duration
        (see _playing_input) — the rest of the game is frozen anyway.
        """
        if event.type != pygame.KEYDOWN:
            return
        direction = _CONTEST_DIRECTION_KEYS.get(event.key)
        if direction is not None:
            self._contest_direction_queue.append(direction)

    def _mouse_to_logical(self, screen_pos):
        """Unproject a window click through the diorama camera onto the
        field's ground plane. None when the click is above the horizon."""
        return self.camera.unproject(*screen_pos)

    def _enter_aim_mode(self):
        """Start a fresh kick-aim: the cursor resets to dead ahead of the
        carrier (their own projected screen position) instead of
        wherever it was left from a previous aim attempt, or wherever
        the mouse pointer happens to be sitting.

        Controller players in particular would otherwise see the
        reticle start somewhere arbitrary and unrelated to where they
        actually are on the field — the two are only reset together
        here, once, on entry; update()'s MODE_AIMING_KICK branch then
        moves the cursor from this point via the right stick or the
        mouse. Resetting _last_mouse_pos too means a stale mouse
        position left over from before this aim attempt can't cause an
        immediate jump the moment aiming starts (see update()).
        """
        self.mode = MODE_AIMING_KICK
        default = None
        carrier = self.carrier
        if carrier is not None:
            proj = self.camera.project(carrier.x, carrier.y, 0.0)
            if proj is not None:
                default = (proj[0], proj[1])
        if default is None:
            default = (settings.WINDOW_W / 2, settings.WINDOW_H / 2)
        self._aim_cursor[0], self._aim_cursor[1] = default
        self._last_mouse_pos = None
        self._aim_input_source = None

    def _apply_aim_assist(self, dt):
        """Controller-only: a gentle screen-space pull toward the nearest
        teammate once the cursor is close to them (settings.
        AIM_ASSIST_RADIUS), so lining up a pass doesn't need
        pixel-perfect stick control the way a mouse gets for free.

        Deliberately soft, not a lock-on: this blends the cursor a
        fraction of the way toward the target each frame (the fraction
        set by AIM_ASSIST_STRENGTH), on top of whatever the raw stick
        input already did this frame — it never overrides the stick, so
        holding it away from the pull always wins. Called only while
        self._aim_input_source == "controller" (see update()); mouse
        aiming is precise enough on its own and never gets this.
        """
        carrier = self.carrier
        target = None
        target_dist = settings.AIM_ASSIST_RADIUS
        for t in self.teammates:
            if t is carrier:
                continue
            proj = self.camera.project(t.x, t.y, 0.0)
            if proj is None:
                continue
            dist = math.hypot(proj[0] - self._aim_cursor[0],
                              proj[1] - self._aim_cursor[1])
            if dist < target_dist:
                target_dist = dist
                target = proj
        if target is None:
            return
        k = min(1.0, settings.AIM_ASSIST_STRENGTH * dt)
        self._aim_cursor[0] = max(0, min(settings.WINDOW_W,
            self._aim_cursor[0] + (target[0] - self._aim_cursor[0]) * k))
        self._aim_cursor[1] = max(0, min(settings.WINDOW_H,
            self._aim_cursor[1] + (target[1] - self._aim_cursor[1]) * k))
        self._aim_cursor[1] += (target[1] - self._aim_cursor[1]) * k

    # ── Actions ─────────────────────────────────────────────────────

    def _attempt_handball(self):
        """Handball to the nearest teammate in range; resolves via mechanics.

        Human (YELLOW) only — ai_control never calls this (its
        placeholder loop only runs/kicks, see its HOOK comment), so
        there's no AI path that needs this team-symmetric the way
        _attempt_kick had to become.
        """
        carrier = self.carrier
        if carrier is None or carrier.team != settings.YELLOW or self.ball.in_flight:
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
        """Kick toward a target point: shot on goal or a field kick.

        Team-symmetric: works identically whichever team's player is
        carrying (see ai_control.decide_next_action, which calls this
        exact method for the AI's placeholder kick) — the attacking goal,
        "own"/"opposing" player lists, and possession/turnover outcome
        are all derived from carrier.team rather than assuming YELLOW.
        """
        carrier = self.carrier
        if carrier is None or self.ball.in_flight:
            return
        kick_distance = carrier.distance_to(target_point)
        if kick_distance > settings.KICK_MAX_RANGE:
            self._show_message("TOO FAR")
            return

        own_team = self.teammates if carrier.team == settings.YELLOW else self.opponents
        opposing_team = self.opponents if carrier.team == settings.YELLOW else self.teammates
        pressure = mechanics.calculate_pressure(carrier, opposing_team)
        goal = possession.attacking_goal(carrier.team)

        if (self.mode_config.get("scoring_enabled", True)
                and mechanics.is_scoring_attempt(carrier.pos, target_point, goal)):
            result = mechanics.resolve_scoring_attempt(carrier.pos, target_point, goal)
            self._pending_outcome = {"type": "score", "result": result, "team": carrier.team}
        else:
            outcome = mechanics.resolve_kick(carrier, target_point, opposing_team,
                                             own_team, pressure)
            candidates = outcome.get("candidates") or []
            if (outcome["result"] == "contest"
                    and self.mode_config.get("contests_enabled", True)
                    and len(candidates) >= 2):
                # Defer the dice-roll to a live reaction contest instead
                # of resolving it instantly — the two players actually
                # closest to the drop (not just the first two in
                # resolve_kick's unsorted opponents-then-teammates list)
                # contest it.
                nearest_two = sorted(candidates,
                                     key=lambda p: p.distance_to(target_point))[:2]
                self._pending_outcome = {"type": "contest", "candidates": nearest_two}
            elif outcome["winner"].team == carrier.team:
                # is_mark flags a clean, uncontested mark specifically
                # (result == "mark") rather than any possession-type
                # outcome — a successful handball also resolves to
                # {"type": "possession", ...} (see _attempt_handball) and
                # must never trigger stand-the-mark.
                self._pending_outcome = {"type": "possession",
                                         "player": outcome["winner"],
                                         "is_mark": outcome["result"] == "mark",
                                         "kick_distance": kick_distance}
            else:
                self._pending_outcome = {"type": "turnover",
                                         "player": outcome["winner"]}

        carrier.is_ball_carrier = False
        self.ball.start_flight(carrier.pos, target_point)
        self.mode = MODE_IDLE

    def _bounce(self):
        """Bounce the ball to legally continue running (resets the run meter).

        Human (YELLOW) only — the AI's placeholder loop doesn't play by
        the bounce rule yet (see ai_control.py's HOOK comment).
        """
        carrier = self.carrier
        if carrier is None or carrier.team != settings.YELLOW or self.ball.in_flight:
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

        # A live tackle/50-50 contest freezes the rest of the game (see
        # design note in possession.py's IN_CONTEST) — this is the one
        # branch point, simplest first pass rather than only freezing
        # the two participants.
        if self.active_contest is not None:
            self._update_contest(dt)
            return

        # DEAD_BALL_KICKOUT only exists to mark the single frame the
        # kickout taker was just placed on — a kickout plays out exactly
        # like any other carry from here on (human input or
        # ai_control.decide_next_action), so it's promoted immediately.
        if self.possession_state == possession.DEAD_BALL_KICKOUT:
            self.possession_state = possession.HELD_PLAYER

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

        # Refresh who the human is steering before reading input for this
        # frame (see _update_controlled_player) — must happen before
        # _update_movement below, otherwise input would always drive
        # last frame's controlled_player instead of this frame's.
        self._update_controlled_player()

        # Human carrier: keyboard/controller polling (_update_movement
        # no-ops for a RED carrier). AI carrier: ai_control's placeholder
        # loop (no-ops for a YELLOW carrier) — see its HOOK comment for
        # where real decision-making eventually replaces this.
        self._update_movement(dt)
        ai_control.decide_next_action(self, dt)

        # Closing defenders converge while someone holds the ball. In
        # FULL GAME (not scenarios — see FORMATION_LINES/_load_layout
        # comments) the rest of both sides also ease toward their
        # kickoff formation shape, blended toward the ball, so a
        # 16-a-side roster doesn't stand frozen off the ball.
        #
        # `carrier` gets re-fetched after the ball-flight/turnover
        # handling further down, since a completed ball flight can hand
        # possession to a different player (_apply_pending_outcome) —
        # that one isn't safe to cache across this block.
        carrier = self.carrier
        if carrier is not None:
            home = self._home_positions if self.game_mode == "full" else None
            # Whichever team ISN'T carrying closes in (this used to always
            # be RED chasing YELLOW — now that RED can carry too, the
            # chasing/resting sides swap with carrier.team so a human
            # defender actually converges on an AI carrier the same way
            # RED converges on the human, instead of RED harmlessly
            # "chasing" its own teammate).
            defending_team = self.opponents if carrier.team == settings.YELLOW else self.teammates
            carrying_teammates = self.teammates if carrier.team == settings.YELLOW else self.opponents
            # A defender currently standing the mark (see standing_mark /
            # _start_standing_mark) is frozen — excluded from the chase
            # entirely for the duration, same as a resting off-ball
            # teammate is excluded below. The human's controlled_player is
            # also excluded here whenever it's a defending-side player
            # (i.e. YELLOW is NOT carrying) — update_defenders drives both
            # the active chase step AND (via its own internal
            # update_off_ball call, see mechanics.py) the off-ball drift
            # for non-chasing defenders, so it must never touch whichever
            # defender the human is currently steering, or input and
            # auto-drift would fight over the same player every frame.
            standing_defender = self.standing_mark["defender"] if self.standing_mark else None
            excluded_defender = (self.controlled_player
                                 if self.controlled_player in defending_team else None)
            chasing = [d for d in defending_team
                      if d is not standing_defender and d is not excluded_defender]
            mechanics.update_defenders(chasing, carrier.pos, dt, home)
            if home is not None:
                resting = [t for t in carrying_teammates
                          if not t.is_ball_carrier and t is not self.controlled_player]
                mechanics.update_off_ball(resting, home, carrier.pos, dt)

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
        mechanics.separate_players(self.players, settings.PLAYER_MIN_SEPARATION)

        self.contest_cooldown = max(0.0, self.contest_cooldown - dt)
        if self.standing_mark is not None:
            self.standing_mark["timer"] -= dt
            if self.standing_mark["timer"] <= 0.0:
                self.standing_mark = None

        # A defender closing to tackle range starts a live contest
        # instead of holding at arm's length forever (see
        # possession.find_tackle_trigger / TACKLE_TRIGGER_RADIUS).
        # Gated on contest_cooldown so a just-resolved contest's still-
        # adjacent participants (see _separate_after_contest) don't
        # immediately restart another one back to back.
        if (self.possession_state == possession.HELD_PLAYER
                and self.mode_config.get("contests_enabled", True)
                and self.contest_cooldown <= 0.0):
            participants = possession.find_tackle_trigger(self)
            if participants is not None:
                self._start_contest(participants, "tackle")
                return

        self.ball.follow_carrier()
        if self.ball.advance_flight(dt):
            self._apply_pending_outcome()

        carrier = self.carrier
        if carrier is not None:
            opposing = self.opponents if carrier.team == settings.YELLOW else self.teammates
            self.pressure = mechanics.calculate_pressure(carrier, opposing)
        else:
            self.pressure = 0.0
        if self.mode == MODE_AIMING_KICK:
            # The right stick (if pushed) nudges the cursor incrementally;
            # otherwise the mouse takes over, but only once it's actually
            # moved since last frame — snapping to wherever the OS pointer
            # happens to be sitting on *every* idle frame (the old
            # behavior) fought with the controller for control, since the
            # stick naturally recenters between pushes: the instant it did,
            # the cursor would jump to the physical mouse position, however
            # far away that happened to be, then jump again on the next
            # stick input. _enter_aim_mode() resets both the cursor (to
            # dead ahead of the carrier) and _last_mouse_pos (to None) on
            # every fresh entry into this mode, so a stale mouse position
            # from before this aim attempt can't cause that same jump
            # right at the start either.
            rdx, rdy = controller.right_stick()
            mouse_pos = pygame.mouse.get_pos()
            mouse_moved = (self._last_mouse_pos is not None
                          and mouse_pos != self._last_mouse_pos)
            if rdx or rdy:
                self._aim_cursor[0] = max(0, min(settings.WINDOW_W,
                    self._aim_cursor[0] + rdx * settings.AIM_CURSOR_SPEED * raw_dt))
                self._aim_cursor[1] = max(0, min(settings.WINDOW_H,
                    self._aim_cursor[1] + rdy * settings.AIM_CURSOR_SPEED * raw_dt))
                self._aim_input_source = "controller"
            elif mouse_moved:
                self._aim_cursor[0], self._aim_cursor[1] = mouse_pos
                self._aim_input_source = "mouse"
            self._last_mouse_pos = mouse_pos
            # Soft aim assist only while the controller is the device
            # actually steering the cursor (see _apply_aim_assist) —
            # mouse aiming stays exactly as precise/untouched as before.
            if self._aim_input_source == "controller":
                self._apply_aim_assist(raw_dt)
            self.aim_point = self._mouse_to_logical(tuple(self._aim_cursor))
        else:
            self.aim_point = None
            self._last_mouse_pos = None
            self._aim_input_source = None

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
        """Poll held keys to move the controlled player; enforce the
        running-bounce rule against whoever is actually carrying.

        Human (YELLOW) controlled_player only — an AI (RED) carrier is
        driven by ai_control.decide_next_action instead (see update()),
        so this no-ops rather than reading keyboard/controller input into
        a RED player. controlled_player is the ball carrier whenever
        YELLOW holds it (unchanged behavior) or a chosen defender while
        YELLOW doesn't (see _update_controlled_player /
        _switch_controlled_player) — either way this is the one player
        keyboard/controller input drives this frame.
        """
        moved_player = self.controlled_player
        self.carrier_moving = False
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
        if self.game_mode == "full":
            speed = (self.character.applied_speed if self.character is not None
                     else settings.FULL_GAME_PLAYER_SPEED)
        moved = moved_player.move(dx, dy, dt, speed=speed)
        # carrier_moving/the bounce-rule only mean anything for the actual
        # ball carrier — moving a non-carrying defender around never
        # accrues run-since-bounce or triggers the "ran too far" turnover.
        if not moved_player.is_ball_carrier:
            return
        self.carrier_moving = moved > 0.0
        self.run_since_bounce += moved

        # Running too far past the bounce limit is a turnover.
        if self.run_since_bounce >= settings.BOUNCE_INTERVAL * 1.5:
            nearest = min(self.opponents, key=lambda o: o.distance_to(moved_player.pos))
            self._give_possession(nearest)
            self._show_message("RAN TOO FAR - TURNOVER")
            self.mode = MODE_IDLE
            self._register_turnover()

    def _update_controlled_player(self):
        """Keep self.controlled_player pointing at the right YELLOW player.

        While YELLOW holds the ball, it's always the carrier (today's
        unchanged behavior — regaining the ball, e.g. by gathering a mark
        or winning a contest, means they simply become the carrier and
        controlled_player already points at them via this branch, no
        special-casing needed). While YELLOW doesn't hold it, it stays
        exactly as the human left it (via _switch_controlled_player)
        across frames — except on the single frame defense is first
        entered (tracked by _was_carrying), where it resets to the
        nearest teammate to the ball so a stale reference from a previous
        defensive spell, or None on the very first frame, doesn't linger.
        """
        carrier = self.carrier
        yellow_carrying = carrier is not None and carrier.team == settings.YELLOW
        if yellow_carrying:
            self.controlled_player = carrier
        else:
            entering_defense = self._was_carrying or self.controlled_player is None
            if entering_defense:
                ball_pos = self.ball.pos
                self.controlled_player = min(self.teammates,
                                             key=lambda t: t.distance_to(ball_pos))
        self._was_carrying = yellow_carrying

    def _switch_controlled_player(self):
        """Cycle control to another YELLOW teammate, nearest-next by
        distance to the ball. Only meaningful while YELLOW doesn't hold
        the ball — switching the human's own ball carrier away from
        themselves doesn't apply (matches the FIFA/NBA "play now" style
        this is modelled on: you always drive the ball carrier directly).
        """
        carrier = self.carrier
        if carrier is not None and carrier.team == settings.YELLOW:
            return
        teammates = self.teammates
        if len(teammates) < 2:
            return
        ball_pos = self.ball.pos
        ordered = sorted(teammates, key=lambda t: t.distance_to(ball_pos))
        if self.controlled_player not in ordered:
            self.controlled_player = ordered[0]
            return
        idx = ordered.index(self.controlled_player)
        self.controlled_player = ordered[(idx + 1) % len(ordered)]

    # ── Outcome application ─────────────────────────────────────────

    def _apply_pending_outcome(self):
        """The ball has landed — apply whatever mechanics decided at launch."""
        outcome, self._pending_outcome = self._pending_outcome, None
        if outcome is None:
            return

        if outcome["type"] == "possession":
            self._give_possession(outcome["player"])
            if outcome.get("is_mark") and outcome.get("kick_distance", 0.0) > settings.MARK_STAND_MIN_DISTANCE:
                self._start_standing_mark(outcome["player"])

        elif outcome["type"] == "turnover":
            self._give_possession(outcome["player"])
            self._show_message("TURNOVER")
            self._register_turnover()

        elif outcome["type"] == "contest":
            self._start_contest(outcome["candidates"], "loose_ball")

        elif outcome["type"] == "score":
            self._apply_score(outcome["result"], outcome["team"])

    def _apply_score(self, result, team):
        """Register a goal, behind, or miss for whichever team took the
        shot, and check scenario objectives.

        Team-symmetric: an AI (RED) shot updates the same score dict
        under "opp_goals"/"opp_behinds" instead of forking into a
        separate code path — see mode/HUD note below.
        """
        yellow_scored = team == settings.YELLOW
        if result == "goal":
            if yellow_scored:
                self.score["goals"] += 1
                self._show_message("GOAL - 6 POINTS")
            else:
                self.score["opp_goals"] = self.score.get("opp_goals", 0) + 1
                self._show_message("OPPONENT GOAL")
            self.flash = {"color": settings.YELLOW if yellow_scored else settings.RED,
                          "timer": settings.FLASH_DURATION}
        elif result == "behind":
            if yellow_scored:
                self.score["behinds"] += 1
                self._show_message("BEHIND - 1 POINT")
            else:
                self.score["opp_behinds"] = self.score.get("opp_behinds", 0) + 1
                self._show_message("OPPONENT BEHIND")
            self.flash = {"color": settings.BG, "timer": settings.FLASH_DURATION}

        # Scenario objectives are about the human's performance — an AI
        # score never completes or fails one (there's no "concede a
        # score" scenario objective in this pass; see levels.py).
        if self.game_mode == "scenario" and yellow_scored:
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

        if result == "goal":
            self._reset_to_kickoff()
            # EXTEND: ruck contest at start of play / after a goal
        elif result == "behind":
            # The defending team kicks out from their goal square (see
            # possession.resolve_behind) instead of the plain center-
            # bounce reset a goal gets.
            possession.resolve_behind(self, team)
        else:  # miss → turnover where the ball landed
            defending_team = self.opponents if yellow_scored else self.teammates
            nearest = min(defending_team, key=lambda p: p.distance_to(self.ball.pos))
            self._give_possession(nearest)
            self._show_message("MISS - TURNOVER")
            self._register_turnover()

    def _register_turnover(self):
        """Scenario fail-on-turnover check.

        Possession itself is applied immediately by _give_possession
        wherever this is called from — there's no passive delay-then-
        auto-return to the human anymore now that an AI (RED) carrier
        actually plays out its possession (see ai_control.py) instead
        of just holding the spot for TURNOVER_RESET_DELAY seconds.
        """
        if (self.game_mode == "scenario"
                and self.scenario.get("fail_on_turnover")):
            self.phase = PHASE_END
            self.result = "fail"

    def _give_possession(self, player):
        """Make the given player the new ball-carrier (either team)."""
        for p in self.players:
            p.is_ball_carrier = False
        player.is_ball_carrier = True
        self.ball.give_to(player)
        self.possession_state = possession.HELD_PLAYER
        self.run_since_bounce = 0.0

    def _start_standing_mark(self, marker):
        """A mark taken from beyond MARK_STAND_MIN_DISTANCE freezes the
        nearest opponent to the marker at their current spot and shields
        the marker from a tackle trigger, both for MARK_HOLD_DURATION
        seconds (see settings.py). No-ops if the marker's team has no
        opponents on field (can't happen in practice, but keeps this
        symmetric/safe the way _give_possession's callers already are)."""
        opposing = self.opponents if marker.team == settings.YELLOW else self.teammates
        if not opposing:
            self.standing_mark = None
            return
        defender = min(opposing, key=lambda o: o.distance_to(marker.pos))
        self.standing_mark = {
            "marker": marker,
            "defender": defender,
            "timer": settings.MARK_HOLD_DURATION,
        }

    def _start_contest(self, participants, kind):
        """Freeze play and begin a tackle/50-50 reaction contest between
        exactly two players (see contest_minigame.py).

        Also drops any in-progress kick-aim: a tackle can interrupt the
        human mid-aim (the trigger check only looks at possession_state,
        not self.mode), and whoever's carrying can change once the
        contest resolves — a stale MODE_AIMING_KICK left pointing at the
        old aim target/carrier must not survive into that.
        """
        self.active_contest = contest_minigame.start(participants, kind)
        self.possession_state = possession.IN_CONTEST
        self._contest_direction_queue = []
        self.mode = MODE_IDLE

    def _update_contest(self, dt):
        """Advance the live contest one frame; apply its result once
        resolved (winner keeps/gains possession outright — see the
        design note in contest_minigame.py on tackle/50-50 outcomes).

        A resolved TACKLE contest leaves the two participants standing
        right next to each other, well inside TACKLE_TRIGGER_RADIUS —
        without separating them, the very next frame's trigger check
        (see update()) would see the same pair still in range and start
        a brand new contest immediately, forever. _separate_after_contest
        pushes them apart and a short self.contest_cooldown holds off
        re-triggering, so the winner gets an actual window of play
        before another tackle can start.
        """
        human_inputs, self._contest_direction_queue = self._contest_direction_queue, []
        contest_minigame.update(self.active_contest, dt, human_inputs)
        if self.active_contest.resolved:
            contest, self.active_contest = self.active_contest, None
            self.possession_state = possession.HELD_PLAYER
            if contest.winner is not None:
                self._give_possession(contest.winner)
            self._separate_after_contest(contest.participants)
            self.contest_cooldown = settings.CONTEST_COOLDOWN

    def _separate_after_contest(self, participants):
        """Push a resolved contest's two participants apart to just
        beyond TACKLE_TRIGGER_RADIUS (see _update_contest) instead of
        leaving them standing on top of each other."""
        if len(participants) < 2:
            return
        a, b = participants[0], participants[1]
        dx, dy = b.x - a.x, b.y - a.y
        dist = math.hypot(dx, dy)
        if dist < 0.01:
            dx, dy, dist = 1.0, 0.0, 1.0
        target_gap = settings.TACKLE_TRIGGER_RADIUS * 1.6
        push = max(0.0, target_gap - dist) / 2
        ux, uy = dx / dist, dy / dist
        a.x, a.y = mechanics.clamp_to_oval(a.x - ux * push, a.y - uy * push)
        b.x, b.y = mechanics.clamp_to_oval(b.x + ux * push, b.y + uy * push)

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

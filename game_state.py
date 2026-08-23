"""game_state.py — owns all mutable game state and interprets input.

GameState runs a small phase machine:
  PHASE_MENU    — main menu / scenario select (render draws the menus)
  PHASE_PLAYING — a match or scenario in progress
  PHASE_END     — result overlay (win / fail / full time) with retry flow

It calls into mechanics.py for every probabilistic resolution and never
draws anything itself (render.py reads from it instead).

Setup/loading and phase-machine dispatch live here; menu navigation
(menu.py), the frame-by-frame update loop and player actions
(gameplay.py), and possession/score/contest resolution (outcomes.py)
are split into their own modules, each self-contained around one
concern. Every one of those modules follows the same convention
mechanics.py/possession.py/ai_control.py already use: functions take
the owning GameState as their first argument rather than being methods.
"""

import pygame

import formations
import gameplay
import levels
import menu
import possession
import settings
from character_state import CharacterState
from entities import Ball, Player
from game_phases import (MODE_AIMING_KICK, MODE_IDLE, PHASE_CHARACTER,
                          PHASE_END, PHASE_GOALKICK, PHASE_HERO,
                          PHASE_MENU, PHASE_PLAYING, ROOT_OPTIONS,
                          SCREEN_HERO, SCREEN_HERO_LEAGUES, SCREEN_ROOT)
from goalkick_state import GoalKickState
from hero_camera import HeroCamera
from hero_state import HeroState

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
        self.hero_unlocked = 1           # how many hero levels are playable (flat,
                                          # across every league — see hero_levels.py)
        self.hero_league_index = 0       # which league SCREEN_HERO is currently
                                          # showing the level list for (see menu.py)
        # AFL HERO's league-to-league swipe (SCREEN_HERO's "GO TO THE
        # LEAGUE" row) — None while idle, else "out" (covering) or "in"
        # (revealing); mirrors CharacterState's transition_dir/_t as a
        # couple of plain fields rather than a whole new class, since
        # this never leaves PHASE_MENU. See menu.update_menu.
        self.hero_transition_dir = None
        self.hero_transition_t = 0.0
        self.hero_transition_target = None   # league index to switch to once covered
        self.hero_transition_progress = 0.0  # 0..1 wipe coverage, updated by menu.update_menu
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
        self._load_layout(formations.FULL_GAME_LAYOUT)
        self.timer = settings.QUARTER_LENGTH
        self.score = {"goals": 0, "behinds": 0}

        # Kick-aim cursor: tracks the mouse by default; a controller's
        # right stick can nudge it independently (see gameplay.update_
        # pressure_aim_and_camera) so kick aiming works with either
        # input with no mode-switching needed. This starting value only
        # matters before the very first aim attempt — enter_aim_mode()
        # resets it fresh every time aim mode is actually entered (see
        # below).
        self._aim_cursor = [settings.WINDOW_W / 2, settings.WINDOW_H / 2]
        self._last_mouse_pos = None   # see gameplay's MODE_AIMING_KICK branch
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
        # AI run-heading variation (see ai_control.decide_next_action /
        # settings.AI_RUN_WOBBLE_DEGREES) — a fresh random offset picked
        # every AI_WOBBLE_INTERVAL seconds so an AI carry doesn't run a
        # razor-straight line at goal every single possession.
        self.ai_wobble_timer = 0.0
        self.ai_wobble_angle = 0.0
        self.contest_cooldown = 0.0
        self._contest_direction_queue = []
        # Seconds the current carrier has held the ball — reset in
        # outcomes.give_possession, incremented once per frame in
        # gameplay.update_playing. Feeds "prior opportunity" (see
        # mechanics.resolve_tackle / settings.PRIOR_OPPORTUNITY_GRACE):
        # a tackle before the grace window elapses is always a neutral
        # ball-up, never holding-the-ball, regardless of the break-
        # tackle roll.
        self.possession_held_timer = 0.0
        # Cooldown after ANY tackle resolution (broken or holding-the-
        # ball) before that exact pairing can trigger another — see
        # outcomes.resolve_tackle_now / settings.POST_TACKLE_COOLDOWN.
        # Separate from contest_cooldown (loose-ball/ruck contests still
        # use that one) since tackles no longer go through
        # contest_minigame at all.
        self.tackle_cooldown = 0.0
        # A >MARK_STAND_MIN_DISTANCE mark freezes the nearest opponent in
        # place and protects the marker from a tackle trigger for
        # MARK_HOLD_DURATION seconds — see outcomes.start_standing_mark,
        # decremented once per frame in gameplay.decay_contest_timers,
        # and consulted by both the defender-chase call site
        # (gameplay.update_defenders_and_shape) and
        # possession.find_tackle_trigger. None when no mark is being held.
        self.standing_mark = None
        # Who the human is currently steering — the ball carrier whenever
        # YELLOW holds it, or a chosen defender otherwise (see
        # gameplay.update_controlled_player / switch_controlled_player).
        # Reset fresh on every load/kickoff so a stale reference from a
        # previous spell can't survive into the new one.
        self.controlled_player = None
        self._was_carrying = False
        # Arrival-time kick context for the ball currently in flight —
        # None, or a dict {"landing", "kicker", "own_team",
        # "opposing_team", "kick_distance"} set only for a genuine field
        # kick (see gameplay.attempt_kick), read every frame it's
        # airborne to pull nearby players toward the drop zone
        # (mechanics.converge_on_drop_zone) and to resolve mark/contest/
        # grounded at arrival against live positions
        # (mechanics.resolve_kick_landing) — see gameplay.advance_ball.
        # A handball never sets this (see settings.py's Out of bounds
        # note — only a kicked ball's flight can be ruled out on the
        # full); a scoring attempt is also exempt (its own goal/behind/
        # miss resolution already owns the boundary near the goal line).
        self._in_flight_kick = None
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
        self._load_layout(formations.FULL_GAME_LAYOUT)
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
    def opp_points(self):
        """The AI's score — outcomes.apply_score tracks it under
        "opp_goals"/"opp_behinds" whenever a RED shot lands, but FULL
        GAME's own kickoff carries no such thing as a fixed narrative
        score the way a scenario's away_score_start does, so this is
        the one place that total gets computed for display (see
        field_render's HUD and render._render_end's FULL TIME line)."""
        return self.score.get("opp_goals", 0) * 6 + self.score.get("opp_behinds", 0)

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

    # ── Actions (public — called across module boundaries) ───────────

    def attempt_kick(self, target_point):
        """Kick toward a target point — see gameplay.attempt_kick.
        Public: ai_control.py's AI carrier calls this exact entry point,
        same as the human path through gameplay.handle_playing_input."""
        gameplay.attempt_kick(self, target_point)

    # ── Input dispatch ──────────────────────────────────────────────

    def handle_input(self, event):
        """Route one Pygame event to the active phase's handler.

        The CHARACTER MENU hotkey (K_c) is checked ahead of the normal
        phase dispatch so it's reachable from PHASE_MENU or mid-match
        (PHASE_PLAYING), the same way M already opens the controls
        overlay during a match. `C` doesn't collide with any existing
        binding (see gameplay.handle_playing_input / GoalKickState.
        handle_input).
        """
        if event.type == pygame.KEYDOWN and event.key == pygame.K_c:
            # While typing a new saved player's name, "C" is a letter to
            # type, not the menu hotkey — let it fall through to the
            # normal PHASE_CHARACTER dispatch below instead of closing.
            naming = (self.phase == PHASE_CHARACTER and self.character is not None
                     and self.character.screen == "naming")
            if not naming:
                if self.phase == PHASE_CHARACTER:
                    menu.request_close_character(self)
                    return
                if self.phase in (PHASE_MENU, PHASE_PLAYING):
                    menu.open_character(self)
                    return

        if self.phase == PHASE_MENU:
            menu.handle_menu_input(self, event)
        elif self.phase == PHASE_CHARACTER:
            menu.handle_character_input(self, event)
        elif self.phase == PHASE_HERO:
            if self.hero is not None:
                self.hero.handle_input(event)
        elif self.phase == PHASE_GOALKICK:
            if self.goalkick is not None:
                self.goalkick.handle_input(event)
        elif self.phase == PHASE_END:
            menu.handle_end_input(self, event)
        else:
            gameplay.handle_playing_input(self, event)

    # ── Update loop ─────────────────────────────────────────────────

    def update(self, dt):
        """Advance whichever phase is active. PHASE_PLAYING's frame
        pipeline lives in gameplay.update_playing; the other phases
        each bridge to their own submode's update via menu.py."""
        if self.phase == PHASE_HERO:
            menu.update_hero(self, dt)
            return
        if self.phase == PHASE_GOALKICK:
            menu.update_goalkick(self, dt)
            return
        if self.phase == PHASE_CHARACTER:
            menu.update_character(self, dt)
            return
        if self.phase == PHASE_MENU:
            menu.update_menu(self, dt)
            return
        if self.phase != PHASE_PLAYING or self.show_menu:
            return
        gameplay.update_playing(self, dt)

    # ── Small helpers ───────────────────────────────────────────────

    def _show_message(self, text, duration=2.0):
        """Show a HUD message for `duration` seconds (default matches
        every existing short event message; start_scenario passes a
        longer one for its scenario-briefing sentence)."""
        self.message = text
        self.message_timer = duration

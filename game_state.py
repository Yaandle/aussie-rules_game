"""game_state.py — owns all mutable game state and interprets input.

GameState runs a small phase machine:
  PHASE_MENU    — main menu / scenario select (render draws the menus)
  PHASE_PLAYING — a match or scenario in progress
  PHASE_END     — result overlay (win / fail / full time) with retry flow

It calls into mechanics.py for every probabilistic resolution and never
draws anything itself (render.py reads from it instead).
"""

import pygame

import hero_levels
import levels
import mechanics
import settings
from entities import Ball, Player
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

# Menu screens and options
SCREEN_ROOT = "root"
SCREEN_SCENARIOS = "scenarios"
SCREEN_HERO = "hero_select"
ROOT_OPTIONS = ("FULL GAME", "SCENARIOS", "AFL HERO", "QUIT")

# Default kickoff layout for full game mode.
FULL_GAME_LAYOUT = {
    "yellow": [(98, 56), (109, 41), (123, 69), (146, 54)],
    "red":    [(91, 47), (111, 58), (127, 41), (132, 71), (155, 56)],
}

# EXTEND: multi-quarter match structure
# EXTEND: two controllable teams in full game mode


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

    def start_hero(self, index):
        """Begin one AFL Hero level (swipe-based possession puzzle)."""
        self.hero = HeroState(index)
        self.phase = PHASE_HERO

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
        """Route one Pygame event to the active phase's handler."""
        if self.phase == PHASE_MENU:
            self._menu_input(event)
        elif self.phase == PHASE_HERO:
            if self.hero is not None:
                self.hero.handle_input(event)
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

        # Closing defenders converge while someone holds the ball.
        carrier = self.carrier
        if carrier is not None:
            mechanics.update_defenders(self.opponents, carrier.pos, dt)

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
        moved = carrier.move(dx, dy, dt)
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

    def _show_message(self, text):
        """Show a short HUD message."""
        self.message = text
        self.message_timer = 2.0

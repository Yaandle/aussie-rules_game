"""goalkick_state.py — GOAL KICKING mode: a freeform kicking practice range.

Walk "the mark" anywhere in a wide arc in front of goal, read the wind,
then time a two-stage power/accuracy meter to send the ball at goal. No
opposition beyond a decorative "man on the mark" standing where you
kicked from — this is a practice range, not a contest, so there's no
level list or unlock progression (compare hero_state.py / levels.py).

A fresh wind rolls at the start of every attempt, visible while you're
still choosing the mark — so it factors into where you decide to stand,
not just how you compensate the kick.

The camera starts pulled back into a wide establishing shot while you
walk the mark around (so you can see the goal and the ground around it),
then swoops into the tight first-person kicking view once you confirm a
spot — see GK_TRANSITION and settings.GOALKICK_WIDE_CAM_* /
GOALKICK_CAM_*. It's the same HeroCamera class throughout, just handed
different — and briefly, interpolated — rig parameters; hero_camera.py
itself is never touched.

Aiming is two layers, both live during GK_ACCURACY: hold left/right to
steer an intended line by hand (the bias — this is where you actually
compensate the wind, watch the aim reticle to see where you're
pointed), while the sweeping bar adds a smaller timing-precision wobble
on top when you lock it. Read the wind, dial in a line, then still
need decent timing to hit it clean.

Sub-mode machine:
  GK_POSITION   — walk the mark around in the wide shot; SPACE confirms it
  GK_TRANSITION — a brief swoop from the wide shot into the tight kicking view
  GK_POWER      — a power bar sweeps; SPACE locks how hard you kick it
  GK_ACCURACY   — steer your aim and time the bar; SPACE locks both
  GK_FLIGHT     — the ball travels to a landing spot consistent with the roll
  GK_RESULT     — goal / behind / miss banner and a running tally; SPACE for another

All probabilistic resolution comes from mechanics.py; this module owns
mutable state and input only; goalkick_render.py draws it.
"""

import math

import pygame

import mechanics
import settings
from entities import Ball, Player
from hero_camera import HeroCamera

GK_POSITION = "position"
GK_TRANSITION = "transition"
GK_POWER = "power"
GK_ACCURACY = "accuracy"
GK_FLIGHT = "flight"
GK_RESULT = "result"


class GoalKickState:
    """Single source of truth for the GOAL KICKING practice range."""

    def __init__(self):
        self.exit_request = None      # "menu" — read by GameState
        self.tally = {"goals": 0, "behinds": 0, "misses": 0}
        self._new_attempt(reset_mark=True)

    # ── Setup ───────────────────────────────────────────────────────

    def _new_attempt(self, reset_mark=False):
        """Start (or restart) one attempt: reset the meters, keep the tally."""
        if reset_mark:
            self.mark_distance = (settings.GOALKICK_MIN_RANGE
                                  + settings.GOALKICK_MAX_RANGE) / 2.0
            self.mark_angle_deg = 0.0

        self.mode = GK_POSITION
        self.wind = mechanics.roll_wind()   # visible while you still pick the mark
        self.meter_elapsed = 0.0
        self.meter_value = 0.0
        self.power_t = None
        self.power_quality = None
        self.aim_bias_deg = 0.0        # your hand-steered aim, adjusted during GK_ACCURACY
        self.aim_angle_deg = None      # bias + timing wobble, set once GK_ACCURACY locks
        self.result = None             # "goal" | "behind" | "miss" once GK_RESULT
        self.transition_t = 0.0        # progress through GK_TRANSITION's swoop

        self.mark_defender = Player(*self.mark_pos, settings.RED)
        self.ball = Ball(*self.mark_pos)
        self.flash = None              # reuses render._render_flash's duck-typed shape

        self.camera = self._wide_camera()
        self.show_menu = False
        self.message = ""
        self.message_timer = 0.0

    def _wide_camera(self):
        """A fresh establishing-shot camera, pinned to the mark's current
        position — rebuilt every GK_POSITION frame (see update()) rather
        than eased, so it follows your held-key movement with zero lag."""
        return HeroCamera(
            (0.0, 0.0),
            back=settings.GOALKICK_WIDE_CAM_BACK,
            height=settings.GOALKICK_WIDE_CAM_HEIGHT,
            focal=settings.GOALKICK_WIDE_CAM_FOCAL,
            zoom_mult=settings.GOALKICK_CAM_ZOOM,
            lerp=settings.GOALKICK_CAM_LERP,
            horizon_y=settings.GOALKICK_HORIZON_Y,
        )

    # ── Accessors ───────────────────────────────────────────────────

    @property
    def mark_pos(self):
        """World (x, y) for the current mark: `mark_distance` out from
        goal, `mark_angle_deg` around it (0 = dead straight in front)."""
        goal = settings.GOAL_RIGHT
        rad = math.radians(self.mark_angle_deg)
        x = goal[0] - math.cos(rad) * self.mark_distance
        y = goal[1] + math.sin(rad) * self.mark_distance
        return mechanics.clamp_to_oval(x, y)

    @property
    def in_meter(self):
        return self.mode in (GK_POWER, GK_ACCURACY)

    @property
    def ideal_power_t(self):
        """Where the power bar's sweet spot sits for the current mark."""
        return min(self.mark_distance / settings.GOALKICK_POWER_RANGE, 1.0)

    # ── Input ───────────────────────────────────────────────────────

    def handle_input(self, event):
        """Route one Pygame event: overlay keys, or a single confirm key
        that means something different in each sub-mode."""
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_m:
            self.show_menu = not self.show_menu
            return
        if event.key == pygame.K_ESCAPE:
            if self.show_menu:
                self.show_menu = False
            elif self.mode in (GK_TRANSITION, GK_POWER, GK_ACCURACY):
                self._new_attempt()          # bail the attempt, keep the mark
            else:
                self.exit_request = "menu"
            return
        if self.show_menu:
            return

        confirm = event.key in (pygame.K_SPACE, pygame.K_RETURN)
        if not confirm:
            return
        if self.mode == GK_POSITION:
            self._confirm_mark()
        elif self.in_meter:
            self._lock_meter()
        elif self.mode == GK_RESULT:
            self._new_attempt()

    def _confirm_mark(self):
        self.mode = GK_TRANSITION
        self.transition_t = 0.0

    def _lock_meter(self):
        value = self.meter_value
        if self.mode == GK_POWER:
            self.power_t = value
            self.power_quality = mechanics.goalkick_power_quality(
                value, self.ideal_power_t)
            self.mode = GK_ACCURACY
            self.meter_elapsed = 0.0
        else:                                             # GK_ACCURACY
            wobble = (value - 0.5) * 2.0 * settings.GOALKICK_ACC_SPREAD
            self.aim_angle_deg = self.aim_bias_deg + wobble
            self._launch()

    # ── Update loop ─────────────────────────────────────────────────

    def update(self, dt):
        if self.message_timer > 0.0:
            self.message_timer -= dt
            if self.message_timer <= 0.0:
                self.message = ""
        if self.flash is not None:
            self.flash["timer"] -= dt
            if self.flash["timer"] <= 0.0:
                self.flash = None

        if self.show_menu:
            return

        # GK_POSITION and GK_TRANSITION each manage `self.camera` directly
        # (rebuilding it every frame) rather than easing a persistent
        # instance — see _wide_camera / _update_transition — so they
        # return early instead of falling into the shared camera.update()
        # every other stage below relies on.
        if self.mode == GK_POSITION:
            self._update_position(dt)
            self.camera = self._wide_camera()
            return
        if self.mode == GK_TRANSITION:
            self._update_transition(dt)
            return

        if self.in_meter:
            self.meter_elapsed += dt
            self.meter_value = mechanics.triangle_wave(
                self.meter_elapsed, settings.GOALKICK_METER_PERIOD)
            if self.mode == GK_ACCURACY:
                self._update_aim(dt)
        elif self.mode == GK_FLIGHT:
            self._update_flight(dt)

        self.camera.update(dt, self._focus_local(), self.in_meter)

    def _update_aim(self, dt):
        """Hold left/right to steer the intended aim (see module docstring
        — this is the hand-controlled half of aiming; the meter you're
        also watching right now supplies the other half, a smaller
        timing wobble around wherever this points)."""
        keys = pygame.key.get_pressed()
        turn = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - \
               (keys[pygame.K_LEFT] or keys[pygame.K_a])
        self.aim_bias_deg = max(-settings.GOALKICK_AIM_BIAS_MAX, min(
            settings.GOALKICK_AIM_BIAS_MAX,
            self.aim_bias_deg + turn * settings.GOALKICK_AIM_BIAS_SPEED * dt))

    def _update_position(self, dt):
        """Poll held keys to walk the mark around its allowed arc."""
        keys = pygame.key.get_pressed()
        turn = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - \
               (keys[pygame.K_LEFT] or keys[pygame.K_a])
        step = (keys[pygame.K_UP] or keys[pygame.K_w]) - \
               (keys[pygame.K_DOWN] or keys[pygame.K_s])

        self.mark_angle_deg = max(-settings.GOALKICK_MAX_ANGLE, min(
            settings.GOALKICK_MAX_ANGLE,
            self.mark_angle_deg + turn * settings.GOALKICK_MARK_TURN_SPEED * dt))
        self.mark_distance = max(settings.GOALKICK_MIN_RANGE, min(
            settings.GOALKICK_MAX_RANGE,
            self.mark_distance + step * settings.GOALKICK_MARK_MOVE_SPEED * dt))

        pos = self.mark_pos
        self.mark_defender.x, self.mark_defender.y = pos
        self.ball.x, self.ball.y = pos

    def _update_transition(self, dt):
        """Swoop the rig from the wide establishing shot to the tight
        kicking view over GOALKICK_TRANSITION_TIME seconds.

        The mark is already frozen by this point (GK_POSITION is over),
        so there's nothing to track — this only interpolates the
        camera's own back/height/focal and rebuilds it fresh each frame,
        the same trick _wide_camera uses. HeroCamera's own easing
        (self.camera.update()) isn't involved: we're driving the "zoom"
        ourselves, frame by frame, until it lands exactly on the tight
        rig's numbers.
        """
        self.transition_t += dt
        frac = mechanics.smoothstep(
            self.transition_t / settings.GOALKICK_TRANSITION_TIME)

        back = settings.GOALKICK_WIDE_CAM_BACK + (
            settings.GOALKICK_CAM_BACK - settings.GOALKICK_WIDE_CAM_BACK) * frac
        height = settings.GOALKICK_WIDE_CAM_HEIGHT + (
            settings.GOALKICK_CAM_HEIGHT - settings.GOALKICK_WIDE_CAM_HEIGHT) * frac
        focal = settings.GOALKICK_WIDE_CAM_FOCAL + (
            settings.GOALKICK_CAM_FOCAL - settings.GOALKICK_WIDE_CAM_FOCAL) * frac
        self.camera = HeroCamera(
            (0.0, 0.0), back=back, height=height, focal=focal,
            zoom_mult=settings.GOALKICK_CAM_ZOOM, lerp=settings.GOALKICK_CAM_LERP,
            horizon_y=settings.GOALKICK_HORIZON_Y,
        )

        if frac >= 1.0:
            self.mode = GK_POWER
            self.meter_elapsed = 0.0

    def _launch(self):
        """Decide the outcome first (see mechanics.resolve_goalkick), then
        stage a landing point for the flight animation to match it."""
        mark = self.mark_pos
        travel_dist = self.power_t * settings.GOALKICK_POWER_RANGE
        wind_deg = mechanics.wind_angle_effect(self.wind, travel_dist)

        self.result = mechanics.resolve_goalkick(
            mark, self.aim_angle_deg, self.power_quality, wind_deg)
        landing = mechanics.goalkick_landing_point(
            mark, self.result, self.aim_angle_deg, wind_deg, self.power_quality)

        self.ball.start_flight(mark, landing, speed=settings.GOALKICK_FLIGHT_SPEED)
        self.mode = GK_FLIGHT

    def _update_flight(self, dt):
        if self.ball.advance_flight(dt):
            self._arrive()

    def _arrive(self):
        if self.result == "goal":
            self.tally["goals"] += 1
            self.flash = {"color": settings.YELLOW, "timer": settings.FLASH_DURATION}
            self._show_message("GOAL - 6 POINTS")
        elif self.result == "behind":
            self.tally["behinds"] += 1
            self.flash = {"color": settings.BG, "timer": settings.FLASH_DURATION}
            self._show_message("BEHIND - 1 POINT")
        else:
            self.tally["misses"] += 1
            self._show_message("MISSED")
        self.mode = GK_RESULT

    def _focus_local(self):
        """Camera focus in mark-relative local space (see goalkick_render
        for the same transform applied to everything else on screen).
        The kicker never moves once the mark is confirmed, so this is the
        origin except while the ball is actually in flight."""
        if self.mode in (GK_FLIGHT, GK_RESULT):
            fwd, right = mechanics.kick_axes(self.mark_pos, settings.GOAL_RIGHT)
            return mechanics.to_kick_space(self.mark_pos, fwd, right, self.ball.pos)
        return (0.0, 0.0)

    def _show_message(self, text):
        self.message = text
        self.message_timer = 2.5

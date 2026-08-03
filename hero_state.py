"""hero_state.py — AFL Hero mode: every possession is a puzzle.

One HeroState instance runs one level: receive the ball, slow the world,
draw a decision (run / handball / kick) with the mouse, then watch it
play out in real time. Losing the ball fails the level.

Sub-mode machine:
  HS_DECIDE — slow-motion; the player drags a path from the carrier
  HS_RUN    — the carrier follows a drawn run path; defenders hunt
  HS_FLIGHT — the ball travels a curved kick/handball path
  HS_LOOSE  — an unmarked ball bounces; a ground scramble resolves it
  HS_DONE   — win/fail overlay (R retry, Enter next, Esc menu)

All probabilistic resolution comes from mechanics.py. This module owns
mutable state and input only; hero_render.py draws it.
"""

import math

import pygame

import hero_levels
import mechanics
import settings
from entities import Ball, Player
from hero_camera import HeroCamera

HS_DECIDE = "decide"
HS_RUN = "run"
HS_FLIGHT = "flight"
HS_LOOSE = "loose"
HS_DONE = "done"

_RUN_BUTTON = 3      # right-drag draws a run path
_KICK_BUTTON = 1     # left-drag draws a handball / kick


class HeroState:
    """Single source of truth for one AFL Hero level attempt."""

    def __init__(self, index):
        self.level_index = index
        self.level = hero_levels.HERO_LEVELS[index]
        self.exit_request = None      # "menu" | "next" — read by GameState
        self._load()

    def _load(self):
        """(Re)build the level's players, ball, camera, and transient state."""
        lvl = self.level
        self.teammates = [Player(x, y, settings.YELLOW) for (x, y) in lvl["yellow"]]
        self.opponents = [Player(x, y, settings.RED) for (x, y) in lvl["red"]]
        carrier = self.teammates[0]
        carrier.is_ball_carrier = True
        self.ball = Ball(carrier.x, carrier.y)
        self.ball.give_to(carrier)
        self.leads = {self.teammates[i]: tuple(p)
                      for i, p in lvl.get("leads", {}).items()}

        self.mode = HS_DECIDE
        self.result = None            # "win" | "fail" once HS_DONE
        self.timer = lvl["time_limit"]
        self.camera = HeroCamera(carrier.pos)
        self.pressure = 0.0

        self.run_path = []            # remaining waypoints while HS_RUN
        self.flight = None            # dict while HS_FLIGHT (see _launch)
        self.loose_point = None
        self.loose_timer = 0.0

        self.drag_button = None       # active mouse button while drawing
        self.drag_points = []         # unprojected field points of the drag
        self.message = ""
        self.message_timer = 0.0

    # ── Accessors ───────────────────────────────────────────────────

    @property
    def players(self):
        return self.teammates + self.opponents

    @property
    def carrier(self):
        for p in self.teammates:
            if p.is_ball_carrier:
                return p
        return None

    @property
    def in_decision(self):
        return self.mode == HS_DECIDE

    # ── Input ───────────────────────────────────────────────────────

    def handle_input(self, event):
        """Route one Pygame event: overlay keys, or swipe capture."""
        if self.mode == HS_DONE:
            self._done_input(event)
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.drag_button is not None:
                    self._cancel_drag()
                else:
                    self.exit_request = "menu"
            elif event.key == pygame.K_r:
                self._load()
            return

        if event.type == pygame.MOUSEBUTTONDOWN and \
                event.button in (_RUN_BUTTON, _KICK_BUTTON):
            self._begin_drag(event.button, event.pos)
        elif event.type == pygame.MOUSEMOTION and self.drag_button is not None:
            pt = self.camera.unproject(*event.pos)
            if pt is not None:
                self.drag_points.append(pt)
        elif event.type == pygame.MOUSEBUTTONUP and \
                event.button == self.drag_button:
            self._end_drag()

    def _done_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_r:
            self._load()
        elif event.key == pygame.K_ESCAPE:
            self.exit_request = "menu"
        elif event.key == pygame.K_RETURN and self.result == "win":
            self.exit_request = "next"

    def _begin_drag(self, button, screen_pos):
        """A drag only arms if it starts on (near) the ball carrier."""
        carrier = self.carrier
        if carrier is None or self.mode not in (HS_DECIDE, HS_RUN):
            return
        pt = self.camera.unproject(*screen_pos)
        if pt is None:
            return
        if carrier.distance_to(pt) <= settings.HERO_GRAB_RADIUS:
            self.drag_button = button
            self.drag_points = [pt]

    def _cancel_drag(self):
        self.drag_button = None
        self.drag_points = []

    def _end_drag(self):
        """Interpret the finished swipe as a run, handball, or kick."""
        button, points = self.drag_button, self.drag_points
        self._cancel_drag()
        carrier = self.carrier
        if carrier is None or len(points) < 2:
            return
        if math.hypot(points[-1][0] - points[0][0],
                      points[-1][1] - points[0][1]) < 2.0:
            return                                    # a tap, not a swipe

        if button == _RUN_BUTTON:
            self._start_run(points)
        else:
            self._dispose(carrier, points)

    # ── Decisions ───────────────────────────────────────────────────

    def _start_run(self, points):
        """Adopt the drawn path (clipped to HERO_PATH_MAX) and start running."""
        path, total = [], 0.0
        last = points[0]
        for pt in points[1:]:
            seg = math.hypot(pt[0] - last[0], pt[1] - last[1])
            if seg < 1.5:
                continue
            total += seg
            if total > settings.HERO_PATH_MAX:
                break
            path.append(mechanics.clamp_to_oval(*pt))
            last = pt
        if path:
            self.run_path = path
            self.mode = HS_RUN

    def _dispose(self, carrier, points):
        """A left-drag releases the ball: short = handball, long = kick."""
        end = points[-1]
        dist = carrier.distance_to(end)
        if dist > settings.HERO_KICK_MAX:            # cap the drawn range
            scale = settings.HERO_KICK_MAX / dist
            end = (carrier.x + (end[0] - carrier.x) * scale,
                   carrier.y + (end[1] - carrier.y) * scale)
            dist = settings.HERO_KICK_MAX
        self.pressure = mechanics.calculate_pressure(carrier, self.opponents)

        if dist <= settings.HERO_HANDBALL_MAX:
            self._handball(carrier, end, dist)
        else:
            self._kick(carrier, points, end, dist)

    def _handball(self, carrier, end, dist):
        """Quick flat pass toward the release point; needs a teammate there."""
        receivers = [t for t in self.teammates
                     if t is not carrier
                     and t.distance_to(end) <= settings.HERO_MARK_RADIUS]
        if not receivers:
            self._show_message("NO ONE THERE")
            return
        target = min(receivers, key=lambda t: t.distance_to(end))
        outcome = mechanics.resolve_handball(carrier, target, self.pressure)
        receiver = target if outcome["success"] else None
        landing = (target.pos if receiver
                   else mechanics.scatter_point(target.pos, 4.0))
        self._launch(carrier, landing, ctrl=None, dist=dist,
                     speed=settings.BALL_FLIGHT_SPEED * 1.3,
                     shot=False, receiver=receiver)

    def _kick(self, carrier, points, end, dist):
        """A drawn kick: swipe bend becomes curl, accuracy scatters the drop."""
        ctrl = mechanics.swipe_curve([carrier.pos] + points[1:-1] + [end])
        shot = mechanics.is_scoring_attempt(carrier.pos, end,
                                            settings.GOAL_RIGHT)
        if shot:
            landing = end                 # the scoring roll happens on arrival
        else:
            error = mechanics.hero_kick_error(self.pressure, dist)
            landing = mechanics.clamp_to_oval(
                *mechanics.scatter_point(end, error))
        self._launch(carrier, landing, ctrl=ctrl, dist=dist,
                     speed=settings.HERO_FLIGHT_SPEED, shot=shot,
                     receiver=None)

    def _launch(self, carrier, landing, ctrl, dist, speed, shot, receiver):
        """Put the ball in the air along a (possibly curved) path."""
        p0 = carrier.pos
        self.flight = {
            "p0": p0,
            "ctrl": ctrl if ctrl is not None
                    else ((p0[0] + landing[0]) / 2, (p0[1] + landing[1]) / 2),
            "p1": landing,
            "t": 0.0,
            "dur": max(dist / speed, 0.25),
            "dist": dist,
            "shot": shot,
            "receiver": receiver,
            "kicker": carrier,
        }
        carrier.is_ball_carrier = False
        self.ball.possessed_by = None
        self.run_path = []
        self.mode = HS_FLIGHT

    # ── Update loop ─────────────────────────────────────────────────

    def update(self, dt):
        """Advance the world; deep time dilation while a decision is drawn."""
        if self.message_timer > 0.0:
            self.message_timer -= dt
            if self.message_timer <= 0.0:
                self.message = ""

        if self.mode == HS_DONE:
            self.camera.update(dt, (self.camera.fx, self.camera.fz), False)
            return

        world_dt = dt * (settings.HERO_SLOWMO if self.in_decision else 1.0)
        self.timer = max(0.0, self.timer - world_dt)
        if self.timer <= 0.0:
            self._fail("THE CLOCK BEAT YOU")
            return

        self._update_leads(world_dt)
        if self.mode == HS_DECIDE:
            self._update_decide(world_dt)
        elif self.mode == HS_RUN:
            self._update_run(world_dt)
        elif self.mode == HS_FLIGHT:
            self._update_flight(world_dt)
        elif self.mode == HS_LOOSE:
            self._update_loose(world_dt)

        carrier = self.carrier
        self.pressure = (mechanics.calculate_pressure(carrier, self.opponents)
                         if carrier else 0.0)

        focus = (self.ball.pos if self.mode in (HS_FLIGHT, HS_LOOSE)
                 else (carrier.pos if carrier else self.ball.pos))
        self.camera.update(dt, focus, self.in_decision)

    def _update_leads(self, dt):
        """Leading teammates run their patterns whenever the world moves."""
        for player, target in self.leads.items():
            if not player.is_ball_carrier:
                mechanics._step_toward(player, target,
                                       settings.HERO_LEAD_SPEED, dt,
                                       stop_at=0.5)

    def _update_decide(self, dt):
        """The world creeps forward while the player reads the field."""
        carrier = self.carrier
        if carrier is not None:
            mechanics.update_hero_defenders(self.opponents, carrier.pos,
                                            self.teammates, dt)
        self.ball.follow_carrier()

    def _update_run(self, dt):
        """Carry out a drawn run: follow waypoints, dodge the tackle."""
        carrier = self.carrier
        if carrier is None:
            self.mode = HS_DECIDE
            return
        mechanics.update_hero_defenders(self.opponents, carrier.pos,
                                        self.teammates, dt)

        budget = settings.HERO_RUN_SPEED * dt
        while budget > 0.0 and self.run_path:
            wp = self.run_path[0]
            d = carrier.distance_to(wp)
            if d <= budget:
                carrier.x, carrier.y = wp
                self.run_path.pop(0)
                budget -= d
            else:
                carrier.x += (wp[0] - carrier.x) / d * budget
                carrier.y += (wp[1] - carrier.y) / d * budget
                budget = 0.0
        self.ball.follow_carrier()

        for opp in self.opponents:
            if opp.distance_to(carrier.pos) <= settings.HERO_TACKLE_RADIUS:
                self._fail("WRAPPED UP IN THE TACKLE")
                return
        if self._check_territory(carrier):
            return
        if not self.run_path:
            self.mode = HS_DECIDE       # breath taken — read the field again

    def _update_flight(self, dt):
        """Fly the ball along its bezier; defenders read it and close."""
        fl = self.flight
        fl["t"] = min(fl["t"] + dt / fl["dur"], 1.0)
        self.ball.x, self.ball.y = mechanics.bezier_point(
            fl["p0"], fl["ctrl"], fl["p1"], fl["t"])

        mechanics.update_hero_interceptors(self.opponents, fl["p1"], dt)
        interceptor = mechanics.try_hero_intercept(self.opponents,
                                                   self.ball.pos, fl["t"])
        if interceptor is not None and fl["t"] < 1.0:
            self.ball.give_to(interceptor)
            self._fail("READ AND CUT OFF")
            return
        if fl["t"] >= 1.0:
            self._arrive(fl)

    def _arrive(self, fl):
        """The ball has come down: score it, mark it, or spill it."""
        self.flight = None

        if fl["shot"]:
            result = mechanics.resolve_scoring_attempt(fl["p0"], fl["p1"])
            self._apply_shot(result)
            return

        if fl["receiver"] is not None:                # clean handball
            self._take_possession(fl["receiver"])
            return

        kind, player = mechanics.resolve_hero_landing(
            fl["p1"], self.teammates, self.opponents, fl["kicker"])
        if kind == "mark":
            if self.level["objective"] == "mark_lead":
                self._take_possession(player)
                self._win("MARK ON THE LEAD")
                return
            self._show_message("MARK")
            self._take_possession(player)
        elif kind == "contest":
            if player.team == settings.YELLOW:
                self._show_message("WON THE CONTEST")
                self._take_possession(player)
            else:
                self.ball.give_to(player)
                self._fail("BEATEN IN THE AIR")
        else:                                          # ground ball
            travel = (fl["p1"][0] - fl["p0"][0], fl["p1"][1] - fl["p0"][1])
            self.loose_point = mechanics.oval_ball_bounce(fl["p1"], travel)
            self.loose_timer = settings.HERO_LOOSE_DELAY
            self.mode = HS_LOOSE

    def _update_loose(self, dt):
        """An oval ball on the turf: it skids while everyone dives on it."""
        lp = self.loose_point
        d = math.hypot(lp[0] - self.ball.x, lp[1] - self.ball.y)
        if d > 0.3:
            step = min(settings.HERO_INTERCEPT_SPEED * 1.4 * dt, d)
            self.ball.x += (lp[0] - self.ball.x) / d * step
            self.ball.y += (lp[1] - self.ball.y) / d * step

        mechanics.update_hero_interceptors(self.opponents, lp, dt)
        gatherer = min(self.teammates, key=lambda t: t.distance_to(lp))
        mechanics._step_toward(gatherer, lp,
                               settings.HERO_INTERCEPT_SPEED, dt, stop_at=0.5)

        self.loose_timer -= dt
        if self.loose_timer > 0.0:
            return
        winner = mechanics.resolve_loose_ball(lp, self.teammates,
                                              self.opponents)
        if winner is None:
            self.loose_timer = 0.3                    # still scrambling
            return
        if winner.team == settings.YELLOW:
            self._show_message("GATHERED")
            self._take_possession(winner)
        else:
            self.ball.give_to(winner)
            self._fail("LOOSE BALL LOST")

    # ── Outcomes ────────────────────────────────────────────────────

    def _apply_shot(self, result):
        """Resolve a shot on goal against the level objective."""
        objective = self.level["objective"]
        if result == "goal":
            self._win("GOAL")
        elif result == "behind":
            if objective == "score":
                self._win("A BEHIND - IT COUNTS")
            else:
                self._fail("OFF LINE - A BEHIND ONLY")
        else:
            self._fail("MISSED EVERYTHING")

    def _take_possession(self, player):
        """A YELLOW player secures the ball; objectives may resolve."""
        for p in self.players:
            p.is_ball_carrier = False
        player.is_ball_carrier = True
        self.ball.give_to(player)
        if not self._check_territory(player):
            self.mode = HS_DECIDE

    def _check_territory(self, player):
        """Territory levels end the moment the ball is held past the line."""
        if (self.level["objective"] == "territory"
                and player.x >= self.level["territory_x"]):
            self._win("THROUGH THE PRESS")
            return True
        return False

    def _win(self, msg):
        self.mode = HS_DONE
        self.result = "win"
        self._show_message(msg)

    def _fail(self, msg):
        self.mode = HS_DONE
        self.result = "fail"
        self._show_message(msg)

    def _show_message(self, text):
        self.message = text
        self.message_timer = 2.5

    # ── Renderer support ────────────────────────────────────────────

    def drag_preview(self):
        """Live interpretation of the current drag, for hero_render.

        Returns None, or a dict:
          {"type": "run",  "points": [...]}
          {"type": "handball", "target": (x, y)}
          {"type": "kick", "samples": [...], "landing": (x, y),
           "error": float, "shot": bool}
        """
        carrier = self.carrier
        if self.drag_button is None or carrier is None \
                or len(self.drag_points) < 2:
            return None
        points = self.drag_points

        if self.drag_button == _RUN_BUTTON:
            return {"type": "run", "points": points}

        end = points[-1]
        dist = carrier.distance_to(end)
        if dist > settings.HERO_KICK_MAX:
            scale = settings.HERO_KICK_MAX / dist
            end = (carrier.x + (end[0] - carrier.x) * scale,
                   carrier.y + (end[1] - carrier.y) * scale)
            dist = settings.HERO_KICK_MAX
        if dist <= settings.HERO_HANDBALL_MAX:
            return {"type": "handball", "target": end}

        ctrl = mechanics.swipe_curve([carrier.pos] + points[1:-1] + [end])
        samples = [mechanics.bezier_point(carrier.pos, ctrl, end, i / 14.0)
                   for i in range(15)]
        pressure = mechanics.calculate_pressure(carrier, self.opponents)
        return {"type": "kick", "samples": samples, "landing": end,
                "error": mechanics.hero_kick_error(pressure, dist),
                "shot": mechanics.is_scoring_attempt(carrier.pos, end,
                                                     settings.GOAL_RIGHT)}

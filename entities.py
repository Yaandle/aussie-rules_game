"""entities.py — dumb data holders: Player and Ball.

These classes carry position and simple self-contained behavior only.
All game rules (pressure, kicks, contests, scoring) live in mechanics.py.
"""

import math

import settings


class Player:
    """A single player: position, team color, and whether they hold the ball."""

    def __init__(self, x, y, team, is_ball_carrier=False):
        self.x = float(x)
        self.y = float(y)
        self.team = team                    # settings.YELLOW or settings.RED
        self.is_ball_carrier = is_ball_carrier

    @property
    def pos(self):
        """Position as an (x, y) tuple."""
        return (self.x, self.y)

    def move(self, dx, dy, dt, speed=None):
        """Move by a normalized direction, clamped inside the field oval.

        `speed` overrides settings.PLAYER_SPEED for callers that want a
        different pace — FULL GAME passes settings.FULL_GAME_PLAYER_SPEED
        (or the character menu's live-adjusted value) for its carrier, for
        instance, same pattern as Ball.start_flight's `speed` param. Every
        other caller leaves it at the default and behaves exactly as before.

        Returns the distance actually travelled (used for the bounce rule).
        """
        if dx == 0 and dy == 0:
            return 0.0
        length = math.hypot(dx, dy)
        step = (speed if speed is not None else settings.PLAYER_SPEED) * dt
        nx = self.x + (dx / length) * step
        ny = self.y + (dy / length) * step

        # Clamp inside the field oval (ellipse test, slight inset for the border).
        rx = settings.FIELD_W / 2 - 2
        ry = settings.FIELD_H / 2 - 2
        ex = (nx - settings.FIELD_CX) / rx
        ey = (ny - settings.FIELD_CY) / ry
        if ex * ex + ey * ey > 1.0:
            return 0.0  # would leave the oval — stay put

        moved = math.hypot(nx - self.x, ny - self.y)
        self.x, self.y = nx, ny
        return moved

    def distance_to(self, point):
        """Straight-line distance from this player to an (x, y) point."""
        return math.hypot(self.x - point[0], self.y - point[1])


class Ball:
    """The football: either possessed by a player or in flight toward a point."""

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.possessed_by = None    # Player holding the ball, or None
        self.in_flight = False
        self._flight_from = None
        self._flight_to = None
        self._flight_t = 0.0        # 0..1 progress along the flight path
        self._flight_duration = 0.0
        self.flight_distance = 0.0  # total path length (drives the arc height)
        # Ground contact played out at the landing spot right after a
        # flight arrives — see start_bounce/advance_bounce. Two parts:
        # a vertical hop (bounce_height, purely cosmetic — read by
        # field_render, never affects gameplay) and a horizontal roll
        # (moves x/y a short, capped, decelerating distance along the
        # kick's own travel direction — this part IS real: a grounded
        # kick's actual resting spot ends up a little past where it
        # first touched down, same as a real footy, and that's where
        # players need to converge to gather it — see settings.py's
        # "Loose ball" section / GameState._update_loose_ball).
        self.bouncing = False
        self.bounce_height = 0.0
        self._bounce_hops_left = 0
        self._bounce_t = 0.0
        self._bounce_duration = 0.0
        self._bounce_peak = 0.0
        self._roll_dir = (0.0, 0.0)
        self._roll_origin = (0.0, 0.0)
        self._roll_total_distance = 0.0
        self._roll_elapsed = 0.0
        self._roll_duration = 0.0

    @property
    def pos(self):
        return (self.x, self.y)

    def give_to(self, player):
        """Attach the ball to a player and end any flight."""
        self.possessed_by = player
        self.in_flight = False
        self.bouncing = False
        self.bounce_height = 0.0
        self.x, self.y = player.x, player.y

    def start_flight(self, from_point, to_point, speed=None):
        """Launch the ball from one point toward another (kick/handball travel).

        `speed` overrides settings.BALL_FLIGHT_SPEED for callers that want
        a different pace — GOAL KICKING plays its flight out slower, for
        instance (settings.GOALKICK_FLIGHT_SPEED), so there's time to
        actually watch the kick. Every other caller leaves it at the
        default and behaves exactly as before.
        """
        self.possessed_by = None
        self.in_flight = True
        self.bouncing = False
        self.bounce_height = 0.0
        self._flight_from = from_point
        self._flight_to = to_point
        self._flight_t = 0.0
        dist = math.hypot(to_point[0] - from_point[0], to_point[1] - from_point[1])
        self.flight_distance = dist
        self._flight_duration = max(dist / (speed or settings.BALL_FLIGHT_SPEED), 0.1)
        self.x, self.y = from_point

    def advance_flight(self, dt):
        """Move the ball along its flight path. Returns True on arrival.

        Does NOT start the cosmetic ground-bounce itself — a clean mark
        or a successful handball catch means the ball never actually hits
        the turf, so the caller (GameState._apply_pending_outcome) decides
        whether this particular arrival warrants one (see start_bounce)
        once it knows what kind of outcome this flight resolved to.
        """
        if not self.in_flight:
            return False
        self._flight_t += dt / self._flight_duration
        if self._flight_t >= 1.0:
            self.x, self.y = self._flight_to
            self.in_flight = False
            return True
        t = self._flight_t
        fx, fy = self._flight_from
        tx, ty = self._flight_to
        self.x = fx + (tx - fx) * t
        self.y = fy + (ty - fy) * t
        return False

    def start_bounce(self, flight_distance):
        """Begin ground contact at the ball's current (x, y) — called
        automatically once a flight arrives. Two things start together:

        - A short, diminishing vertical hop (bounce_height, cosmetic —
          see advance_bounce). Longer kicks get a slightly higher first
          hop, same idea as hero_render's _flight_lift scaling lift with
          distance, capped so a full-length kick doesn't bounce
          unrealistically high.
        - A horizontal roll continuing along the flight's own travel
          direction (self._flight_from -> self._flight_to, still set
          from whichever start_flight produced this arrival), capped and
          decelerating to a stop — this genuinely moves x/y a short
          distance rather than leaving the ball dead-stopped exactly on
          the aimed target point, same as a real footy carries on a
          little after it hits the turf.

        `flight_distance == 0` (the boundary/ruck ball-up call site,
        which places the ball directly rather than via a flight) skips
        the roll entirely — there's no meaningful travel direction to
        roll along, and it's about to be picked up by a contest anyway.
        """
        self.bouncing = True
        self._bounce_hops_left = settings.BALL_BOUNCE_HOPS
        self._bounce_t = 0.0
        self._bounce_peak = min(flight_distance / 10.0, settings.BALL_BOUNCE_MAX_HEIGHT)
        self._bounce_duration = settings.BALL_BOUNCE_HOP_DURATION
        self.bounce_height = 0.0

        self._roll_dir = (0.0, 0.0)
        self._roll_total_distance = 0.0
        self._roll_elapsed = 0.0
        self._roll_duration = settings.BALL_ROLL_DURATION
        self._roll_origin = (self.x, self.y)
        if flight_distance > 0.0 and self._flight_from is not None and self._flight_to is not None:
            fx, fy = self._flight_from
            tx, ty = self._flight_to
            length = math.hypot(tx - fx, ty - fy)
            if length > 0.01:
                self._roll_dir = ((tx - fx) / length, (ty - fy) / length)
                self._roll_total_distance = min(
                    flight_distance * settings.BALL_ROLL_DISTANCE_FACTOR,
                    settings.BALL_ROLL_MAX_DISTANCE)

    def advance_bounce(self, dt):
        """Step ground contact forward one frame: the vertical hop
        sequence (each hop progressively lower/quicker until it settles
        flat) and the horizontal roll (decelerating to a stop), running
        side by side. `bouncing` stays True until BOTH are finished."""
        if not self.bouncing:
            return

        self._bounce_t += dt
        t = min(self._bounce_t / self._bounce_duration, 1.0)
        # A single hop's height follows the same sine arc real flight
        # uses (see hero_render._flight_lift) — up and back down to zero.
        self.bounce_height = math.sin(math.pi * t) * self._bounce_peak
        hops_done = False
        if t >= 1.0:
            self._bounce_hops_left -= 1
            if self._bounce_hops_left <= 0:
                hops_done = True
                self.bounce_height = 0.0
            else:
                # Each successive hop is lower and a touch quicker, same
                # "settling down" shape a real ball loses energy in.
                self._bounce_peak *= settings.BALL_BOUNCE_DECAY
                self._bounce_duration *= settings.BALL_BOUNCE_DECAY
                self._bounce_t = 0.0

        roll_done = True
        if self._roll_dir != (0.0, 0.0) and self._roll_elapsed < self._roll_duration:
            self._roll_elapsed = min(self._roll_elapsed + dt, self._roll_duration)
            frac = self._roll_elapsed / self._roll_duration
            # Ease-out matching constant deceleration (like real ground
            # friction): distance covered rises fast at first, tapering
            # to a dead stop exactly at frac == 1.0.
            progress = 2.0 * frac - frac * frac
            dist = self._roll_total_distance * progress
            nx = self._roll_origin[0] + self._roll_dir[0] * dist
            ny = self._roll_origin[1] + self._roll_dir[1] * dist
            # Inline oval clamp (mirrors Player.move's own inline clamp —
            # entities.py deliberately doesn't import mechanics.py, see
            # this module's docstring). If the roll would carry it past
            # the boundary, it just stops there instead of crossing.
            rx = settings.FIELD_W / 2 - 2
            ry = settings.FIELD_H / 2 - 2
            ex = (nx - settings.FIELD_CX) / rx
            ey = (ny - settings.FIELD_CY) / ry
            if ex * ex + ey * ey <= 1.0:
                self.x, self.y = nx, ny
            else:
                self._roll_elapsed = self._roll_duration  # stop rolling in place
            roll_done = self._roll_elapsed >= self._roll_duration

        if hops_done and roll_done:
            self.bouncing = False
            self.bounce_height = 0.0

    @property
    def flight_progress(self):
        """0..1 progress along the current flight (1.0 when landed/held)."""
        return min(self._flight_t, 1.0)

    def follow_carrier(self):
        """Keep the ball glued to its carrier while possessed. A no-op
        whenever possessed_by is None — which now covers a genuinely
        long-lived state, not just a brief instant: a grounded kick or
        spilled handball leaves the ball entirely unpossessed (see
        possession.LOOSE_BALL / GameState._start_loose_ball) until some
        player actually reaches it, so there's no carrier to follow for
        as long as that takes.

        Also skipped while a ground-bounce/roll is still playing even if
        possessed_by IS already set (see start_bounce/advance_bounce) —
        _apply_pending_outcome's old "turnover" path used to hand the
        ball to a player immediately and only then start the bounce at
        the (now stale) landing spot; snapping straight to that player
        first would have cut the bounce off after a single frame.
        """
        if self.possessed_by is not None and not self.bouncing:
            self.x, self.y = self.possessed_by.x, self.possessed_by.y

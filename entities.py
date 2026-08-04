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

    def move(self, dx, dy, dt):
        """Move by a normalized direction, clamped inside the field oval.

        Returns the distance actually travelled (used for the bounce rule).
        """
        if dx == 0 and dy == 0:
            return 0.0
        length = math.hypot(dx, dy)
        step = settings.PLAYER_SPEED * dt
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

    @property
    def pos(self):
        return (self.x, self.y)

    def give_to(self, player):
        """Attach the ball to a player and end any flight."""
        self.possessed_by = player
        self.in_flight = False
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
        self._flight_from = from_point
        self._flight_to = to_point
        self._flight_t = 0.0
        dist = math.hypot(to_point[0] - from_point[0], to_point[1] - from_point[1])
        self.flight_distance = dist
        self._flight_duration = max(dist / (speed or settings.BALL_FLIGHT_SPEED), 0.1)
        self.x, self.y = from_point

    def advance_flight(self, dt):
        """Move the ball along its flight path. Returns True on arrival."""
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

    @property
    def flight_progress(self):
        """0..1 progress along the current flight (1.0 when landed/held)."""
        return min(self._flight_t, 1.0)

    def follow_carrier(self):
        """Keep the ball glued to its carrier while possessed."""
        if self.possessed_by is not None:
            self.x, self.y = self.possessed_by.x, self.possessed_by.y

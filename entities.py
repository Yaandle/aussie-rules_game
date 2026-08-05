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
        # Cosmetic ground-bounce, played out at the landing spot right
        # after a flight arrives — see start_bounce/advance_bounce. Purely
        # visual: it only ever drives bounce_height (read by field_render
        # for an extra hop or two before the ball settles), never x/y, so
        # nothing that resolves outcomes off the ball's actual position
        # (GameState._apply_pending_outcome, the OOB checks, etc.) needs
        # to know this exists or wait for it to finish.
        self.bouncing = False
        self.bounce_height = 0.0
        self._bounce_hops_left = 0
        self._bounce_t = 0.0
        self._bounce_duration = 0.0
        self._bounce_peak = 0.0

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
        """Begin a short, diminishing ground-bounce at the ball's current
        (x, y) — called automatically once a flight arrives. Longer kicks
        get a slightly higher first hop, same idea as hero_render's
        _flight_lift scaling lift with distance, capped so a full-length
        kick doesn't bounce unrealistically high.
        """
        self.bouncing = True
        self._bounce_hops_left = settings.BALL_BOUNCE_HOPS
        self._bounce_t = 0.0
        self._bounce_peak = min(flight_distance / 10.0, settings.BALL_BOUNCE_MAX_HEIGHT)
        self._bounce_duration = settings.BALL_BOUNCE_HOP_DURATION
        self.bounce_height = 0.0

    def advance_bounce(self, dt):
        """Step the cosmetic bounce forward; each hop is progressively
        lower and quicker than the last until it settles flat."""
        if not self.bouncing:
            return
        self._bounce_t += dt
        t = min(self._bounce_t / self._bounce_duration, 1.0)
        # A single hop's height follows the same sine arc real flight
        # uses (see hero_render._flight_lift) — up and back down to zero.
        self.bounce_height = math.sin(math.pi * t) * self._bounce_peak
        if t >= 1.0:
            self._bounce_hops_left -= 1
            if self._bounce_hops_left <= 0:
                self.bouncing = False
                self.bounce_height = 0.0
                return
            # Each successive hop is lower and a touch quicker, same
            # "settling down" shape a real ball loses energy in.
            self._bounce_peak *= settings.BALL_BOUNCE_DECAY
            self._bounce_duration *= settings.BALL_BOUNCE_DECAY
            self._bounce_t = 0.0

    @property
    def flight_progress(self):
        """0..1 progress along the current flight (1.0 when landed/held)."""
        return min(self._flight_t, 1.0)

    def follow_carrier(self):
        """Keep the ball glued to its carrier while possessed.

        Deliberately skipped while a cosmetic ground-bounce is still
        playing (see start_bounce/advance_bounce): a turnover's bounce
        happens at the landing spot, which can be well away from
        whichever player picks the loose ball up (there's no "walk over
        and gather it" animation in this engine — possession changes
        hands instantly) — snapping straight to them would cut the
        bounce off after a single frame instead of letting it play out
        where the ball actually landed. GameState.update() ends the
        bounce and lets this resume once advance_bounce finishes.
        """
        if self.possessed_by is not None and not self.bouncing:
            self.x, self.y = self.possessed_by.x, self.possessed_by.y

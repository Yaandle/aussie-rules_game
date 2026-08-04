"""mechanics.py — pure probability and resolution logic.

No Pygame imports, no drawing, no input. Every function takes plain
positions/players and returns plain results, so this module can be
unit-tested in isolation.
"""

import math
import random

import settings

# EXTEND: tackling interaction when carrier is under high pressure
# EXTEND: ruck contest at start of play / after a goal
# EXTEND: man-on-man, zone, and interceptor defender behaviours
#         (closing-pressure behaviour implemented in update_defenders below)


def _dist(a, b):
    """Distance between two (x, y) points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def update_defenders(opponents, carrier_pos, dt, home_positions=None):
    """Closing-pressure AI: the nearest defenders converge on the carrier.

    Only the closest MAX_CHASERS defenders within CHASE_RADIUS give chase,
    at a deliberate walk, and they pull up at arm's length — enough to
    threaten pressure without tackling (see EXTEND notes above).

    Everyone else on the side is idle by default, which was fine against
    a handful of opponents but reads as a wall of statues at full 18-a-side
    strength. When `home_positions` is supplied (FULL GAME only — see
    update_off_ball), the non-chasing rest of the team eases toward their
    kickoff formation spot blended with the ball, holding rough team shape
    instead of standing frozen. Scenarios pass None and keep their
    original, fully-static non-chasers untouched.
    """
    chasers = sorted(opponents,
                     key=lambda o: o.distance_to(carrier_pos))[:settings.MAX_CHASERS]
    chaser_ids = {id(o) for o in chasers}
    for opp in chasers:
        d = opp.distance_to(carrier_pos)
        if d > settings.CHASE_RADIUS or d <= settings.DEFENDER_MIN_DIST:
            continue
        step = min(settings.DEFENDER_SPEED * dt, d - settings.DEFENDER_MIN_DIST)
        nx = opp.x + (carrier_pos[0] - opp.x) / d * step
        ny = opp.y + (carrier_pos[1] - opp.y) / d * step
        # Stay inside the field oval (same clamp the carrier obeys).
        rx = settings.FIELD_W / 2 - 2
        ry = settings.FIELD_H / 2 - 2
        ex = (nx - settings.FIELD_CX) / rx
        ey = (ny - settings.FIELD_CY) / ry
        if ex * ex + ey * ey <= 1.0:
            opp.x, opp.y = nx, ny

    if home_positions:
        resting = [o for o in opponents if id(o) not in chaser_ids]
        update_off_ball(resting, home_positions, carrier_pos, dt)


def update_off_ball(players, home_positions, focus_pos, dt):
    """Ease off-ball players toward a blend of their kickoff "home" spot
    and the ball, so the far side of the ground holds rough team shape
    while the near side leans into the contest.

    `home_positions` maps id(player) -> the (x, y) formation spot they
    were kicked off from (captured once in GameState._load_layout).
    OFF_BALL_DRIFT caps how far off that home spot the ball pulls them —
    small, so the formation stays recognisable. This is shape-holding,
    not real off-ball running: just enough that a full 36-player oval
    doesn't read as half statues.
    """
    for p in players:
        home = home_positions.get(id(p))
        if home is None:
            continue
        tx = home[0] + (focus_pos[0] - home[0]) * settings.OFF_BALL_DRIFT
        ty = home[1] + (focus_pos[1] - home[1]) * settings.OFF_BALL_DRIFT
        _step_toward(p, (tx, ty), settings.OFF_BALL_SPEED, dt, stop_at=1.0)


def calculate_pressure(ball_carrier, opponents):
    """Pressure on the carrier, 0.0 (free) to 1.0 (smothered).

    Inverse function of distance to the nearest RED player: an opponent
    standing on top of the carrier gives 1.0, one at PRESSURE_RADIUS or
    beyond gives 0.0.
    """
    if not opponents:
        return 0.0
    nearest = min(opp.distance_to(ball_carrier.pos) for opp in opponents)
    return max(0.0, min(1.0, 1.0 - nearest / settings.PRESSURE_RADIUS))


def handball_accuracy(pressure):
    """Success chance for a handball at the given pressure level."""
    return settings.HANDBALL_BASE_ACC * (1.0 - settings.PRESSURE_PENALTY_HB * pressure)


def kick_accuracy(pressure, distance):
    """Success chance for a kick, eroded by pressure and by distance."""
    dist_factor = min(distance / settings.KICK_MAX_RANGE, 1.0)
    acc = settings.KICK_BASE_ACC
    acc *= 1.0 - settings.PRESSURE_PENALTY_KICK * pressure
    acc *= 1.0 - settings.KICK_DISTANCE_PENALTY * dist_factor
    return acc


def resolve_handball(carrier, target_teammate, pressure):
    """Resolve a handball attempt.

    Returns {"success": bool, "receiver": Player} — on failure the caller
    treats it as a turnover at the target's location.
    """
    chance = handball_accuracy(pressure)
    return {"success": random.random() < chance, "receiver": target_teammate}


def resolve_kick(carrier, target_point, opponents, teammates, pressure):
    """Resolve a kick toward target_point.

    Returns a dict with:
      "result": "mark" | "contest" | "turnover"
      "winner": the Player who ends up with the ball (None only if no
                players exist at all)
    Rules:
      - A RED player within CONTEST_RADIUS of the target forces a contest,
        resolved by proximity-weighted roll (resolve_contest).
      - Otherwise a clean accuracy roll: success gives the mark to the
        nearest teammate in MARK_RADIUS (or the carrier retains if none);
        failure is a turnover to the nearest RED player.
    """
    distance = _dist(carrier.pos, target_point)

    contesting = [o for o in opponents
                  if o.distance_to(target_point) <= settings.CONTEST_RADIUS]
    if contesting:
        candidates = contesting + [t for t in teammates
                                   if t.distance_to(target_point) <= settings.CONTEST_RADIUS
                                   and t is not carrier]
        winner = resolve_contest(target_point, candidates)
        result = "contest"
        return {"result": result, "winner": winner}

    if random.random() < kick_accuracy(pressure, distance):
        receivers = [t for t in teammates
                     if t is not carrier
                     and t.distance_to(target_point) <= settings.MARK_RADIUS]
        if receivers:
            winner = min(receivers, key=lambda t: t.distance_to(target_point))
        else:
            winner = carrier  # uncontested mark retained by the carrier
        return {"result": "mark", "winner": winner}

    # Missed kick: nearest opponent to the landing spot takes possession.
    winner = min(opponents, key=lambda o: o.distance_to(target_point)) if opponents else carrier
    return {"result": "turnover", "winner": winner}


def resolve_contest(target_point, nearby_players):
    """Weighted random roll among players near a contested ball drop.

    Each player's weight is the inverse of their distance to the target,
    so closer players are favored but never guaranteed.
    """
    weights = [1.0 / (p.distance_to(target_point) + 0.5) for p in nearby_players]
    return random.choices(nearby_players, weights=weights, k=1)[0]


# ── AFL Hero mode helpers (pure; used by hero_state) ────────────────
# Hero outcomes resolve interactively (interception mid-flight, marks at
# landing) rather than via the top-down _pending_outcome pattern, because
# defenders keep moving while the ball is in the air.

def clamp_to_oval(x, y):
    """Pull a point back inside the playing oval if it has strayed out."""
    rx = settings.FIELD_W / 2 - 2
    ry = settings.FIELD_H / 2 - 2
    ex = (x - settings.FIELD_CX) / rx
    ey = (y - settings.FIELD_CY) / ry
    d = math.sqrt(ex * ex + ey * ey)
    if d <= 1.0:
        return (x, y)
    return (settings.FIELD_CX + ex / d * rx, settings.FIELD_CY + ey / d * ry)


def bezier_point(p0, ctrl, p1, t):
    """Quadratic bezier sample — the curved flight path of a hero kick."""
    inv = 1.0 - t
    return (inv * inv * p0[0] + 2 * inv * t * ctrl[0] + t * t * p1[0],
            inv * inv * p0[1] + 2 * inv * t * ctrl[1] + t * t * p1[1])


def swipe_curve(points):
    """Signed lateral bend of a drawn swipe, as a bezier control point.

    Measures how far the swipe's midpoint sits off the straight chord
    from first to last point — sideways only — clamped to HERO_CURVE_MAX.
    A straight (or too-short) swipe returns the chord midpoint.
    """
    p0, p1 = points[0], points[-1]
    chord_mx = (p0[0] + p1[0]) / 2
    chord_my = (p0[1] + p1[1]) / 2
    if len(points) < 3:
        return (chord_mx, chord_my)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return (chord_mx, chord_my)
    px, py = -dy / length, dx / length          # unit perpendicular
    mid = points[len(points) // 2]
    off = (mid[0] - chord_mx) * px + (mid[1] - chord_my) * py
    off = max(-settings.HERO_CURVE_MAX, min(settings.HERO_CURVE_MAX, off))
    # Doubling the offset makes the bezier actually pass near the midpoint.
    return (chord_mx + px * off * 2, chord_my + py * off * 2)


def hero_kick_error(pressure, distance):
    """Landing scatter radius for a hero kick — pressure and range hurt."""
    dist_factor = min(distance / settings.HERO_KICK_MAX, 1.0)
    return 1.5 + 6.0 * dist_factor + 5.0 * pressure


def scatter_point(point, radius, rng=random):
    """A random point inside `radius` of `point` (kick inaccuracy)."""
    angle = rng.uniform(0.0, math.tau)
    r = radius * math.sqrt(rng.random())
    return (point[0] + math.cos(angle) * r, point[1] + math.sin(angle) * r)


def oval_ball_bounce(landing, travel_dir, rng=random):
    """Where an unmarked oval ball ends up after its unpredictable bounce.

    Mostly bounces on, roughly along the kick direction, but with real
    sideways scatter — the AFL ball keeps nobody honest.
    """
    dx, dy = travel_dir
    length = math.hypot(dx, dy) or 1.0
    fwd = settings.HERO_BOUNCE_SCATTER * (0.4 + 0.6 * rng.random())
    side = settings.HERO_BOUNCE_SCATTER * (rng.random() - 0.5)
    bx = landing[0] + dx / length * fwd - dy / length * side
    by = landing[1] + dy / length * fwd + dx / length * side
    return clamp_to_oval(bx, by)


def update_hero_defenders(opponents, carrier_pos, teammates, dt):
    """Hero defence: two nearest press the carrier, the rest man-mark.

    Markers stand between their nearest YELLOW target and where the ball
    would come from, closing space and shadowing leads.
    """
    by_dist = sorted(opponents, key=lambda o: o.distance_to(carrier_pos))
    pressers = by_dist[:settings.MAX_CHASERS]
    for opp in pressers:
        _step_toward(opp, carrier_pos, settings.HERO_PRESS_SPEED, dt,
                     stop_at=settings.DEFENDER_MIN_DIST * 0.6)
    receivers = [t for t in teammates if not t.is_ball_carrier]
    for opp in by_dist[settings.MAX_CHASERS:]:
        if not receivers:
            break
        man = min(receivers, key=lambda t: t.distance_to(opp.pos))
        # Sit on the ball side of the man: a step from him toward the carrier.
        gx = man.x + (carrier_pos[0] - man.x) * 0.15
        gy = man.y + (carrier_pos[1] - man.y) * 0.15
        _step_toward(opp, (gx, gy), settings.HERO_PRESS_SPEED * 0.85, dt,
                     stop_at=1.5)


def update_hero_interceptors(opponents, landing_point, dt):
    """Defenders near a kick's drop zone converge on it while it flies."""
    for opp in opponents:
        if opp.distance_to(landing_point) <= settings.HERO_INTERCEPT_RADIUS:
            _step_toward(opp, landing_point, settings.HERO_INTERCEPT_SPEED,
                         dt, stop_at=0.5)


def try_hero_intercept(opponents, ball_pos, flight_progress):
    """The defender who cuts off a dropping ball, or None.

    Only possible late in flight (the ball is up out of reach before
    HERO_INTERCEPT_WINDOW) and within arm's length of the ball's shadow.
    """
    if flight_progress < settings.HERO_INTERCEPT_WINDOW:
        return None
    for opp in opponents:
        if opp.distance_to(ball_pos) <= settings.HERO_INTERCEPT_GRAB:
            return opp
    return None


def resolve_hero_landing(landing, teammates, opponents, kicker):
    """Classify a hero kick's arrival: mark, contest, or ground ball.

    Returns ("mark", player) / ("contest", winner) / ("ground", None).
    """
    markers = [t for t in teammates
               if t is not kicker
               and t.distance_to(landing) <= settings.HERO_MARK_RADIUS]
    spoilers = [o for o in opponents
                if o.distance_to(landing) <= settings.HERO_MARK_RADIUS]
    if markers and spoilers:
        return ("contest", resolve_contest(landing, markers + spoilers))
    if markers:
        return ("mark", min(markers, key=lambda t: t.distance_to(landing)))
    if spoilers:
        return ("contest", resolve_contest(landing, spoilers))
    return ("ground", None)


def resolve_loose_ball(point, teammates, opponents):
    """Scramble for a bouncing loose ball: nearest players roll for it.

    Returns the winning Player, or None when nobody is close enough
    (the nearest YELLOW player should then be sent to gather it).
    """
    nearby = [p for p in teammates + opponents
              if p.distance_to(point) <= settings.HERO_LOOSE_RADIUS]
    if not nearby:
        return None
    return resolve_contest(point, nearby)


def _step_toward(player, point, speed, dt, stop_at=0.0):
    """Move a player toward a point at `speed`, clamped to the oval."""
    d = player.distance_to(point)
    if d <= stop_at or d == 0.0:
        return
    step = min(speed * dt, d - stop_at)
    nx = player.x + (point[0] - player.x) / d * step
    ny = player.y + (point[1] - player.y) / d * step
    player.x, player.y = clamp_to_oval(nx, ny)


def is_scoring_attempt(kick_origin, target_point, goal_center):
    """True when a kick should be treated as a shot on goal.

    The kick must be launched from inside the scoring arc and aimed
    within SCORING_MAX_ANGLE degrees of the direct line to goal.
    """
    if _dist(kick_origin, goal_center) > settings.SCORING_ARC_RADIUS:
        return False
    to_goal = (goal_center[0] - kick_origin[0], goal_center[1] - kick_origin[1])
    to_target = (target_point[0] - kick_origin[0], target_point[1] - kick_origin[1])
    mag = math.hypot(*to_goal) * math.hypot(*to_target)
    if mag == 0:
        return False
    cos_a = (to_goal[0] * to_target[0] + to_goal[1] * to_target[1]) / mag
    angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
    return angle <= settings.SCORING_MAX_ANGLE


def resolve_scoring_attempt(kick_origin, target_point):
    """Resolve a shot on goal into "goal", "behind", or "miss".

    Longer and more angled shots are less likely to split the middle.
    Distance and angle each erode goal probability; a wide draw becomes
    a behind, and the worst rolls miss entirely.
    """
    goal = settings.GOAL_RIGHT
    distance = _dist(kick_origin, goal)
    dist_factor = min(distance / settings.SCORING_ARC_RADIUS, 1.0)

    # Angle off the direct goal axis, 0 (straight in front) .. 1 (max angle).
    dx = goal[0] - kick_origin[0]
    dy = goal[1] - kick_origin[1]
    angle = abs(math.degrees(math.atan2(dy, dx)))
    angle = min(angle, 180.0 - angle)  # fold to 0..90 off the horizontal axis
    angle_factor = min(angle / settings.SCORING_MAX_ANGLE, 1.0)

    p_goal = 0.75 * (1.0 - 0.45 * dist_factor) * (1.0 - 0.5 * angle_factor)
    p_behind = 0.20 + 0.15 * dist_factor  # wayward shots drift into behinds

    roll = random.random()
    if roll < p_goal:
        return "goal"
    if roll < p_goal + p_behind:
        return "behind"
    return "miss"


# ── GOAL KICKING mode helpers (pure) ─────────────────────────────────
# The practice range's own resolution: a timed power/accuracy meter and
# a crosswind, instead of a clicked target point. Distance/angle-off-goal
# difficulty follows the same shape as resolve_scoring_attempt above;
# meter timing (power_quality, aim_angle_deg) and wind layer on top.

def kick_axes(from_point, to_point):
    """Forward (from_point -> to_point) and right unit vectors.

    The local axes for GOAL KICKING's camera and entity projection,
    which — unlike the fixed broadcast rigs (MAIN_CAM/HERO_CAM), which
    never yaw and always show goals left/right — always faces whichever
    goal the current kick is aimed at.
    """
    fx = to_point[0] - from_point[0]
    fy = to_point[1] - from_point[1]
    length = math.hypot(fx, fy) or 1.0
    fwd = (fx / length, fy / length)
    right = (-fwd[1], fwd[0])
    return fwd, right


def aim_ray_point(origin, fwd, right, angle_deg, distance):
    """A point `distance` out from `origin`, along `fwd` (from kick_axes)
    rotated by `angle_deg` toward `right`.

    Used for the GOAL KICKING aim reticle: wherever this lands is where
    the kick is currently pointed, before the timing meter's precision
    wobble gets added on top.
    """
    rad = math.radians(angle_deg)
    dx = fwd[0] * math.cos(rad) + right[0] * math.sin(rad)
    dy = fwd[1] * math.cos(rad) + right[1] * math.sin(rad)
    return (origin[0] + dx * distance, origin[1] + dy * distance)


def to_kick_space(origin, fwd, right, point):
    """World (x, y) -> local (x, z) around `origin`, aligned to the
    `fwd`/`right` axes from kick_axes, ready for HeroCamera.project().

    Local z shrinks toward (and past) zero as a point nears the goal,
    matching the "small z is far" convention HeroCamera already uses
    for every other camera in the game.
    """
    dx = point[0] - origin[0]
    dy = point[1] - origin[1]
    forward_dist = dx * fwd[0] + dy * fwd[1]
    lateral = dx * right[0] + dy * right[1]
    return (lateral, -forward_dist)


def smoothstep(t):
    """Ease-in-out a 0..1 progress value — cheap, no overshoot. Drives the
    GOAL KICKING camera's wide-to-tight swoop (see GoalKickState's
    GK_TRANSITION), where a plain linear blend would feel mechanical."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def triangle_wave(elapsed, period):
    """0..1 triangle wave: rises for the first half of `period`, falls for
    the second half. Drives the GOAL KICKING power/accuracy meters."""
    phase = (elapsed % period) / period
    return 1.0 - abs(2.0 * phase - 1.0)


def roll_wind():
    """A fresh crosswind for one GOAL KICKING attempt: signed strength up
    to GOALKICK_WIND_MAX (positive blows the ball toward +y — "right" as
    the kicker looks down the line at goal)."""
    return random.uniform(-settings.GOALKICK_WIND_MAX, settings.GOALKICK_WIND_MAX)


def wind_angle_effect(wind_speed, distance):
    """Convert a crosswind (roll_wind units) and kick distance into the
    equivalent uncompensated aim drift, in degrees.

    Longer kicks spend more time exposed to the wind, so the same
    breeze pushes them further off line.
    """
    dist_factor = min(distance / settings.GOALKICK_MAX_RANGE, 1.0)
    return wind_speed * dist_factor * settings.GOALKICK_WIND_DEG_PER_UNIT


def goalkick_power_quality(power_t, ideal_t):
    """0..1 timing quality for the power meter: 1.0 when the locked value
    exactly matches the distance-scaled ideal, decaying to 0 once the
    miss reaches GOALKICK_POWER_TOLERANCE."""
    error = abs(power_t - ideal_t)
    return max(0.0, 1.0 - error / settings.GOALKICK_POWER_TOLERANCE)


def resolve_goalkick(mark_pos, aim_angle_deg, power_quality, wind_deg):
    """Resolve a timed GOAL KICKING attempt into "goal" / "behind" / "miss".

    Follows the same distance/angle-off-goal difficulty curve as a shot
    on goal elsewhere (resolve_scoring_attempt), layered with the
    kicker's timing skill: `aim_angle_deg` is the angle locked on the
    accuracy meter (0 = dead straight at goal), `wind_deg` is the wind's
    uncompensated push added on top, and `power_quality` (0..1, 1 =
    perfectly timed) is how well the power meter matched the distance —
    badly undercooked power rules a goal out entirely.
    """
    goal = settings.GOAL_RIGHT
    distance = _dist(mark_pos, goal)
    dist_factor = min(distance / settings.GOALKICK_MAX_RANGE, 1.0)

    final_angle = abs(aim_angle_deg + wind_deg)
    angle_factor = min(final_angle / settings.GOALKICK_ACC_SPREAD, 1.0)

    p_goal = (0.88 * power_quality
              * (1.0 - 0.4 * dist_factor)
              * (1.0 - angle_factor) ** 1.6)
    p_behind = max(0.0, 0.22 + 0.20 * angle_factor - 0.12 * power_quality)
    if power_quality < 0.3:               # badly undercooked — never a goal
        p_goal = 0.0

    roll = random.random()
    if roll < p_goal:
        return "goal"
    if roll < p_goal + p_behind:
        return "behind"
    return "miss"


def goalkick_landing_point(mark_pos, result, aim_angle_deg, wind_deg, power_quality):
    """A plausible landing spot for the flight animation, consistent with
    an already-decided resolve_goalkick() result.

    The outcome is decided first (probability, not physics); this only
    stages where the ball visibly comes down to match it — through the
    main posts for a goal, wide of them but inside the points for a
    behind, and either short (badly undercooked power) or well wide
    otherwise for a miss.
    """
    goal = settings.GOAL_RIGHT
    side = 1.0 if (aim_angle_deg + wind_deg) >= 0.0 else -1.0

    if result == "goal":
        y = settings.FIELD_CY + side * random.uniform(0.0, 2.0)
        return (goal[0], y)
    if result == "behind":
        y = settings.FIELD_CY + side * random.uniform(3.5, 6.5)
        return (goal[0], y)

    if power_quality < 0.3:               # fell short, never reached the line
        frac = 0.55 + 0.25 * power_quality
        return (mark_pos[0] + (goal[0] - mark_pos[0]) * frac,
                mark_pos[1] + (goal[1] - mark_pos[1]) * frac)
    y = settings.FIELD_CY + side * random.uniform(8.0, 13.0)  # well wide
    return (goal[0], y)

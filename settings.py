"""settings.py — all tunable constants for the AFL prototype.

No logic lives here. Every other module imports from this file so the
whole game can be re-balanced or re-themed from one place.
"""

# ── Core palette ────────────────────────────────────────────────────
BG     = "#f9f3ef"   # warm off-white (flashes, highlights)
INK    = "#22241d"   # deep charcoal-green (outlines, hard borders)
YELLOW = "#e9c95e"   # ball-carrier team guernsey (muted gold)
RED    = "#c95f55"   # opponents' guernsey (muted brick)

# ── Scene palette (light pastel sage, hazy diffuse light) ───────────
GRASS_OUT   = "#acbf85"   # surrounds outside the boundary
BEYOND      = "#bfcc9a"   # hazy paddock beyond the fences
GRASS_IN    = "#b2c589"   # playing surface, mown band A
GRASS_IN2   = "#b6c98d"   # playing surface, mown band B (near-uniform)
GRASS_DARK  = "#9db077"   # speckle shade
GRASS_LIGHT = "#c9d89e"   # speckle highlight
MOSS        = "#8a9c66"   # tufts / contact shadows
GRASS_EDGE  = "#93a76c"   # oval extrusion side (faux thickness)
GRASS_EDGE_SHADOW = "#a1b276"  # soft ground shadow under the extrusion
LINE        = "#f4f1e0"   # soft-cream field markings & post shafts
TREE        = "#66794e"   # canopy
TREE_DARK   = "#546741"   # canopy shading
TREE_LIGHT  = "#788c5c"   # canopy lit speckle
WOOD        = "#6b5a40"   # trunks
WOOD_DARK   = "#544733"   # trunk shading
FENCE       = "#454738"   # dark rail fences and benches
POST_RED    = "#c65449"   # red band at the base of each post
ACCENT_RED  = "#c65449"   # scoreboard dot, warnings, countdown
DIRT        = "#b0a273"   # worn patches
SKIN        = "#ecc9a0"   # player face/limb pixels
HAIR        = "#2c241d"   # the big dark mop
SHORTS      = "#2a2c33"   # player shorts
BALL_BROWN  = "#8a5a35"   # the football
UI_CHARCOAL = "#33362e"   # scoreboard fill
CREAM       = "#ebe4cc"   # scoreboard text
WARM_LIGHT  = (238, 246, 210)  # hazy green-white tint (alpha in render)

# ── Resolution & scaling ────────────────────────────────────────────
# Finer logical grid than before = a "zoomed out" scene: sprites stay
# small while the frame gains breathing room around the oval.
LOGICAL_W = 200          # logical pixel grid (structural layer)
LOGICAL_H = 112
SCALE     = 6            # nearest-neighbor upscale factor
WINDOW_W  = LOGICAL_W * SCALE   # 1200
WINDOW_H  = LOGICAL_H * SCALE   # 672
FPS       = 60

# ── Field geometry (logical units) ──────────────────────────────────
# Reference-image proportions: the oval spans ~85% of frame width with a
# quiet band of surrounds — players read smaller against more open grass.
FIELD_MARGIN_X = 20
FIELD_MARGIN_Y = 14
FIELD_LEFT   = FIELD_MARGIN_X
FIELD_TOP    = FIELD_MARGIN_Y
FIELD_W      = LOGICAL_W - 2 * FIELD_MARGIN_X   # 160
FIELD_H      = LOGICAL_H - 2 * FIELD_MARGIN_Y   # 84
FIELD_CX     = LOGICAL_W / 2
FIELD_CY     = LOGICAL_H / 2

# Goals sit at the extreme left/right of the oval on the horizontal axis.
GOAL_RIGHT = (FIELD_LEFT + FIELD_W, FIELD_CY)   # YELLOW attacks right
GOAL_LEFT  = (FIELD_LEFT, FIELD_CY)
SCORING_ARC_RADIUS = 40   # the 50m arc: kicks from inside may score
SCORING_MAX_ANGLE  = 55   # degrees off the goal axis still counted a shot

# ── Match rules ─────────────────────────────────────────────────────
QUARTER_LENGTH  = 180.0   # seconds, single quarter (full game mode)
BOUNCE_INTERVAL = 15.0    # logical units of running allowed between bounces

# ── Movement / action tuning ────────────────────────────────────────
PLAYER_SPEED    = 28.0    # logical units per second (slow, deliberate)
HANDBALL_RANGE  = 34.0    # max distance to a teammate for a handball
KICK_MAX_RANGE  = 88.0    # beyond this a kick can't be aimed
BALL_FLIGHT_SPEED = 95.0  # logical units per second while ball is airborne

# ── Slow-motion decision mode ───────────────────────────────────────
SLOWMO_FACTOR = 0.25      # time dilation while lining up a kick

# ── Defender AI ─────────────────────────────────────────────────────
DEFENDER_SPEED    = 9.0   # closing defenders converge at this speed
CHASE_RADIUS      = 38.0  # defenders further than this stay home
DEFENDER_MIN_DIST = 4.0   # they hold off at arm's length (no tackling yet)
MAX_CHASERS       = 2     # how many defenders pressure at once

# Off-ball shape (FULL GAME only — scenarios keep their original fully
# static non-chasers, so hand-tuned puzzle moments don't drift).
OFF_BALL_SPEED = 5.0   # well under DEFENDER_SPEED: repositioning, not chasing
OFF_BALL_DRIFT = 0.30  # 0..1 lean from formation "home" spot toward the ball

# ── Probability model ───────────────────────────────────────────────
PRESSURE_RADIUS      = 20.0  # opponent within this range applies pressure
HANDBALL_BASE_ACC    = 0.92  # short range, high base accuracy
KICK_BASE_ACC        = 0.68  # long range, lower base accuracy
PRESSURE_PENALTY_HB  = 0.35  # how much full pressure erodes a handball
PRESSURE_PENALTY_KICK = 0.50 # how much full pressure erodes a kick
KICK_DISTANCE_PENALTY = 0.35 # accuracy lost at maximum kick range
CONTEST_RADIUS       = 10.0  # RED player this close to a kick target contests
MARK_RADIUS          = 12.0  # teammate this close to target can take the mark

# ── Turnover / reset pacing ─────────────────────────────────────────
TURNOVER_RESET_DELAY = 1.5   # seconds RED "holds" the ball before reset
FLASH_DURATION       = 0.5   # seconds a score flash stays on screen
BOUNCE_TICK_DURATION = 0.4   # seconds the bounce tick mark is visible

# ── AFL Hero mode: camera (field-level diorama view) ────────────────
HERO_CAM_BACK   = 46.0   # camera ground distance behind the focus point
HERO_CAM_HEIGHT = 24.0   # camera height above the turf (field units)
HERO_CAM_FOCAL  = 520.0  # pinhole focal length in display pixels
HERO_CAM_ZOOM   = 1.35   # focal multiplier while a decision is being drawn
HERO_CAM_LERP   = 3.0    # focus/zoom smoothing rate (per second)
HERO_HORIZON_Y  = 0.40   # screen-height fraction where the look-at point sits
HERO_SPRITE_SCALE = 1.15 # world-size multiplier for billboarded sprites

# ── FULL GAME / SCENARIOS: camera (broadcast-style, distinct from Hero) ──
# Same rig as AFL Hero's, tuned slightly differently so the two modes read
# as different views: a touch higher/steeper (more vertical), slower to
# ease toward the play (reads as more fixed), and a little further back
# (mildly zoomed out) to keep more of the field in frame.
MAIN_CAM_BACK   = 50.0   # a bit further back than Hero's 46.0
MAIN_CAM_HEIGHT = 30.0   # higher than Hero's 24.0 -> steeper, more vertical look
MAIN_CAM_FOCAL  = 500.0  # slightly wider than Hero's 520.0 -> mild zoom out
MAIN_CAM_ZOOM   = 1.20   # gentler zoom-in while aiming a kick than Hero's 1.35
MAIN_CAM_LERP   = 1.8    # slower ease than Hero's 3.0 -> camera feels more fixed
MAIN_HORIZON_Y  = 0.40   # unchanged
# Own sprite-scale knob (mirrors HERO_SPRITE_SCALE) so FULL GAME / SCENARIOS
# can be tuned independently of Hero mode. Smaller than Hero's 1.15: with
# up to 36 bodies on the oval instead of a handful, shrinking each sprite
# a touch keeps the foreground readable instead of turning into a mush of
# overlapping guernseys.
MAIN_SPRITE_SCALE = 0.85

# ── AFL Hero mode: decision & swipe tuning ──────────────────────────
HERO_SLOWMO       = 0.12  # deep time dilation while deciding
HERO_GRAB_RADIUS  = 10.0  # a drag must begin this close to the carrier
HERO_PATH_MAX     = 60.0  # max drawn run-path length
HERO_RUN_SPEED    = 30.0  # carrier speed along a drawn run path
HERO_HANDBALL_MAX = 22.0  # a release closer than this is a handball
HERO_KICK_MAX     = 95.0  # drawn kicks cap at this distance
HERO_CURVE_MAX    = 14.0  # max lateral curve carried over from swipe bend
HERO_TACKLE_RADIUS = 2.5  # defender this close to a running carrier tackles

# ── AFL Hero mode: flight, marking, interception ────────────────────
HERO_FLIGHT_SPEED     = 85.0  # kick travel speed (slower = higher arcs)
HERO_MARK_RADIUS      = 10.0  # teammate this close to the drop takes the mark
HERO_INTERCEPT_RADIUS = 12.0  # defenders this close to the drop converge on it
HERO_INTERCEPT_GRAB   = 3.0   # reach needed to pick a dropping ball out of the air
HERO_INTERCEPT_WINDOW = 0.55  # flight progress after which the ball can be cut off
HERO_INTERCEPT_SPEED  = 14.0  # interceptor closing speed
HERO_PRESS_SPEED      = 12.0  # pressing defenders close at this speed
HERO_LEAD_SPEED       = 16.0  # leading forwards run at this speed
HERO_BOUNCE_SCATTER   = 7.0   # max deflection of an oval-ball ground bounce
HERO_LOOSE_RADIUS     = 12.0  # players this close join a loose-ball scramble
HERO_LOOSE_DELAY      = 0.7   # seconds the loose ball sits before the scramble

# ── GOAL KICKING mode: range & wind ──────────────────────────────────
# A freeform practice range, not a hand-placed level list: walk "the
# mark" anywhere in this arc, read the wind, then time a two-stage
# power/accuracy meter. Always kicks at GOAL_RIGHT, same as everywhere
# else YELLOW attacks.
GOALKICK_MIN_RANGE    = 15.0   # closest you can mark out from goal
GOALKICK_MAX_RANGE    = 65.0   # furthest practice kick allowed
GOALKICK_POWER_RANGE  = GOALKICK_MAX_RANGE * 1.15  # distance a full-power kick travels
GOALKICK_MAX_ANGLE    = 48.0   # degrees either side of dead-straight you can mark from
GOALKICK_MARK_MOVE_SPEED = 16.0  # units/sec walking the mark in/out
GOALKICK_MARK_TURN_SPEED = 30.0  # deg/sec walking the mark around the arc

GOALKICK_WIND_MAX          = 18.0  # strongest crosswind a practice kick will throw at you
GOALKICK_WIND_DEG_PER_UNIT = 0.75  # aim drift (degrees) per wind unit at max range

# ── GOAL KICKING mode: the timing meter ──────────────────────────────
GOALKICK_METER_PERIOD    = 1.05  # seconds for one full sweep of either bar
GOALKICK_POWER_TOLERANCE = 0.15  # +/- miss on the power bar before quality hits 0
GOALKICK_ACC_SPREAD      = 26.0  # degrees of aim swing across the accuracy bar

# ── GOAL KICKING mode: camera ────────────────────────────────────────
# Reuses HeroCamera's projection math untouched via a per-attempt
# coordinate swap (see mechanics.kick_axes / to_kick_space) instead of a
# new camera class — GOAL KICKING always looks straight down the kicking
# line at whichever goal you're aiming for, unlike the broadcast-style
# MAIN_CAM / HERO_CAM rigs, which never yaw and always show goals
# left/right. Closer and lower than the wide establishing shot below for
# a first-person read, but pulled back enough that the goal structure
# stays fully in frame through the power/accuracy meters and the kick's
# flight, rather than cropping in tight on the ground right in front of
# the kicker.
GOALKICK_CAM_BACK    = 26.0   # far enough back the whole goal structure reads
GOALKICK_CAM_HEIGHT  = 17.0   # above head height -> the posts don't clip out of frame
GOALKICK_CAM_FOCAL   = 470.0  # wider than the original 620 -> goals stay in view
GOALKICK_CAM_ZOOM    = 1.25   # zooms in further while a meter is running
GOALKICK_CAM_LERP    = 2.4    # eases about as briskly as Hero's camera
GOALKICK_HORIZON_Y   = 0.46   # a little lower in frame -> more sky, more "standing height"
GOALKICK_SPRITE_SCALE = 1.4   # bigger than Hero's 1.15 -> reads up close

# While you're still walking the mark around, pull the same rig back
# into a wide establishing shot instead — roughly half the ground in
# frame, so you can see the goal and where you're standing relative to
# it. GOALKICK_TRANSITION_TIME then swoops the rig from these values
# down to the tight GOALKICK_CAM_* ones above once the mark is confirmed
# (see goalkick_state.GoalKickState._update_transition) — a "GTA loading
# screen" style zoom-in, not a cut.
GOALKICK_WIDE_CAM_BACK   = 55.0
GOALKICK_WIDE_CAM_HEIGHT = 34.0
GOALKICK_WIDE_CAM_FOCAL  = 430.0
GOALKICK_TRANSITION_TIME = 0.9   # seconds for the wide -> tight swoop

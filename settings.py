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
# Margins trimmed slightly (from 20/14) to grow the oval a bit, compensating
# for FULL GAME's 16-a-side roster (see game_state.FORMATION_LINES) without
# touching LOGICAL_W/H/WINDOW_W/H or any camera rig. Scenarios/AFL HERO use
# literal hand-placed coordinates (levels.py/hero_levels.py), so the bigger
# oval reads as a modest cosmetic change there, not a functional one.
FIELD_MARGIN_X = 17
FIELD_MARGIN_Y = 12
FIELD_LEFT   = FIELD_MARGIN_X
FIELD_TOP    = FIELD_MARGIN_Y
FIELD_W      = LOGICAL_W - 2 * FIELD_MARGIN_X   # 166
FIELD_H      = LOGICAL_H - 2 * FIELD_MARGIN_Y   # 88
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
# FULL GAME only (see entities.Player.move's speed override and
# game_state._update_movement) — a further ~32% cut on top of PLAYER_SPEED,
# tuned for the bigger 16-a-side FULL GAME field. SCENARIOS keeps
# PLAYER_SPEED untouched since its levels.py time_limit values were balanced
# against it. The character menu's Speed stat (character_state.py) adjusts
# this same value live, within CHARACTER_SPEED_MIN/MAX below.
FULL_GAME_PLAYER_SPEED = 19.0
HANDBALL_RANGE  = 34.0    # max distance to a teammate for a handball
KICK_MAX_RANGE  = 88.0    # beyond this a kick can't be aimed
BALL_FLIGHT_SPEED = 95.0  # logical units per second while ball is airborne

# Cosmetic ground-bounce played out at the landing spot right after a
# flight arrives (see entities.Ball.start_bounce/advance_bounce) — visual
# only, height offset alone, never touches the ball's actual (x, y), so
# every outcome resolution keeps firing at the exact same moment it
# always has (see GameState._apply_pending_outcome). Just makes a kick
# read as an actual footy hitting the turf instead of stopping dead in
# mid-air the instant it "arrives".
BALL_BOUNCE_HOPS = 2            # diminishing hops before it settles flat
BALL_BOUNCE_MAX_HEIGHT = 3.0    # world units, first hop's peak height cap
BALL_BOUNCE_HOP_DURATION = 0.22 # seconds for one hop's up-and-down arc
BALL_BOUNCE_DECAY = 0.45        # each successive hop's height/duration multiplier
# Display pixels/second the kick-aim cursor moves under a controller's
# right stick (see game_state.GameState.update / controller.right_stick).
# Only used while a controller is actively pushing that stick — mouse
# aiming is untouched. Trimmed down from an initial 900 — full stick
# deflection felt too twitchy/hard to place precisely; retune to taste.
AIM_CURSOR_SPEED = 550.0

# Controller-only kick-aim assist: a gentle screen-space pull toward the
# nearest teammate once the cursor is close to them, so lining up a pass
# doesn't need pixel-perfect stick control the way a mouse gets for
# free. Deliberately soft — it's a per-frame blend toward the target,
# not a hard lock, so pushing the stick away from the pull always wins;
# see game_state.GameState._apply_aim_assist. Mouse aiming is precise
# enough on its own and never gets this.
AIM_ASSIST_RADIUS = 70.0     # screen px: cursor-to-teammate distance
                              # within which the pull starts
AIM_ASSIST_STRENGTH = 6.0    # pull rate; higher = snaps in faster

# ── Slow-motion decision mode ───────────────────────────────────────
SLOWMO_FACTOR = 0.25      # time dilation while lining up a kick

# ── Defender AI ─────────────────────────────────────────────────────
DEFENDER_SPEED    = 9.0   # closing defenders converge at this speed
CHASE_RADIUS      = 38.0  # defenders further than this stay home
DEFENDER_MIN_DIST = 7.0   # they hold off at arm's length (no tackling yet) —
                           # kept comfortably outside TACKLE_TRIGGER_RADIUS
                           # (see below) so a defender's normal resting
                           # distance doesn't itself sit inside tackle range;
                           # bumped from 4.0, which left only a 0.5-unit gap
                           # to TACKLE_TRIGGER_RADIUS (4.5) — practically no
                           # buffer, so a contest fired almost as soon as a
                           # defender arrived at all
MAX_CHASERS       = 2     # how many defenders pressure at once

# Off-ball shape (FULL GAME only — scenarios keep their original fully
# static non-chasers, so hand-tuned puzzle moments don't drift).
OFF_BALL_SPEED = 5.0   # well under DEFENDER_SPEED: repositioning, not chasing
OFF_BALL_DRIFT = 0.30  # 0..1 lean from formation "home" spot toward the ball

# Minimum gap kept between any two players' logical positions (see
# mechanics.separate_players, called once per frame from GameState.update)
# so one sprite can never fully hide another on screen. Deliberately well
# under TACKLE_TRIGGER_RADIUS (3.5) so it never gets in the way of a
# legitimate tackle contest actually triggering.
PLAYER_MIN_SEPARATION = 2.2

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
FLASH_DURATION       = 0.5   # seconds a score flash stays on screen
BOUNCE_TICK_DURATION = 0.4   # seconds the bounce tick mark is visible

# ── AI possession / tackle contest (see possession.py, ai_control.py,
#    contest_minigame.py) ────────────────────────────────────────────
# Placeholder-only tuning for this pass — no player attributes/tendencies
# feed into any of these yet (see each HOOK comment at the call site).
AI_HOLD_TIMEOUT = 3.0        # seconds an AI carrier runs before auto-kicking
                              # (only forces a kick if it hasn't already taken
                              # a shot on reaching scoring range — see
                              # ai_control.decide_next_action)
                              # HOOK: future tendency/attribute-driven timing

# The AI carrier used to run dead-straight at the goal center for the
# full AI_HOLD_TIMEOUT and then punt at goal regardless of range — from
# a typical kickoff spot that's still well outside SCORING_ARC_RADIUS,
# so it read as "always beelines to goal" and the kick was never
# actually a scoring attempt (mechanics.is_scoring_attempt requires
# being inside the arc first), just a low-percentage contested field
# kick aimed at the goal mouth. These fix that without building out a
# real decision tree (still explicitly future work — see
# ai_control.decide_next_action's HOOK comment):
AI_RUN_WOBBLE_DEGREES = 22.0   # the AI's run-at-goal heading gets a fresh
                                 # random offset within +/- this many degrees
                                 # every AI_WOBBLE_INTERVAL seconds, so a carry
                                 # reads as running the ball into space rather
                                 # than a razor-straight rail every time
AI_WOBBLE_INTERVAL = 0.8       # seconds between re-rolling that heading offset
AI_SHOT_AIM_SPREAD_DEGREES = 18.0  # once actually taking a shot on goal, the
                                     # AI aims within +/- this many degrees of
                                     # dead-straight instead of always dead
                                     # center — varies shot difficulty/outcome
                                     # instead of every shot being identical
TACKLE_TRIGGER_RADIUS = 3.5  # defender this close to the carrier starts a tackle contest —
                              # deliberately inside DEFENDER_MIN_DIST (7.0) now, so a defender
                              # holding at their normal arm's-length stop point does NOT sit
                              # inside tackle range by default; a tackle only fires when the
                              # carrier is actively moved toward the defender (or vice versa)
                              # past that arm's-length gap, not as a matter of course
                              # HOOK: future positioning/timing/attributes narrow or widen this
CONTEST_COOLDOWN = 1.2       # seconds after a contest resolves before another can trigger
                              # for the same pairing (see GameState._separate_after_contest —
                              # without this, a resolved tackle's still-adjacent participants
                              # would restart another contest on the very next eligible frame)

# ── Mark / stand-the-mark (see GameState.standing_mark, possession.py) ──
MARK_STAND_MIN_DISTANCE = 15.0  # a kick landing as a mark past this distance
                                  # triggers stand-the-mark; short marks don't
MARK_HOLD_DURATION = 5.0        # seconds the marker is tackle-immune and the
                                  # nearest defender is frozen at the mark

# Loose-ball/50-50 reaction minigame tuning — one place to balance, see
# contest_minigame.py. Miss policy is deliberately configurable rather
# than hardcoded (see contest_minigame._miss). Tackles no longer use this
# minigame (see TACKLE_* below / mechanics.resolve_tackle) — this block
# now only drives a loose ball landing in a pack (kind="loose_ball", see
# GameState._apply_pending_outcome's "contest" branch) and a ruck contest
# at a boundary ball-up (see possession.start_ruck_contest), both of
# which still resolve via this same reaction race.
CONTEST_PROMPT_COUNT = 3
CONTEST_AI_REACTION_RANGE = (0.35, 0.55)  # seconds per prompt, placeholder
                                            # HOOK: future attribute-driven AI reaction speed
CONTEST_INPUT_WINDOW = 1.4        # seconds allowed per prompt before it times out
CONTEST_MISS_POLICY = "reset_combo"   # "reset_combo" | "time_penalty" | "instant_loss"
CONTEST_MISS_TIME_PENALTY = 0.4

# ── Tackle resolution: holding the ball / prior opportunity ──────────
# A tackle (possession.find_tackle_trigger) no longer opens the reaction
# minigame — it resolves instantly (see mechanics.resolve_tackle),
# because the outcome now depends on match-rule state (how long the
# carrier has held the ball) rather than a race either player can be
# equally good at regardless of the football situation.
#
# GameState.possession_held_timer counts seconds since the current
# carrier gained the ball (reset in _give_possession, incremented once
# per frame in update()). A tackle before PRIOR_OPPORTUNITY_GRACE has
# elapsed is "no prior opportunity" — the carrier hasn't had a real
# chance to dispose yet, so it's a neutral ball-up, no penalty either
# way. A tackle after that window is judged as holding the ball: an
# almost-random break-tackle roll (TACKLE_BREAK_CHANCE) decides whether
# the carrier shrugs the tackle off (keeps the ball) or is pinged for
# holding it (free kick to the tackler).
#
# HOOK: TACKLE_BREAK_CHANCE is a flat placeholder — a future
# strength/agility/tackling attribute system replaces the single
# probability with something derived per-player, the same way every
# other placeholder in this file (AI_HOLD_TIMEOUT, CONTEST_AI_REACTION_
# RANGE) already flags where attributes eventually plug in.
PRIOR_OPPORTUNITY_GRACE = 0.5   # seconds after gaining the ball a tackle is
                                  # always a neutral ball-up, never holding-the-ball
TACKLE_BREAK_CHANCE = 0.45      # odds the carrier breaks a past-grace tackle
                                  # and keeps the ball instead of holding it
POST_TACKLE_COOLDOWN = 1.0      # seconds after ANY tackle resolution (broken or
                                  # not) before that pairing can trigger another —
                                  # reuses the same separation idea as
                                  # CONTEST_COOLDOWN/_separate_after_contest so a
                                  # broken tackle doesn't instantly re-trigger

# ── Out of bounds ──────────────────────────────────────────────────────
# Two distinct AFL rulings, both detected on the ball rather than on any
# player (players are already clamped inside the oval — see Player.move —
# so only the ball, in flight or resting after a missed kick, can
# actually leave it):
#   "out on the full"  — a kicked ball crosses the boundary line in the
#                         air, before landing/being marked/contested.
#                         Free kick to whichever team didn't kick it,
#                         taken from where it crossed the line.
#   "ball-up" (ruck)    — the ball comes down outside the oval (a grounded
#                         miss that rolls/bounces out) rather than crossing
#                         it on the full. Neutral: a boundary throw-in,
#                         resolved as a loose_ball contest between the
#                         nearest player of each team at that spot.
OOB_BOUNDARY_INSET = 2.0   # matches the inset mechanics.clamp_to_oval/Player.move
                             # already use for "inside the oval" — kept as one
                             # named constant here so the OOB check reads the
                             # exact same boundary every other clamp already does

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
# up to 32 bodies on the oval instead of a handful, shrinking each sprite
# a touch keeps the foreground readable instead of turning into a mush of
# overlapping guernseys. Dropped further (from 0.85) alongside FULL GAME's
# 16-a-side retune (settings.FULL_GAME_PLAYER_SPEED, game_state.FORMATION_LINES)
# so the smaller, slower roster reads as a deliberate scale change, not
# just a lower body count.
MAIN_SPRITE_SCALE = 0.65

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

GOALKICK_FLIGHT_SPEED = 60.0  # slower than the default BALL_FLIGHT_SPEED (95) — a kick
                               # this deliberate deserves time in the air to watch

# ── GOAL KICKING mode: the timing meter ──────────────────────────────
# Aim is now two layers: you steer an intended line by hand (the bias,
# arrow keys, up to GOALKICK_AIM_BIAS_MAX either way — this is where you
# actually compensate the wind), then the accuracy meter adds a smaller
# timing-precision wobble on top of wherever you aimed. Mistime it and
# even a well-read wind gets shanked slightly off your intended line.
GOALKICK_METER_PERIOD    = 1.05  # seconds for one full sweep of either bar
GOALKICK_POWER_TOLERANCE = 0.15  # +/- miss on the power bar before quality hits 0
GOALKICK_ACC_SPREAD      = 9.0   # timing-precision wobble, degrees either way
GOALKICK_AIM_BIAS_MAX    = 26.0  # how far off dead-straight you can deliberately aim
GOALKICK_AIM_BIAS_SPEED  = 22.0  # deg/sec nudging the aim bias while it's live

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

# ── CHARACTER MENU: camera & attributes (character_state.py) ─────────
# A hotkey-triggered (K_c) customization screen, entirely separate from
# ROOT_OPTIONS — a single fixed HeroCamera framing, close on a standing
# player, following the same *_CAM_* naming as every other mode's rig.
# Closer and lower than GOAL KICKING's already-close first-person rig for
# a tight "portrait" read, since there's exactly one player on screen and
# nothing else needs to fit in frame.
CHARACTER_CAM_BACK   = 15.0
CHARACTER_CAM_HEIGHT = 9.0
CHARACTER_CAM_FOCAL  = 480.0
CHARACTER_CAM_LERP   = 2.0
CHARACTER_HORIZON_Y  = 0.50
# Own sprite-scale knob (mirrors HERO_SPRITE_SCALE / GOALKICK_SPRITE_SCALE).
# Bigger than either — a close single-player portrait can afford it.
CHARACTER_SPRITE_SCALE = 1.8

# Speed nudges settings.FULL_GAME_PLAYER_SPEED's live value directly (see
# game_state._update_movement); Height has no gameplay hook yet, so it
# just scales the preview sprite (character_render.py) until a future pass
# gives it one, per the character menu's feature note in game_state.py.
CHARACTER_SPEED_MIN   = 12.0
CHARACTER_SPEED_MAX   = 26.0
CHARACTER_SPEED_STEP  = 1.0
# Height is stored and displayed in real centimeters. CHARACTER_HEIGHT_BASELINE_CM
# is the height that maps to a 1.0 preview-sprite scale multiplier (see
# character_render._render_scene); everything above/below it scales the
# sprite proportionally.
CHARACTER_HEIGHT_MIN  = 165.0
CHARACTER_HEIGHT_MAX  = 205.0
CHARACTER_HEIGHT_STEP = 1.0
CHARACTER_HEIGHT_BASELINE_CM = 185.0

# Pixel-wipe transition in/out of the menu (character_render.py) — short
# and hard-edged, consistent with this game's chunky low-res look.
CHARACTER_TRANSITION_TIME = 0.3   # seconds

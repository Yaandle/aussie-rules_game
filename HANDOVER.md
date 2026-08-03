# AGENT HANDOVER — AFL Prototype

You are taking over development of a working Python/Pygame game. Read this
fully before writing code. The owner values correctness, readability, and a
calm minimalist aesthetic over speed of output. Do not restructure the
project or restyle the visuals without being asked.

---

## 1. What this is

A top-down 2D pixel-art Australian Rules Football game with an introspective,
quiet indie feel ("Score! Hero meets AFL tactical decision-making" is the
long-term direction). Currently playable: a free-play quarter (FULL GAME) and
four scenario missions with objectives, win/fail/retry, and progression.

**Run:** `pip install pygame-ce` then `python main.py` (plain `pygame` fails
to build on newer Python; pygame-ce is the drop-in replacement). There are no
external assets — every visual is drawn procedurally with Pygame primitives.
The user runs it from a venv at `aussie-rule_venv/`.

---

## 2. Architecture (strict separation — preserve it)

| File | Responsibility | Rule |
|---|---|---|
| `main.py` | Entry point: init, event/update/render loop | Orchestrates only, implements nothing |
| `settings.py` | Every constant: palette, geometry, tuning | No logic |
| `entities.py` | `Player`, `Ball` — dumb data + self-contained movement | No game rules |
| `mechanics.py` | Pure resolution logic: pressure, kicks, contests, scoring, defender AI | **No Pygame drawing/input; testable in isolation** |
| `game_state.py` | `GameState`: phase machine, input handling, all mutable state | Never draws |
| `render.py` | All drawing | Never mutates game state |
| `levels.py` | Scenario mission definitions (data only) | No logic |

`mechanics.py` computes outcomes **at the moment of action**; the result is
stored as a `_pending_outcome` dict on GameState and applied when the ball's
flight animation lands. Keep this pattern.

### Phase machine (`game_state.py`)
- `PHASE_MENU` — root menu or scenario select (`menu_screen`, `menu_index`)
- `PHASE_PLAYING` — a match/scenario; sub-modes `MODE_IDLE` / `MODE_AIMING_KICK`
- `PHASE_END` — result overlay; `result` is `"win" | "fail" | "fulltime"`

`game_over` and `in_slowmo` are derived properties. `unlocked` (int) gates
scenario progression, in-memory only.

---

## 3. Visual style (the owner cares deeply about this)

Reference: `Screenshot 2026-08-03 183049.png` in the project root — a pastel
sage AFL oval, hazy diffuse light, chibi character, physical scoreboards.
Match it; when in doubt, choose restraint over decoration.

**Principles**
- Light pastel sage greens, low contrast, desaturated. Muted gold (`YELLOW`)
  vs muted brick (`RED`) teams. All colors live in `settings.py` — never
  hardcode hex in render code.
- Chunky pixel art: structural pixels are drawn on a small **logical surface
  (200×112)** then scaled ×6 with **nearest-neighbor** (`pygame.transform.scale`)
  to the 1200×672 window. Crisp edges, no anti-aliasing on structure.
- "Soft neomorphic" ambience is display-resolution only: glows, haze, bloom,
  vignette are smoothscaled low-res surfaces layered over the pixel grid.
  Softness must never blur the pixels themselves.
- Faux depth tricks in use: oval extrusion (dark offset ellipse), vertical
  light gradient inside the oval, side-shaded sprites lit from upper-left,
  shadows that stay grounded while bodies bob, ball lifting off its shadow
  in flight. Long shadows cast right/lower-right.
- Mood: introspective, spacious, slow. Generous negative space; oval fills
  ~70% of frame. UI is charcoal boxes + cream monospace text (Consolas).

**Scene inventory** (static, built once and cached in `render._background()`):
mown-stripe oval with boundary/centre circles/centre square/50m arcs/"50"
pixel digits/goal squares; four posts per end (white, red base band, sun-caught
cap); dark rail fences top & bottom; puffy 3-lobe trees; benches; hazy
paddock strips beyond the fences. Scoreboards are *physical structures* on
legs with roof caps: left = HOME/AWAY + clock, right = FOCUS/DISCIPLINE/
GROWTH + red dot.

**Sprites**: 5×10 chibi — oversized dark mop of hair (~half the sprite), face
under fringe, striped team guernsey with bare arms, dark shorts/boots.
Two-frame walk cycle (carrier only), idle bob (desynced per player), hover
arrow above the carrier.

---

## 4. Gameplay systems (current)

**Controls**: WASD/arrows move · 1/Q handball · 2/K kick then click to aim ·
3/Space bounce · Esc cancel aim / controls overlay · M controls overlay ·
Backspace (from overlay) quit to menu · Menus: arrows + Enter.

- **Pressure** = inverse distance to nearest opponent (`PRESSURE_RADIUS`).
  Lowers handball/kick accuracy (`resolve_handball`, `kick_accuracy`).
- **Kick**: enters slow-mo decision mode (`SLOWMO_FACTOR 0.25` scales dt for
  the whole sim while aiming; render adds cool tint + letterbox + rings under
  reachable teammates). Click resolves: contest if a defender is within
  `CONTEST_RADIUS` of target (proximity-weighted roll), else accuracy roll →
  mark to nearest teammate in `MARK_RADIUS` / retain / turnover to nearest red.
- **Scoring**: kicks from inside `SCORING_ARC_RADIUS` of the right goal within
  `SCORING_MAX_ANGLE` become shots → goal (6) / behind (1) / miss, weighted by
  distance + angle. YELLOW always attacks **right**.
- **Bounce rule**: carrier must bounce every `BOUNCE_INTERVAL` (15) run units;
  1.5× over = turnover. "BOUNCE!" warning shows when due.
- **Turnovers**: possession to nearest red, then after `TURNOVER_RESET_DELAY`
  play restarts with nearest yellow (stand-in until RED can attack).
- **Defender AI**: `mechanics.update_defenders` — the nearest `MAX_CHASERS`
  within `CHASE_RADIUS` converge at `DEFENDER_SPEED`, stopping at
  `DEFENDER_MIN_DIST`. No tackling yet.
- **Scenarios** (`levels.py`): each has name, tagline, objective
  (`"goal"`/`"score"`), `time_limit`, `fail_on_turnover`, and yellow/red
  position lists (index 0 = carrier). Win → `PHASE_END` + unlock next.
  Timeout → fail. Grand Final Moment fails on any turnover.

Coordinate facts: field center (100, 56); oval usable radii ~68×36 around it;
goals at (30, 56) and (170, 56). Keep all scenario positions inside the oval
(entities clamp movement to it).

---

## 5. Marked extension points (search `# EXTEND:`)

- Tackling when pressure is high (`mechanics.py`)
- Ruck contest at start of play / after a goal
- Man-on-man, zone, and interceptor defender behaviours
- Multi-quarter match structure; two controllable teams (`game_state.py`)
- Mission star ratings; persistent progression to disk (`levels.py`)

## 6. Roadmap (owner's stated direction — AFL Hero spec)

Priority order discussed: interceptor defenders that read kicks mid-flight →
swipe/drag path drawing for the carrier (Score! Hero style) → richer ball
physics (bounce/roll/curve) → full match mode (4 quarters, two teams, full
team sizes) → more scenario missions & campaign progression. Keep everything
minimal and aesthetic; gameplay clarity beats spectacle.

## 7. Working conventions

- Comment every class and non-trivial method with a one-line purpose.
- New tuning values go in `settings.py`; new pure logic in `mechanics.py`.
- The static scene cache (`render._bg_scaled`) must be invalidated if you
  change field geometry at runtime.
- Guard `set_at` near surface edges (helpers exist; out-of-bounds raises).
- The owner tests by running the game and sharing screenshots — after visual
  changes, ask for one and iterate. The dev sandbox here has no display and
  pygame may be missing; verify by careful review if you cannot execute.

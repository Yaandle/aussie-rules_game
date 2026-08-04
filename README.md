# AFL Prototype

A small, hand-rolled Aussie Rules football game built in Python and Pygame. No engine, no asset pipeline — every player, tree, and blade of grass is procedural pixel art drawn in code.

## Setup

Requires Python 3 and Pygame (pygame-ce also works).

```
pip install pygame
python main.py
```

## Modes

- **FULL GAME** — an 18-a-side match, one quarter, on the full oval. You control the ball carrier; the rest of both sides hold rough formation shape and lean into the contest around the ball.
- **SCENARIOS** — four designed possession moments, each with its own objective and clock: Centre Clearance, Hit the Lead, Break the Wing, Grand Final Moment.
- **AFL HERO** — a swipe-based possession puzzle mode across five levels: Break the Press, Down the Wing, Hit the Lead, Inside Fifty, After the Siren.

## Controls

**Full Game / Scenarios**

| Key | Action |
| --- | --- |
| WASD / Arrows | Move the ball carrier |
| 1 / Q | Handball to the nearest teammate in range |
| 2 / K | Aim a kick, click to release |
| 3 / Space | Bounce the ball (required every 15m of running) |
| M / Esc | Open the controls menu |
| Backspace (in menu) | Quit to main menu |

**AFL Hero**

| Input | Action |
| --- | --- |
| Left-drag | Kick (long) or handball (short) — bend the swipe to curl a kick |
| Right-drag | Draw a run path |
| Esc | Cancel a drag |
| R | Retry the level |

## How it plays

Outcomes resolve probabilistically rather than by direct collision: pressure from nearby opponents erodes handball and kick accuracy, contested marks are won by a proximity-weighted roll, and shots on goal split into goals, behinds, or misses based on distance and angle off the posts. All of it lives in `mechanics.py` as small, pure, testable functions.

## Project layout

- `settings.py` — every tunable constant: colors, field geometry, speeds, camera rig
- `entities.py` — `Player` and `Ball`, plain data holders
- `mechanics.py` — pure probability/resolution logic: pressure, kicks, marks, contests, AI
- `game_state.py` — `GameState`: FULL GAME / SCENARIOS state, phase machine, input, update loop
- `hero_state.py` — `HeroState`: the AFL Hero swipe-puzzle mode
- `render.py` — shared drawing: the player sprite, field background, menus, HUD chrome
- `field_render.py` — diorama renderer for FULL GAME / SCENARIOS
- `hero_render.py` — diorama renderer for AFL Hero
- `hero_camera.py` — the shared pinhole projection camera
- `levels.py` / `hero_levels.py` — scenario and Hero level data
- `main.py` — entry point

## Look & feel

A pastel-sage oval under hazy diffuse light: chibi pixel players with oversized mops of hair, physical scoreboards standing on legs, dark rail fences, puffy trees, and a low broadcast-style camera looking in across the ground. Everything is built from small logical surfaces upscaled with nearest-neighbor scaling — no external image assets, ever.

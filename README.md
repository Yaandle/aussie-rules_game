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
- **GOAL KICKING** — a freeform practice range shot from a tight, first-person-ish camera. Walk the mark anywhere in a wide arc out from goal, read the wind, then time a two-stage power/accuracy meter to send the ball at the big sticks.

## Controls

**Full Game / Scenarios**

| Key | Action |
| --- | --- |
| WASD / Arrows | Move the ball carrier |
| 1 / Q | Handball to the nearest teammate in range |
| 2 / K | Aim a kick, click to release |
| 3 / Space | Bounce the ball (required every 15m of running) |
| Tab | Switch controlled player (while defending) |
| M / Esc | Open the controls menu |
| Backspace (in menu) | Quit to main menu |

**AFL Hero**

| Input | Action |
| --- | --- |
| Left-drag | Kick (long) or handball (short) — bend the swipe to curl a kick |
| Right-drag | Draw a run path |
| Esc | Cancel a drag |
| R | Retry the level |

**Goal Kicking**

| Key | Action |
| --- | --- |
| Arrows / WASD | Walk the mark around (while choosing your spot) |
| Space / Enter | Confirm the mark, then lock the power meter, then the accuracy meter |
| Esc | Cancel the current attempt (keeps your mark) / menu |
| M | Open the controls menu |

## How it plays

Outcomes resolve probabilistically rather than by direct collision: pressure from nearby opponents erodes handball and kick accuracy, contested marks are won by a proximity-weighted roll, and shots on goal split into goals, behinds, or misses based on distance and angle off the posts. All of it lives in `mechanics.py` as small, pure, testable functions.

A handful of match rules sit on top of that resolution layer:

- **Mark / stand the mark** — a clean mark taken from beyond 15m freezes the nearest defender in place and shields the marker from a tackle for 5 seconds.
- **Holding the ball** — get tackled and the ball is judged on how long you've held it: within the first half-second it's a neutral ball-up (nobody's fault yet), past that it's an almost-random chance to break the tackle and keep it or be pinged for holding the ball (free kick to the tackler).
- **Out of bounds** — a kick that crosses the boundary in the air without landing first is out on the full (free kick to the other side); a kick that comes down and rolls or bounces out is a neutral ball-up instead.
- **Loose ball** — an inaccurate kick, an accurate kick nobody was there to mark, or a spilled handball hits the turf for real: it bounces and rolls a short distance before settling, and just sits there — the nearest couple of players from each side run at it, and whoever actually reaches it gathers it (a simultaneous arrival is a genuine 50/50). Nothing is handed to "the nearest player" on the spot anymore.

## Project layout

- `settings.py` — every tunable constant: colors, field geometry, speeds, camera rig
- `entities.py` — `Player` and `Ball`, plain data holders
- `mechanics.py` — pure probability/resolution logic: pressure, kicks, marks, contests, AI
- `game_state.py` — `GameState`: FULL GAME / SCENARIOS state, phase machine, input, update loop
- `hero_state.py` — `HeroState`: the AFL Hero swipe-puzzle mode
- `goalkick_state.py` — `GoalKickState`: the GOAL KICKING practice range
- `render.py` — shared drawing: the player sprite, field background, menus, HUD chrome
- `field_render.py` — diorama renderer for FULL GAME / SCENARIOS
- `hero_render.py` — diorama renderer for AFL Hero
- `goalkick_render.py` — first-person-ish renderer for GOAL KICKING
- `hero_camera.py` — the shared pinhole projection camera
- `levels.py` / `hero_levels.py` — scenario and Hero level data
- `main.py` — entry point

## Look & feel

A pastel-sage oval under hazy diffuse light: chibi pixel players with oversized mops of hair, physical scoreboards standing on legs, dark rail fences, puffy trees, and a low broadcast-style camera looking in across the ground. Everything is built from small logical surfaces upscaled with nearest-neighbor scaling — no external image assets, ever.

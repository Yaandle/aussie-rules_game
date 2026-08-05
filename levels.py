"""levels.py — scenario missions (the AFL Hero layer).

Each scenario recreates a specific match situation — a quarter, a score
context, a clock, one objective — rather than an abstract puzzle. That's
the difference from AFL HERO's levels (hero_levels.py): those are
swipe-mechanic puzzles with their own controls; these play with FULL
GAME's exact controls/mechanics, just dropped into a designed moment
with the drama of a real broadcast (see `quarter`/`situation`/
`*_score_start` below, read by game_state.py and field_render.py).

Objectives:
  "score"    — a goal or a behind completes it.
  "goal"     — only a goal completes it.
  "comeback" — score enough (any mix of goals/behinds) during the
               scenario to reach or pass `away_score_start` before the
               clock runs out (see GameState._apply_score). There's no
               real opposing-scoring mechanic in this engine, so a
               comeback is modelled as "outscore the deficit yourself."

Coordinates are logical grid units; YELLOW always attacks the right
goal. Each scenario hand-places a few "featured" positions — the actual
puzzle — first in its yellow/red list, then `_padded()` fills the rest
of a proper 16-a-side roster around them with a generic AFL-shaped
formation, purely for a realistic on-field look; only the featured
players (and, for RED, whichever couple end up closest to the carrier —
see mechanics.update_defenders' MAX_CHASERS) ever do anything.

`_padded`'s formation math intentionally duplicates
game_state.FORMATION_LINES's shape rather than importing it — game_state
already imports this module, so importing back would cycle. It's a pure
data-generation helper, not gameplay logic, so the duplication is cheap.
"""

import math

import settings


def _formation_slots(attack_positive):
    """A generic 16-a-side AFL-shaped base layout (six lines, same shape
    as game_state.FORMATION_LINES) — only used to pad a scenario's few
    hand-placed "featured" positions out to a full roster."""
    lines = (
        (0.06, ((-0.62, 0.02), (0.0, 0.0), (0.62, 0.02))),
        (0.28, ((-0.68, 0.02), (0.0, 0.0), (0.68, 0.02))),
        (0.50, ((-0.85, 0.0), (0.85, 0.0))),
        (0.50, ((0.06, -0.02), (-0.20, -0.035))),
        (0.72, ((-0.68, -0.02), (0.0, 0.0), (0.68, -0.02))),
        (0.94, ((-0.62, -0.02), (0.0, 0.0), (0.62, -0.02))),
    )
    positions = []
    for depth, slots in lines:
        for lateral_frac, nudge in slots:
            d = depth + nudge
            x_frac = d if attack_positive else 1.0 - d
            x = settings.FIELD_LEFT + x_frac * settings.FIELD_W
            t = max(-0.999, min(0.999, (x - settings.FIELD_CX) / (settings.FIELD_W / 2)))
            half_width = (settings.FIELD_H / 2) * math.sqrt(1.0 - t * t)
            y = settings.FIELD_CY + lateral_frac * half_width * 0.82
            positions.append((x, y))
    return positions


def _padded(featured, attack_positive, count=16):
    """The hand-placed `featured` spots (kept first, and kept exactly as
    designed) plus enough generic formation slots to reach `count`."""
    combined = list(featured)
    for pos in _formation_slots(attack_positive):
        if len(combined) >= count:
            break
        combined.append(pos)
    return combined[:count]


SCENARIOS = [
    {
        "name": "CENTRE CLEARANCE",
        "tagline": "WIN THE STOPPAGE - SCORE ANY WAY",
        "situation": "FIRST BOUNCE OF THE DAY - GET IT MOVING YOUR WAY",
        "quarter": "Q1",
        "objective": "score",
        "home_score_start": 0,
        "away_score_start": 0,
        "time_limit": 45.0,
        "fail_on_turnover": False,
        "yellow": _padded([(100, 56), (116, 43), (121, 67), (146, 52)],
                          attack_positive=True),
        "red": _padded([(93, 49), (107, 63), (111, 45), (125, 58), (153, 60)],
                       attack_positive=False),
    },
    {
        "name": "HIT THE LEAD",
        "tagline": "FIND THE FORWARD - GOAL ONLY",
        "situation": "SIX POINTS DOWN AT THE HALF - HIT THE LEAD, CLOSE IT",
        "quarter": "Q2",
        "objective": "goal",
        "home_score_start": 18,
        "away_score_start": 24,
        "time_limit": 30.0,
        "fail_on_turnover": False,
        "yellow": _padded([(121, 41), (153, 60), (132, 74)], attack_positive=True),
        "red": _padded([(130, 47), (157, 65), (146, 38), (164, 54)],
                       attack_positive=False),
    },
    {
        "name": "BREAK THE WING",
        "tagline": "HALF-BACK TO A GOAL, LINK BY LINK",
        "situation": "THIRD QUARTER - LINK IT UP FROM DEFENSE, MAKE IT COUNT",
        "quarter": "Q3",
        "objective": "goal",
        "home_score_start": 35,
        "away_score_start": 41,
        "time_limit": 60.0,
        "fail_on_turnover": False,
        "yellow": _padded([(52, 41), (82, 32), (95, 65), (127, 47), (153, 58)],
                          attack_positive=True),
        "red": _padded([(66, 47), (91, 43), (109, 56), (132, 60), (148, 43), (159, 63)],
                       attack_positive=False),
    },
    {
        "name": "GRAND FINAL MOMENT",
        "tagline": "ONE POSSESSION. NO TURNOVERS. GOAL WINS.",
        "situation": "FINAL QUARTER, ONE POINT DOWN - ONE CHANCE, MAKE IT A GOAL",
        "quarter": "Q4",
        "objective": "goal",
        "home_score_start": 61,
        "away_score_start": 62,
        "time_limit": 15.0,
        "fail_on_turnover": True,
        "yellow": _padded([(148, 49), (159, 65)], attack_positive=True),
        "red": _padded([(143, 56), (155, 43), (166, 58)], attack_positive=False),
    },
    {
        "name": "THE COMEBACK",
        "tagline": "13 POINTS DOWN - CLAW IT BACK BEFORE THE SIREN",
        "situation": "FOUR MINUTES LEFT, DOWN BY 13 - KEEP IT ALIVE, CHASE EVERY POINT",
        "quarter": "Q4",
        "objective": "comeback",
        "home_score_start": 42,
        "away_score_start": 55,
        "time_limit": 240.0,
        "fail_on_turnover": False,
        "yellow": _padded([(150, 48), (135, 61), (159, 57), (142, 40)],
                          attack_positive=True),
        "red": _padded([(147, 55), (139, 46), (156, 62), (163, 49), (131, 58)],
                       attack_positive=False),
    },
]

# EXTEND: mission rewards / star ratings based on time remaining
# EXTEND: persistent progression saved to disk between sessions

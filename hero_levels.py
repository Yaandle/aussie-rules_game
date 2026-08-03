"""hero_levels.py — AFL Hero mode levels (data only, no logic).

Each level is one possession treated as a puzzle: fixed starting
positions, an objective, a clock, and a defensive setup to unpick.
Losing the ball in Hero mode always fails the level — retry is cheap.

Coordinates are logical field units (YELLOW attacks the right goal,
index 0 of "yellow" starts as the carrier).

Objectives:
  "territory" — a YELLOW player must hold the ball past x = territory_x.
  "mark_lead" — a teammate (not the carrier) must mark a kick.
  "score"     — a goal or a behind completes the level.
  "goal"      — only a goal completes it.

Optional "leads": {teammate_index: (x, y)} — those teammates run to the
given spot whenever play is live, dragging their defenders with them.
"""

HERO_LEVELS = [
    {
        "name": "BREAK THE PRESS",
        "tagline": "SWIPE OUT OF THE TRAP - CROSS THE CENTRE",
        "objective": "territory",
        "territory_x": 100,
        "time_limit": 35.0,
        "yellow": [(46, 56), (62, 40), (66, 70), (92, 52)],
        "red":    [(52, 50), (54, 63), (72, 55), (86, 42), (98, 62)],
    },
    {
        "name": "DOWN THE WING",
        "tagline": "CHAIN POSSESSIONS ALONG THE BOUNDARY",
        "objective": "territory",
        "territory_x": 152,
        "time_limit": 45.0,
        "yellow": [(58, 36), (92, 30), (122, 34), (148, 46)],
        "red":    [(74, 40), (104, 36), (132, 42), (150, 58), (118, 56)],
        "leads": {3: (160, 52)},
    },
    {
        "name": "HIT THE LEAD",
        "tagline": "THE FORWARD BREAKS - FIND HIS CHEST",
        "objective": "mark_lead",
        "time_limit": 25.0,
        "yellow": [(108, 52), (134, 64), (128, 38)],
        "red":    [(114, 46), (140, 58), (134, 44), (150, 52)],
        "leads": {1: (156, 60), 2: (148, 34)},
    },
    {
        "name": "INSIDE FIFTY",
        "tagline": "CREATE THE CHANCE - ANY SCORE COUNTS",
        "objective": "score",
        "time_limit": 30.0,
        "yellow": [(126, 44), (146, 62), (156, 46)],
        "red":    [(132, 50), (150, 54), (152, 40), (164, 58), (142, 68)],
    },
    {
        "name": "AFTER THE SIREN",
        "tagline": "ONE POSSESSION LEFT. GOAL OR NOTHING.",
        "objective": "goal",
        "time_limit": 18.0,
        "yellow": [(144, 50), (158, 64)],
        "red":    [(148, 56), (156, 44), (166, 58)],
    },
]

# EXTEND: star ratings from time remaining / possessions used
# EXTEND: persistent hero progression saved to disk

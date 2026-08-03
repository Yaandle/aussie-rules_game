"""levels.py — scenario missions (the AFL Hero layer).

Each scenario is a designed football moment: fixed starting positions,
one objective, a clock, and a fail condition. Coordinates are logical
grid units; YELLOW always attacks the right goal.

Objectives:
  "goal"  — only a goal completes the mission.
  "score" — a goal or a behind completes it.
"""

SCENARIOS = [
    {
        "name": "CENTRE CLEARANCE",
        "tagline": "WIN THE STOPPAGE - SCORE ANY WAY",
        "objective": "score",
        "time_limit": 45.0,
        "fail_on_turnover": False,
        "yellow": [(100, 56), (116, 43), (121, 67), (146, 52)],
        "red":    [(93, 49), (107, 63), (111, 45), (125, 58), (153, 60)],
    },
    {
        "name": "HIT THE LEAD",
        "tagline": "FIND THE FORWARD - GOAL ONLY",
        "objective": "goal",
        "time_limit": 30.0,
        "fail_on_turnover": False,
        "yellow": [(121, 41), (153, 60), (132, 74)],
        "red":    [(130, 47), (157, 65), (146, 38), (164, 54)],
    },
    {
        "name": "BREAK THE WING",
        "tagline": "HALF-BACK TO A GOAL, LINK BY LINK",
        "objective": "goal",
        "time_limit": 60.0,
        "fail_on_turnover": False,
        "yellow": [(52, 41), (82, 32), (95, 65), (127, 47), (153, 58)],
        "red":    [(66, 47), (91, 43), (109, 56), (132, 60), (148, 43), (159, 63)],
    },
    {
        "name": "GRAND FINAL MOMENT",
        "tagline": "ONE POSSESSION. NO TURNOVERS. GOAL WINS.",
        "objective": "goal",
        "time_limit": 15.0,
        "fail_on_turnover": True,
        "yellow": [(148, 49), (159, 65)],
        "red":    [(143, 56), (155, 43), (166, 58)],
    },
]

# EXTEND: mission rewards / star ratings based on time remaining
# EXTEND: persistent progression saved to disk between sessions

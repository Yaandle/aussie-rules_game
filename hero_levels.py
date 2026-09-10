"""hero_levels.py — Aussie Rules Hero mode levels and leagues (data only).

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

Levels are grouped into HERO_LEAGUES — a pathway of escalating
difficulty (tighter clocks, more/closer defenders), each a small,
single-screen list of hand-placed levels rather than a generated set.
The rest of this file derives a few flat lookups from that grouping
(HERO_LEVELS / LEVEL_LEAGUE_INDEX / LEAGUE_LEVEL_RANGE) so every
existing per-flat-index consumer (hero_state.py, hero_render.py,
menu.py) keeps working unchanged — leagues are purely a menu/
presentation grouping over the same flat level list and the same
GameState.hero_unlocked progression counter that always existed.
"""

HERO_LEAGUES = [
    {
        "name": "JUNIORS",
        "tagline": "WHERE IT ALL STARTS",
        "levels": [
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
        ],
    },
    {
        "name": "REPRESENTATIVE",
        "tagline": "PUT YOUR HAND UP",
        "levels": [
            {
                "name": "TALENT DAY",
                "tagline": "EVERYONE'S WATCHING - GET IT MOVING",
                "objective": "territory",
                "territory_x": 96,
                "time_limit": 30.0,
                "yellow": [(38, 58), (56, 44), (60, 72), (84, 54)],
                "red":    [(44, 52), (46, 66), (66, 58), (78, 44), (90, 64), (96, 50)],
            },
            {
                "name": "OVERLAP RUN",
                "tagline": "USE THE EXTRA MAN OUT WIDE",
                "objective": "territory",
                "territory_x": 150,
                "time_limit": 40.0,
                "yellow": [(50, 32), (84, 26), (112, 30), (140, 42), (120, 50)],
                "red":    [(66, 36), (96, 32), (126, 38), (146, 54), (112, 52), (134, 60)],
                "leads": {3: (158, 48)},
            },
            {
                "name": "SECOND EFFORT",
                "tagline": "THE LEAD COMES BACK THE OTHER WAY",
                "objective": "mark_lead",
                "time_limit": 22.0,
                "yellow": [(104, 50), (130, 62), (124, 36)],
                "red":    [(110, 44), (136, 56), (130, 42), (146, 50), (118, 58)],
                "leads": {1: (154, 58), 2: (146, 32)},
            },
            {
                "name": "CREATE SOMETHING",
                "tagline": "NOTHING ON - MAKE YOUR OWN CHANCE",
                "objective": "score",
                "time_limit": 27.0,
                "yellow": [(120, 42), (142, 60), (152, 44), (134, 66)],
                "red":    [(126, 48), (148, 52), (150, 38), (162, 56), (140, 66), (158, 66)],
            },
            {
                "name": "SEAL THE WIN",
                "tagline": "LAST MINUTE - SLAM THE DOOR SHUT",
                "objective": "goal",
                "time_limit": 16.0,
                "yellow": [(140, 48), (154, 62), (148, 36)],
                "red":    [(146, 54), (154, 42), (164, 56), (150, 64)],
            },
        ],
    },
    {
        "name": "ACADEMY",
        "tagline": "THE PATHWAY GETS SERIOUS",
        "levels": [
            {
                "name": "FULL-TIME PROGRAM",
                "tagline": "DRILLED DEFENCE - FIND THE GAP ANYWAY",
                "objective": "territory",
                "territory_x": 94,
                "time_limit": 27.0,
                "yellow": [(36, 62), (52, 46), (58, 78), (80, 58)],
                "red":    [(42, 56), (44, 70), (62, 62), (72, 46), (86, 68), (92, 52), (54, 50)],
            },
            {
                "name": "RUN THE TAPE OUT",
                "tagline": "A WING THAT NEVER STOPS RUNNING",
                "objective": "territory",
                "territory_x": 148,
                "time_limit": 36.0,
                "yellow": [(46, 78), (80, 84), (110, 80), (136, 68), (118, 62)],
                "red":    [(62, 82), (92, 86), (122, 78), (144, 62), (110, 66), (132, 72), (100, 76)],
                "leads": {3: (156, 66)},
            },
            {
                "name": "PATHWAY PLAYER",
                "tagline": "SCOUTS AT THE FENCE - HIT THE MARK CLEAN",
                "objective": "mark_lead",
                "time_limit": 20.0,
                "yellow": [(100, 46), (126, 60), (118, 32)],
                "red":    [(106, 40), (132, 52), (126, 38), (142, 46), (114, 54), (98, 36)],
                "leads": {1: (150, 54), 2: (140, 28)},
            },
            {
                "name": "MAKE THEM PAY",
                "tagline": "ONE CRACK AT IT - DON'T WASTE IT",
                "objective": "score",
                "time_limit": 24.0,
                "yellow": [(116, 36), (138, 56), (150, 40), (128, 62)],
                "red":    [(122, 42), (144, 48), (146, 34), (158, 52), (136, 62), (154, 62), (130, 50)],
            },
            {
                "name": "SELECTION MEETING",
                "tagline": "PROVE IT ONE MORE TIME - GOAL, NOW",
                "objective": "goal",
                "time_limit": 15.0,
                "yellow": [(138, 44), (152, 58), (144, 32)],
                "red":    [(144, 50), (152, 38), (162, 52), (146, 60), (156, 62)],
            },
        ],
    },
    {
        "name": "SENIORS",
        "tagline": "MAN'S FOOTY NOW",
        "levels": [
            {
                "name": "FIRST SENIOR GAME",
                "tagline": "BIGGER, FASTER, NO SPACE ANYWHERE",
                "objective": "territory",
                "territory_x": 92,
                "time_limit": 24.0,
                "yellow": [(34, 40), (50, 26), (54, 56), (78, 36), (66, 62)],
                "red":    [(40, 34), (42, 48), (60, 40), (70, 26), (84, 50), (90, 32), (52, 30), (60, 50)],
            },
            {
                "name": "SPREAD THE FIELD",
                "tagline": "SEVEN DEEP AND STILL FINDING A LANE",
                "objective": "territory",
                "territory_x": 146,
                "time_limit": 32.0,
                "yellow": [(44, 24), (76, 20), (104, 24), (132, 34), (114, 44)],
                "red":    [(60, 28), (88, 24), (118, 30), (140, 46), (108, 40), (128, 52), (98, 36)],
                "leads": {3: (154, 40)},
            },
            {
                "name": "SPOILED TWICE",
                "tagline": "THE FIRST LEAD GETS SHUT DOWN - FIND THE NEXT",
                "objective": "mark_lead",
                "time_limit": 18.0,
                "yellow": [(96, 60), (122, 72), (114, 44), (100, 40)],
                "red":    [(102, 54), (128, 64), (122, 50), (138, 58), (110, 66), (92, 46), (118, 40)],
                "leads": {1: (146, 66), 2: (136, 38)},
            },
            {
                "name": "TRAFFIC EVERYWHERE",
                "tagline": "SIX BODIES IN THE GOAL SQUARE - GO",
                "objective": "score",
                "time_limit": 21.0,
                "yellow": [(114, 30), (136, 50), (148, 34), (126, 56), (140, 62)],
                "red":    [(120, 36), (142, 42), (144, 28), (156, 46), (130, 56), (152, 56), (124, 44), (146, 60)],
            },
            {
                "name": "SIT ON THE LEAD",
                "tagline": "PROTECT IT - ONE MORE GOAL SEALS IT",
                "objective": "goal",
                "time_limit": 13.0,
                "yellow": [(136, 40), (150, 54), (142, 26), (128, 48)],
                "red":    [(142, 46), (150, 34), (160, 48), (144, 56), (154, 58), (132, 54)],
            },
        ],
    },
    {
        "name": "STATE",
        "tagline": "PLAYING FOR THE JUMPER",
        "levels": [
            {
                "name": "INTERSTATE CLASH",
                "tagline": "THE WHOLE STATE IS WATCHING",
                "objective": "territory",
                "territory_x": 90,
                "time_limit": 21.0,
                "yellow": [(32, 66), (48, 80), (52, 50), (76, 70), (64, 44)],
                "red":    [(38, 60), (40, 74), (58, 64), (68, 78), (82, 62), (88, 46), (50, 56), (60, 46)],
            },
            {
                "name": "SUDDEN DEATH WING",
                "tagline": "MISS THIS AND IT'S OVER",
                "objective": "territory",
                "territory_x": 144,
                "time_limit": 28.0,
                "yellow": [(44, 84), (74, 96), (102, 90), (130, 78), (112, 68)],
                "red":    [(56, 88), (86, 96), (116, 88), (138, 72), (106, 76), (126, 82), (96, 86), (144, 60)],
                "leads": {3: (152, 74)},
            },
            {
                "name": "MARK OF THE YEAR CHANCE",
                "tagline": "ONE FRAME OF FILM - MAKE IT COUNT",
                "objective": "mark_lead",
                "time_limit": 16.0,
                "yellow": [(92, 34), (118, 46), (110, 20), (96, 62)],
                "red":    [(98, 28), (124, 40), (118, 24), (134, 32), (106, 52), (88, 22), (114, 56)],
                "leads": {1: (142, 40), 2: (132, 16)},
            },
            {
                "name": "PACKED FORWARD LINE",
                "tagline": "EIGHT IN DEFENCE - THREAD IT ANYWAY",
                "objective": "score",
                "time_limit": 19.0,
                "yellow": [(110, 24), (132, 44), (146, 28), (122, 50), (136, 58)],
                "red":    [(116, 30), (138, 36), (140, 22), (152, 40), (126, 50), (148, 50), (120, 38), (144, 54), (130, 62)],
            },
            {
                "name": "STATE OF ORIGIN MOMENT",
                "tagline": "THE SIREN'S ABOUT TO GO - GOAL WINS IT",
                "objective": "goal",
                "time_limit": 12.0,
                "yellow": [(132, 34), (148, 48), (140, 20), (124, 44)],
                "red":    [(138, 40), (146, 28), (158, 44), (140, 52), (150, 54), (128, 50)],
            },
        ],
    },
    {
        "name": "COUNTRY",
        "tagline": "THE HIGHEST HONOUR THERE IS",
        "levels": [
            {
                "name": "WEARING THE JUMPER",
                "tagline": "PLAYING FOR YOUR COUNTRY NOW - GET IT GOING",
                "objective": "territory",
                "territory_x": 88,
                "time_limit": 18.0,
                "yellow": [(30, 48), (44, 34), (48, 64), (72, 44), (60, 70)],
                "red":    [(36, 42), (38, 56), (54, 46), (64, 32), (78, 56), (84, 40), (46, 38), (56, 60)],
            },
            {
                "name": "NO ROOM, NO TIME",
                "tagline": "THE BEST DEFENCE IN THE WORLD - BEAT IT ANYWAY",
                "objective": "territory",
                "territory_x": 142,
                "time_limit": 24.0,
                "yellow": [(44, 26), (70, 22), (98, 18), (126, 28), (108, 38)],
                "red":    [(54, 22), (82, 18), (112, 24), (136, 40), (102, 34), (122, 46), (92, 30), (140, 54)],
                "leads": {3: (150, 34)},
            },
            {
                "name": "FRAME OF THE MATCH",
                "tagline": "THIS IS THE ONE THEY'LL REPLAY FOREVER",
                "objective": "mark_lead",
                "time_limit": 14.0,
                "yellow": [(88, 66), (114, 78), (106, 50), (92, 30)],
                "red":    [(94, 60), (120, 70), (114, 56), (130, 64), (102, 74), (84, 28), (110, 44), (98, 34)],
                "leads": {1: (138, 60), 2: (128, 24)},
            },
            {
                "name": "EVERY DEFENDER IN THE WORLD",
                "tagline": "THEY BROUGHT ALL ELEVEN BACK - SCORE ANYWAY",
                "objective": "score",
                "time_limit": 17.0,
                "yellow": [(104, 20), (126, 40), (140, 24), (118, 46), (132, 54)],
                "red":    [(110, 26), (132, 32), (134, 18), (146, 36), (120, 46), (142, 46), (114, 34), (138, 50), (124, 58), (150, 52)],
            },
            {
                "name": "THE LAST KICK OF THE SEASON",
                "tagline": "EVERYTHING COMES DOWN TO THIS ONE",
                "objective": "goal",
                "time_limit": 11.0,
                "yellow": [(128, 30), (144, 44), (136, 24), (120, 40)],
                "red":    [(134, 36), (142, 24), (154, 40), (136, 48), (146, 50), (122, 46), (150, 30)],
            },
        ],
    },
    # EXTEND: a 7th league beyond COUNTRY is teased but not built yet —
    # the pathway is meant to keep going (see menu.py/render.py's
    # "MORE LEAGUES COMING" row, shown once COUNTRY is fully cleared).
]


def _flatten_leagues(leagues):
    """One flat level list plus two small lookups derived from the
    league grouping above — every existing consumer that already
    indexes by a flat level_index (hero_state.HeroState, hero_render's
    has-next check, menu.py's level select/unlock flow) keeps reading
    HERO_LEVELS exactly as before; leagues are purely a menu grouping
    layered on top, not a change to how a level itself is stored or
    how GameState.hero_unlocked counts progression."""
    flat_levels = []
    level_league_index = []
    league_level_range = []
    for league_i, league in enumerate(leagues):
        start = len(flat_levels)
        flat_levels.extend(league["levels"])
        level_league_index.extend([league_i] * len(league["levels"]))
        league_level_range.append((start, len(flat_levels)))
    return flat_levels, level_league_index, league_level_range


HERO_LEVELS, LEVEL_LEAGUE_INDEX, LEAGUE_LEVEL_RANGE = _flatten_leagues(HERO_LEAGUES)

# EXTEND: star ratings from time remaining / possessions used
# EXTEND: persistent hero progression saved to disk

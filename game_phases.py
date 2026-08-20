"""game_phases.py — phase/mode/screen identifiers shared across the
GameState split (game_state.py, menu.py, gameplay.py, outcomes.py).

A dependency-free leaf module. game_state.py, menu.py, and gameplay.py
all need these constants, and game_state.py also needs to import
menu.py/gameplay.py themselves (to call their functions) — putting the
constants here instead of in game_state.py avoids the circular import
that would otherwise create. game_state.py re-imports and re-exports
every name below, so existing external imports (main.py's
`from game_state import PHASE_MENU`, field_render.py's
`from game_state import MODE_AIMING_KICK, PHASE_END`, render.py's
`from game_state import ROOT_OPTIONS, SCREEN_HERO, SCREEN_ROOT`) are
unaffected.
"""

import pygame

# App phases
PHASE_MENU = "menu"
PHASE_PLAYING = "playing"
PHASE_END = "end"
PHASE_HERO = "hero"
PHASE_GOALKICK = "goalkick"
# The character customization menu — hotkey-triggered (K_c), reachable from
# PHASE_MENU or PHASE_PLAYING and never listed in ROOT_OPTIONS/SCREEN_ROOT;
# see menu.open_character / menu.handle_character_input.
PHASE_CHARACTER = "character"

# Input modes (while playing)
MODE_IDLE = "idle"
MODE_AIMING_KICK = "aiming_kick"

# Menu screens and options
SCREEN_ROOT = "root"
SCREEN_SCENARIOS = "scenarios"
SCREEN_HERO = "hero_select"
ROOT_OPTIONS = ("FULL GAME", "SCENARIOS", "AFL HERO", "GOAL KICKING", "QUIT")

# Directional prompt keys read while a loose-ball/ruck contest is live (see
# gameplay.handle_contest_input) — arrow keys and numpad, per the contest's
# own spec; a connected gamepad's D-pad already arrives as synthetic
# K_UP/DOWN/LEFT/RIGHT KEYDOWN events (see controller.poll_events), so it
# needs no entry of its own here.
CONTEST_DIRECTION_KEYS = {
    pygame.K_UP: "UP", pygame.K_KP8: "UP",
    pygame.K_DOWN: "DOWN", pygame.K_KP2: "DOWN",
    pygame.K_LEFT: "LEFT", pygame.K_KP4: "LEFT",
    pygame.K_RIGHT: "RIGHT", pygame.K_KP6: "RIGHT",
}

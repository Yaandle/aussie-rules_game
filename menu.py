"""menu.py — root/scenario/hero menu navigation, the CHARACTER MENU
hotkey flow, and the three submode update bridges (Hero/Goal Kicking/
Character) that route a finished submode's exit_request back to a menu
screen.

Split out of game_state.py (see AUDIT.md's game_state.py decomposition)
— follows the same convention as mechanics.py/possession.py/
ai_control.py: every function takes the owning `game_state` object as
its first argument rather than being a GameState method.
"""

import pygame

import hero_levels
import levels
from character_state import CharacterState
from game_phases import (PHASE_CHARACTER, PHASE_MENU, ROOT_OPTIONS,
                          SCREEN_HERO, SCREEN_ROOT, SCREEN_SCENARIOS)

# ── Menu input ──────────────────────────────────────────────────────

def menu_options(game_state):
    """The entries on the current menu screen."""
    if game_state.menu_screen == SCREEN_ROOT:
        return list(ROOT_OPTIONS)
    if game_state.menu_screen == SCREEN_HERO:
        return [lv["name"] for lv in hero_levels.HERO_LEVELS] + ["BACK"]
    return [s["name"] for s in levels.SCENARIOS] + ["BACK"]


def handle_menu_input(game_state, event):
    if event.type != pygame.KEYDOWN:
        return
    options = menu_options(game_state)
    if event.key in (pygame.K_UP, pygame.K_w):
        game_state.menu_index = (game_state.menu_index - 1) % len(options)
    elif event.key in (pygame.K_DOWN, pygame.K_s):
        game_state.menu_index = (game_state.menu_index + 1) % len(options)
    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
        select_menu_option(game_state)
    elif event.key == pygame.K_ESCAPE and game_state.menu_screen != SCREEN_ROOT:
        back_index = 2 if game_state.menu_screen == SCREEN_HERO else 1
        game_state.menu_screen = SCREEN_ROOT
        game_state.menu_index = back_index


def select_menu_option(game_state):
    if game_state.menu_screen == SCREEN_ROOT:
        if game_state.menu_index == 0:
            game_state.start_full_game()
        elif game_state.menu_index == 1:
            game_state.menu_screen = SCREEN_SCENARIOS
            game_state.menu_index = 0
        elif game_state.menu_index == 2:
            game_state.menu_screen = SCREEN_HERO
            game_state.menu_index = 0
        elif game_state.menu_index == 3:
            game_state.start_goal_kicking()
        else:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
    elif game_state.menu_screen == SCREEN_HERO:
        if game_state.menu_index >= len(hero_levels.HERO_LEVELS):   # BACK
            game_state.menu_screen = SCREEN_ROOT
            game_state.menu_index = 2
        elif game_state.menu_index < game_state.hero_unlocked:
            game_state.start_hero(game_state.menu_index)
    else:
        if game_state.menu_index >= len(levels.SCENARIOS):      # BACK entry
            game_state.menu_screen = SCREEN_ROOT
            game_state.menu_index = 1
        elif game_state.menu_index < game_state.unlocked:       # locked ones ignore
            game_state.start_scenario(game_state.menu_index)


# ── End-screen input ────────────────────────────────────────────────

def handle_end_input(game_state, event):
    if event.type != pygame.KEYDOWN:
        return
    if event.key == pygame.K_r:
        if game_state.game_mode == "scenario":
            game_state.start_scenario(game_state.scenario_index)
        else:
            game_state.start_full_game()
    elif event.key == pygame.K_RETURN:
        nxt = game_state.scenario_index + 1
        if (game_state.result == "win" and game_state.game_mode == "scenario"
                and nxt < len(levels.SCENARIOS) and nxt < game_state.unlocked):
            game_state.start_scenario(nxt)
    elif event.key == pygame.K_ESCAPE:
        game_state.phase = PHASE_MENU
        game_state.menu_screen = SCREEN_ROOT
        game_state.menu_index = 0


# ── CHARACTER MENU (K_c hotkey, not a ROOT_OPTIONS entry) ────────────

def open_character(game_state):
    """Enter the character menu, remembering whichever phase was
    active so ESC / the hotkey again restores it instead of always
    dropping back to the root menu. Adjustments made on a previous
    visit (game_state.character) persist — this is a live attributes
    screen, not a level select, so there's nothing to reset."""
    if game_state.character is None:
        game_state.character = CharacterState()
    else:
        game_state.character.reset_transition_in()
    game_state._pre_character_phase = game_state.phase
    game_state.phase = PHASE_CHARACTER


def request_close_character(game_state):
    """Start the covering half of the pixel wipe; update_character
    flips the phase back once it finishes (see CharacterState's
    transition_dir/exit_ready)."""
    if game_state.character is not None:
        game_state.character.request_exit(game_state._pre_character_phase or PHASE_MENU)


def handle_character_input(game_state, event):
    if game_state.character is None:
        game_state.phase = PHASE_MENU
        return
    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
        # On the main attributes screen, ESC closes the whole menu;
        # on any screen nested under it (roster / naming / the save
        # prompt), ESC steps back one level instead (see
        # CharacterState.back()).
        if game_state.character.screen == "attributes":
            request_close_character(game_state)
        else:
            game_state.character.back()
        return
    game_state.character.handle_input(event)


# ── Submode update bridges ────────────────────────────────────────────

def update_hero(game_state, dt):
    """Drive the active Hero level; harvest unlocks and exit requests."""
    if game_state.hero is None:
        game_state.phase = PHASE_MENU
        return
    game_state.hero.update(dt)
    if game_state.hero.result == "win":
        game_state.hero_unlocked = max(game_state.hero_unlocked,
                                       game_state.hero.level_index + 2)
    request, game_state.hero.exit_request = game_state.hero.exit_request, None
    if request == "menu":
        game_state.phase = PHASE_MENU
        game_state.menu_screen = SCREEN_HERO
        game_state.menu_index = game_state.hero.level_index
    elif request == "next":
        nxt = game_state.hero.level_index + 1
        if nxt < len(hero_levels.HERO_LEVELS) and nxt < game_state.hero_unlocked:
            game_state.start_hero(nxt)


def update_goalkick(game_state, dt):
    """Drive the GOAL KICKING practice range; harvest exit requests.

    Freeform, no unlocks to track — unlike update_hero there's
    nothing to do here but forward the update and watch for "menu".
    """
    if game_state.goalkick is None:
        game_state.phase = PHASE_MENU
        return
    game_state.goalkick.update(dt)
    request, game_state.goalkick.exit_request = game_state.goalkick.exit_request, None
    if request == "menu":
        game_state.phase = PHASE_MENU
        game_state.menu_screen = SCREEN_ROOT
        game_state.menu_index = 3


def update_character(game_state, dt):
    """Drive the character menu's transition timer; hand the phase
    back to wherever it was opened from once the covering wipe
    finishes (see CharacterState.request_exit / exit_ready)."""
    if game_state.character is None:
        game_state.phase = PHASE_MENU
        return
    game_state.character.update(dt)
    if game_state.character.exit_ready:
        game_state.phase = game_state.character.pending_exit_phase or PHASE_MENU
        game_state._pre_character_phase = None

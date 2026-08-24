"""menu.py — root/scenario/hero menu navigation, the CHARACTER MENU
hotkey flow, and the three submode update bridges (Hero/Goal Kicking/
Character) that route a finished submode's exit_request back to a
menu screen.

Split out of game_state.py to keep menu navigation and submode
bridging in their own module — follows the same convention as
mechanics.py/possession.py/
ai_control.py: every function takes the owning `game_state` object as
its first argument rather than being a GameState method.
"""

import pygame

import hero_levels
import levels
from character_state import CharacterState
from game_phases import (PHASE_CHARACTER, PHASE_MENU, ROOT_OPTIONS,
                          SCREEN_HERO, SCREEN_HERO_LEAGUES, SCREEN_ROOT,
                          SCREEN_SCENARIOS)

# ── Menu input ──────────────────────────────────────────────────────

def hero_league_is_new(game_state, league_index):
    """True when `league_index` just became reachable and the player
    hasn't beaten its first level yet — i.e. exactly its first level
    is unlocked and nothing beyond it. Drives the league picker's
    small NEW tag (render.py) purely from existing unlock state, no
    separate "seen it" flag to track."""
    start, _ = hero_levels.LEAGUE_LEVEL_RANGE[league_index]
    return game_state.hero_unlocked == start + 1


def hero_league_just_cleared(game_state, league_index):
    """True once every level in `league_index` is unlocked AND a next
    league exists to advance into. Drives two things: the small NEW
    sticker render.py draws next to SCREEN_HERO's BACK row (purely
    decorative — see render._new_icon, there's no separate row for
    this), and which league BACK/ESC actually lands the cursor on
    (see _leave_hero_level_list below) — the next one, not the one
    just finished, so the player lands right where that league's own
    NEW sticker is waiting on the picker (see hero_league_is_new)."""
    _, end = hero_levels.LEAGUE_LEVEL_RANGE[league_index]
    return (game_state.hero_unlocked > end
           and league_index + 1 < len(hero_levels.HERO_LEAGUES))


def hero_league_rows(game_state, league_index):
    """Every selectable row for one league's level-list screen
    (SCREEN_HERO), in display order: each of its levels, then — only
    once every level in the league is unlocked and there's no next
    league to advance into — a locked, inert MORE LEAGUES COMING
    placeholder, then BACK.

    One shared table rather than separate ad-hoc lists, so
    handle_menu_input/select_menu_option (dispatch) and render.py
    (labels/locked state) can never drift out of sync on row count or
    order — exactly the kind of thing that's easy to get subtly wrong
    twice. Whether BACK carries the small NEW sticker (see
    hero_league_just_cleared) is decided separately, purely for
    rendering — it's a decoration on this row, never a row or a
    button of its own.

    Each row: (label, locked, tagline, kind) — kind is "level" (select
    to start it, only when not locked), "locked" (inert — a level past
    hero_unlocked, or MORE LEAGUES COMING), or "back".
    """
    start, end = hero_levels.LEAGUE_LEVEL_RANGE[league_index]
    rows = []
    for flat_i in range(start, end):
        lvl = hero_levels.HERO_LEVELS[flat_i]
        locked = flat_i >= game_state.hero_unlocked
        rows.append((lvl["name"], locked, lvl["tagline"],
                    "locked" if locked else "level"))
    if (game_state.hero_unlocked > end
            and league_index + 1 >= len(hero_levels.HERO_LEAGUES)):
        rows.append(("MORE LEAGUES COMING", True, None, "locked"))
    rows.append(("BACK", False, None, "back"))
    return rows


def _leave_hero_level_list(game_state):
    """Return to the league picker from SCREEN_HERO — shared by
    select_menu_option's BACK row and handle_menu_input's ESC, so
    both leave the same way. Lands on the next league if this one's
    fully cleared (hero_league_just_cleared), otherwise back on the
    one just left, same as ever."""
    league = game_state.hero_league_index
    game_state.menu_screen = SCREEN_HERO_LEAGUES
    game_state.menu_index = (league + 1 if hero_league_just_cleared(game_state, league)
                             else league)


def menu_options(game_state):
    """The entries on the current menu screen (labels only — see
    hero_league_rows for SCREEN_HERO's fuller per-row detail)."""
    if game_state.menu_screen == SCREEN_ROOT:
        return list(ROOT_OPTIONS)
    if game_state.menu_screen == SCREEN_HERO_LEAGUES:
        return [lg["name"] for lg in hero_levels.HERO_LEAGUES] + ["BACK"]
    if game_state.menu_screen == SCREEN_HERO:
        return [row[0] for row in hero_league_rows(game_state, game_state.hero_league_index)]
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
        if game_state.menu_screen == SCREEN_HERO:
            _leave_hero_level_list(game_state)
        else:
            back_index = 2 if game_state.menu_screen == SCREEN_HERO_LEAGUES else 1
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
            game_state.menu_screen = SCREEN_HERO_LEAGUES
            game_state.menu_index = 0
        elif game_state.menu_index == 3:
            game_state.start_goal_kicking()
        else:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    elif game_state.menu_screen == SCREEN_HERO_LEAGUES:
        leagues = hero_levels.HERO_LEAGUES
        if game_state.menu_index >= len(leagues):        # BACK
            game_state.menu_screen = SCREEN_ROOT
            game_state.menu_index = 2
            return
        start, _ = hero_levels.LEAGUE_LEVEL_RANGE[game_state.menu_index]
        if start < game_state.hero_unlocked:              # league reachable
            game_state.hero_league_index = game_state.menu_index
            game_state.menu_screen = SCREEN_HERO
            game_state.menu_index = 0

    elif game_state.menu_screen == SCREEN_HERO:
        rows = hero_league_rows(game_state, game_state.hero_league_index)
        _, locked, _, kind = rows[game_state.menu_index]
        if kind == "level" and not locked:
            start, _ = hero_levels.LEAGUE_LEVEL_RANGE[game_state.hero_league_index]
            game_state.start_hero(start + game_state.menu_index)
        elif kind == "back":
            _leave_hero_level_list(game_state)
        # kind == "locked" (a not-yet-unlocked level, or MORE LEAGUES
        # COMING): inert, same as a locked scenario below.

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
        level_index = game_state.hero.level_index
        league = hero_levels.LEVEL_LEAGUE_INDEX[level_index]
        start, _ = hero_levels.LEAGUE_LEVEL_RANGE[league]
        game_state.phase = PHASE_MENU
        game_state.menu_screen = SCREEN_HERO
        game_state.hero_league_index = league
        game_state.menu_index = level_index - start
    elif request == "next":
        # Capped at the league boundary: clearing a league's last
        # level always routes back through the menu, where SCREEN_
        # HERO's NEW row is the deliberate way to advance tiers,
        # rather than ENTER silently carrying you across into the
        # next league's level 1 (see hero_render._render_done's
        # matching has_next cap, which keeps the win screen from even
        # offering this in that case).
        nxt = game_state.hero.level_index + 1
        same_league = (nxt < len(hero_levels.HERO_LEVELS)
                      and hero_levels.LEVEL_LEAGUE_INDEX[nxt] ==
                          hero_levels.LEVEL_LEAGUE_INDEX[game_state.hero.level_index])
        if same_league and nxt < game_state.hero_unlocked:
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

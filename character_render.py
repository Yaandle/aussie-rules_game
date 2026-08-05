"""character_render.py — drawing for the CHARACTER MENU. Never mutates
state (see character_state.CharacterState).

Reuses hero_render's ground scene and cached player-sprite helpers
directly, and imitates render.py's `_render_main_menu` entry-loop look
(the "> " prefix, gold-when-selected / cream-when-active convention) for
every screen — the main attributes panel, the saved-players roster list,
the new-player naming box, and the disk/session save prompt. No new
visual language, no new art, procedural pixel art only like everywhere
else in this project.
"""

import pygame

import character_state
import hero_render
import mechanics
import render
import settings

_wipe_cache = {}   # rounded progress (0..1, 2dp) -> scaled wipe Surface

ROW_H = 34
GROUP_GAP = 16
BAR_W = 110   # fillable stat-meter rectangle, right-aligned on a stat row
BAR_H = 14


# ── Scene: ground + a single standing portrait ──────────────────────

def _render_scene(display, state):
    """Ground (hero_render's shared routine) plus one player, centered,
    facing the camera — the existing sprite is already a front-facing
    billboard, so this just scales it up for a close-up read."""
    cam = state.camera
    hero_render._render_ground(display, cam)

    proj = cam.project(settings.FIELD_CX, settings.FIELD_CY, 0.0)
    if proj is None:
        return
    sx, sy, scale, depth = proj

    # Height is stored/displayed in real cm (see character_state.py); the
    # baseline cm maps to a 1.0 scale multiplier, everything else scales
    # proportionally from there. Uses the live draft, not the applied
    # default, so the portrait always reflects whatever's on screen —
    # the ALL PLAYERS default, or whichever saved player is loaded.
    height_mult = state.height / settings.CHARACTER_HEIGHT_BASELINE_CM
    sprite_world_h = 4.0 * settings.CHARACTER_SPRITE_SCALE * height_mult
    k = sprite_world_h * scale / 12.0
    w, h = max(3, int(7 * k)), max(5, int(12 * k))

    base = hero_render._player_sprite(settings.YELLOW, False, 0, variant=0)
    sprite = hero_render._scaled(base, w, h, ("character_portrait", w, h))
    w, h = sprite.get_size()
    shadow = hero_render._soft_ellipse_shadow(max(4, int(w * 1.1)),
                                              max(2, int(w * 0.4)))

    # A slow idle sway (no walk cycle here) so the portrait doesn't read
    # as a static cardboard cutout.
    bob = int(1 + k * 0.15) * ((pygame.time.get_ticks() // 900) % 2)

    display.blit(shadow, (int(sx) - shadow.get_width() // 2,
                          int(sy) - shadow.get_height() // 2))
    display.blit(sprite, (int(sx) - w // 2, int(sy) - h - bob))


# ── Shared panel chrome ──────────────────────────────────────────────

def _panel_box(display, rect):
    """The charcoal plate every screen in this menu is drawn on, styled
    exactly like render.py's controls/end-screen boxes."""
    charcoal = pygame.Color(settings.UI_CHARCOAL)
    ink = pygame.Color(settings.INK)
    shadow = render._soft_shadow(rect.w, rect.h)
    display.blit(shadow, (rect.x - (shadow.get_width() - rect.w) // 2,
                          rect.y - (shadow.get_height() - rect.h) // 2 + 6))
    pygame.draw.rect(display, charcoal, rect)
    pygame.draw.rect(display, ink, rect, 3)


def _footer(display, text, y):
    """Inline hint line, e.g. "ARROWS · ENTER SELECT/ADJUST · ESC BACK".

    Out of scope for the controller-support pass that added Xbox hints
    to the three popup CONTROLS overlays (render.py / hero_render.py /
    goalkick_render.py's `_render_menu`/`_render_controls`) — this menu
    already reads controller D-pad/stick/A/B/START input fine (see
    controller.py; every existing handle_input picks up its synthetic
    KEYDOWN events for free), it just doesn't advertise it inline here
    yet. Revisit if that's confusing in practice.
    """
    font, font_small, font_big = render._fonts()
    cream = pygame.Color(settings.CREAM)
    label = font_small.render(text, True, cream)
    display.blit(label, (settings.WINDOW_W // 2 - label.get_width() // 2, y))


# ── Attributes panel (the main screen) ──────────────────────────────

def _stat_range(row):
    if row["key"] == "speed":
        return settings.CHARACTER_SPEED_MIN, settings.CHARACTER_SPEED_MAX
    if row["key"] == "height":
        return settings.CHARACTER_HEIGHT_MIN, settings.CHARACTER_HEIGHT_MAX
    return None


def _stat_value_text(state, row):
    if row["key"] == "speed":
        return f"{state.speed:.1f}"
    if row["key"] == "height":
        return f"{state.height:.0f} CM"
    return ""


def _draw_stat_bar(display, x, y, frac, fill_color, border_color):
    """A small rectangle stat meter: dark track, filled left-to-right by
    `frac` (0..1) as the value moves through its min/max range."""
    rect = pygame.Rect(x, y, BAR_W, BAR_H)
    pygame.draw.rect(display, (20, 22, 16), rect)
    fill_w = int((BAR_W - 4) * max(0.0, min(1.0, frac)))
    if fill_w > 0:
        pygame.draw.rect(display, fill_color,
                         (rect.x + 2, rect.y + 2, fill_w, BAR_H - 4))
    pygame.draw.rect(display, border_color, rect, 2)


def _row_label(state, i, row):
    """('> '/'  ' + text, color) for one row of the attributes screen."""
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color("#b3ac97")
    gold = pygame.Color(settings.YELLOW)
    selected = i == state.selected
    prefix = "> " if selected else "  "
    kind = row["kind"]

    if kind == "stat":
        locked = row["key"] is None
        text = prefix + row["name"] + ("  · LOCKED" if locked else "")
        color = muted if locked else (gold if selected else cream)
    elif kind == "toggle":
        glyph = "[X]" if state.apply_all else "[ ]"
        text = prefix + f"{glyph} APPLY TO ALL PLAYERS"
        color = gold if selected else cream
    elif kind == "picker":
        player = state.selected_player()
        name = player["name"] if player else "NONE — PRESS ENTER"
        text = prefix + f"SAVED PLAYER: {name}"
        color = gold if selected else cream
    else:   # "action" — SAVE
        text = prefix + "SAVE"
        color = gold if selected else cream
    return text, color


def render_attributes_panel(display, state):
    """Attributes list in a charcoal plate down the left side of the
    screen: the 8 stat rows (Speed/Height adjustable with a fillable
    value bar, the rest locked), then the APPLY TO toggle, the saved-
    player picker (only while APPLY TO ALL PLAYERS is off), and SAVE."""
    font, font_small, font_big = render._fonts()
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color("#b3ac97")
    gold = pygame.Color(settings.YELLOW)

    box = pygame.Rect(40, 40, 440, 560)
    _panel_box(display, box)

    title = font_big.render("CHARACTER", True, cream)
    display.blit(title, (box.x + 30, box.y + 20))
    sub = font_small.render("SPEED / HEIGHT ADJUSTABLE  ·  REST LOCKED",
                            True, muted)
    display.blit(sub, (box.x + 30, box.y + 52))

    rows = state.attribute_screen_rows()
    stat_count = len(character_state.ATTRIBUTE_ROWS)
    y = box.y + 86
    for i, row in enumerate(rows):
        if i == character_state.GROUP_1_LEN or i == stat_count:
            y += GROUP_GAP

        text, color = _row_label(state, i, row)
        label = font.render(text, True, color)
        display.blit(label, (box.x + 30, y))

        if row["kind"] == "stat" and row["key"] is not None:
            selected = i == state.selected
            vmin, vmax = _stat_range(row)
            value = state.speed if row["key"] == "speed" else state.height
            frac = (value - vmin) / (vmax - vmin) if vmax > vmin else 0.0
            bar_x = box.right - 30 - BAR_W
            bar_y = y + (label.get_height() - BAR_H) // 2
            _draw_stat_bar(display, bar_x, bar_y, frac,
                           gold if selected else cream, pygame.Color(settings.INK))
            val_text = font_small.render(_stat_value_text(state, row), True, muted)
            display.blit(val_text, (bar_x - 10 - val_text.get_width(),
                                    y + (label.get_height() - val_text.get_height()) // 2))
        y += ROW_H

    _footer(display, "ARROWS · ENTER SELECT/ADJUST · ESC BACK",
           box.bottom - 34)


# ── Saved-players roster screen ──────────────────────────────────────

def render_roster_panel(display, state):
    font, font_small, font_big = render._fonts()
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color("#b3ac97")
    gold = pygame.Color(settings.YELLOW)

    box = pygame.Rect(40, 40, 440, 560)
    _panel_box(display, box)

    title = font_big.render("SAVED PLAYERS", True, cream)
    display.blit(title, (box.x + 30, box.y + 20))
    sub = font_small.render("PICK A PLAYER TO APPLY THESE ATTRIBUTES TO",
                            True, muted)
    display.blit(sub, (box.x + 30, box.y + 52))

    rows = state.roster_rows()
    y = box.y + 86
    for i, item in enumerate(rows):
        selected = i == state.selected
        prefix = "> " if selected else "  "
        if item == character_state.ROSTER_NEW:
            text = prefix + "+ NEW PLAYER"
        elif item == character_state.ROSTER_BACK:
            text = prefix + "BACK"
        else:
            tag = "  · SAVED" if item.get("persisted") else "  · SESSION"
            text = prefix + item["name"] + tag
        label = font.render(text, True, gold if selected else cream)
        display.blit(label, (box.x + 30, y))

        if selected and isinstance(item, dict):
            stat = font_small.render(
                f"SPD {item['speed']:.1f}  ·  HGT {item['height']:.0f} CM",
                True, muted)
            display.blit(stat, (box.x + 38, y + 24))
            y += 18
        y += ROW_H

    _footer(display, "ARROWS · ENTER SELECT · ESC BACK", box.bottom - 34)


# ── New-player naming screen ─────────────────────────────────────────

def render_naming_panel(display, state):
    font, font_small, font_big = render._fonts()
    cream = pygame.Color(settings.CREAM)
    ink = pygame.Color(settings.INK)

    box = pygame.Rect(40, 40, 440, 200)
    _panel_box(display, box)

    title = font_big.render("NAME YOUR PLAYER", True, cream)
    display.blit(title, (box.x + 30, box.y + 20))

    cursor = "_" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
    field_box = pygame.Rect(box.x + 30, box.y + 80, box.w - 60, 34)
    pygame.draw.rect(display, (20, 22, 16), field_box)
    pygame.draw.rect(display, ink, field_box, 2)
    field = font.render(state.name_draft + cursor, True, cream)
    display.blit(field, (field_box.x + 8, field_box.y + 6))

    _footer(display, "TYPE A NAME · ENTER CONFIRM · ESC CANCEL",
           box.bottom - 34)


# ── Disk / session save prompt (modal over the attributes screen) ────

def render_save_prompt(display, state):
    font, font_small, font_big = render._fonts()
    cream = pygame.Color(settings.CREAM)
    gold = pygame.Color(settings.YELLOW)

    display.blit(render._dim(140), (0, 0))

    box = pygame.Rect(0, 0, 460, 220)
    box.center = (settings.WINDOW_W // 2, settings.WINDOW_H // 2)
    _panel_box(display, box)

    title_text = "SAVE PLAYER" if not state.apply_all else "SAVE DEFAULT"
    title = font_big.render(title_text, True, cream)
    display.blit(title, (box.centerx - title.get_width() // 2, box.y + 24))

    options = ("SAVE TO DISK", "SESSION ONLY (THIS RUN)")
    y = box.y + 90
    for i, opt in enumerate(options):
        selected = i == state.save_choice
        text = ("> " if selected else "  ") + opt
        label = font.render(text, True, gold if selected else cream)
        display.blit(label, (box.centerx - 140, y))
        y += 36

    _footer(display, "ARROWS · ENTER CONFIRM · ESC CANCEL", box.bottom - 34)


# ── Message toast ─────────────────────────────────────────────────────

def _render_message(display, state):
    if not state.message:
        return
    font, font_small, font_big = render._fonts()
    cream = pygame.Color(settings.CREAM)
    charcoal = pygame.Color(settings.UI_CHARCOAL)
    ink = pygame.Color(settings.INK)

    text = font.render(state.message, True, cream)
    rect = pygame.Rect(0, 0, text.get_width() + 32, 40)
    rect.center = (settings.WINDOW_W // 2, settings.WINDOW_H - 90)
    pygame.draw.rect(display, charcoal, rect)
    pygame.draw.rect(display, ink, rect, 3)
    display.blit(text, (rect.x + 16, rect.y + 9))


# ── Pixel-wipe transition ────────────────────────────────────────────

def _wipe_surface(progress):
    """A hard-edged, blocky wipe panel: built on the small logical grid
    (structural pixels, no antialiasing) and nearest-neighbor scaled up —
    the same trick every other visual in this project uses, so entry/exit
    reads as a chunky pixel-art swipe rather than a smooth cross-fade.

    `progress` 0..1: 0 fully revealed (no panel drawn), 1 fully covered
    (panel spans the whole logical width). Sweeps in from the left.
    """
    key = round(progress, 2)
    if key not in _wipe_cache:
        small = pygame.Surface((settings.LOGICAL_W, settings.LOGICAL_H),
                               pygame.SRCALPHA)
        edge = int(settings.LOGICAL_W * key)
        if edge > 0:
            pygame.draw.rect(small, pygame.Color(settings.INK),
                             (0, 0, edge, settings.LOGICAL_H))
        _wipe_cache[key] = pygame.transform.scale(
            small, (settings.WINDOW_W, settings.WINDOW_H))
    return _wipe_cache[key]


# ── Master compose ──────────────────────────────────────────────────

def render_character(display, state):
    """One CHARACTER MENU frame: ground + standing portrait, whichever
    screen is active, the message toast, and the entry/exit pixel wipe
    on top of everything."""
    if state is None:
        return

    _render_scene(display, state)
    display.blit(render._haze(), (0, 0))
    display.blit(render._build_vignette(), (0, 0))

    if state.screen == "roster":
        render_roster_panel(display, state)
    elif state.screen == "naming":
        render_naming_panel(display, state)
    elif state.screen == "save_prompt":
        render_attributes_panel(display, state)
        render_save_prompt(display, state)
    else:
        render_attributes_panel(display, state)

    _render_message(display, state)

    progress = mechanics.smoothstep(state.wipe_progress)
    if progress > 0.0:
        display.blit(_wipe_surface(progress), (0, 0))

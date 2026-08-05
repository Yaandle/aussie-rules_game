"""character_render.py — drawing for the CHARACTER MENU. Never mutates
state (see character_state.CharacterState).

Reuses hero_render's ground scene and cached player-sprite helpers
directly, and imitates render.py's `_render_main_menu` entry-loop look
(the "> " prefix, gold-when-selected / cream-when-active / muted-and-
LOCKED convention) for the attributes panel — no new visual language, no
new art, procedural pixel art only like everywhere else in this project.
"""

import pygame

import character_state
import hero_render
import mechanics
import render
import settings

_wipe_cache = {}   # rounded progress (0..1, 2dp) -> scaled wipe Surface


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
    # proportionally from there.
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


# ── Attributes panel ─────────────────────────────────────────────────

BAR_W = 110   # fillable stat-meter rectangle, right-aligned on each
BAR_H = 14    # adjustable row's own line (see _render_panel)


def _stat_range(row):
    """(min, max) for an adjustable row's live value, or None when locked."""
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


def _render_panel(display, state):
    """Attributes list in a charcoal plate down the left side of the
    screen, styled exactly like _render_main_menu's entry loop."""
    font, font_small, font_big = render._fonts()
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color("#b3ac97")
    gold = pygame.Color(settings.YELLOW)
    charcoal = pygame.Color(settings.UI_CHARCOAL)
    ink = pygame.Color(settings.INK)

    box = pygame.Rect(40, 50, 440, 580)
    shadow = render._soft_shadow(box.w, box.h)
    display.blit(shadow, (box.x - (shadow.get_width() - box.w) // 2,
                          box.y - (shadow.get_height() - box.h) // 2 + 6))
    pygame.draw.rect(display, charcoal, box)
    pygame.draw.rect(display, ink, box, 3)

    title = font_big.render("CHARACTER", True, cream)
    display.blit(title, (box.x + 30, box.y + 24))
    sub = font_small.render("SPEED / HEIGHT ADJUSTABLE  ·  REST LOCKED",
                            True, muted)
    display.blit(sub, (box.x + 30, box.y + 62))

    y = box.y + 106
    for i, row in enumerate(character_state.ATTRIBUTE_ROWS):
        if i == character_state.GROUP_1_LEN:
            y += 20   # gap between the two attribute groups
        selected = i == state.selected
        locked = row["key"] is None
        text = ("> " if selected else "  ") + row["name"] + \
               ("  · LOCKED" if locked else "")
        color = muted if locked else (gold if selected else cream)
        label = font.render(text, True, color)
        display.blit(label, (box.x + 30, y))

        # Adjustable rows show their live value on the same line,
        # right-aligned: a numeric readout next to a fillable stat bar
        # instead of a muted tagline underneath.
        if not locked:
            vmin, vmax = _stat_range(row)
            value = state.speed if row["key"] == "speed" else state.height
            frac = (value - vmin) / (vmax - vmin) if vmax > vmin else 0.0
            bar_x = box.right - 30 - BAR_W
            bar_y = y + (label.get_height() - BAR_H) // 2
            bar_col = gold if selected else cream
            _draw_stat_bar(display, bar_x, bar_y, frac, bar_col, ink)

            val_text = font_small.render(_stat_value_text(state, row), True, muted)
            display.blit(val_text, (bar_x - 10 - val_text.get_width(),
                                    y + (label.get_height() - val_text.get_height()) // 2))
        y += 40

    footer = font_small.render("ARROWS · ENTER ADJUST · ESC BACK", True, muted)
    display.blit(footer, (settings.WINDOW_W // 2 - footer.get_width() // 2,
                          settings.WINDOW_H - 60))


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
    """One CHARACTER MENU frame: ground + standing portrait, attributes
    panel, and the entry/exit pixel wipe on top of everything."""
    if state is None:
        return

    _render_scene(display, state)
    display.blit(render._haze(), (0, 0))
    display.blit(render._build_vignette(), (0, 0))
    _render_panel(display, state)

    progress = mechanics.smoothstep(state.wipe_progress)
    if progress > 0.0:
        display.blit(_wipe_surface(progress), (0, 0))

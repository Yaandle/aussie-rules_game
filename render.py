"""render.py — all drawing, fully separated from game logic.

Aesthetic (per reference image): a pastel-sage AFL oval bathed in hazy
diffuse light. Chibi pixel players with big dark mops of hair, physical
scoreboards standing on legs at the top corners, dark rail fences along
the top and bottom edges with puffy tree clusters and park benches, and
white goal posts with red bands casting long shadows to the right.

Structural pixels live on small logical surfaces scaled up with
nearest-neighbor; ambient effects (haze, bloom, glow, vignette) render
at display resolution so softness never blurs the pixel grid. The
static scene is built once and cached.
"""

import math
import random

import pygame

import hero_levels
import levels
import settings
from game_state import ROOT_OPTIONS, SCREEN_HERO, SCREEN_ROOT

# ── Module-level caches (built lazily, once) ────────────────────────
_bg_scaled = None
_glow_cache = {}
_vignette = None
_haze_overlay = None
_slowmo_overlay = None
_font = None
_font_small = None
_font_big = None

# 3x5 pixel digit bitmaps for on-field "50" markings.
_DIGITS = {
    "5": ["111", "100", "111", "001", "111"],
    "0": ["111", "101", "101", "101", "111"],
}


# ── Small color/utility helpers ─────────────────────────────────────

def _fonts():
    """Lazy-load the monospace HUD fonts."""
    global _font, _font_small, _font_big
    if _font is None:
        _font = pygame.font.SysFont("consolas,couriernew,monospace", 18, bold=True)
        _font_small = pygame.font.SysFont("consolas,couriernew,monospace", 13, bold=True)
        _font_big = pygame.font.SysFont("consolas,couriernew,monospace", 26, bold=True)
    return _font, _font_small, _font_big


def _lighten(color, f):
    """Blend a color toward white by factor f (0..1)."""
    c = pygame.Color(color)
    return (int(c.r + (255 - c.r) * f), int(c.g + (255 - c.g) * f),
            int(c.b + (255 - c.b) * f))


def _darken(color, f):
    """Blend a color toward black by factor f (0..1)."""
    c = pygame.Color(color)
    return (int(c.r * (1 - f)), int(c.g * (1 - f)), int(c.b * (1 - f)))


def _dim(alpha):
    """Cached full-screen dark-green dim layer (one per alpha in use)."""
    key = ("dim", alpha)
    if key not in _glow_cache:
        surf = pygame.Surface((settings.WINDOW_W, settings.WINDOW_H),
                              pygame.SRCALPHA)
        surf.fill((16, 20, 12, alpha))
        _glow_cache[key] = surf
    return _glow_cache[key]


def _soft_shadow(w, h, alpha=80):
    """A soft blurred rectangular shadow (cached), for grounding structures."""
    key = ("shadow", w, h, alpha)
    if key not in _glow_cache:
        pad = 6
        small = pygame.Surface((w // 4 + pad * 2, h // 4 + pad * 2), pygame.SRCALPHA)
        pygame.draw.rect(small, (0, 0, 0, alpha),
                         (pad, pad, w // 4, h // 4), border_radius=3)
        _glow_cache[key] = pygame.transform.smoothscale(
            small, (w + pad * 8, h + pad * 8))
    return _glow_cache[key]


def _build_vignette():
    """One-time per-pixel vignette on a tiny surface, smoothscaled up."""
    global _vignette
    if _vignette is not None:
        return _vignette
    small_w, small_h = 80, 50
    surf = pygame.Surface((small_w, small_h), pygame.SRCALPHA)
    cx, cy = small_w / 2, small_h / 2
    for y in range(small_h):
        for x in range(small_w):
            r = (((x - cx) / cx) ** 2 + ((y - cy) / cy) ** 2) ** 0.5
            alpha = int(max(0.0, min(1.0, (r - 0.75) / 0.5)) * 70)
            if alpha:
                surf.set_at((x, y), (26, 32, 18, alpha))
    _vignette = pygame.transform.smoothscale(
        surf, (settings.WINDOW_W, settings.WINDOW_H))
    return _vignette


def _haze():
    """Cached atmosphere: pale mist at the top of frame, hazy tint overall."""
    global _haze_overlay
    if _haze_overlay is None:
        col = pygame.Surface((1, 64), pygame.SRCALPHA)
        r, g, b = settings.WARM_LIGHT
        for i in range(64):
            rel = i / 63.0
            # Bright misty band at the top fading out by mid-frame,
            # plus a faint overall wash.
            alpha = 10 + int(30 * max(0.0, 1.0 - rel * 2.6))
            col.set_at((0, i), (r, g, b, alpha))
        _haze_overlay = pygame.transform.smoothscale(
            col, (settings.WINDOW_W, settings.WINDOW_H))
    return _haze_overlay


def _inside_oval(x, y, inflate=0.0):
    """Normalized elliptical distance test against the field boundary."""
    rx = settings.FIELD_W / 2 + inflate
    ry = settings.FIELD_H / 2 + inflate
    ex = (x - settings.FIELD_CX) / rx
    ey = (y - settings.FIELD_CY) / ry
    return ex * ex + ey * ey <= 1.0


def _draw_pixel_text(surface, text, x, y, color):
    """Tiny 3x5 pixel digits (for the on-field '50' markings)."""
    col = pygame.Color(color)
    for ch in text:
        bitmap = _DIGITS.get(ch)
        if bitmap:
            for row, bits in enumerate(bitmap):
                for c, bit in enumerate(bits):
                    if bit == "1":
                        surface.set_at((x + c, y + row), col)
        x += 4


# ── Static scene (built once, logical resolution) ───────────────────

def render_field(surface):
    """Field markings: boundary, centre circles/square, 50m arcs, goals."""
    field_rect = pygame.Rect(settings.FIELD_LEFT, settings.FIELD_TOP,
                             settings.FIELD_W, settings.FIELD_H)
    cx, cy = int(settings.FIELD_CX), int(settings.FIELD_CY)

    # Boundary line, centre circles (3m inner + 10m outer), centre square.
    pygame.draw.ellipse(surface, settings.LINE, field_rect, 1)
    pygame.draw.circle(surface, settings.LINE, (cx, cy), 9, 1)
    pygame.draw.circle(surface, settings.LINE, (cx, cy), 3, 1)
    pygame.draw.rect(surface, settings.LINE, (cx - 12, cy - 12, 24, 24), 1)

    # 50m arcs facing infield from each goal.
    r = settings.SCORING_ARC_RADIUS
    right = pygame.Rect(settings.GOAL_RIGHT[0] - r, cy - r, r * 2, r * 2)
    left = pygame.Rect(settings.GOAL_LEFT[0] - r, cy - r, r * 2, r * 2)
    pygame.draw.arc(surface, settings.LINE, right, math.pi / 2, math.pi * 1.5)
    pygame.draw.arc(surface, settings.LINE, left, -math.pi / 2, math.pi / 2)

    # "50" markings just inside each arc.
    _draw_pixel_text(surface, "50", int(settings.GOAL_RIGHT[0] - r - 6), cy - 2, settings.LINE)
    _draw_pixel_text(surface, "50", int(settings.GOAL_LEFT[0] + r), cy - 2, settings.LINE)

    # Goal squares extending infield from each goal line.
    gx_r, gx_l = int(settings.GOAL_RIGHT[0]), int(settings.GOAL_LEFT[0])
    pygame.draw.rect(surface, settings.LINE, (gx_r - 6, cy - 4, 6, 8), 1)
    pygame.draw.rect(surface, settings.LINE, (gx_l, cy - 4, 6, 8), 1)
    pygame.draw.ellipse(surface, settings.DIRT, (gx_r - 5, cy - 1, 3, 2))  # worn turf
    pygame.draw.ellipse(surface, settings.DIRT, (gx_l + 2, cy - 1, 3, 2))

    # Four posts per end: white shafts, red base bands, long right shadows.
    for gx in (gx_l, gx_r):
        for dy, height in ((-3, 6), (3, 6), (-7, 4), (7, 4)):
            bx, by = gx, cy + dy
            pygame.draw.line(surface, settings.MOSS,          # long shadow → right
                             (bx + 1, by + 1), (bx + 4, by + 2))
            pygame.draw.line(surface, settings.LINE,          # white shaft
                             (bx, by), (bx, by - height))
            pygame.draw.line(surface, settings.POST_RED,      # red base band
                             (bx, by), (bx, by - 1))
            surface.set_at((bx, by - height), pygame.Color(settings.BG))  # sun cap


def _render_grass(surface, rng):
    """Pastel grass: hazy paddocks beyond the fences, near-uniform oval."""
    surface.fill(pygame.Color(settings.GRASS_OUT))
    field_rect = pygame.Rect(settings.FIELD_LEFT, settings.FIELD_TOP,
                             settings.FIELD_W, settings.FIELD_H)

    # Hazy paddock strips beyond the top and bottom fences.
    pygame.draw.rect(surface, pygame.Color(settings.BEYOND),
                     (0, 0, settings.LOGICAL_W, 9))
    pygame.draw.rect(surface, pygame.Color(settings.BEYOND),
                     (0, settings.LOGICAL_H - 6, settings.LOGICAL_W, 6))

    # Subtle faux thickness: soft shadow, then extrusion side under the oval.
    pygame.draw.ellipse(surface, pygame.Color(settings.GRASS_EDGE_SHADOW),
                        field_rect.move(0, 3))
    pygame.draw.ellipse(surface, pygame.Color(settings.GRASS_EDGE),
                        field_rect.move(0, 1))

    # Mown stripes clipped to the oval — near-uniform, whisper-quiet contrast.
    rx, ry = settings.FIELD_W / 2, settings.FIELD_H / 2
    for x in range(settings.FIELD_LEFT, settings.FIELD_LEFT + settings.FIELD_W + 1):
        t = (x - settings.FIELD_CX) / rx
        if abs(t) >= 1.0:
            continue
        dy = ry * math.sqrt(1.0 - t * t)
        shade = settings.GRASS_IN if (x // 10) % 2 == 0 else settings.GRASS_IN2
        pygame.draw.line(surface, shade,
                         (x, int(settings.FIELD_CY - dy)),
                         (x, int(settings.FIELD_CY + dy)))

    # Gentle vertical light inside the oval: lit top, shaded base.
    grad = pygame.Surface((settings.LOGICAL_W, settings.LOGICAL_H), pygame.SRCALPHA)
    for y in range(settings.FIELD_TOP, settings.FIELD_TOP + settings.FIELD_H + 1):
        ty = (y - settings.FIELD_CY) / ry
        if abs(ty) >= 1.0:
            continue
        dx = rx * math.sqrt(1.0 - ty * ty)
        rel = (y - settings.FIELD_TOP) / settings.FIELD_H
        if rel < 0.45:
            alpha = int((0.45 - rel) / 0.45 * 20)
            col = (246, 252, 220, alpha)
        elif rel > 0.55:
            alpha = int((rel - 0.55) / 0.45 * 22)
            col = (40, 52, 28, alpha)
        else:
            continue
        pygame.draw.line(grad, col,
                         (int(settings.FIELD_CX - dx), y),
                         (int(settings.FIELD_CX + dx), y))
    surface.blit(grad, (0, 0))

    # Sparse clean texture: light speckle and tiny sprigs, reference-style.
    for _ in range(260):
        x = rng.randrange(settings.LOGICAL_W)
        y = rng.randrange(settings.LOGICAL_H)
        if _inside_oval(x, y):
            if rng.random() < 0.30:
                surface.set_at((x, y), pygame.Color(
                    rng.choice((settings.GRASS_LIGHT, settings.GRASS_DARK))))
        else:
            surface.set_at((x, y), pygame.Color(
                rng.choice((settings.GRASS_DARK, settings.MOSS,
                            settings.GRASS_LIGHT))))

    # Small grass sprigs: a few on the oval, more on the surrounds.
    def sprig(x, y):
        surface.set_at((x, y), pygame.Color(settings.MOSS))
        surface.set_at((x - 1, y + 1), pygame.Color(settings.MOSS))
        surface.set_at((x + 1, y + 1), pygame.Color(settings.GRASS_DARK))

    placed = 0
    while placed < 14:
        x = rng.randrange(30, settings.LOGICAL_W - 30)
        y = rng.randrange(20, settings.LOGICAL_H - 20)
        if _inside_oval(x, y, inflate=-6):
            sprig(x, y)
            placed += 1
    placed = 0
    while placed < 16:
        x = rng.randrange(3, settings.LOGICAL_W - 3)
        y = rng.randrange(9, settings.LOGICAL_H - 7)
        if not _inside_oval(x, y, inflate=2):
            sprig(x, y)
            placed += 1

    # The rare cream fleck on the surrounds — restraint over decoration.
    flecks = 0
    while flecks < 5:
        x = rng.randrange(3, settings.LOGICAL_W - 3)
        y = rng.randrange(9, settings.LOGICAL_H - 7)
        if not _inside_oval(x, y, inflate=4):
            surface.set_at((x, y), pygame.Color(settings.CREAM))
            flecks += 1


def _tree(surface, x, y):
    """A puffy tree cluster: three overlapping lobes, lit speckle, soft shadow."""
    def dot(px, py, color):
        if 0 <= px < settings.LOGICAL_W and 0 <= py < settings.LOGICAL_H:
            surface.set_at((px, py), pygame.Color(color))

    pygame.draw.ellipse(surface, pygame.Color(settings.MOSS), (x - 3, y + 3, 12, 3))
    pygame.draw.circle(surface, pygame.Color(settings.TREE_DARK), (x + 2, y + 1), 3)
    pygame.draw.circle(surface, pygame.Color(settings.TREE), (x - 2, y), 3)
    pygame.draw.circle(surface, pygame.Color(settings.TREE), (x + 1, y - 1), 3)
    dot(x - 3, y - 2, settings.TREE_LIGHT)
    dot(x, y - 3, settings.TREE_LIGHT)
    dot(x + 2, y - 2, settings.TREE_LIGHT)


def _render_environment(surface, rng):
    """Rail fences top/bottom, puffy trees, bushes, and dark park benches."""

    # Dark rail fences: posts every few units joined by a single rail.
    def fence_row(rail_y):
        pygame.draw.line(surface, settings.FENCE,
                         (6, rail_y), (settings.LOGICAL_W - 7, rail_y))
        for x in range(8, settings.LOGICAL_W - 7, 6):
            surface.set_at((x, rail_y - 1), pygame.Color(settings.FENCE))
            surface.set_at((x, rail_y + 1), pygame.Color(settings.FENCE))
            surface.set_at((x + 1, rail_y + 2), pygame.Color(settings.MOSS))  # shadow

    fence_row(9)
    fence_row(settings.LOGICAL_H - 7)

    # Trees: clustered along the top and bottom edges, plus the open sides.
    trees = ((10, 7), (48, 5), (96, 4), (142, 6), (188, 8),
             (8, 104), (44, 107), (92, 106), (148, 107), (190, 104),
             (14, 30), (12, 84), (186, 28), (188, 86))
    for (x, y) in trees:
        _tree(surface, x, y)

    # Bushes: small mounds tucked between the trees.
    for (x, y) in ((30, 8), (166, 6), (72, 107), (126, 106), (12, 60), (188, 58)):
        surface.set_at((x + 2, y + 1), pygame.Color(settings.MOSS))
        pygame.draw.circle(surface, pygame.Color(settings.TREE), (x, y), 2)
        surface.set_at((x, y - 1), pygame.Color(settings.TREE_LIGHT))

    # Park benches with backrests, in front of the bottom fence.
    for (x, y) in ((60, 108), (116, 108)):
        pygame.draw.line(surface, settings.FENCE, (x, y - 1), (x + 14, y - 1))  # back
        pygame.draw.line(surface, settings.FENCE, (x, y + 1), (x + 14, y + 1))  # seat
        surface.set_at((x + 1, y + 2), pygame.Color(settings.FENCE))            # legs
        surface.set_at((x + 13, y + 2), pygame.Color(settings.FENCE))


def _background():
    """Build (once) and return the full static scene, scaled to the window."""
    global _bg_scaled
    if _bg_scaled is None:
        rng = random.Random(11)   # seeded: the scene is stable across frames
        layer = pygame.Surface((settings.LOGICAL_W, settings.LOGICAL_H))
        _render_grass(layer, rng)
        render_field(layer)
        _render_environment(layer, rng)
        _bg_scaled = pygame.transform.scale(
            layer, (settings.WINDOW_W, settings.WINDOW_H))
    return _bg_scaled


# ── Dynamic entities (logical resolution, redrawn per frame) ────────

def _draw_player_sprite(surface, x, y, team, walking, walk_frame):
    """Chibi sprite, 7 wide x 12 tall: big dark mop, side-shaded guernsey.

    Reference proportions — the head is nearly half the body. The 3D feel
    comes entirely from lighting: every surface is lit from the upper-left,
    so the right column of hair, skin, and guernsey sits one shade darker
    and the upper-left hair pixels catch the sun.
    """
    hair = pygame.Color(settings.HAIR)
    hair_lit = _lighten(settings.HAIR, 0.22)
    skin = pygame.Color(settings.SKIN)
    skin_sh = _darken(settings.SKIN, 0.18)
    body = pygame.Color(team)
    body_sh = _darken(team, 0.28)
    stripe = _darken(team, 0.5)
    boot = pygame.Color(settings.SHORTS)

    # The mop: rounded and oversized, sun catching the upper-left curve.
    pygame.draw.rect(surface, hair, (x - 1, y - 6, 3, 1))
    pygame.draw.rect(surface, hair, (x - 2, y - 5, 5, 1))
    pygame.draw.rect(surface, hair, (x - 3, y - 4, 7, 2))
    surface.set_at((x - 1, y - 6), hair_lit)
    surface.set_at((x - 2, y - 5), hair_lit)
    surface.set_at((x - 3, y - 4), hair_lit)

    # Face under the fringe, framed by side locks; right cheek in shade.
    surface.set_at((x - 2, y - 2), hair)
    surface.set_at((x + 2, y - 2), hair)
    pygame.draw.rect(surface, skin, (x - 1, y - 2, 3, 1))
    surface.set_at((x + 1, y - 2), skin_sh)
    pygame.draw.rect(surface, skin, (x - 1, y - 1, 3, 1))   # chin
    surface.set_at((x + 1, y - 1), skin_sh)

    # Guernsey: shoulders, then torso with bare arms; right side shaded.
    pygame.draw.rect(surface, body, (x - 2, y, 5, 1))
    surface.set_at((x, y), stripe)
    surface.set_at((x + 2, y), body_sh)
    surface.set_at((x - 3, y + 1), skin)                    # arms
    surface.set_at((x + 3, y + 1), skin_sh)
    pygame.draw.rect(surface, body, (x - 2, y + 1, 5, 1))
    surface.set_at((x, y + 1), stripe)
    surface.set_at((x + 2, y + 1), body_sh)
    pygame.draw.rect(surface, body, (x - 1, y + 2, 3, 1))
    surface.set_at((x, y + 2), stripe)
    surface.set_at((x + 1, y + 2), body_sh)

    pygame.draw.rect(surface, pygame.Color(settings.SHORTS), (x - 1, y + 3, 3, 1))

    # Legs and boots — the two-frame stride lifts alternate feet.
    surface.set_at((x - 1, y + 4), skin)
    surface.set_at((x + 1, y + 4), skin_sh)
    if walking and walk_frame == 0:
        surface.set_at((x - 1, y + 5), boot)     # left planted, right lifted
        surface.set_at((x + 1, y + 4), boot)
    elif walking:
        surface.set_at((x + 1, y + 5), boot)     # right planted, left lifted
        surface.set_at((x - 1, y + 4), boot)
    else:
        surface.set_at((x - 1, y + 5), boot)
        surface.set_at((x + 1, y + 5), boot)


# ── Scoreboards & HUD (display resolution) ──────────────────────────

def _render_menu(display):
    """Controls overlay: dims the paused scene, lists every binding."""
    font, font_small, font_big = _fonts()

    display.blit(_dim(160), (0, 0))

    box = pygame.Rect(0, 0, 540, 396)
    box.center = (settings.WINDOW_W // 2, settings.WINDOW_H // 2)
    shadow = _soft_shadow(box.w, box.h)
    display.blit(shadow, (box.x - (shadow.get_width() - box.w) // 2,
                          box.y - (shadow.get_height() - box.h) // 2 + 6))
    pygame.draw.rect(display, pygame.Color(settings.UI_CHARCOAL), box)
    pygame.draw.rect(display, pygame.Color(settings.INK), box, 3)

    title = font_big.render("CONTROLS", True, pygame.Color(settings.CREAM))
    display.blit(title, (box.centerx - title.get_width() // 2, box.y + 22))

    rows = (("WASD / ARROWS", "MOVE"),
            ("1 / Q", "HANDBALL"),
            ("2 / K", "KICK — CLICK TO AIM"),
            ("3 / SPACE", "BOUNCE"),
            ("ESC", "CANCEL AIM / MENU"),
            ("M", "OPEN · CLOSE MENU"),
            ("BACKSPACE", "QUIT TO MAIN MENU"))
    muted = pygame.Color("#b3ac97")
    for i, (key, action) in enumerate(rows):
        y = box.y + 76 + i * 38
        display.blit(font.render(key, True, pygame.Color(settings.YELLOW)),
                     (box.x + 36, y))
        display.blit(font.render(action, True, muted), (box.x + 250, y))

    footer = font_small.render("BOUNCE EVERY 15M OF RUNNING  ·  GAME PAUSED",
                               True, muted)
    display.blit(footer, (box.centerx - footer.get_width() // 2,
                          box.bottom - 40))


def _slowmo():
    """Cached cinematic overlay for decision mode: cool tint + letterbox."""
    global _slowmo_overlay
    if _slowmo_overlay is None:
        _slowmo_overlay = pygame.Surface(
            (settings.WINDOW_W, settings.WINDOW_H), pygame.SRCALPHA)
        _slowmo_overlay.fill((70, 80, 90, 26))
        bar_h = 40
        pygame.draw.rect(_slowmo_overlay, (24, 28, 20, 140),
                         (0, 0, settings.WINDOW_W, bar_h))
        pygame.draw.rect(_slowmo_overlay, (24, 28, 20, 140),
                         (0, settings.WINDOW_H - bar_h, settings.WINDOW_W, bar_h))
    return _slowmo_overlay


def _render_main_menu(display, game_state):
    """Title and mode select, floating over the quiet empty oval."""
    font, font_small, font_big = _fonts()
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color("#b3ac97")
    gold = pygame.Color(settings.YELLOW)

    display.blit(_dim(90), (0, 0))

    title = font_big.render("AFL PROTOTYPE", True, cream)
    display.blit(title, (settings.WINDOW_W // 2 - title.get_width() // 2, 140))
    sub = font_small.render("TOP-DOWN POSSESSION PLAY", True, muted)
    display.blit(sub, (settings.WINDOW_W // 2 - sub.get_width() // 2, 182))

    # Options for the current screen (mirrors GameState._menu_options).
    if game_state.menu_screen == SCREEN_ROOT:
        entries = [(name, False, None) for name in ROOT_OPTIONS]
    elif game_state.menu_screen == SCREEN_HERO:
        entries = [(lv["name"], i >= game_state.hero_unlocked, lv["tagline"])
                   for i, lv in enumerate(hero_levels.HERO_LEVELS)]
        entries.append(("BACK", False, None))
    else:
        entries = [(s["name"], i >= game_state.unlocked, s["tagline"])
                   for i, s in enumerate(levels.SCENARIOS)]
        entries.append(("BACK", False, None))

    y = 280
    for i, (name, locked, tagline) in enumerate(entries):
        selected = i == game_state.menu_index
        text = ("> " if selected else "  ") + name + ("  · LOCKED" if locked else "")
        color = muted if locked else (gold if selected else cream)
        label = font.render(text, True, color)
        display.blit(label, (settings.WINDOW_W // 2 - 140, y))
        if selected and tagline and not locked:
            tip = font_small.render(tagline, True, muted)
            display.blit(tip, (settings.WINDOW_W // 2 - 132, y + 24))
            y += 22
        y += 44

    footer = font_small.render("ARROWS · ENTER SELECT · ESC BACK", True, muted)
    display.blit(footer, (settings.WINDOW_W // 2 - footer.get_width() // 2,
                          settings.WINDOW_H - 60))


def _render_end(display, game_state):
    """Result overlay: outcome, context line, and the retry prompts."""
    font, font_small, font_big = _fonts()
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color("#b3ac97")

    display.blit(_dim(150), (0, 0))

    box = pygame.Rect(0, 0, 560, 260)
    box.center = (settings.WINDOW_W // 2, settings.WINDOW_H // 2)
    shadow = _soft_shadow(box.w, box.h)
    display.blit(shadow, (box.x - (shadow.get_width() - box.w) // 2,
                          box.y - (shadow.get_height() - box.h) // 2 + 6))
    pygame.draw.rect(display, pygame.Color(settings.UI_CHARCOAL), box)
    pygame.draw.rect(display, pygame.Color(settings.INK), box, 3)

    if game_state.result == "win":
        title_text, title_col = "SCENARIO COMPLETE", pygame.Color(settings.YELLOW)
        context = game_state.scenario["name"]
        nxt = game_state.scenario_index + 1
        has_next = nxt < len(levels.SCENARIOS)
        prompts = ("ENTER NEXT · R RETRY · ESC MENU" if has_next
                   else "R RETRY · ESC MENU")
    elif game_state.result == "fail":
        title_text, title_col = "SCENARIO FAILED", pygame.Color(settings.ACCENT_RED)
        context = game_state.scenario["name"]
        prompts = "R RETRY · ESC MENU"
    else:
        title_text, title_col = "FULL TIME", cream
        context = f"FINAL SCORE   HOME {game_state.yellow_points:02d} - AWAY 00"
        prompts = "R REPLAY · ESC MENU"

    title = font_big.render(title_text, True, title_col)
    display.blit(title, (box.centerx - title.get_width() // 2, box.y + 44))
    ctx = font.render(context, True, cream)
    display.blit(ctx, (box.centerx - ctx.get_width() // 2, box.y + 110))
    tip = font_small.render(prompts, True, muted)
    display.blit(tip, (box.centerx - tip.get_width() // 2, box.bottom - 52))


def _render_flash(display, game_state):
    """Full-screen score flash: warm gold for goals, faint cream for behinds."""
    if game_state.flash is None:
        return
    fade = max(0.0, game_state.flash["timer"] / settings.FLASH_DURATION)
    color = pygame.Color(game_state.flash["color"])
    peak = 95 if game_state.flash["color"] == settings.YELLOW else 50
    overlay = pygame.Surface((settings.WINDOW_W, settings.WINDOW_H), pygame.SRCALPHA)
    overlay.fill((color.r, color.g, color.b, int(peak * fade)))
    display.blit(overlay, (0, 0))


# ── Master compose ──────────────────────────────────────────────────

def render(display, game_state):
    """Render the main menu. FULL GAME / SCENARIOS / AFL HERO frames are
    drawn by field_render.py and hero_render.py instead (see main.py's
    phase dispatch); this module supplies their shared display-resolution
    overlays (haze, vignette, slow-mo, controls menu, end screen)."""
    display.blit(_background(), (0, 0))
    display.blit(_haze(), (0, 0))
    display.blit(_build_vignette(), (0, 0))
    _render_main_menu(display, game_state)

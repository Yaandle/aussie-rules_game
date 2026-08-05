"""hero_render.py — all drawing for AFL Hero mode. Never mutates state.

The same pastel-sage world as the top-down game, seen from the southern
boundary: a pinhole camera (hero_camera.HeroCamera) projects the ground
plane into a low, cinematic diorama view. Structure keeps the chunky
pixel identity — player sprites are the exact 7x12 chibi from render.py,
billboard-scaled with nearest-neighbor so distance never blurs them.
Flat-shaded projected polygons do the low-poly ground; soft effects
(haze, letterbox, vignette) reuse render.py's display-resolution caches.
"""

import math

import pygame

import controller
import hero_levels
import render
import settings
from hero_state import HS_DONE, HS_RUN

# ── Module-level caches ─────────────────────────────────────────────
_sprite_cache = {}      # (team, walking, frame, variant) → 7x12 Surface
_shadow_cache = {}      # (w, h) → soft ellipse Surface
_scaled_cache = {}      # (key, w, h) → nearest-neighbor scaled Surface
_text_cache = {}        # (font, text, color) → rendered text Surface
_tree_sprite = None
_ball_sprite = None


def _text(kind, text, color):
    """Cached font rendering ("f" normal, "s" small, "b" big) — HUD text
    is nearly static, so re-rendering it every frame was pure waste."""
    key = (kind, text, str(color))
    if key not in _text_cache:
        font, font_small, font_big = render._fonts()
        chosen = {"f": font, "s": font_small, "b": font_big}[kind]
        _text_cache[key] = chosen.render(text, True, color)
    return _text_cache[key]


def _scaled(base, w, h, key):
    """Nearest-neighbor scale with a bucketed cache (per-frame scaling of
    every billboard was the renderer's main per-frame cost)."""
    w, h = max(2, w // 2 * 2), max(2, h // 2 * 2)
    ck = (key, w, h)
    if ck not in _scaled_cache:
        _scaled_cache[ck] = pygame.transform.scale(base, (w, h))
    return _scaled_cache[ck]


# ── Cached mini-sprites ─────────────────────────────────────────────

def _player_sprite(team, walking, frame, variant=0):
    """The 7x12 chibi sprite on a transparent surface, cached.

    `variant` (see render.SPRITE_VARIANTS) picks the small deterministic
    hairstyle/build/stance mix — callers pass a stable per-player key
    (their list index) so the same player looks the same all match.
    """
    key = (team, walking, frame, variant)
    if key not in _sprite_cache:
        surf = pygame.Surface((7, 12), pygame.SRCALPHA)
        render._draw_player_sprite(surf, 3, 6, team, walking, frame, variant)
        _sprite_cache[key] = surf
    return _sprite_cache[key]


def _soft_ellipse_shadow(w, h):
    """A soft dark ground ellipse, cached in size buckets of 4px."""
    w, h = max(4, w // 4 * 4), max(2, h // 2 * 2)
    key = (w, h)
    if key not in _shadow_cache:
        small = pygame.Surface((16, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(small, (30, 40, 24, 85), (0, 0, 16, 8))
        _shadow_cache[key] = pygame.transform.smoothscale(small, (w, h))
    return _shadow_cache[key]


def _tree():
    """A puffy billboard tree on a small surface, cached."""
    global _tree_sprite
    if _tree_sprite is None:
        surf = pygame.Surface((13, 12), pygame.SRCALPHA)
        pygame.draw.rect(surf, pygame.Color(settings.WOOD), (6, 8, 2, 4))
        pygame.draw.circle(surf, pygame.Color(settings.TREE_DARK), (8, 5), 4)
        pygame.draw.circle(surf, pygame.Color(settings.TREE), (4, 5), 4)
        pygame.draw.circle(surf, pygame.Color(settings.TREE), (7, 3), 4)
        surf.set_at((4, 1), pygame.Color(settings.TREE_LIGHT))
        surf.set_at((6, 0), pygame.Color(settings.TREE_LIGHT))
        surf.set_at((2, 3), pygame.Color(settings.TREE_LIGHT))
        _tree_sprite = surf
    return _tree_sprite


def _ball():
    """The oval ball: a tiny leather-brown sprite with a lit top, cached."""
    global _ball_sprite
    if _ball_sprite is None:
        surf = pygame.Surface((3, 2), pygame.SRCALPHA)
        surf.fill(pygame.Color(settings.BALL_BROWN))
        surf.set_at((1, 0), render._lighten(settings.BALL_BROWN, 0.35))
        _ball_sprite = surf
    return _ball_sprite


# ── Projection helpers ──────────────────────────────────────────────

def _proj_line(display, cam, world_pts, color, width=2, h=0.0, closed=False):
    """Project a world polyline and draw it, skipping unprojectable points."""
    pts = []
    for (x, z) in world_pts:
        p = cam.project(x, z, h)
        if p is not None:
            pts.append((int(p[0]), int(p[1])))
    if len(pts) >= 2:
        pygame.draw.lines(display, color, closed, pts, width)


def _proj_dots(display, cam, world_pts, color, every=1, h=0.0):
    """Project world points and draw a dotted trail."""
    for i, (x, z) in enumerate(world_pts):
        if i % every:
            continue
        p = cam.project(x, z, h)
        if p is not None:
            r = max(2, int(p[2] * 0.18))
            pygame.draw.circle(display, color, (int(p[0]), int(p[1])), r)


def _circle_pts(cx, cy, r, n=24, a0=0.0, a1=math.tau):
    """Sampled points of a (partial) circle on the ground plane."""
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n),
             cy + r * math.sin(a0 + (a1 - a0) * i / n))
            for i in range(n + 1)]


def _flight_lift(t, dist):
    """Ball height above the turf at flight progress t (world units)."""
    return math.sin(math.pi * min(max(t, 0.0), 1.0)) * min(dist / 6.0, 12.0)


# ── Scene: sky, oval, markings, posts ───────────────────────────────

def _render_ground(display, cam):
    """Sky, surrounds, far fence and trees, then the striped oval."""
    display.fill(pygame.Color(settings.GRASS_OUT))

    # Horizon: where the ground plane vanishes.
    far = cam.project(cam.fx, cam.fz - 500.0)
    horizon = int(far[1]) if far else int(settings.WINDOW_H * 0.2)
    pygame.draw.rect(display, render._lighten(settings.BEYOND, 0.4),
                     (0, 0, settings.WINDOW_W, max(horizon, 0)))
    # Hazy paddock band between the horizon and the far fence.
    fence = cam.project(cam.fx, 9.0)
    if fence is not None and fence[1] > horizon:
        pygame.draw.rect(display, pygame.Color(settings.BEYOND),
                         (0, horizon, settings.WINDOW_W,
                          int(fence[1]) - horizon))

    # Far fence rail with posts, then billboard trees behind it.
    rail = [(x, 9.0) for x in range(6, 195, 8)]
    _proj_line(display, cam, rail, pygame.Color(settings.FENCE),
               width=2, h=1.2)
    for x in range(8, 195, 12):
        base = cam.project(x, 9.0, 0.0)
        top = cam.project(x, 9.0, 1.2)
        if base and top:
            pygame.draw.line(display, pygame.Color(settings.FENCE),
                             (int(base[0]), int(base[1])),
                             (int(top[0]), int(top[1])), 2)
    tree_sprite = _tree()
    for (x, z) in ((10, 6), (48, 4), (96, 3), (142, 5), (188, 7)):
        p = cam.project(x, z, 0.0)
        if p is None:
            continue
        k = max(p[2] * 0.55, 0.5)
        img = _scaled(tree_sprite, int(13 * k), int(12 * k), "tree")
        display.blit(img, (int(p[0]) - img.get_width() // 2,
                           int(p[1]) - img.get_height()))

    # The oval: mown stripe bands as flat-shaded projected polygons.
    cx, cy = settings.FIELD_CX, settings.FIELD_CY
    rx, ry = settings.FIELD_W / 2, settings.FIELD_H / 2

    def y_edge(x, sign):
        t = max(-1.0, min(1.0, (x - cx) / rx))
        return cy + sign * ry * math.sqrt(max(0.0, 1.0 - t * t))

    left = settings.FIELD_LEFT
    for band in range(0, settings.FIELD_W, 10):
        a, b = left + band, min(left + band + 10, left + settings.FIELD_W)
        xs = [a + (b - a) * i / 4 for i in range(5)]
        world = ([(x, y_edge(x, -1)) for x in xs] +
                 [(x, y_edge(x, 1)) for x in reversed(xs)])
        pts = []
        for (x, z) in world:
            p = cam.project(x, z)
            if p is not None:
                pts.append((int(p[0]), int(p[1])))
        if len(pts) >= 3:
            shade = settings.GRASS_IN if (band // 10) % 2 == 0 else settings.GRASS_IN2
            pygame.draw.polygon(display, pygame.Color(shade), pts)


def _render_markings(display, cam):
    """Boundary, centre circles/square, 50m arcs, goal squares."""
    line = pygame.Color(settings.LINE)
    cx, cy = settings.FIELD_CX, settings.FIELD_CY
    rx, ry = settings.FIELD_W / 2, settings.FIELD_H / 2

    boundary = [(cx + rx * math.cos(a), cy + ry * math.sin(a))
                for a in [math.tau * i / 64 for i in range(65)]]
    _proj_line(display, cam, boundary, line, width=2)

    _proj_line(display, cam, _circle_pts(cx, cy, 9), line, width=2)
    _proj_line(display, cam, _circle_pts(cx, cy, 3, n=12), line, width=2)
    square = [(cx - 12, cy - 12), (cx + 12, cy - 12),
              (cx + 12, cy + 12), (cx - 12, cy + 12)]
    _proj_line(display, cam, square + [square[0]], line, width=2)

    r = settings.SCORING_ARC_RADIUS
    gxr, gxl = settings.GOAL_RIGHT[0], settings.GOAL_LEFT[0]
    _proj_line(display, cam,
               _circle_pts(gxr, cy, r, n=24, a0=math.pi / 2, a1=math.pi * 1.5),
               line, width=2)
    _proj_line(display, cam,
               _circle_pts(gxl, cy, r, n=24, a0=-math.pi / 2, a1=math.pi / 2),
               line, width=2)

    for gx, inward in ((gxr, -6), (gxl, 6)):
        sq = [(gx, cy - 4), (gx + inward, cy - 4),
              (gx + inward, cy + 4), (gx, cy + 4)]
        _proj_line(display, cam, sq, line, width=2)


def _post_drawables(cam):
    """Goal posts as depth-sorted drawables (they sit among the players)."""
    items = []
    cy = settings.FIELD_CY
    for gx in (settings.GOAL_LEFT[0], settings.GOAL_RIGHT[0]):
        for dz, height in ((-3, 11.0), (3, 11.0), (-7, 7.0), (7, 7.0)):
            base = cam.project(gx, cy + dz, 0.0)
            band = cam.project(gx, cy + dz, height * 0.15)
            top = cam.project(gx, cy + dz, height)
            if not (base and band and top):
                continue

            def draw(display, base=base, band=band, top=top):
                w = max(2, int(base[2] * 0.35))
                # Long ground shadow to the right, then the shaft.
                sx, sy = int(base[0]), int(base[1])
                pygame.draw.line(display, pygame.Color(settings.MOSS),
                                 (sx + 2, sy + 1),
                                 (sx + int(base[2] * 3.0), sy + 3), 2)
                pygame.draw.line(display, pygame.Color(settings.LINE),
                                 (int(band[0]), int(band[1])),
                                 (int(top[0]), int(top[1])), w)
                pygame.draw.line(display, pygame.Color(settings.POST_RED),
                                 (sx, sy), (int(band[0]), int(band[1])), w)
                pygame.draw.circle(display, pygame.Color(settings.BG),
                                   (int(top[0]), int(top[1])),
                                   max(1, w // 2))

            items.append((base[3], draw))
    return items


# ── Entities ────────────────────────────────────────────────────────

def _entity_drawables(cam, state):
    """Players and the ball as (depth, draw) pairs for painter's order."""
    items = []
    ticks = pygame.time.get_ticks()
    walk_frame = (ticks // 160) % 2
    sprite_world_h = 4.0 * settings.HERO_SPRITE_SCALE

    moving = set()
    if state.mode == HS_RUN and state.carrier is not None:
        moving.add(state.carrier)
    for player, target in state.leads.items():
        if player.distance_to(target) > 1.0:
            moving.add(player)

    for idx, p in enumerate(state.players):
        proj = cam.project(p.x, p.y, 0.0)
        if proj is None:
            continue
        sx, sy, scale, depth = proj
        k = sprite_world_h * scale / 12.0
        w, h = max(3, int(7 * k)), max(5, int(12 * k))
        walking = p in moving
        bob = 0 if walking else int(k) * (((ticks // 600) + idx) % 2)
        variant = idx % render.SPRITE_VARIANTS
        sprite = _scaled(_player_sprite(p.team, walking, walk_frame, variant),
                         w, h, ("player", p.team, walking, walk_frame, variant))
        w, h = sprite.get_size()
        shadow = _soft_ellipse_shadow(max(4, int(w * 1.1)), max(2, int(w * 0.4)))
        is_carrier = p.is_ball_carrier

        def draw(display, sx=sx, sy=sy, sprite=sprite, shadow=shadow,
                 w=w, h=h, bob=bob, is_carrier=is_carrier, k=k):
            display.blit(shadow, (int(sx) - shadow.get_width() // 2,
                                  int(sy) - shadow.get_height() // 2))
            display.blit(sprite, (int(sx) - w // 2, int(sy) - h - bob))
            if is_carrier:                       # hover arrow overhead
                ax, ay = int(sx), int(sy) - h - int(6 * k) - bob
                ay -= int(k) * ((pygame.time.get_ticks() // 400) % 2)
                s = max(2, int(2 * k))
                pygame.draw.polygon(display, pygame.Color(settings.LINE),
                                    [(ax - s, ay - s), (ax + s, ay - s),
                                     (ax, ay)])

        items.append((depth, draw))

    # The ball, lifted by its flight arc when airborne.
    lift = 0.0
    if state.flight is not None:
        lift = _flight_lift(state.flight["t"], state.flight["dist"])
    bx, bz = state.ball.x, state.ball.y
    if state.ball.possessed_by is not None:
        bx += 1.0
    proj = cam.project(bx, bz, lift + 0.6)
    ground = cam.project(bx, bz, 0.0)
    if proj is not None:
        sx, sy, scale, depth = proj
        w = max(3, int(scale * 0.9))
        img = _scaled(_ball(), w, max(2, int(w * 0.66)), "ball")

        def draw_ball(display, sx=sx, sy=sy, img=img, ground=ground,
                      lift=lift, scale=scale):
            if ground is not None and lift > 0.5:
                sh = _soft_ellipse_shadow(max(4, int(scale * 0.9)),
                                          max(2, int(scale * 0.35)))
                display.blit(sh, (int(ground[0]) - sh.get_width() // 2,
                                  int(ground[1]) - sh.get_height() // 2))
            display.blit(img, (int(sx) - img.get_width() // 2,
                               int(sy) - img.get_height() // 2))

        items.append((depth - 0.5, draw_ball))
    return items


# ── Decision previews ───────────────────────────────────────────────

def _render_decision(display, cam, state):
    """Rings, drawn paths, kick arcs, landing zones — the planning layer."""
    carrier = state.carrier
    if carrier is None:
        return
    line = pygame.Color(settings.LINE)
    gold = pygame.Color(settings.YELLOW)

    # A gentle pulsing ring under the carrier: "draw from here".
    pulse = 2.3 + 0.4 * math.sin(pygame.time.get_ticks() * 0.004)
    _proj_line(display, cam, _circle_pts(carrier.x, carrier.y, pulse, n=18),
               gold, width=2)

    # Soft rings under reachable teammates: the field of options.
    for t in state.teammates:
        if t is carrier:
            continue
        if t.distance_to(carrier.pos) <= settings.HERO_KICK_MAX:
            _proj_line(display, cam, _circle_pts(t.x, t.y, 2.6, n=18),
                       line, width=2)

    preview = state.drag_preview()
    if preview is None:
        return

    if preview["type"] == "run":
        _proj_dots(display, cam, preview["points"], line, every=2)

    elif preview["type"] == "handball":
        tx, tz = preview["target"]
        _proj_line(display, cam, _circle_pts(tx, tz, 1.8, n=14), gold, width=2)
        _proj_dots(display, cam,
                   [(carrier.x + (tx - carrier.x) * i / 6,
                     carrier.y + (tz - carrier.y) * i / 6)
                    for i in range(1, 7)], gold, h=1.0)

    elif preview["type"] == "kick":
        color = gold if preview["shot"] else line
        # Predicted flight: the curved path lifted by its arc.
        dist = carrier.distance_to(preview["landing"])
        n = len(preview["samples"]) - 1
        arc = []
        for i, (x, z) in enumerate(preview["samples"]):
            p = cam.project(x, z, _flight_lift(i / n, dist) + 0.6)
            if p is not None:
                arc.append((int(p[0]), int(p[1])))
        if len(arc) >= 2:
            pygame.draw.lines(display, color, False, arc, 2)
        # Landing marker and the honest scatter zone.
        lx, lz = preview["landing"]
        _proj_line(display, cam, _circle_pts(lx, lz, preview["error"], n=22),
                   color, width=1)
        p = cam.project(lx, lz)
        if p is not None:
            x, y = int(p[0]), int(p[1])
            pygame.draw.line(display, color, (x - 5, y), (x + 5, y), 2)
            pygame.draw.line(display, color, (x, y - 3), (x, y + 3), 2)


# ── HUD & overlays ──────────────────────────────────────────────────

_OBJECTIVE_TEXT = {
    "territory": "CARRY IT PAST THE LINE",
    "mark_lead": "A TEAMMATE MUST MARK",
    "score": "ANY SCORE WINS",
    "goal": "GOAL ONLY",
}


def _render_hud(display, state):
    """Charcoal chips: level, clock, controls, pressure, messages."""
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color("#b3ac97")
    charcoal = pygame.Color(settings.UI_CHARCOAL)
    ink = pygame.Color(settings.INK)

    # Level chip, top center.
    name = _text("s", state.level["name"], cream)
    obj = _text("s", _OBJECTIVE_TEXT[state.level["objective"]], muted)
    w = max(name.get_width(), obj.get_width()) + 28
    chip = pygame.Rect(0, 0, w, 52)
    chip.midtop = (settings.WINDOW_W // 2, 20)
    pygame.draw.rect(display, charcoal, chip)
    pygame.draw.rect(display, ink, chip, 2)
    display.blit(name, (chip.centerx - name.get_width() // 2, chip.y + 8))
    display.blit(obj, (chip.centerx - obj.get_width() // 2, chip.y + 28))

    # Clock chip, top left — red inside the final ten seconds.
    m, s = divmod(int(state.timer), 60)
    col = pygame.Color(settings.ACCENT_RED) if state.timer < 10 else cream
    clock = _text("f", f"{m:01d}:{s:02d}", col)
    box = pygame.Rect(24, 24, clock.get_width() + 28, 36)
    pygame.draw.rect(display, charcoal, box)
    pygame.draw.rect(display, ink, box, 2)
    display.blit(clock, (box.x + 14, box.y + 7))

    # Controls hint, bottom left.
    hint = _text("s", "M · CONTROLS", cream)
    chip = pygame.Rect(24, settings.WINDOW_H - 56, hint.get_width() + 28, 32)
    pygame.draw.rect(display, charcoal, chip)
    pygame.draw.rect(display, ink, chip, 2)
    display.blit(hint, (chip.x + 14, chip.y + 8))

    # Pressure bar above the carrier while deciding.
    carrier = state.carrier
    if carrier is not None and state.in_decision:
        p = state.camera.project(carrier.x, carrier.y, 0.0)
        if p is not None:
            bar = pygame.Rect(int(p[0]) - 30, int(p[1]) - 110, 60, 10)
            pygame.draw.rect(display, cream, bar)
            fill = int((bar.w - 4) * state.pressure)
            pygame.draw.rect(display, pygame.Color(settings.ACCENT_RED),
                             (bar.x + 2, bar.y + 2, fill, bar.h - 4))
            pygame.draw.rect(display, ink, bar, 2)

    # Event message, bottom center.
    if state.message:
        text = _text("f", state.message, cream)
        rect = pygame.Rect(0, 0, text.get_width() + 32, 40)
        rect.center = (settings.WINDOW_W // 2, settings.WINDOW_H - 100)
        pygame.draw.rect(display, charcoal, rect)
        pygame.draw.rect(display, ink, rect, 3)
        display.blit(text, (rect.x + 16, rect.y + 9))


def _render_controls(display):
    """Controls overlay: dims the paused level, lists the swipe bindings.

    AFL Hero's core mechanic (drawing a run/handball/kick) is mouse-drag
    only — no controller equivalent exists for it, so those rows are
    left as-is even with a pad connected. Only the two rows that do have
    a real controller binding (ESC, M — see controller.py's B/Start
    mapping) get one appended, live. RETRY has no controller binding at
    all, so it's left alone too — nothing here would be accurate."""
    font, font_small, font_big = render._fonts()
    pad = controller.is_connected()

    def key_label(keys, xbox):
        return f"{keys} · {xbox}" if pad else keys

    display.blit(render._dim(160), (0, 0))

    box = pygame.Rect(0, 0, 560, 360)
    box.center = (settings.WINDOW_W // 2, settings.WINDOW_H // 2)
    shadow = render._soft_shadow(box.w, box.h)
    display.blit(shadow, (box.x - (shadow.get_width() - box.w) // 2,
                          box.y - (shadow.get_height() - box.h) // 2 + 6))
    pygame.draw.rect(display, pygame.Color(settings.UI_CHARCOAL), box)
    pygame.draw.rect(display, pygame.Color(settings.INK), box, 3)

    title = font_big.render("CONTROLS", True, pygame.Color(settings.CREAM))
    display.blit(title, (box.centerx - title.get_width() // 2, box.y + 22))

    rows = (("L-DRAG LONG", "KICK — BEND THE SWIPE TO CURL"),
            ("L-DRAG SHORT", "HANDBALL TO A TEAMMATE"),
            ("R-DRAG", "DRAW A RUN PATH"),
            (key_label("ESC", "B"), "CANCEL DRAG / BACK"),
            ("R", "RETRY LEVEL"),
            (key_label("M", "START"), "OPEN · CLOSE THIS MENU"))
    muted = pygame.Color("#b3ac97")
    for i, (key, action) in enumerate(rows):
        y = box.y + 76 + i * 38
        display.blit(font.render(key, True, pygame.Color(settings.YELLOW)),
                     (box.x + 36, y))
        display.blit(font.render(action, True, muted), (box.x + 230, y))

    footer = font_small.render("EVERY DRAG STARTS ON YOUR PLAYER  ·  GAME PAUSED",
                               True, muted)
    display.blit(footer, (box.centerx - footer.get_width() // 2,
                          box.bottom - 40))


def _render_done(display, state):
    """Win/fail overlay in the shared charcoal-plate style."""
    font, font_small, font_big = render._fonts()
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color("#b3ac97")

    display.blit(render._dim(150), (0, 0))

    box = pygame.Rect(0, 0, 560, 260)
    box.center = (settings.WINDOW_W // 2, settings.WINDOW_H // 2)
    shadow = render._soft_shadow(box.w, box.h)
    display.blit(shadow, (box.x - (shadow.get_width() - box.w) // 2,
                          box.y - (shadow.get_height() - box.h) // 2 + 6))
    pygame.draw.rect(display, pygame.Color(settings.UI_CHARCOAL), box)
    pygame.draw.rect(display, pygame.Color(settings.INK), box, 3)

    if state.result == "win":
        title_text, col = "POSSESSION WON", pygame.Color(settings.YELLOW)
        has_next = state.level_index + 1 < len(hero_levels.HERO_LEVELS)
        prompts = ("ENTER NEXT · R RETRY · ESC MENU" if has_next
                   else "R RETRY · ESC MENU")
    else:
        title_text, col = "POSSESSION LOST", pygame.Color(settings.ACCENT_RED)
        prompts = "R RETRY · ESC MENU"

    title = font_big.render(title_text, True, col)
    display.blit(title, (box.centerx - title.get_width() // 2, box.y + 44))
    ctx = font.render(state.message or state.level["name"], True, cream)
    display.blit(ctx, (box.centerx - ctx.get_width() // 2, box.y + 110))
    tip = font_small.render(prompts, True, muted)
    display.blit(tip, (box.centerx - tip.get_width() // 2, box.bottom - 52))


# ── Master compose ──────────────────────────────────────────────────

def render_hero(display, state):
    """One AFL Hero frame: diorama scene, entities, previews, HUD."""
    cam = state.camera

    _render_ground(display, cam)
    _render_markings(display, cam)

    if state.in_decision:
        _render_decision(display, cam, state)

    drawables = _post_drawables(cam) + _entity_drawables(cam, state)
    drawables.sort(key=lambda item: -item[0])
    for _, draw in drawables:
        draw(display)

    display.blit(render._haze(), (0, 0))
    if state.in_decision:
        display.blit(render._slowmo(), (0, 0))

    _render_hud(display, state)
    display.blit(render._build_vignette(), (0, 0))

    if state.mode == HS_DONE:
        _render_done(display, state)
    elif state.show_menu:
        _render_controls(display)

"""goalkick_render.py — GOAL KICKING mode presentation.

A tight, low, first-person-ish camera that always faces whichever goal
you're kicking at — unlike the broadcast-style MAIN_CAM/HERO_CAM rigs
(field_render.py, hero_render.py), which never yaw and always show
goals left/right. Reuses HeroCamera's projection math completely
unmodified: every world point is rotated into a per-attempt "kick
space" (mechanics.kick_axes / to_kick_space) before it's projected, so
from the camera's point of view it's just another fixed, non-yawing rig
looking down its own local z axis.

The ground here is a simple banded plane rather than the full oval
renderer's boundary — this view never shows the boundary itself, so
there's nothing to gain from that extra geometry — but the 50m arc and
goal square around the goal you're kicking at are drawn (same numbers
as render_field / hero_render._render_markings, rotated into kick-space)
so the mark reads against real field distances. Sprites, shadows, and
cached text all reuse hero_render's helpers. Never mutates state.
"""

import math

import pygame

import goalkick_state as gks
import hero_render
import mechanics
import render as overlays
import settings

_MUTED = "#b3ac97"


# ── Local-space projection helpers ───────────────────────────────────

def _axes(state):
    """Forward/right unit vectors for this attempt's fixed mark -> goal
    line (frozen in practice once GK_POSITION ends, since the mark
    doesn't move again — see GoalKickState._focus_local)."""
    return mechanics.kick_axes(state.mark_pos, settings.GOAL_RIGHT)


def _local(state, fwd, right, point):
    return mechanics.to_kick_space(state.mark_pos, fwd, right, point)


def _proj_world_line(display, cam, state, fwd, right, world_pts, color,
                     width=2, closed=False):
    """Like hero_render._proj_line, but `world_pts` are ordinary field
    coordinates (the same ones render_field / hero_render._render_markings
    use) — rotated into this attempt's kick-space before projecting."""
    local_pts = [_local(state, fwd, right, p) for p in world_pts]
    hero_render._proj_line(display, cam, local_pts, color, width=width,
                           closed=closed)


# ── Ground & sky ──────────────────────────────────────────────────────

def _render_ground(display, cam):
    """Sky above the horizon, a banded grass plane below it, and a thin
    dotted guide straight down the kicking line."""
    display.fill(pygame.Color(settings.GRASS_OUT))
    far = cam.project(0.0, -400.0)
    horizon = int(far[1]) if far else int(settings.WINDOW_H * 0.2)
    pygame.draw.rect(display, overlays._lighten(settings.BEYOND, 0.4),
                     (0, 0, settings.WINDOW_W, max(horizon, 0)))

    half_w, band, z0 = 60.0, 8.0, 20.0
    for i in range(15):
        z_near, z_far = z0 - i * band, z0 - (i + 1) * band
        world = [(-half_w, z_near), (half_w, z_near),
                 (half_w, z_far), (-half_w, z_far)]
        pts = []
        for (x, z) in world:
            p = cam.project(x, z)
            if p is not None:
                pts.append((int(p[0]), int(p[1])))
        if len(pts) >= 3:
            shade = settings.GRASS_IN if i % 2 == 0 else settings.GRASS_IN2
            pygame.draw.polygon(display, pygame.Color(shade), pts)

    guide = [(0.0, 12.0 - s) for s in range(0, 90, 4)]
    hero_render._proj_dots(display, cam, guide, pygame.Color(settings.LINE))


def _render_field_markings(display, cam, state):
    """The 50m arc and goal square around the goal you're kicking at —
    the same geometry render_field / hero_render._render_markings draw
    for the other modes, rotated into kick-space. Reference lines so
    walking the mark around (and the kick itself) reads against the
    real field rather than an abstract practice range."""
    fwd, right = _axes(state)
    cy = settings.FIELD_CY
    gx = settings.GOAL_RIGHT[0]
    r = settings.SCORING_ARC_RADIUS
    line = pygame.Color(settings.LINE)

    arc = hero_render._circle_pts(gx, cy, r, n=32,
                                  a0=math.pi / 2, a1=math.pi * 1.5)
    _proj_world_line(display, cam, state, fwd, right, arc, line, width=2)

    square = [(gx, cy - 4), (gx - 6, cy - 4), (gx - 6, cy + 4), (gx, cy + 4)]
    _proj_world_line(display, cam, state, fwd, right, square, line,
                     width=2, closed=True)


def _goal_drawables(cam, state):
    """The goal you're kicking at, projected into local kick-space —
    mirrors hero_render._post_drawables for one end only, rotated into
    this attempt's coordinate frame instead of the fixed field axes
    every other renderer assumes."""
    fwd, right = _axes(state)
    cy = settings.FIELD_CY
    gx = settings.GOAL_RIGHT[0]
    items = []
    for dy, height in ((-3, 11.0), (3, 11.0), (-7, 7.0), (7, 7.0)):
        lx, lz = _local(state, fwd, right, (gx, cy + dy))
        base = cam.project(lx, lz, 0.0)
        band = cam.project(lx, lz, height * 0.15)
        top = cam.project(lx, lz, height)
        if not (base and band and top):
            continue

        def draw(display, base=base, band=band, top=top):
            w = max(2, int(base[2] * 0.35))
            pygame.draw.line(display, pygame.Color(settings.LINE),
                             (int(band[0]), int(band[1])),
                             (int(top[0]), int(top[1])), w)
            pygame.draw.line(display, pygame.Color(settings.POST_RED),
                             (int(base[0]), int(base[1])),
                             (int(band[0]), int(band[1])), w)
            pygame.draw.circle(display, pygame.Color(settings.BG),
                               (int(top[0]), int(top[1])), max(1, w // 2))

        items.append((base[3], draw))
    return items


def _aim_drawable(cam, state):
    """A small reticle at goal-mouth height, wherever the current aim
    bias currently points — the visual half of GK_ACCURACY's hand-aim
    control (see GoalKickState._update_aim). Only live while the
    accuracy stage is actually asking you to steer it."""
    if state.mode != gks.GK_ACCURACY:
        return None
    fwd, right = _axes(state)
    dist = math.hypot(settings.GOAL_RIGHT[0] - state.mark_pos[0],
                      settings.GOAL_RIGHT[1] - state.mark_pos[1])
    target = mechanics.aim_ray_point(state.mark_pos, fwd, right,
                                     state.aim_bias_deg, dist)
    lx, lz = _local(state, fwd, right, target)
    proj = cam.project(lx, lz, 5.0)     # roughly mid-post height
    if proj is None:
        return None
    sx, sy, scale, depth = proj

    def draw(display, sx=sx, sy=sy, scale=scale):
        s = max(3, int(scale * 0.5))
        col = pygame.Color(settings.YELLOW)
        x, y = int(sx), int(sy)
        pygame.draw.line(display, col, (x - s, y), (x + s, y), 2)
        pygame.draw.line(display, col, (x, y - s), (x, y + s), 2)
        pygame.draw.circle(display, col, (x, y), s + 3, 1)

    return (depth, draw)


# ── Entities ────────────────────────────────────────────────────────

def _entity_drawables(cam, state):
    """The "man on the mark" and the ball, as (depth, draw) pairs."""
    fwd, right = _axes(state)
    items = []
    ticks = pygame.time.get_ticks()
    walk_frame = (ticks // 160) % 2
    sprite_world_h = 4.0 * settings.GOALKICK_SPRITE_SCALE

    # The mark defender: decorative only, nudged toward goal from the
    # ball so the two don't sit on the same pixel.
    dlx, dlz = _local(state, fwd, right, state.mark_defender.pos)
    proj = cam.project(dlx, dlz - 3.0, 0.0)
    if proj is not None:
        sx, sy, scale, depth = proj
        k = sprite_world_h * scale / 12.0
        w, h = max(3, int(7 * k)), max(5, int(12 * k))
        variant = 5   # fixed — a specific, stable-looking "opponent"
        sprite = hero_render._scaled(
            hero_render._player_sprite(settings.RED, False, walk_frame, variant),
            w, h, ("goalkick_defender", walk_frame, variant))
        w, h = sprite.get_size()
        shadow = hero_render._soft_ellipse_shadow(max(4, int(w * 1.1)),
                                                  max(2, int(w * 0.4)))

        def draw_defender(display, sx=sx, sy=sy, sprite=sprite,
                          shadow=shadow, w=w, h=h):
            display.blit(shadow, (int(sx) - shadow.get_width() // 2,
                                  int(sy) - shadow.get_height() // 2))
            display.blit(sprite, (int(sx) - w // 2, int(sy) - h))

        items.append((depth, draw_defender))

    # The ball: resting at the mark, or arcing through its flight.
    ball = state.ball
    lift = (hero_render._flight_lift(ball.flight_progress, ball.flight_distance)
            if ball.in_flight else 0.0)
    blx, blz = _local(state, fwd, right, ball.pos)
    proj = cam.project(blx, blz, lift + 0.5)
    ground = cam.project(blx, blz, 0.0)
    if proj is not None:
        sx, sy, scale, depth = proj
        w = max(3, int(scale * 0.9))
        img = hero_render._scaled(hero_render._ball(), w,
                                  max(2, int(w * 0.66)), "ball")

        def draw_ball(display, sx=sx, sy=sy, img=img, ground=ground,
                      lift=lift, scale=scale):
            if ground is not None and lift > 0.5:
                sh = hero_render._soft_ellipse_shadow(max(4, int(scale * 0.9)),
                                                      max(2, int(scale * 0.35)))
                display.blit(sh, (int(ground[0]) - sh.get_width() // 2,
                                  int(ground[1]) - sh.get_height() // 2))
            display.blit(img, (int(sx) - img.get_width() // 2,
                               int(sy) - img.get_height() // 2))

        items.append((depth - 0.5, draw_ball))
    return items


# ── Meters, wind, HUD ─────────────────────────────────────────────────

def _render_meters(display, state):
    """The active timing bar: a moving marker, and (power only) a gold
    sweet-spot tick. The accuracy bar's centre tick is just a neutral
    "no wobble" reference now — aiming itself is the reticle plus
    arrow-key steering (see _aim_drawable), this bar only adds
    timing-precision noise around wherever that's pointed."""
    charcoal = pygame.Color(settings.UI_CHARCOAL)
    ink = pygame.Color(settings.INK)
    cream = pygame.Color(settings.CREAM)
    gold = pygame.Color(settings.YELLOW)
    muted = pygame.Color(_MUTED)

    def bar(label, marker_frac, tick_frac, tick_color):
        rect = pygame.Rect(0, 0, 360, 22)
        rect.midtop = (settings.WINDOW_W // 2, settings.WINDOW_H - 130)
        pygame.draw.rect(display, charcoal, rect)
        pygame.draw.rect(display, ink, rect, 2)
        if tick_frac is not None:
            tx = rect.x + int(tick_frac * rect.w)
            pygame.draw.rect(display, tick_color, (tx - 2, rect.y, 4, rect.h))
        mx = rect.x + int(max(0.0, min(1.0, marker_frac)) * rect.w)
        pygame.draw.rect(display, cream, (mx - 2, rect.y - 5, 4, rect.h + 10))
        tag = hero_render._text("s", label, cream)
        display.blit(tag, (rect.centerx - tag.get_width() // 2, rect.y - 20))

    if state.mode == gks.GK_POWER:
        bar("POWER", state.meter_value, state.ideal_power_t, gold)
    elif state.mode == gks.GK_ACCURACY:
        bar("TIMING", state.meter_value, 0.5, muted)


def _render_wind(display, state):
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color(_MUTED)
    charcoal = pygame.Color(settings.UI_CHARCOAL)
    ink = pygame.Color(settings.INK)

    label = hero_render._text("s", "WIND", muted)
    arrow = "→" if state.wind >= 0 else "←"
    value = hero_render._text("f", f"{arrow} {abs(state.wind):4.1f}", cream)
    w = max(label.get_width(), value.get_width()) + 28
    chip = pygame.Rect(0, 24, w, 52)
    chip.right = settings.WINDOW_W - 24
    pygame.draw.rect(display, charcoal, chip)
    pygame.draw.rect(display, ink, chip, 2)
    display.blit(label, (chip.x + 14, chip.y + 8))
    display.blit(value, (chip.x + 14, chip.y + 26))


def _render_hud(display, state):
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color(_MUTED)
    charcoal = pygame.Color(settings.UI_CHARCOAL)
    ink = pygame.Color(settings.INK)

    _render_wind(display, state)

    t = state.tally
    tally = hero_render._text(
        "s", f"GOALS {t['goals']:02d}  BEHINDS {t['behinds']:02d}  "
             f"MISSES {t['misses']:02d}", cream)
    chip = pygame.Rect(24, 24, tally.get_width() + 28, 36)
    pygame.draw.rect(display, charcoal, chip)
    pygame.draw.rect(display, ink, chip, 2)
    display.blit(tally, (chip.x + 14, chip.y + 8))

    if not state.show_menu:
        hint_text = {
            gks.GK_POSITION: "ARROWS WALK THE MARK  ·  SPACE TO KICK FROM HERE",
            gks.GK_POWER: "SPACE — LOCK YOUR POWER",
            gks.GK_ACCURACY: "ARROWS STEER YOUR AIM  ·  SPACE — LOCK YOUR TIMING",
            gks.GK_RESULT: "SPACE — KICK AGAIN  ·  ESC MENU",
        }.get(state.mode)
        if hint_text:
            hint = hero_render._text("s", hint_text, cream)
            rect = pygame.Rect(0, 0, hint.get_width() + 32, 34)
            rect.center = (settings.WINDOW_W // 2, settings.WINDOW_H - 40)
            pygame.draw.rect(display, charcoal, rect)
            pygame.draw.rect(display, ink, rect, 2)
            display.blit(hint, (rect.x + 16, rect.y + 7))

        controls = hero_render._text("s", "M · CONTROLS", cream)
        chip = pygame.Rect(24, settings.WINDOW_H - 56,
                           controls.get_width() + 28, 32)
        pygame.draw.rect(display, charcoal, chip)
        pygame.draw.rect(display, ink, chip, 2)
        display.blit(controls, (chip.x + 14, chip.y + 8))

    if state.message:
        text = hero_render._text("f", state.message, cream)
        rect = pygame.Rect(0, 0, text.get_width() + 32, 40)
        rect.center = (settings.WINDOW_W // 2, settings.WINDOW_H // 2 - 140)
        pygame.draw.rect(display, charcoal, rect)
        pygame.draw.rect(display, ink, rect, 3)
        display.blit(text, (rect.x + 16, rect.y + 9))


def _render_controls(display):
    """Controls overlay: dims the paused range, lists the bindings."""
    font, font_small, font_big = overlays._fonts()
    display.blit(overlays._dim(160), (0, 0))

    box = pygame.Rect(0, 0, 540, 300)
    box.center = (settings.WINDOW_W // 2, settings.WINDOW_H // 2)
    shadow = overlays._soft_shadow(box.w, box.h)
    display.blit(shadow, (box.x - (shadow.get_width() - box.w) // 2,
                          box.y - (shadow.get_height() - box.h) // 2 + 6))
    pygame.draw.rect(display, pygame.Color(settings.UI_CHARCOAL), box)
    pygame.draw.rect(display, pygame.Color(settings.INK), box, 3)

    title = font_big.render("CONTROLS", True, pygame.Color(settings.CREAM))
    display.blit(title, (box.centerx - title.get_width() // 2, box.y + 22))

    rows = (("ARROWS / WASD", "WALK THE MARK  ·  STEER YOUR AIM"),
            ("SPACE / ENTER", "CONFIRM MARK  ·  LOCK THE METER"),
            ("ESC", "CANCEL ATTEMPT / MENU"),
            ("M", "OPEN · CLOSE MENU"))
    muted = pygame.Color(_MUTED)
    for i, (key, action) in enumerate(rows):
        y = box.y + 76 + i * 38
        display.blit(font.render(key, True, pygame.Color(settings.YELLOW)),
                     (box.x + 36, y))
        display.blit(font.render(action, True, muted), (box.x + 230, y))

    footer = font_small.render(
        "READ THE WIND, STEER YOUR AIM, THEN TIME YOUR STRIKE  ·  GAME PAUSED",
        True, muted)
    display.blit(footer, (box.centerx - footer.get_width() // 2,
                          box.bottom - 40))


# ── Master compose ──────────────────────────────────────────────────

def render_goalkick(display, state):
    """One GOAL KICKING frame: kick-space diorama, meters, HUD."""
    cam = state.camera

    _render_ground(display, cam)
    _render_field_markings(display, cam, state)

    drawables = _goal_drawables(cam, state) + _entity_drawables(cam, state)
    aim = _aim_drawable(cam, state)
    if aim is not None:
        drawables.append(aim)
    drawables.sort(key=lambda item: -item[0])
    for _, draw in drawables:
        draw(display)

    display.blit(overlays._haze(), (0, 0))

    if state.in_meter:
        _render_meters(display, state)
    _render_hud(display, state)
    display.blit(overlays._build_vignette(), (0, 0))
    overlays._render_flash(display, state)

    if state.show_menu:
        _render_controls(display)

"""field_render.py — diorama presentation for FULL GAME and SCENARIOS.

The two classic modes now share AFL Hero's look: the same pastel
field-level scene, projected through GameState's own HeroCamera, with
the same billboarded chibi sprites. Mechanics and keyboard controls are
untouched — this module only draws.

It reuses hero_render's cached scene and sprite helpers (read-only) and
render.py's screen-space overlays (slow-mo, flash, end screen, controls
menu), leaving all AFL Hero code unaltered. Never mutates game state.
"""

import pygame

import hero_render
import render as overlays          # aliased: this module defines render()
import settings
from game_state import MODE_AIMING_KICK, PHASE_END


# ── Entities ────────────────────────────────────────────────────────

def _entity_drawables(cam, gs):
    """GameState's players and ball as (depth, draw) pairs.

    Mirrors hero_render's billboard treatment: feet anchored to the
    projected ground point, grounded soft shadows, idle bob, and the
    hover arrow over the carrier.
    """
    items = []
    ticks = pygame.time.get_ticks()
    walk_frame = (ticks // 160) % 2
    # FULL GAME / SCENARIOS get their own sprite-scale knob (see
    # settings.MAIN_SPRITE_SCALE) instead of sharing Hero mode's — up to
    # 36 bodies on screen at once reads as a mush of overlapping
    # guernseys at Hero's size, so this mode's sprites run a bit smaller.
    sprite_world_h = 4.0 * settings.MAIN_SPRITE_SCALE

    for idx, p in enumerate(gs.players):
        proj = cam.project(p.x, p.y, 0.0)
        if proj is None:
            continue
        sx, sy, scale, depth = proj
        k = sprite_world_h * scale / 12.0
        walking = gs.carrier_moving and p.is_ball_carrier
        bob = 0 if walking else int(k) * (((ticks // 600) + idx) % 2)
        variant = idx % overlays.SPRITE_VARIANTS
        sprite = hero_render._scaled(
            hero_render._player_sprite(p.team, walking, walk_frame, variant),
            max(3, int(7 * k)), max(5, int(12 * k)),
            ("player", p.team, walking, walk_frame, variant))
        w, h = sprite.get_size()
        shadow = hero_render._soft_ellipse_shadow(max(4, int(w * 1.1)),
                                                  max(2, int(w * 0.4)))
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
    ball = gs.ball
    lift = (hero_render._flight_lift(ball.flight_progress,
                                     ball.flight_distance)
            if ball.in_flight else 0.0)
    bx, bz = ball.x, ball.y
    if ball.possessed_by is not None:
        bx += 1.0
    proj = cam.project(bx, bz, lift + 0.6)
    ground = cam.project(bx, bz, 0.0)
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


# ── Aiming overlay ──────────────────────────────────────────────────

def _render_aim(display, cam, gs):
    """Kick-aiming layer: option rings, dotted aim line, target cross."""
    carrier = gs.carrier
    if carrier is None:
        return
    line = pygame.Color(settings.LINE)

    for t in gs.teammates:
        if t is carrier:
            continue
        if t.distance_to(carrier.pos) <= settings.KICK_MAX_RANGE:
            hero_render._proj_line(display, cam,
                                   hero_render._circle_pts(t.x, t.y, 2.6, n=18),
                                   line, width=2)

    aim = gs.aim_point
    if aim is None:
        return
    dx, dz = aim[0] - carrier.x, aim[1] - carrier.y
    dist = max((dx * dx + dz * dz) ** 0.5, 0.001)
    n = max(int(dist // 3), 1)
    hero_render._proj_dots(display, cam,
                           [(carrier.x + dx * i / n, carrier.y + dz * i / n)
                            for i in range(1, n + 1)], line)
    p = cam.project(aim[0], aim[1])
    if p is not None:
        x, y = int(p[0]), int(p[1])
        pygame.draw.line(display, line, (x - 5, y), (x + 5, y), 2)
        pygame.draw.line(display, line, (x, y - 3), (x, y + 3), 2)


# ── HUD ─────────────────────────────────────────────────────────────

def _render_hud(display, gs):
    """Hero-style charcoal chips: score & clock, mission, hints, warnings."""
    cream = pygame.Color(settings.CREAM)
    muted = pygame.Color("#b3ac97")
    charcoal = pygame.Color(settings.UI_CHARCOAL)
    ink = pygame.Color(settings.INK)

    # Score & clock chip, top left. SCENARIOS carry their own match
    # context (levels.py's home_score_start/away_score_start/quarter) so
    # a mission reads as a specific broadcast situation rather than a
    # generic puzzle — AWAY stays fixed (this engine has no opposing-
    # scoring mechanic; see levels.py's "comeback" objective note) while
    # HOME climbs from its starting score as you actually score.
    if gs.game_mode == "scenario" and gs.scenario is not None:
        home_disp = gs.scenario.get("home_score_start", 0) + gs.yellow_points
        away_disp = gs.scenario.get("away_score_start", 0)
        clock_label = gs.scenario.get("quarter", "TIME")
    else:
        home_disp = gs.yellow_points
        away_disp = 0
        clock_label = "Q1"
    score = hero_render._text(
        "s", f"HOME {home_disp:02d}  AWAY {away_disp:02d}", cream)
    m, s = divmod(int(gs.timer), 60)
    urgent = gs.game_mode == "scenario" and gs.timer < 10
    clock = hero_render._text(
        "s", f"{clock_label}  {m:01d}:{s:02d}",
        pygame.Color(settings.ACCENT_RED) if urgent else muted)
    w = max(score.get_width(), clock.get_width()) + 28
    chip = pygame.Rect(24, 24, w, 52)
    pygame.draw.rect(display, charcoal, chip)
    pygame.draw.rect(display, ink, chip, 2)
    display.blit(score, (chip.x + 14, chip.y + 8))
    display.blit(clock, (chip.x + 14, chip.y + 28))

    # Mission chip, top center (scenario mode only) — name, then the
    # quarter folded into the tagline line so the context is visible for
    # the whole scenario, not just the intro briefing message.
    if gs.game_mode == "scenario" and gs.scenario is not None:
        name = hero_render._text("s", gs.scenario["name"], cream)
        tag_text = f"{gs.scenario.get('quarter', '')} · {gs.scenario['tagline']}".strip(" ·")
        tag = hero_render._text("s", tag_text, muted)
        w = max(name.get_width(), tag.get_width()) + 28
        chip = pygame.Rect(0, 0, w, 52)
        chip.midtop = (settings.WINDOW_W // 2, 20)
        pygame.draw.rect(display, charcoal, chip)
        pygame.draw.rect(display, ink, chip, 2)
        display.blit(name, (chip.centerx - name.get_width() // 2, chip.y + 8))
        display.blit(tag, (chip.centerx - tag.get_width() // 2, chip.y + 28))

    # Controls hint chip, bottom left.
    if not gs.show_menu:
        hint = hero_render._text("s", "M · CONTROLS", cream)
        chip = pygame.Rect(24, settings.WINDOW_H - 56,
                           hint.get_width() + 28, 32)
        pygame.draw.rect(display, charcoal, chip)
        pygame.draw.rect(display, ink, chip, 2)
        display.blit(hint, (chip.x + 14, chip.y + 8))

    # Pressure bar above the carrier while lining up a kick.
    carrier = gs.carrier
    if carrier is not None and gs.mode == MODE_AIMING_KICK:
        p = gs.camera.project(carrier.x, carrier.y, 0.0)
        if p is not None:
            bar = pygame.Rect(int(p[0]) - 30, int(p[1]) - 110, 60, 10)
            pygame.draw.rect(display, cream, bar)
            fill = int((bar.w - 4) * gs.pressure)
            pygame.draw.rect(display, pygame.Color(settings.ACCENT_RED),
                             (bar.x + 2, bar.y + 2, fill, bar.h - 4))
            pygame.draw.rect(display, ink, bar, 2)

    # Bounce warning below the carrier when overdue.
    if carrier is not None and gs.must_bounce and not gs.game_over:
        p = gs.camera.project(carrier.x, carrier.y, 0.0)
        if p is not None:
            warn = hero_render._text("s", "BOUNCE!",
                                     pygame.Color(settings.ACCENT_RED))
            display.blit(warn, (int(p[0]) - warn.get_width() // 2,
                                int(p[1]) + 16))

    # Event message plate, bottom center.
    if gs.message:
        text = hero_render._text("f", gs.message, cream)
        rect = pygame.Rect(0, 0, text.get_width() + 32, 40)
        rect.center = (settings.WINDOW_W // 2, settings.WINDOW_H - 100)
        pygame.draw.rect(display, charcoal, rect)
        pygame.draw.rect(display, ink, rect, 3)
        display.blit(text, (rect.x + 16, rect.y + 9))


# ── Master compose ──────────────────────────────────────────────────

def render(display, gs):
    """One FULL GAME / SCENARIOS frame in the shared diorama style."""
    cam = gs.camera

    hero_render._render_ground(display, cam)
    hero_render._render_markings(display, cam)

    if gs.mode == MODE_AIMING_KICK and not gs.show_menu:
        _render_aim(display, cam, gs)

    drawables = hero_render._post_drawables(cam) + _entity_drawables(cam, gs)
    drawables.sort(key=lambda item: -item[0])
    for _, draw in drawables:
        draw(display)

    display.blit(overlays._haze(), (0, 0))
    if gs.in_slowmo:
        display.blit(overlays._slowmo(), (0, 0))

    _render_hud(display, gs)
    display.blit(overlays._build_vignette(), (0, 0))
    overlays._render_flash(display, gs)

    if gs.phase == PHASE_END:
        overlays._render_end(display, gs)
    elif gs.show_menu:
        overlays._render_menu(display)

"""formations.py — FULL GAME's programmatic kickoff layout.

Pure data and geometry, no GameState coupling — split out of
game_state.py as part of the game_state.py decomposition (see AUDIT.md).
"""

import math

import settings

# ── FULL GAME formation ──────────────────────────────────────────────
# Six standard AFL lines (16 on-field a side — interchange isn't modelled
# yet; trimmed from 18 by dropping one slot each from centre/followers
# below, part of the FULL GAME retune alongside settings.
# FULL_GAME_PLAYER_SPEED / MAIN_SPRITE_SCALE / FIELD_MARGIN_*). Each line
# is a "depth" — 0.0 at a team's own goal, 1.0 at the goal they're
# attacking — plus a tuple of lateral "slots": how far across the ground
# each player sits (-1..1, as a fraction of the oval's local half-width
# at that depth) and a small depth "nudge" so flanks sit in a shallow
# curve rather than a dead-straight rank. Purely a data table — neither
# _line_positions nor _build_team_formation hardcodes a slot count, so a
# designer can retune the whole formation (including its size) by editing
# the numbers below; nothing is randomized.
FORMATION_LINES = (
    # name,            depth,  slots: (lateral fraction, depth nudge)
    ("full_back",     0.06,  ((-0.62,  0.02), (0.0,  0.0), (0.62,  0.02))),
    ("half_back",     0.28,  ((-0.68,  0.02), (0.0,  0.0), (0.68,  0.02))),
    ("centre",        0.50,  ((-0.85,  0.0),  (0.85,  0.0))),
    ("followers",     0.50,  (( 0.06, -0.02), (-0.20, -0.035))),
    ("half_forward",  0.72,  ((-0.68, -0.02), (0.0,  0.0), (0.68, -0.02))),
    ("full_forward",  0.94,  ((-0.62, -0.02), (0.0,  0.0), (0.62, -0.02))),
)


def _line_positions(depth, slots, attack_positive):
    """World (x, y) for one formation line.

    `depth` runs 0 (own goal) -> 1 (attacking goal); a team attacking +x
    (YELLOW) reads it directly, a team attacking -x (RED) mirrors it
    (1 - depth) so both sides face off across the centre with the same
    shape. Lateral fractions are scaled by the oval's local half-width
    at that depth (narrower near the goals than at the centre), with a
    safety inset so nobody generates outside the boundary.
    """
    positions = []
    for lateral_frac, nudge in slots:
        d = depth + nudge
        x_frac = d if attack_positive else 1.0 - d
        x = settings.FIELD_LEFT + x_frac * settings.FIELD_W

        t = max(-0.999, min(0.999, (x - settings.FIELD_CX) / (settings.FIELD_W / 2)))
        half_width = (settings.FIELD_H / 2) * math.sqrt(1.0 - t * t)
        y = settings.FIELD_CY + lateral_frac * half_width * 0.82
        positions.append((x, y))
    return positions


def _build_team_formation(attack_positive):
    """All 16 on-field spots for one team, kickoff carrier first.

    The carrier ends up at index 0 of the returned list because
    GameState._load_layout always hands the ball to players[0] — here
    that's the lead follower (the "rover" slot), standing in for winning
    the imaginary opening centre clearance, rather than a fixed fullback.
    """
    lines = {name: _line_positions(depth, slots, attack_positive)
             for name, depth, slots in FORMATION_LINES}
    carrier, *other_followers = lines["followers"]
    ordered = [carrier] + other_followers
    for name in ("full_back", "half_back", "centre", "half_forward", "full_forward"):
        ordered.extend(lines[name])
    return ordered


def _build_full_game_layout():
    """Programmatic 16-a-side FULL GAME kickoff layout (see
    FORMATION_LINES) — both teams share the same formation shape,
    mirrored front-to-back so they face off across the centre (YELLOW
    attacks +x, RED attacks -x; settings.GOAL_RIGHT / GOAL_LEFT)."""
    return {
        "yellow": _build_team_formation(attack_positive=True),
        "red": _build_team_formation(attack_positive=False),
    }


# Default kickoff layout for full game mode.
FULL_GAME_LAYOUT = _build_full_game_layout()

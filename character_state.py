"""character_state.py — state for the CHARACTER MENU (hotkey K_c).

A standalone attributes screen, entirely separate from
game_state.ROOT_OPTIONS/SCREEN_ROOT — see GameState._open_character /
_character_input / _update_character for how it's reached and torn down.
A player stands facing the camera (character_render.py draws the scene);
this module owns the attribute rows, row selection, live value edits, the
fixed portrait camera, and the entry/exit pixel-wipe timer. No drawing,
no game rules — mirrors every other mode's `*_state.py` split.

Two stats are live-adjustable right now: Speed and Height. The other six
are locked placeholders for a future player-attribute/upgrade system —
there's no currency, points, or save file yet, so a direct, immediate
adjustment (no gating) is the right amount of functionality for this
pass. Speed writes straight into this state's own value, which
game_state._update_movement reads in preference to
settings.FULL_GAME_PLAYER_SPEED once a CharacterState exists, so it's
felt next time FULL GAME runs. Height has no real gameplay hook yet, so
character_render.py uses it to scale the preview sprite as a stand-in.
"""

import pygame

import settings
from hero_camera import HeroCamera

# Attribute rows, in on-screen order — two groups per the spec, flattened
# into one list so selection/nudging don't need to know about the
# grouping; character_render.py re-splits them visually using GROUP_1_LEN.
# `key` names the live value on this class for the two adjustable rows;
# locked rows carry `key = None` and are inert (arrow/enter presses no-op),
# the same convention as a locked hero-level/scenario menu entry.
ATTRIBUTE_ROWS = (
    {"key": "speed", "name": "SPEED"},
    {"key": None, "name": "JUMPING"},
    {"key": None, "name": "KICKING POWER"},
    {"key": None, "name": "KICKING ACCURACY"},
    {"key": None, "name": "STRENGTH"},
    {"key": "height", "name": "HEIGHT"},
    {"key": None, "name": "WEIGHT"},
    {"key": None, "name": "KICKING FOOT"},
)
GROUP_1_LEN = 5   # first five rows are group 1; the rest render as group 2


class CharacterState:
    """Live attribute values, row selection, and the portrait camera."""

    def __init__(self):
        self.selected = 0
        self.speed = settings.FULL_GAME_PLAYER_SPEED
        self.height = 1.0   # preview-sprite scale multiplier; see docstring

        self.transition_dir = "in"    # "in" reveals, "out" covers before exit
        self.transition_t = 0.0
        self.pending_exit_phase = None

        # Single fixed framing (see character_render.py) — the camera never
        # moves, but still ticks every frame like every other mode's rig.
        self.camera = HeroCamera(
            (settings.FIELD_CX, settings.FIELD_CY),
            back=settings.CHARACTER_CAM_BACK,
            height=settings.CHARACTER_CAM_HEIGHT,
            focal=settings.CHARACTER_CAM_FOCAL,
            zoom_mult=1.0,
            lerp=settings.CHARACTER_CAM_LERP,
            horizon_y=settings.CHARACTER_HORIZON_Y,
        )

    @property
    def current_row(self):
        return ATTRIBUTE_ROWS[self.selected]

    # ── Input ───────────────────────────────────────────────────────

    def handle_input(self, event):
        """Arrow keys move the selection or nudge the selected row's
        value. Inert while the exit wipe is covering the screen, same as
        a locked row — nothing you press here should still land."""
        if event.type != pygame.KEYDOWN or self.transition_dir == "out":
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(ATTRIBUTE_ROWS)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(ATTRIBUTE_ROWS)
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._nudge(-1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._nudge(1)

    def _nudge(self, direction):
        row = self.current_row
        if row["key"] == "speed":
            self.speed = max(settings.CHARACTER_SPEED_MIN, min(
                settings.CHARACTER_SPEED_MAX,
                self.speed + direction * settings.CHARACTER_SPEED_STEP))
        elif row["key"] == "height":
            self.height = max(settings.CHARACTER_HEIGHT_MIN, min(
                settings.CHARACTER_HEIGHT_MAX,
                self.height + direction * settings.CHARACTER_HEIGHT_STEP))
        # row["key"] is None -> locked row, no-op.

    # ── Transition sequencing ──────────────────────────────────────

    def reset_transition_in(self):
        """Re-entering after a previous visit: play the reveal wipe again
        rather than resuming mid-exit."""
        self.transition_dir = "in"
        self.transition_t = 0.0
        self.pending_exit_phase = None

    def request_exit(self, return_phase):
        """Start the covering half of the wipe. GameState flips the phase
        once `exit_ready` goes true (see game_state._update_character)."""
        if self.transition_dir == "out":
            return
        self.pending_exit_phase = return_phase
        self.transition_dir = "out"
        self.transition_t = 0.0

    @property
    def wipe_progress(self):
        """0..1 how covered the screen currently is: 1.0 fully covered,
        0.0 fully revealed. Entering counts down from covered to
        revealed; exiting counts back up to covered."""
        frac = min(1.0, self.transition_t / settings.CHARACTER_TRANSITION_TIME)
        return (1.0 - frac) if self.transition_dir == "in" else frac

    @property
    def exit_ready(self):
        return (self.transition_dir == "out"
                and self.transition_t >= settings.CHARACTER_TRANSITION_TIME)

    # ── Update ──────────────────────────────────────────────────────

    def update(self, dt):
        if self.transition_t < settings.CHARACTER_TRANSITION_TIME:
            self.transition_t = min(settings.CHARACTER_TRANSITION_TIME,
                                    self.transition_t + dt)
        # Fixed framing (see __init__) — nothing to ease toward, but the
        # camera still rebuilds its per-frame basis like every other rig.
        self.camera.update(dt, (settings.FIELD_CX, settings.FIELD_CY), False)

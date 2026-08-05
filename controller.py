"""controller.py — Xbox (XInput-style) controller support.

Built on pygame's SDL_GameController wrapper (`pygame._sdl2.controller`),
not the raw `pygame.joystick` axis/button-index API an earlier version
of this file used. The raw joystick API reports axes and buttons in
whatever order the driver happens to expose them — and that order
genuinely varies. An Xbox controller wired in, on the official wireless
adapter, or paired over Bluetooth can each enumerate their axes
differently on Windows, so a single hardcoded index scheme — even one
someone confirmed against their own pad — isn't something every
player's setup can rely on. That's what caused both the original
"kick-aim cursor jumps far away" bug and a follow-up "still off / too
far / not calibrated" report even after the index numbers were
corrected for one specific layout: the fix was still guessing.

pygame._sdl2.controller sidesteps the guessing entirely. Every device
SDL recognizes as a game controller (its bundled mapping database
covers essentially every Xbox controller, whatever the connection
type) is exposed through the same fixed set of named axes and buttons —
CONTROLLER_AXIS_LEFTX, CONTROLLER_BUTTON_A, and so on, all defined at
the top-level `pygame` module — so this file never has to guess an
index again, on any pad. If a device *isn't* SDL-recognized (no
mapping — rare, but possible for an obscure third-party pad),
is_controller() returns False and it's silently skipped, same as no
controller at all.

Two ways this feeds into the rest of the game, so no other module needs
to know pygame._sdl2.controller exists:

  1. Discrete actions (menu navigation, confirm/back, bounce, handball,
     the character-menu hotkey, pause, kick-aim enter/confirm) become
     synthetic pygame KEYDOWN events, one per button-press, per D-pad
     flick, or per trigger pull (edge-triggered, exactly like a real
     keypress — not fired every frame a button is held or a trigger
     stays pulled; LT/RT are analog axes, not real buttons, so they get
     their own threshold-crossing edge detection — see _prev_triggers).
     main.py injects these into the same game_state.handle_input() every
     real KEYDOWN already goes through, so every existing `handle_input`
     in this project (GameState, HeroState's own menus, GoalKickState,
     CharacterState) picks them up with zero changes of their own.
  2. Continuous input (the FULL GAME/SCENARIOS carrier, GOAL KICKING's
     mark-walking/aim bias, the kick-aim cursor) is polled every frame
     via direction()/right_stick(), merged into the handful of call
     sites that already poll pygame.key.get_pressed() or the mouse —
     mirrors how a held keyboard key or a moved mouse works.

With no controller connected, every function here returns its neutral
default (no direction, no events) and the rest of the game behaves
exactly as it did before this file existed.
"""

import pygame
from pygame._sdl2 import controller as _sdl

# ── Layout (SDL_GameController's fixed semantic mapping) ──────────────
# Not indices to guess at — SDL resolves whatever the physical device
# actually reports into this same fixed set for any recognized
# controller, so these constants are correct on every Xbox pad without
# per-device tuning.
BTN_A = pygame.CONTROLLER_BUTTON_A
BTN_B = pygame.CONTROLLER_BUTTON_B
BTN_X = pygame.CONTROLLER_BUTTON_X
BTN_Y = pygame.CONTROLLER_BUTTON_Y          # unbound — see _BUTTON_KEYS
BTN_LB = pygame.CONTROLLER_BUTTON_LEFTSHOULDER
BTN_RB = pygame.CONTROLLER_BUTTON_RIGHTSHOULDER
BTN_BACK = pygame.CONTROLLER_BUTTON_BACK
BTN_START = pygame.CONTROLLER_BUTTON_START
BTN_DPAD_UP = pygame.CONTROLLER_BUTTON_DPAD_UP
BTN_DPAD_DOWN = pygame.CONTROLLER_BUTTON_DPAD_DOWN
BTN_DPAD_LEFT = pygame.CONTROLLER_BUTTON_DPAD_LEFT
BTN_DPAD_RIGHT = pygame.CONTROLLER_BUTTON_DPAD_RIGHT

AXIS_LEFT_X = pygame.CONTROLLER_AXIS_LEFTX
AXIS_LEFT_Y = pygame.CONTROLLER_AXIS_LEFTY
AXIS_RIGHT_X = pygame.CONTROLLER_AXIS_RIGHTX
AXIS_RIGHT_Y = pygame.CONTROLLER_AXIS_RIGHTY
AXIS_LEFT_TRIGGER = pygame.CONTROLLER_AXIS_TRIGGERLEFT    # LT
AXIS_RIGHT_TRIGGER = pygame.CONTROLLER_AXIS_TRIGGERRIGHT  # RT

# SDL's raw ranges (see Controller.get_axis in pygame's docs): sticks
# report -32768..32767, triggers report 0..32768 — never negative, no
# more "rests near -1" guesswork like the raw joystick API had.
# Normalize both down to -1.0..1.0 / 0.0..1.0 once, here (_stick_axis /
# _trigger_axis), so everything below this line works in plain floats.
_STICK_MAX = 32767.0
_TRIGGER_MAX = 32768.0

STICK_DEADZONE = 0.35    # magnitude below this counts as centered
AIM_DEADZONE = 0.25      # smaller deadzone for the finer aim cursor
TRIGGER_THRESHOLD = 0.5  # pulled-fraction (0..1) past which a trigger counts as pressed

# Flip True temporarily to print every open controller's normalized
# axis values once per second — mainly useful if a specific third-party
# pad still looks miscalibrated even through SDL's mapping (rare — SDL's
# built-in database covers essentially all Xbox controllers correctly,
# which is the whole reason this file uses pygame._sdl2.controller
# instead of raw pygame.joystick indices). Flip back to False once
# confirmed; this is noisy and not meant to ship on.
DEBUG_AXES = False
_debug_timer = 0.0

# Button -> synthetic KEYDOWN key. A and RB double up on RETURN/SPACE to
# match the keyboard's own redundant confirm bindings (menu select is
# RETURN or SPACE; bounce is 3 or SPACE; GOAL KICKING confirm is SPACE or
# RETURN) so this one table covers every screen with no special-casing.
#
# Y is deliberately unbound: kick-aim entry moved to LT (see
# _TRIGGER_KEYS below) so aiming can be a natural "hold LT, steer with
# the right stick, pull RT to confirm" gesture instead of a face button.
# A still also confirms a kick (via K_RETURN, same as RT) — left in
# place rather than removed since redundant bindings are already this
# project's convention (SPACE/RETURN are doubled up in several places).
_BUTTON_KEYS = {
    BTN_A: pygame.K_RETURN,     # confirm / select / confirm kick target
    BTN_B: pygame.K_ESCAPE,     # back / cancel / pause
    BTN_X: pygame.K_1,          # handball
    BTN_RB: pygame.K_SPACE,     # bounce / confirm
    BTN_LB: pygame.K_c,         # character menu toggle
    BTN_START: pygame.K_m,      # pause / controls overlay
}

# Trigger axis -> synthetic KEYDOWN key. Triggers are analog (see
# AXIS_LEFT_TRIGGER/AXIS_RIGHT_TRIGGER), not digital buttons, so they
# can't use _BUTTON_KEYS/get_button() — poll_events() edge-triggers
# them itself via _prev_triggers, the same one-shot-per-pull idea as
# _prev_buttons. Synthesizing the same keys Y/A used to produce means
# game_state.py and character_state.py need zero further changes.
_TRIGGER_KEYS = {
    AXIS_LEFT_TRIGGER: pygame.K_2,        # LT — enter kick-aim mode
    AXIS_RIGHT_TRIGGER: pygame.K_RETURN,  # RT — confirm the kick
}

# D-pad -> (dx, dy) in the same "+1 is down" convention keyboard/stick
# input already uses (see direction()). Read as four buttons, not a
# hat switch — SDL maps every recognized controller's D-pad onto these
# regardless of whether the underlying device reports it as a hat or
# discrete buttons, so there's no hat-sign convention left to assume.
_DPAD = {
    BTN_DPAD_LEFT: (-1, 0),
    BTN_DPAD_RIGHT: (1, 0),
    BTN_DPAD_UP: (0, -1),
    BTN_DPAD_DOWN: (0, 1),
}

_controllers = {}         # id -> pygame._sdl2.controller.Controller
_prev_buttons = {}        # button constant -> bool, for edge-triggering
_prev_triggers = {}       # trigger axis constant -> bool, for edge-triggering
_prev_direction = (0, 0)  # last discretized D-pad+stick direction


def init():
    """Open every controller already connected. Safe to call once at
    startup; controllers plugged in later are picked up by
    handle_device_event via pygame's CONTROLLERDEVICEADDED event."""
    pygame.joystick.init()  # SDL_GameController relies on this subsystem
    _sdl.init()
    for i in range(_sdl.get_count()):
        _open(i)
    if not _controllers:
        print("[controller] none detected — keyboard/mouse only "
             "(plugging one in later still works)")


def _open(index):
    if not _sdl.is_controller(index):
        return   # a joystick-class device SDL has no controller mapping for
    try:
        c = _sdl.Controller(index)
    except pygame.error:
        return
    _controllers[c.id] = c
    print(f"[controller] connected: {c.name}")


def handle_device_event(event):
    """Call for every pygame event — picks up CONTROLLERDEVICEADDED/
    REMOVED so connecting or disconnecting a controller mid-session just
    works."""
    if event.type == pygame.CONTROLLERDEVICEADDED:
        _open(event.device_index)
    elif event.type == pygame.CONTROLLERDEVICEREMOVED:
        _controllers.pop(event.instance_id, None)


def _active_controller():
    return next(iter(_controllers.values()), None)


def is_connected():
    """True while at least one controller is open — for controls overlays
    (render.py / hero_render.py / goalkick_render.py) that want to show
    Xbox bindings alongside the keyboard ones. Live: reflects hot-plug
    state frame to frame, since _open/handle_device_event mutate
    _controllers directly."""
    return bool(_controllers)


def _stick_axis(c, axis, deadzone):
    v = max(-1.0, min(1.0, c.get_axis(axis) / _STICK_MAX))
    return v if abs(v) > deadzone else 0.0


def _trigger_axis(c, axis):
    return max(0.0, min(1.0, c.get_axis(axis) / _TRIGGER_MAX))


def direction():
    """(dx, dy) in {-1, 0, 1}, D-pad and left stick merged — matches the
    existing WASD/arrow-key convention exactly (dy: +1 is down), ready to
    OR straight into a pygame.key.get_pressed() dx/dy read. (0, 0) with
    no controller connected."""
    c = _active_controller()
    if c is None:
        return (0, 0)
    hx = hy = 0
    for button, (bx, by) in _DPAD.items():
        if c.get_button(button):
            hx, hy = hx or bx, hy or by
    lx = _stick_axis(c, AXIS_LEFT_X, STICK_DEADZONE)
    ly = _stick_axis(c, AXIS_LEFT_Y, STICK_DEADZONE)
    dx = hx if hx else (1 if lx > 0 else -1 if lx < 0 else 0)
    dy = hy if hy else (1 if ly > 0 else -1 if ly < 0 else 0)
    return (dx, dy)


def right_stick():
    """Raw (-1..1, -1..1) right-stick deflection for the kick-aim cursor
    (see GameState.update) — a smaller deadzone than direction() since
    it's steering a cursor smoothly, not picking a discrete direction.
    Already screen-space-aligned (push up -> negative -> cursor moves
    up), so callers can add this straight onto a screen position."""
    c = _active_controller()
    if c is None:
        return (0.0, 0.0)
    return (_stick_axis(c, AXIS_RIGHT_X, AIM_DEADZONE),
           _stick_axis(c, AXIS_RIGHT_Y, AIM_DEADZONE))


def poll_events():
    """Synthetic pygame KEYDOWN events for this frame: newly-pressed
    buttons, freshly-pulled triggers, plus an edge-triggered D-pad/stick
    direction change (one event per press/pull/flick, like a real
    keypress — not one per frame held), so every existing menu's
    up/down/left/right/confirm/back handling works unchanged. Call once
    per frame after pygame.event.get()."""
    global _prev_direction, _debug_timer
    events = []
    c = _active_controller()
    if c is None:
        return events

    if DEBUG_AXES:
        now = pygame.time.get_ticks()
        if now - _debug_timer > 1000:
            _debug_timer = now
            print(f"[controller] LX={_stick_axis(c, AXIS_LEFT_X, 0):+.2f} "
                 f"LY={_stick_axis(c, AXIS_LEFT_Y, 0):+.2f} "
                 f"RX={_stick_axis(c, AXIS_RIGHT_X, 0):+.2f} "
                 f"RY={_stick_axis(c, AXIS_RIGHT_Y, 0):+.2f} "
                 f"LT={_trigger_axis(c, AXIS_LEFT_TRIGGER):.2f} "
                 f"RT={_trigger_axis(c, AXIS_RIGHT_TRIGGER):.2f}")

    for button, key in _BUTTON_KEYS.items():
        pressed = bool(c.get_button(button))
        if pressed and not _prev_buttons.get(button, False):
            events.append(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
        _prev_buttons[button] = pressed

    for axis, key in _TRIGGER_KEYS.items():
        pulled = _trigger_axis(c, axis) > TRIGGER_THRESHOLD
        if pulled and not _prev_triggers.get(axis, False):
            events.append(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
        _prev_triggers[axis] = pulled

    dx, dy = direction()
    if (dx, dy) != _prev_direction:
        if dx == -1:
            events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT, mod=0))
        elif dx == 1:
            events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0))
        if dy == -1:
            events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, mod=0))
        elif dy == 1:
            events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN, mod=0))
    _prev_direction = (dx, dy)
    return events

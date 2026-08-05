"""character_state.py — state for the CHARACTER MENU (hotkey K_c).

A standalone attributes screen, entirely separate from
game_state.ROOT_OPTIONS/SCREEN_ROOT — see GameState._open_character /
_character_input / _update_character for how it's reached and torn down.
character_render.py draws whatever `self.screen` currently is; this
module owns all of it: attribute rows, row selection, live value edits,
the fixed portrait camera, the roster of saved players, and the
entry/exit pixel-wipe timer.

Two stats are live-adjustable right now: Speed and Height. The other six
are locked placeholders for a future player-attribute/upgrade system.
Edits are a draft (self.speed/self.height) until the SAVE row commits
them — either to the ALL PLAYERS default that FULL GAME actually reads
(game_state._update_movement), or to a specific saved player's record —
and only then, via a disk/session prompt, decides whether that record
should persist to disk (player_data.py) or just live for this run.

This is the first slice of a future MyPlayer/Ultimate-Team-style roster
(distinct players with distinct attributes assigned to a team) — right
now there's only ever one controllable carrier, so "APPLY TO ALL
PLAYERS" is the only thing that actually changes gameplay; "APPLY TO A
SAVED PLAYER" just builds and persists profiles for that future system.

Screens (self.screen): "attributes" (the main panel) -> "roster" (pick
or start a new saved player) -> "naming" (type a new player's name), and
"attributes" -> "save_prompt" (disk vs session) as a short modal detour.
"""

import pygame

import player_data
import settings
from hero_camera import HeroCamera

# The 8 fixed attribute rows, in on-screen order — two groups per the
# original spec, flattened into one list so up/down doesn't need to know
# about the grouping; character_render.py re-splits them using
# GROUP_1_LEN. `key` names the live value on this class for the two
# adjustable rows; locked rows carry `key = None` and are inert.
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

# Sentinels for the two non-player entries on the roster screen (kept out
# of the player dicts themselves so nothing stray ever leaks into a saved
# player's JSON record).
ROSTER_NEW = "__new__"
ROSTER_BACK = "__back__"


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


class CharacterState:
    """Live attribute values, the saved-player roster, screen/selection
    state, and the portrait camera."""

    def __init__(self):
        default, saved_players = player_data.load()

        self.applied_speed = settings.FULL_GAME_PLAYER_SPEED
        self.applied_height = settings.CHARACTER_HEIGHT_BASELINE_CM
        if default:
            self.applied_speed = _clamp(
                default.get("speed", self.applied_speed),
                settings.CHARACTER_SPEED_MIN, settings.CHARACTER_SPEED_MAX)
            self.applied_height = _clamp(
                default.get("height", self.applied_height),
                settings.CHARACTER_HEIGHT_MIN, settings.CHARACTER_HEIGHT_MAX)

        self._next_id = 0
        self.roster = []
        for p in saved_players:
            pid = p.get("id")
            if not isinstance(pid, int):
                pid = self._next_id + 1
            self._next_id = max(self._next_id, pid)
            self.roster.append({
                "id": pid,
                "name": str(p.get("name", "PLAYER"))[:18],
                "speed": _clamp(p.get("speed", self.applied_speed),
                                settings.CHARACTER_SPEED_MIN, settings.CHARACTER_SPEED_MAX),
                "height": _clamp(p.get("height", self.applied_height),
                                 settings.CHARACTER_HEIGHT_MIN, settings.CHARACTER_HEIGHT_MAX),
                "persisted": True,
            })

        self.screen = "attributes"
        self.selected = 0
        self.apply_all = True
        self.roster_selected_id = None
        self.speed = self.applied_speed     # the draft being edited right now
        self.height = self.applied_height
        self.name_draft = ""
        self.save_choice = 0                # 0 = disk, 1 = session (save_prompt screen)

        self.message = ""
        self.message_timer = 0.0

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

    # ── Row lists (character_render.py reads these too) ─────────────

    def attribute_screen_rows(self):
        """The main panel's rows: the 8 stat rows, the apply-mode toggle,
        the saved-player picker (only while apply_all is off), and the
        SAVE action — all one up/down list, same convention as every
        other menu in this project."""
        rows = [dict(row, kind="stat") for row in ATTRIBUTE_ROWS]
        rows.append({"kind": "toggle"})
        if not self.apply_all:
            rows.append({"kind": "picker"})
        rows.append({"kind": "action"})
        return rows

    def roster_rows(self):
        return list(self.roster) + [ROSTER_NEW, ROSTER_BACK]

    def selected_player(self):
        if self.roster_selected_id is None:
            return None
        for p in self.roster:
            if p["id"] == self.roster_selected_id:
                return p
        return None

    # ── Input ───────────────────────────────────────────────────────

    def handle_input(self, event):
        if self.transition_dir == "out":
            return   # inert while the exit wipe is covering the screen
        if self.screen == "attributes":
            self._attributes_input(event)
        elif self.screen == "roster":
            self._roster_input(event)
        elif self.screen == "naming":
            self._naming_input(event)
        elif self.screen == "save_prompt":
            self._save_prompt_input(event)

    def back(self):
        """One step back up the menu tree — called by GameState for ESC
        on any screen except "attributes" (ESC there closes the whole
        menu instead; see game_state._character_input)."""
        if self.screen == "naming":
            pygame.key.stop_text_input()
            self.name_draft = ""
            self.screen = "roster"
        elif self.screen == "roster":
            self.screen = "attributes"
            self.selected = len(ATTRIBUTE_ROWS) + 1   # the SAVED PLAYER row
        elif self.screen == "save_prompt":
            self.screen = "attributes"

    def _attributes_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        rows = self.attribute_screen_rows()
        if event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(rows)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(rows)
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._activate(rows[self.selected], -1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._activate(rows[self.selected], 1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._activate(rows[self.selected], 0)

    def _activate(self, row, direction):
        kind = row["kind"]
        if kind == "stat":
            if direction != 0:
                self._nudge(row, direction)
        elif kind == "toggle":
            self._toggle_apply_all()
        elif kind == "picker":
            self.selected = 0
            self.screen = "roster"
        elif kind == "action":
            self._begin_save()

    def _nudge(self, row, direction):
        if row["key"] == "speed":
            self.speed = _clamp(
                self.speed + direction * settings.CHARACTER_SPEED_STEP,
                settings.CHARACTER_SPEED_MIN, settings.CHARACTER_SPEED_MAX)
        elif row["key"] == "height":
            self.height = _clamp(
                self.height + direction * settings.CHARACTER_HEIGHT_STEP,
                settings.CHARACTER_HEIGHT_MIN, settings.CHARACTER_HEIGHT_MAX)

    def _toggle_apply_all(self):
        self.apply_all = not self.apply_all
        if self.apply_all:
            self.speed = self.applied_speed
            self.height = self.applied_height
        else:
            player = self.selected_player()
            if player is not None:
                self.speed = player["speed"]
                self.height = player["height"]
            # else: no player selected yet — keep the current draft as the
            # starting point for whichever player gets created/picked next.

    def _begin_save(self):
        if not self.apply_all and self.selected_player() is None:
            self._show_message("SELECT OR CREATE A PLAYER FIRST")
            return
        self.save_choice = 0
        self.screen = "save_prompt"

    def _roster_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        rows = self.roster_rows()
        if event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(rows)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(rows)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            item = rows[self.selected]
            if item == ROSTER_BACK:
                self.screen = "attributes"
            elif item == ROSTER_NEW:
                self.name_draft = ""
                self.screen = "naming"
                pygame.key.start_text_input()
            else:
                self._select_player(item)

    def _select_player(self, player):
        self.roster_selected_id = player["id"]
        self.speed = player["speed"]
        self.height = player["height"]
        self.screen = "attributes"
        self.selected = len(ATTRIBUTE_ROWS) + 1   # the SAVED PLAYER row

    def _naming_input(self, event):
        if event.type == pygame.TEXTINPUT:
            if len(self.name_draft) < 18:
                self.name_draft += event.text.upper()
            return
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_BACKSPACE:
            self.name_draft = self.name_draft[:-1]
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            name = self.name_draft.strip() or f"PLAYER {len(self.roster) + 1}"
            pygame.key.stop_text_input()
            self._create_player(name)

    def _create_player(self, name):
        self._next_id += 1
        self.roster.append({
            "id": self._next_id, "name": name[:18],
            "speed": self.speed, "height": self.height, "persisted": False,
        })
        self.roster_selected_id = self._next_id
        self.name_draft = ""
        self.screen = "attributes"
        self.selected = len(ATTRIBUTE_ROWS) + 1   # the SAVED PLAYER row

    def _save_prompt_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT,
                         pygame.K_w, pygame.K_s, pygame.K_a, pygame.K_d):
            self.save_choice = 1 - self.save_choice
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._commit_save(persist_to_disk=(self.save_choice == 0))

    def _disk_roster(self):
        """Player records due to be written to disk: everyone already
        persisted, stripped of the in-memory-only `persisted` flag."""
        return [{"id": p["id"], "name": p["name"],
                "speed": p["speed"], "height": p["height"]}
                for p in self.roster if p.get("persisted")]

    def _commit_save(self, persist_to_disk):
        if self.apply_all:
            self.applied_speed = self.speed
            self.applied_height = self.height
            if persist_to_disk:
                player_data.save({"speed": self.applied_speed,
                                  "height": self.applied_height},
                                 self._disk_roster())
            self._show_message("DEFAULT SAVED TO DISK" if persist_to_disk
                               else "DEFAULT SAVED (THIS SESSION)")
        else:
            player = self.selected_player()
            if player is None:
                self._show_message("SELECT OR CREATE A PLAYER FIRST")
                self.screen = "attributes"
                return
            player["speed"] = self.speed
            player["height"] = self.height
            if persist_to_disk:
                player["persisted"] = True
                player_data.save({"speed": self.applied_speed,
                                  "height": self.applied_height},
                                 self._disk_roster())
            self._show_message(f"{player['name']} SAVED TO DISK" if persist_to_disk
                               else f"{player['name']} SAVED (THIS SESSION)")
        self.screen = "attributes"

    def _show_message(self, text):
        self.message = text
        self.message_timer = 2.5

    # ── Transition sequencing ──────────────────────────────────────

    def reset_transition_in(self):
        """Re-entering after a previous visit: play the reveal wipe
        again and land back on the main attributes panel."""
        self.transition_dir = "in"
        self.transition_t = 0.0
        self.pending_exit_phase = None
        self.screen = "attributes"

    def request_exit(self, return_phase):
        """Start the covering half of the wipe. GameState flips the phase
        once `exit_ready` goes true (see game_state._update_character)."""
        if self.transition_dir == "out":
            return
        if self.screen == "naming":
            pygame.key.stop_text_input()
        self.screen = "attributes"
        self.name_draft = ""
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
        if self.message_timer > 0.0:
            self.message_timer -= dt
            if self.message_timer <= 0.0:
                self.message = ""
        # Fixed framing (see __init__) — nothing to ease toward, but the
        # camera still rebuilds its per-frame basis like every other rig.
        self.camera.update(dt, (settings.FIELD_CX, settings.FIELD_CY), False)

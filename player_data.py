"""player_data.py — CHARACTER MENU roster persistence.

The only module in this project that touches the filesystem. Every
saved player is session-only by default (see character_state.py) — a
player (or the ALL PLAYERS default) only reaches disk when the SAVE
flow's disk/session prompt is answered "disk", at which point the whole
roster of *disk-saved* players plus the current default round-trip
through one small JSON file next to this module. Session-only players
never touch this file.
"""

import json
import os

_SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "player_saves.json")


def load():
    """Everything persisted on disk: (all_players_default dict or None,
    list of saved player dicts). Never raises — a missing or corrupt
    save file just means nobody has saved to disk yet, same as a fresh
    install."""
    if not os.path.exists(_SAVE_PATH):
        return None, []
    try:
        with open(_SAVE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None, []
    return data.get("all_players_default"), data.get("players", [])


def save(all_players_default, players):
    """Overwrite the save file with the given default + player list.
    Callers only ever pass players the user chose to persist (see
    character_state.CharacterState._disk_roster) — session-only players
    are filtered out before this is called."""
    data = {"all_players_default": all_players_default, "players": players}
    try:
        with open(_SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass   # best-effort — a failed write shouldn't crash the menu

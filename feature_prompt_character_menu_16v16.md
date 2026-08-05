# Feature prompt: FULL GAME retuning + character customization menu

Paste everything below to a coding agent with access to this repo. It gives full project
context up front so the agent doesn't need to explore blindly, then scopes exactly what to
touch.

---

## 1. What this project is

A Python/Pygame AFL (Aussie Rules) prototype. No engine, no external art — every visual is
procedural pixel art (`pygame.draw` + `set_at`) on a small logical grid (`settings.LOGICAL_W`
x `settings.LOGICAL_H`) upscaled by nearest-neighbor (`settings.SCALE`) to the real window.
Four playable modes share one phase machine in `game_state.py`:

- **FULL GAME** — free-play quarter, 18-a-side, human controls one carrier at a time.
- **SCENARIOS** — hand-designed short missions from `levels.py` (fixed start positions, a
  clock, an objective).
- **AFL HERO** — a swipe-based possession puzzle mode (`hero_state.py`/`hero_render.py`),
  levels defined in `hero_levels.py`.
- **GOAL KICKING** — freeform kicking-for-goal practice range (`goalkick_state.py`/
  `goalkick_render.py`), its own first-person-ish camera.

Every mode follows the same architectural split: a `*_state.py` (mutable state, input,
`update(dt)`, no drawing) paired with a `*_render.py` (drawing only, never mutates state).
`mechanics.py` holds pure, side-effect-free probability/resolution functions (no Pygame
imports). `settings.py` holds every tunable constant, no logic — every module reads from it,
nothing computes into it beyond simple derived constants (e.g. `FIELD_W = LOGICAL_W - 2 *
FIELD_MARGIN_X`). `entities.py` has two dumb data holders, `Player` and `Ball`. `main.py` is a
thin loop: poll events → `game_state.handle_input` → `game_state.update(dt)` → dispatch to the
right `*_render` module by `game_state.phase`.

A shared `HeroCamera` (`hero_camera.py`) does pinhole projection (`project`/`unproject`) with
smoothed follow. It is reused across modes by constructing it with different parameters
(`settings.MAIN_CAM_*` for FULL GAME/SCENARIOS, `settings.HERO_CAM_*` for AFL HERO,
`settings.GOALKICK_CAM_*`/`GOALKICK_WIDE_CAM_*` for GOAL KICKING) — **the class itself is
never modified**, only constructed differently. This convention should hold for anything new
built here too.

Player sprites are a 7x12 chibi billboard (`render._draw_player_sprite`, wrapped by
`hero_render._player_sprite`/`_scaled` with a cache), always facing the camera — there is no
side-profile logic to worry about. `render.SPRITE_VARIANTS = 8` and a `variant` int (0-7)
deterministically decode to three cosmetic bits (hair part, stocky shoulders, idle stance) so
players aren't all identical; `variant = idx % 8` per player index.

The existing main menu (`render._render_main_menu`, called from `render.render()` while
`game_state.phase == PHASE_MENU`) is the visual language to reuse for the new character menu:
a full-screen dim (`_dim(90)`), a big cream title, then entries drawn as

```python
text = ("> " if selected else "  ") + name + ("  · LOCKED" if locked else "")
color = muted if locked else (gold if selected else cream)
```

where `gold = pygame.Color(settings.YELLOW)`, `cream = pygame.Color(settings.CREAM)`,
`muted = pygame.Color("#b3ac97")`. Locked entries never show a tagline; selected+unlocked
entries show one in `muted` beneath the row. A footer line at the bottom states the controls
(`"ARROWS · ENTER SELECT · ESC BACK"` style). This is the exact block to imitate, adapted to a
different layout (see §3).

## 2. Files relevant to this feature

**Will change:**
- `settings.py` — new/changed constants only (see §2 below for the exact list). No logic.
- `entities.py` — `Player.move()` needs an optional per-call speed override (same pattern
  already used for `Ball.start_flight(..., speed=None)` — see below).
- `game_state.py` — `FORMATION_LINES`/`_build_team_formation` (18 → 16 per side), the FULL
  GAME carrier-speed call site, a new `PHASE_CHARACTER`, a hotkey dispatch, `self.character`.
- `field_render.py` — only if sprite-scale/formation changes need touch-ups here (it just
  reads `settings.MAIN_SPRITE_SCALE`, so likely no change needed beyond the settings value).
- `main.py` — one more `elif` branch to dispatch `PHASE_CHARACTER` to the new render module.

**New files (recommended, mirrors every existing mode):**
- `character_state.py` — new `CharacterState` class.
- `character_render.py` — new `render_character(display, state)`.

**Read-only references (do not edit, but lean on their code/patterns):**
- `hero_camera.py` — reuse `HeroCamera` by construction, exactly like every other mode. Do
  not change its default behavior or any `HERO_CAM_*` constant.
- `hero_render.py` — reuse its small helpers directly: `_player_sprite`, `_scaled`,
  `_soft_ellipse_shadow`, `_render_ground`, `_text`, `_flight_lift`, etc. All read-only
  utilities, safe to import from.
- `render.py` — reuse `_dim`, `_fonts`, `_build_vignette`, `_draw_player_sprite`, and the
  `_render_main_menu` block as the styling reference. Don't restructure the existing menu
  functions, just imitate their look.
- `mechanics.py` — reuse `smoothstep` if the swipe transition wants an eased curve.

**Do not touch at all:**
- `levels.py`, `hero_levels.py` — hand-tuned scenario/level data. See the field-size note in
  §4 for why this matters here specifically.
- `hero_state.py` — AFL HERO's own state machine; not in scope.
- `goalkick_state.py`, `goalkick_render.py` — GOAL KICKING is done and confirmed working;
  don't touch it. (`entities.Ball.start_flight`'s optional `speed` param already added for
  its slow-motion kick already exists — see §2, it's the precedent for the `Player.move`
  change below, not something to redo.)
- No external image/audio assets, ever — procedural pixel art only, consistent with
  everything else in this project.

## 3. FULL GAME retuning: slower players, smaller sprites, 16v16, bigger field

This is prep work for a future player-attribute/upgrade system (the character menu in §4 is
the first piece of that future UI, not the upgrade mechanics themselves — no save file,
currency, or persistence system exists yet or is in scope here). Four linked changes, all
scoped to FULL GAME:

**a) Slow down player movement.** `settings.PLAYER_SPEED = 28.0` currently drives
`entities.Player.move()` for the human-controlled carrier — and that single constant is
shared by **both** FULL GAME and SCENARIOS (SCENARIOS' hand-tuned `time_limit` values in
`levels.py` were balanced against the current speed). Since only FULL GAME should slow down:

1. Give `Player.move(self, dx, dy, dt, speed=None)` an optional override, defaulting to
   `settings.PLAYER_SPEED` when `None` — exactly the same pattern already used for
   `Ball.start_flight(self, from_point, to_point, speed=None)` in `entities.py`. Existing
   2-arg-plus-dt call sites are unaffected.
2. Add a new constant, e.g. `FULL_GAME_PLAYER_SPEED` (suggest roughly 18-20, i.e. a ~30-35%
   cut from 28.0 — tune by feel), and in `game_state._update_movement`, pass
   `speed=settings.FULL_GAME_PLAYER_SPEED if self.game_mode == "full" else None`. This
   leaves `PLAYER_SPEED`/SCENARIOS' balance completely untouched.

**b) Shrink the sprites.** `settings.MAIN_SPRITE_SCALE = 0.85` already exists specifically so
FULL GAME/SCENARIOS can be tuned independently of AFL HERO's `HERO_SPRITE_SCALE` and GOAL
KICKING's `GOALKICK_SPRITE_SCALE` (see `field_render._entity_drawables`, the only reader).
Just lower this one number — suggest somewhere around 0.60-0.70, then eyeball it at 16v16. No
other file needs to change for this part.

**c) 16-a-side instead of 18-a-side.** `game_state.FORMATION_LINES` is a data table — six
named lines, each a depth (0..1) plus a tuple of lateral "slots" (fraction, depth-nudge). Both
`_line_positions` (iterates `for lateral_frac, nudge in slots`) and `_build_team_formation`
(extends a list per line name) are generic over slot-tuple length — **neither hardcodes 3**,
so dropping two total slots to land on 16 is a pure data-table edit, no loop logic changes
needed. Simplest approach: drop one slot from two of the six lines (e.g. `centre` and
`followers` each go from 3 → 2) so the AFL-shaped shell (six lines, backs/mids/forwards) is
preserved. `FULL_GAME_LAYOUT = _build_full_game_layout()` at module scope picks the change up
automatically. This only affects `_build_full_game_layout`; `SCENARIOS` layouts come from
`levels.py` (untouched, unaffected) and AFL HERO/GOAL KICKING don't use `FORMATION_LINES` at
all.

**d) Bigger field, to compensate.** This is the one constant that is **not** mode-scoped —
`settings.FIELD_W`/`FIELD_H` (derived from `LOGICAL_W`/`LOGICAL_H` minus
`FIELD_MARGIN_X`/`FIELD_MARGIN_Y`) drive the oval boundary clamp
(`entities.Player.move`, `mechanics.py`), the oval's drawn shape (`render.py`,
`hero_render.py`), and are shared by every mode's diorama, including AFL HERO and GOAL
KICKING. Recommended approach: **shrink `FIELD_MARGIN_X`/`FIELD_MARGIN_Y` modestly** rather
than touching `LOGICAL_W`/`LOGICAL_H`/`WINDOW_W`/`WINDOW_H` — this grows the oval within the
same window/resolution, no camera-rig or scale-factor knock-on effects. Concretely check
after the change: `levels.py` and `hero_levels.py` contain **literal** `(x, y)` coordinates
(not derived from `FIELD_W`/`FIELD_H`), so growing the oval leaves those designed formations
sitting exactly where they were — nobody ends up outside the (now-bigger) boundary, since the
clamp reads the live constants, but the hand-placed scenario/hero shapes will look a little
more clustered toward the middle rather than filling the bigger oval. That's a cosmetic
side-effect, not a functional break, and it's the reason `levels.py`/`hero_levels.py` are
off-limits rather than something to "fix" — a modest field-size bump (not a drastic one) keeps
this side-effect small. Sanity-check SCENARIOS, AFL HERO, and GOAL KICKING still look/play
fine after the bump; if the cosmetic drift bothers you, prefer a smaller field increase over
a larger one rather than editing those data files.

## 4. New feature: character customization menu

A hotkey-triggered menu, entirely separate from `game_state.ROOT_OPTIONS`/`SCREEN_ROOT` (do
not add an entry there — this is explicitly *not* one of the main menu options). Suggested
key: `K_c` — free in the current bindings (`M` = controls overlay toggle, `1/Q` handball,
`2/K` kick, `3/space` bounce, arrows/WASD movement, `R` retry, `Enter` confirm, `Esc` back/
cancel — `C` doesn't collide with any of these, including GOAL KICKING's arrow-key aim-bias
controls).

**Entry/exit.** Add `PHASE_CHARACTER = "character"` to `game_state.py` and
`self.character = None` in `GameState.__init__`. Check the hotkey ahead of (or alongside) the
normal phase dispatch in `handle_input` so it's reachable at least from `PHASE_MENU` (and
ideally from `PHASE_PLAYING`, similar to how `M` already works mid-match) — remember
whichever phase was active (e.g. `self._pre_character_phase`) so `Esc`/the hotkey again
restores it, rather than always dropping back to the root menu. `main.py` needs one more
branch: `elif game_state.phase == PHASE_CHARACTER: character_render.render_character(display,
game_state.character)`.

**Transition.** A quick "pixel swipe" — a hard-edged, blocky wipe consistent with this game's
chunky low-res look (draw it on the small logical surface before the nearest-neighbor
upscale, the same trick every other visual in this project uses, rather than a smooth
alpha cross-fade). Short: ~0.25-0.35s, sliding a solid panel across to cover the old scene
then reveal the new one underneath. `mechanics.smoothstep` (already used for the GOAL
KICKING camera swoop) is available if a slight ease reads better than linear — try both.

**Scene.** A player standing in the environment, facing the camera. The existing sprite is
already a front-facing billboard (no side-profile logic exists to fight), so reuse
`hero_render._player_sprite`/`_scaled` directly at a larger scale for a close-up "portrait"
feel, standing on ground drawn with `hero_render._render_ground` (or `render.py`'s grass
routines) for a consistent look — no new art needed. A single fixed `HeroCamera` framing
(new constants, e.g. `CHARACTER_CAM_*`, following the existing `*_CAM_BACK`/`HEIGHT`/`FOCAL`
naming) close on the player is enough; it doesn't need to move.

**Attributes panel**, one side of the screen, styled exactly like `_render_main_menu`'s entry
loop (§1 code block: `"> "` prefix + `settings.YELLOW` color when selected, `settings.CREAM`
when active-but-not-selected, `"#b3ac97"` muted + `"  · LOCKED"` suffix when locked, no
tagline row for locked entries). Two groups, per the spec:

- Group 1: **Speed** (active/adjustable now), then locked/pending: **Jumping**, **Kicking
  Power**, **Kicking Accuracy**, **Strength**.
- Group 2 (below the first, same list style): **Height** (active/adjustable now), then
  locked/pending: **Weight**, **Kicking Foot**.

For the two active entries, left/right (or up/down) on the selected row should nudge a stored
numeric value within a small defined range — there's no currency/points system to gate this
with yet (that's the future character-development layer this menu is a first step toward), so
a direct, immediate adjustment is fine for now. Suggested hook so the menu isn't purely
decorative: Speed's value writes into the new `settings.FULL_GAME_PLAYER_SPEED` (or a
`GameState`-held variable that feeds the same call site from §3a) so it's felt next time FULL
GAME starts; Height doesn't have a real gameplay hook yet, so scaling the on-screen preview
sprite is a reasonable stand-in until a future pass gives it one. Locked entries should be
inert (arrow/enter presses on them no-op), same as the existing hero-level/scenario lists'
`locked` handling.

Footer line, matching the existing footer convention: something like
`"ARROWS · ENTER ADJUST · ESC BACK"`.

## 5. What "done" looks like

FULL GAME still runs at a good frame rate with the new roster size; the carrier reads at a
visibly slower, smaller scale without SCENARIOS' pacing changing; SCENARIOS/AFL HERO/GOAL
KICKING all still look and play correctly after the field-size change; the character menu
opens instantly from its hotkey with a snappy pixel-wipe, shows a clearly-readable standing
player and an attributes panel that unmistakably matches the main menu's yellow-highlight
style, Speed/Height are actually adjustable, and the six locked stats read as clearly "not yet
available" without looking broken.

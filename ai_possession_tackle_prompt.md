# Prompt: AI Possession, Kickouts & Tackle Contest System

## Context

This is a Pygame-based Aussie Rules football game (`aussie-rules_game`, Python venv at `aussie-rule_venv`). Two modes exist: **Full Game** and **Scenarios**. Right now the AI has no possession logic at all — it cannot hold, contest, or regain the ball. This prompt covers the first real step toward game AI: giving the AI possession capability, wiring up behinds → kickouts, and adding a tackle/contest mini-game so possession changes are decided by a skill-based input contest rather than instantly.

This is foundational work. Player attributes, tendencies, positioning/timing-based tackling, and smarter AI decision-making are explicitly **out of scope** for this pass — design the system so those can slot in later without a rewrite, but don't build them now.

## Before writing code

1. Read the existing codebase structure first — locate wherever ball possession, game state, scoring, and the Full Game / Scenario loaders currently live. Do not assume file names; report back what you find.
2. Propose a short design doc covering:
   - A possession state machine (e.g. `LOOSE`, `HELD_PLAYER`, `IN_CONTEST`, `DEAD_BALL_KICKOUT`) and which entity (human player, AI player, ball) owns state at each point.
   - The data model for a "contest" (who's involved, whose input is expected, timer, result).
   - How this plugs into both Full Game and Scenarios without duplicating logic (shared possession/contest module, mode-specific config for what's enabled).
   - How a scenario can pre-load the AI already in possession, since scenarios need to start from arbitrary states, not just kickoff.
3. Get that design reviewed before implementing.

## Feature 1: AI Possession

The AI must be able to gain, hold, and lose possession of the ball, symmetrically with the human player.

- AI can pick up a loose/bouncing ball if it's the nearest eligible player (reuse whatever proximity/pickup logic the human player uses today, don't fork it).
- While AI holds possession, the game must track it as the current ball carrier the same way it does for the human, so downstream systems (camera, contest triggers, scoring checks) don't need to special-case "who" has the ball.
- AI in possession should, for now, use minimal placeholder decision-making (e.g. run toward goal, kick after N seconds or when tackled) — just enough that a possession loop is observable and testable. Do not build real AI decision trees yet; leave a clearly marked hook (e.g. `decide_next_action()`) where future tendency/attribute-driven logic will go.
- This must work in **Full Game** as the primary path, and in **Scenarios** wherever a scenario is configured to start with the AI already holding the ball (since scenario designers need to test "get the ball back off the AI" situations).

## Feature 2: Behind → AI Kickout

When the human (or AI) scores a behind, possession must transfer to the opposing team, who takes a kickout from the goal square.

- Detect the behind event off the existing scoring system (find and hook into wherever majors/behinds are currently registered — don't create a parallel scoring path).
- On a behind scored against the AI's goal, the ball resets to the AI's goal square and the AI takes possession and executes a kickout (simple forward kick placeholder is fine — no need for smart kickout targeting yet).
- On a behind scored against the human's goal, mirror this: ball resets to the human's goal square, human takes the kickout (this may already partially exist for the human side — check before rebuilding).
- This needs to fire correctly in Full Game. In Scenarios, only wire it up where the scenario config says scoring/behinds are active — some scenarios may want scoring disabled entirely, so make this configurable, not hardcoded on.

## Feature 3: Tackle / Contest Mini-Game

When a tackle or ball-up contest is triggered (AI attempts to tackle human, human attempts to tackle AI, or a 50/50 loose-ball contest), resolve it with a quick reaction-based input minigame instead of an instant dice roll.

**Trigger conditions** (initial pass — keep simple):
- Defender (human or AI) gets within tackle range of the ball carrier → triggers a tackle contest.
- Two players (any combination of human/AI) reach a loose ball at effectively the same time → triggers a 50/50 contest.

**Contest flow:**
1. Game pauses normal movement for the two contesting entities (rest of play can keep running or freeze — pick whichever is simpler to implement first and flag it as a decision point).
2. Three directional prompts appear in sequence, each one of `UP` / `DOWN` / `LEFT` / `RIGHT`, randomly chosen (avoid immediate repeats of the same direction back-to-back so it doesn't feel like a stutter). Visual layout as a horizontal row of arrow slots, e.g.:
   `[ ^ ] [ > ] [ v ]`
   (reference: "reaction training" style prompts, like a rhythm/QTE minigame — think along the lines of Mario Party-style quick reaction combos.)
3. Both the human and the AI are racing to complete the same 3-input combo:
   - Human input: arrow keys, numpad directions, and D-pad on connected gamepad (`pygame.joystick` — hat/D-pad input), all mapped to the same four directions.
   - AI input: on a timer roughly matching a plausible human reaction+input speed for this pass (placeholder — no attribute-driven speed yet), the AI "presses" the current required prompt.
4. When a prompt is correctly hit (by either side), animate it as consumed: highlight/flash the slot then have it slide/fade out, and reveal the next prompt in the sequence. Wrong input on that prompt should give clear negative feedback (e.g. shake/flash red) without necessarily failing the whole contest — decide and note whether a miss costs time, resets the combo, or is instant loss, and make it configurable/tunable rather than hardcoded.
5. Whoever completes all 3 prompts first wins the contest:
   - Human wins tackle → breaks the tackle / wins the ball-up and retains or gains possession.
   - AI wins tackle → human loses possession, AI gains it (or the tackle is completed and ball becomes loose, per whatever the design doc lands on for tackle outcomes vs. ball-up outcomes).
6. Unpause/resume normal play with the resolved possession state applied.

**Implementation notes:**
- Build this as a self-contained, reusable module (e.g. `contest_minigame.py`) that Full Game and Scenarios both call into — pass in "who's contesting" and get back a winner, don't duplicate the minigame per mode.
- Keep all tunables (prompt count, AI reaction timing, input window, whether misses reset combo) in one config block so they're easy to balance later without touching game logic.
- Leave explicit hooks/comments for where player attributes (strength, agility), tendencies, and positioning/timing will later modify: AI reaction speed, contest trigger radius, and win probability weighting. Do not implement those systems now — just leave the seams.
- This needs to work in Full Game as the primary path, and in Scenarios for any scenario configured to include contests (some scenarios may want contests disabled to isolate other mechanics being tested — make it toggleable per scenario, not global).

## Testing / verification

- Manual test: in Full Game, get tackled by AI and confirm the minigame triggers, both win/lose paths correctly transfer possession, and the game resumes cleanly.
- Manual test: score a behind against AI's goal, confirm AI kickout triggers and ball/possession reset correctly; repeat for a behind against the human's goal.
- Manual test: set up (or add) a Scenario where AI starts in possession, confirm the human can trigger a tackle contest and take the ball back.
- Confirm Scenarios where contests/scoring are toggled off behave correctly (no minigame/kickout fires).
- Check for regressions in existing human-only possession/scoring flows — nothing here should change current human-side behavior when the AI isn't involved.

## Deliverable

1. Short design doc (state machine + data model + integration points) for review before implementation.
2. Implementation: AI possession, behind→kickout for both goals, and the tackle/contest minigame, wired into both Full Game and Scenarios per the toggles above.
3. Brief summary of what was built, what's stubbed/placeholder (AI decision-making, attribute hooks), and what the next logical milestone would be (e.g. wiring in player attributes to the contest win-weighting and AI reaction timing).

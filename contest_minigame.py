"""contest_minigame.py — reaction-based loose-ball / 50-50 / ruck contest.

Tackles used to run through here too ("kind" could be "tackle") but no
longer do — see GameState._resolve_tackle_now / mechanics.resolve_tackle,
which judge a tackle instantly against match-rule state (how long the
carrier has held the ball) instead of racing it, since a stat-driven
"almost random" break-tackle roll isn't something either player being
faster on the buttons should decide. This module still owns every
contest kind where nobody's holding-the-ball status is in question: a
kick landing in a pack ("loose_ball") and a boundary ball-up
("ruck" — see GameState._start_ruck_contest).

Self-contained: FULL GAME and SCENARIOS both call start()/update() the
same way, passing in who's contesting and reading the result back off
the returned Contest (.resolved / .winner). No mode-specific branching
lives here — see game_state.py for how the two modes wire this in via
GameState.mode_config's "contests_enabled" toggle.

No Pygame imports, same rule mechanics.py follows — this is pure state
advancement, so it can be driven/tested without a display. Rendering
lives in field_render.py, reading a Contest's public fields directly.

All tunables are read from settings.py once, into CONTEST_CONFIG below,
so balancing this doesn't touch any logic here or in game_state.py.
"""

import random

import settings

DIRECTIONS = ("UP", "DOWN", "LEFT", "RIGHT")

CONTEST_CONFIG = {
    "prompt_count": settings.CONTEST_PROMPT_COUNT,
    "ai_reaction_range": settings.CONTEST_AI_REACTION_RANGE,
    "input_window": settings.CONTEST_INPUT_WINDOW,
    "miss_policy": settings.CONTEST_MISS_POLICY,   # "reset_combo" | "time_penalty" | "instant_loss"
    "miss_time_penalty": settings.CONTEST_MISS_TIME_PENALTY,
}


class Contest:
    """One tackle or 50/50 reaction contest between exactly two players.

    Both sides race the same `prompts` sequence independently — each
    tracks its own `progress` index into it. First to reach the end wins.
    """

    def __init__(self, participants, kind, config):
        self.participants = list(participants)
        self.kind = kind                     # "tackle" | "loose_ball"
        self.config = config
        self.prompts = _generate_prompts(config["prompt_count"])
        self.progress = {id(p): 0 for p in self.participants}
        self.prompt_timer = {id(p): 0.0 for p in self.participants}
        self.flash = {id(p): 0.0 for p in self.participants}  # >0: slot flashing on a miss
        self.human = next((p for p in self.participants
                           if p.team == settings.YELLOW), None)
        self.ai_participants = [p for p in self.participants if p is not self.human]
        self._ai_next_press = {id(p): _roll_ai_reaction(config)
                               for p in self.ai_participants}
        self.resolved = False
        self.winner = None


def _generate_prompts(count):
    """`count` random directions, never repeating the previous one back
    to back (per the prompt spec — a stutter reads as a glitch, not a
    combo)."""
    prompts = []
    last = None
    for _ in range(count):
        d = random.choice([x for x in DIRECTIONS if x != last])
        prompts.append(d)
        last = d
    return prompts


def _roll_ai_reaction(config):
    lo, hi = config["ai_reaction_range"]
    return random.uniform(lo, hi)


def start(participants, kind, config=None):
    """Begin a new contest between exactly two players."""
    return Contest(participants, kind, config or CONTEST_CONFIG)


def _advance(contest, player):
    """`player` correctly hit their current prompt: consume it and
    either resolve the contest (last prompt) or reveal the next one."""
    pid = id(player)
    contest.progress[pid] += 1
    contest.prompt_timer[pid] = 0.0
    if contest.progress[pid] >= len(contest.prompts):
        contest.resolved = True
        contest.winner = player


def _miss(contest, player):
    """Wrong input, or a prompt that timed out. Configurable per
    CONTEST_CONFIG["miss_policy"] rather than one hardcoded outcome —
    see settings.CONTEST_MISS_POLICY's comment for the tradeoff.

    HOOK: future strength/agility attributes could scale the time
    penalty or how harsh the reset is, per player, instead of one flat
    policy shared by both sides.
    """
    pid = id(player)
    contest.flash[pid] = 0.25
    policy = contest.config["miss_policy"]
    if policy == "instant_loss":
        other = next((p for p in contest.participants if p is not player), None)
        contest.resolved = True
        contest.winner = other
    elif policy == "time_penalty":
        contest.prompt_timer[pid] = -contest.config["miss_time_penalty"]
    else:  # "reset_combo" (default) — knocked back to the start of the sequence
        contest.progress[pid] = 0
        contest.prompt_timer[pid] = 0.0


def update(contest, dt, human_inputs=()):
    """Advance one frame.

    `human_inputs` is the list of direction strings ("UP"/"DOWN"/"LEFT"/
    "RIGHT") the human pressed this frame — see game_state.py's
    _contest_direction_queue, fed by real KEYDOWN events and by
    controller.py's synthesized ones (D-pad), so gamepad input works
    with zero changes here.
    """
    if contest.resolved:
        return

    for pid in contest.flash:
        if contest.flash[pid] > 0.0:
            contest.flash[pid] = max(0.0, contest.flash[pid] - dt)

    human = contest.human
    if human is not None and not contest.resolved:
        pid = id(human)
        if contest.progress[pid] < len(contest.prompts):
            for pressed in human_inputs:
                if contest.resolved:
                    break
                expected = contest.prompts[contest.progress[pid]]
                if pressed == expected:
                    _advance(contest, human)
                else:
                    _miss(contest, human)
            if not contest.resolved and contest.progress[pid] < len(contest.prompts):
                contest.prompt_timer[pid] += dt
                if contest.prompt_timer[pid] >= contest.config["input_window"]:
                    _miss(contest, human)

    # AI side(s): fire a "press" once its reaction timer elapses — always
    # correct for this pass (no attribute-driven accuracy yet — see
    # settings.CONTEST_AI_REACTION_RANGE's HOOK note).
    for ai in contest.ai_participants:
        if contest.resolved:
            break
        pid = id(ai)
        if contest.progress[pid] >= len(contest.prompts):
            continue
        contest.prompt_timer[pid] += dt
        if contest.prompt_timer[pid] >= contest._ai_next_press[pid]:
            _advance(contest, ai)
            if not contest.resolved:
                contest._ai_next_press[pid] = _roll_ai_reaction(contest.config)

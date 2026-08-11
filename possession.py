"""possession.py — shared possession state machine, tackle-trigger check,
and behind→kickout handling.

Used identically by FULL GAME and SCENARIOS; mode differences are always
expressed through GameState.mode_config (see game_state.DEFAULT_MODE_CONFIG),
never branched on game_mode in here.

State machine:
  HELD_PLAYER      — a Player's is_ball_carrier is True (either team —
                      see entities.Ball.give_to / GameState._give_possession,
                      which have always been team-agnostic under the hood).
  IN_CONTEST       — a contest_minigame.Contest is in progress
                      (GameState.active_contest); normal play is frozen
                      (see GameState.update). Only loose_ball (a kick
                      landing in a pack) and ruck (a boundary ball-up)
                      contests reach this state — a tackle resolves
                      instantly instead (see find_tackle_trigger /
                      GameState._resolve_tackle_now) and never sets it.
  DEAD_BALL_KICKOUT — set for one frame after a behind, while the
                      defending team's kicker is being placed in their
                      goal square; promoted straight back to HELD_PLAYER
                      the next frame (see GameState.update) since a
                      kickout is just a normal carry from a fixed spot,
                      not an ongoing dead-ball phase in this pass.
  LOOSE_BALL        — nobody's carrying: an inaccurate kick, an accurate
                      kick nobody was there to mark, or a spilled
                      handball. The ball bounces/rolls to a stop (see
                      entities.Ball.start_bounce) and just sits there —
                      both teams' nearest players converge on it (see
                      GameState._update_loose_ball) and whoever actually
                      reaches it gathers it, human included, simply by
                      running their controlled player over it. Replaces
                      what used to be an instant handoff to "the nearest
                      opponent, however far away they actually were."
"""

import settings

HELD_PLAYER = "held_player"
IN_CONTEST = "in_contest"
DEAD_BALL_KICKOUT = "dead_ball_kickout"
LOOSE_BALL = "loose_ball"


def attacking_goal(team):
    """Which goal a team scores at — YELLOW attacks GOAL_RIGHT, RED
    attacks GOAL_LEFT (see game_state.FORMATION_LINES / levels.py)."""
    return settings.GOAL_RIGHT if team == settings.YELLOW else settings.GOAL_LEFT


def find_tackle_trigger(game_state):
    """The [carrier, defender] pair to resolve a tackle between, or None.
    The nearest opposing player closing to within TACKLE_TRIGGER_RADIUS
    of the carrier triggers it — this is the same "nearest defender
    closes in" behaviour update_defenders already drives (see
    mechanics.py), just no longer stopping short of the carrier without
    consequence. The tackle itself resolves instantly (see
    GameState._resolve_tackle_now / mechanics.resolve_tackle) — this
    function only answers "has a tackle happened this frame," not how it
    plays out.

    HOOK: future positioning/timing/attributes would narrow or widen
    the trigger radius per-defender instead of one flat constant, and
    could favor better-positioned defenders over the single nearest one.
    """
    carrier = game_state.carrier
    if carrier is None:
        return None
    # A carrier currently protected by stand-the-mark (see
    # GameState.standing_mark / _start_standing_mark) is immune to a
    # tackle trigger for the hold's duration — the nearest opponent is
    # frozen at the mark anyway (see update()'s defender-chase exclusion),
    # so this only matters for a *different* opponent closing in.
    standing_mark = getattr(game_state, "standing_mark", None)
    if standing_mark is not None and standing_mark["marker"] is carrier:
        return None
    opposing = (game_state.opponents if carrier.team == settings.YELLOW
                else game_state.teammates)
    if not opposing:
        return None
    defender = min(opposing, key=lambda o: o.distance_to(carrier.pos))
    if defender.distance_to(carrier.pos) <= settings.TACKLE_TRIGGER_RADIUS:
        return [carrier, defender]
    return None


def resolve_behind(game_state, scoring_team):
    """A behind was conceded at `scoring_team`'s attacking goal — reload
    the mode's layout (same reset every score already used, see
    GameState._reset_to_kickoff) but hand the defending team's nearest
    player the ball at their own goal square instead of the usual
    kickoff carrier, for a placeholder forward kickout.
    """
    defending_team = settings.RED if scoring_team == settings.YELLOW else settings.YELLOW

    keep = (game_state.score, game_state.timer, game_state.flash,
            game_state.message, game_state.message_timer)
    game_state._load_layout(game_state._current_layout)
    (game_state.score, game_state.timer, game_state.flash,
     game_state.message, game_state.message_timer) = keep

    goal = attacking_goal(scoring_team)   # the goal the behind was shot at
    squad = (game_state.opponents if defending_team == settings.RED
              else game_state.teammates)
    kicker = min(squad, key=lambda p: p.distance_to(goal))

    for p in game_state.players:
        p.is_ball_carrier = False
    kicker.x, kicker.y = goal
    kicker.is_ball_carrier = True
    game_state.ball.give_to(kicker)
    game_state.possession_state = DEAD_BALL_KICKOUT
    game_state.run_since_bounce = 0.0

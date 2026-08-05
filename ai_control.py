"""ai_control.py — placeholder AI ball-carrier behavior.

Real decision-making (tendencies, attributes, positioning/timing) is
explicitly out of scope for this pass — see decide_next_action's HOOK
comment below. This module only exists to make the AI's possession loop
observable and testable: run at goal, kick after a timeout. It always
kicks through GameState._attempt_kick, the exact same pipeline the human
uses, so scoring/marking/turnover resolution never forks between teams.
"""

import possession
import settings


def decide_next_action(game_state, dt):
    """Drive the AI ball-carrier for one frame, called every update()
    tick regardless of who currently holds the ball (see game_state.py) —
    this function is the single gate that no-ops unless a RED player is
    actually the free-running carrier.

    HOOK: this whole body is the placeholder — a future tendency/
    attribute-driven decision tree (pass vs. run vs. shoot, reaction to
    pressure, etc.) replaces it without needing to change how it's
    called from game_state.update().
    """
    carrier = game_state.carrier
    if (carrier is None
            or carrier.team != settings.RED
            or not game_state.mode_config.get("ai_enabled", True)
            or game_state.possession_state != possession.HELD_PLAYER
            or game_state.ball.in_flight):
        game_state.ai_hold_timer = 0.0
        return

    goal = possession.attacking_goal(carrier.team)
    dx, dy = goal[0] - carrier.x, goal[1] - carrier.y
    carrier.move(dx, dy, dt, speed=settings.DEFENDER_SPEED)

    game_state.ai_hold_timer += dt
    if game_state.ai_hold_timer >= settings.AI_HOLD_TIMEOUT:
        game_state.ai_hold_timer = 0.0
        game_state._attempt_kick(goal)

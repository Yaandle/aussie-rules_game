"""ai_control.py — placeholder AI ball-carrier behavior.

Real decision-making (tendencies, attributes, positioning/timing) is
explicitly out of scope for this pass — see decide_next_action's HOOK
comment below. This module only exists to make the AI's possession loop
observable and testable: run at goal, shoot once actually in range. It
always kicks through GameState._attempt_kick, the exact same pipeline
the human uses, so scoring/marking/turnover resolution never forks
between teams.

Two things this deliberately fixes without building out a real decision
tree (still future work): the AI used to run a razor-straight line at
the goal center and, on AI_HOLD_TIMEOUT, punt dead-straight at goal
regardless of range — since a typical possession starts well outside
SCORING_ARC_RADIUS, that kick was almost never actually a scoring
attempt (mechanics.is_scoring_attempt requires being inside the arc
first), just a low-percentage contested punt aimed at the goal mouth
that read as "always beelines to goal, never scores." Now: (1) the run
heading gets a periodic random wobble instead of a fixed rail, and (2)
a shot only fires once genuinely in range, aimed with some spread
instead of always dead center.
"""

import random

import mechanics
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
        game_state.ai_wobble_timer = 0.0
        return

    goal = possession.attacking_goal(carrier.team)
    dx, dy = goal[0] - carrier.x, goal[1] - carrier.y
    in_range = mechanics.is_scoring_attempt(carrier.pos, goal, goal)

    # Once genuinely in range, take the shot immediately rather than
    # continuing to run it down to point-blank — a real player shoots
    # from the first good opportunity, not the last possible moment.
    if in_range:
        game_state.ai_hold_timer = 0.0
        game_state.ai_wobble_timer = 0.0
        angle = random.uniform(-settings.AI_SHOT_AIM_SPREAD_DEGREES,
                               settings.AI_SHOT_AIM_SPREAD_DEGREES)
        aim_dx, aim_dy = mechanics.rotate_vector(dx, dy, angle)
        target = (carrier.x + aim_dx, carrier.y + aim_dy)
        game_state._attempt_kick(target)
        return

    # Still out of range: keep running toward goal, but re-roll a small
    # random heading offset every AI_WOBBLE_INTERVAL seconds instead of
    # holding a perfectly straight line the whole carry (see settings.py
    # for the rationale) — re-rolled periodically rather than every
    # frame so it reads as a deliberate running line, not a jitter.
    game_state.ai_wobble_timer -= dt
    if game_state.ai_wobble_timer <= 0.0:
        game_state.ai_wobble_timer = settings.AI_WOBBLE_INTERVAL
        game_state.ai_wobble_angle = random.uniform(
            -settings.AI_RUN_WOBBLE_DEGREES, settings.AI_RUN_WOBBLE_DEGREES)
    run_dx, run_dy = mechanics.rotate_vector(dx, dy, game_state.ai_wobble_angle)
    carrier.move(run_dx, run_dy, dt, speed=settings.DEFENDER_SPEED)

    # Still force a kick past AI_HOLD_TIMEOUT even if it never reached
    # range (e.g. running along the boundary rather than toward the
    # arc) — better to give the ball up on a contested punt than run
    # out the clock holding it forever, same fallback the old behavior had.
    game_state.ai_hold_timer += dt
    if game_state.ai_hold_timer >= settings.AI_HOLD_TIMEOUT:
        game_state.ai_hold_timer = 0.0
        game_state._attempt_kick(goal)

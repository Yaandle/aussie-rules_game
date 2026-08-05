"""main.py — entry point. Orchestrates; implements nothing.

Run with:  pip install pygame  →  python main.py
"""

import pygame

import character_render
import controller
import field_render
import goalkick_render
import hero_render
import render
import settings
from game_state import (PHASE_CHARACTER, PHASE_GOALKICK, PHASE_HERO,
                        PHASE_MENU, GameState)


def main():
    """Initialize Pygame, run the event/update/render loop, quit cleanly."""
    pygame.init()
    display = pygame.display.set_mode((settings.WINDOW_W, settings.WINDOW_H))
    pygame.display.set_caption("AFL Prototype")
    clock = pygame.time.Clock()
    controller.init()

    game_state = GameState()
    running = True

    while running:
        dt = clock.tick(settings.FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            else:
                controller.handle_device_event(event)
                game_state.handle_input(event)

        # Xbox controller: buttons/D-pad/stick become synthetic KEYDOWN
        # events here, so every existing keyboard-driven menu and action
        # picks them up with no changes of its own (see controller.py).
        for synth_event in controller.poll_events():
            game_state.handle_input(synth_event)

        game_state.update(dt)
        if game_state.phase == PHASE_HERO and game_state.hero is not None:
            hero_render.render_hero(display, game_state.hero)
        elif game_state.phase == PHASE_GOALKICK and game_state.goalkick is not None:
            goalkick_render.render_goalkick(display, game_state.goalkick)
        elif game_state.phase == PHASE_CHARACTER:
            character_render.render_character(display, game_state.character)
        elif game_state.phase == PHASE_MENU:
            render.render(display, game_state)
        else:
            field_render.render(display, game_state)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()

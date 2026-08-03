"""main.py — entry point. Orchestrates; implements nothing.

Run with:  pip install pygame  →  python main.py
"""

import pygame

import field_render
import hero_render
import render
import settings
from game_state import PHASE_HERO, PHASE_MENU, GameState


def main():
    """Initialize Pygame, run the event/update/render loop, quit cleanly."""
    pygame.init()
    display = pygame.display.set_mode((settings.WINDOW_W, settings.WINDOW_H))
    pygame.display.set_caption("AFL Prototype")
    clock = pygame.time.Clock()

    game_state = GameState()
    running = True

    while running:
        dt = clock.tick(settings.FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            else:
                game_state.handle_input(event)

        game_state.update(dt)
        if game_state.phase == PHASE_HERO and game_state.hero is not None:
            hero_render.render_hero(display, game_state.hero)
        elif game_state.phase == PHASE_MENU:
            render.render(display, game_state)
        else:
            field_render.render(display, game_state)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()

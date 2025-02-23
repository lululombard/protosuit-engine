#include "scenes.h"
#include <math.h>

void render_idle_scene(SDL_Renderer *renderer, double angle)
{
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);

    // Calculate center position
    int center_x = WINDOW_WIDTH / 2;
    int center_y = WINDOW_HEIGHT / 2;

    // Create square points
    SDL_Point points[5];
    for (int i = 0; i < 4; i++)
    {
        double point_angle = angle + (M_PI / 2.0) * i;
        points[i].x = center_x + cos(point_angle) * SQUARE_SIZE;
        points[i].y = center_y + sin(point_angle) * SQUARE_SIZE;
    }
    points[4] = points[0]; // Close the square

    // Draw rotating square
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);
    for (int i = 0; i < 4; i++)
    {
        SDL_RenderDrawLine(renderer, points[i].x, points[i].y, points[i + 1].x, points[i + 1].y);
    }
}
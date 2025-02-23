#include "scenes.h"
#include <stdio.h>

// Forward declaration of cleanup function
void cleanup_doom_process(SceneState *state);

void init_scene_system(SceneState *state, SDL_Renderer *renderer)
{
    // Create two render textures at window size
    state->scene_a = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA8888,
                                       SDL_TEXTUREACCESS_TARGET, WINDOW_WIDTH, WINDOW_HEIGHT);
    state->scene_b = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA8888,
                                       SDL_TEXTUREACCESS_TARGET, WINDOW_WIDTH, WINDOW_HEIGHT);

    if (!state->scene_a || !state->scene_b)
    {
        printf("Failed to create scene textures: %s\n", SDL_GetError());
        return;
    }

    // Enable alpha blending for both textures
    SDL_SetTextureBlendMode(state->scene_a, SDL_BLENDMODE_BLEND);
    SDL_SetTextureBlendMode(state->scene_b, SDL_BLENDMODE_BLEND);

    // Initialize state
    state->current = SCENE_IDLE;
    state->next = SCENE_IDLE;
    state->transition_progress = 1.0f;
    state->scene_a_is_current = SDL_TRUE;
    state->doom_pid = 0;
    state->doom_manually_closed = SDL_FALSE;
    // Don't reset mqtt_connected here as it's managed by the MQTT callbacks

    // Clear both textures to black
    SDL_SetRenderTarget(renderer, state->scene_a);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);

    SDL_SetRenderTarget(renderer, state->scene_b);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);

    SDL_SetRenderTarget(renderer, NULL);
}

void cleanup_scene_system(SceneState *state)
{
    // Cleanup Doom process if running
    cleanup_doom_process(state);

    if (state->scene_a)
    {
        SDL_DestroyTexture(state->scene_a);
        state->scene_a = NULL;
    }
    if (state->scene_b)
    {
        SDL_DestroyTexture(state->scene_b);
        state->scene_b = NULL;
    }
}

void start_scene_transition(SceneState *state, Scene new_scene, SDL_Renderer *renderer, TTF_Font *font)
{
    // Don't start a new transition if we're already transitioning to the same scene
    if (state->transition_progress < 1.0f || state->next == new_scene)
    {
        return;
    }

    // If we're transitioning away from Doom, cleanup the process
    if (state->current == SCENE_DOOM)
    {
        state->doom_manually_closed = SDL_TRUE;
        cleanup_doom_process(state);
    }

    // Set up the transition
    state->next = new_scene;
    state->transition_progress = 0.0f;

    // Render the next scene to the disengaged texture
    SDL_Texture *next_texture = state->scene_a_is_current ? state->scene_b : state->scene_a;
    SDL_SetRenderTarget(renderer, next_texture);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);

    if (new_scene == SCENE_DEBUG)
    {
        if (font)
        {
            render_debug_scene(renderer, font, state->mqtt_connected);
        }
    }
    else if (new_scene == SCENE_DOOM)
    {
        // Reset the manually closed flag when explicitly switching to Doom
        state->doom_manually_closed = SDL_FALSE;
        render_doom_scene(renderer, state);
    }
    else
    {
        render_idle_scene(renderer, 0);
    }

    SDL_SetRenderTarget(renderer, NULL);
}

void update_scene_transition(SceneState *state, float delta_time)
{
    if (state->transition_progress < 1.0f)
    {
        state->transition_progress += delta_time / TRANSITION_DURATION;
        if (state->transition_progress >= 1.0f)
        {
            // Transition complete - "engage the clutch"
            state->current = state->next;
            state->transition_progress = 1.0f;
            state->scene_a_is_current = !state->scene_a_is_current;
        }
    }
}

void render_scene_transition(SDL_Renderer *renderer, SceneState *state, TTF_Font *font, double rotation_angle)
{
    // Always start with the default render target
    SDL_SetRenderTarget(renderer, NULL);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);

    // If we're in Doom scene and Doom process is gone, switch to debug scene
    if ((state->current == SCENE_DOOM || state->next == SCENE_DOOM) && state->doom_pid == 0)
    {
        if (state->transition_progress >= 1.0f) // Only start new transition if not already transitioning
        {
            printf("Doom process terminated, switching back to debug scene\n");
            start_scene_transition(state, SCENE_DEBUG, renderer, font);
            // Render the debug scene immediately
            render_debug_scene(renderer, font, state->mqtt_connected);
            return;
        }
    }

    if (state->transition_progress < 1.0f)
    {
        // During transition, we need to render to textures
        SDL_Texture *current_tex = state->scene_a_is_current ? state->scene_a : state->scene_b;
        SDL_Texture *next_tex = state->scene_a_is_current ? state->scene_b : state->scene_a;

        // Render the current scene to its texture
        SDL_SetRenderTarget(renderer, current_tex);
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
        SDL_RenderClear(renderer);
        if (state->current == SCENE_DEBUG)
        {
            if (font)
            {
                render_debug_scene(renderer, font, state->mqtt_connected);
            }
        }
        else if (state->current == SCENE_DOOM)
        {
            render_doom_scene(renderer, state);
        }
        else
        {
            render_idle_scene(renderer, rotation_angle);
        }

        // Render the next scene to its texture
        SDL_SetRenderTarget(renderer, next_tex);
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
        SDL_RenderClear(renderer);
        if (state->next == SCENE_DEBUG)
        {
            if (font)
            {
                render_debug_scene(renderer, font, state->mqtt_connected);
            }
        }
        else if (state->next == SCENE_DOOM)
        {
            render_doom_scene(renderer, state);
        }
        else
        {
            render_idle_scene(renderer, rotation_angle);
        }

        // Switch back to the screen and render both textures
        SDL_SetRenderTarget(renderer, NULL);
        SDL_RenderClear(renderer);

        // Ensure we finish all rendering before setting alpha
        SDL_RenderFlush(renderer);

        // Set alpha values and render the textures
        SDL_SetTextureAlphaMod(current_tex, (Uint8)(255 * (1.0f - state->transition_progress)));
        SDL_SetTextureAlphaMod(next_tex, (Uint8)(255 * state->transition_progress));

        SDL_RenderCopy(renderer, current_tex, NULL, NULL);
        SDL_RenderCopy(renderer, next_tex, NULL, NULL);
    }
    else
    {
        // No transition, render directly to the screen
        if (state->current == SCENE_DEBUG)
        {
            if (font)
            {
                render_debug_scene(renderer, font, state->mqtt_connected);
            }
        }
        else if (state->current == SCENE_DOOM)
        {
            render_doom_scene(renderer, state);
        }
        else
        {
            render_idle_scene(renderer, rotation_angle);
        }
    }
}
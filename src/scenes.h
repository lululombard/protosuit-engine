#ifndef SCENES_H
#define SCENES_H

#include <SDL.h>
#include <SDL_ttf.h>

#define WINDOW_WIDTH 720
#define WINDOW_HEIGHT 720
#define SQUARE_SIZE 100
#define TRANSITION_DURATION 0.5f // Duration in seconds

typedef enum
{
    SCENE_DEBUG,
    SCENE_IDLE,
    SCENE_DOOM,
    SCENE_COUNT
} Scene;

typedef struct
{
    Scene current;
    Scene next;
    float transition_progress;     // 0.0 to 1.0
    SDL_Texture *scene_a;          // First "clutch"
    SDL_Texture *scene_b;          // Second "clutch"
    SDL_bool scene_a_is_current;   // Which clutch is currently engaged
    pid_t doom_pid;                // Track Doom process ID
    SDL_bool doom_manually_closed; // Track if Doom was closed by user
    SDL_bool mqtt_connected;       // Track MQTT connection status
} SceneState;

// Scene rendering functions
void render_debug_scene(SDL_Renderer *renderer, TTF_Font *font, SDL_bool mqtt_connected);
void render_idle_scene(SDL_Renderer *renderer, double angle);
void render_doom_scene(SDL_Renderer *renderer, SceneState *state);

// Scene transition functions
void init_scene_system(SceneState *state, SDL_Renderer *renderer);
void cleanup_scene_system(SceneState *state);
void start_scene_transition(SceneState *state, Scene new_scene, SDL_Renderer *renderer, TTF_Font *font);
void update_scene_transition(SceneState *state, float delta_time);
void render_scene_transition(SDL_Renderer *renderer, SceneState *state, TTF_Font *font, double rotation_angle);

#endif // SCENES_H
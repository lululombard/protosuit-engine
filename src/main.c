#include "scenes.h"
#include "embedded_assets.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <mosquitto.h>

#define DEFAULT_MQTT_BROKER "localhost"
#define DEFAULT_MQTT_PORT 1883

SceneState scene_state = {
    .current = SCENE_IDLE,
    .next = SCENE_IDLE,
    .transition_progress = 1.0f,
    .scene_a = NULL,
    .scene_b = NULL,
    .scene_a_is_current = SDL_TRUE,
    .doom_pid = 0,
    .doom_manually_closed = SDL_FALSE,
    .mqtt_connected = SDL_FALSE};

SDL_Window *window = NULL;
SDL_Renderer *renderer = NULL;
TTF_Font *font = NULL;
struct mosquitto *mosq = NULL;

void mqtt_callback(struct mosquitto *mosq, void *userdata, const struct mosquitto_message *message)
{
    if (!message)
    {
        printf("Received null MQTT message\n");
        return;
    }

    printf("Received MQTT message on topic %s\n", message->topic);
    scene_state.mqtt_connected = SDL_TRUE;

    if (strcmp(message->topic, "sdl/scene") == 0)
    {
        Scene new_scene = scene_state.current;
        if (strcmp((char *)message->payload, "debug") == 0)
        {
            new_scene = SCENE_DEBUG;
            printf("Switching to debug scene\n");
        }
        else if (strcmp((char *)message->payload, "idle") == 0)
        {
            new_scene = SCENE_IDLE;
            printf("Switching to idle scene\n");
        }
        else if (strcmp((char *)message->payload, "doom") == 0)
        {
            new_scene = SCENE_DOOM;
            printf("Switching to doom scene\n");
        }
        if (new_scene != scene_state.current)
        {
            start_scene_transition(&scene_state, new_scene, renderer, font);
        }
    }
}

void mqtt_connect_callback(struct mosquitto *mosq, void *userdata, int result)
{
    printf("MQTT connect callback with result: %d (%s)\n", result, mosquitto_strerror(result));
    if (!result)
    {
        // Subscribe to scene control topic
        printf("Connection successful, subscribing to sdl/scene...\n");
        int rc = mosquitto_subscribe(mosq, NULL, "sdl/scene", 0);
        if (rc == MOSQ_ERR_SUCCESS)
        {
            scene_state.mqtt_connected = SDL_TRUE;
            printf("Successfully subscribed to sdl/scene (mqtt_connected=%d)\n", scene_state.mqtt_connected);
        }
        else
        {
            scene_state.mqtt_connected = SDL_FALSE;
            printf("Failed to subscribe: %s (mqtt_connected=%d)\n", mosquitto_strerror(rc), scene_state.mqtt_connected);
        }
    }
    else
    {
        scene_state.mqtt_connected = SDL_FALSE;
        printf("Connection failed: %s (mqtt_connected=%d)\n", mosquitto_strerror(result), scene_state.mqtt_connected);
    }
}

void mqtt_disconnect_callback(struct mosquitto *mosq, void *userdata, int rc)
{
    printf("MQTT disconnect callback with code %d (%s)\n", rc, mosquitto_strerror(rc));
    scene_state.mqtt_connected = SDL_FALSE;
    printf("Connection state updated (mqtt_connected=%d)\n", scene_state.mqtt_connected);

    // Try to reconnect if the disconnect was unexpected
    if (rc != 0)
    {
        printf("Unexpected disconnect, attempting to reconnect...\n");
        int result = mosquitto_reconnect(mosq);
        if (result != MOSQ_ERR_SUCCESS)
        {
            printf("Failed to initiate reconnection: %s\n", mosquitto_strerror(result));
        }
        else
        {
            printf("Reconnection initiated\n");
        }
    }
}

int main(void)
{
    // Get MQTT broker from environment variable
    const char *mqtt_broker = getenv("MQTT_BROKER");
    if (!mqtt_broker)
    {
        mqtt_broker = DEFAULT_MQTT_BROKER;
        printf("MQTT_BROKER not set, using default: %s\n", mqtt_broker);
    }
    else
    {
        printf("Using MQTT broker: %s\n", mqtt_broker);
    }

    // Get MQTT port from environment variable (optional)
    int mqtt_port = DEFAULT_MQTT_PORT;
    const char *mqtt_port_str = getenv("MQTT_PORT");
    if (mqtt_port_str)
    {
        mqtt_port = atoi(mqtt_port_str);
        printf("Using MQTT port: %d\n", mqtt_port);
    }

    // Initialize MQTT
    mosquitto_lib_init();
    mosq = mosquitto_new(NULL, true, NULL);
    if (!mosq)
    {
        printf("MQTT initialization failed\n");
        return 1;
    }

    // Enable automatic reconnection
    mosquitto_reconnect_delay_set(mosq, 1, 10, true);

    // Set MQTT callbacks
    mosquitto_connect_callback_set(mosq, mqtt_connect_callback);
    mosquitto_disconnect_callback_set(mosq, mqtt_disconnect_callback);
    mosquitto_message_callback_set(mosq, mqtt_callback);

    // Connect to MQTT broker
    printf("Attempting to connect to MQTT broker at %s:%d\n", mqtt_broker, mqtt_port);
    int connect_result = mosquitto_connect(mosq, mqtt_broker, mqtt_port, 60);
    if (connect_result)
    {
        printf("Could not connect to MQTT broker at %s:%d: %s\n", mqtt_broker, mqtt_port, mosquitto_strerror(connect_result));
    }

    // Start MQTT loop in background
    int loop_result = mosquitto_loop_start(mosq);
    if (loop_result != MOSQ_ERR_SUCCESS)
    {
        printf("Failed to start MQTT loop: %s\n", mosquitto_strerror(loop_result));
        mosquitto_destroy(mosq);
        mosquitto_lib_cleanup();
        return 1;
    }
    printf("MQTT loop started successfully\n");

    if (SDL_Init(SDL_INIT_VIDEO) < 0)
    {
        printf("SDL initialization failed: %s\n", SDL_GetError());
        return 1;
    }

    if (TTF_Init() < 0)
    {
        printf("TTF initialization failed: %s\n", TTF_GetError());
        SDL_Quit();
        return 1;
    }

    window = SDL_CreateWindow("SDL Scenes",
                              SDL_WINDOWPOS_UNDEFINED,
                              SDL_WINDOWPOS_UNDEFINED,
                              WINDOW_WIDTH, WINDOW_HEIGHT,
                              SDL_WINDOW_SHOWN);
    if (!window)
    {
        printf("Window creation failed: %s\n", SDL_GetError());
        TTF_Quit();
        SDL_Quit();
        return 1;
    }

    renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED);
    if (!renderer)
    {
        printf("Renderer creation failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(window);
        TTF_Quit();
        SDL_Quit();
        return 1;
    }

    // Load font from embedded data
    SDL_RWops *font_rw = SDL_RWFromConstMem(roboto_mono_regular_ttf, roboto_mono_regular_ttf_len);
    if (!font_rw)
    {
        printf("Failed to create RWops for font: %s\n", SDL_GetError());
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        TTF_Quit();
        SDL_Quit();
        return 1;
    }

    font = TTF_OpenFontRW(font_rw, 1, 24); // 1 means SDL_RWops will be auto-freed
    if (!font)
    {
        printf("Font loading failed: %s\n", TTF_GetError());
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        TTF_Quit();
        SDL_Quit();
        return 1;
    }

    // Initialize scene system
    init_scene_system(&scene_state, renderer);

    SDL_Event event;
    int running = 1;
    Uint32 last_time = SDL_GetTicks();
    double rotation_angle = 0.0;

    while (running)
    {
        while (SDL_PollEvent(&event))
        {
            if (event.type == SDL_QUIT)
            {
                running = 0;
            }
            else if (event.type == SDL_KEYDOWN)
            {
                if (event.key.keysym.sym == SDLK_SPACE)
                {
                    Scene new_scene = (scene_state.current + 1) % SCENE_COUNT;
                    start_scene_transition(&scene_state, new_scene, renderer, font);
                }
            }
        }

        // Update timing
        Uint32 current_time = SDL_GetTicks();
        float delta_time = (current_time - last_time) / 1000.0f;
        last_time = current_time;

        // Update rotation angle for idle scene
        rotation_angle += delta_time;

        // Update scene transition
        update_scene_transition(&scene_state, delta_time);

        // Render current scene with transition
        render_scene_transition(renderer, &scene_state, font, rotation_angle);

        SDL_RenderPresent(renderer);
        SDL_Delay(16); // Cap at roughly 60 FPS
    }

    // Cleanup scene system
    cleanup_scene_system(&scene_state);

    mosquitto_loop_stop(mosq, true);
    mosquitto_destroy(mosq);
    mosquitto_lib_cleanup();

    TTF_CloseFont(font);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    TTF_Quit();
    SDL_Quit();
    return 0;
}
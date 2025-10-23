/*
 * Protosuit Remote Control - Input Handler Implementation
 */

#include "input.h"
#include "../config.h"
#include <string.h>
#include <stdio.h>

// Button mapping table
static button_map_t default_button_map[] = {
    {PSP_CTRL_UP,       "Up",        false},
    {PSP_CTRL_DOWN,     "Down",      false},
    {PSP_CTRL_LEFT,     "Left",      false},
    {PSP_CTRL_RIGHT,    "Right",     false},
    {PSP_CTRL_CROSS,    "Return",    false},  // Enter
    {PSP_CTRL_CIRCLE,   "Escape",    false},
    {PSP_CTRL_TRIANGLE, "space",     false},
    {PSP_CTRL_SQUARE,   "Control_L", false},
    {PSP_CTRL_START,    "Return",    false},  // Also Enter
    {PSP_CTRL_SELECT,   "Tab",       false},
};

void input_init(input_context_t *ctx) {
    memset(ctx, 0, sizeof(input_context_t));

    // Set up controller
    sceCtrlSetSamplingCycle(0);
    sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);

    // Initialize button map
    ctx->button_map = default_button_map;
    ctx->button_count = sizeof(default_button_map) / sizeof(button_map_t);
    ctx->current_display = DISPLAY_LEFT;
    ctx->frame_counter = 0;
}

int input_poll(input_context_t *ctx, void (*callback)(const char *key, const char *action, const char *display)) {
    int events = 0;

    // Store previous state
    ctx->prev_pad = ctx->pad;

    // Read current state
    sceCtrlReadBufferPositive(&ctx->pad, 1);

    // Increment frame counter
    ctx->frame_counter++;

    // Check for display switch (L/R buttons)
    // L button = left display
    if ((ctx->pad.Buttons & PSP_CTRL_LTRIGGER) && !(ctx->prev_pad.Buttons & PSP_CTRL_LTRIGGER)) {
        ctx->current_display = DISPLAY_LEFT;
        events++;
    }

    // R button = right display
    if ((ctx->pad.Buttons & PSP_CTRL_RTRIGGER) && !(ctx->prev_pad.Buttons & PSP_CTRL_RTRIGGER)) {
        ctx->current_display = DISPLAY_RIGHT;
        events++;
    }

    // Get display string
    const char *display = input_get_display(ctx);

    // Check each mapped button
    for (int i = 0; i < ctx->button_count; i++) {
        button_map_t *btn = &ctx->button_map[i];
        bool currently_pressed = (ctx->pad.Buttons & btn->psp_button) != 0;
        bool was_pressed = btn->pressed;

        // Button pressed (keydown)
        if (currently_pressed && !was_pressed) {
            btn->pressed = true;
            if (callback) {
                callback(btn->key_name, "keydown", display);
            }
            events++;
        }
        // Button released (keyup)
        else if (!currently_pressed && was_pressed) {
            btn->pressed = false;
            if (callback) {
                callback(btn->key_name, "keyup", display);
            }
            events++;
        }
    }

    return events;
}

const char* input_get_display(input_context_t *ctx) {
    return input_display_to_string(ctx->current_display);
}

const char* input_display_to_string(display_t display) {
    return (display == DISPLAY_LEFT) ? "left" : "right";
}

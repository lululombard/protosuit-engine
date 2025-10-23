/*
 * PSP MQTT Controller - Input Handler Header
 */

#ifndef INPUT_H
#define INPUT_H

#include <pspctrl.h>
#include <stdbool.h>

// Display selection
typedef enum {
    DISPLAY_LEFT,
    DISPLAY_RIGHT
} display_t;

// Button mapping entry
typedef struct {
    unsigned int psp_button;
    const char *key_name;
    bool pressed;
} button_map_t;

// Input context
typedef struct {
    SceCtrlData pad;
    SceCtrlData prev_pad;
    display_t current_display;
    button_map_t *button_map;
    int button_count;
    int frame_counter;
} input_context_t;

// Initialize input system
void input_init(input_context_t *ctx);

// Poll input and return events
// Returns number of events generated
int input_poll(input_context_t *ctx, void (*callback)(const char *key, const char *action, const char *display));

// Get current display selection
const char* input_get_display(input_context_t *ctx);

// Get display as string
const char* input_display_to_string(display_t display);

#endif // INPUT_H


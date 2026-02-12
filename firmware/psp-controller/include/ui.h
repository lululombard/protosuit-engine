/*
 * Protosuit Remote Control - UI Header
 */

#ifndef UI_H
#define UI_H

#include "wifi.h"
#include "mqtt.h"
#include "input.h"

// UI context
typedef struct {
    bool initialized;
} ui_context_t;

// Initialize UI subsystem
int ui_init(ui_context_t *ctx);

// Draw the UI
void ui_draw(ui_context_t *ctx, wifi_context_t *wifi, mqtt_context_t *mqtt, input_context_t *input);

// Shutdown UI subsystem
void ui_shutdown(ui_context_t *ctx);

#endif // UI_H

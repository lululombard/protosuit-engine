/*
 * PSP MQTT Controller - UI Implementation
 */

#include "ui.h"
#include <pspgu.h>
#include <pspdisplay.h>
#include <pspkernel.h>
#include <string.h>
#include <stdio.h>

// Simple debug screen functions (basic text rendering)
#define SCREEN_WIDTH 480
#define SCREEN_HEIGHT 272
#define LINE_HEIGHT 10

// Color definitions (ABGR format for PSP)
#define COLOR_WHITE     0xFFFFFFFF
#define COLOR_GREEN     0xFF00FF00
#define COLOR_YELLOW    0xFF00FFFF
#define COLOR_RED       0xFF0000FF
#define COLOR_CYAN      0xFFFFFF00
#define COLOR_GRAY      0xFF808080

// External pspDebugScreen functions (available in PSPSDK)
extern void pspDebugScreenInit();
extern void pspDebugScreenClear();
extern void pspDebugScreenSetXY(int x, int y);
extern void pspDebugScreenSetTextColor(unsigned int color);
extern void pspDebugScreenPrintf(const char *fmt, ...);

int ui_init(ui_context_t *ctx) {
    memset(ctx, 0, sizeof(ui_context_t));

    // Initialize debug screen for simple text output
    pspDebugScreenInit();

    ctx->initialized = true;
    return 0;
}

void ui_draw(ui_context_t *ctx, wifi_context_t *wifi, mqtt_context_t *mqtt, input_context_t *input) {
    if (!ctx->initialized) {
        return;
    }

    // Clear screen
    pspDebugScreenClear();

    // Title
    pspDebugScreenSetXY(0, 0);
    pspDebugScreenSetTextColor(COLOR_CYAN);
    pspDebugScreenPrintf("========================================");
    pspDebugScreenSetXY(0, 1);
    pspDebugScreenPrintf("  PSP MQTT Controller - Protosuit Engine");
    pspDebugScreenSetXY(0, 2);
    pspDebugScreenPrintf("========================================");

    // WiFi Status
    pspDebugScreenSetXY(0, 4);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("WiFi: ");

    switch (wifi_get_state(wifi)) {
        case WIFI_DISCONNECTED:
            pspDebugScreenSetTextColor(COLOR_GRAY);
            pspDebugScreenPrintf("Disconnected");
            break;
        case WIFI_CONNECTING:
            pspDebugScreenSetTextColor(COLOR_YELLOW);
            pspDebugScreenPrintf("Connecting...");
            break;
        case WIFI_CONNECTED:
            pspDebugScreenSetTextColor(COLOR_GREEN);
            pspDebugScreenPrintf("Connected");
            if (wifi_get_ip(wifi)) {
                pspDebugScreenPrintf(" (%s)", wifi_get_ip(wifi));
            }
            break;
        case WIFI_ERROR:
            pspDebugScreenSetTextColor(COLOR_RED);
            pspDebugScreenPrintf("Error");
            break;
    }

    // MQTT Status
    pspDebugScreenSetXY(0, 5);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("MQTT: ");

    switch (mqtt_get_state(mqtt)) {
        case MQTT_DISCONNECTED:
            pspDebugScreenSetTextColor(COLOR_GRAY);
            pspDebugScreenPrintf("Disconnected");
            break;
        case MQTT_CONNECTING:
            pspDebugScreenSetTextColor(COLOR_YELLOW);
            pspDebugScreenPrintf("Connecting...");
            break;
        case MQTT_CONNECTED:
            pspDebugScreenSetTextColor(COLOR_GREEN);
            pspDebugScreenPrintf("Connected");
            break;
        case MQTT_ERROR:
            pspDebugScreenSetTextColor(COLOR_RED);
            pspDebugScreenPrintf("Error");
            break;
    }

    // Display Selection
    pspDebugScreenSetXY(0, 7);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("Display: ");
    pspDebugScreenSetTextColor(COLOR_CYAN);
    const char *display = input_get_display(input);
    pspDebugScreenPrintf("%s", display);
    pspDebugScreenSetTextColor(COLOR_GRAY);
    pspDebugScreenPrintf("  [L=Left] [R=Right]");

    // Button mappings
    pspDebugScreenSetXY(0, 9);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("Button Mappings:");

    pspDebugScreenSetXY(0, 10);
    pspDebugScreenSetTextColor(COLOR_GRAY);
    pspDebugScreenPrintf("  D-Pad      = Arrow Keys");

    pspDebugScreenSetXY(0, 11);
    pspDebugScreenPrintf("  Cross (X)  = Enter");

    pspDebugScreenSetXY(0, 12);
    pspDebugScreenPrintf("  Circle (O) = Escape");

    pspDebugScreenSetXY(0, 13);
    pspDebugScreenPrintf("  Triangle   = Space");

    pspDebugScreenSetXY(0, 14);
    pspDebugScreenPrintf("  Square     = Control");

    pspDebugScreenSetXY(0, 15);
    pspDebugScreenPrintf("  Start      = Enter");

    pspDebugScreenSetXY(0, 16);
    pspDebugScreenPrintf("  Select     = Tab");

    // Active buttons indicator
    pspDebugScreenSetXY(0, 18);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("Active: ");

    bool any_pressed = false;
    pspDebugScreenSetTextColor(COLOR_GREEN);

    if (input->pad.Buttons & PSP_CTRL_UP) {
        pspDebugScreenPrintf("UP ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_DOWN) {
        pspDebugScreenPrintf("DOWN ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_LEFT) {
        pspDebugScreenPrintf("LEFT ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_RIGHT) {
        pspDebugScreenPrintf("RIGHT ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_CROSS) {
        pspDebugScreenPrintf("X ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_CIRCLE) {
        pspDebugScreenPrintf("O ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_TRIANGLE) {
        pspDebugScreenPrintf("TRI ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_SQUARE) {
        pspDebugScreenPrintf("SQ ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_START) {
        pspDebugScreenPrintf("START ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_SELECT) {
        pspDebugScreenPrintf("SELECT ");
        any_pressed = true;
    }

    if (!any_pressed) {
        pspDebugScreenSetTextColor(COLOR_GRAY);
        pspDebugScreenPrintf("(none)");
    }

    // Footer
    pspDebugScreenSetXY(0, 32);
    pspDebugScreenSetTextColor(COLOR_GRAY);
    pspDebugScreenPrintf("Press HOME to exit");
}

void ui_shutdown(ui_context_t *ctx) {
    ctx->initialized = false;
}


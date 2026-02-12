/*
 * Protosuit Remote Control - UI Implementation
 */

#include "ui.h"
#include <pspgu.h>
#include <pspdisplay.h>
#include <pspkernel.h>
#include <pspdebug.h>
#include <psppower.h>
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

int ui_init(ui_context_t *ctx) {
    memset(ctx, 0, sizeof(ui_context_t));

    // Initialize debug screen for simple text output
    pspDebugScreenInit();

    // Enable VSync to prevent tearing
    sceDisplayWaitVblankStart();

    ctx->initialized = true;
    return 0;
}

void ui_draw(ui_context_t *ctx, Wi-Fi_context_t *Wi-Fi, mqtt_context_t *mqtt, input_context_t *input) {
    if (!ctx->initialized) {
        return;
    }

    // Only clear and redraw title on first call
    static int first_draw = 1;
    if (first_draw) {
        pspDebugScreenClear();
        // Title
        pspDebugScreenSetXY(0, 0);
        pspDebugScreenSetTextColor(COLOR_CYAN);
        pspDebugScreenPrintf("========================================");
        pspDebugScreenSetXY(0, 1);
        pspDebugScreenPrintf("      Protosuit Remote Control");
        pspDebugScreenSetXY(0, 2);
        pspDebugScreenPrintf("========================================");
        first_draw = 0;
    }

    // Wi-Fi Status - clear line and redraw
    pspDebugScreenSetXY(0, 4);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("Wi-Fi: ");

    switch (Wi-Fi_get_state(Wi-Fi)) {
        case Wi-Fi_DISCONNECTED:
            pspDebugScreenSetTextColor(COLOR_GRAY);
            pspDebugScreenPrintf("Disconnected                         ");
            break;
        case Wi-Fi_CONNECTING:
            pspDebugScreenSetTextColor(COLOR_YELLOW);
            pspDebugScreenPrintf("Connecting...                        ");
            break;
        case Wi-Fi_CONNECTED:
            pspDebugScreenSetTextColor(COLOR_GREEN);
            pspDebugScreenPrintf("Connected");
            if (Wi-Fi_get_ip(Wi-Fi)) {
                pspDebugScreenPrintf(" (%s)                  ", Wi-Fi_get_ip(Wi-Fi));
            } else {
                pspDebugScreenPrintf("                                     ");
            }
            break;
        case Wi-Fi_ERROR:
            pspDebugScreenSetTextColor(COLOR_RED);
            pspDebugScreenPrintf("Error                                ");
            break;
    }

    // MQTT Status - clear line and redraw
    pspDebugScreenSetXY(0, 5);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("MQTT: ");

    switch (mqtt_get_state(mqtt)) {
        case MQTT_DISCONNECTED:
            pspDebugScreenSetTextColor(COLOR_GRAY);
            pspDebugScreenPrintf("Disconnected                         ");
            break;
        case MQTT_CONNECTING:
            pspDebugScreenSetTextColor(COLOR_YELLOW);
            pspDebugScreenPrintf("Connecting...                        ");
            break;
        case MQTT_CONNECTED:
            pspDebugScreenSetTextColor(COLOR_GREEN);
            pspDebugScreenPrintf("Connected                            ");
            break;
        case MQTT_ERROR:
            pspDebugScreenSetTextColor(COLOR_RED);
            pspDebugScreenPrintf("Error                                ");
            break;
    }

    // Battery Status - like PSP-FTPD
    pspDebugScreenSetXY(0, 6);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("Battery: ");

    if (scePowerIsBatteryExist()) {
        int percent = scePowerGetBatteryLifePercent();
        int charging = scePowerIsPowerOnline();

        // Color based on battery level
        if (percent < 15) {
            pspDebugScreenSetTextColor(COLOR_RED);
        } else if (percent < 30) {
            pspDebugScreenSetTextColor(COLOR_YELLOW);
        } else {
            pspDebugScreenSetTextColor(COLOR_GREEN);
        }

        pspDebugScreenPrintf("%d%%", percent);

        if (charging) {
            pspDebugScreenSetTextColor(COLOR_CYAN);
            pspDebugScreenPrintf(" (Charging)");
        } else {
            // Show remaining time if not charging
            int time_left = scePowerGetBatteryLifeTime();
            if (time_left >= 0) {
                pspDebugScreenSetTextColor(COLOR_GRAY);
                pspDebugScreenPrintf(" (%dh%02d)", time_left / 60, time_left % 60);
            }
        }
        pspDebugScreenPrintf("                    ");
    } else {
        pspDebugScreenSetTextColor(COLOR_GRAY);
        pspDebugScreenPrintf("No battery                           ");
    }

    // Display Selection - clear line and redraw
    pspDebugScreenSetXY(0, 8);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("Display: ");
    pspDebugScreenSetTextColor(COLOR_CYAN);
    const char *display = input_get_display(input);
    pspDebugScreenPrintf("%-10s", display);
    pspDebugScreenSetTextColor(COLOR_GRAY);
    pspDebugScreenPrintf("  [L=Left] [R=Right]        ");

    // Button mappings - only draw once
    static int mappings_drawn = 0;
    if (!mappings_drawn) {
        pspDebugScreenSetXY(0, 9);
        pspDebugScreenSetTextColor(COLOR_WHITE);
        pspDebugScreenPrintf("Button Mappings:");

        pspDebugScreenSetXY(0, 10);
        pspDebugScreenSetTextColor(COLOR_GRAY);
        pspDebugScreenPrintf("  D-Pad      = Arrow Keys");

        pspDebugScreenSetXY(0, 11);
        pspDebugScreenPrintf("  Cross (X)  = A");

        pspDebugScreenSetXY(0, 12);
        pspDebugScreenPrintf("  Circle (O) = B");

        pspDebugScreenSetXY(0, 32);
        pspDebugScreenSetTextColor(COLOR_GRAY);
        pspDebugScreenPrintf("Press HOME to exit");

        mappings_drawn = 1;
    }

    // Active buttons indicator - clear entire line first
    pspDebugScreenSetXY(0, 18);
    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("Active: ");

    bool any_pressed = false;
    char button_str[60] = "";

    if (input->pad.Buttons & PSP_CTRL_UP) {
        strcat(button_str, "UP ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_DOWN) {
        strcat(button_str, "DOWN ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_LEFT) {
        strcat(button_str, "LEFT ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_RIGHT) {
        strcat(button_str, "RIGHT ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_CROSS) {
        strcat(button_str, "X ");
        any_pressed = true;
    }
    if (input->pad.Buttons & PSP_CTRL_CIRCLE) {
        strcat(button_str, "O ");
        any_pressed = true;
    }

    if (any_pressed) {
        pspDebugScreenSetTextColor(COLOR_GREEN);
        pspDebugScreenPrintf("%-50s", button_str);
    } else {
        pspDebugScreenSetTextColor(COLOR_GRAY);
        pspDebugScreenPrintf("(none)%-44s", "");
    }
}

void ui_shutdown(ui_context_t *ctx) {
    ctx->initialized = false;
}

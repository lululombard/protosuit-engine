/*
 * Protosuit Remote Control - Main Application
 *
 * A PSP homebrew app that sends MQTT commands to control protosuit-engine
 */

#include <pspkernel.h>
#include <pspdebug.h>
#include <pspdisplay.h>
#include <pspctrl.h>
#include <psppower.h>
#include <stdio.h>
#include <string.h>

#include "Wi-Fi.h"
#include "Wi-Fi_menu.h"
#include "mqtt.h"
#include "input.h"
#include "ui.h"
#include "config_loader.h"
#include "../config.h"

PSP_MODULE_INFO("Protosuit_Remote", 0, 1, 0);
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER | THREAD_ATTR_VFPU);

// Global contexts
static Wi-Fi_context_t Wi-Fi_ctx;
static mqtt_context_t mqtt_ctx;
static input_context_t input_ctx;
static ui_context_t ui_ctx;

// Running flag
static volatile int running = 1;

// Exit callback
int exit_callback(int arg1, int arg2, void *common) {
    running = 0;
    return 0;
}

// Callback thread
int callback_thread(SceSize args, void *argp) {
    int cbid = sceKernelCreateCallback("Exit Callback", exit_callback, NULL);
    sceKernelRegisterExitCallback(cbid);
    sceKernelSleepThreadCB();
    return 0;
}

// Setup callbacks
int setup_callbacks(void) {
    int thid = sceKernelCreateThread("update_thread", callback_thread, 0x11, 0xFA0, 0, 0);
    if (thid >= 0) {
        sceKernelStartThread(thid, 0, 0);
    }
    return thid;
}

// Global config for callback
static app_config_t *g_app_config = NULL;

// Input event callback - sends MQTT message
void input_event_callback(const char *key, const char *action, const char *display) {
    if (!mqtt_is_connected(&mqtt_ctx) || !g_app_config) {
        return;
    }

    // Build JSON message: {"key":"Up","action":"keydown","display":"left"}
    char payload[128];
    snprintf(payload, sizeof(payload),
             "{\"key\":\"%s\",\"action\":\"%s\",\"display\":\"%s\"}",
             key, action, display);

    // Publish to MQTT
    mqtt_publish(&mqtt_ctx, g_app_config->mqtt_topic, payload);
}

int main(int argc, char *argv[]) {
    // Setup callbacks for clean exit
    setup_callbacks();

    // Lock CPU speed for better performance and power efficiency
    scePowerSetClockFrequency(333, 333, 166);

    // Initialize UI
    if (ui_init(&ui_ctx) < 0) {
        sceKernelExitGame();
        return -1;
    }

    // Load configuration
    app_config_t app_config;
    int config_loaded = load_config(&app_config);
    g_app_config = &app_config;

    if (!config_loaded) {
        // No config file found, create a default one
        pspDebugScreenPrintf("Creating default config.txt...\n");
        save_default_config();
        pspDebugScreenPrintf("Edit ms0:/PSP/GAME/ProtosuitRemote/config.txt\n");
        pspDebugScreenPrintf("Using default settings for now...\n");
        sceKernelDelayThread(2000000);
    }

    // Initialize input
    input_init(&input_ctx);

    // Always show Wi-Fi profile selection menu (like PSP ftpd)
    int selected_profile = 1;
    if (Wi-Fi_menu_select_profile(&selected_profile) < 0) {
        pspDebugScreenPrintf("Wi-Fi setup cancelled\n");
        sceKernelDelayThread(2000000);
        sceKernelExitGame();
        return -1;
    }

    // Initialize Wi-Fi with selected profile
    if (Wi-Fi_init(&Wi-Fi_ctx, selected_profile) < 0) {
        pspDebugScreenPrintf("Failed to initialize Wi-Fi\n");
        sceKernelDelayThread(3000000);
        sceKernelExitGame();
        return -1;
    }

    // Connect and wait for Wi-Fi (with progress display)
    if (Wi-Fi_menu_wait_for_connection(&Wi-Fi_ctx) < 0) {
        pspDebugScreenPrintf("Wi-Fi connection cancelled\n");
        sceKernelDelayThread(2000000);
        sceKernelExitGame();
        return -1;
    }

    // Initialize MQTT
    mqtt_init(&mqtt_ctx, app_config.mqtt_broker_ip, app_config.mqtt_broker_port,
              app_config.mqtt_client_id, app_config.mqtt_keepalive);

    // Connection state tracking
    bool Wi-Fi_connected = false;
    bool mqtt_connected = false;
    uint32_t last_ui_update = 0;
    uint32_t last_Wi-Fi_retry = 0;
    uint32_t last_mqtt_retry = 0;

    // Main loop
    while (running) {
        uint32_t current_time = sceKernelGetSystemTimeLow();

        // Wi-Fi connection management
        if (!Wi-Fi_connected) {
            if (current_time - last_Wi-Fi_retry > Wi-Fi_RETRY_DELAY) {
                Wi-Fi_connect(&Wi-Fi_ctx);
                last_Wi-Fi_retry = current_time;
            }
        }

        Wi-Fi_connected = Wi-Fi_is_connected(&Wi-Fi_ctx);

        // MQTT connection management
        if (Wi-Fi_connected && !mqtt_connected) {
            if (current_time - last_mqtt_retry > MQTT_RETRY_DELAY) {
                mqtt_connect(&mqtt_ctx);
                last_mqtt_retry = current_time;
            }
        }

        mqtt_connected = mqtt_is_connected(&mqtt_ctx);

        // Keep MQTT connection alive
        if (mqtt_connected) {
            mqtt_keepalive(&mqtt_ctx);
        }

        // Poll input and send MQTT messages
        if (mqtt_connected) {
            input_poll(&input_ctx, input_event_callback);
        } else {
            // Still poll input to update display selection
            input_poll(&input_ctx, NULL);
        }

        // Update UI periodically
        if (current_time - last_ui_update > UI_REFRESH_DELAY) {
            ui_draw(&ui_ctx, &Wi-Fi_ctx, &mqtt_ctx, &input_ctx);
            last_ui_update = current_time;
        }

        // Small delay to prevent excessive CPU usage
        sceKernelDelayThread(INPUT_POLL_DELAY);
    }

    // Cleanup
    mqtt_disconnect(&mqtt_ctx);
    Wi-Fi_shutdown(&Wi-Fi_ctx);
    ui_shutdown(&ui_ctx);

    sceKernelExitGame();
    return 0;
}

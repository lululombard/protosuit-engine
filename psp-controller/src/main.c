/*
 * PSP MQTT Controller - Main Application
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

#include "wifi.h"
#include "mqtt.h"
#include "input.h"
#include "ui.h"
#include "../config.h"

PSP_MODULE_INFO("PSP_MQTT_Controller", 0, 1, 0);
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER | THREAD_ATTR_VFPU);

// Global contexts
static wifi_context_t wifi_ctx;
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

// Input event callback - sends MQTT message
void input_event_callback(const char *key, const char *action, const char *display) {
    if (!mqtt_is_connected(&mqtt_ctx)) {
        return;
    }

    // Build JSON message: {"key":"Up","action":"keydown","display":"left"}
    char payload[128];
    snprintf(payload, sizeof(payload),
             "{\"key\":\"%s\",\"action\":\"%s\",\"display\":\"%s\"}",
             key, action, display);

    // Publish to MQTT
    mqtt_publish(&mqtt_ctx, MQTT_TOPIC, payload);
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

    // Initialize input
    input_init(&input_ctx);

    // Initialize WiFi
    pspDebugScreenPrintf("Initializing WiFi...\n");
    if (wifi_init(&wifi_ctx, WIFI_SSID, WIFI_PASSWORD) < 0) {
        pspDebugScreenPrintf("Failed to initialize WiFi\n");
        sceKernelDelayThread(3000000);
        sceKernelExitGame();
        return -1;
    }

    // Initialize MQTT
    mqtt_init(&mqtt_ctx, MQTT_BROKER_IP, MQTT_BROKER_PORT,
              MQTT_CLIENT_ID, MQTT_KEEPALIVE);

    // Connection state tracking
    bool wifi_connected = false;
    bool mqtt_connected = false;
    uint32_t last_ui_update = 0;
    uint32_t last_wifi_retry = 0;
    uint32_t last_mqtt_retry = 0;

    // Main loop
    while (running) {
        uint32_t current_time = sceKernelGetSystemTimeLow();

        // WiFi connection management
        if (!wifi_connected) {
            if (current_time - last_wifi_retry > WIFI_RETRY_DELAY) {
                wifi_connect(&wifi_ctx);
                last_wifi_retry = current_time;
            }
        }

        wifi_connected = wifi_is_connected(&wifi_ctx);

        // MQTT connection management
        if (wifi_connected && !mqtt_connected) {
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
            ui_draw(&ui_ctx, &wifi_ctx, &mqtt_ctx, &input_ctx);
            last_ui_update = current_time;
        }

        // Small delay to prevent excessive CPU usage
        sceKernelDelayThread(INPUT_POLL_DELAY);
    }

    // Cleanup
    mqtt_disconnect(&mqtt_ctx);
    wifi_shutdown(&wifi_ctx);
    ui_shutdown(&ui_ctx);

    sceKernelExitGame();
    return 0;
}


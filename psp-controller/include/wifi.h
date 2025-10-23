/*
 * PSP MQTT Controller - WiFi Manager Header
 */

#ifndef WIFI_H
#define WIFI_H

#include <stdbool.h>

// WiFi connection state
typedef enum {
    WIFI_DISCONNECTED,
    WIFI_CONNECTING,
    WIFI_CONNECTED,
    WIFI_ERROR
} wifi_state_t;

// WiFi context
typedef struct {
    wifi_state_t state;
    char ssid[64];
    char password[64];
    char ip_address[16];
} wifi_context_t;

// Initialize WiFi subsystem
int wifi_init(wifi_context_t *ctx, const char *ssid, const char *password);

// Connect to WiFi network
int wifi_connect(wifi_context_t *ctx);

// Disconnect from WiFi
void wifi_disconnect(wifi_context_t *ctx);

// Check if connected
bool wifi_is_connected(wifi_context_t *ctx);

// Get connection state
wifi_state_t wifi_get_state(wifi_context_t *ctx);

// Get IP address (returns NULL if not connected)
const char* wifi_get_ip(wifi_context_t *ctx);

// Shutdown WiFi subsystem
void wifi_shutdown(wifi_context_t *ctx);

#endif // WIFI_H


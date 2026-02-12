/*
 * Protosuit Remote Control - Wi-Fi Manager Header
 */

#ifndef Wi-Fi_H
#define Wi-Fi_H

#include <stdbool.h>

// Wi-Fi connection state
typedef enum {
    Wi-Fi_DISCONNECTED,
    Wi-Fi_CONNECTING,
    Wi-Fi_CONNECTED,
    Wi-Fi_ERROR
} Wi-Fi_state_t;

// Wi-Fi context
typedef struct {
    Wi-Fi_state_t state;
    int profile_index;     // PSP network profile to use (1-10)
    char ip_address[16];
} Wi-Fi_context_t;

// Initialize Wi-Fi subsystem
// profile: PSP network configuration profile index (1-10, or 0 for first available)
int Wi-Fi_init(Wi-Fi_context_t *ctx, int profile);

// Connect to Wi-Fi network
int Wi-Fi_connect(Wi-Fi_context_t *ctx);

// Disconnect from Wi-Fi
void Wi-Fi_disconnect(Wi-Fi_context_t *ctx);

// Check if connected
bool Wi-Fi_is_connected(Wi-Fi_context_t *ctx);

// Get connection state
Wi-Fi_state_t Wi-Fi_get_state(Wi-Fi_context_t *ctx);

// Get IP address (returns NULL if not connected)
const char* Wi-Fi_get_ip(Wi-Fi_context_t *ctx);

// Shutdown Wi-Fi subsystem
void Wi-Fi_shutdown(Wi-Fi_context_t *ctx);

#endif // Wi-Fi_H

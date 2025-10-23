/*
 * PSP MQTT Controller - MQTT Client Header
 */

#ifndef MQTT_H
#define MQTT_H

#include <stdint.h>
#include <stdbool.h>

// MQTT connection state
typedef enum {
    MQTT_DISCONNECTED,
    MQTT_CONNECTING,
    MQTT_CONNECTED,
    MQTT_ERROR
} mqtt_state_t;

// MQTT context
typedef struct {
    int socket;
    mqtt_state_t state;
    uint16_t packet_id;
    uint32_t last_ping_time;
    char client_id[32];
    char broker_ip[16];
    int broker_port;
    int keepalive;
} mqtt_context_t;

// Initialize MQTT context
void mqtt_init(mqtt_context_t *ctx, const char *broker_ip, int broker_port,
               const char *client_id, int keepalive);

// Connect to MQTT broker
int mqtt_connect(mqtt_context_t *ctx);

// Disconnect from MQTT broker
void mqtt_disconnect(mqtt_context_t *ctx);

// Publish a message (QoS 0)
int mqtt_publish(mqtt_context_t *ctx, const char *topic, const char *payload);

// Keep connection alive (call periodically)
int mqtt_keepalive(mqtt_context_t *ctx);

// Check if connected
bool mqtt_is_connected(mqtt_context_t *ctx);

// Get connection state
mqtt_state_t mqtt_get_state(mqtt_context_t *ctx);

#endif // MQTT_H


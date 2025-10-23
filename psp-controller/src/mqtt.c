/*
 * PSP MQTT Controller - Minimal MQTT Client Implementation
 * Supports MQTT 3.1.1 protocol (CONNECT, PUBLISH, PINGREQ only)
 */

#include "mqtt.h"
#include "../config.h"
#include <string.h>
#include <stdio.h>
#include <pspnet_inet.h>
#include <psputility.h>
#include <psprtc.h>

// MQTT packet types
#define MQTT_CONNECT     0x10
#define MQTT_CONNACK     0x20
#define MQTT_PUBLISH     0x30
#define MQTT_PINGREQ     0xC0
#define MQTT_PINGRESP    0xD0
#define MQTT_DISCONNECT  0xE0

// Helper function to encode remaining length
static int encode_remaining_length(uint8_t *buf, int length) {
    int pos = 0;
    do {
        uint8_t byte = length % 128;
        length /= 128;
        if (length > 0) {
            byte |= 0x80;
        }
        buf[pos++] = byte;
    } while (length > 0);
    return pos;
}

// Helper function to write uint16 in MSB order
static void write_uint16(uint8_t *buf, uint16_t value) {
    buf[0] = (value >> 8) & 0xFF;
    buf[1] = value & 0xFF;
}

// Helper function to write string with length prefix
static int write_string(uint8_t *buf, const char *str) {
    int len = strlen(str);
    write_uint16(buf, len);
    memcpy(buf + 2, str, len);
    return len + 2;
}

void mqtt_init(mqtt_context_t *ctx, const char *broker_ip, int broker_port,
               const char *client_id, int keepalive) {
    memset(ctx, 0, sizeof(mqtt_context_t));
    strncpy(ctx->client_id, client_id, sizeof(ctx->client_id) - 1);
    strncpy(ctx->broker_ip, broker_ip, sizeof(ctx->broker_ip) - 1);
    ctx->broker_port = broker_port;
    ctx->keepalive = keepalive;
    ctx->socket = -1;
    ctx->state = MQTT_DISCONNECTED;
    ctx->packet_id = 1;
}

int mqtt_connect(mqtt_context_t *ctx) {
    if (ctx->state == MQTT_CONNECTED) {
        return 0; // Already connected
    }

    ctx->state = MQTT_CONNECTING;

    // Create socket
    ctx->socket = sceNetInetSocket(AF_INET, SOCK_STREAM, 0);
    if (ctx->socket < 0) {
        ctx->state = MQTT_ERROR;
        return -1;
    }

    // Set non-blocking mode
    int val = 1;
    sceNetInetSetsockopt(ctx->socket, SOL_SOCKET, SO_NONBLOCK, &val, sizeof(val));

    // Connect to broker
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = sceNetHtons(ctx->broker_port);
    sceNetInetInetAton(ctx->broker_ip, &addr.sin_addr);

    int result = sceNetInetConnect(ctx->socket, (struct sockaddr *)&addr, sizeof(addr));
    if (result < 0 && result != 0x80410709) { // EINPROGRESS is ok
        sceNetInetClose(ctx->socket);
        ctx->socket = -1;
        ctx->state = MQTT_ERROR;
        return -1;
    }

    // Wait for connection (with timeout)
    sceKernelDelayThread(100000); // 100ms

    // Build CONNECT packet
    uint8_t packet[256];
    int pos = 0;

    // Fixed header
    packet[pos++] = MQTT_CONNECT;

    // Calculate remaining length
    int protocol_name_len = 4; // "MQTT"
    int client_id_len = strlen(ctx->client_id);
    int remaining_length = 2 + protocol_name_len + 1 + 1 + 2 + 2 + client_id_len;

    pos += encode_remaining_length(&packet[pos], remaining_length);

    // Variable header
    pos += write_string(&packet[pos], "MQTT");     // Protocol name
    packet[pos++] = 0x04;                           // Protocol level (3.1.1)
    packet[pos++] = 0x02;                           // Connect flags (clean session)
    write_uint16(&packet[pos], ctx->keepalive);    // Keep alive
    pos += 2;

    // Payload
    pos += write_string(&packet[pos], ctx->client_id);

    // Send CONNECT packet
    int sent = sceNetInetSend(ctx->socket, packet, pos, 0);
    if (sent != pos) {
        sceNetInetClose(ctx->socket);
        ctx->socket = -1;
        ctx->state = MQTT_ERROR;
        return -1;
    }

    // Wait for CONNACK
    uint8_t response[4];
    sceKernelDelayThread(200000); // 200ms
    int received = sceNetInetRecv(ctx->socket, response, sizeof(response), 0);

    if (received >= 4 && response[0] == MQTT_CONNACK && response[3] == 0x00) {
        ctx->state = MQTT_CONNECTED;
        u64 tick;
        sceRtcGetCurrentTick(&tick);
        ctx->last_ping_time = tick / 1000000; // Convert to seconds
        return 0;
    }

    sceNetInetClose(ctx->socket);
    ctx->socket = -1;
    ctx->state = MQTT_ERROR;
    return -1;
}

void mqtt_disconnect(mqtt_context_t *ctx) {
    if (ctx->socket >= 0) {
        // Send DISCONNECT packet
        uint8_t packet[2] = {MQTT_DISCONNECT, 0x00};
        sceNetInetSend(ctx->socket, packet, 2, 0);
        sceNetInetClose(ctx->socket);
        ctx->socket = -1;
    }
    ctx->state = MQTT_DISCONNECTED;
}

int mqtt_publish(mqtt_context_t *ctx, const char *topic, const char *payload) {
    if (ctx->state != MQTT_CONNECTED) {
        return -1;
    }

    int topic_len = strlen(topic);
    int payload_len = strlen(payload);
    int remaining_length = 2 + topic_len + payload_len;

    uint8_t packet[512];
    int pos = 0;

    // Fixed header (QoS 0, no retain)
    packet[pos++] = MQTT_PUBLISH;
    pos += encode_remaining_length(&packet[pos], remaining_length);

    // Variable header
    pos += write_string(&packet[pos], topic);

    // Payload
    memcpy(&packet[pos], payload, payload_len);
    pos += payload_len;

    // Send packet
    int sent = sceNetInetSend(ctx->socket, packet, pos, 0);
    if (sent != pos) {
        ctx->state = MQTT_ERROR;
        return -1;
    }

    return 0;
}

int mqtt_keepalive(mqtt_context_t *ctx) {
    if (ctx->state != MQTT_CONNECTED) {
        return -1;
    }

    u64 tick;
    sceRtcGetCurrentTick(&tick);
    uint32_t current_time = tick / 1000000; // Convert to seconds

    // Send PINGREQ if needed
    if (current_time - ctx->last_ping_time >= ctx->keepalive / 2) {
        uint8_t packet[2] = {MQTT_PINGREQ, 0x00};
        int sent = sceNetInetSend(ctx->socket, packet, 2, 0);
        if (sent != 2) {
            ctx->state = MQTT_ERROR;
            return -1;
        }
        ctx->last_ping_time = current_time;
    }

    return 0;
}

bool mqtt_is_connected(mqtt_context_t *ctx) {
    return ctx->state == MQTT_CONNECTED;
}

mqtt_state_t mqtt_get_state(mqtt_context_t *ctx) {
    return ctx->state;
}


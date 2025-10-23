/*
 * PSP MQTT Controller - WiFi Manager Implementation
 */

#include "wifi.h"
#include "../config.h"
#include <string.h>
#include <stdio.h>
#include <pspnet.h>
#include <pspnet_inet.h>
#include <pspnet_apctl.h>
#include <psputility.h>
#include <pspkernel.h>

int wifi_init(wifi_context_t *ctx, const char *ssid, const char *password) {
    memset(ctx, 0, sizeof(wifi_context_t));
    strncpy(ctx->ssid, ssid, sizeof(ctx->ssid) - 1);
    strncpy(ctx->password, password, sizeof(ctx->password) - 1);
    ctx->state = WIFI_DISCONNECTED;

    // Load network modules
    int ret = sceUtilityLoadNetModule(PSP_NET_MODULE_COMMON);
    if (ret < 0) return ret;

    ret = sceUtilityLoadNetModule(PSP_NET_MODULE_INET);
    if (ret < 0) return ret;

    // Initialize networking
    ret = sceNetInit(128*1024, 42, 4*1024, 42, 4*1024);
    if (ret < 0 && ret != 0x80410A05) { // Already initialized is OK
        return ret;
    }

    ret = sceNetInetInit();
    if (ret < 0 && ret != 0x80410A05) {
        return ret;
    }

    ret = sceNetApctlInit(0x1800, 42);
    if (ret < 0 && ret != 0x80410A05) {
        return ret;
    }

    return 0;
}

int wifi_connect(wifi_context_t *ctx) {
    if (ctx->state == WIFI_CONNECTED) {
        return 0; // Already connected
    }

    ctx->state = WIFI_CONNECTING;

    // Try to use first available network profile
    // In a production app, you'd want to scan and match SSID
    int ret = sceNetApctlConnect(1); // Profile 1
    if (ret < 0) {
        ctx->state = WIFI_ERROR;
        return ret;
    }

    // Wait for connection (up to 10 seconds)
    int timeout = 100; // 10 seconds (100 * 100ms)
    while (timeout-- > 0) {
        int state;
        ret = sceNetApctlGetState(&state);
        if (ret < 0) {
            ctx->state = WIFI_ERROR;
            return ret;
        }

        if (state == PSP_NET_APCTL_STATE_GOT_IP) {
            // Get IP address
            union SceNetApctlInfo info;
            ret = sceNetApctlGetInfo(PSP_NET_APCTL_INFO_IP, &info);
            if (ret == 0) {
                strncpy(ctx->ip_address, info.ip, sizeof(ctx->ip_address) - 1);
            }
            ctx->state = WIFI_CONNECTED;
            return 0;
        }

        sceKernelDelayThread(100000); // 100ms
    }

    ctx->state = WIFI_ERROR;
    return -1;
}

void wifi_disconnect(wifi_context_t *ctx) {
    if (ctx->state == WIFI_CONNECTED || ctx->state == WIFI_CONNECTING) {
        sceNetApctlDisconnect();
    }
    ctx->state = WIFI_DISCONNECTED;
}

bool wifi_is_connected(wifi_context_t *ctx) {
    if (ctx->state != WIFI_CONNECTED) {
        return false;
    }

    // Verify we're still connected
    int state;
    int ret = sceNetApctlGetState(&state);
    if (ret < 0 || state != PSP_NET_APCTL_STATE_GOT_IP) {
        ctx->state = WIFI_DISCONNECTED;
        return false;
    }

    return true;
}

wifi_state_t wifi_get_state(wifi_context_t *ctx) {
    return ctx->state;
}

const char* wifi_get_ip(wifi_context_t *ctx) {
    if (ctx->state == WIFI_CONNECTED) {
        return ctx->ip_address;
    }
    return NULL;
}

void wifi_shutdown(wifi_context_t *ctx) {
    wifi_disconnect(ctx);
    sceNetApctlTerm();
    sceNetInetTerm();
    sceNetTerm();
    sceUtilityUnloadNetModule(PSP_NET_MODULE_INET);
    sceUtilityUnloadNetModule(PSP_NET_MODULE_COMMON);
}


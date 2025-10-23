/*
 * Protosuit Remote Control - WiFi Manager Implementation
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

int wifi_init(wifi_context_t *ctx, int profile) {
    memset(ctx, 0, sizeof(wifi_context_t));
    ctx->profile_index = (profile > 0 && profile <= 10) ? profile : 1; // Default to profile 1
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
    // Don't try to connect if already connected
    int state = 0;
    sceNetApctlGetState(&state);
    if (state == PSP_NET_APCTL_STATE_GOT_IP) {
        ctx->state = WIFI_CONNECTED;
        return 0;  // Already connected
    }

    ctx->state = WIFI_CONNECTING;

    // Connect using the configured PSP network profile (1-based index)
    // NOTE: Don't disconnect first - PSP-FTPD doesn't do this
    int ret = sceNetApctlConnect(ctx->profile_index);
    if (ret < 0) {
        // Only set error if not already connecting (error code 0x80410a0b)
        if (ret != 0x80410a0b) {
            ctx->state = WIFI_ERROR;
        }
        return ret;
    }

    return 0; // Return immediately, let caller poll for connection
}

void wifi_disconnect(wifi_context_t *ctx) {
    if (ctx->state == WIFI_CONNECTED || ctx->state == WIFI_CONNECTING) {
        sceNetApctlDisconnect();
    }
    ctx->state = WIFI_DISCONNECTED;
}

bool wifi_is_connected(wifi_context_t *ctx) {
    // Always check actual network state
    int state = 0;
    int ret = sceNetApctlGetState(&state);

    if (ret < 0) {
        ctx->state = WIFI_ERROR;
        return false;
    }

    if (state == PSP_NET_APCTL_STATE_GOT_IP) {
        // Update context state and IP if connected
        ctx->state = WIFI_CONNECTED;

        // Get IP address if we don't have it yet
        if (ctx->ip_address[0] == 0) {
            union SceNetApctlInfo info;
            if (sceNetApctlGetInfo(PSP_NET_APCTL_INFO_IP, &info) == 0) {
                strncpy(ctx->ip_address, info.ip, sizeof(ctx->ip_address) - 1);
            }
        }
        return true;
    }

    // Update state based on actual connection state
    if (state == PSP_NET_APCTL_STATE_DISCONNECTED) {
        ctx->state = WIFI_DISCONNECTED;
    } else if (state > PSP_NET_APCTL_STATE_DISCONNECTED && state < PSP_NET_APCTL_STATE_GOT_IP) {
        ctx->state = WIFI_CONNECTING;
    }

    return false;
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
    // Quick disconnect without waiting
    sceNetApctlDisconnect();
    ctx->state = WIFI_DISCONNECTED;

    // Terminate network stack (don't wait for clean shutdown)
    sceNetApctlTerm();
    sceNetInetTerm();
    sceNetTerm();

    // Unload modules
    sceUtilityUnloadNetModule(PSP_NET_MODULE_INET);
    sceUtilityUnloadNetModule(PSP_NET_MODULE_COMMON);
}

/*
 * Protosuit Remote Control - WiFi Connection Menu
 * Shows available WiFi profiles and waits for connection
 */

#include "wifi_menu.h"
#include <pspdebug.h>
#include <pspctrl.h>
#include <pspkernel.h>
#include <pspdisplay.h>
#include <pspnet_apctl.h>
#include <psputility.h>
#include <string.h>
#include <stdio.h>

// PSP utility functions for querying network profiles are in psputility.h
// sceUtilityCheckNetParam - returns 0 if profile exists
// sceUtilityGetNetParam - gets profile info (name, ssid, etc.)

#define COLOR_WHITE     0xFFFFFFFF
#define COLOR_GREEN     0xFF00FF00
#define COLOR_YELLOW    0xFF00FFFF
#define COLOR_RED       0xFF0000FF
#define COLOR_CYAN      0xFFFFFF00
#define COLOR_GRAY      0xFF808080

int wifi_menu_select_profile(int *selected_profile) {
    SceCtrlData pad, oldPad;
    int current_selection = 0;
    int need_redraw = 1;

    // Structure to hold profile information
    typedef struct {
        int index;
        char name[128];
        char ssid[64];
    } profile_info_t;

    profile_info_t profiles[10];
    int display_count = 0;

    // Enumerate configured profiles (based on PSP-FTPD code)
    for (int i = 1; i <= 10; i++) {
        // Check if this profile is configured
        if (sceUtilityCheckNetParam(i) != 0) {
            continue;  // Profile not configured, skip it
        }

        // Get profile name and SSID using netData union
        netData data;

        // Get connection name (PSP_NETPARAM_NAME = 0)
        sceUtilityGetNetParam(i, PSP_NETPARAM_NAME, &data);
        snprintf(profiles[display_count].name, sizeof(profiles[display_count].name),
                 "%s", data.asString);

        // Get SSID (PSP_NETPARAM_SSID = 1)
        sceUtilityGetNetParam(i, PSP_NETPARAM_SSID, &data);
        snprintf(profiles[display_count].ssid, sizeof(profiles[display_count].ssid),
                 "%s", data.asString);

        // Store profile index
        profiles[display_count].index = i;

        display_count++;
        if (display_count >= 10) break;  // Safety limit
    }

    // If no profiles found, show error
    if (display_count == 0) {
        pspDebugScreenClear();
        pspDebugScreenSetXY(0, 0);
        pspDebugScreenSetTextColor(COLOR_RED);
        pspDebugScreenPrintf("No WiFi profiles configured!\n\n");
        pspDebugScreenSetTextColor(COLOR_WHITE);
        pspDebugScreenPrintf("Please configure a profile in:\n");
        pspDebugScreenPrintf("Settings > Network Settings >\n");
        pspDebugScreenPrintf("Infrastructure Mode > New Connection\n\n");
        pspDebugScreenSetTextColor(COLOR_GRAY);
        pspDebugScreenPrintf("Press O to exit\n");

        while (1) {
            sceCtrlReadBufferPositive(&pad, 1);
            if (pad.Buttons & PSP_CTRL_CIRCLE) {
                return -1;
            }
            sceDisplayWaitVblankStart();
        }
    }

    memset(&oldPad, 0, sizeof(oldPad));

    while (1) {
        sceCtrlReadBufferPositive(&pad, 1);

        // Only redraw when needed (prevents flicker)
        if (need_redraw) {
            pspDebugScreenClear();

            // Title
            pspDebugScreenSetXY(0, 0);
            pspDebugScreenSetTextColor(COLOR_CYAN);
            pspDebugScreenPrintf("========================================\n");
            pspDebugScreenPrintf("      Protosuit Remote Control\n");
            pspDebugScreenPrintf("========================================\n\n");

            pspDebugScreenSetTextColor(COLOR_WHITE);
            pspDebugScreenPrintf("Select Network Configuration:\n\n");

            // List configured profiles with names and SSIDs
            for (int i = 0; i < display_count; i++) {
                pspDebugScreenSetXY(0, 6 + (i * 2));

                if (i == current_selection) {
                    pspDebugScreenSetTextColor(COLOR_YELLOW);
                    pspDebugScreenPrintf(" > ");
                } else {
                    pspDebugScreenSetTextColor(COLOR_GRAY);
                    pspDebugScreenPrintf("   ");
                }

                // Show profile name
                pspDebugScreenSetTextColor(i == current_selection ? COLOR_WHITE : COLOR_GRAY);
                pspDebugScreenPrintf("%s\n", profiles[i].name);

                // Show SSID on next line
                pspDebugScreenSetXY(5, 7 + (i * 2));
                pspDebugScreenSetTextColor(COLOR_GRAY);
                pspDebugScreenPrintf("SSID: %s\n", profiles[i].ssid);
            }

            pspDebugScreenSetXY(0, 26);
            pspDebugScreenSetTextColor(COLOR_GRAY);
            pspDebugScreenPrintf("  Up/Down: Select\n");
            pspDebugScreenPrintf("  X:       Connect\n");
            pspDebugScreenPrintf("  O:       Cancel\n");

            need_redraw = 0;
        }

        // Handle input (only on button press, not hold)
        if (pad.Buttons != oldPad.Buttons) {
            if (pad.Buttons & PSP_CTRL_UP) {
                current_selection--;
                if (current_selection < 0) current_selection = display_count - 1;
                need_redraw = 1;
            }
            else if (pad.Buttons & PSP_CTRL_DOWN) {
                current_selection++;
                if (current_selection >= display_count) current_selection = 0;
                need_redraw = 1;
            }
            else if (pad.Buttons & PSP_CTRL_CROSS) {
                *selected_profile = profiles[current_selection].index;
                return 0;
            }
            else if (pad.Buttons & PSP_CTRL_CIRCLE) {
                return -1;  // Cancelled
            }
        }

        oldPad = pad;
        sceDisplayWaitVblankStart();  // Sync to VBlank to prevent tearing
    }
}

int wifi_menu_wait_for_connection(wifi_context_t *ctx) {
    pspDebugScreenClear();

    pspDebugScreenSetXY(0, 0);
    pspDebugScreenSetTextColor(COLOR_CYAN);
    pspDebugScreenPrintf("========================================\n");
    pspDebugScreenPrintf("      Protosuit Remote Control\n");
    pspDebugScreenPrintf("========================================\n\n");

    pspDebugScreenSetTextColor(COLOR_WHITE);
    pspDebugScreenPrintf("Connecting to Access Point...\n\n");

    // Start connection (non-blocking)
    int result = wifi_connect(ctx);
    if (result < 0) {
        pspDebugScreenSetTextColor(COLOR_RED);
        pspDebugScreenPrintf("Failed to start connection!\n");
        pspDebugScreenPrintf("Error: 0x%08X\n\n", result);
        pspDebugScreenSetTextColor(COLOR_GRAY);
        pspDebugScreenPrintf("Press X to retry or O to exit\n");

        SceCtrlData pad, oldPad;
        memset(&oldPad, 0, sizeof(oldPad));
        while (1) {
            sceCtrlReadBufferPositive(&pad, 1);
            if ((pad.Buttons & PSP_CTRL_CROSS) && !(oldPad.Buttons & PSP_CTRL_CROSS)) {
                return wifi_menu_wait_for_connection(ctx);
            }
            if ((pad.Buttons & PSP_CTRL_CIRCLE) && !(oldPad.Buttons & PSP_CTRL_CIRCLE)) {
                return -1;
            }
            oldPad = pad;
            sceKernelDelayThread(50000);
        }
    }

    // Wait for connection with progress display
    int prev_state = -1;
    int max_retries = 600;  // 30 seconds max (600 * 50ms)

    while (max_retries-- > 0) {
        int state = 0;
        int ret = sceNetApctlGetState(&state);

        // Check for errors
        if (ret < 0) {
            pspDebugScreenSetXY(0, 7);
            pspDebugScreenSetTextColor(COLOR_RED);
            pspDebugScreenPrintf("Connection error: 0x%08X\n\n", ret);
            pspDebugScreenSetTextColor(COLOR_GRAY);
            pspDebugScreenPrintf("Press X to retry or O to exit\n");

            SceCtrlData pad, oldPad;
            memset(&oldPad, 0, sizeof(oldPad));
            while (1) {
                sceCtrlReadBufferPositive(&pad, 1);
                if ((pad.Buttons & PSP_CTRL_CROSS) && !(oldPad.Buttons & PSP_CTRL_CROSS)) {
                    return wifi_menu_wait_for_connection(ctx);
                }
                if ((pad.Buttons & PSP_CTRL_CIRCLE) && !(oldPad.Buttons & PSP_CTRL_CIRCLE)) {
                    return -1;
                }
                oldPad = pad;
                sceDisplayWaitVblankStart();
            }
        }

        // Check if connection dropped from JOINING back to DISCONNECTED
        // PSP-FTPD automatically retries when this happens (state 2 -> 0)
        if (state == PSP_NET_APCTL_STATE_DISCONNECTED && prev_state == PSP_NET_APCTL_STATE_JOINING) {
            pspDebugScreenSetXY(0, 7);
            pspDebugScreenSetTextColor(COLOR_YELLOW);
            pspDebugScreenPrintf("Connection dropped, retrying...        \n");

            // Wait a bit before retry
            sceKernelDelayThread(500000);  // 500ms like PSP-FTPD

            // Reset state and retry connection (like PSP-FTPD does with goto)
            prev_state = -1;

            // Call connect again without disconnecting first
            int result = sceNetApctlConnect(ctx->profile_index);
            if (result < 0) {
                pspDebugScreenSetXY(0, 7);
                pspDebugScreenSetTextColor(COLOR_RED);
                pspDebugScreenPrintf("Retry failed: 0x%08X              \n\n", result);
                pspDebugScreenSetTextColor(COLOR_GRAY);
                pspDebugScreenPrintf("Press X to retry or O to exit\n");

                SceCtrlData pad, oldPad;
                memset(&oldPad, 0, sizeof(oldPad));
                while (1) {
                    sceCtrlReadBufferPositive(&pad, 1);
                    if ((pad.Buttons & PSP_CTRL_CROSS) && !(oldPad.Buttons & PSP_CTRL_CROSS)) {
                        return wifi_menu_wait_for_connection(ctx);
                    }
                    if ((pad.Buttons & PSP_CTRL_CIRCLE) && !(oldPad.Buttons & PSP_CTRL_CIRCLE)) {
                        return -1;
                    }
                    oldPad = pad;
                    sceDisplayWaitVblankStart();
                }
            }
            // Continue polling after retry
            continue;
        }

        // Only update display when state changes
        if (state != prev_state) {
            prev_state = state;

            pspDebugScreenSetXY(0, 5);

            // Display connection progress (0/4 to 4/4)
            int progress = 0;
            const char *state_text = "";

            if (state == PSP_NET_APCTL_STATE_SCANNING) {
                progress = 1;
                state_text = "Scanning...";
            }
            else if (state == PSP_NET_APCTL_STATE_JOINING) {
                progress = 2;
                state_text = "Joining network...";
            }
            else if (state == PSP_NET_APCTL_STATE_GETTING_IP) {
                progress = 3;
                state_text = "Getting IP address...";
            }
            else if (state == PSP_NET_APCTL_STATE_GOT_IP) {
                progress = 4;
                state_text = "Connected!";
            }

            if (progress > 0) {
                pspDebugScreenSetTextColor(progress == 4 ? COLOR_GREEN : COLOR_YELLOW);
                pspDebugScreenPrintf("Connection: [%d/4]                    \n", progress);
                pspDebugScreenSetTextColor(COLOR_WHITE);
                pspDebugScreenPrintf("%s                              \n", state_text);
            }
        }

        // Check if fully connected
        if (state == PSP_NET_APCTL_STATE_GOT_IP) {
            // Small delay to ensure IP is assigned
            sceKernelDelayThread(500000);  // 500ms

            // Get IP address
            union SceNetApctlInfo info;
            if (sceNetApctlGetInfo(PSP_NET_APCTL_INFO_IP, &info) == 0) {
                strncpy(ctx->ip_address, info.ip, sizeof(ctx->ip_address) - 1);
            }

            pspDebugScreenSetXY(0, 8);
            pspDebugScreenSetTextColor(COLOR_GREEN);
            pspDebugScreenPrintf("Connection successful!\n\n");
            pspDebugScreenSetTextColor(COLOR_WHITE);
            pspDebugScreenPrintf("IP Address: %s\n\n", ctx->ip_address);
            pspDebugScreenSetTextColor(COLOR_GRAY);
            pspDebugScreenPrintf("Press X to continue...\n");

            ctx->state = WIFI_CONNECTED;

            // Wait for X button
            SceCtrlData pad, oldPad;
            memset(&oldPad, 0, sizeof(oldPad));
            while (1) {
                sceCtrlReadBufferPositive(&pad, 1);
                if ((pad.Buttons & PSP_CTRL_CROSS) && !(oldPad.Buttons & PSP_CTRL_CROSS)) {
                    return 0;
                }
                oldPad = pad;
                sceDisplayWaitVblankStart();
            }
        }

        sceKernelDelayThread(50000);  // 50ms
    }

    // Timeout
    pspDebugScreenSetXY(0, 8);
    pspDebugScreenSetTextColor(COLOR_RED);
    pspDebugScreenPrintf("Connection timeout!\n\n");
    pspDebugScreenSetTextColor(COLOR_GRAY);
    pspDebugScreenPrintf("Press X to retry or O to exit\n");

    SceCtrlData pad, oldPad;
    memset(&oldPad, 0, sizeof(oldPad));
    while (1) {
        sceCtrlReadBufferPositive(&pad, 1);
        if ((pad.Buttons & PSP_CTRL_CROSS) && !(oldPad.Buttons & PSP_CTRL_CROSS)) {
            return wifi_menu_wait_for_connection(ctx);
        }
        if ((pad.Buttons & PSP_CTRL_CIRCLE) && !(oldPad.Buttons & PSP_CTRL_CIRCLE)) {
            return -1;
        }
        oldPad = pad;
        sceDisplayWaitVblankStart();
    }
}

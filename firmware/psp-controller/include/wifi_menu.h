/*
 * Protosuit Remote Control - WiFi Connection Menu Header
 */

#ifndef WIFI_MENU_H
#define WIFI_MENU_H

#include "wifi.h"

// Show WiFi profile selection menu
// Returns selected profile (1-10) or -1 to use default from config
int wifi_menu_select_profile(int *selected_profile);

// Wait for WiFi connection with visual feedback
// Returns 0 on success, -1 on error/cancel
int wifi_menu_wait_for_connection(wifi_context_t *ctx);

#endif // WIFI_MENU_H

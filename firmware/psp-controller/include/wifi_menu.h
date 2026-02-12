/*
 * Protosuit Remote Control - Wi-Fi Connection Menu Header
 */

#ifndef Wi-Fi_MENU_H
#define Wi-Fi_MENU_H

#include "Wi-Fi.h"

// Show Wi-Fi profile selection menu
// Returns selected profile (1-10) or -1 to use default from config
int Wi-Fi_menu_select_profile(int *selected_profile);

// Wait for Wi-Fi connection with visual feedback
// Returns 0 on success, -1 on error/cancel
int Wi-Fi_menu_wait_for_connection(Wi-Fi_context_t *ctx);

#endif // Wi-Fi_MENU_H

/*
 * Protosuit Remote Control - Performance Configuration
 *
 * NOTE: User settings (MQTT broker, topic, etc.) are now in config.txt
 *       This file contains only compile-time performance tuning constants.
 */

#ifndef CONFIG_H
#define CONFIG_H

// Connection retry timing (microseconds)
#define WIFI_RETRY_DELAY 5000000  // 5 seconds - how often to retry WiFi connection
#define MQTT_RETRY_DELAY 3000000  // 3 seconds - how often to retry MQTT connection

// Input polling rate (microseconds)
#define INPUT_POLL_DELAY 16666    // ~60 FPS (16.6ms) - button sampling rate

// UI refresh rate (microseconds)
#define UI_REFRESH_DELAY 16666    // ~60 FPS (16.6ms) - slow to prevent screen flicker

// Button repeat delay (frames)
#define BUTTON_REPEAT_DELAY 2    // Prevent accidental double-presses

#endif // CONFIG_H

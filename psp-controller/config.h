/*
 * PSP MQTT Controller - Configuration
 * Edit these values to match your network setup
 */

#ifndef CONFIG_H
#define CONFIG_H

// WiFi Configuration
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// MQTT Broker Configuration
#define MQTT_BROKER_IP "192.168.1.100"  // Replace with your Raspberry Pi IP
#define MQTT_BROKER_PORT 1883
#define MQTT_CLIENT_ID "psp-controller"
#define MQTT_TOPIC "protogen/fins/launcher/input/exec"

// MQTT Keepalive (seconds)
#define MQTT_KEEPALIVE 60

// Connection retry settings
#define WIFI_RETRY_DELAY 5000000  // 5 seconds in microseconds
#define MQTT_RETRY_DELAY 3000000  // 3 seconds in microseconds

// Input polling rate (microseconds)
#define INPUT_POLL_DELAY 16666    // ~60 FPS (16.666ms)

// UI refresh rate (microseconds)
#define UI_REFRESH_DELAY 100000   // 100ms (10 FPS)

// Button repeat delay (frames)
#define BUTTON_REPEAT_DELAY 10    // Prevent accidental double-presses

#endif // CONFIG_H


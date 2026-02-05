#pragma once

#include <Arduino.h>

// Teensy menu state (mirrors ProtoTracer Menu)
struct TeensyMenu {
    uint8_t face = 0;
    uint8_t bright = 3;
    uint8_t accentBright = 5;
    uint8_t microphone = 1;
    uint8_t micLevel = 5;
    uint8_t boopSensor = 1;
    uint8_t spectrumMirror = 1;
    uint8_t faceSize = 7;
    uint8_t color = 0;
    uint8_t hueF = 0;
    uint8_t hueB = 0;
    uint8_t effect = 0;
    uint8_t fanSpeed = 0;
};

// Callback type for menu changes that need fan control
typedef void (*FanSpeedCallback)(int percent);
typedef void (*TeensyCommandCallback)(const String& cmd);

void mqttBridgeInit();
void mqttBridgeSetCallbacks(FanSpeedCallback fanCb, TeensyCommandCallback teensyCb);
void mqttBridgeProcess();
void mqttBridgePublish(const char* topic, const char* payload);

bool mqttBridgeIsPiAlive();
unsigned long mqttBridgeGetLastHeartbeat();
const String& mqttBridgeGetShader();
int mqttBridgeGetControllerCount();
const TeensyMenu& mqttBridgeGetMenu();

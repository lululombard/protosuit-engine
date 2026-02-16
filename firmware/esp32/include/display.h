#pragma once

#include <Arduino.h>

struct DisplayData {
    // Row 1 — Pi system
    bool piAlive;
    unsigned long piUptime;     // seconds
    float piTemp;               // °C
    int piFanPercent;           // 0-100
    int controllerCount;
    int piCpuFreqMhz;          // CPU frequency in MHz (e.g. 2400)

    // Row 2 — Activity
    float fps;
    const char* activityName;   // priority-resolved: preset > video > exec > audio > shader

    // Row 3 — Teensy
    const char* faceName;       // label string (e.g. "DEFAULT")
    const char* colorName;      // label string (e.g. "BASE")
    uint8_t brightness;

    // Row 4 — ESP sensors
    float temperature;          // DHT22
    float humidity;             // DHT22
    int fanPercent;             // ESP fan 0-100
    bool fanAutoMode;
};

void displayInit();
void displayUpdate(const DisplayData& data);
void displayShowNotification(const char* title, const char* message);

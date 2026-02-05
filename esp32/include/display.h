#pragma once

#include <Arduino.h>

struct DisplayData {
    bool piAlive;
    int controllerCount;
    const char* shader;
    int fanPercent;
    unsigned long fanRpm;
    float temperature;
    float humidity;
    bool fanAutoMode;
};

void displayInit();
void displayUpdate(const DisplayData& data);

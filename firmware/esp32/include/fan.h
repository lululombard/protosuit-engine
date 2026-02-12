#pragma once

#include <Arduino.h>

void fanInit();
void fanSetSpeed(int percent);
int fanGetSpeedPercent();
unsigned long fanGetRpm();
void fanUpdateRpm();

#pragma once

#include <Arduino.h>

void sensorsInit();
void sensorsUpdate();
float sensorsGetTemperature();
float sensorsGetHumidity();

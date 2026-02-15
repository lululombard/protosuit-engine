#pragma once

#include <Arduino.h>

void ledStripsInit();
void ledStripsUpdate();
void ledStripsSetColor(uint8_t colorIndex, uint8_t hueF, uint8_t hueB, uint8_t bright);
void ledStripsSetBooped(bool booped);
void ledStripsSetFace(uint8_t face);

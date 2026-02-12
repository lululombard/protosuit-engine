#pragma once

#include <Arduino.h>

#define MAX_CURVE_POINTS 8

struct CurvePoint {
    float value;
    uint8_t fan;
};

struct FanCurveConfig {
    bool autoMode;
    CurvePoint temperatureCurve[MAX_CURVE_POINTS];
    uint8_t temperatureCurveSize;
    CurvePoint humidityCurve[MAX_CURVE_POINTS];
    uint8_t humidityCurveSize;
};

void fanCurveInit();
int fanCurveCalculate(float temperature, float humidity);
bool fanCurveIsAutoMode();
void fanCurveSetAutoMode(bool enabled);
const FanCurveConfig& fanCurveGetConfig();
bool fanCurveSetConfig(const char* json);
String fanCurveConfigToJson();
void fanCurveSave();
void fanCurveLoad();

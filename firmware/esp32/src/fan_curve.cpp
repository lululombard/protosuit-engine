#include "fan_curve.h"
#include <Preferences.h>
#include <ArduinoJson.h>

static Preferences prefs;

// Default curves based on requirements:
// Temp: <15=0%, 15-20=20-30%, 20-25=30-50%, 25-30=50-80%, 30-35=80-100%
// Humidity: <30=0%, 30-40=20-40%, 40-60=40-60%, 60-80=60-100%
static FanCurveConfig config = {
    .autoMode = false,
    .temperatureCurve = {
        {15.0f, 0},
        {20.0f, 30},
        {25.0f, 50},
        {30.0f, 80},
        {35.0f, 100}
    },
    .temperatureCurveSize = 5,
    .humidityCurve = {
        {30.0f, 0},
        {40.0f, 40},
        {60.0f, 60},
        {80.0f, 100}
    },
    .humidityCurveSize = 4
};

static int interpolateCurve(const CurvePoint* curve, uint8_t size, float value) {
    if (size == 0) return 0;
    if (value <= curve[0].value) return curve[0].fan;
    if (value >= curve[size - 1].value) return curve[size - 1].fan;

    for (uint8_t i = 0; i < size - 1; i++) {
        if (value >= curve[i].value && value < curve[i + 1].value) {
            float range = curve[i + 1].value - curve[i].value;
            float t = (value - curve[i].value) / range;
            return curve[i].fan + t * (curve[i + 1].fan - curve[i].fan);
        }
    }
    return curve[size - 1].fan;
}

void fanCurveInit() {
    // Nothing special needed, defaults are set statically
}

int fanCurveCalculate(float temperature, float humidity) {
    int tempSpeed = interpolateCurve(config.temperatureCurve, config.temperatureCurveSize, temperature);
    int humSpeed = interpolateCurve(config.humidityCurve, config.humidityCurveSize, humidity);
    return max(tempSpeed, humSpeed);
}

bool fanCurveIsAutoMode() {
    return config.autoMode;
}

void fanCurveSetAutoMode(bool enabled) {
    config.autoMode = enabled;
}

const FanCurveConfig& fanCurveGetConfig() {
    return config;
}

bool fanCurveSetConfig(const char* json) {
    JsonDocument doc;
    if (deserializeJson(doc, json) != DeserializationError::Ok) {
        return false;
    }

    if (doc.containsKey("mode")) {
        config.autoMode = (strcmp(doc["mode"], "auto") == 0);
    }

    if (doc.containsKey("temperature")) {
        JsonArray tempArr = doc["temperature"].as<JsonArray>();
        uint8_t i = 0;
        for (JsonObject point : tempArr) {
            if (i >= MAX_CURVE_POINTS) break;
            config.temperatureCurve[i].value = point["value"];
            config.temperatureCurve[i].fan = point["fan"];
            i++;
        }
        config.temperatureCurveSize = i;
    }

    if (doc.containsKey("humidity")) {
        JsonArray humArr = doc["humidity"].as<JsonArray>();
        uint8_t i = 0;
        for (JsonObject point : humArr) {
            if (i >= MAX_CURVE_POINTS) break;
            config.humidityCurve[i].value = point["value"];
            config.humidityCurve[i].fan = point["fan"];
            i++;
        }
        config.humidityCurveSize = i;
    }

    return true;
}

String fanCurveConfigToJson() {
    JsonDocument doc;
    doc["mode"] = config.autoMode ? "auto" : "manual";

    JsonArray tempArr = doc["temperature"].to<JsonArray>();
    for (uint8_t i = 0; i < config.temperatureCurveSize; i++) {
        JsonObject point = tempArr.add<JsonObject>();
        point["value"] = config.temperatureCurve[i].value;
        point["fan"] = config.temperatureCurve[i].fan;
    }

    JsonArray humArr = doc["humidity"].to<JsonArray>();
    for (uint8_t i = 0; i < config.humidityCurveSize; i++) {
        JsonObject point = humArr.add<JsonObject>();
        point["value"] = config.humidityCurve[i].value;
        point["fan"] = config.humidityCurve[i].fan;
    }

    String output;
    serializeJson(doc, output);
    return output;
}

void fanCurveSave() {
    prefs.begin("fancurve", false);
    prefs.putBool("auto", config.autoMode);
    prefs.putUChar("tempSize", config.temperatureCurveSize);
    prefs.putBytes("temp", config.temperatureCurve, sizeof(CurvePoint) * config.temperatureCurveSize);
    prefs.putUChar("humSize", config.humidityCurveSize);
    prefs.putBytes("hum", config.humidityCurve, sizeof(CurvePoint) * config.humidityCurveSize);
    prefs.end();
}

void fanCurveLoad() {
    prefs.begin("fancurve", true);
    if (prefs.isKey("auto")) {
        config.autoMode = prefs.getBool("auto", false);
        config.temperatureCurveSize = prefs.getUChar("tempSize", 5);
        prefs.getBytes("temp", config.temperatureCurve, sizeof(CurvePoint) * config.temperatureCurveSize);
        config.humidityCurveSize = prefs.getUChar("humSize", 4);
        prefs.getBytes("hum", config.humidityCurve, sizeof(CurvePoint) * config.humidityCurveSize);
    }
    prefs.end();
}

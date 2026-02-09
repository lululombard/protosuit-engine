#include <Arduino.h>
#include <ArduinoJson.h>
#include "config.h"
#include "fan.h"
#include "fan_curve.h"
#include "sensors.h"
#include "display.h"
#include "mqtt_bridge.h"
#include "teensy_comm.h"

static unsigned long lastSensorUpdate = 0;
static unsigned long lastSensorPublish = 0;
static unsigned long lastConfigPublish = 0;

static void onTeensyMessage(const String& msg) {
    mqttBridgeHandleTeensyResponse(msg);
    mqttBridgePublish("protogen/visor/teensy/raw", msg.c_str());
}

static void onTeensyCommand(const String& cmd) {
    teensyCommSend(cmd);
}

static void onFanSpeedChange(int percent) {
    fanSetSpeed(percent);
}

static void publishSensorData() {
    JsonDocument doc;
    doc["temperature"] = sensorsGetTemperature();
    doc["humidity"] = sensorsGetHumidity();
    doc["rpm"] = fanGetRpm();
    doc["fan"] = fanGetSpeedPercent();
    doc["mode"] = fanCurveIsAutoMode() ? "auto" : "manual";

    char buffer[160];
    serializeJson(doc, buffer);
    mqttBridgePublish("protogen/visor/esp/status/sensors", buffer);
}

static void updateDisplayData() {
    DisplayData data;
    data.piAlive = mqttBridgeIsPiAlive();
    data.controllerCount = mqttBridgeGetControllerCount();
    data.shader = mqttBridgeGetShader().c_str();
    data.fanPercent = fanGetSpeedPercent();
    data.fanRpm = fanGetRpm();
    data.temperature = sensorsGetTemperature();
    data.humidity = sensorsGetHumidity();
    data.fanAutoMode = fanCurveIsAutoMode();
    displayUpdate(data);
}

void setup() {
    mqttBridgeInit();
    teensyCommInit();

    delay(500);

    displayInit();
    sensorsInit();
    fanInit();
    fanCurveInit();
    fanCurveLoad();

    mqttBridgeSetCallbacks(onFanSpeedChange, onTeensyCommand);
    teensyCommSetCallback(onTeensyMessage);

    mqttBridgePublish("protogen/visor/esp/status/alive", "true");
    mqttBridgePublish("protogen/visor/esp/status/fancurve", fanCurveConfigToJson().c_str());
    mqttBridgeRequestTeensySync();
    updateDisplayData();
}

void loop() {
    unsigned long now = millis();

    // Update sensors and RPM every second
    if (now - lastSensorUpdate >= 1000) {
        fanUpdateRpm();
        sensorsUpdate();

        // Auto fan control
        if (fanCurveIsAutoMode()) {
            int targetSpeed = fanCurveCalculate(
                sensorsGetTemperature(),
                sensorsGetHumidity()
            );
            fanSetSpeed(targetSpeed);
        }

        updateDisplayData();
        lastSensorUpdate = now;
    }

    // Publish sensor data periodically
    if (now - lastSensorPublish >= SENSOR_PUBLISH_INTERVAL) {
        publishSensorData();
        lastSensorPublish = now;
    }

    // Publish fan curve config every 30 seconds
    if (now - lastConfigPublish >= 30000) {
        mqttBridgePublish("protogen/visor/esp/status/fancurve", fanCurveConfigToJson().c_str());
        lastConfigPublish = now;
    }

    // Process serial communications
    mqttBridgeProcess();
    teensyCommProcess();
}

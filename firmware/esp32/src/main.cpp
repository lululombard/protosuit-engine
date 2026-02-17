#include <Arduino.h>
#include <ArduinoJson.h>
#include "config.h"
#include "fan.h"
#include "fan_curve.h"
#include "sensors.h"
#include "display.h"
#include "mqtt_bridge.h"
#include "teensy_comm.h"
#include "led_strips.h"

static unsigned long lastSensorUpdate = 0;
static unsigned long lastSensorPublish = 0;
static unsigned long lastConfigPublish = 0;
static bool initialSyncDone = false;

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
    // Notification overlay takes over the display (auto-expires after NOTIFICATION_DURATION)
    if (mqttBridgeHasNotification()) {
        displayShowNotification(
            mqttBridgeGetNotificationTitle(),
            mqttBridgeGetNotificationMessage()
        );
        return;
    }

    DisplayData data;

    // Row 1 — Pi system
    data.piAlive = mqttBridgeIsPiAlive();
    data.piUptime = mqttBridgeGetPiUptime();
    data.piTemp = mqttBridgeGetPiTemp();
    data.piFanPercent = mqttBridgeGetPiFanPercent();
    data.controllerCount = mqttBridgeGetControllerCount();
    data.piCpuFreqMhz = mqttBridgeGetPiCpuFreqMhz();

    // Row 2 — Activity
    data.fps = mqttBridgeGetFps();
    data.activityName = mqttBridgeGetActivityName();

    // Row 3 — Teensy
    data.faceName = mqttBridgeGetFaceLabel();
    data.colorName = mqttBridgeGetColorLabel();
    data.brightness = mqttBridgeGetMenu().bright;

    // Row 4 — ESP sensors
    data.temperature = sensorsGetTemperature();
    data.humidity = sensorsGetHumidity();
    data.fanPercent = fanGetSpeedPercent();
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

    ledStripsInit();

    mqttBridgeSetCallbacks(onFanSpeedChange, onTeensyCommand);
    teensyCommSetCallback(onTeensyMessage);

    mqttBridgePublish("protogen/visor/esp/status/alive", "true");
    mqttBridgePublish("protogen/visor/esp/status/fancurve", fanCurveConfigToJson().c_str());
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

    // Also update display more frequently when notification is active (for smooth transitions)
    // or when Pi temp is blinking (needs ~500ms refresh)
    if (mqttBridgeHasNotification() || mqttBridgeGetPiTemp() >= PI_TEMP_WARN_THRESHOLD) {
        static unsigned long lastFastUpdate = 0;
        if (now - lastFastUpdate >= 250) {
            updateDisplayData();
            lastFastUpdate = now;
        }
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

    // Delayed initial sync (give espbridge time to connect)
    if (!initialSyncDone && now >= 3000) {
        initialSyncDone = true;
        mqttBridgePublishSchema();
        mqttBridgePublishEspHueStatus();
        mqttBridgeRequestTeensySync();
    }

    // Process serial communications
    mqttBridgeProcess();
    teensyCommProcess();

    // Update LED strip animations
    ledStripsUpdate();
}

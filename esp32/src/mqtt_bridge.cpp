#include "mqtt_bridge.h"
#include "config.h"
#include "fan_curve.h"
#include <ArduinoJson.h>

static String inputBuffer;
static String currentShader;
static int controllerCount = 0;
static bool piAlive = false;
static unsigned long lastPiHeartbeat = 0;
static TeensyMenu teensyMenu;

static FanSpeedCallback onFanSpeed = nullptr;
static TeensyCommandCallback onTeensyCommand = nullptr;

void mqttBridgeInit() {
    Serial.begin(PI_BAUD);
    inputBuffer.reserve(512);
}

void mqttBridgeSetCallbacks(FanSpeedCallback fanCb, TeensyCommandCallback teensyCb) {
    onFanSpeed = fanCb;
    onTeensyCommand = teensyCb;
}

void mqttBridgePublish(const char* topic, const char* payload) {
    Serial.print(MSG_TO_PI);
    Serial.print(topic);
    Serial.print(MSG_SEPARATOR);
    Serial.print(payload);
    Serial.print('\n');
}

static void processMessage(const String& topic, const String& payload) {
    piAlive = true;
    lastPiHeartbeat = millis();

    if (topic == "protogen/visor/esp/set/fan") {
        int speed = payload.toInt();
        fanCurveSetAutoMode(false);  // Switch to manual when user sets speed
        fanCurveSave();
        if (onFanSpeed) onFanSpeed(speed);
        mqttBridgePublish("protogen/visor/esp/status/fancurve", fanCurveConfigToJson().c_str());
    }
    else if (topic == "protogen/visor/esp/set/fanmode") {
        bool autoMode = (payload == "auto");
        fanCurveSetAutoMode(autoMode);
        fanCurveSave();
        mqttBridgePublish("protogen/visor/esp/status/fancurve", fanCurveConfigToJson().c_str());
    }
    else if (topic == "protogen/visor/esp/config/fancurve") {
        if (fanCurveSetConfig(payload.c_str())) {
            fanCurveSave();
            mqttBridgePublish("protogen/visor/esp/status/fancurve", fanCurveConfigToJson().c_str());
        }
    }
    else if (topic.startsWith("protogen/fins/renderer/status/shader")) {
        Serial.print("DEBUG: shader len=");
        Serial.print(payload.length());
        Serial.print(" data=");
        Serial.println(payload);
        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, payload);
        if (err == DeserializationError::Ok) {
            const char* shader = doc["current"]["left"];
            Serial.print("DEBUG: parsed=");
            Serial.println(shader ? shader : "(null)");
            if (shader) {
                currentShader = shader;
            }
        } else {
            Serial.print("DEBUG: err=");
            Serial.println(err.c_str());
        }
    }
    else if (topic.startsWith("protogen/fins/bluetoothbridge/status/devices")) {
        JsonDocument doc;
        if (deserializeJson(doc, payload) == DeserializationError::Ok) {
            int count = 0;
            JsonArray devices = doc.as<JsonArray>();
            for (JsonObject device : devices) {
                if (device["connected"] == true) {
                    count++;
                }
            }
            controllerCount = count;
        }
    }
    else if (topic.startsWith("protogen/visor/teensy/menu/set")) {
        JsonDocument doc;
        if (deserializeJson(doc, payload) == DeserializationError::Ok) {
            const char* param = doc["param"];
            int value = doc["value"];

            if (param) {
                String p = param;
                if (p == "face") teensyMenu.face = value;
                else if (p == "bright") teensyMenu.bright = value;
                else if (p == "accentBright") teensyMenu.accentBright = value;
                else if (p == "microphone") teensyMenu.microphone = value;
                else if (p == "micLevel") teensyMenu.micLevel = value;
                else if (p == "boopSensor") teensyMenu.boopSensor = value;
                else if (p == "spectrumMirror") teensyMenu.spectrumMirror = value;
                else if (p == "faceSize") teensyMenu.faceSize = value;
                else if (p == "color") teensyMenu.color = value;
                else if (p == "hueF") teensyMenu.hueF = value;
                else if (p == "hueB") teensyMenu.hueB = value;
                else if (p == "effect") teensyMenu.effect = value;
                else if (p == "fanSpeed") {
                    teensyMenu.fanSpeed = value;
                    if (onFanSpeed) onFanSpeed(value * 10);
                }

                if (onTeensyCommand) {
                    String cmd = "M:" + p + "=" + String(value);
                    onTeensyCommand(cmd);
                }
            }
        }
    }
}

void mqttBridgeProcess() {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n') {
            if (inputBuffer.length() > 0 && inputBuffer[0] == MSG_FROM_PI) {
                int sepIndex = inputBuffer.indexOf(MSG_SEPARATOR);
                if (sepIndex > 1) {
                    String topic = inputBuffer.substring(1, sepIndex);
                    String payload = inputBuffer.substring(sepIndex + 1);
                    processMessage(topic, payload);
                }
            }
            inputBuffer = "";
        } else if (c != '\r') {
            inputBuffer += c;
            if (inputBuffer.length() > 512) {
                inputBuffer = "";
            }
        }
    }
}

bool mqttBridgeIsPiAlive() {
    if (piAlive && (millis() - lastPiHeartbeat > PI_TIMEOUT)) {
        piAlive = false;
    }
    return piAlive;
}

unsigned long mqttBridgeGetLastHeartbeat() {
    return lastPiHeartbeat;
}

const String& mqttBridgeGetShader() {
    return currentShader;
}

int mqttBridgeGetControllerCount() {
    return controllerCount;
}

const TeensyMenu& mqttBridgeGetMenu() {
    return teensyMenu;
}

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

// Mapping between Pi camelCase param names and Teensy protocol uppercase names
struct ParamMapping {
    const char* camel;
    const char* proto;
    uint8_t TeensyMenu::* field;
};

static const ParamMapping paramMap[] = {
    {"face",           "FACE",   &TeensyMenu::face},
    {"bright",         "BRIGHT", &TeensyMenu::bright},
    {"accentBright",   "ABRIGHT",&TeensyMenu::accentBright},
    {"microphone",     "MIC",    &TeensyMenu::microphone},
    {"micLevel",       "MICLVL", &TeensyMenu::micLevel},
    {"boopSensor",     "BOOP",   &TeensyMenu::boopSensor},
    {"spectrumMirror", "SPEC",   &TeensyMenu::spectrumMirror},
    {"faceSize",       "SIZE",   &TeensyMenu::faceSize},
    {"color",          "COLOR",  &TeensyMenu::color},
    {"hueF",           "HUEF",   &TeensyMenu::hueF},
    {"hueB",           "HUEB",   &TeensyMenu::hueB},
    {"effect",         "EFFECT", &TeensyMenu::effect},
    {"fanSpeed",       "FAN",    &TeensyMenu::fanSpeed},
};
static const int paramMapSize = sizeof(paramMap) / sizeof(paramMap[0]);

static const ParamMapping* findByCamel(const String& name) {
    for (int i = 0; i < paramMapSize; i++) {
        if (name == paramMap[i].camel) return &paramMap[i];
    }
    return nullptr;
}

static const ParamMapping* findByProto(const String& name) {
    String upper = name;
    upper.toUpperCase();
    for (int i = 0; i < paramMapSize; i++) {
        if (upper == paramMap[i].proto) return &paramMap[i];
    }
    return nullptr;
}

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
    else if (topic == "protogen/visor/teensy/menu/set") {
        JsonDocument doc;
        if (deserializeJson(doc, payload) == DeserializationError::Ok) {
            const char* param = doc["param"];
            int value = doc["value"];

            if (param) {
                const ParamMapping* m = findByCamel(String(param));
                if (m) {
                    teensyMenu.*(m->field) = value;

                    if (strcmp(m->camel, "fanSpeed") == 0 && onFanSpeed) {
                        onFanSpeed(value * 10);
                    }

                    if (onTeensyCommand) {
                        String cmd = "SET " + String(m->proto) + " " + String(value);
                        onTeensyCommand(cmd);
                    }
                }
            }
        }
    }
    else if (topic == "protogen/visor/teensy/menu/get") {
        if (onTeensyCommand) onTeensyCommand("GET ALL");
    }
    else if (topic == "protogen/visor/teensy/menu/save") {
        if (onTeensyCommand) onTeensyCommand("SAVE");
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

void mqttBridgeHandleTeensyResponse(const String& msg) {
    if (msg.startsWith("OK SAVED")) {
        mqttBridgePublish("protogen/visor/teensy/menu/status", "{\"saved\":true}");
        return;
    }
    if (msg.startsWith("ERR")) {
        JsonDocument doc;
        doc["error"] = msg;
        char buffer[128];
        serializeJson(doc, buffer);
        mqttBridgePublish("protogen/visor/teensy/menu/status", buffer);
        return;
    }

    int eqIdx = msg.indexOf('=');
    if (eqIdx > 0) {
        String protoParam = msg.substring(0, eqIdx);
        protoParam.trim();
        int value = msg.substring(eqIdx + 1).toInt();

        const ParamMapping* m = findByProto(protoParam);
        if (m) {
            teensyMenu.*(m->field) = value;

            if (strcmp(m->camel, "fanSpeed") == 0 && onFanSpeed) {
                onFanSpeed(value * 10);
            }

            JsonDocument doc;
            doc["param"] = m->camel;
            doc["value"] = value;
            char buffer[64];
            serializeJson(doc, buffer);
            mqttBridgePublish("protogen/visor/teensy/menu/status", buffer);
        }
    }
}

void mqttBridgeRequestTeensySync() {
    if (onTeensyCommand) onTeensyCommand("GET ALL");
}

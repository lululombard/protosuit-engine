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

// Value label arrays for params with named options
static const char* const faceLabels[] = {
    "DEFAULT","ANGRY","DOUBT","FROWN","LOOKUP","SAD","AUDIO1","AUDIO2","AUDIO3"
};
static const char* const colorLabels[] = {
    "BASE","YELLOW","ORANGE","WHITE","GREEN","PURPLE","RED","BLUE",
    "RAINBOW","RAINBOWNOISE","HORIZONTALRAINBOW","BLACK"
};
static const char* const effectLabels[] = {
    "NONE","PHASEY","PHASEX","PHASER","GLITCHX",
    "MAGNET","FISHEYE","HBLUR","VBLUR","RBLUR"
};
static const char* const toggleLabels[] = {"OFF","ON"};
// Mapping between Pi camelCase param names and Teensy protocol uppercase names
struct ParamMapping {
    const char* camel;
    const char* proto;
    uint8_t TeensyMenu::* field;
    uint8_t maxVal;
    const char* const* labels;  // NULL for numeric-only params
};

static const ParamMapping paramMap[] = {
    {"face",           "FACE",   &TeensyMenu::face,           8,  faceLabels},
    {"bright",         "BRIGHT", &TeensyMenu::bright,         10, nullptr},
    {"accentBright",   "ABRIGHT",&TeensyMenu::accentBright,   10, nullptr},
    {"microphone",     "MIC",    &TeensyMenu::microphone,     1,  toggleLabels},
    {"micLevel",       "MICLVL", &TeensyMenu::micLevel,       10, nullptr},
    {"boopSensor",     "BOOP",   &TeensyMenu::boopSensor,     1,  toggleLabels},
    {"spectrumMirror", "SPEC",   &TeensyMenu::spectrumMirror, 1,  toggleLabels},
    {"faceSize",       "SIZE",   &TeensyMenu::faceSize,       10, nullptr},
    {"color",          "COLOR",  &TeensyMenu::color,          11, colorLabels},
    {"hueF",           "HUEF",   &TeensyMenu::hueF,           10, nullptr},
    {"hueB",           "HUEB",   &TeensyMenu::hueB,           10, nullptr},
    {"effect",         "EFFECT", &TeensyMenu::effect,          9,  effectLabels},
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

                    if (onTeensyCommand) {
                        String cmd = "SET " + String(m->proto) + " " + String(value);
                        onTeensyCommand(cmd);
                    }
                }
            }
        }
    }
    else if (topic == "protogen/visor/teensy/menu/get") {
        mqttBridgePublishSchema();
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

static void publishParamStatus(const ParamMapping* m, uint8_t value) {
    String topic = "protogen/visor/teensy/menu/status/" + String(m->camel);
    JsonDocument doc;
    doc["value"] = value;
    if (m->labels && value <= m->maxVal) {
        doc["label"] = m->labels[value];
    }
    char buffer[96];
    serializeJson(doc, buffer);
    mqttBridgePublish(topic.c_str(), buffer);
}

void mqttBridgeHandleTeensyResponse(const String& msg) {
    if (msg.startsWith("OK SAVED")) {
        mqttBridgePublish("protogen/visor/teensy/menu/saved", "true");
        return;
    }
    if (msg.startsWith("ERR")) {
        JsonDocument doc;
        doc["error"] = msg;
        char buffer[128];
        serializeJson(doc, buffer);
        mqttBridgePublish("protogen/visor/teensy/menu/error", buffer);
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

            publishParamStatus(m, value);
        }
    }
}

void mqttBridgePublishSchema() {
    JsonDocument doc;
    for (int i = 0; i < paramMapSize; i++) {
        const ParamMapping& m = paramMap[i];
        JsonObject param = doc[m.camel].to<JsonObject>();
        param["min"] = 0;
        param["max"] = m.maxVal;
        if (m.labels) {
            param["type"] = (m.maxVal <= 1) ? "toggle" : "select";
            JsonArray options = param["options"].to<JsonArray>();
            for (int j = 0; j <= m.maxVal; j++) {
                options.add(m.labels[j]);
            }
        } else {
            param["type"] = "range";
        }
    }
    String output;
    serializeJson(doc, output);
    mqttBridgePublish("protogen/visor/teensy/menu/schema", output.c_str());
}

void mqttBridgeRequestTeensySync() {
    if (onTeensyCommand) onTeensyCommand("GET ALL");
}

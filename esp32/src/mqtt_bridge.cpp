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

// CRC-8/SMBUS lookup table (polynomial 0x07)
static const uint8_t PROGMEM crc8Table[256] = {
    0x00,0x07,0x0E,0x09,0x1C,0x1B,0x12,0x15,0x38,0x3F,0x36,0x31,0x24,0x23,0x2A,0x2D,
    0x70,0x77,0x7E,0x79,0x6C,0x6B,0x62,0x65,0x48,0x4F,0x46,0x41,0x54,0x53,0x5A,0x5D,
    0xE0,0xE7,0xEE,0xE9,0xFC,0xFB,0xF2,0xF5,0xD8,0xDF,0xD6,0xD1,0xC4,0xC3,0xCA,0xCD,
    0x90,0x97,0x9E,0x99,0x8C,0x8B,0x82,0x85,0xA8,0xAF,0xA6,0xA1,0xB4,0xB3,0xBA,0xBD,
    0xC7,0xC0,0xC9,0xCE,0xDB,0xDC,0xD5,0xD2,0xFF,0xF8,0xF1,0xF6,0xE3,0xE4,0xED,0xEA,
    0xB7,0xB0,0xB9,0xBE,0xAB,0xAC,0xA5,0xA2,0x8F,0x88,0x81,0x86,0x93,0x94,0x9D,0x9A,
    0x27,0x20,0x29,0x2E,0x3B,0x3C,0x35,0x32,0x1F,0x18,0x11,0x16,0x03,0x04,0x0D,0x0A,
    0x57,0x50,0x59,0x5E,0x4B,0x4C,0x45,0x42,0x6F,0x68,0x61,0x66,0x73,0x74,0x7D,0x7A,
    0x89,0x8E,0x87,0x80,0x95,0x92,0x9B,0x9C,0xB1,0xB6,0xBF,0xB8,0xAD,0xAA,0xA3,0xA4,
    0xF9,0xFE,0xF7,0xF0,0xE5,0xE2,0xEB,0xEC,0xC1,0xC6,0xCF,0xC8,0xDD,0xDA,0xD3,0xD4,
    0x69,0x6E,0x67,0x60,0x75,0x72,0x7B,0x7C,0x51,0x56,0x5F,0x58,0x4D,0x4A,0x43,0x44,
    0x19,0x1E,0x17,0x10,0x05,0x02,0x0B,0x0C,0x21,0x26,0x2F,0x28,0x3D,0x3A,0x33,0x34,
    0x4E,0x49,0x40,0x47,0x52,0x55,0x5C,0x5B,0x76,0x71,0x78,0x7F,0x6A,0x6D,0x64,0x63,
    0x3E,0x39,0x30,0x37,0x22,0x25,0x2C,0x2B,0x06,0x01,0x08,0x0F,0x1A,0x1D,0x14,0x13,
    0xAE,0xA9,0xA0,0xA7,0xB2,0xB5,0xBC,0xBB,0x96,0x91,0x98,0x9F,0x8A,0x8D,0x84,0x83,
    0xDE,0xD9,0xD0,0xD7,0xC2,0xC5,0xCC,0xCB,0xE6,0xE1,0xE8,0xEF,0xFA,0xFD,0xF4,0xF3
};

static uint8_t crc8(const char* data, size_t len) {
    uint8_t crc = 0x00;
    for (size_t i = 0; i < len; i++) {
        crc = pgm_read_byte(&crc8Table[crc ^ (uint8_t)data[i]]);
    }
    return crc;
}

static const char hexChars[] = "0123456789ABCDEF";

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
    {"bright",         "BRIGHT", &TeensyMenu::bright,         254, nullptr},
    {"accentBright",   "ABRIGHT",&TeensyMenu::accentBright,   254, nullptr},
    {"microphone",     "MIC",    &TeensyMenu::microphone,     1,  toggleLabels},
    {"micLevel",       "MICLVL", &TeensyMenu::micLevel,       10, nullptr},
    {"boopSensor",     "BOOP",   &TeensyMenu::boopSensor,     1,  toggleLabels},
    {"spectrumMirror", "SPEC",   &TeensyMenu::spectrumMirror, 1,  toggleLabels},
    {"faceSize",       "SIZE",   &TeensyMenu::faceSize,       10, nullptr},
    {"color",          "COLOR",  &TeensyMenu::color,          11, colorLabels},
    {"hueF",           "HUEF",   &TeensyMenu::hueF,           254, nullptr},
    {"hueB",           "HUEB",   &TeensyMenu::hueB,           254, nullptr},
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
    // Build the body: topic\tpayload
    String body = String(topic) + MSG_SEPARATOR + payload;
    uint8_t crc = crc8(body.c_str(), body.length());

    Serial.print(MSG_TO_PI);
    Serial.print(body);
    Serial.print(MSG_CRC_DELIM);
    Serial.print(hexChars[crc >> 4]);
    Serial.print(hexChars[crc & 0x0F]);
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
                // Strip direction marker for body parsing
                String body = inputBuffer.substring(1);

                // Require CRC
                int crcIdx = body.lastIndexOf(MSG_CRC_DELIM);
                if (crcIdx <= 0 || body.length() - crcIdx != 3) {
                    Serial.println("CRC MISSING");
                    inputBuffer = "";
                    continue;
                }

                String crcHex = body.substring(crcIdx + 1);
                String data = body.substring(0, crcIdx);
                uint8_t expected = (uint8_t)strtoul(crcHex.c_str(), nullptr, 16);
                uint8_t actual = crc8(data.c_str(), data.length());
                if (expected != actual) {
                    Serial.println("CRC FAIL");
                    inputBuffer = "";
                    continue;
                }

                int sepIndex = data.indexOf(MSG_SEPARATOR);
                if (sepIndex > 0) {
                    String topic = data.substring(0, sepIndex);
                    String payload = data.substring(sepIndex + 1);
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

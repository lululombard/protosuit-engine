#include "teensy_comm.h"
#include "config.h"

static String inputBuffer;
static TeensyMessageCallback onMessage = nullptr;

void teensyCommInit() {
    Serial1.begin(TEENSY_BAUD, SERIAL_8N1, TEENSY_RX, TEENSY_TX);
    inputBuffer.reserve(256);
}

void teensyCommSetCallback(TeensyMessageCallback cb) {
    onMessage = cb;
}

void teensyCommProcess() {
    while (Serial1.available()) {
        char c = Serial1.read();
        if (c == '\n') {
            if (inputBuffer.length() > 0 && onMessage) {
                Serial.print("[TEENSY] ");
                Serial.println(inputBuffer);
                onMessage(inputBuffer);
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

void teensyCommSend(const String& data) {
    Serial1.println(data);
}

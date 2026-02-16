#include "display.h"
#include "config.h"
#include <U8g2lib.h>
#include <Wire.h>

static U8G2_SSD1306_128X64_NONAME_F_HW_I2C display(U8G2_R0, U8X8_PIN_NONE, I2C_SCL, I2C_SDA);

void displayInit() {
    display.begin();
    display.setContrast(255);
}

// Helper: lowercase a string into a buffer, truncated to maxLen
static void toLowerTrunc(char* dst, const char* src, int maxLen) {
    int i = 0;
    while (src[i] && i < maxLen) {
        dst[i] = (src[i] >= 'A' && src[i] <= 'Z') ? src[i] + 32 : src[i];
        i++;
    }
    dst[i] = '\0';
}

// Helper: format uptime into compact string
// <60m: "33m" | 1-24h: "2h33" | >=24h: "2d5h"
static void formatUptime(char* dst, size_t size, unsigned long seconds) {
    unsigned long minutes = seconds / 60;
    unsigned long hours = minutes / 60;
    unsigned long days = hours / 24;

    if (hours == 0) {
        snprintf(dst, size, "%lum", minutes);
    } else if (days == 0) {
        snprintf(dst, size, "%luh%02lu", hours, minutes % 60);
    } else {
        snprintf(dst, size, "%lud%luh", days, hours % 24);
    }
}

void displayUpdate(const DisplayData& data) {
    display.clearBuffer();
    display.setFont(u8g2_font_6x10_tf);

    char buf[24];

    // === Row 1 (y=8): Pi uptime, Pi temp, Pi fan%, controllers, freq ===
    int x = 0;

    // Uptime
    if (data.piAlive) {
        formatUptime(buf, sizeof(buf), data.piUptime);
    } else {
        strcpy(buf, "--");
    }
    display.drawStr(x, 8, buf);
    x += strlen(buf) * 6 + 3;

    // Pi CPU temp (blink if >= threshold)
    if (data.piAlive) {
        bool showTemp = true;
        if (data.piTemp >= PI_TEMP_WARN_THRESHOLD) {
            showTemp = (millis() / 500) % 2 == 0;
        }
        if (showTemp) {
            snprintf(buf, sizeof(buf), "T%dC", (int)data.piTemp);
            display.drawStr(x, 8, buf);
        }
        x += 4 * 6 + 3;  // reserve space even when blinking off
    } else {
        display.drawStr(x, 8, "T--");
        x += 3 * 6 + 3;
    }

    // Pi fan%
    if (data.piAlive) {
        snprintf(buf, sizeof(buf), "F%d%%", data.piFanPercent);
    } else {
        strcpy(buf, "F--");
    }
    display.drawStr(x, 8, buf);
    x += strlen(buf) * 6 + 3;

    // Controller count
    snprintf(buf, sizeof(buf), "C%d", data.controllerCount);
    display.drawStr(x, 8, buf);
    x += strlen(buf) * 6 + 3;

    // CPU frequency (GHz)
    if (data.piAlive && data.piCpuFreqMhz > 0) {
        snprintf(buf, sizeof(buf), "%.1fG", data.piCpuFreqMhz / 1000.0f);
        display.drawStr(x, 8, buf);
    }

    display.drawHLine(0, 13, 128);

    // === Row 2 (y=23): FPS + activity name ===
    x = 0;
    if (data.piAlive && data.fps > 0) {
        snprintf(buf, sizeof(buf), "%dfps", (int)data.fps);
    } else {
        strcpy(buf, "--fps");
    }
    display.drawStr(x, 23, buf);
    x += strlen(buf) * 6 + 4;

    if (data.activityName && data.activityName[0] != '\0') {
        int remaining = (128 - x) / 6;
        if (remaining > 0) {
            char nameBuf[22];
            int len = strlen(data.activityName);
            if (len > remaining) len = remaining;
            strncpy(nameBuf, data.activityName, len);
            nameBuf[len] = '\0';
            display.drawStr(x, 23, nameBuf);
        }
    }

    display.drawHLine(0, 28, 128);

    // === Row 3 (y=38): face label, color label, brightness ===
    x = 0;
    char faceBuf[8], colorBuf[8];

    if (data.faceName) {
        toLowerTrunc(faceBuf, data.faceName, 7);
    } else {
        strcpy(faceBuf, "---");
    }
    display.drawStr(x, 38, faceBuf);
    x += strlen(faceBuf) * 6 + 4;

    if (data.colorName) {
        toLowerTrunc(colorBuf, data.colorName, 7);
    } else {
        strcpy(colorBuf, "---");
    }
    display.drawStr(x, 38, colorBuf);
    x += strlen(colorBuf) * 6 + 4;

    snprintf(buf, sizeof(buf), "B%d", data.brightness);
    display.drawStr(x, 38, buf);

    display.drawHLine(0, 43, 128);

    // === Row 4 (y=53): DHT22 temp, humidity, ESP fan% ===
    snprintf(buf, sizeof(buf), "T%.1fC", data.temperature);
    display.drawStr(0, 53, buf);

    snprintf(buf, sizeof(buf), "H%.0f%%", data.humidity);
    display.drawStr(48, 53, buf);

    snprintf(buf, sizeof(buf), "F%d%%%c", data.fanPercent, data.fanAutoMode ? 'A' : ' ');
    display.drawStr(90, 53, buf);

    display.sendBuffer();
}

void displayShowNotification(const char* title, const char* message) {
    display.clearBuffer();
    display.setFont(u8g2_font_6x10_tf);

    // Title line (y=10), truncated to 21 chars
    char titleBuf[22];
    strncpy(titleBuf, title, 21);
    titleBuf[21] = '\0';
    display.drawStr(0, 10, titleBuf);

    display.drawHLine(0, 12, 128);

    // Word-wrap message across up to 4 lines
    if (message && message[0] != '\0') {
        const int maxChars = 21;
        const int maxLines = 4;
        int yPositions[] = {24, 36, 48, 60};

        const char* ptr = message;
        for (int line = 0; line < maxLines && *ptr; line++) {
            int len = strlen(ptr);
            int lineLen = (len > maxChars) ? maxChars : len;

            // Try to break at a space if we need to truncate
            if (len > maxChars) {
                int breakAt = maxChars;
                for (int i = maxChars - 1; i > maxChars / 2; i--) {
                    if (ptr[i] == ' ') {
                        breakAt = i;
                        break;
                    }
                }
                lineLen = breakAt;
            }

            char lineBuf[22];
            strncpy(lineBuf, ptr, lineLen);
            lineBuf[lineLen] = '\0';
            display.drawStr(0, yPositions[line], lineBuf);

            ptr += lineLen;
            // Skip the space at the wrap point
            if (*ptr == ' ') ptr++;
        }
    }

    display.sendBuffer();
}

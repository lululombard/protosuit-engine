#include "display.h"
#include "config.h"
#include <U8g2lib.h>
#include <Wire.h>

static U8G2_SSD1306_128X64_NONAME_F_HW_I2C display(U8G2_R0, U8X8_PIN_NONE, I2C_SCL, I2C_SDA);

void displayInit() {
    display.begin();
    display.setContrast(255);
}

void displayUpdate(const DisplayData& data) {
    display.clearBuffer();

    // Top row: Connection status and shader
    display.setFont(u8g2_font_6x10_tf);

    // Pi connection indicator
    display.drawStr(0, 10, data.piAlive ? "PI" : "--");

    // Controller count
    char ctrlStr[8];
    snprintf(ctrlStr, sizeof(ctrlStr), "C:%d", data.controllerCount);
    display.drawStr(20, 10, ctrlStr);

    // Shader name (truncate if needed)
    if (data.shader && data.shader[0] != '\0') {
        char shaderDisplay[12];
        strncpy(shaderDisplay, data.shader, 10);
        shaderDisplay[10] = '\0';
        display.drawStr(50, 10, shaderDisplay);
    }

    display.drawHLine(0, 14, 128);

    // Row 2: Fan info
    char fanStr[26];
    snprintf(fanStr, sizeof(fanStr), "Fan:%3d%%%c RPM:%4lu",
             data.fanPercent,
             data.fanAutoMode ? 'A' : ' ',
             data.fanRpm);
    display.drawStr(0, 26, fanStr);

    display.drawHLine(0, 30, 128);

    // Row 3-4: Temperature and Humidity (larger)
    display.setFont(u8g2_font_10x20_tf);

    char tempStr[16];
    snprintf(tempStr, sizeof(tempStr), "%.1fC", data.temperature);
    display.drawStr(0, 50, tempStr);

    char humStr[16];
    snprintf(humStr, sizeof(humStr), "%.0f%%", data.humidity);
    display.drawStr(70, 50, humStr);

    // Labels
    display.setFont(u8g2_font_6x10_tf);
    display.drawStr(0, 62, "Temp");
    display.drawStr(70, 62, "Humid");

    display.sendBuffer();
}

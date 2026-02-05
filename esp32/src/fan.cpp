#include "fan.h"
#include "config.h"

static volatile unsigned long pulseCount = 0;
static unsigned long currentRpm = 0;
static int fanSpeedPercent = 50;

static void IRAM_ATTR tachISR() {
    pulseCount++;
}

void fanInit() {
    ledcSetup(PWM_CHANNEL, PWM_FREQ, PWM_RESOLUTION);
    ledcAttachPin(PWM_PIN, PWM_CHANNEL);

    pinMode(TACH_PIN, INPUT);
    attachInterrupt(digitalPinToInterrupt(TACH_PIN), tachISR, FALLING);

    fanSetSpeed(fanSpeedPercent);
}

void fanSetSpeed(int percent) {
    percent = constrain(percent, 0, 100);
    fanSpeedPercent = percent;

    // Invert duty cycle due to transistor driver
    int dutyCycle = 255 - (percent * 255 / 100);
    ledcWrite(PWM_CHANNEL, dutyCycle);
}

int fanGetSpeedPercent() {
    return fanSpeedPercent;
}

unsigned long fanGetRpm() {
    return currentRpm;
}

void fanUpdateRpm() {
    noInterrupts();
    unsigned long count = pulseCount;
    pulseCount = 0;
    interrupts();

    currentRpm = (count * 60) / PULSES_PER_REV;
}

#pragma once

// Pin definitions
#define PWM_PIN 33
#define TACH_PIN 35
#define I2C_SDA 21
#define I2C_SCL 22
#define DHT_PIN 27

// Teensy serial pins
#define TEENSY_RX 16
#define TEENSY_TX 17

// DHT settings
#define DHT_TYPE DHT22

// PWM settings
#define PWM_FREQ 25000
#define PWM_RESOLUTION 8
#define PWM_CHANNEL 0

// Tachometer settings
#define PULSES_PER_REV 2

// Protocol characters for Pi communication
#define MSG_FROM_PI '>'
#define MSG_TO_PI '<'
#define MSG_SEPARATOR '\t'

// Timing
#define SENSOR_PUBLISH_INTERVAL 1000
#define PI_TIMEOUT 5000

// Serial baud rates
#define PI_BAUD 921600
#define TEENSY_BAUD 115200

#include "sensors.h"
#include "config.h"
#include <DHT.h>

static DHT dht(DHT_PIN, DHT_TYPE);
static float temperature = 0.0;
static float humidity = 0.0;

void sensorsInit() {
    dht.begin();
}

void sensorsUpdate() {
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (!isnan(h) && !isnan(t)) {
        humidity = h;
        temperature = t;
    }
}

float sensorsGetTemperature() {
    return temperature;
}

float sensorsGetHumidity() {
    return humidity;
}

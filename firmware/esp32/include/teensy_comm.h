#pragma once

#include <Arduino.h>

typedef void (*TeensyMessageCallback)(const String& msg);

void teensyCommInit();
void teensyCommSetCallback(TeensyMessageCallback cb);
void teensyCommProcess();
void teensyCommSend(const String& data);

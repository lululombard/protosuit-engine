# Firmware Documentation

## ESP32 Firmware (esp32/)

**Overview:** PlatformIO C++ project targeting esp32dev. Handles visor sensors, fan control, OLED display, and bridges MQTT <-> Teensy communication.

**Build & Upload:**
```bash
./esp32/build_and_upload.sh
```
Restarts protosuit-espbridge service after upload.

**Dependencies (platformio.ini):**
- ArduinoJson 7.3
- U8g2 2.35
- Adafruit DHT sensor library
- Adafruit Unified Sensor

**Modules:**

| Module | File | Purpose |
|--------|------|---------|
| Main | src/main.cpp | Init, main loop, coordination |
| Sensors | sensors.h/cpp | DHT22 temperature/humidity reading |
| Fan | fan.h/cpp | PWM fan control + tachometer RPM |
| Fan Curve | fan_curve.h/cpp | Auto fan curves, NVS persistence |
| Display | display.h/cpp | SSD1306 OLED status display |
| MQTT Bridge | mqtt_bridge.h/cpp | Serial <-> MQTT gateway (Pi side) |
| Teensy Comm | teensy_comm.h/cpp | UART communication with Teensy |
| Config | config.h | GPIO pin definitions, constants |

**Serial Protocol (Pi <-> ESP32):**
- Baud: 921,600 bps
- Pi to ESP32: `>topic\tpayload*CRC\n`
- ESP32 to Pi: `<topic\tpayload*CRC\n`
- CRC-8/SMBUS (polynomial 0x07) checksum on message body
- Messages with invalid CRC are dropped silently
- 512-byte buffer limit on ESP32 side (large payloads are filtered/stripped)

**Python Bridge (espbridge/espbridge.py):**
- Subscribes to `protogen/#`, filters to 9 specific topic patterns for forwarding
- CRC-8 lookup table (256 entries)
- Caches retained MQTT messages, forwards once when ESP32 connects
- Timeout: 10s no messages -> marks ESP32 offline
- Threading: main loop (reconnect/timeout), serial read thread, serial write thread (50ms delay between writes)

**Fan Control:**
- PWM on GPIO 33 (21.6 kHz, 8-bit, inverted duty cycle due to transistor driver)
- Tachometer on GPIO 35 (FALLING edge, 2 pulses/revolution)
- Speed clamped to 0-100%

**Fan Curve System:**
- Auto mode: fan speed = max(temperature curve, humidity curve)
- Manual mode: direct percentage control
- Linear interpolation between curve points
- Max 8 points per curve (compile-time limit)
- Persisted to ESP32 NVS (non-volatile storage) via Preferences API
- Default temperature curve: 15C->0%, 20C->30%, 25C->50%, 30C->80%, 35C->100%
- Default humidity curve: 30%->0%, 40%->40%, 60%->60%, 80%->100%
- Published every 30 seconds + on boot + on config change

**OLED Display Layout:**
```
+-----------------------------+
| PI    C:2    SHADER         |  (status bar)
+-----------------------------+
| Fan:75% A   RPM:2150        |  (fan info)
+-----------------------------+
|        24.5C    45%         |  (sensor readings)
|        Temp    Humid        |
+-----------------------------+
```
- "PI" shows when Pi heartbeat active (5s timeout)
- "A" indicates auto fan mode
- Updated every ~1 second

**Teensy Menu System:**
The ESP32 acts as a proxy between MQTT and Teensy, managing a menu with 12 parameters:

| Parameter | Type | Range | Default | Options/Labels |
|-----------|------|-------|---------|----------------|
| face | Select | 0-8 | 0 | DEFAULT, ANGRY, DOUBT, FROWN, LOOKUP, SAD, AUDIO1, AUDIO2, AUDIO3 |
| bright | Range | 0-254 | 75 | Numeric brightness |
| accentBright | Range | 0-254 | 127 | Numeric |
| microphone | Toggle | 0-1 | 1 | OFF, ON |
| micLevel | Range | 0-10 | 5 | Numeric |
| boopSensor | Toggle | 0-1 | 1 | OFF, ON |
| spectrumMirror | Toggle | 0-1 | 1 | OFF, ON |
| faceSize | Range | 0-10 | 7 | Numeric |
| color | Select | 0-11 | 0 | BASE, YELLOW, ORANGE, WHITE, GREEN, PURPLE, RED, BLUE, RAINBOW, RAINBOWNOISE, HORIZONTALRAINBOW, BLACK |
| hueF | Range | 0-254 | 0 | Numeric |
| hueB | Range | 0-254 | 0 | Numeric |
| effect | Select | 0-9 | 0 | NONE, PHASEY, PHASEX, PHASER, GLITCHX, MAGNET, FISHEYE, HBLUR, VBLUR, RBLUR |

Commands to Teensy (text over UART): `GET ALL`, `SET PARAM VALUE`, `SAVE`
Responses: `PARAM=VALUE`, `OK SAVED`, `ERR <message>`

Schema published as retained MQTT on connect. Web UI auto-generates controls from schema.

**Startup Sequence:**
1. mqttBridgeInit() -- Init serial for Pi
2. teensyCommInit() -- Init serial for Teensy
3. displayInit() -- Init OLED
4. sensorsInit() -- Init DHT22
5. fanInit() -- Init PWM + tachometer interrupt
6. fanCurveInit() -- Setup curve state
7. fanCurveLoad() -- Load NVS settings
8. Set message callbacks
9. Publish alive=true + initial fancurve
10. 3s delay for Pi startup, then publish schema + request Teensy state

**Main Loop (every iteration):**
- Process serial messages (MQTT bridge + Teensy)
- Every 1s: update RPM, read sensors, auto fan control, update display, publish sensors
- Every 30s: republish fancurve config

---

## ProtoTracer / Teensy 4.0 (ProtoTracer/)

**Overview:** Git submodule -- fork of [coelacant1/ProtoTracer](https://github.com/coelacant1/ProtoTracer), adapted for ESP32/Pi communication.
- Fork: [lululombard/ProtoTracer](https://github.com/lululombard/ProtoTracer)

**What it does:**
- Real-time 3D LED rendering engine for Teensy 4.0
- Drives [WS35 LED matrix panels](https://coelacant1.gumroad.com/l/ws35) (design by Coela Can't!)
- Face animations with multiple expressions
- Audio visualization (FFT-based)
- Post-processing effects (phase, glitch, fisheye, blur, etc.)
- Communicates with ESP32 via UART serial (text commands)

**Build & Upload:**
```bash
./ProtoTracer/build_and_upload.sh
```
- PlatformIO environment: `teensy40ws35`
- Shows Teensy uploader GUI on the HDMI displays (DISPLAY=:0)
- Kills existing teensy loader before upload, kills uploader UI after
- Uses project-root venv: `env/bin/pio`

**Communication Protocol:**
- UART serial at 921,600 baud (ESP32 GPIO 16 RX / 17 TX)
- Text-based, newline-terminated
- Commands: `GET ALL`, `SET <PARAM> <VALUE>`, `SAVE`
- Responses: `<PARAM>=<VALUE>`, `OK SAVED`, `ERR <msg>`
- Parameters managed by ESP32 menu system (see above)

**USB Connection:** See [hardware docs](hardware.md#pi-to-teensy-40----usb-without-5v-power) for details. USB is only used for firmware uploads, runtime communication goes through the ESP32 UART bridge.

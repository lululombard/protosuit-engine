# ESPBridge

Serial bridge between MQTT and ESP32. Forwards filtered MQTT messages to the ESP32 over serial and publishes ESP32 sensor data back to MQTT.

## Serial Protocol

- Pi to ESP32: `>topic\tpayload*XX\n` (CRC-8/SMBUS checksum)
- ESP32 to Pi: `<topic\tpayload*XX\n`
- See [firmware/README.md](../../firmware/README.md) for full protocol details (buffer limits, threading, CRC table)

## MQTT Topics

### Subscribes
- `protogen/#` -all messages, filtered to forward only topics the ESP32 handles:
  - `protogen/visor/esp/set/fan`, `protogen/visor/esp/set/fanmode`
  - `protogen/visor/esp/config/fancurve`
  - `protogen/fins/renderer/status/shader` (stripped to current+transition only)
  - `protogen/fins/bluetoothbridge/status/devices`
  - `protogen/visor/notifications`
  - `protogen/visor/teensy/menu/{set,get,save}`

### Publishes (from ESP32)
- `protogen/visor/esp/status/sensors` -temperature, humidity, fan RPM (retained)
- `protogen/visor/esp/status/alive` -ESP32 connection status (retained)
- `protogen/visor/teensy/raw` -raw Teensy serial messages
- `protogen/visor/teensy/menu/status/*`, `protogen/visor/teensy/menu/schema` -Teensy menu data (retained)

## Configuration

Reads from `config.yaml` section: `esp32` (serial_port, baud_rate)

Supports `--port` and `--baud` CLI arguments.

## Dependencies

- paho-mqtt, pyserial

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/espbridge/espbridge.py --port /dev/ttyUSB0 --baud 921600
```

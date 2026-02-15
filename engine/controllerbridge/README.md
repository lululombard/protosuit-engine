# ControllerBridge

Monitors Bluetooth gamepad connections via bluetoothbridge, reads evdev input events, and forwards mapped button presses to the launcher.

## MQTT Topics

### Subscribes
- `protogen/fins/bluetoothbridge/status/devices` -gamepad connection/disconnection events
- `protogen/fins/controllerbridge/assign` -assign a controller to a display (`{"mac": "...", "display": "left|right"}`)
- `protogen/fins/controllerbridge/status/assignments` -restore retained assignments on startup

### Publishes
- `protogen/fins/controllerbridge/status/assignments` -current controller-to-display assignments (retained)
- `protogen/fins/launcher/input/exec` -forwarded input events (`{"key", "action", "display"}`, QoS 0)
- `protogen/global/notifications` -controller connect/disconnect notifications

## Configuration

Reads from `config.yaml` section: `controllerbridge.button_mapping` (falls back to `bluetoothbridge`)

Default button mapping: BTN_SOUTH=a, BTN_EAST=b, ABS_HAT0X=dpad_x, ABS_HAT0Y=dpad_y

## Dependencies

- paho-mqtt, evdev
- Requires read access to `/dev/input/event*` devices

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/controllerbridge/controllerbridge.py
```

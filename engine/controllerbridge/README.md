# ControllerBridge

Monitors Bluetooth gamepad connections via bluetoothbridge, reads evdev input events, and forwards mapped button presses to the launcher. Supports three assignment slots: left display, right display, and a dedicated presets controller for gamepad combo activation.

## MQTT Topics

### Subscribes
- `protogen/fins/bluetoothbridge/status/devices` -gamepad connection/disconnection events
- `protogen/fins/controllerbridge/assign` -assign a controller to a slot (`{"mac": "...", "display": "left|right|presets"}`)
- `protogen/fins/controllerbridge/status/assignments` -restore retained assignments on startup
- `protogen/fins/launcher/status/presets` -load preset gamepad combos for combo detection

### Publishes
- `protogen/fins/controllerbridge/status/assignments` -current controller-to-slot assignments (retained)
- `protogen/fins/launcher/input/exec` -forwarded input events (`{"key", "action", "display"}`, QoS 0)
- `protogen/fins/launcher/preset/activate` -preset activation triggered by gamepad combo
- `protogen/global/notifications` -controller connect/disconnect notifications

## Assignment Slots

- **left** / **right**: forward gamepad input to launcher for executable control
- **presets**: dedicated combo controller — tracks raw button state and matches against preset gamepad combos. Does NOT forward input to launcher. 1-second cooldown between combo activations.

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

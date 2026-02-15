# BluetoothBridge

Manages Bluetooth scanning, pairing, connecting, and disconnecting via the BlueZ D-Bus API. Separates gamepads and audio devices onto configurable HCI adapters and publishes device state for other services to consume.

## MQTT Topics

### Subscribes
- `protogen/fins/bluetoothbridge/scan/start` -start BT discovery on both adapters
- `protogen/fins/bluetoothbridge/scan/stop` -stop BT discovery
- `protogen/fins/bluetoothbridge/connect` -connect device (JSON `{mac}`)
- `protogen/fins/bluetoothbridge/disconnect` -disconnect device (JSON `{mac}`)
- `protogen/fins/bluetoothbridge/unpair` -remove device (JSON `{mac}`)
- `protogen/fins/bluetoothbridge/bluetooth/restart` -restart bluetoothd and re-pair
- `protogen/fins/bluetoothbridge/forget_disconnected` -remove all disconnected devices
- `protogen/fins/bluetoothbridge/status/last_audio_device` -retained message for auto-reconnect

### Publishes
- `protogen/fins/bluetoothbridge/status/scanning` -scan active flag (retained)
- `protogen/fins/bluetoothbridge/status/devices` -gamepad device list (retained)
- `protogen/fins/bluetoothbridge/status/audio_devices` -audio device list (retained)
- `protogen/fins/bluetoothbridge/status/connection` -per-device connection events
- `protogen/fins/bluetoothbridge/status/last_audio_device` -last connected speaker (retained)
- `protogen/global/notifications` -user-facing connect/disconnect notifications

## Configuration

Reads from `config.yaml` section: `bluetoothbridge.adapters` (gamepads adapter, audio adapter)

## Dependencies

- paho-mqtt, PyGObject (gi), pydbus
- BlueZ 5 (bluetoothd) with D-Bus API
- `bluetoothbridge/bluez_dbus.py` for adapter/device/agent wrappers

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/bluetoothbridge/bluetoothbridge.py
```

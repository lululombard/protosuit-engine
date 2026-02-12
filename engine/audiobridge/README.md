# AudioBridge

Manages PulseAudio volume control, audio output device switching, and Bluetooth speaker tracking via MQTT. Monitors external volume changes (e.g. BT speaker hardware buttons) and republishes them.

## MQTT Topics

### Subscribes
- `protogen/fins/audiobridge/volume/set` -set volume (integer or JSON `{volume}`)
- `protogen/fins/audiobridge/audio/device/set` -switch output device (JSON `{device}`)
- `protogen/fins/bluetoothbridge/status/audio_devices` -react to BT speaker connect/disconnect
- `protogen/fins/audiobridge/status/audio_device/current` -retained message to restore last device

### Publishes
- `protogen/fins/audiobridge/status/volume` -current volume, min, max (retained)
- `protogen/fins/audiobridge/status/audio_devices` -available output devices (retained)
- `protogen/fins/audiobridge/status/audio_device/current` -active output device (retained)
- `protogen/visor/notifications` -speaker connect/disconnect notifications

## Configuration

Reads from `config.yaml` section: `audiobridge`
- `volume.default`, `volume.min`, `volume.max`
- `audio_device.auto_reconnect`, `audio_device.fallback_to_non_hdmi`, `audio_device.exclude_hdmi`

## Dependencies

- paho-mqtt, pulsectl
- PulseAudio (pactl)
- `audiobridge/audio_device_manager.py` for PulseAudio sink operations

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/audiobridge/audiobridge.py
```

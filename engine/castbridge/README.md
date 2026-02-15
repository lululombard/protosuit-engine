# CastBridge

Manages shairport-sync (AirPlay) and spotifyd (Spotify Connect) services via systemd/D-Bus, with bidirectional volume sync and playback tracking.

## MQTT Topics

### Subscribes
- `protogen/fins/castbridge/airplay/enable` -enable/disable AirPlay (`{"enable": true}`)
- `protogen/fins/castbridge/airplay/config` -update AirPlay config (device_name, password)
- `protogen/fins/castbridge/spotify/enable` -enable/disable Spotify (`{"enable": true}`)
- `protogen/fins/castbridge/spotify/config` -update Spotify config (device_name, username, password)
- `protogen/fins/castbridge/spotify/event` -spotifyd onevent playback events
- `protogen/fins/castbridge/airplay/playback/#` -shairport-sync metadata, play state, cover, volume
- `protogen/fins/audiobridge/status/volume` -system volume for bidirectional sync

### Publishes
- `protogen/fins/castbridge/status/airplay` -AirPlay service status (retained)
- `protogen/fins/castbridge/status/spotify` -Spotify service status (retained)
- `protogen/fins/castbridge/status/airplay/playback` -AirPlay now-playing state (retained)
- `protogen/fins/castbridge/status/airplay/playback/cover` -AirPlay cover art (retained)
- `protogen/fins/castbridge/status/spotify/playback` -Spotify now-playing state (retained)
- `protogen/fins/castbridge/status/{service}/health` -systemd health (retained)
- `protogen/fins/castbridge/status/{service}/logs` -journal log stream
- `protogen/fins/audiobridge/volume/set` -volume commands to audiobridge
- `protogen/global/notifications` -service lifecycle notifications

## Configuration

Reads from `config.yaml` sections: `cast.airplay`, `cast.spotify`, `cast.lyrics`, `mqtt`

## Dependencies

- paho-mqtt, pydbus (via ServiceController), PyGObject
- System services: shairport-sync, spotifyd, mosquitto

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/castbridge/castbridge.py
```

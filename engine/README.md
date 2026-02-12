# Protosuit Engine

The `engine/` directory contains all Python services, shared utilities, and configuration modules that make up the Protosuit Engine software layer. Nine independent services communicate via MQTT, with shared modules for logging, MQTT client setup, D-Bus integration, and systemd service control.

## Services

| Service | Directory | Role | Tech |
|---------|-----------|------|------|
| [Renderer](renderer/) | `renderer/` | OpenGL shader rendering | ModernGL + Pygame |
| [Launcher](launcher/) | `launcher/` | Audio/video/executable playback | mpv, ffplay, xdotool |
| [Web](web/) | `web/` | Browser control interface | Flask |
| [BluetoothBridge](bluetoothbridge/) | `bluetoothbridge/` | BT discovery, pairing, connection | D-Bus, BlueZ |
| [AudioBridge](audiobridge/) | `audiobridge/` | Audio device/volume management | pulsectl, PulseAudio |
| [ControllerBridge](controllerbridge/) | `controllerbridge/` | Gamepad input forwarding | evdev + D-Bus |
| [CastBridge](castbridge/) | `castbridge/` | AirPlay, Spotify, lyrics | D-Bus, systemd, lrclib.net |
| [NetworkingBridge](networkingbridge/) | `networkingbridge/` | Wi-Fi client/AP, NAT routing | hostapd, dnsmasq |
| [ESPBridge](espbridge/) | `espbridge/` | ESP32 serial bridge | pyserial (CRC-8/SMBUS) |

**Supporting services** (not in engine/): X11 (`xserver`), MQTT broker (`mosquitto`), audio server (`pulseaudio`)

## Shared Modules

| Module | Path | Purpose |
|--------|------|---------|
| MQTT Client | `utils/mqtt_client.py` | Paho MQTT wrapper with auto-reconnect |
| Logger | `utils/logger.py` | Structured logging for all services |
| Service Controller | `utils/service_controller.py` | Generic systemd wrapper via pydbus (D-Bus) |
| Config Loader | `config/loader.py` | YAML config parser (`config.yaml` at project root) |

## Communication

- **MQTT**: All inter-service messaging under `protogen/fins/*` and `protogen/visor/*`
- **D-Bus**: BlueZ (Bluetooth), systemd (service control), PulseAudio (audio sinks)
- **Serial**: ESP32 <-> Pi (tab-separated with CRC-8 checksum, 921,600 baud), ESP32 <-> Teensy (text commands)

## Configuration

Edit `config.yaml` (at project root) to customize the system. Key sections:

```yaml
default_animation: "aperture"       # Boot animation

animations:                         # Shader definitions with uniforms
  aperture:
    name: "Aperture"
    left_shader: "aperture.glsl"
    right_shader: "aperture.glsl"
    render_scale: 1.0
    uniforms:
      speed: {type: float, value: 1.0, min: 0.0, max: 5.0, step: 0.1}

transitions:                        # Cross-fade settings
  duration: 0.75
  blur: {enabled: true, strength: 8.0}

bluetoothbridge:                    # BT adapter assignment
  adapters: {gamepads: "hci1", audio: "hci1"}

controllerbridge:                   # Evdev button mapping
  button_mapping: {BTN_SOUTH: "a", BTN_EAST: "b"}

audiobridge:                        # Audio device settings
  volume: {default: 50, min: 0, max: 100}
  audio_device: {auto_reconnect: true, exclude_hdmi: true}

cast:                               # AirPlay/Spotify + lyrics
  lyrics: {enabled: true, priority: ["airplay", "spotify"]}

espbridge:                          # ESP32 serial config
  serial: {port: "/dev/ttyUSB0", baud: 921600}
```

**Asset directories** (auto-scanned): `assets/shaders/`, `assets/audio/`, `assets/video/`, `assets/executables/`

---

# MQTT API Reference

All inter-service communication in the Protosuit Engine uses MQTT via the local Mosquitto broker. This section covers every MQTT topic published or subscribed to across all services.

## Conventions

| Convention | Detail |
|---|---|
| Broker | `localhost:1883` (Mosquitto) |
| QoS | 0 for all messages unless noted otherwise |
| Retained topics | Persist across broker restarts. Marked with **R** in tables below. |
| Display values | `"left"`, `"right"`, `"both"` |
| Uniform types | `"float"`, `"int"`, `"vec2"`, `"vec3"`, `"vec4"` |
| Payload encoding | UTF-8 JSON unless noted otherwise. Binary payloads are noted explicitly. |
| Empty payload | Send a zero-length message or omit the payload entirely. |

---

## Renderer

**Topic prefix:** `protogen/fins/renderer/`

### Commands

| Topic | Payload | R | Description |
|---|---|---|---|
| `set/shader/file` | JSON | | Load a shader by name with optional transition |
| `set/shader/uniform` | JSON | | Set a shader uniform parameter |
| `config/reload` | empty | | Reload `config.yaml` at runtime |

#### `set/shader/file`

```json
{
  "display": "both",
  "name": "idle",
  "transition_duration": 0.75
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `display` | string | yes | Target display: `"left"`, `"right"`, `"both"` |
| `name` | string | yes | Shader filename (without extension) |
| `transition_duration` | float | no | Crossfade duration in seconds (default from config) |

#### `set/shader/uniform`

```json
{
  "display": "both",
  "name": "speed",
  "type": "float",
  "value": 2.5
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `display` | string | yes | Target display |
| `name` | string | yes | Uniform variable name |
| `type` | string | yes | `"float"`, `"int"`, `"vec2"`, `"vec3"`, `"vec4"` |
| `value` | varies | yes | Scalar or array matching the type |

### Status (retained)

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/performance` | JSON | **R** | FPS, resolution, frame timing |
| `status/shader` | JSON | **R** | Available shaders, current animation, transition state |
| `status/uniform` | JSON | **R** | Uniform values with metadata (min/max/step) |

#### `status/performance`

```json
{
  "fps": 60.0,
  "resolution": [64, 32],
  "frame_time_ms": 16.6
}
```

#### `status/shader`

```json
{
  "available": ["idle", "angry", "happy", "rainbow"],
  "current": {
    "left": "idle",
    "right": "idle"
  },
  "transitioning": false,
  "transition_progress": 0.0
}
```

#### `status/uniform`

```json
{
  "speed": {
    "type": "float",
    "value": 1.0,
    "min": 0.0,
    "max": 10.0,
    "step": 0.1
  }
}
```

---

## Launcher

**Topic prefix:** `protogen/fins/launcher/`

### Commands

| Topic | Payload | R | Description |
|---|---|---|---|
| `start/audio` | string or JSON | | Play audio file (stackable, multiple can play) |
| `start/video` | string or JSON | | Play video file (exclusive, one at a time) |
| `start/exec` | string | | Run an executable / script |
| `input/exec` | JSON | | Send keyboard input to running executable |
| `stop/audio` | string | | Gracefully stop audio (`"filename"` or `"all"`) |
| `stop/video` | empty | | Gracefully stop video |
| `stop/exec` | empty | | Gracefully stop executable |
| `kill/audio` | string | | Force kill audio (`"filename"` or `"all"`) |
| `kill/video` | empty | | Force kill video |
| `kill/exec` | empty | | Force kill executable |
| `config/reload` | empty | | Rescan asset directories |

#### `start/audio`

Simple form (string):
```
file.mp3
```

JSON form:
```json
{
  "name": "file.mp3"
}
```

#### `start/video`

Simple form (string):
```
file.mp4
```

JSON form:
```json
{
  "name": "file.mp4"
}
```

#### `input/exec`

```json
{
  "key": "a",
  "action": "key",
  "display": "left"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `key` | string | yes | Key name (e.g. `"a"`, `"space"`, `"enter"`) |
| `action` | string | yes | `"key"` (press+release), `"keydown"` (press), `"keyup"` (release) |
| `display` | string | yes | Target display for the input |

### Status (retained)

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/audio` | JSON | **R** | Currently playing and available audio files |
| `status/video` | JSON | **R** | Currently playing and available video files |
| `status/exec` | JSON | **R** | Currently running executable and available scripts |

#### `status/audio`

```json
{
  "playing": ["file.mp3"],
  "available": ["file.mp3", "alert.wav", "music.ogg"]
}
```

#### `status/video`

```json
{
  "playing": "file.mp4",
  "available": ["file.mp4", "intro.mp4"]
}
```

#### `status/exec`

```json
{
  "running": "script.sh",
  "pid": 1234,
  "available": ["script.sh", "game.sh"]
}
```

### Internal

| Topic | Payload | R | Description |
|---|---|---|---|
| `setup` | varies | | Published by exec_launcher during game setup |

---

## BluetoothBridge

**Topic prefix:** `protogen/fins/bluetoothbridge/`

Handles Bluetooth device discovery, pairing, and connection via D-Bus (BlueZ API).

### Commands

| Topic | Payload | R | Description |
|---|---|---|---|
| `scan/start` | empty | | Start BLE/classic scanning |
| `scan/stop` | empty | | Stop scanning |
| `connect` | JSON | | Connect to a device by MAC |
| `disconnect` | JSON | | Disconnect a device by MAC |
| `unpair` | JSON | | Remove (forget) a paired device |
| `forget_disconnected` | empty | | Remove all disconnected devices |
| `bluetooth/restart` | empty | | Restart the BlueZ service |

#### `connect` / `disconnect` / `unpair`

```json
{
  "mac": "AA:BB:CC:DD:EE:FF"
}
```

### Status (retained)

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/scanning` | boolean | **R** | `true` while scanning, `false` otherwise |
| `status/devices` | JSON array | **R** | Discovered/paired gamepad devices |
| `status/audio_devices` | JSON array | **R** | Discovered/paired audio devices |
| `status/connection` | JSON | **R** | Connection attempt status |
| `status/last_audio_device` | string | **R** | MAC of last selected BT audio device |

#### `status/devices`

```json
[
  {
    "mac": "AA:BB:CC:DD:EE:FF",
    "name": "Xbox Wireless Controller",
    "paired": true,
    "connected": true
  }
]
```

#### `status/audio_devices`

```json
[
  {
    "mac": "11:22:33:44:55:66",
    "name": "JBL Speaker",
    "paired": true,
    "connected": true,
    "type": "audio"
  }
]
```

---

## AudioBridge

**Topic prefix:** `protogen/fins/audiobridge/`

Manages audio output devices and volume via pulsectl (PulseAudio).

### Commands

| Topic | Payload | R | Description |
|---|---|---|---|
| `volume/set` | JSON | | Set system volume (0-100) |
| `audio/device/set` | JSON | | Select a PulseAudio output sink |

#### `volume/set`

```json
{
  "volume": 75
}
```

#### `audio/device/set`

```json
{
  "device": "bluez_sink.XX_YY_ZZ_AA_BB_CC"
}
```

### Status (retained)

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/volume` | JSON | **R** | Current volume with min/max bounds |
| `status/audio_devices` | JSON array | **R** | Available PulseAudio sinks |
| `status/audio_device/current` | JSON | **R** | Currently active output device |

#### `status/volume`

```json
{
  "volume": 50,
  "min": 0,
  "max": 100
}
```

#### `status/audio_devices`

```json
[
  {
    "name": "bluez_sink.XX_YY_ZZ_AA_BB_CC",
    "description": "JBL Speaker",
    "type": "bluetooth"
  }
]
```

#### `status/audio_device/current`

```json
{
  "device": "bluez_sink.XX_YY_ZZ_AA_BB_CC",
  "description": "JBL Speaker",
  "type": "bluetooth"
}
```

---

## ControllerBridge

**Topic prefix:** `protogen/fins/controllerbridge/`

Reads gamepad input via evdev, forwards to launcher as MQTT.

**Data flow:** bluetoothbridge publishes device list -> controllerbridge maps MAC to evdev -> reads input -> publishes to `launcher/input/exec`.

### Commands

| Topic | Payload | R | Description |
|---|---|---|---|
| `assign` | JSON | **R** | Assign or unassign a controller to a display |

#### `assign`

Assign a controller:
```json
{
  "mac": "AA:BB:CC:DD:EE:FF",
  "display": "left"
}
```

Unassign a display:
```json
{
  "mac": null,
  "display": "left"
}
```

### Status (retained)

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/assignments` | JSON | **R** | Current controller-to-display mapping |

#### `status/assignments`

```json
{
  "left": {
    "mac": "AA:BB:CC:DD:EE:FF",
    "name": "Xbox Wireless Controller",
    "connected": true
  },
  "right": null
}
```

---

## CastBridge

**Topic prefix:** `protogen/fins/castbridge/`

Manages AirPlay (shairport-sync) and Spotify Connect (spotifyd), plus real-time lyrics.

### Control Commands

| Topic | Payload | R | Description |
|---|---|---|---|
| `airplay/enable` | JSON | | Enable or disable AirPlay service |
| `airplay/config` | JSON | | Configure AirPlay device name and password |
| `spotify/enable` | JSON | | Enable or disable Spotify Connect service |
| `spotify/config` | JSON | | Configure Spotify device name and credentials |

#### `airplay/enable` / `spotify/enable`

```json
{
  "enable": true
}
```

#### `airplay/config`

```json
{
  "device_name": "Protosuit",
  "password": ""
}
```

#### `spotify/config`

```json
{
  "device_name": "Protosuit",
  "username": "",
  "password": ""
}
```

### Service Status (retained)

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/airplay` | JSON | **R** | AirPlay service state and config |
| `status/spotify` | JSON | **R** | Spotify service state and config |

#### `status/airplay`

```json
{
  "enabled": false,
  "running": false,
  "device_name": "Protosuit",
  "password": ""
}
```

#### `status/spotify`

```json
{
  "enabled": false,
  "running": false,
  "device_name": "Protosuit",
  "username": "",
  "password": ""
}
```

### Playback Metadata (retained)

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/airplay/playback` | JSON | **R** | AirPlay now-playing metadata |
| `status/spotify/playback` | JSON | **R** | Spotify now-playing metadata |
| `status/airplay/playback/cover` | binary (JPEG) | **R** | AirPlay album art |

#### `status/airplay/playback`

```json
{
  "playing": true,
  "title": "Song",
  "artist": "Artist",
  "album": "Album",
  "genre": "Pop",
  "track_id": "abc",
  "duration_ms": 240000,
  "position_ms": 60000
}
```

#### `status/spotify/playback`

```json
{
  "playing": true,
  "title": "Song",
  "artist": "Artist",
  "cover_url": "https://i.scdn.co/image/...",
  "track_id": "spotify:track:xxx",
  "duration_ms": 240000,
  "position_ms": 60000
}
```

#### `status/airplay/playback/cover`

Binary JPEG payload. Not JSON. Use `mosquitto_sub` with `-C 1` to capture a single image:

```bash
mosquitto_sub -t 'protogen/fins/castbridge/status/airplay/playback/cover' -C 1 > cover.jpg
```

### Lyrics (retained)

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/lyrics` | JSON | **R** | Current synced lyric line and position |
| `status/lyrics/full` | JSON | **R** | Full lyrics for the current track |

#### `status/lyrics`

```json
{
  "source": "spotify",
  "playing": true,
  "loading": false,
  "current_line": "lyrics text",
  "next_line": "next text",
  "current_line_ts": 60000,
  "next_line_ts": 63000,
  "line_index": 5,
  "total_lines": 42,
  "position_ms": 61000,
  "instrumental": false
}
```

#### `status/lyrics/full`

```json
{
  "source": "spotify",
  "track_name": "Song",
  "artist_name": "Artist",
  "instrumental": false,
  "synced_lines": [
    { "ts": 0, "text": "First line" },
    { "ts": 3000, "text": "Second line" }
  ],
  "plain": "unsynced lyrics text"
}
```

### Health Monitoring (retained)

Published every 10 seconds per service.

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/airplay/health` | JSON | **R** | shairport-sync systemd health |
| `status/spotify/health` | JSON | **R** | spotifyd systemd health |

#### Health payload format

```json
{
  "is_enabled": true,
  "is_active": true,
  "active_state": "active",
  "sub_state": "running",
  "memory_mb": 12.5,
  "cpu_percent": 2.1,
  "uptime_seconds": 3600
}
```

### Log Streaming (NOT retained)

Streamed from journalctl in real time. One JSON message per log line.

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/airplay/logs` | JSON | | shairport-sync log output |
| `status/spotify/logs` | JSON | | spotifyd log output |

#### Log payload format

```json
{
  "message": "Playing audio stream.",
  "priority": 6,
  "timestamp": "2025-01-15T12:34:56.789Z",
  "pid": "1234"
}
```

### Internal: shairport-sync Raw Metadata

These topics are published by shairport-sync's MQTT metadata output and consumed by castbridge. They are **not** intended for external use.

| Topic | Payload | R | Description |
|---|---|---|---|
| `airplay/playback/title` | string | | Track title |
| `airplay/playback/artist` | string | | Artist name |
| `airplay/playback/album` | string | | Album name |
| `airplay/playback/genre` | string | | Genre string |
| `airplay/playback/track_id` | string | | Track identifier |
| `airplay/playback/play_start` | empty | | Playback started |
| `airplay/playback/play_end` | empty | | Playback ended |
| `airplay/playback/play_resume` | empty | | Playback resumed |
| `airplay/playback/play_flush` | empty | | Playback flushed (seek/skip) |
| `airplay/playback/cover` | binary (JPEG) | | Album art |
| `airplay/playback/core/astm` | binary | | Duration: 4-byte big-endian milliseconds |
| `airplay/playback/ssnc/prgr` | string | | RTP frame positions (start/current/end) |
| `airplay/playback/ssnc/phbt` | string | | Frame position + monotonic timestamp |

### Internal: spotifyd Event Hook

| Topic | Payload | R | Description |
|---|---|---|---|
| `spotify/event` | JSON | | Published by `spotify_event.sh` on player events |

#### `spotify/event`

```json
{
  "PLAYER_EVENT": "playing",
  "TRACK_ID": "spotify:track:xxx"
}
```

---

## NetworkingBridge

**Topic prefix:** `protogen/fins/networkingbridge/`

Manages Wi-Fi client, access point, and NAT routing via NetworkManager.

### Commands

| Topic | Payload | R | Description |
|---|---|---|---|
| `scan/start` | empty | | Scan for Wi-Fi networks |
| `client/enable` | JSON | | Enable or disable Wi-Fi client mode |
| `client/connect` | JSON | | Connect to a Wi-Fi network |
| `client/disconnect` | empty | | Disconnect from current network |
| `ap/enable` | JSON | | Enable or disable access point |
| `ap/config` | JSON | | Configure access point settings |
| `routing/enable` | JSON | | Enable or disable NAT routing (AP to client) |
| `qrcode/generate` | empty | | Generate QR code for AP connection |

#### `client/enable` / `ap/enable` / `routing/enable`

```json
{
  "enable": true
}
```

#### `client/connect`

```json
{
  "ssid": "NetworkName",
  "password": "pass"
}
```

#### `ap/config`

```json
{
  "ssid": "Protosuit",
  "security": "wpa2",
  "password": "BeepBoop",
  "ip_cidr": "192.168.50.1/24"
}
```

| Security value | Description |
|---|---|
| `"open"` | No authentication |
| `"wpa"` | WPA1 (for legacy devices like PSP) |
| `"wpa2"` | WPA2 (recommended) |

### Status (retained)

| Topic | Payload | R | Description |
|---|---|---|---|
| `status/interfaces` | JSON | **R** | Interface detection status |
| `status/client` | JSON | **R** | Wi-Fi client connection state |
| `status/ap` | JSON | **R** | Access point state and connected clients |
| `status/scan` | JSON array | **R** | Discovered Wi-Fi networks |
| `status/scanning` | boolean | **R** | `true` while scanning |
| `status/qrcode` | JSON | **R** | Base64 QR code PNG for AP credentials |
| `status/connection` | JSON | **R** | Connection status updates |

#### `status/client`

```json
{
  "connected": true,
  "ssid": "HomeNetwork",
  "ip_address": "192.168.1.42",
  "signal_percent": 80
}
```

#### `status/ap`

```json
{
  "enabled": true,
  "ssid": "Protosuit",
  "clients": []
}
```

#### `status/qrcode`

```json
{
  "qrcode": "data:image/png;base64,iVBORw0KGgo..."
}
```

---

## ESPBridge

**Topic prefix:** `protogen/visor/`

Communicates with the ESP32 (fan/sensor controller) and Teensy (LED matrix controller) over serial, bridged to MQTT.

### ESP32 Commands

| Topic | Payload | R | Description |
|---|---|---|---|
| `esp/set/fan` | string | | Set fan speed 0-100% (switches to manual mode) |
| `esp/set/fanmode` | string | | `"auto"` or `"manual"` |
| `esp/config/fancurve` | JSON | | Set fan curve with temperature and humidity points |

#### `esp/set/fan`

```
50
```

#### `esp/config/fancurve`

```json
{
  "mode": "auto",
  "temperature": [
    { "value": 15.0, "fan": 0 },
    { "value": 20.0, "fan": 30 },
    { "value": 25.0, "fan": 50 },
    { "value": 30.0, "fan": 80 },
    { "value": 35.0, "fan": 100 }
  ],
  "humidity": [
    { "value": 30.0, "fan": 0 },
    { "value": 40.0, "fan": 40 },
    { "value": 60.0, "fan": 60 },
    { "value": 80.0, "fan": 100 }
  ]
}
```

### ESP32 Status

| Topic | Payload | R | Description |
|---|---|---|---|
| `esp/status/sensors` | JSON | **R** | Temperature, humidity, fan RPM, duty cycle, mode |
| `esp/status/alive` | string | **R** | `"true"` or `"false"` |
| `esp/status/fancurve` | JSON | **R** | Current fan curve config (same format as command) |

#### `esp/status/sensors`

```json
{
  "temperature": 24.5,
  "humidity": 45.3,
  "rpm": 2150,
  "fan": 75,
  "mode": "auto"
}
```

### Teensy Commands

| Topic | Payload | R | Description |
|---|---|---|---|
| `teensy/menu/set` | JSON | | Set a Teensy parameter value |
| `teensy/menu/get` | empty | | Request all Teensy parameter values |
| `teensy/menu/save` | empty | | Save current settings to EEPROM |

#### `teensy/menu/set`

```json
{
  "param": "bright",
  "value": 5
}
```

#### Teensy Parameters

| Parameter | Range | Description |
|---|---|---|
| `face` | 0-8 | Face animation select |
| `bright` | 0-254 | Main LED brightness |
| `accentBright` | 0-254 | Accent LED brightness |
| `microphone` | 0-1 | Microphone toggle |
| `micLevel` | 0-10 | Microphone sensitivity |
| `boopSensor` | 0-1 | Boop sensor toggle |
| `spectrumMirror` | 0-1 | Spectrum mirror toggle |
| `faceSize` | 0-10 | Face size |
| `color` | 0-11 | Color palette select |
| `hueF` | 0-254 | Front hue value |
| `hueB` | 0-254 | Back hue value |
| `effect` | 0-9 | Effect select |

### Teensy Status

| Topic | Payload | R | Description |
|---|---|---|---|
| `teensy/menu/schema` | JSON | **R** | Parameter definitions with types, ranges, labels |
| `teensy/menu/status/{param}` | JSON | **R** | Per-parameter value and label |
| `teensy/menu/saved` | string | | `"true"` on save confirmation |
| `teensy/menu/error` | JSON | | Error details |
| `teensy/raw` | string | | Raw serial messages from Teensy |

#### `teensy/menu/status/{param}`

```json
{
  "value": 5,
  "label": "LABEL"
}
```

#### `teensy/menu/error`

```json
{
  "error": "message"
}
```

---

## Notifications

**Topic:** `protogen/visor/notifications`

Cross-service notification bus. Published by bluetoothbridge, audiobridge, controllerbridge, and castbridge. Subscribed by espbridge, which forwards messages to the ESP32 OLED display.

| Topic | Payload | R | Description |
|---|---|---|---|
| `protogen/visor/notifications` | JSON | | Service notification for OLED display |

```json
{
  "event": "connected",
  "service": "bluetooth",
  "message": "Xbox Controller connected"
}
```

---

## Miscellaneous

| Topic | Payload | R | Description |
|---|---|---|---|
| `protogen/fins/uniform/query` | empty | | Published by web UI to request uniform state from renderer |

---

## Quick Reference: mosquitto_pub / mosquitto_sub Examples

### Load a shader

```bash
mosquitto_pub -t 'protogen/fins/renderer/set/shader/file' \
  -m '{"display":"both","name":"happy","transition_duration":0.5}'
```

### Set a uniform

```bash
mosquitto_pub -t 'protogen/fins/renderer/set/shader/uniform' \
  -m '{"display":"both","name":"speed","type":"float","value":3.0}'
```

### Play audio

```bash
mosquitto_pub -t 'protogen/fins/launcher/start/audio' -m 'alert.mp3'
```

### Stop all audio

```bash
mosquitto_pub -t 'protogen/fins/launcher/stop/audio' -m 'all'
```

### Start Bluetooth scan

```bash
mosquitto_pub -t 'protogen/fins/bluetoothbridge/scan/start' -n
```

### Connect a Bluetooth device

```bash
mosquitto_pub -t 'protogen/fins/bluetoothbridge/connect' \
  -m '{"mac":"AA:BB:CC:DD:EE:FF"}'
```

### Set volume

```bash
mosquitto_pub -t 'protogen/fins/audiobridge/volume/set' -m '{"volume":60}'
```

### Enable Spotify Connect

```bash
mosquitto_pub -t 'protogen/fins/castbridge/spotify/enable' -m '{"enable":true}'
```

### Connect to Wi-Fi

```bash
mosquitto_pub -t 'protogen/fins/networkingbridge/client/connect' \
  -m '{"ssid":"MyNetwork","password":"secret"}'
```

### Set fan speed

```bash
mosquitto_pub -t 'protogen/visor/esp/set/fan' -m '75'
```

### Set Teensy brightness

```bash
mosquitto_pub -t 'protogen/visor/teensy/menu/set' -m '{"param":"bright","value":200}'
```

### Watch all retained status topics

```bash
mosquitto_sub -t 'protogen/fins/+/status/#' -t 'protogen/visor/+/status/#' -v
```

### Watch notifications

```bash
mosquitto_sub -t 'protogen/visor/notifications' -v
```

### Dump album art to file

```bash
mosquitto_sub -t 'protogen/fins/castbridge/status/airplay/playback/cover' -C 1 > cover.jpg
```

---

## Topic Tree Summary

```
protogen/
  fins/
    renderer/
      set/shader/file
      set/shader/uniform
      config/reload
      status/performance          [R]
      status/shader               [R]
      status/uniform              [R]
    launcher/
      start/audio
      start/video
      start/exec
      input/exec
      stop/audio
      stop/video
      stop/exec
      kill/audio
      kill/video
      kill/exec
      config/reload
      setup
      status/audio                [R]
      status/video                [R]
      status/exec                 [R]
    bluetoothbridge/
      scan/start
      scan/stop
      connect
      disconnect
      unpair
      forget_disconnected
      bluetooth/restart
      status/scanning             [R]
      status/devices              [R]
      status/audio_devices        [R]
      status/connection           [R]
      status/last_audio_device    [R]
    audiobridge/
      volume/set
      audio/device/set
      status/volume               [R]
      status/audio_devices        [R]
      status/audio_device/current [R]
    controllerbridge/
      assign                      [R]
      status/assignments          [R]
    castbridge/
      airplay/enable
      airplay/config
      spotify/enable
      spotify/config
      airplay/playback/title              (internal)
      airplay/playback/artist             (internal)
      airplay/playback/album              (internal)
      airplay/playback/genre              (internal)
      airplay/playback/track_id           (internal)
      airplay/playback/play_start         (internal)
      airplay/playback/play_end           (internal)
      airplay/playback/play_resume        (internal)
      airplay/playback/play_flush         (internal)
      airplay/playback/cover              (internal)
      airplay/playback/core/astm          (internal)
      airplay/playback/ssnc/prgr          (internal)
      airplay/playback/ssnc/phbt          (internal)
      spotify/event                       (internal)
      status/airplay              [R]
      status/spotify              [R]
      status/airplay/playback     [R]
      status/spotify/playback     [R]
      status/airplay/playback/cover [R]
      status/lyrics               [R]
      status/lyrics/full          [R]
      status/airplay/health       [R]
      status/spotify/health       [R]
      status/airplay/logs
      status/spotify/logs
    networkingbridge/
      scan/start
      client/enable
      client/connect
      client/disconnect
      ap/enable
      ap/config
      routing/enable
      qrcode/generate
      status/interfaces           [R]
      status/client               [R]
      status/ap                   [R]
      status/scan                 [R]
      status/scanning             [R]
      status/qrcode               [R]
      status/connection           [R]
    uniform/query
  visor/
    esp/set/fan
    esp/set/fanmode
    esp/config/fancurve
    esp/status/sensors            [R]
    esp/status/alive              [R]
    esp/status/fancurve           [R]
    teensy/menu/set
    teensy/menu/get
    teensy/menu/save
    teensy/menu/schema            [R]
    teensy/menu/status/{param}    [R]
    teensy/menu/saved
    teensy/menu/error
    teensy/raw
    notifications
```

`[R]` = retained

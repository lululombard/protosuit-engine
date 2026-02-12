# Protosuit Engine

**The brain of my Protogen fursuit, featuring GLSL shaders on dual round displays, LED matrix visor control, AirPlay/Spotify streaming, Doom, Super Haxagon, Bluetooth gamepads and speakers, and way more than I originally planned.**

My friend [Miggy](https://github.com/Myggi) and I make our Protogen fursuits together, he handles 3D CAD and I handle the electronics and software. My original suit (v1) from 2023 ran a fork of [b0xcat/protocontrol](https://github.com/b0xcat/protocontrol) ([my fork](https://github.com/lululombard/protocontrol)) with 14 basic MAX7219 matrices and no sensors. I wore it at [NFC](https://nordicfuzzcon.org/) and [FBL](https://fblacklight.org/) 2024. It worked, but I wanted more.

In 2023, we found some 5-inch 1080x1080 round displays on AliExpress. Miggy designed and almost finished building a suit around them, looking back they were pretty bulky and heavy. Then in 2024 we found 4-inch 720x720 displays and that's when I jumped on board to use them for my v2 suit and his too. The project was reborn.

Miggy did all the 3D modeling to fit the displays on [b0xcat's Protato base](https://b0xcat.gumroad.com/l/protato), paired with [Coela Can't!'s WS35 LED matrices](https://coelacant1.gumroad.com/l/ws35) and [b0xcat adapters](https://coelacant1.gumroad.com/l/b0xcatadapter). In 2024 the plan was a RockPro64 with two Raspberry Pi Zero 2Ws in USB gadget mode as display drivers. Early 2025 we switched to an RPi 5 with the two Zeros, then in October 2025 I ditched the Zeros entirely and used the Pi 5's dual HDMI output directly, that's when I really restarted the project and wrote the current codebase. I started adapting Shadertoy shaders to run on it, and features just kept getting added from there.

If you're building a Protogen and want animated fin displays, feel free to adapt this for your own build!

### Thank You

- **[Miggy](https://github.com/Myggi)**: for all the 3D CAD, creating some shaders for the project, building our v1 and v2 suits together, hyping me up on everything, pitching great ideas like the now playing with lyrics, and for letting me stay at his place for weeks when we need to work on stuff
- **Kuroda**: for helping with my v1 fursuit, and for building the original b0xcat-based suits with Miggy before I joined in, and for being so welcoming and a big reason I joined the fandom in the first place
- **[b0xcat](https://github.com/b0xcat)**: for the original Protato CAD design that this project builds on, and the PETG thermoformed visor my suit is still using after all these years, I wish him the best
- **[Coela Can't!](https://github.com/coelacant1)**: for the WS35 LED matrices, the b0xcat adapter, and ProtoTracer
- **Shadertoy authors**: most shaders are adapted from Shadertoy, heavily modified for OpenGL ES and uniforms control, original credits are in each `.glsl` file

---

## Quick Start

1. Flash **Raspberry Pi OS Lite (64-bit)** on a microSD card with username `proto`
2. Boot the Pi and run:

```bash
sudo apt update
sudo apt install git ansible -y
git clone --recurse-submodules git@github.com:lululombard/protosuit-engine.git
cd protosuit-engine
ansible/scripts/deploy.sh
```

That's it! The system will auto-configure and start on boot.

---

## Hardware

### Recommended Setup

- **Raspberry Pi 5** (4GB+ RAM recommended)
- **Two 4-inch 720x720 round displays** (search "wisecoco 4 inch 720 round" on AliExpress) with HDMI-MIPI driver boards
- **USB Wi-Fi 6 + Bluetooth dongle** (RTL8851BU chipset), handles both Wi-Fi client and Bluetooth
  - Built-in RPi radio has issues running AP + BT simultaneously; this dongle handles Wi-Fi + 3 BT devices (2 controllers + 1 speaker) smoothly
  - Built-in RPi Wi-Fi is used for AP mode
  - See [ansible/README.md](ansible/README.md#wi-fi-hardware-configuration) for details
- **USB microphone dongle**: for sound-reactive shader audio capture (FFT)

### USB Connections

| Connection | Power | Visible in lsusb | Purpose |
|------------|-------|-------------------|---------|
| Pi ↔ Teensy 4.0 | No USB 5V (VUSB=VIN, no cut trace) | Only during bootloader upload | Firmware uploads only |
| Pi ↔ ESP32 | USB 5V (CH341 needs bus power) | Always (`/dev/ttyUSB0`) | Serial communication (921,600 baud) |

The Teensy is powered from the main PCB 5V 8A rail. The ESP32's CH341 USB-serial chip is not connected to the ESP32 main 5V rail, so it requires USB bus power.

### Custom PCB ([ProtosuitDevBoard/](ProtosuitDevBoard/))

KiCad 9.0 power distribution and interconnect board:

- **9-25V input** via XT60 connector, powered by a USB-C PD 20V to XT60 cable from a power bank (minimizes power loss)
- **1x 5V 5A low-ESR buck-boost**: shared between RPi and 2x LCD displays
- **1x 5V 8A buck-boost**: main PCB powering Teensy 4.0, ESP32, WS35 matrices, and LED strips
- **4x WS35 LED matrix** screw terminal connectors (3-pin, Coela Can't! design)
- **5x LED strip** screw terminal connectors (3-pin): 2x fins, 2x ears, 1x upper arch
- I2C, MAX9814 microphone input (Teensy), DHT22 sensor connector (ESP32), all JST
- MPU6050 gyro/accelerometer (on-board, currently unused)
- Screw terminals and power connectors use ferrule crimps

Currently a validation prototype using off-the-shelf modules (buck converters, ESP32 dev board) with no SMD components. See [Future Plans](#future-plans) for the roadmap toward a production-ready board.

See [docs/hardware.md](docs/hardware.md) for full details including custom footprints and gerber files.

### Display Configuration

Dual 720x720 displays mounted on fursuit fins:
- Left display rotated 90° clockwise
- Right display rotated 90° counter-clockwise
- Extended desktop spanning both displays

---

## Features

- **GLSL Shader Animations**: 33+ shaders with smooth cross-fade transitions, blur effects, and real-time parameter control
- **Media Playback**: Videos (exclusive), audio (stackable), synchronized playback
- **Executables**: Run shell scripts (Doom, Super Haxagon, Ring Ding) across both displays
- **Bluetooth Device Management**: Discover, pair, and connect devices via D-Bus (BlueZ API)
- **Gamepad Input**: Assign controllers to displays with evdev-based input reading and MQTT forwarding
- **Audio Device Control**: Manage output devices and volume via pulsectl (PulseAudio), with auto-reconnect
- **AirPlay & Spotify Connect**: Stream audio with now-playing metadata and cover art
- **Synced Lyrics**: Real-time synchronized lyrics from lrclib.net for AirPlay and Spotify
- **Wi-Fi Management**: Dual-mode networking with AP hotspot, client mode, NAT routing, and QR code sharing
- **ESP32 Visor**: Temperature/humidity monitoring, auto fan curves, OLED status display
- **Teensy LED Visor**: ProtoTracer 3D LED rendering with face animations, audio visualization, and effects
- **Web Control Interface**: Browser-based control with live preview, physics-based sliders, and performance monitoring
- **PSP Remote Controller**: PSP homebrew app as wireless gamepad over MQTT
- **Custom PCB**: KiCad-designed power distribution board with LED matrix/strip connectors

---

## Web Interface

Open your browser to `http://<raspberry-pi-ip>`

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Shader selector, parameter sliders, live preview, FPS monitor, visor status |
| Virtual Controller | `/controller` | Mobile-friendly gamepad UI for testing inputs |
| Bluetooth & Audio | `/bluetooth` | Device scanning, pairing, controller assignment, audio device selection |
| Cast Settings | `/cast` | AirPlay/Spotify enable/config, now-playing with cover art, synced lyrics |
| Networking | `/networking` | Wi-Fi client/AP config, QR code sharing, NAT routing |

The dashboard includes a visor panel with fan curve editor and Teensy LED menu controls (face, brightness, color, effects).

---

## Architecture

### Services

Nine independent Python services + three supporting services, all communicating via MQTT:

| Service | Role | Tech |
|---------|------|------|
| `protosuit-renderer` | OpenGL shader rendering | ModernGL + Pygame |
| `protosuit-launcher` | Audio/video/executable playback | mpv, ffplay, xdotool |
| `protosuit-web` | Browser control interface | Flask |
| `protosuit-bluetoothbridge` | BT discovery, pairing, connection | D-Bus → BlueZ |
| `protosuit-audiobridge` | Audio device/volume management | pulsectl → PulseAudio |
| `protosuit-controllerbridge` | Gamepad input forwarding | evdev + D-Bus |
| `protosuit-castbridge` | AirPlay, Spotify, lyrics | D-Bus → systemd, lrclib.net |
| `protosuit-networkingbridge` | Wi-Fi client/AP, NAT routing | hostapd, dnsmasq |
| `protosuit-espbridge` | ESP32 serial bridge | pyserial (CRC-8/SMBUS) |

**Supporting:** `xserver` (X11), `mosquitto` (MQTT broker), `pulseaudio` (audio server)

### Communication

- **MQTT**: All inter-service messaging under `protogen/fins/*` and `protogen/visor/*`
- **D-Bus**: BlueZ (Bluetooth), systemd (service control), PulseAudio (audio sinks)
- **Serial**: ESP32 ↔ Pi (tab-separated with CRC-8 checksum, 921,600 baud), ESP32 ↔ Teensy (text commands)

---

## MQTT API

Full reference with payloads and examples: **[docs/mqtt-api.md](docs/mqtt-api.md)**

Summary of topic prefixes:

| Prefix | Service | Topics |
|--------|---------|--------|
| `protogen/fins/renderer/` | Renderer | Shader loading, uniforms, performance status |
| `protogen/fins/launcher/` | Launcher | Media start/stop/kill, input forwarding, playback status |
| `protogen/fins/bluetoothbridge/` | Bluetoothbridge | Scan, connect, unpair, device lists |
| `protogen/fins/audiobridge/` | Audiobridge | Volume, device selection, current device |
| `protogen/fins/controllerbridge/` | Controllerbridge | Controller-to-display assignment |
| `protogen/fins/castbridge/` | Castbridge | AirPlay/Spotify config, playback metadata, lyrics, health, logs |
| `protogen/fins/networkingbridge/` | Networkingbridge | Wi-Fi scan, client/AP config, routing, QR codes |
| `protogen/visor/esp/` | ESPBridge | Fan control, fan curves, sensor data |
| `protogen/visor/teensy/` | ESPBridge | Teensy menu (schema, get/set/save, per-param status) |
| `protogen/visor/notifications` | Cross-service | System notifications for OLED display |

---

## Configuration

Edit `config.yaml` to customize the system. Key sections:

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

## Repository Layout

```
protosuit-engine/
├── ansible/              # Ansible deployment playbooks and templates
├── assets/               # Shaders (.glsl), audio, video, executables (.sh)
├── audiobridge/          # Audio device/volume management service
├── bluetoothbridge/      # Bluetooth discovery/pairing service
├── castbridge/           # AirPlay, Spotify Connect, lyrics service
├── config/               # Config loader module
├── controllerbridge/     # Gamepad input forwarding service
├── data/                 # OUI MAC address lookup table
├── docs/                 # Detailed documentation
│   ├── mqtt-api.md       #   Full MQTT topic reference
│   ├── hardware.md       #   PCB, GPIO pinout, USB connections
│   ├── firmware.md       #   ESP32 + ProtoTracer firmware
│   └── psp-controller.md #   PSP homebrew controller
├── esp32/                # ESP32 firmware (PlatformIO C++)
├── espbridge/            # ESP32 serial bridge service
├── launcher/             # Media/executable launcher service
├── networkingbridge/     # Wi-Fi client/AP management service
├── ProtoTracer/          # Teensy LED visor firmware (git submodule)
├── ProtosuitDevBoard/    # KiCad 8.0 PCB design
├── psp-controller/       # PSP homebrew MQTT controller (C/PSP SDK)
├── renderer/             # OpenGL shader renderer service
├── scripts/              # Utility scripts
├── tests/                # Integration tests
├── utils/                # Shared Python modules (MQTT, logger, D-Bus, etc.)
├── web/                  # Flask web interface + static assets
├── config.yaml           # Main configuration file
├── protosuit_engine.py   # Development launcher (all services in one process)
└── requirements.txt      # Python dependencies
```

---

## Firmware

### ESP32 ([esp32/](esp32/))

PlatformIO C++ firmware for the visor ESP32: temperature/humidity sensors, fan control with auto curves, OLED status display, and serial bridge between MQTT and Teensy.

```bash
./esp32/build_and_upload.sh    # Build, upload, restart espbridge service
```

See [docs/firmware.md](docs/firmware.md) for modules, serial protocol, fan curve system, and Teensy menu parameters.

### ProtoTracer / Teensy 4.0 ([ProtoTracer/](ProtoTracer/))

Git submodule, fork of [coelacant1/ProtoTracer](https://github.com/coelacant1/ProtoTracer), adapted for ESP32/Pi communication.

Real-time 3D LED rendering engine: face animations, audio visualization, post-processing effects. Drives WS35 LED matrix panels.

- Fork: [lululombard/ProtoTracer](https://github.com/lululombard/ProtoTracer)

```bash
./ProtoTracer/build_and_upload.sh    # Build, upload via Teensy loader GUI
```

See [docs/firmware.md](docs/firmware.md) for build details and communication protocol.

---

## PSP Controller ([psp-controller/](psp-controller/))

PSP homebrew app that turns a PlayStation Portable into a wireless MQTT gamepad. Connects via Wi-Fi, sends D-pad and button events to the launcher.

See [docs/psp-controller.md](docs/psp-controller.md) for build, deploy, and configuration.

---

## Service Management

```bash
# Check status
sudo systemctl status protosuit-renderer
sudo systemctl status protosuit-launcher
sudo systemctl status protosuit-web
sudo systemctl status protosuit-bluetoothbridge
sudo systemctl status protosuit-audiobridge
sudo systemctl status protosuit-controllerbridge
sudo systemctl status protosuit-castbridge
sudo systemctl status protosuit-networkingbridge
sudo systemctl status protosuit-espbridge

# View logs
sudo journalctl -u protosuit-renderer -f

# Restart a service
sudo systemctl restart protosuit-renderer
```

---

## Creating Custom Shaders

Create GLSL shaders in `assets/shaders/`:

```glsl
#version 300 es
precision highp float;

uniform float iTime;
uniform vec2 iResolution;
uniform float speed;        // MQTT-controllable
uniform vec3 color1;        // MQTT-controllable

in vec2 v_fragCoord;
out vec4 fragColor;

void main() {
    vec2 uv = v_fragCoord / iResolution;
    vec3 col = color1 * sin(uv.x * 10.0 + iTime * speed);
    fragColor = vec4(col, 1.0);
}
```

Add to `config.yaml` and control via MQTT. See [docs/mqtt-api.md](docs/mqtt-api.md) for examples.

---

## Testing

```bash
./tests/test_mqtt_inputs.sh    # Tests Doom, Super Haxagon, Ring Ding inputs
```

---

## Development

```bash
cd ~/protosuit-engine
source env/bin/activate
python protosuit_engine.py     # All services in one process (dev only)
```

For production, use systemd services (see [Service Management](#service-management)).

---

## Troubleshooting

### Displays not showing content
```bash
sudo systemctl status xserver
sudo systemctl status protosuit-renderer
DISPLAY=:0 xrandr --query
```

### MQTT commands not working
```bash
sudo systemctl status mosquitto
mosquitto_sub -t "protogen/#" -v    # Monitor all topics
```

### ESP32 not connecting
```bash
sudo journalctl -u protosuit-espbridge -f
ls -la /dev/ttyUSB0                  # Check serial device exists
```

### Teensy upload issues
```bash
lsusb | grep Teensy                  # Only visible in bootloader mode
killall teensy                       # Kill stuck uploader UI
./ProtoTracer/build_and_upload.sh    # Retry
```

For more help, [open an issue on GitHub](https://github.com/lululombard/protosuit-engine/issues).

---

## Future Plans

### Hardware
- SMD power circuitry instead of off-the-shelf buck converter modules
- ESP32 module directly on-board instead of a dev board
- Raspberry Pi Compute Module instead of a full RPi 5
- Custom display driver circuitry instead of separate HDMI-MIPI boards

### Features
- **Shader image/video support**: load images and videos as shader inputs (textures)
- **Firmware restart commands**: restart Teensy and ESP32 via MQTT commands

### Reliability
- **NetworkController**: manage hostapd/dnsmasq via `utils/service_controller` instead of direct process management
- **Systemd-first approach**: use `enable --now` / `disable --now` everywhere, read config from services at boot instead of relying on MQTT retained messages to start processes, tighter D-Bus integration
- **Live web preview performance**: ffmpeg slows the whole system and the preview lags behind after extended use
- **System bridge**: new service to expose CPU/memory/IO/storage usage, temperature, fan speed, undervoltage events, plus reboot and shutdown controls
- **Notifications**: expand `protogen/visor/notifications` usage across all services, rename to `protogen/global/notifications`

### Repo
- Move all Python services/utils into `engine/` (major refactor, affects systemd units, imports, paths)
- Consolidate hardware files: `ProtosuitDevBoard/` → `hardware/pcb/`
- Per-service README.md files with service-specific docs
- Separate `firmware/` umbrella for ESP32 + Teensy

---

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0), matching the [ProtoTracer](https://github.com/coelacant1/ProtoTracer) license.

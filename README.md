# Protosuit Engine

**A Raspberry Pi display system for Protogen fursuit fins with shader animations, media playback, and executables.**

Designed for fursuit makers and Protogen enthusiasts who want dynamic, synchronized displays on their fin panels.

---

## Quick Start

1. Flash **Raspberry Pi OS Lite (64-bit)** on a microSD card with username `proto`
2. Boot the Pi and run:

```bash
sudo apt update
sudo apt install git ansible -y
git clone git@github.com:lululombard/protosuit-engine.git
cd protosuit-engine
ansible/scripts/deploy.sh
```

That's it! The system will auto-configure and start on boot.

---

## Hardware Requirements

### Recommended Setup

- **Raspberry Pi 5** (4GB+ RAM recommended)
- **Two 720x720 HDMI displays** (for fursuit fins)
- **USB Wi-Fi 6 dongle** (RTL8851BU chipset) - for client/internet connectivity
  - The built-in Raspberry Pi Wi-Fi is used for AP mode
  - RTL8851BU drivers work well for client mode but are unstable as access points (kernel bugs)
  - Many RTL8851BU dongles include integrated Bluetooth
  - See [ansible/README.md](ansible/README.md#wi-fi-hardware-configuration) for details
- **USB Bluetooth adapter** (optional, if your Wi-Fi dongle doesn't have Bluetooth, or for separating gamepad and audio devices to avoid bandwidth conflicts)

### Display Configuration

The system is designed for **dual 720x720 displays** mounted on fursuit fins:
- Left display rotated 90° clockwise
- Right display rotated 90° counter-clockwise
- Extended desktop spanning both displays

---

## Features

- **GLSL Shader Animations** - Smooth cross-fade transitions with blur effects and real-time parameter control
- **Media Playback** - Videos (exclusive), audio (stackable), synchronized playback
- **Executables** - Run shell scripts (like Doom) positioned across both displays
- **MQTT Input Control** - Send keyboard inputs to running games via MQTT (ready for ESP32 or custom input devices)
- **Bluetooth Gamepad Support** - Pair Bluetooth controllers and assign one per display for independent control
- **AirPlay & Spotify Connect** - Stream audio from Apple devices or Spotify app via shairport-sync and raspotify
- **Wi-Fi Management** - Dual-mode networking with AP hotspot and client mode, NAT routing, and QR code sharing
- **Web Control Interface** - Browser-based control with live preview and performance monitoring
- **MQTT Integration** - Remote control and automation from external devices

---

## Basic Usage

### Web Interface

Open your browser to `http://<raspberry-pi-ip>`

- Control animations with one click
- View live preview of both displays
- Monitor FPS and resolution
- Launch media and executables
- Adjust shader parameters with sliders

### Virtual Controller

Access the virtual controller at `http://<raspberry-pi-ip>/controller`

Optional URL parameters:
- `?display=left` - Start with left display selected (default)
- `?display=right` - Start with right display selected

Mobile-friendly gamepad interface for testing MQTT inputs:
- **D-Pad**: Arrow keys for movement (Up/Down/Left/Right)
- **Action Buttons**: A and B buttons
- **Display Selector**: Target left or right display
- Matches industrial protogen UI aesthetic
- Works on phones, tablets, and desktop browsers
- Touch-optimized with press/release events
- Responsive: side-by-side in landscape, stacked in portrait

**Physics-Based Sliders:**

The web interface features a spring physics system for parameter sliders, providing smooth, natural interaction:
- **Spring dynamics** - Sliders have momentum and damping for satisfying tactile feedback
- **Real-time updates** - Changes are sent via MQTT instantly as you drag
- **Per-display control** - Adjust left and right displays independently or sync both
- **Range constraints** - Min/max values defined in config.yaml with custom step sizes

### Bluetooth Controller Manager

Access the Bluetooth controller manager at `http://<raspberry-pi-ip>/bluetooth`

Pair and manage Bluetooth devices for gaming and audio:

**Gamepad Features:**
- **Scan for devices** - Discover nearby Bluetooth controllers and speakers
- **Connect controllers** - Pair and connect up to 2 gamepads
- **Assign displays** - Assign one controller to left display, one to right (persists across restarts)
- **Auto-reconnect** - Controllers automatically reconnect when powered on (no need to restart software)
- **Independent control** - Each player controls their own game instance
- **Real-time status** - See connection status and device information
- **Button mapping** - D-pad, A, and B buttons automatically mapped to game controls

**Audio Features:**
- **Bluetooth speakers** - Pair and connect Bluetooth speakers, headphones, or earbuds
- **Smart audio routing** - Automatically switches to Bluetooth speaker when it reconnects (if previously used)
- **Intelligent fallback** - Automatically falls back to built-in audio when Bluetooth disconnects
- **Manual selection** - Choose audio output device from dropdown (excludes HDMI by default)
- **Seamless switching** - Active audio streams automatically move to new device

**System:**
- **Restart Bluetooth** - Fix connection issues with one click (handles org.bluez.Error.NotReady)

**Supported Controllers:**
- Xbox controllers (all generations)
- PlayStation controllers (DualShock 4, DualSense)
- Nintendo Switch Pro Controller
- 8BitDo controllers
- Most generic Bluetooth gamepads

**Button Mapping:**
- **D-Pad**: Up, Down, Left, Right
- **A Button**: A key (confirm/jump)
- **B Button**: B key (back/action)

### Cast Settings

Access the cast settings at `http://<raspberry-pi-ip>/cast`

Enable and configure audio streaming services:

- **AirPlay (shairport-sync)** - Stream audio from Apple devices (iPhone, iPad, Mac)
  - Enable/disable with one click
  - Configure device name (appears in AirPlay menu)
  - Optional password protection
- **Spotify Connect (raspotify)** - Stream music from the Spotify app
  - Enable/disable with one click
  - Configure device name (appears in Spotify devices)
  - Optional username/password for premium features

Both services output audio through PulseAudio, so they respect the current audio device selection (Bluetooth speaker, built-in audio, etc.).

### Networking Settings

Access the networking settings at `http://<raspberry-pi-ip>/networking`

Manage Wi-Fi connectivity with dual-mode operation:

**Client Mode (wlan1 - USB Wi-Fi):**
- **Scan for networks** - Find available Wi-Fi networks
- **Connect to networks** - Join external Wi-Fi for internet access
- **Connection status** - View signal strength, IP address, and gateway
- **Auto-reconnect** - Automatically reconnects to known networks

**Access Point Mode (wlan0 - Built-in Wi-Fi):**
- **Enable/disable AP** - Toggle the "Protosuit" hotspot
- **Configure SSID** - Change the network name
- **Security options** - WPA, WPA2, or Open
- **Password protection** - Set a custom password
- **QR code sharing** - Generate QR code for easy mobile connection
- **Connected clients** - View devices connected to the hotspot

**Routing:**
- **NAT forwarding** - Share internet from client interface to AP clients
- **Automatic setup** - IP forwarding and iptables rules managed automatically

### Service Management

```bash
# Check status
sudo systemctl status protosuit-renderer
sudo systemctl status protosuit-launcher
sudo systemctl status protosuit-web
sudo systemctl status protosuit-bluetoothbridge
sudo systemctl status protosuit-castbridge
sudo systemctl status protosuit-networkingbridge

# View logs
sudo journalctl -u protosuit-renderer -f
sudo journalctl -u protosuit-launcher -f
sudo journalctl -u protosuit-web -f
sudo journalctl -u protosuit-bluetoothbridge -f
sudo journalctl -u protosuit-castbridge -f
sudo journalctl -u protosuit-networkingbridge -f

# Restart services
sudo systemctl restart protosuit-renderer
sudo systemctl restart protosuit-launcher
sudo systemctl restart protosuit-bluetoothbridge
sudo systemctl restart protosuit-castbridge
sudo systemctl restart protosuit-networkingbridge
```

---

## System Architecture

### Components

**Six independent services:**
- `protosuit-renderer` - OpenGL shader renderer (ModernGL + Pygame)
- `protosuit-launcher` - Audio/video/executable launcher (mpv, ffplay, shell scripts)
- `protosuit-web` - Flask web interface with live preview
- `protosuit-bluetoothbridge` - Bluetooth gamepad manager and input forwarder
- `protosuit-castbridge` - AirPlay and Spotify Connect manager (shairport-sync, raspotify)
- `protosuit-networkingbridge` - Wi-Fi client/AP manager with NAT routing (hostapd, dnsmasq)

**Supporting services:**
- `xserver` - X11 server for dual display management
- `mosquitto` - MQTT broker for inter-process communication
- `pulseaudio` - Audio server with Bluetooth A2DP support (auto-started by launcher)

All services communicate via MQTT topics under `protogen/fins/*`

**Audio Setup:**
- The launcher automatically starts PulseAudio on boot with Bluetooth support
- Default audio device is set to non-HDMI (usually built-in audio or USB)
- **Bluetooth audio quality:** When a Bluetooth speaker connects, the system automatically:
  - Detects the current profile (HSP/HFP vs A2DP)
  - Switches to A2DP (Advanced Audio Distribution Profile) for high-quality stereo audio
  - HSP/HFP profiles are for phone calls and have poor audio quality (mono, 8kHz)
  - A2DP profiles provide full stereo audio with good quality codecs
- Audio device switching is seamless with automatic stream migration

**Bluetooth Adapter Management:**
- The system supports multiple Bluetooth adapters to avoid bandwidth conflicts
- Configure in `config.yaml` under `bluetoothbridge.adapters`:
  - `gamepads`: Adapter for game controllers (default: `hci0` - built-in)
  - `audio`: Adapter for speakers/headphones (default: `hci1` - USB dongle)
- **Why separate adapters?** When multiple devices share one adapter, bandwidth is split causing:
  - Audio stuttering and quality degradation
  - Controller input lag
  - Connection instability
- **Setup steps:**
  1. Check available adapters: `bluetoothctl list` or `hciconfig -a`
  2. Enable USB adapter: `sudo rfkill unblock bluetooth && sudo hciconfig hci1 up`
  3. Devices will automatically connect to the correct adapter based on their type
  4. Already-paired devices may need to be removed and re-paired after configuration change
- **How it works:** The service uses `hciconfig` to get adapter MAC addresses, then uses `bluetoothctl select` to target specific adapters for each operation

---

## MQTT API

### Renderer Topics

**Commands (subscribe):**

| Topic | Payload | Description |
|-------|---------|-------------|
| `protogen/fins/renderer/set/shader/file` | `{"display":"both","name":"idle","transition_duration":0.75}` | Load shader animation |
| `protogen/fins/renderer/set/shader/uniform` | `{"display":"both","name":"speed","type":"float","value":2.5}` | Set shader parameter |
| `protogen/fins/renderer/config/reload` | - | Reload config.yaml |

**Status (publish, retained):**

| Topic | Content |
|-------|---------|
| `protogen/fins/renderer/status/performance` | JSON with FPS, resolution, frame times |
| `protogen/fins/renderer/status/shader` | JSON with available shaders, current animation, transition state |
| `protogen/fins/renderer/status/uniform` | JSON with uniform values and metadata (min/max/step) |

**Examples:**

```bash
# Switch animation with transition
mosquitto_pub -t "protogen/fins/renderer/set/shader/file" \
  -m '{"display":"both","name":"aperture","transition_duration":0.75}'

# Adjust speed on both displays
mosquitto_pub -t "protogen/fins/renderer/set/shader/uniform" \
  -m '{"display":"both","name":"speed","type":"float","value":2.5}'

# Set color on left display only
mosquitto_pub -t "protogen/fins/renderer/set/shader/uniform" \
  -m '{"display":"left","name":"color1","type":"vec3","value":[1.0,0.0,0.5]}'

# Get current status
mosquitto_sub -t "protogen/fins/renderer/status/#" -v
```

**Display values:** `"left"`, `"right"`, or `"both"`

**Uniform types:** `"float"`, `"int"`, `"vec2"`, `"vec3"`, `"vec4"`

---

### Launcher Topics

**Commands (subscribe):**

| Topic | Payload | Description |
|-------|---------|-------------|
| `protogen/fins/launcher/start/audio` | `"file.mp3"` or JSON | Play audio (stackable) |
| `protogen/fins/launcher/start/video` | `"file.mp4"` or JSON | Play video (exclusive) |
| `protogen/fins/launcher/start/exec` | `"script.sh"` | Run executable script |
| `protogen/fins/launcher/input/exec` | JSON (see below) | Send keyboard input to running executable |
| `protogen/fins/launcher/stop/audio` | `"file.mp3"` or `"all"` | Stop audio gracefully |
| `protogen/fins/launcher/stop/video` | - | Stop video gracefully |
| `protogen/fins/launcher/stop/exec` | - | Stop executable gracefully |
| `protogen/fins/launcher/kill/audio` | `"file.mp3"` or `"all"` | Force kill audio |
| `protogen/fins/launcher/kill/video` | - | Force kill video |
| `protogen/fins/launcher/kill/exec` | - | Force kill executable |
| `protogen/fins/launcher/audio/device/set` | `{"device":"sink_name"}` | Set audio output device |
| `protogen/fins/launcher/config/reload` | - | Rescan asset directories |

**Status (publish, retained):**

| Topic | Content |
|-------|---------|
| `protogen/fins/launcher/status/audio` | `{"playing":["file.mp3"],"available":[...]}` |
| `protogen/fins/launcher/status/video` | `{"playing":"file.mp4","available":[...]}` |
| `protogen/fins/launcher/status/exec` | `{"running":"script.sh","pid":1234,"available":[...]}` |
| `protogen/fins/launcher/status/audio_devices` | JSON array of available audio output devices |
| `protogen/fins/launcher/status/audio_device/current` | JSON object with current audio device info |
| `protogen/fins/launcher/status/volume` | `{"volume":50,"min":0,"max":100}` |

**Examples:**

```bash
# Play audio (multiple can stack)
mosquitto_pub -t "protogen/fins/launcher/start/audio" -m "song.mp3"

# Play video (replaces current video)
mosquitto_pub -t "protogen/fins/launcher/start/video" -m "animation.mp4"

# Launch executable
mosquitto_pub -t "protogen/fins/launcher/start/exec" -m "doom.sh"

# Send input to running executable (press A button on left display)
mosquitto_pub -t "protogen/fins/launcher/input/exec" \
  -m '{"key": "a", "action": "key", "display": "left"}'

# Hold and release a key (for timing-based games)
mosquitto_pub -t "protogen/fins/launcher/input/exec" \
  -m '{"key": "Left", "action": "keydown", "display": "left"}'
# ... wait ...
mosquitto_pub -t "protogen/fins/launcher/input/exec" \
  -m '{"key": "Left", "action": "keyup", "display": "left"}'

# Send input to specific window in multi-window games (like Doom)
mosquitto_pub -t "protogen/fins/launcher/input/exec" \
  -m '{"key": "w", "action": "keydown", "display": "right"}'

# Stop gracefully
mosquitto_pub -t "protogen/fins/launcher/stop/video" -m ""

# Force kill all audio
mosquitto_pub -t "protogen/fins/launcher/kill/audio" -m "all"

# Get current status
mosquitto_sub -t "protogen/fins/launcher/status/#" -v
```

**Input message format:**

```json
{
  "key": "a",          // xdotool key name (a, b, Left, Right, Up, Down, etc.)
  "action": "key",     // "key" (press+release), "keydown" (press), "keyup" (release)
  "display": "left"    // "left", "right", or "both"
}
```

**Input routing behavior:**
- **Single-window games** (Ring Ding, Super Haxagon): Inputs sent to focused window regardless of display parameter
- **Multi-window games** (Doom): Inputs targeted to specific window based on display parameter
- Automatic window discovery via process PID tree (handles script wrappers)

**Input device options:**
- Bluetooth gamepads via bluetoothbridge service
- ESP32 microcontrollers sending MQTT messages
- PSP controllers via psp-controller homebrew app
- Custom input devices publishing to MQTT

---

### Bluetoothbridge Topics

**Commands (subscribe):**

| Topic | Payload | Description |
|-------|---------|-------------|
| `protogen/fins/bluetoothbridge/scan/start` | - | Start Bluetooth scanning |
| `protogen/fins/bluetoothbridge/scan/stop` | - | Stop Bluetooth scanning |
| `protogen/fins/bluetoothbridge/connect` | `{"mac":"AA:BB:CC:DD:EE:FF"}` | Connect to device |
| `protogen/fins/bluetoothbridge/disconnect` | `{"mac":"AA:BB:CC:DD:EE:FF"}` | Disconnect device |
| `protogen/fins/bluetoothbridge/unpair` | `{"mac":"AA:BB:CC:DD:EE:FF"}` | Unpair/remove device |
| `protogen/fins/bluetoothbridge/assign` | `{"mac":"AA:BB:CC:DD:EE:FF","display":"left"}` or `{"mac":null,"display":"left"}` | Assign controller to display or remove assignment (persists via retained message) |
| `protogen/fins/bluetoothbridge/bluetooth/restart` | - | Restart Bluetooth service (fixes org.bluez.Error.NotReady) |

**Status (publish, retained):**

| Topic | Content |
|-------|---------|
| `protogen/fins/bluetoothbridge/status/scanning` | `true` or `false` - Scanning state |
| `protogen/fins/bluetoothbridge/status/devices` | JSON array of discovered gamepad devices |
| `protogen/fins/bluetoothbridge/status/audio_devices` | JSON array of discovered Bluetooth audio devices |
| `protogen/fins/bluetoothbridge/status/assignments` | JSON object with left/right gamepad assignments |

**Examples:**

```bash
# Start scanning for Bluetooth devices
mosquitto_pub -t "protogen/fins/bluetoothbridge/scan/start" -m ""

# Stop scanning
mosquitto_pub -t "protogen/fins/bluetoothbridge/scan/stop" -m ""

# Connect to a controller
mosquitto_pub -t "protogen/fins/bluetoothbridge/connect" \
  -m '{"mac":"AA:BB:CC:DD:EE:FF"}'

# Assign controller to left display
mosquitto_pub -t "protogen/fins/bluetoothbridge/assign" \
  -m '{"mac":"AA:BB:CC:DD:EE:FF","display":"left"}'

# Remove assignment from left display
mosquitto_pub -t "protogen/fins/bluetoothbridge/assign" \
  -m '{"mac":null,"display":"left"}'

# Restart Bluetooth service (if you get org.bluez.Error.NotReady)
mosquitto_pub -t "protogen/fins/bluetoothbridge/bluetooth/restart" -m ""

# Unpair a device
mosquitto_pub -t "protogen/fins/bluetoothbridge/unpair" \
  -m '{"mac":"AA:BB:CC:DD:EE:FF"}'

# Connect to a Bluetooth speaker
mosquitto_pub -t "protogen/fins/bluetoothbridge/connect" \
  -m '{"mac":"XX:YY:ZZ:AA:BB:CC"}'

# Select audio output device
mosquitto_pub -t "protogen/fins/launcher/audio/device/set" \
  -m '{"device":"bluez_sink.XX_YY_ZZ_AA_BB_CC"}'

# Monitor status
mosquitto_sub -t "protogen/fins/bluetoothbridge/status/#" -v
mosquitto_sub -t "protogen/fins/launcher/status/audio_device/#" -v
```

**Gamepad device status format:**

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

**Gamepad assignment status format:**

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

**Audio device status format:**

```json
[
  {
    "mac": "XX:YY:ZZ:AA:BB:CC",
    "name": "JBL Speaker",
    "paired": true,
    "connected": true,
    "type": "audio"
  }
]
```

**Available audio devices format (from launcher):**

```json
[
  {
    "name": "bluez_sink.XX_YY_ZZ_AA_BB_CC",
    "description": "JBL Speaker",
    "type": "bluetooth"
  },
  {
    "name": "alsa_output.usb-device",
    "description": "USB Audio",
    "type": "usb"
  }
]
```

**Current audio device format:**

```json
{
  "device": "bluez_sink.XX_YY_ZZ_AA_BB_CC",
  "description": "JBL Speaker",
  "type": "bluetooth"
}
```

**Audio Device Behavior:**
- When a Bluetooth speaker connects, it automatically becomes available in the device list
- If the Bluetooth speaker was the last selected device, audio automatically switches to it when it reconnects
- If the Bluetooth speaker disconnects, audio automatically falls back to a non-HDMI device (usually built-in audio)
- HDMI audio outputs are excluded from the UI and fallback logic by default
- Manual device selection via the web interface stores the preference for auto-reconnect

---

### Castbridge Topics

The castbridge service manages AirPlay (shairport-sync) and Spotify Connect (raspotify) audio streaming.

**Commands (subscribe):**

| Topic | Payload | Description |
|-------|---------|-------------|
| `protogen/fins/castbridge/airplay/enable` | `{"enable":true}` | Enable or disable AirPlay |
| `protogen/fins/castbridge/airplay/config` | `{"device_name":"Protosuit","password":""}` | Configure AirPlay settings |
| `protogen/fins/castbridge/spotify/enable` | `{"enable":true}` | Enable or disable Spotify Connect |
| `protogen/fins/castbridge/spotify/config` | `{"device_name":"Protosuit","username":"","password":""}` | Configure Spotify settings |

**Status (publish, retained):**

| Topic | Content |
|-------|---------|
| `protogen/fins/castbridge/status/airplay` | `{"enabled":false,"device_name":"Protosuit","password":"","running":false}` |
| `protogen/fins/castbridge/status/spotify` | `{"enabled":false,"device_name":"Protosuit","username":"","password":"","running":false}` |

**Examples:**

```bash
# Enable AirPlay
mosquitto_pub -t "protogen/fins/castbridge/airplay/enable" \
  -m '{"enable":true}'

# Configure AirPlay with custom name
mosquitto_pub -t "protogen/fins/castbridge/airplay/config" \
  -m '{"device_name":"My Protosuit","password":""}'

# Enable Spotify Connect
mosquitto_pub -t "protogen/fins/castbridge/spotify/enable" \
  -m '{"enable":true}'

# Configure Spotify with credentials
mosquitto_pub -t "protogen/fins/castbridge/spotify/config" \
  -m '{"device_name":"Protosuit","username":"myuser","password":"mypass"}'

# Monitor castbridge status
mosquitto_sub -t "protogen/fins/castbridge/status/#" -v
```

**Notes:**
- Services are disabled and masked by default (managed by castbridge, not systemd)
- Enabling a service unmasks it and starts it with the configured settings
- Configuration changes restart the service automatically if it's running
- Audio is routed through PulseAudio, respecting current audio device selection

---

### Networkingbridge Topics

The networkingbridge service manages Wi-Fi client connections, access point hosting, and NAT routing.

**Commands (subscribe):**

| Topic | Payload | Description |
|-------|---------|-------------|
| `protogen/fins/networkingbridge/scan/start` | - | Scan for available Wi-Fi networks |
| `protogen/fins/networkingbridge/client/connect` | `{"ssid":"NetworkName","password":"pass"}` | Connect to a Wi-Fi network |
| `protogen/fins/networkingbridge/client/disconnect` | - | Disconnect from current network |
| `protogen/fins/networkingbridge/ap/enable` | `{"enable":true}` | Enable or disable the access point |
| `protogen/fins/networkingbridge/ap/config` | `{"ssid":"Protosuit","security":"wpa","password":"BeepBoop","ip_cidr":"192.168.50.1/24"}` | Configure access point settings |
| `protogen/fins/networkingbridge/routing/enable` | `{"enable":true}` | Enable or disable NAT routing |
| `protogen/fins/networkingbridge/qrcode/generate` | - | Generate QR code for AP connection |

**Status (publish, retained):**

| Topic | Content |
|-------|---------|
| `protogen/fins/networkingbridge/status/interfaces` | Interface detection status |
| `protogen/fins/networkingbridge/status/client` | `{"connected":true,"ssid":"...","ip_address":"...","signal_percent":80}` |
| `protogen/fins/networkingbridge/status/ap` | `{"enabled":true,"ssid":"Protosuit","clients":[...]}` |
| `protogen/fins/networkingbridge/status/scan` | Array of discovered networks |
| `protogen/fins/networkingbridge/status/scanning` | `true` or `false` |
| `protogen/fins/networkingbridge/status/qrcode` | `{"qrcode":"data:image/png;base64,..."}` |

**Examples:**

```bash
# Scan for Wi-Fi networks
mosquitto_pub -t "protogen/fins/networkingbridge/scan/start" -m ""

# Connect to a network
mosquitto_pub -t "protogen/fins/networkingbridge/client/connect" \
  -m '{"ssid":"MyWiFi","password":"mypassword"}'

# Enable access point
mosquitto_pub -t "protogen/fins/networkingbridge/ap/enable" \
  -m '{"enable":true}'

# Configure AP with custom settings
mosquitto_pub -t "protogen/fins/networkingbridge/ap/config" \
  -m '{"ssid":"MyProtosuit","security":"wpa2","password":"SecurePass123"}'

# Generate QR code for AP
mosquitto_pub -t "protogen/fins/networkingbridge/qrcode/generate" -m ""

# Enable NAT routing
mosquitto_pub -t "protogen/fins/networkingbridge/routing/enable" \
  -m '{"enable":true}'

# Monitor networking status
mosquitto_sub -t "protogen/fins/networkingbridge/status/#" -v
```

**Security options:** `"wpa"` (WPA1 for legacy devices like PSP), `"wpa2"`, or `"open"`

**Notes:**
- Client mode uses the USB Wi-Fi dongle (wlan1) for internet connectivity
- AP mode uses the built-in Raspberry Pi Wi-Fi (wlan0) for stability
- NAT routing allows AP clients to access the internet through the client connection
- QR codes use the standard Wi-Fi QR format, scannable by most phone cameras

---

## Configuration

Edit `config.yaml` to customize animations:

```yaml
default_animation: "aperture"  # Animation to load on boot

animations:
  aperture:
    name: "Aperture"
    emoji: "🔆"
    left_shader: "aperture.glsl"
    right_shader: "aperture.glsl"
    render_scale: 1.0  # 1.0 = full res, 0.5 = half res for performance
    uniforms:
      rotationSpeed:
        left: {type: float, value: 0.5, min: -2.0, max: 2.0, step: 0.1}
        right: {type: float, value: -0.5, min: -2.0, max: 2.0, step: 0.1}
      focusSharpness: {type: float, value: 360.0, min: 10.0, max: 1000.0, step: 10.0}
      apertureColor: {type: vec3, value: [1.0, 0.6, 0.0], min: 0.0, max: 1.0, step: 0.01}

transitions:
  enabled: true
  duration: 0.75  # Transition duration in seconds
  easing: "smoothstep"
  blur:
    enabled: true
    strength: 8.0
```

**Asset Directories** (automatically scanned):
- `assets/shaders/` - GLSL shader files (`.glsl`)
- `assets/audio/` - Audio files (`.mp3`, `.wav`, `.flac`, etc.)
- `assets/video/` - Video files (`.mp4`, `.mkv`, `.webm`, etc.)
- `assets/executables/` - Shell scripts (`.sh`)

---

## Creating Custom Shaders

Create GLSL shaders in `assets/shaders/`:

```glsl
#version 300 es
precision highp float;

// Built-in uniforms (automatically provided)
uniform float iTime;       // Elapsed time in seconds
uniform vec2 iResolution;  // Display resolution (720x720)
uniform int frame;         // Frame counter

// Custom uniforms (MQTT-controllable)
uniform float speed;
uniform vec3 color1;

in vec2 v_fragCoord;
out vec4 fragColor;

void main() {
    vec2 uv = v_fragCoord / iResolution;
    float time = iTime * speed;

    vec3 col = color1 * sin(uv.x * 10.0 + time);
    fragColor = vec4(col, 1.0);
}
```

Add to `config.yaml`:

```yaml
animations:
  my_shader:
    name: "My Shader"
    emoji: "🎨"
    left_shader: "my_shader.glsl"
    right_shader: "my_shader.glsl"
    uniforms:
      speed: {type: float, value: 1.0, min: 0.0, max: 5.0, step: 0.1}
      color1: {type: vec3, value: [1.0, 0.5, 0.0]}
```

Control via MQTT (see [MQTT API](#mqtt-api) section above for examples).

---

## Testing

### MQTT Input Test Script

A comprehensive test script is available to verify MQTT input handling across all games:

```bash
./tests/test_mqtt_inputs.sh
```

This script automatically tests:
- **Doom**: Multi-window targeting with independent left/right controls
- **Super Haxagon**: Single-window focused mode with timed inputs
- **Ring Ding**: Single-window focused mode with simple key presses

The script restarts the launcher, launches each game, sends MQTT inputs, and verifies behavior. Watch the displays to confirm inputs are working correctly.

---

## Development

### Development Launcher (Single Process)

For local development:

```bash
cd ~/protosuit-engine
source env/bin/activate
python protosuit_engine.py
```

⚠️ **For production, use systemd services** (single point of failure issue)

### Manual Service Start

```bash
cd ~/protosuit-engine
source env/bin/activate

# Terminal 1
python renderer/renderer.py

# Terminal 2
python launcher/launcher.py

# Terminal 3
python web/server.py
```

---

## Troubleshooting

### Displays not showing content

```bash
sudo systemctl status xserver
sudo systemctl status protosuit-renderer
sudo journalctl -u protosuit-renderer -f
DISPLAY=:0 xrandr --query  # Test displays
```

### MQTT commands not working

```bash
sudo systemctl status mosquitto
mosquitto_sub -t "protogen/fins/#" -v  # Monitor all topics
sudo systemctl status protosuit-renderer
sudo systemctl status protosuit-launcher
```

### Service won't start

```bash
sudo journalctl -u protosuit-renderer -f
sudo journalctl -u protosuit-launcher -f
sudo journalctl -u protosuit-web -f
systemctl get-default  # Should be graphical.target
```

### Shader animations frozen

```bash
sudo journalctl -u protosuit-renderer -f
sudo systemctl restart protosuit-renderer
mosquitto_sub -t "protogen/fins/renderer/status/#" -v
```

### Web interface not loading

```bash
sudo systemctl status protosuit-web
sudo netstat -tulpn | grep 5000
sudo journalctl -u protosuit-web -f
```

For more help, [open an issue on GitHub](https://github.com/lululombard/protosuit-engine/issues).

---

## License

This is a personal fursuit project. Feel free to adapt for your own use.

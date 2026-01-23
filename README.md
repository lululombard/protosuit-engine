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

## Features

- **GLSL Shader Animations** - Smooth cross-fade transitions with blur effects and real-time parameter control
- **Media Playback** - Videos (exclusive), audio (stackable), synchronized playback
- **Executables** - Run shell scripts (like Doom) positioned across both displays
- **MQTT Input Control** - Send keyboard inputs to running games via MQTT (ready for ESP32 or custom input devices)
- **Bluetooth Gamepad Support** - Pair Bluetooth controllers and assign one per display for independent control
- **Web Control Interface** - Browser-based control with live preview and performance monitoring
- **MQTT Integration** - Remote control and automation from external devices

---

## Basic Usage

### Web Interface

Open your browser to `http://<raspberry-pi-ip>:5000`

- Control animations with one click
- View live preview of both displays
- Monitor FPS and resolution
- Launch media and executables
- Adjust shader parameters with sliders

### Virtual Controller

Access the virtual controller at `http://<raspberry-pi-ip>:5000/controller`

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

Access the Bluetooth controller manager at `http://<raspberry-pi-ip>:5000/bt-controller`

Pair and manage Bluetooth gamepads for physical game control:
- **Scan for devices** - Discover nearby Bluetooth controllers
- **Connect controllers** - Pair and connect up to 2 gamepads
- **Assign displays** - Assign one controller to left display, one to right (persists across restarts)
- **Independent control** - Each player controls their own game instance
- **Real-time status** - See connection status and device information
- **Button mapping** - D-pad, A, and B buttons automatically mapped to game controls

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

### Service Management

```bash
# Check status
sudo systemctl status protosuit-renderer
sudo systemctl status protosuit-launcher
sudo systemctl status protosuit-web
sudo systemctl status protosuit-controllerbridge

# View logs
sudo journalctl -u protosuit-renderer -f
sudo journalctl -u protosuit-launcher -f
sudo journalctl -u protosuit-web -f
sudo journalctl -u protosuit-controllerbridge -f

# Restart services
sudo systemctl restart protosuit-renderer
sudo systemctl restart protosuit-launcher
sudo systemctl restart protosuit-controllerbridge
```

---

## System Architecture

### Components

**Four independent services:**
- `protosuit-renderer` - OpenGL shader renderer (ModernGL + Pygame)
- `protosuit-launcher` - Audio/video/executable launcher (mpv, ffplay, shell scripts)
- `protosuit-web` - Flask web interface with live preview
- `protosuit-controllerbridge` - Bluetooth gamepad manager and input forwarder

**Supporting services:**
- `xserver` - X11 server for dual display management
- `mosquitto` - MQTT broker for inter-process communication

All services communicate via MQTT topics under `protogen/fins/*`

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
| `protogen/fins/launcher/config/reload` | - | Rescan asset directories |

**Status (publish, retained):**

| Topic | Content |
|-------|---------|
| `protogen/fins/launcher/status/audio` | `{"playing":["file.mp3"],"available":[...]}` |
| `protogen/fins/launcher/status/video` | `{"playing":"file.mp4","available":[...]}` |
| `protogen/fins/launcher/status/exec` | `{"running":"script.sh","pid":1234,"available":[...]}` |

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
- Bluetooth gamepads via controllerbridge service
- ESP32 microcontrollers sending MQTT messages
- PSP controllers via psp-controller homebrew app
- Custom input devices publishing to MQTT

---

### Controllerbridge Topics

**Commands (subscribe):**

| Topic | Payload | Description |
|-------|---------|-------------|
| `protogen/fins/controllerbridge/scan/start` | - | Start Bluetooth scanning |
| `protogen/fins/controllerbridge/scan/stop` | - | Stop Bluetooth scanning |
| `protogen/fins/controllerbridge/connect` | `{"mac":"AA:BB:CC:DD:EE:FF"}` | Connect to device |
| `protogen/fins/controllerbridge/disconnect` | `{"mac":"AA:BB:CC:DD:EE:FF"}` | Disconnect device |
| `protogen/fins/controllerbridge/unpair` | `{"mac":"AA:BB:CC:DD:EE:FF"}` | Unpair/remove device |
| `protogen/fins/controllerbridge/assign` | `{"mac":"AA:BB:CC:DD:EE:FF","display":"left"}` or `{"mac":null,"display":"left"}` | Assign controller to display or remove assignment (persists via retained message) |

**Status (publish, retained):**

| Topic | Content |
|-------|---------|
| `protogen/fins/controllerbridge/status/scanning` | `true` or `false` - Scanning state |
| `protogen/fins/controllerbridge/status/devices` | JSON array of discovered devices |
| `protogen/fins/controllerbridge/status/assignments` | JSON object with left/right assignments |

**Examples:**

```bash
# Start scanning for Bluetooth devices
mosquitto_pub -t "protogen/fins/controllerbridge/scan/start" -m ""

# Stop scanning
mosquitto_pub -t "protogen/fins/controllerbridge/scan/stop" -m ""

# Connect to a controller
mosquitto_pub -t "protogen/fins/controllerbridge/connect" \
  -m '{"mac":"AA:BB:CC:DD:EE:FF"}'

# Assign controller to left display
mosquitto_pub -t "protogen/fins/controllerbridge/assign" \
  -m '{"mac":"AA:BB:CC:DD:EE:FF","display":"left"}'

# Remove assignment from left display
mosquitto_pub -t "protogen/fins/controllerbridge/assign" \
  -m '{"mac":null,"display":"left"}'

# Unpair a device
mosquitto_pub -t "protogen/fins/controllerbridge/unpair" \
  -m '{"mac":"AA:BB:CC:DD:EE:FF"}'

# Monitor status
mosquitto_sub -t "protogen/fins/controllerbridge/status/#" -v
```

**Device status format:**

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

**Assignment status format:**

```json
{
  "left": {
    "mac": "AA:BB:CC:DD:EE:FF",
    "name": "Xbox Wireless Controller"
  },
  "right": null
}
```

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

## Hardware

- **Raspberry Pi 5** (or compatible model)
- **Two 720x720 displays** via HDMI1 and HDMI2 (4-inch round LCDs recommended)
- **microSD card** - 16GB or more

---

## License

This is a personal fursuit project. Feel free to adapt for your own use.

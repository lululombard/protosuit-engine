# Protosuit Engine

**A Raspberry Pi display system for Protogen fursuit fins with shader animations, media playback, and games.**

Designed for fursuit makers and Protogen enthusiasts who want dynamic, synchronized displays on their fin panels.

### Key Features
- **GLSL Shader Animations** - Smooth cross-fade transitions with blur effects and real-time parameter control
- **Media Playback** - Videos (exclusive), audio (stackable), and synchronized playback
- **Games** - Doom 1v1 networked gameplay across both displays
- **Web Control Interface** - Browser-based control with live preview and performance monitoring
- **MQTT Integration** - Remote control and automation from external devices

---

## Hardware Requirements

- **Raspberry Pi 5** (or compatible model)
- **Two 720x720 displays** - Connected via HDMI1 and HDMI2 (4-inch round LCDs recommended)
- **microSD card** - 16GB or more

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

That's it! The system will:
- Install all required packages
- Configure dual display setup
- Set up Python environment
- Create systemd services
- Auto-start on boot

---

## Basic Usage

### Web Interface (Recommended)

Open your browser to `http://<raspberry-pi-ip>:5000`

- Control animations with one click
- View live preview of both displays
- Monitor FPS and resolution
- Launch games and media
- Adjust shader parameters with sliders

### MQTT Commands

For automation and external control:

```bash
# Switch shader animation
mosquitto_pub -t "protogen/fins/sync" -m "idle"

# Play media file
mosquitto_pub -t "protogen/fins/media" -m "video.mp4"

# Stop media/game
mosquitto_pub -t "protogen/fins/media" -m "stop"

# Launch game
mosquitto_pub -t "protogen/fins/game" -m "doom"

# Control shader parameters
mosquitto_pub -t "protogen/fins/uniform" -m "speed:float:2.5"
```

### Service Management

```bash
# Check status
sudo systemctl status protosuit-system

# View logs
sudo journalctl -u protosuit-renderer -f
sudo journalctl -u protosuit-engine -f

# Restart all services
sudo systemctl restart protosuit-system
```

---

## Features

### Shader Animations

- **Smooth Transitions** - Cross-fade between shaders with configurable duration and easing
- **Blur Effects** - Dynamic blur during transitions for smooth visual flow
- **Resolution Scaling** - Render complex shaders at lower resolution (e.g., 0.25x for 16x speedup)
- **Real-Time Control** - Adjust shader parameters via MQTT (speed, colors, intensity, etc.)

Configure in `config.yaml`:

```yaml
animations:
  idle:
    name: "Idle"
    emoji: "✨"
    left_shader: "stars_left_out.glsl"
    right_shader: "stars_right_in.glsl"
    rate: 60
    render_scale: 1.0  # Full resolution

  outer_wilds:
    name: "Outer Wilds"
    emoji: "🌌"
    left_shader: "outer_wilds.glsl"
    right_shader: "outer_wilds.glsl"
    rate: 30
    render_scale: 0.25  # 1/4 resolution for performance

transitions:
  enabled: true
  duration: 0.75
  easing: "smoothstep"
  blur:
    enabled: true
    strength: 8.0
```

### Media Playback

- **Videos** - Play `.mp4`, `.mkv`, `.webm`, etc. (only one at a time)
- **Audio** - Play `.mp3`, `.wav`, `.flac`, etc. (multiple can stack)
- **Dual Display** - Videos automatically span both 720x720 displays

```bash
# Play video (kills any existing video)
mosquitto_pub -t "protogen/fins/media" -m "video.mp4"

# Play audio (stacks with video/other audio)
mosquitto_pub -t "protogen/fins/media" -m "audio.mp3"
```

### Games

- **Doom 1v1** - Networked Doom instances across left/right displays
- **Auto-Return** - Returns to shader animation when game exits

```bash
mosquitto_pub -t "protogen/fins/game" -m "doom"
mosquitto_pub -t "protogen/fins/game" -m "stop"
```

### Web Interface

Access at `http://<raspberry-pi-ip>:5000`:

- Animation control buttons (auto-generated from `config.yaml`)
- Live 60fps MJPEG preview of both displays
- Real-time FPS and resolution monitoring
- Media upload and playback
- Game launcher
- Shader parameter sliders
- MQTT message log

---

## Architecture & Technical Details

### System Components

```
┌─────────────────┐     MQTT      ┌──────────────────┐
│  protosuit-     │ ◄──────────► │  protosuit-      │
│  engine         │               │  renderer        │
│  (Controller)   │               │  (OpenGL)        │
└────────┬────────┘               └────────┬─────────┘
         │                                 │
         │ MQTT                            │ Display
         │                                 │
         ▼                                 ▼
┌─────────────────┐               ┌──────────────────┐
│  protosuit-web  │               │  X11 / HDMI      │
│  (Browser UI)   │               │  720x720 x2      │
└─────────────────┘               └──────────────────┘
```

**Core Services:**
- `protosuit-engine` - Main controller (MQTT command handler, process management)
- `protosuit-renderer` - Unified OpenGL renderer (shader animations, transitions)
- `protosuit-web` - Flask web interface (browser control, live preview)
- `xserver` - X11 server for dual display management
- `mosquitto` - MQTT broker

**Media Players:**
- `mpv` - Video playback (exclusive, single instance)
- `ffplay` - Audio playback (stackable, multiple instances)

### Display Management

- Dual 720x720 displays configured as extended desktop in X11
- Unified OpenGL renderer handles both displays in single process
- MQTT-based communication between engine and renderer
- Smooth shader transitions with blur effects
- Dynamic resolution scaling for performance
- Window positioning via `xdotool` for external programs

### MQTT Topics

**Engine Commands** (subscribed by `protosuit-engine`):
- `protogen/fins/sync` - Switch shader animation (payload: animation name)
- `protogen/fins/media` - Play media file (payload: filename or "stop")
- `protogen/fins/media/blank` - Play media with blank background
- `protogen/fins/game` - Launch game (payload: game name or "stop")
- `protogen/fins/uniform` - Set shader parameter (format: `name:type:value` or `display:name:type:value`)
- `protogen/fins/uniform/query` - Request current uniform state

**Renderer Commands** (subscribed by `protosuit-renderer`):
- `protogen/renderer/shader` - Load shader (format: `display:duration:scale:source`)
- `protogen/renderer/uniform` - Set uniform (format: `display:name:type:value`)
- `protogen/renderer/command` - Control commands (`quit`, `reload_config`)

**Status Topics** (published by `protosuit-engine` and `protosuit-renderer`):
- `protogen/fins/current_animation` - Current animation name (retained)
- `protogen/fins/uniform/state` - All uniform values as JSON (retained)
- `protogen/fins/uniform/changed` - Uniform change notification
- `protogen/renderer/fps` - Renderer FPS and resolution data
- `protogen/renderer/status` - Renderer status and health

---

## Advanced

### Manual Installation

For manual setup without Ansible, see [ansible/README.md](ansible/README.md) for detailed instructions.

### Development Setup

```bash
cd ~/protosuit-engine
source env/bin/activate
python protosuit_engine.py  # Run engine
python renderer/renderer.py  # Run renderer (separate terminal)
python web/server.py         # Run web interface (separate terminal)
```

### Creating Custom Shaders

Create GLSL shaders in `shaders/` directory:

```glsl
#version 300 es
precision highp float;

// Built-in uniforms
uniform float iTime;       // Elapsed time in seconds
uniform vec2 iResolution;  // Display resolution
uniform int frame;         // Frame counter

// Custom uniforms (MQTT-controllable)
uniform float speed;
uniform vec3 color1;
uniform float intensity;

in vec2 v_fragCoord;
out vec4 fragColor;

void main() {
    vec2 uv = v_fragCoord / iResolution;
    float time = iTime * speed;
    vec3 col = color1 * intensity;

    // Your shader code here

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
    rate: 60
    uniforms:
      speed: 1.0
      color1: [1.0, 0.5, 0.0]
      intensity: 1.0
```

Control uniforms via MQTT:

```bash
# Both displays
mosquitto_pub -t "protogen/fins/uniform" -m "speed:float:2.5"

# Left display only (display 0)
mosquitto_pub -t "protogen/fins/uniform" -m "0:color1:vec3:1.0,0.0,0.5"

# Right display only (display 1)
mosquitto_pub -t "protogen/fins/uniform" -m "1:intensity:float:0.8"
```

### MQTT Payload Formats

**Uniform Types:**
- `float` - Single number: `"speed:float:2.5"`
- `int` - Integer: `"count:int:10"`
- `vec2` - Two floats: `"position:vec2:0.5,0.3"`
- `vec3` - Three floats (RGB): `"color:vec3:1.0,0.5,0.0"`
- `vec4` - Four floats (RGBA): `"tint:vec4:1.0,0.5,0.0,0.8"`

**Display Targeting:**
- No prefix - Both displays
- `0:` prefix - Left display only
- `1:` prefix - Right display only

---

## Troubleshooting

### Displays not showing content
- Check X server: `sudo systemctl status xserver`
- Check renderer: `sudo systemctl status protosuit-renderer`
- Test displays: `DISPLAY=:0 xrandr --query`

### MQTT commands not working
- Check broker: `sudo systemctl status mosquitto`
- Test subscription: `mosquitto_sub -t "protogen/fins/#" -v`
- Check engine: `sudo systemctl status protosuit-engine`

### Service won't start
- Check logs: `sudo journalctl -u protosuit-system -f`
- Verify boot target: `systemctl get-default` (should be `graphical.target`)
- Check file permissions in project directory

### Shader animations frozen
- Check renderer logs: `sudo journalctl -u protosuit-renderer -f`
- Verify MQTT communication: `mosquitto_sub -t "protogen/renderer/#" -v`
- Restart renderer: `sudo systemctl restart protosuit-renderer`

### Web interface not loading
- Check service: `sudo systemctl status protosuit-web`
- Verify port 5000 is not in use: `sudo netstat -tulpn | grep 5000`
- Check firewall settings

For more help, [open an issue on GitHub](https://github.com/lululombard/protosuit-engine/issues).

---

## License

This is a personal fursuit project. Feel free to adapt for your own use.

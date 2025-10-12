# Protogen Fursuit Fin Display System

## Project Summary

A Raspberry Pi-based display management system for Protogen fursuit fin displays (side "ear" panels), featuring synchronized animations, games, and MQTT-based control with ESP32 facial expression integration.

## Hardware Setup

- **Device**: Raspberry Pi 5
- **Displays**: Two 4-inch round 720x720 LCD displays connected via HDMI1 and HDMI2
- **Purpose**: Fin displays for a Protogen fursuit (the side "ear" panels, not the face visor)
- **Additional Hardware**: ESP32 running LED matrix animations for facial expressions
- **Controllers**: Bluetooth controllers (only active during games)

## Project Goals

- Display synchronized animations/shaders on both fin displays
- Play videos, images, and GIFs on both fins
- Run games (like Doom 1v1) as a novelty feature
- Sync fin animations with ESP32 facial expressions
- Control everything via MQTT commands (no manual controller input for switching modes)

## Software Architecture

### Core Components

- **Python control script**: Main manager that handles all display switching and process management
- **MQTT**: All control commands come via MQTT topics
- **mpv**: For videos, shaders, and animations
- **feh**: For static images
- **chocolate-doom**: For running Doom in networked 1v1 mode
- **mosquitto**: MQTT broker

### Display Management

- Both fin displays always show the same content (synchronized)
- mpv processes use `DISPLAY` environment variable for display targeting
- X11 apps (Doom, feh) use `DISPLAY=:0.0` and `DISPLAY=:0.1`
- Content types: shaders (GLSL), videos, images, GIFs, games

## MQTT Command Structure

```
protogen/fins/shader → "shader_name.glsl"
protogen/fins/video → "path/to/video.mp4"
protogen/fins/image → "path/to/image.png"
protogen/fins/sync → "happy" | "angry" | "surprised" (syncs with face expressions)
protogen/fins/game → "doom" | "pong" | etc
protogen/fins/mode → "idle" | "reactive" | etc
protogen/fins/status → query current mode
```

## ESP32 Integration

- ESP32 controls LED matrix face expressions
- ESP32 publishes face expression changes via MQTT
- Fin display manager subscribes and reacts with matching animations
- Two-way communication: fins can notify face when entering game mode

## Key Implementation Details

### Process Management

- All display content runs as separate processes
- When switching modes, old processes are cleanly terminated
- Game processes are monitored; when they exit, return to idle animation

### Controller Handling

- Bluetooth controllers are completely ignored except during games
- When launching Doom, controllers automatically bind to game instances
- Left fin = Player 1, Right fin = Player 2 (networked Doom instances)
- No controller input routing needed - games grab controllers automatically

### Display Configuration

- Each display: 720x720 (1:1 aspect ratio, physically round)
- X11 configured with displays side-by-side (extended desktop)
- Content should ideally be masked to circular viewport for round displays

## Installation

### Required Packages

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y mosquitto mosquitto-clients python3 python3-pip \
  mpv feh chocolate-doom retroarch bluetooth bluez python3-evdev \
  x11-xserver-utils xorg git
```

### Python Environment Setup

```bash
mkdir ~/wip
cd ~/wip
python3 -m venv env
source env/bin/activate
pip install paho-mqtt
```

## Main Python Script Structure

```python
class FinDisplayManager:
    def __init__(self):
        self.displays = [':0.0', ':0.1']  # X11 displays
        self.current_processes = []
        self.current_mode = None

    def cleanup_processes(self):
        # Kill all running display processes

    def show_shader(self, shader_name):
        # Launch mpv with GLSL shader on both displays

    def show_video(self, video_path):
        # Play video synchronized on both displays

    def show_image(self, image_path):
        # Display static image on both displays

    def launch_doom(self):
        # Launch networked Doom: server on display 0, client on display 1
        # Controllers automatically bind to respective instances

    def sync_with_expression(self, expression):
        # Map face expressions to fin shaders

    def handle_mqtt(self, client, userdata, msg):
        # Route MQTT commands to appropriate methods

    def start(self):
        # Connect to MQTT, subscribe to topics, start main loop
```

## Typical Workflow

1. System boots → fins start with idle shader animation
2. ESP32 face changes expression to "happy" → publishes MQTT → fins switch to sparkles shader
3. User wants to play Doom → publishes `protogen/fins/game = "doom"` via MQTT
4. Fins launch Doom 1v1, controllers become active, face gets notified
5. Players finish → Doom exits → fins return to idle animation automatically

## Design Principles

- **Stateless switching**: Can jump between any content type at any time
- **Clean process management**: Old content is always killed before starting new
- **MQTT-first**: All commands via MQTT, no local input handling (except in games)
- **Synchronized displays**: Both fins always show identical content
- **ESP32 integration**: Bidirectional communication for coordinated effects

## Running the System

```bash
cd ~/wip
source env/bin/activate
python test.py
```

The script will:
- Connect to the local MQTT broker (localhost:1883)
- Subscribe to `protogen/fins/#` topics
- Start displaying the idle shader animation
- Listen for MQTT commands to switch modes

## Testing MQTT Commands

```bash
# Show a shader
mosquitto_pub -t "protogen/fins/shader" -m "sparkles.glsl"

# Play a video
mosquitto_pub -t "protogen/fins/video" -m "/path/to/video.mp4"

# Display an image
mosquitto_pub -t "protogen/fins/image" -m "/path/to/image.png"

# Sync with face expression
mosquitto_pub -t "protogen/fins/sync" -m "happy"

# Launch Doom
mosquitto_pub -t "protogen/fins/game" -m "doom"

# Return to idle
mosquitto_pub -t "protogen/fins/mode" -m "idle"
```

## Future Expansion Ideas

- Audio-reactive shaders (respond to music/sound)
- Motion-reactive effects (IMU data from ESP32)
- More games (Pong, Snake, Tetris)
- Custom shader library with smooth transitions
- Web interface for easier control (publishes MQTT commands)

## Troubleshooting

### Displays not showing content
- Check X11 configuration: `xrandr`
- Verify display connections: both HDMI ports connected
- Test with: `DISPLAY=:0.0 mpv --fs video.mp4`

### MQTT not working
- Check mosquitto is running: `sudo systemctl status mosquitto`
- Test connection: `mosquitto_sub -t "protogen/fins/#" -v`

### Shader files not found
- Ensure shader directory exists: `/shaders/`
- Check file paths in MQTT messages
- Verify mpv supports GLSL shaders

## License

This is a personal fursuit project. Feel free to adapt for your own use.

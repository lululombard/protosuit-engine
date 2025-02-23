# Protosuit Engine

A Protogen fursuit control system combining networked Raspberry Pi devices with SDL-based animation control. Manages two Pi Zero 2W (one per fin) with a round 4" 720x720 display each via a Raspberry Pi 5 which acts as a hub using USB gadget mode networking and MQTT messaging.

## Project overview

The Protosuit Engine consists of those main components:

1. **Ansible deployment** (Hub + Fins)
   - Raspberry Pi 5 hub managing two Pi Zero 2W nodes (one per fin)
   - USB gadget mode networking for reliable low-latency communication between the hub and the fins
   - NAT routing between dedicated subnets to allow the fins to access the internet through the hub
   - MQTT broker for control messages
   - X11 server for efficient display management on the Pi Zero 2W
     - Minimal X server installation
     - Hidden cursor for clean UI
     - No window decorations
     - Optimized for embedded displays
     - Automatic startup via systemd

2. **Engine fins** (for the two Pi Zero 2W)
   - Rust-based SDL application runtime
   - MQTT-controlled animation/application management
   - Support for embedded applications (Doom, custom animations, etc)

## System architecture

```ascii
                    [Raspberry Pi 5 Hub]
                    /                  \
[Left Fin] USB <-> (192.168.42.0/24)   (192.168.43.0/24) <-> USB [Right Fin]
 720x720 Display                       720x720 Display
```

## System requirements

### Hub (Raspberry Pi 5)
- Raspberry Pi OS Lite (64-bit)
- 2x USB ports for fin connections (or use a USB hub)
- Wi-Fi for initial setup
- 2GB+ RAM recommended

### Fins (Raspberry Pi Zero 2W)
- Raspberry Pi OS Lite (32-bit)
- Wi-Fi for initial setup
- Micro USB OTG connected to the hub via USB cable (or to a USB hub)
- 4" 720x720 round display (or any other display with the same resolution, or be creative but you're on your own then)

## Initial setup

### 1. Prepare the Hub (Raspberry Pi 5)

1. Install Raspberry Pi OS Lite (64-bit) on the hub
   - Use Raspberry Pi Imager and click the gear icon (⚙️) to pre-configure:
     - Hostname: `protohub`
     - SSH (enable and set password or add your key)
     - Wi-Fi credentials
2. Boot the Pi and wait for it to connect to your network

### 2. Prepare the Pi Zeros

1. Install Raspberry Pi OS Lite (32-bit) on both Pi Zeros
   - Use Raspberry Pi Imager and click the gear icon (⚙️) to pre-configure:
     - Hostname: `protoleftfin` for left Pi Zero, `protorightfin` for right Pi Zero
     - SSH: enable and set password (or add your key, but you will have to copy the key to the hub manually)
     - Wi-Fi credentials
2. Boot the Pi Zeros and wait for them to connect to your network

### 3. Configure SSH access

1. Connect to the hub via SSH:
   ```bash
   ssh proto@protohub
   ```

2. Generate SSH key on the hub:
   ```bash
   ssh-keygen -t ed25519 -N "" -f ~/.ssh/protosuit
   ```

3. Make that key default for SSH:
   ```bash
   echo -e "Host *\n    IdentityFile ~/.ssh/protosuit" >> ~/.ssh/config
   ```

4. Copy SSH key to all devices (including the hub itself):
   ```bash
   # Copy to the hub itself (needed for Ansible local connections)
   ssh-copy-id -i ~/.ssh/protosuit.pub localhost

   # Copy to both Pi Zeros
   ssh-copy-id -i ~/.ssh/protosuit.pub proto@protoleftfin
   ssh-copy-id -i ~/.ssh/protosuit.pub proto@protorightfin
   ```

5. Connect via SSH to all devices to allow the key fingerprint to be added to the known_hosts file:
   ```bash
   ssh proto@127.0.0.1
   ssh proto@protoleftfin
   ssh proto@protorightfin
   ```

### 4. Clone the repository

1. Install Ansible and dependencies:
   ```bash
   sudo apt update
   sudo apt install -y ansible git
   ```
2. Clone this repository:
   ```bash
   git clone https://github.com/lululombard/protosuit-engine.git
   cd protosuit-engine
   ```

### 5. Configure Ansible inventory

1. Edit `ansible/inventory/hosts.yml` and replace the placeholder IP addresses with actual Wi-Fi IPs:
   ```yaml
   all:
     children:
       hub:
         hosts:
           hub_pi:
             ansible_host: "127.0.0.1"
       fins:
         hosts:
           left_fin:
             ansible_host: "192.168.42.1"  # Replace with protoleftfin's actual Wi-Fi IP
           right_fin:
             ansible_host: "192.168.43.1"  # Replace with protorightfin's actual Wi-Fi IP
   ```

## Running the playbook

Follow these steps in order:

1. Test connectivity to all nodes:
   ```bash
   ansible all -i ansible/inventory/hosts.yml -m ping
   ```

2. Configure networking:
   ```bash
   ansible-playbook -i ansible/inventory/hosts.yml ansible/networking.yml
   ```

3. Disconnect and reconnect to the hub to apply the new shell configuration:
   ```bash
   exit
   ssh proto@protohub
   cd protosuit-engine
   ```

4. Once connected to the hub with the new shell, revert `ansible/inventory/hosts.yml` to use the newly created USB network:
   ```bash
   git checkout -- ansible/inventory/hosts.yml
   ```

5. Configure displays:
   ```bash
   ansible-playbook -i ansible/inventory/hosts.yml ansible/display.yml
   ```

6. Configure hub server (MQTT broker):
   ```bash
   ansible-playbook -i ansible/inventory/hosts.yml ansible/hub_server.yml
   ```

7. Build and deploy the Engine Fin application:
   ```bash
   ansible-playbook -i ansible/inventory/hosts.yml ansible/engine_fin.yml
   ```

Note: The Engine Fin deployment step will take approximately 15-30 minutes on the first run as it needs to install the Rust toolchain and compile the application.

### Troubleshooting

If you experience issues with the step-by-step setup, you can try running the complete setup in one go:
```bash
ansible-playbook -i ansible/inventory/hosts.yml ansible/site.yml
```

Note: The playbooks are idempotent - you can safely run them multiple times. Each run will ensure the configuration is correct without breaking existing setups.

## Network configuration details

### Hub interfaces
| Interface | IP Address    | MAC Address |
|-----------|---------------|-------------|
| usb_left  | 192.168.42.2  | 00:05:69:00:42:02 |
| usb_right | 192.168.43.2  | 00:05:69:00:43:02 |

### Fin interfaces
| Device | IP Address    | Gateway     | MAC Address |
|--------|---------------|-------------|-------------|
| usb0   | 192.168.42.1  | 192.168.42.2| 00:05:69:00:42:01|
| usb0   | 192.168.43.1  | 192.168.43.2| 00:05:69:00:43:01|

## Common tools and shell setup

The Ansible playbook automatically installs and configures common tools on all devices:

### Development tools
- `git` for version control and to clone repositories
- `htop` for system monitoring
- `tmux` for terminal multiplexing and persistent sessions

### Shell environment
- `zsh` as default shell
- Oh My Zsh configuration
  - Robbyrussell theme
  - Git plugin enabled
  - Custom aliases and improvements

These tools are installed during the networking setup phase to ensure a consistent development environment across all devices.

## Display configuration details (Pi Zero 2W)

The Ansible playbook configures a minimal display environment optimized for the round displays:

### Window manager setup
  - Minimal memory footprint
  - No window decorations
  - Hidden cursor
  - Automatic startup at boot
  - Power management disabled
  - Screen blanking disabled

### X server configuration
- Minimal X server installation
  - Only essential input drivers
  - No unnecessary extensions
  - Optimized for embedded displays
  - DPMS (power management) disabled
  - Automatic startup via systemd

## Engine client development

The Engine Client is a Rust application that runs on the Pi Zeros. It is responsible for managing the SDL-based animation/application and sending control messages to the hub. It will be installed automatically by the Ansible playbook, but if you want to install it manually (for development purposes), here are the dependencies you need to install:

### Cross-platform development setup

The engine client can be developed and tested on different platforms:

#### macOS
```bash
# Install dependencies via Homebrew
brew install sdl2 sdl2_ttf sdl2_gfx mosquitto pkg-config

# Build and run in debug mode
make dev
```

#### Linux (Debian/Ubuntu/Raspberry Pi OS)
```bash
# Install dependencies
sudo apt update
sudo apt install -y \
    build-essential \
    libsdl2-dev \
    libsdl2-ttf-dev \
    libsdl2-gfx-dev \
    libx11-dev \
    mosquitto \
    mosquitto-clients

# Build
make
```

### Feature flags
- `x11`: Enables X11 window management (required for Linux/Raspberry Pi, not needed for macOS)

## Building

1. Build the project:
```bash
cargo build --release
```

2. The optimized binary will be available at `target/release/protosuit-engine-fin`

## Development

For quick development and testing, you can use:
```bash
# Compile and run in debug mode with logging
make dev

# Compile for current platform
make

# Compile for ARMhf (Raspberry Pi 32-bit)
make armhf
```

These commands combine the build and run steps. The `RUST_LOG` environment variable enables debug logging to help track what's happening in the application.

## Configuration

The application can be configured through environment variables:

- `PROTOSUIT_ENGINE_DEFAULT_SCENE`: Default scene to load at startup ("debug" or "idle", default: "debug")
- `MQTT_BROKER`: MQTT broker address (default: "localhost")
- `MQTT_PORT`: MQTT broker port (default: 1883)
- `DOOM_PATH`: Path to the Doom executable (default: "/usr/games/chocolate-doom")
- `DOOM_IWAD`: Path to the Doom IWAD file (default: "/usr/share/games/doom/freedoom1.wad")


### Scene management

The engine supports two built-in scenes:
- Debug scene: Displays system information and MQTT connection status
- Idle scene: Shows current date and time

Scenes can be switched via MQTT commands:
```bash
# Switch to debug scene
mosquitto_pub -t "app/switch" -m '{"name": "debug"}'

# Switch to idle scene
mosquitto_pub -t "app/switch" -m '{"name": "idle"}'
```

## Running

1. Start the application (if running as root/sudo):
```bash
sudo DISPLAY=:0 target/release/protosuit-engine-fin
```

2. Control applications through MQTT messages:

Start an application:
```bash
mosquitto_pub -t "app/start" -m '{
    "name": "doom",
    "command": "/usr/games/doom",
    "args": ["--fullscreen"]
}'
```

Switch to an application:
```bash
mosquitto_pub -t "app/switch" -m '{
    "name": "doom"
}'
```

Stop an application:
```bash
mosquitto_pub -t "app/stop" -m '{
    "name": "doom"
}'
```

## MQTT topics

- `app/start`: Start a new application
- `app/switch`: Switch to a different scene or application
- `app/stop`: Stop an application
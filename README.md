# Protosuit Engine

A Protogen fursuit control system combining networked Raspberry Pi devices with SDL-based animation control. Manages two Pi Zero 2W (one per fin) with a round 4" 720x720 display each via a Raspberry Pi 5 hub using USB gadget mode networking and MQTT messaging.

## Project Overview

The Protosuit Engine consists of three main components:

1. **Ansible Deployment** (Hub + Fins)
   - Raspberry Pi 5 hub managing two Pi Zero 2W nodes
   - USB gadget mode networking for reliable low-latency communication
   - NAT routing between dedicated subnets
   - MQTT broker for control messages
   - Matchbox window manager for display management
   - Automated Ansible deployment

2. **Engine Client** (Fins)
   - Rust-based SDL application runtime
   - MQTT-controlled animation/application management
   - Lightweight X11 environment with Matchbox WM
   - Support for embedded applications (Doom, custom animations, etc)

## System Architecture

```ascii
                    [Raspberry Pi 5 Hub]
                    /                  \
[Left Fin] USB <-> (192.168.42.0/24)   (192.168.43.0/24) <-> USB [Right Fin]
 720x720 Display                       720x720 Display
```

## System Requirements

### Hub (Raspberry Pi 5)
- Raspberry Pi OS Lite (64-bit)
- 2x USB ports for fin connections (or use a USB hub)
- Wi-Fi for initial setup
- 4GB+ RAM recommended

### Fins (Raspberry Pi Zero 2W)
- Raspberry Pi OS Lite (32-bit)
- Wi-Fi for initial setup
- USB gadget via micro USB OTG
- 4" 720x720 round display

## Initial Setup

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

### 3. Configure SSH Access

1. Connect to the hub via SSH:
   ```bash
   ssh pi@protohub
   ```

2. Generate SSH key on the hub:
   ```bash
   ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
   ```

2. Copy SSH key to all devices (including the hub itself):
   ```bash
   # Copy to the hub itself (needed for Ansible local connections)
   ssh-copy-id localhost -i ~/.ssh/id_ed25519.pub

   # Copy to both Pi Zeros
   ssh-copy-id pi@protoleftfin -i ~/.ssh/id_ed25519.pub
   ssh-copy-id pi@protorightfin -i ~/.ssh/id_ed25519.pub
   ```

3. Test SSH access to all devices:
   ```bash
   ssh pi@protoleftfin
   ssh pi@protorightfin
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

### 5. Configure Ansible Inventory

1. Edit `ansible/inventory/hosts.yml` and replace the placeholder IP addresses with actual Wi-Fi IPs:
   ```yaml
   all:
     children:
       hub:
         hosts:
           hub_pi:
             ansible_host: "192.168.1.X"  # Replace with protohub's actual Wi-Fi IP
       pizeros:
         hosts:
           left_pizero:
             ansible_host: "192.168.1.Y"  # Replace with protoleftfin's actual Wi-Fi IP
           right_pizero:
             ansible_host: "192.168.1.Z"  # Replace with protorightfin's actual Wi-Fi IP
   ```

## Running the Playbook

1. Test connectivity to all nodes:
   ```bash
   ansible all -i ansible/inventory/hosts.yml -m ping
   ```

2. Run the playbook:
   ```bash
   ansible-playbook -i ansible/inventory/hosts.yml ansible/site.yml
   ```
   Note: The playbooks are idempotent - you can safely run them multiple times. Each run will ensure the configuration is correct without breaking existing setups.

3. Revert `ansible/inventory/hosts.yml` to use the newly created USB network instead of Wi-Fi:
   ```bash
   git checkout -- ansible/inventory/hosts.yml
   ```

## Network Configuration Details

### Hub Interfaces
| Interface | IP Address    | MAC Address |
|-----------|---------------|-------------|
| usb_left  | 192.168.42.2  | 00:05:69:00:42:02 |
| usb_right | 192.168.43.2  | 00:05:69:00:43:02 |

### Fin Interfaces
| Device | IP Address    | Gateway     | MAC Address |
|--------|---------------|-------------|-------------|
| usb0   | 192.168.42.1  | 192.168.42.2| 00:05:69:00:42:01|
| usb0   | 192.168.43.1  | 192.168.43.2| 00:05:69:00:43:01|

## Engine Client

The Engine Client is a Rust application that runs on the Pi Zeros. It is responsible for managing the SDL-based animation/application and sending control messages to the hub.

### Installing Dependencies

On Raspberry Pi OS or Debian/Ubuntu:
```bash
sudo apt update
sudo apt install -y \
    build-essential \
    libsdl2-dev \
    libsdl2-ttf-dev \
    libsdl2-gfx-dev \
    libx11-dev \
    mosquitto \
    mosquitto-clients \
    curl \
    git \
    cmake \
    pkg-config

# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
```

## Building

1. Build the project:
```bash
cargo build --release
```

2. The optimized binary will be available at `target/release/protosuit-engine-client`

## Configuration

The application can be configured through environment variables:

- `MQTT_BROKER`: MQTT broker address (default: "localhost")
- `MQTT_PORT`: MQTT broker port (default: 1883)
- `RUST_LOG`: Logging level (default: "info")
- `SDL_WINDOW_WIDTH`: Window width in pixels (default: 720)
- `SDL_WINDOW_HEIGHT`: Window height in pixels (default: 720)

## Running

1. Start the application (if running as root/sudo):
```bash
sudo DISPLAY=:0 target/release/protosuit-engine-client
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

## MQTT Topics

- `app/start`: Start a new application
- `app/stop`: Stop a running application
- `app/switch`: Switch focus to a running application
- `app/status/{app_name}`: Status updates for applications

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

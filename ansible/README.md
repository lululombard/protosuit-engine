# Protosuit Engine - Ansible Deployment

This directory contains Ansible playbooks and configuration files for automated deployment of the Protosuit Engine on Raspberry Pi systems.

## Quick Start

### Prerequisites

1. **Clone the repository on your Raspberry Pi**:
   ```bash
   git clone <repository-url> ~/protosuit-engine
   cd ~/protosuit-engine
   ```

2. **Install Ansible** (if not already installed):
   ```bash
   sudo apt update
   sudo apt install ansible
   ```

3. **Ensure you're running as the correct user**:
   - The default configuration expects user `proto`
   - Modify `inventory/hosts.yml` if using a different user

### Deployment

Deploy the system directly on the Pi:

```bash
cd ~/protosuit-engine/ansible
./scripts/deploy.sh
```

This approach is recommended because:
- **Simpler setup**: No need for SSH keys or remote configuration
- **Direct access**: All files are already on the target system
- **Easier debugging**: Can directly access logs and files
- **Better performance**: No network overhead during deployment

## Deployment Types

### Full Deployment (Default)
```bash
./scripts/deploy.sh --type full
```
- Installs all packages
- Configures displays
- Sets up systemd service
- Enables auto-start

### Main Setup Only
```bash
./scripts/deploy.sh --type main
```
- Installs packages
- Sets up Python environment
- Creates systemd service
- Skips display configuration

### Display Configuration Only
```bash
./scripts/deploy.sh --type display
```
- Configures X11 for dual displays
- Sets up display environment
- Skips package installation

## Configuration

### Inventory Configuration

Edit `inventory/hosts.yml` to customize:

- **User settings**: Change `pi_user` and related variables
- **Project directory**: Modify `project_dir` path
- **Display settings**: Adjust resolution and positioning
- **MQTT settings**: Configure broker address and port

**Note**: Since we're deploying directly on the Pi, no remote connection settings are needed.

## File Structure

```
ansible/
├── ansible.cfg                 # Ansible configuration
├── inventory/
│   └── hosts.yml              # Host inventory and variables
├── playbooks/
│   ├── main.yml               # Main setup playbook
│   ├── display-config.yml     # Display configuration playbook
│   └── deploy.yml             # Complete deployment playbook
├── templates/
│   ├── protosuit-engine.service.j2    # Systemd service template
│   ├── protosuit-castbridge.service.j2 # Castbridge service template
│   ├── protosuit-networkingbridge.service.j2 # Networkingbridge service template
│   ├── 99-dual-display.conf.j2        # X11 configuration template
│   ├── xinitrc.j2                     # X11 startup script template
│   └── display-env.sh.j2              # Display environment template
├── scripts/
│   └── deploy.sh              # Deployment script
└── README.md                  # This file
```

## What Gets Configured

### System Packages
- MQTT broker (mosquitto)
- Python 3 and pip
- Media players (mpv, feh)
- Games (chocolate-doom, retroarch)
- Bluetooth support
- X11 and display utilities
- AirPlay receiver (shairport-sync)
- Spotify Connect (raspotify)
- Access point (hostapd, dnsmasq)

### Display Configuration
- Dual HDMI display setup (720x720 each)
- Display rotation (left fin rotated right, right fin rotated left)
- X11 configuration for extended desktop
- Screen blanking disabled
- Power management disabled

### Service Configuration
- Systemd services for auto-start (renderer, launcher, web, bluetoothbridge, castbridge, networkingbridge)
- Services run as non-root user
- Automatic restart on failure
- Proper environment variables
- Security hardening
- Castbridge sudo permissions for managing shairport-sync and raspotify
- Networkingbridge sudo permissions for hostapd, dnsmasq, nmcli, and iptables

### Auto-Start Options
1. **Systemd Service** (recommended): Starts on boot, runs in background
2. **Desktop Autostart**: Starts when user logs into desktop
3. **Manual Start**: Use provided helper functions

### Wi-Fi Hardware Configuration

The networking bridge requires two Wi-Fi interfaces for dual-mode operation:

1. **Built-in Raspberry Pi Wi-Fi (wlan0)**: Used for **Access Point mode**
   - Provides stable AP operation
   - Hosts the "Protosuit" access point for device connectivity

2. **USB Wi-Fi Dongle (wlan1)**: Used for **Client mode**
   - Connects to external Wi-Fi networks for internet access
   - Tested with AliExpress Wi-Fi 6 USB dongles (RTL8851BU chipset)

**Important**: The RTL8851BU unofficial drivers work well in client mode but are **unstable in AP mode**. Running them as access points causes kernel bugs, memory corruption/leaks, and system instability. This is why we use the integrated Raspberry Pi Wi-Fi for AP mode instead.

**Note**: Newer Linux kernel versions include built-in RTL8851BU drivers, but as of January 2026, the latest Raspberry Pi OS still requires out-of-tree drivers for these chipsets.

#### USB Wi-Fi Driver Installation

The deployment playbook automatically installs the RTL8851BU driver from the [morrownr/rtw89](https://github.com/morrownr/rtw89) repository. This is a quality driver repository that provides stable client mode operation.

The driver is compiled during deployment and configured to load automatically on boot. If you're using a different USB Wi-Fi adapter, you may need to modify the driver installation tasks in [playbooks/main.yml](playbooks/main.yml:234-297).

#### Interface Configuration

The interface assignments are configured in:
- **Application config**: [config.yaml](../config.yaml:50-52)
- **Ansible inventory**: [inventory/hosts.yml](inventory/hosts.yml:25-26)

```yaml
networkingbridge:
  interfaces:
    client: "wlan1"  # USB Wi-Fi for client mode
    ap: "wlan0"      # Built-in Wi-Fi for AP mode
```

NetworkManager is configured to leave wlan0 unmanaged so hostapd can control it as an access point. This prevents NetworkManager from trying to connect wlan0 as a client.

## Testing and Verification

### Test Displays
```bash
source ~/.display-env.sh
test_displays
```

### Test MQTT
```bash
# Subscribe to all fin topics
mosquitto_sub -t "protogen/fins/#" -v

# In another terminal, send test commands
mosquitto_pub -t "protogen/fins/shader" -m "waves"
```

### Check Service Status
```bash
sudo systemctl status protosuit-engine
sudo journalctl -u protosuit-engine -f
```

## Troubleshooting

### Common Issues

1. **Permission Denied**:
   - Ensure you're running as the correct user
   - Check sudo permissions
   - Verify file ownership

2. **Display Not Working**:
   - Check HDMI connections
   - Verify display configuration: `xrandr`
   - Test with: `DISPLAY=:0 mpv --fs video.mp4`

3. **MQTT Connection Failed**:
   - Check mosquitto service: `sudo systemctl status mosquitto`
   - Test connection: `mosquitto_sub -t "test" -v`

4. **Service Won't Start**:
   - Check logs: `sudo journalctl -u protosuit-engine -f`
   - Verify Python environment: `source env/bin/activate && python protosuit_engine.py`
   - Check file permissions and paths

### Manual Service Management

```bash
# Start service
sudo systemctl start protosuit-engine

# Stop service
sudo systemctl stop protosuit-engine

# Restart service
sudo systemctl restart protosuit-engine

# Enable auto-start
sudo systemctl enable protosuit-engine

# Disable auto-start
sudo systemctl disable protosuit-engine
```

### Manual Testing

```bash
# Test Python script directly
cd /home/proto/protosuit-engine
source env/bin/activate
python protosuit_engine.py

# Test with helper functions
source ~/.display-env.sh
start_protosuit
```

## Customization

### Adding New Shaders
1. Add shader files to `shaders/` directory
2. Update expression mapping in `protosuit_engine.py`
3. Test with MQTT: `mosquitto_pub -t "protogen/fins/shader" -m "new_shader.glsl"`

### Adding New Games
1. Install game packages in `inventory/hosts.yml`
2. Add game launch logic to `engine/launchers.py`
3. Update MQTT command handling

## Security Notes

- Service runs as non-root user
- Systemd service includes security hardening
- MQTT broker runs locally by default
- File permissions are properly set

For production deployments, consider:
- Using TLS for MQTT connections
- Implementing authentication
- Firewall configuration
- Regular security updates

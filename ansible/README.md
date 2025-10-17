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

### Display Configuration
- Dual HDMI display setup (720x720 each)
- Display rotation (left fin rotated right, right fin rotated left)
- X11 configuration for extended desktop
- Screen blanking disabled
- Power management disabled

### Service Configuration
- Systemd service for auto-start
- Service runs as non-root user
- Automatic restart on failure
- Proper environment variables
- Security hardening

### Auto-Start Options
1. **Systemd Service** (recommended): Starts on boot, runs in background
2. **Desktop Autostart**: Starts when user logs into desktop
3. **Manual Start**: Use provided helper functions

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

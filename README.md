# Protosuit Network

This repository contains Ansible playbooks to configure a network setup with a Raspberry Pi 5 hub and two Pi Zero 2W nodes. The hub acts as a gateway performing NAT between two subnets, with each Pi Zero connected via USB gadget mode.

## System Requirements

### Hub (Raspberry Pi 5)
- Raspberry Pi OS Lite (64-bit)
- Two USB ports for connecting the Pi Zeros
- WiFi connectivity for initial setup and Ansible communication

### Pi Zeros (Raspberry Pi Zero 2W)
- Raspberry Pi OS Lite (32-bit)
- USB gadget mode enabled
- WiFi connectivity for initial setup and Ansible communication

## Initial Setup

### 1. Prepare the Hub (Raspberry Pi 5)

1. Install Raspberry Pi OS Lite (64-bit) on the hub
   - Use Raspberry Pi Imager and click the gear icon (⚙️) to pre-configure:
     - Hostname: `protohub`
     - SSH (enable and set password or add your key)
     - WiFi credentials
2. Boot the Pi and wait for it to connect to your network
3. Install Ansible and dependencies:
   ```bash
   sudo apt update
   sudo apt install -y ansible git
   ```
4. Clone this repository:
   ```bash
   git clone https://github.com/lululombard/protosuit-network.git
   cd protosuit-network
   ```

### 2. Prepare the Pi Zeros

1. Install Raspberry Pi OS Lite (32-bit) on both Pi Zeros
   - Use Raspberry Pi Imager and click the gear icon (⚙️) to pre-configure:
     - Hostname: `protoleftfin` for left Pi Zero, `protorightfin` for right Pi Zero
     - SSH (enable and set password or add your key)
     - WiFi credentials
2. Boot the Pi Zeros and wait for them to connect to your network

Note: If you didn't use Raspberry Pi Imager's pre-configuration, you can manually enable SSH and WiFi by creating these files on the boot partition:
```bash
# Enable SSH
touch /boot/ssh

# Configure WiFi (replace with your details)
cat > /boot/wpa_supplicant.conf << EOF
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="YOUR_WIFI_NAME"
    psk="YOUR_WIFI_PASSWORD"
}
EOF
```

### 3. Configure SSH Access

1. Generate SSH key on the hub (if not already done):
   ```bash
   ssh-keygen -t ed25519
   ```

2. Copy SSH key to both Pi Zeros:
   ```bash
   ssh-copy-id <protoleftfin-wifi-ip>
   ssh-copy-id <protorightfin-wifi-ip>
   ```

### 4. Configure Ansible Inventory

1. Edit `ansible/inventory/hosts.yml` and replace the placeholder IP addresses with actual WiFi IPs:
   ```yaml
   all:
     children:
       hub:
         hosts:
           hub_pi:
             ansible_host: "192.168.1.X"  # Replace with protohub's actual WiFi IP
       pizeros:
         hosts:
           left_pizero:
             ansible_host: "192.168.1.Y"  # Replace with protoleftfin's actual WiFi IP
           right_pizero:
             ansible_host: "192.168.1.Z"  # Replace with protorightfin's actual WiFi IP
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

3. After the playbook completes successfully, reboot all devices:
   ```bash
   ansible all -i ansible/inventory/hosts.yml -m reboot
   ```

## Network Configuration Details

After successful deployment:

### Hub (Raspberry Pi 5)
- Left interface (usb_left):
  - Name: usb_left
  - IP: 192.168.42.2/24
  - MAC: 00:05:69:00:42:02

- Right interface (usb_right):
  - Name: usb_right
  - IP: 192.168.43.2/24
  - MAC: 00:05:69:00:43:02

### Left Pi Zero
- Interface: usb0
- IP: 192.168.42.1/24
- Gateway: 192.168.42.2
- MAC: 00:05:69:00:42:01

### Right Pi Zero
- Interface: usb0
- IP: 192.168.43.1/24
- Gateway: 192.168.43.2
- MAC: 00:05:69:00:43:01

## Troubleshooting

1. If interfaces don't come up after reboot:
   ```bash
   sudo systemctl restart networking
   ```

2. If NAT isn't working:
   ```bash
   sudo iptables-restore < /etc/iptables/rules.v4
   ```

3. To verify interface names on the hub:
   ```bash
   ip addr show
   ```

4. To check USB gadget mode on Pi Zeros:
   ```bash
   lsmod | grep g_ether
   ```

## Notes

- The configuration uses persistent interface naming on the hub via udev rules
- NAT rules are configured to allow traffic between subnets
- All configurations persist across reboots
- The Pi Zeros must be connected to their designated USB ports on the hub

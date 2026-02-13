#!/bin/bash
# AP interface setup - runs as ExecStartPre for hostapd
# Deployed by Ansible - do not edit manually
set -e

source /etc/protosuit/ap.env

# Remove AP interface from NetworkManager control
nmcli device set "$AP_INTERFACE" managed no || true

# Bring interface down/up
ip link set "$AP_INTERFACE" down
sleep 0.5
ip link set "$AP_INTERFACE" up
sleep 0.5

# Disable power save for better performance
iw dev "$AP_INTERFACE" set power_save off || true

# Configure IP address
ip addr flush dev "$AP_INTERFACE"
ip addr add "$AP_IP_CIDR" dev "$AP_INTERFACE"

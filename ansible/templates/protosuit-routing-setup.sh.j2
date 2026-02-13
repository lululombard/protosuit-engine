#!/bin/bash
# NAT routing setup - runs as ExecStartPost for hostapd
# Deployed by Ansible - do not edit manually
set -e

source /etc/protosuit/ap.env

# Enable IP forwarding
sysctl -w net.ipv4.ip_forward=1

# MASQUERADE for AP network going out
iptables -t nat -C POSTROUTING -s "$AP_NETWORK" ! -d "$AP_NETWORK" -j MASQUERADE 2>/dev/null ||
    iptables -t nat -A POSTROUTING -s "$AP_NETWORK" ! -d "$AP_NETWORK" -j MASQUERADE

# Forward from AP interface
iptables -C FORWARD -i "$AP_INTERFACE" -s "$AP_NETWORK" -j ACCEPT 2>/dev/null ||
    iptables -A FORWARD -i "$AP_INTERFACE" -s "$AP_NETWORK" -j ACCEPT

# Forward to AP (established connections)
iptables -C FORWARD -o "$AP_INTERFACE" -d "$AP_NETWORK" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null ||
    iptables -A FORWARD -o "$AP_INTERFACE" -d "$AP_NETWORK" -m state --state RELATED,ESTABLISHED -j ACCEPT

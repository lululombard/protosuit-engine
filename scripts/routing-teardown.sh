#!/bin/bash
# NAT routing teardown - runs as ExecStopPost for hostapd
# Deployed by Ansible - do not edit manually

source /etc/protosuit/ap.env

# Remove iptables rules (ignore errors if rules don't exist)
iptables -t nat -D POSTROUTING -s "$AP_NETWORK" ! -d "$AP_NETWORK" -j MASQUERADE 2>/dev/null || true
iptables -D FORWARD -i "$AP_INTERFACE" -s "$AP_NETWORK" -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -o "$AP_INTERFACE" -d "$AP_NETWORK" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true

# Disable IP forwarding
sysctl -w net.ipv4.ip_forward=0

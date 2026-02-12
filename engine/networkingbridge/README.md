# NetworkingBridge

Manages Wi-Fi client and access point modes via NetworkManager (nmcli), hostapd, and dnsmasq. Provides NAT routing from AP clients to upstream.

## MQTT Topics

### Subscribes
- `protogen/fins/networkingbridge/scan/start` -trigger Wi-Fi scan
- `protogen/fins/networkingbridge/client/enable` -enable/disable client interface
- `protogen/fins/networkingbridge/client/connect` -connect to network (`{"ssid", "password"}`)
- `protogen/fins/networkingbridge/client/disconnect` -disconnect from current network
- `protogen/fins/networkingbridge/ap/enable` -enable/disable AP (`{"enable": true}`)
- `protogen/fins/networkingbridge/ap/config` -update AP config (ssid, security, password, ip_cidr)
- `protogen/fins/networkingbridge/routing/enable` -enable/disable NAT routing (`{"enable": true}`)
- `protogen/fins/networkingbridge/qrcode/generate` -generate Wi-Fi QR code

### Publishes
- `protogen/fins/networkingbridge/status/interfaces` -detected interfaces (retained)
- `protogen/fins/networkingbridge/status/client` -client connection status (retained)
- `protogen/fins/networkingbridge/status/ap` -AP status with connected clients (retained)
- `protogen/fins/networkingbridge/status/scan` -scan results (retained)
- `protogen/fins/networkingbridge/status/scanning` -scan in progress flag
- `protogen/fins/networkingbridge/status/connection` -connect result
- `protogen/fins/networkingbridge/status/qrcode` -Wi-Fi QR code as base64 PNG (retained)

## Configuration

Reads from `config.yaml` sections: `networking.client` (interface), `networking.ap` (interface, ssid, security, password, ip_cidr), `networking.routing`, `mqtt`

## Dependencies

- paho-mqtt, pyyaml, qrcode, Pillow
- System tools: nmcli, hostapd, dnsmasq, iptables, iw

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/networkingbridge/networkingbridge.py
```

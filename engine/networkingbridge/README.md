# NetworkingBridge

Manages Wi-Fi client and access point modes via NetworkManager D-Bus API, hostapd, and dnsmasq (systemd-managed). NAT routing is handled automatically by systemd drop-in scripts when the AP is enabled.

## Architecture

- **Client mode**: NetworkManager D-Bus API (scan, connect, disconnect, status) via `pydbus`
- **AP mode**: `hostapd.service` and `dnsmasq.service` managed via `ServiceController` (D-Bus/systemd)
- **Routing**: Automatic via systemd `ExecStartPost`/`ExecStopPost` scripts (iptables NAT)
- **Boot state**: systemd is the source of truth (`get_health()` at startup), not MQTT retained messages
- **Client list**: `/proc/net/arp` parsing with OUI vendor lookup

### Systemd Drop-in Overrides

hostapd has `ExecStartPre` (interface setup) and `ExecStartPost` (NAT routing), with teardown scripts in `ExecStopPost`. dnsmasq uses `BindsTo=hostapd.service` so it auto-starts/stops with the AP.

## MQTT Topics

### Subscribes
- `protogen/fins/networkingbridge/scan/start` - trigger Wi-Fi scan
- `protogen/fins/networkingbridge/client/enable` - enable/disable client interface
- `protogen/fins/networkingbridge/client/connect` - connect to network (`{"ssid", "password"}`)
- `protogen/fins/networkingbridge/client/disconnect` - disconnect from current network
- `protogen/fins/networkingbridge/ap/enable` - enable/disable AP (`{"enable": true}`)
- `protogen/fins/networkingbridge/ap/config` - update AP config (ssid, security, password, ip_cidr)
- `protogen/fins/networkingbridge/qrcode/generate` - generate Wi-Fi QR code

### Publishes
- `protogen/fins/networkingbridge/status/interfaces` - detected interfaces (retained)
- `protogen/fins/networkingbridge/status/client` - client connection status (retained)
- `protogen/fins/networkingbridge/status/ap` - AP status with connected clients (retained)
- `protogen/fins/networkingbridge/status/scan` - scan results (retained)
- `protogen/fins/networkingbridge/status/scanning` - scan in progress flag
- `protogen/fins/networkingbridge/status/connection` - connect result
- `protogen/fins/networkingbridge/status/qrcode` - Wi-Fi QR code as base64 PNG (retained)
- `protogen/fins/networkingbridge/status/hostapd/health` - hostapd systemd health (retained)
- `protogen/fins/networkingbridge/status/dnsmasq/health` - dnsmasq systemd health (retained)

## Configuration

Reads from `config.yaml` sections: `networking.client` (interface), `networking.ap` (interface, ssid, security, password, ip_cidr), `mqtt`

## Dependencies

- paho-mqtt, pyyaml, qrcode, Pillow, pydbus (NetworkManager D-Bus)
- ServiceController (systemd D-Bus via pydbus)
- System services: hostapd, dnsmasq (managed via systemd)

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/networkingbridge/networkingbridge.py
```

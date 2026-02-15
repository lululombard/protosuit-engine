# SystemBridge

Exposes RPi 5 system health metrics, fan curve control, throttle temperature configuration, and power management (reboot/shutdown) via MQTT. Metrics are published periodically; fan curve changes take effect immediately and persist across reboots.

## MQTT Topics

### Subscribes
- `protogen/fins/systembridge/fan_curve/set` — set fan curve trip points (JSON `{trip_1, trip_2, trip_3, trip_4}`)
- `protogen/fins/systembridge/throttle_temp/set` — set CPU throttle temperature (JSON `{temp}`, reboot required)
- `protogen/fins/systembridge/power/reboot` — reboot the system
- `protogen/fins/systembridge/power/shutdown` — shut down the system

### Publishes
- `protogen/fins/systembridge/status/metrics` — CPU%, memory%, disk%, temp, freq, fan RPM/PWM, uptime, throttle flags (retained)
- `protogen/fins/systembridge/status/fan_curve` — current trip point temperatures (retained)
- `protogen/fins/systembridge/status/throttle_temp` — current throttle temp setting (retained)
- `protogen/global/notifications` — fan curve / throttle / power event notifications

## Configuration

Reads from `config.yaml` section: `systembridge`
- `publish_interval` — metrics publish frequency in seconds (default 5)
- `fan_curve.trip_1` through `fan_curve.trip_4` — fan speed trip point temperatures in °C

Fan curve is written back to `config.yaml` on change and reapplied on service start.

## Dependencies

- paho-mqtt, psutil, pydbus
- `vcgencmd` (RPi userland tools, requires `video` group)
- D-Bus (logind for reboot/shutdown)

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/systembridge/systembridge.py
```

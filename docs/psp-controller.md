# PSP Controller

A PSP homebrew application that turns a PlayStation Portable into a wireless gamepad for Protosuit Engine. Connects via Wi-Fi and sends button events over MQTT.

## How It Works

1. Loads config from Memory Stick (`ms0:/PSP/GAME/ProtosuitRemote/config.txt`)
2. Shows Wi-Fi profile selection menu (uses PSP's saved network profiles)
3. Connects to Wi-Fi, then to the MQTT broker
4. Polls PSP buttons continuously, sends press/release events as JSON
5. L/R shoulder buttons switch between left and right display targeting

## Button Mapping

| PSP Button | Mapped Key | Action |
|------------|-----------|--------|
| D-Pad Up | `Up` | Movement |
| D-Pad Down | `Down` | Movement |
| D-Pad Left | `Left` | Movement |
| D-Pad Right | `Right` | Movement |
| Cross (X) | `A` | Confirm/Jump |
| Circle (O) | `B` | Back/Action |
| L Shoulder | — | Select left display |
| R Shoulder | — | Select right display |

## MQTT Messages

Publishes to `protogen/fins/launcher/input/exec` (configurable):

```json
{"key": "Up", "action": "keydown", "display": "left"}
{"key": "Up", "action": "keyup", "display": "left"}
```

Uses a minimal MQTT 3.1.1 client implementation (QoS 0, clean session).

## Configuration

Create `config.txt` on the PSP Memory Stick at `ms0:/PSP/GAME/ProtosuitRemote/`:

```ini
mqtt_broker_ip=192.168.1.100
mqtt_broker_port=1883
mqtt_client_id=psp-controller
mqtt_topic=protogen/fins/launcher/input/exec
mqtt_keepalive=60
```

A default config is created automatically on first run if missing. No recompilation needed, just edit and restart.

## Building

Requires the [PSP SDK toolchain](https://github.com/pspdev/pspdev).

```bash
cd psp-controller
./setup-sdk.sh    # Install PSP SDK (if not already installed)
./build.sh        # Build EBOOT.PBP
```

Or manually:

```bash
make clean && make
```

Output: `EBOOT.PBP` (PSP executable)

## Deploying

Deploy to one or more PSPs via FTP (PSP must be running an FTP server):

```bash
./deploy.sh 192.168.1.50              # Single PSP
./deploy.sh 192.168.1.50 192.168.1.51 # Multiple PSPs
```

Copies `EBOOT.PBP` to `PSP/GAME/ProtosuitRemote/` on each device.

## Architecture

| File | Purpose |
|------|---------|
| `src/main.c` | App lifecycle, main loop |
| `src/mqtt.c` | Minimal MQTT 3.1.1 client (CONNECT, PUBLISH, PINGREQ) |
| `src/input.c` | PSP button polling and event generation |
| `src/ui.c` | On-screen display rendering |
| `src/wifi.c` | Wi-Fi connection management |
| `src/wifi_menu.c` | Wi-Fi profile selection UI |
| `src/config_loader.c` | Config file parser |

## Connection Behavior

- Wi-Fi retry: every 5 seconds
- MQTT retry: every 3 seconds (after Wi-Fi connects)
- Keepalive ping: every 30 seconds
- Auto-reconnects on disconnection

# Protosuit Remote Control

A PSP homebrew application that sends button inputs to a MQTT broker for controlling protosuit-engine.

## Prerequisites

### On PSP:
- Custom firmware (CFW) installed
- FTP server homebrew (e.g., `ftpd` or `PSPFiler`) for wireless deployment
- Wi-Fi configured in PSP Settings → Network Settings

### On Development Machine:
- PSP SDK (installed via `setup_sdk.sh`)
- `lftp` (recommended) or `ftp` client for deployment

## Setup

### 1. Install PSP SDK

```bash
./setup_sdk.sh
```

This will take over an hour to complete. It installs the complete PSP development environment.

It is normal if you install ends with, just ignore it, it will work anyways:
```
warning: no 'XferCommand' configured
:: Synchronizing package databases...
error: failed to synchronize all databases (error invoking external downloader)
../scripts/003-psp-packages.sh: Failed.
```

### 2. Configure

The app reads settings from `config.txt` on your Memory Stick!

**On first run**, the app will create a default `config.txt` at:
```
ms0:/PSP/GAME/ProtosuitRemote/config.txt
```

Edit this file on your PSP via FTP (or via USB) to change:
- Wi-Fi profile (1-10)
- MQTT broker IP address
- MQTT port, client ID, topic
- Keepalive interval

**Example config.txt:**
```ini
Wi-Fi_profile=1
mqtt_broker_ip=192.168.1.100
mqtt_broker_port=1883
mqtt_client_id=psp-controller
mqtt_topic=protogen/fins/launcher/input/exec
mqtt_keepalive=60
```

No need to recompile! Just edit the file and restart the app.

### 3. Build

```bash
./build.sh
```

This creates `EBOOT.PBP` - the PSP executable.

### 4. Deploy to PSP

**Option A: Via FTP (wireless)**

1. Start FTP server on your PSP
2. Note your PSP's IP address
3. Run:

```bash
./deploy.sh <PSP_IP_ADDRESS>
# Example: ./deploy.sh 192.168.1.100
```

**Option B: Via USB/Memory Stick**

1. Connect PSP to computer or remove Memory Stick
2. Copy `EBOOT.PBP` to:
   ```
   /PSP/GAME/ProtosuitRemote/EBOOT.PBP
   ```

## Usage

1. Configure Wi-Fi on PSP (Settings → Network Settings)
   - The app uses the profile specified in `Wi-Fi_PROFILE`
2. Start your MQTT broker on the configured IP
3. Launch the app from Game → Memory Stick
4. Wait for Wi-Fi and MQTT connection
5. Press PSP buttons - they'll be sent as MQTT messages!

## MQTT Message Format

Button presses are published as JSON:

```json
{
  "key": "Cross",
  "action": "keydown",
  "display": "left"
}
```

## Controls

- **D-Pad**: Navigate displays (left/right/both eyes)
- **Face Buttons**: Send input commands
- **Shoulder Buttons**: Additional controls
- **Start**: Toggle functions
- **Select**: Display selection

## Troubleshooting

**Build fails with "psp-config not found":**
- Make sure PSPDEV is set: `export PSPDEV=/usr/local/pspdev`
- Add to PATH: `export PATH=$PATH:$PSPDEV/bin`

**Wi-Fi connection fails:**
- Verify PSP network profile is configured
- Check that you're using the correct profile number in `config.h`

**MQTT connection fails:**
- Verify MQTT broker IP is correct
- Check that broker is running: `mosquitto -v`
- Ensure firewall allows port 1883

**FTP deployment fails:**
- Ensure FTP server is running on PSP
- Verify PSP IP address
- Try installing lftp: `sudo apt install lftp`

## Files

- `EBOOT.PBP` - PSP executable (deploy this)
- `protosuit-remote-control.elf` - Debug version with symbols
- `src/` - Source code
- `include/` - Header files
- `config.h` - Configuration

## License

Whatever it's just a fun project!
It's open source - modify as needed!

# Launcher

Manages audio playback, video playback, and executable launching via MQTT commands. Scans `assets/audio`, `assets/video`, and `assets/executables` for available files.

## MQTT Topics

### Subscribes
- `protogen/fins/launcher/start/{audio,video,exec}` -start playback/execution (filename or JSON `{file}`)
- `protogen/fins/launcher/stop/{audio,video,exec}` -graceful stop
- `protogen/fins/launcher/kill/{audio,video,exec}` -force stop
- `protogen/fins/launcher/config/reload` -rescan files and reload config
- `protogen/fins/launcher/input/exec` -forward input to running executable

### Publishes
- `protogen/fins/launcher/status/audio` -playing files and available audio list (retained)
- `protogen/fins/launcher/status/video` -playing file and available video list (retained)
- `protogen/fins/launcher/status/exec` -running executable, PID, and available list (retained)

## Configuration

Reads from `config.yaml` sections: `display`, `system`, `mqtt`

## Dependencies

- paho-mqtt
- ffplay (audio), mpv (video) -invoked as subprocesses
- Shell scripts in `assets/executables/` for exec launcher

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/launcher/launcher.py
```

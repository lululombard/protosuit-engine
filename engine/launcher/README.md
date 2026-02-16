# Launcher

Manages audio playback, video playback, executable launching, and presets via MQTT commands. Scans `assets/audio`, `assets/video`, and `assets/executables` for available files. Presets save and restore complete visor state (shader, uniforms, Teensy params) with optional launcher actions and gamepad combo activation.

## MQTT Topics

### Subscribes
- `protogen/fins/launcher/start/{audio,video,exec}` -start playback/execution (filename or JSON `{file}`)
- `protogen/fins/launcher/stop/{audio,video,exec}` -graceful stop
- `protogen/fins/launcher/kill/{audio,video,exec}` -force stop
- `protogen/fins/launcher/config/reload` -rescan files and reload config
- `protogen/fins/launcher/input/exec` -forward input to running executable
- `protogen/fins/launcher/preset/save` -save or update a preset
- `protogen/fins/launcher/preset/delete` -delete a preset by name
- `protogen/fins/launcher/preset/activate` -activate a preset by name
- `protogen/fins/launcher/preset/set_default` -set or clear the default preset

### Publishes
- `protogen/fins/launcher/status/audio` -playing files and available audio list (retained)
- `protogen/fins/launcher/status/video` -playing file and available video list (retained)
- `protogen/fins/launcher/status/exec` -running executable, PID, and available list (retained)
- `protogen/fins/launcher/status/presets` -all presets, active preset, and default preset (retained)

## Presets

Presets are stored as retained MQTT messages and restored on startup. Each preset contains:

- **Shader**: animation name to load
- **Uniforms**: shader parameter values (per-display or both)
- **Teensy params**: face, color, hueF, hueB, brightness, etc.
- **Launcher action** (optional): auto-start a video, exec, or audio file
- **Gamepad combo** (optional): button combination to activate from a dedicated combo controller

When a video or executable finishes, the default preset (if set) is automatically re-applied. The default preset is also applied on boot after a brief delay for retained messages to arrive.

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

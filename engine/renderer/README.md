# Renderer

MQTT-controlled OpenGL shader renderer for dual displays with crossfade transitions and audio-reactive FFT support.

## MQTT Topics

### Subscribes
- `protogen/fins/renderer/set/shader/file` -set shader by animation name (JSON: `{display, name, transition_duration}`)
- `protogen/fins/renderer/set/shader/uniform` -update a shader uniform (JSON: `{display, name, type, value}`)
- `protogen/fins/renderer/config/reload` -reload config.yaml at runtime
- `protogen/fins/launcher/status/exec` -pause rendering while an executable is running
- `protogen/fins/launcher/status/video` -pause rendering while a video is playing

### Publishes
- `protogen/fins/renderer/status/shader` -current/available shaders and transition state (retained)
- `protogen/fins/renderer/status/uniform` -active uniform values and metadata (retained)
- `protogen/fins/renderer/status/performance` -FPS and per-display resolution info (retained)

## Configuration

Reads from `config.yaml` sections: `display`, `monitoring`, `transition`, `mqtt`, `animations`, `default_animation`

## Dependencies

- moderngl, pygame, numpy, paho-mqtt
- Audio capture (optional) for FFT-reactive shaders
- X11 display server (`:0`)

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/renderer/renderer.py
```

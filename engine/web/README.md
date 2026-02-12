# Web

Flask web interface serving the Protosuit control panel. The browser connects directly to the MQTT broker via WebSocket for real-time control; the server only serves pages and an MJPEG display preview stream.

## Routes

- `/` -main dashboard (shader control, launcher, uniforms)
- `/controller` -virtual gamepad controller
- `/bluetooth` -Bluetooth device management
- `/networking` -network settings
- `/cast` -AirPlay and Spotify Connect settings
- `/api/stream` -MJPEG live preview of both displays (via FFmpeg x11grab)

## MQTT Topics

This service does not subscribe or publish MQTT messages directly. The browser-side JavaScript communicates with the MQTT broker over WebSocket (`ws://localhost:9001`).

## Configuration

Reads from `config.yaml` sections: `web` (host, port, debug), `display`, `system`, `animations`

## Dependencies

- flask, paho-mqtt (indirect via browser WebSocket)
- ffmpeg (for `/api/stream` MJPEG capture)
- X11 display server (`:0`)

## Running Standalone

```bash
cd /home/proto/protosuit-engine
PYTHONPATH=engine env/bin/python engine/web/server.py
```

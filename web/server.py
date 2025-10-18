#!/usr/bin/env python3
"""
Web Interface for Protosuit Engine
Serves static web interface and provides display preview API.
Browser connects directly to MQTT broker via WebSocket.
"""

from flask import Flask, render_template, Response
import os
import sys
import subprocess

# Add parent directory to path to import config loader
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.loader import ConfigLoader

app = Flask(__name__)

# Initialize config loader
config_loader = ConfigLoader()


@app.route("/")
def index():
    # Get all animations (base + overlay)
    all_animations = {}
    for anim in config_loader.get_base_animations():
        all_animations[anim["id"]] = anim
    for anim in config_loader.get_overlay_animations():
        all_animations[anim["id"]] = anim
    return render_template("index.html", animations=all_animations)


@app.route("/api/stream")
def api_stream():
    """
    MJPEG stream of the displays using FFmpeg x11grab
    More efficient than repeated screenshots
    """

    def generate_frames():
        # Get display and system config
        display_config = config_loader.get_display_config()
        system_config = config_loader.get_system_config()

        width = display_config.width
        height = display_config.height
        left_x = display_config.left_x
        y = display_config.y
        x_display = system_config.x_display

        # Capture both displays as one stream (side by side)
        total_width = width * 2

        # FFmpeg command for x11grab -> MJPEG stream
        cmd = [
            "ffmpeg",
            "-f",
            "x11grab",
            "-draw_mouse",
            "0",  # Don't capture the mouse cursor
            "-video_size",
            f"{total_width}x{height}",
            "-framerate",
            "60",
            "-i",
            f"{x_display}+{left_x},{y}",
            "-q:v",
            "2",  # JPEG quality (2-31, lower = better)
            "-f",
            "mjpeg",
            "-",
        ]

        proc = None
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )

            # Buffer for accumulating data
            buffer = b""

            while proc.poll() is None:  # Check if process is still running
                # Read chunks from FFmpeg with timeout
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break

                buffer += chunk

                # Look for complete JPEG frames in buffer
                while True:
                    # Find JPEG start marker (FF D8)
                    start_idx = buffer.find(b"\xff\xd8")
                    if start_idx == -1:
                        # No start marker, keep last byte in case it's part of marker
                        buffer = buffer[-1:] if buffer else b""
                        break

                    # Find JPEG end marker (FF D9) after start
                    end_idx = buffer.find(b"\xff\xd9", start_idx + 2)
                    if end_idx == -1:
                        # No complete frame yet, keep from start marker onwards
                        buffer = buffer[start_idx:]
                        break

                    # Extract complete JPEG frame
                    frame_data = buffer[start_idx : end_idx + 2]
                    buffer = buffer[end_idx + 2 :]

                    # Yield as multipart MJPEG
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: "
                        + str(len(frame_data)).encode()
                        + b"\r\n\r\n"
                        + frame_data
                        + b"\r\n"
                    )

        finally:
            # Always cleanup FFmpeg process
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()  # Reap zombie

    return Response(
        generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    print("=" * 60)
    print("Protosuit Engine Web Interface")
    print("=" * 60)
    print("Browser connects directly to MQTT broker via WebSocket")
    print("MQTT WebSocket: ws://localhost:9001")
    print("=" * 60)

    # Run Flask app with config
    web_config = config_loader.get_web_config()
    app.run(host=web_config.host, port=web_config.port, debug=web_config.debug)

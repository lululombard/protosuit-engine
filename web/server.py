#!/usr/bin/env python3
"""
Web Interface for Protosuit Engine
Serves static web interface and provides display preview API.
Browser connects directly to MQTT broker via WebSocket.
"""

from flask import Flask, render_template, send_file, jsonify, Response
import os
import sys
import subprocess
import io
import glob

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


@app.route("/api/animations")
def api_animations():
    """Get available animations from config"""
    animations = []

    # Get all animations (base + overlay)
    all_anims = (
        config_loader.get_base_animations() + config_loader.get_overlay_animations()
    )

    for anim in all_anims:
        animation_data = {
            "id": anim["id"],
            "name": anim.get("name", anim["id"].capitalize()),
            "emoji": anim.get("emoji", ""),
            "rate": anim.get("rate", 60),
            "type": anim.get("type", "base"),
        }

        # Extract controllable uniforms for this animation
        uniforms = anim.get("uniforms", {})
        controllable_uniforms = []
        for uniform_name, uniform_config in uniforms.items():
            if isinstance(uniform_config, dict):
                if "type" in uniform_config:
                    # Simple uniform (both displays)
                    controllable_uniforms.append(
                        {
                            "name": uniform_name,
                            "type": uniform_config["type"],
                            "value": uniform_config.get("value"),
                            "min": uniform_config.get("min"),
                            "max": uniform_config.get("max"),
                            "step": uniform_config.get("step"),
                            "target": "both",
                        }
                    )
                elif "left" in uniform_config or "right" in uniform_config:
                    # Per-display uniform
                    left_config = uniform_config.get("left")
                    right_config = uniform_config.get("right")
                    if left_config and "type" in left_config:
                        controllable_uniforms.append(
                            {
                                "name": uniform_name,
                                "type": left_config["type"],
                                "value": {
                                    "left": left_config.get("value"),
                                    "right": (
                                        right_config.get("value")
                                        if right_config
                                        else left_config.get("value")
                                    ),
                                },
                                "min": left_config.get("min"),
                                "max": left_config.get("max"),
                                "step": left_config.get("step"),
                                "target": "per-display",
                            }
                        )

        if controllable_uniforms:
            animation_data["uniforms"] = controllable_uniforms

        animations.append(animation_data)
    return jsonify({"animations": animations})


@app.route("/api/base_animations")
def api_base_animations():
    """Get only base animations"""
    animations = []
    for anim in config_loader.get_base_animations():
        animations.append(
            {
                "id": anim["id"],
                "name": anim.get("name", anim["id"].capitalize()),
                "emoji": anim.get("emoji", ""),
                "type": "base",
            }
        )
    return jsonify({"animations": animations})


@app.route("/api/overlay_animations")
def api_overlay_animations():
    """Get only overlay animations"""
    animations = []
    for anim in config_loader.get_overlay_animations():
        animations.append(
            {
                "id": anim["id"],
                "name": anim.get("name", anim["id"].capitalize()),
                "emoji": anim.get("emoji", ""),
                "type": "overlay",
                "media": anim.get("media", ""),
                "duration": anim.get("duration"),
                "loop": anim.get("loop", False),
            }
        )
    return jsonify({"animations": animations})


@app.route("/api/media")
def api_media():
    """Get available media files"""
    try:
        # Get media config to find base path
        media_config = config_loader.get_media_config()
        base_path = media_config.base_path

        # Convert to absolute path
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        media_dir = os.path.join(project_root, base_path)

        # Supported media extensions
        extensions = [
            "*.mp4",
            "*.avi",
            "*.mov",
            "*.mkv",
            "*.webm",
            "*.gif",
            "*.png",
            "*.jpg",
            "*.jpeg",
            "*.mp3",
            "*.wav",
            "*.ogg",
        ]

        media_files = []
        for ext in extensions:
            pattern = os.path.join(media_dir, ext)
            files = glob.glob(pattern)
            for file_path in files:
                filename = os.path.basename(file_path)
                file_ext = os.path.splitext(filename)[1].lower()

                # Determine file type
                if file_ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
                    file_type = "video"
                elif file_ext == ".gif":
                    file_type = "gif"
                elif file_ext in [".mp3", ".wav", ".ogg"]:
                    file_type = "audio"
                else:
                    file_type = "image"

                media_files.append(
                    {
                        "name": filename,
                        "path": filename,
                        "type": file_type,
                        "extension": file_ext,
                    }
                )

        # Sort by name
        media_files.sort(key=lambda x: x["name"])

        return jsonify({"media": media_files})

    except Exception as e:
        print(f"Media API error: {e}")
        return jsonify({"error": str(e)}), 500


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

#!/usr/bin/env python3
"""
Web Interface for Protosuit Engine
Serves static web interface and provides WebRTC display preview.
Browser connects directly to MQTT broker via WebSocket.
"""

from flask import Flask, render_template, url_for
from flask_sock import Sock
import os
import sys

# Add parent directory to path to import config loader
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.loader import ConfigLoader
from web.webrtc_stream import WebRTCStream

app = Flask(__name__)
sock = Sock(app)

# Initialize config loader (still needed for display dimensions)
config_loader = ConfigLoader()


@app.context_processor
def cache_bust():
    """Override url_for to append file mtime to static URLs, busting browser caches."""

    def versioned_url_for(endpoint, **values):
        if endpoint == "static":
            filename = values.get("filename", "")
            filepath = os.path.join(app.static_folder, filename)
            try:
                values["v"] = int(os.stat(filepath).st_mtime)
            except OSError:
                pass
        return url_for(endpoint, **values)

    return dict(url_for=versioned_url_for)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/controller")
def controller():
    """Virtual controller interface for MQTT input"""
    return render_template("controller.html")


@app.route("/bluetooth")
def bluetooth():
    """Bluetooth controller management interface"""
    return render_template("bluetooth.html")


@app.route("/networking")
def networking():
    """Network settings management interface"""
    return render_template("networking.html")


@app.route("/cast")
def cast():
    """Cast settings management interface (AirPlay/Spotify)"""
    return render_template("cast.html")


@sock.route("/ws/preview")
def preview_ws(ws):
    """WebRTC signaling endpoint for live display preview."""
    display_config = config_loader.get_display_config()
    system_config = config_loader.get_system_config()

    stream = WebRTCStream(display_config, system_config)
    stream.start(ws)

    try:
        while True:
            raw = ws.receive(timeout=30)
            if raw is None:
                break
            stream.handle_message(raw)
    except Exception:
        pass
    finally:
        stream.stop()


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

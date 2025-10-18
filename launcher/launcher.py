"""
Launcher - Manages audio, video, and executable launching
Independent module with MQTT control
"""

import paho.mqtt.client as mqtt
import signal
import json
import os
import glob
from typing import Optional, Dict, List
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from launcher.launchers.audio_launcher import AudioLauncher
from launcher.launchers.video_launcher import VideoLauncher
from launcher.launchers.exec_launcher import ExecLauncher
from utils.mqtt_client import create_mqtt_client


class Launcher:
    """
    Protosuit Launcher - Audio, Video, and Executable Management

    Subscribes to:
        - protogen/fins/launcher/start/audio
        - protogen/fins/launcher/start/video
        - protogen/fins/launcher/start/exec
        - protogen/fins/launcher/stop/audio
        - protogen/fins/launcher/stop/video
        - protogen/fins/launcher/stop/exec
        - protogen/fins/launcher/kill/audio
        - protogen/fins/launcher/kill/video
        - protogen/fins/launcher/kill/exec
        - protogen/fins/launcher/config/reload

    Publishes:
        - protogen/fins/launcher/status/audio
        - protogen/fins/launcher/status/video
        - protogen/fins/launcher/status/exec
    """

    def __init__(self):
        """Initialize launcher"""
        self.running = True
        self.config_loader = ConfigLoader()

        # MQTT client
        self.mqtt_client: Optional[mqtt.Client] = None

        # Active launchers
        self.audio_launchers: List[AudioLauncher] = []  # Multiple audio can stack
        self.video_launcher: Optional[VideoLauncher] = None  # Only one video at a time
        self.exec_launcher: Optional[ExecLauncher] = None  # Only one exec at a time
        self.current_exec_name: Optional[str] = None  # Track current exec name

        # Available audio/video/executables
        self.available_audio: List[str] = []
        self.available_video: List[str] = []
        self.available_exec: List[str] = []

        # Base paths
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.audio_dir = os.path.join(project_root, "assets", "audio")
        self.video_dir = os.path.join(project_root, "assets", "video")
        self.exec_dir = os.path.join(project_root, "assets", "executables")

        print("[Launcher] Initialized")

    def init_mqtt(self):
        """Initialize MQTT connection and subscriptions"""
        print("[Launcher] Initializing MQTT...")

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                print("[Launcher] Connected to MQTT broker")
                # Subscribe to launcher topics
                client.subscribe("protogen/fins/launcher/start/audio")
                client.subscribe("protogen/fins/launcher/start/video")
                client.subscribe("protogen/fins/launcher/start/exec")
                client.subscribe("protogen/fins/launcher/stop/audio")
                client.subscribe("protogen/fins/launcher/stop/video")
                client.subscribe("protogen/fins/launcher/stop/exec")
                client.subscribe("protogen/fins/launcher/kill/audio")
                client.subscribe("protogen/fins/launcher/kill/video")
                client.subscribe("protogen/fins/launcher/kill/exec")
                client.subscribe("protogen/fins/launcher/config/reload")
                print("[Launcher] Subscribed to topics:")
                print("  - protogen/fins/launcher/start/*")
                print("  - protogen/fins/launcher/stop/*")
                print("  - protogen/fins/launcher/kill/*")
                print("  - protogen/fins/launcher/config/reload")
            else:
                print(f"[Launcher] Failed to connect to MQTT broker: {rc}")

        def on_message(client, userdata, msg):
            self.on_mqtt_message(msg.topic, msg.payload.decode())

        self.mqtt_client = create_mqtt_client(self.config_loader)
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_message = on_message
        self.mqtt_client.loop_start()

        # Scan for available files
        self.scan_files()

        # Publish initial status
        self.publish_audio_status()
        self.publish_video_status()
        self.publish_exec_status()

    def on_mqtt_message(self, topic: str, payload: str):
        """Handle incoming MQTT messages"""
        try:
            # Start commands
            if topic == "protogen/fins/launcher/start/audio":
                self.handle_start_audio(payload)
            elif topic == "protogen/fins/launcher/start/video":
                self.handle_start_video(payload)
            elif topic == "protogen/fins/launcher/start/exec":
                self.handle_start_exec(payload)

            # Stop commands (graceful)
            elif topic == "protogen/fins/launcher/stop/audio":
                self.handle_stop_audio(payload)
            elif topic == "protogen/fins/launcher/stop/video":
                self.handle_stop_video()
            elif topic == "protogen/fins/launcher/stop/exec":
                self.handle_stop_exec()

            # Kill commands (force)
            elif topic == "protogen/fins/launcher/kill/audio":
                self.handle_kill_audio(payload)
            elif topic == "protogen/fins/launcher/kill/video":
                self.handle_kill_video(payload)
            elif topic == "protogen/fins/launcher/kill/exec":
                self.handle_kill_exec(payload)

            # Config reload
            elif topic == "protogen/fins/launcher/config/reload":
                self.handle_config_reload()

        except Exception as e:
            print(f"[Launcher] Error handling message on {topic}: {e}")
            import traceback

            traceback.print_exc()

    def handle_start_audio(self, payload: str):
        """Start audio playback"""
        try:
            # Parse JSON if provided, otherwise treat as filename
            if payload.startswith("{"):
                data = json.loads(payload)
                filename = data.get("file")
            else:
                filename = payload

            print(f"[Launcher] Starting audio: {filename}")

            # Build full path
            audio_path = os.path.join(self.audio_dir, filename)

            # Get configs
            system_config = self.config_loader.get_system_config()

            # Create audio launcher
            launcher = AudioLauncher(
                audio_path, system_config, on_exit_callback=self._on_audio_exit
            )

            # Launch
            if launcher.launch():
                self.audio_launchers.append(launcher)
                print(f"[Launcher] Audio started: {filename}")
                self.publish_audio_status()
            else:
                print(f"[Launcher] Failed to start audio: {filename}")

        except Exception as e:
            print(f"[Launcher] Error starting audio: {e}")
            import traceback

            traceback.print_exc()

    def handle_start_video(self, payload: str):
        """Start video playback"""
        try:
            # Parse JSON if provided
            if payload.startswith("{"):
                data = json.loads(payload)
                filename = data.get("file")
            else:
                filename = payload

            print(f"[Launcher] Starting video: {filename}")

            # Stop existing video
            if self.video_launcher:
                print("[Launcher] Stopping existing video...")
                self.video_launcher.cleanup()
                self.video_launcher = None

            # Build full path
            video_path = os.path.join(self.video_dir, filename)

            # Get configs
            display_config = self.config_loader.get_display_config()
            system_config = self.config_loader.get_system_config()

            # Create video launcher
            launcher = VideoLauncher(
                video_path,
                display_config,
                system_config,
                on_exit_callback=self._on_video_exit,
            )

            # Launch
            if launcher.launch():
                self.video_launcher = launcher
                print(f"[Launcher] Video started: {filename}")
                self.publish_video_status()
            else:
                print(f"[Launcher] Failed to start video: {filename}")

        except Exception as e:
            print(f"[Launcher] Error starting video: {e}")
            import traceback

            traceback.print_exc()

    def handle_start_exec(self, payload: str):
        """Start executable"""
        try:
            # Parse JSON if provided
            if payload.startswith("{"):
                data = json.loads(payload)
                script_name = data.get("file")
            else:
                script_name = payload

            print(f"[Launcher] Starting executable: {script_name}")

            # Stop existing exec
            if self.exec_launcher:
                print("[Launcher] Stopping existing exec...")
                self.exec_launcher.cleanup()
                self.exec_launcher = None

            # Build full path to script
            script_path = os.path.join(self.exec_dir, script_name)
            if not script_name.endswith(".sh"):
                script_path += ".sh"

            # Check if script exists
            if not os.path.exists(script_path):
                print(f"[Launcher] Script not found: {script_path}")
                return

            # Get configs
            display_config = self.config_loader.get_display_config()
            system_config = self.config_loader.get_system_config()

            # Create generic exec launcher
            launcher = ExecLauncher(
                script_path,
                display_config,
                system_config,
                on_exit_callback=self._on_exec_exit,
            )

            if launcher.launch():
                self.exec_launcher = launcher
                self.current_exec_name = script_name.replace(".sh", "")
                print(f"[Launcher] Executable started: {script_name}")
                self.publish_exec_status()
            else:
                print(f"[Launcher] Failed to start executable: {script_name}")

        except Exception as e:
            print(f"[Launcher] Error starting exec: {e}")
            import traceback

            traceback.print_exc()

    def handle_stop_audio(self, payload: str):
        """Stop audio playback (graceful)"""
        if payload == "all":
            print("[Launcher] Stopping all audio...")
            for launcher in self.audio_launchers:
                launcher.cleanup()
            self.audio_launchers = []
        else:
            # Stop specific audio by filename (future enhancement)
            print(f"[Launcher] Stopping specific audio not yet implemented: {payload}")

        self.publish_audio_status()

    def handle_stop_video(self):
        """Stop video playback (graceful)"""
        if self.video_launcher:
            print("[Launcher] Stopping video...")
            self.video_launcher.cleanup()
            self.video_launcher = None
            self.publish_video_status()

    def handle_stop_exec(self):
        """Stop executable (graceful)"""
        if self.exec_launcher:
            print("[Launcher] Stopping executable...")
            self.exec_launcher.cleanup()
            self.exec_launcher = None
            self.publish_exec_status()

    def handle_kill_audio(self, payload: str):
        """Force kill audio playback"""
        # Same as stop for now (ffplay already terminates gracefully)
        self.handle_stop_audio(payload)

    def handle_kill_video(self, payload: str = ""):
        """Force kill video playback"""
        # Same as stop for now (mpv already terminates gracefully)
        self.handle_stop_video()

    def handle_kill_exec(self, payload: str = ""):
        """Force kill executable"""
        # Same as stop for now (doom launcher uses pkill -9)
        self.handle_stop_exec()

    def handle_config_reload(self):
        """Reload configuration"""
        print("[Launcher] Reloading configuration...")
        self.config_loader = ConfigLoader()
        self.scan_files()
        self.publish_audio_status()
        self.publish_video_status()
        self.publish_exec_status()

    def scan_files(self):
        """Scan for available audio, video, and executables"""
        try:
            # Audio extensions
            AUDIO_EXTENSIONS = {
                ".mp3",
                ".wav",
                ".ogg",
                ".flac",
                ".m4a",
                ".aac",
                ".wma",
                ".opus",
            }
            # Video extensions
            VIDEO_EXTENSIONS = {
                ".mp4",
                ".mkv",
                ".avi",
                ".webm",
                ".mov",
                ".flv",
                ".wmv",
                ".m4v",
                ".mpeg",
                ".mpg",
            }

            # Scan audio directory
            self.available_audio = []
            if os.path.exists(self.audio_dir):
                for ext in AUDIO_EXTENSIONS:
                    self.available_audio.extend(
                        [
                            os.path.basename(f)
                            for f in glob.glob(os.path.join(self.audio_dir, f"*{ext}"))
                        ]
                    )
            self.available_audio.sort()
            print(f"[Launcher] Found {len(self.available_audio)} audio files")

            # Scan video directory
            self.available_video = []
            if os.path.exists(self.video_dir):
                for ext in VIDEO_EXTENSIONS:
                    self.available_video.extend(
                        [
                            os.path.basename(f)
                            for f in glob.glob(os.path.join(self.video_dir, f"*{ext}"))
                        ]
                    )
            self.available_video.sort()
            print(f"[Launcher] Found {len(self.available_video)} video files")

            # Scan executables directory
            self.available_exec = []
            if os.path.exists(self.exec_dir):
                self.available_exec = [
                    os.path.basename(f)
                    for f in glob.glob(os.path.join(self.exec_dir, "*.sh"))
                ]
            self.available_exec.sort()
            print(f"[Launcher] Found {len(self.available_exec)} executables")

        except Exception as e:
            print(f"[Launcher] Error scanning files: {e}")

    def publish_audio_status(self):
        """Publish audio status to MQTT"""
        if not self.mqtt_client:
            return

        try:
            # Get list of currently playing audio files
            playing = []
            for launcher in self.audio_launchers:
                if launcher.is_running():
                    # Extract filename from full path
                    filename = os.path.basename(launcher.audio_path)
                    playing.append(filename)

            status = {"playing": playing, "available": self.available_audio}

            self.mqtt_client.publish(
                "protogen/fins/launcher/status/audio", json.dumps(status), retain=True
            )
        except Exception as e:
            print(f"[Launcher] Error publishing audio status: {e}")

    def publish_video_status(self):
        """Publish video status to MQTT"""
        if not self.mqtt_client:
            return

        try:
            playing = None
            if self.video_launcher and self.video_launcher.is_running():
                playing = os.path.basename(self.video_launcher.video_path)

            status = {"playing": playing, "available": self.available_video}

            self.mqtt_client.publish(
                "protogen/fins/launcher/status/video", json.dumps(status), retain=True
            )
        except Exception as e:
            print(f"[Launcher] Error publishing video status: {e}")

    def publish_exec_status(self):
        """Publish executable status to MQTT"""
        if not self.mqtt_client:
            return

        try:
            running = None
            pid = None
            if self.exec_launcher and self.exec_launcher.is_running():
                running = self.current_exec_name
                if self.exec_launcher.processes:
                    pid = self.exec_launcher.processes[0].pid

            status = {"running": running, "pid": pid, "available": self.available_exec}

            self.mqtt_client.publish(
                "protogen/fins/launcher/status/exec", json.dumps(status), retain=True
            )
        except Exception as e:
            print(f"[Launcher] Error publishing exec status: {e}")

    def _on_audio_exit(self):
        """Callback when audio exits"""
        print("[Launcher] Audio playback ended")
        # Remove dead launchers
        self.audio_launchers = [l for l in self.audio_launchers if l.is_running()]
        self.publish_audio_status()

    def _on_video_exit(self):
        """Callback when video exits"""
        print("[Launcher] Video playback ended")
        self.video_launcher = None
        self.publish_video_status()

    def _on_exec_exit(self):
        """Callback when executable exits"""
        print("[Launcher] Executable ended")
        self.exec_launcher = None
        self.current_exec_name = None
        self.publish_exec_status()

    def cleanup(self):
        """Clean up all resources"""
        print("[Launcher] Cleaning up...")

        # Stop all audio
        for launcher in self.audio_launchers:
            launcher.cleanup()
        self.audio_launchers = []

        # Stop video
        if self.video_launcher:
            self.video_launcher.cleanup()
            self.video_launcher = None

        # Stop exec
        if self.exec_launcher:
            self.exec_launcher.cleanup()
            self.exec_launcher = None

        # Stop MQTT
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

        print("[Launcher] Cleanup complete")

    def run(self):
        """Main run loop"""
        print("[Launcher] Starting launcher...")

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Initialize MQTT
        self.init_mqtt()

        print("[Launcher] Launcher is running. Press Ctrl+C to exit.")

        # Keep running
        try:
            while self.running:
                signal.pause()
        except KeyboardInterrupt:
            print("\n[Launcher] Keyboard interrupt received")

        self.cleanup()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n[Launcher] Received signal {signum}, shutting down...")
        self.running = False


def main():
    """Main entry point"""
    launcher = Launcher()
    launcher.run()


if __name__ == "__main__":
    main()

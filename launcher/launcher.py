"""
Launcher - Manages audio, video, and executable launching
Independent module with MQTT control
"""

import paho.mqtt.client as mqtt
import signal
import json
import os
import glob
import subprocess
import re
import threading
from typing import Optional, Dict, List
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from launcher.launchers.audio_launcher import AudioLauncher
from launcher.launchers.video_launcher import VideoLauncher
from launcher.launchers.exec_launcher import ExecLauncher
from launcher.audio_device_manager import AudioDeviceManager
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

        # Volume configuration
        launcher_config = self.config_loader.config.get("launcher", {})
        volume_config = launcher_config.get("volume", {})
        self.default_volume = volume_config.get("default", 50)
        self.volume_min = volume_config.get("min", 0)
        self.volume_max = volume_config.get("max", 100)

        # Audio device management
        self.audio_device_manager = AudioDeviceManager()
        audio_device_config = launcher_config.get("audio_device", {})
        self.auto_reconnect = audio_device_config.get("auto_reconnect", True)
        self.fallback_to_non_hdmi = audio_device_config.get("fallback_to_non_hdmi", True)
        self.exclude_hdmi = audio_device_config.get("exclude_hdmi", True)
        self.last_selected_device = None  # Will be restored from retained MQTT message
        self.bt_device_mac_to_sink = {}  # Map BT MAC addresses to sink names

        print("[Launcher] Initialized")
        
        # Ensure PulseAudio is running and set up audio correctly
        self._init_pulseaudio()

    def _init_pulseaudio(self):
        """Initialize PulseAudio and ensure default device isn't HDMI"""
        print("[Launcher] Setting up PulseAudio...")
        
        try:
            import time
            
            # Check if PulseAudio is already running
            check_result = subprocess.run(
                ["pactl", "info"],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if check_result.returncode == 0:
                print("[Launcher] ✓ PulseAudio is already running (keeping existing instance)")
                # Don't kill it - this preserves existing Bluetooth connections
            else:
                # Start PulseAudio if not running
                print("[Launcher] Starting PulseAudio...")
                result = subprocess.run(
                    ["pulseaudio", "--start"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0 or "already running" in result.stdout.lower():
                    print("[Launcher] ✓ PulseAudio started")
                else:
                    print(f"[Launcher] ⚠ PulseAudio start warning: {result.stderr}")
                
                # Wait for PulseAudio to initialize and load Bluetooth modules
                print("[Launcher] Waiting for PulseAudio to load Bluetooth modules...")
                time.sleep(3)  # Give PulseAudio time to discover Bluetooth devices
            
            # Check current default device
            current = self.audio_device_manager.get_current_device()
            if current:
                print(f"[Launcher] Current audio device: {current}")
                
                # If it's HDMI, switch to non-HDMI device
                if self.audio_device_manager.is_hdmi_device(current):
                    print("[Launcher] Default device is HDMI, switching to non-HDMI...")
                    fallback = self.audio_device_manager.get_non_hdmi_fallback()
                    if fallback:
                        if self.audio_device_manager.set_default_device(fallback):
                            print(f"[Launcher] ✓ Switched to {fallback}")
                        else:
                            print("[Launcher] ⚠ Failed to switch audio device")
                    else:
                        print("[Launcher] ⚠ No non-HDMI device found")
                else:
                    print(f"[Launcher] ✓ Default device is already non-HDMI: {current}")
            else:
                print("[Launcher] ⚠ Could not detect current audio device")
                
        except Exception as e:
            print(f"[Launcher] Error initializing PulseAudio: {e}")
            import traceback
            traceback.print_exc()

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
                client.subscribe("protogen/fins/launcher/input/exec")
                client.subscribe("protogen/fins/launcher/volume/set")
                
                # Audio device management
                client.subscribe("protogen/fins/launcher/audio/device/set")
                client.subscribe("protogen/fins/bluetoothbridge/status/audio_devices")
                client.subscribe("protogen/fins/launcher/status/audio_device/current")  # For restoring state
                
                print("[Launcher] Subscribed to topics:")
                print("  - protogen/fins/launcher/start/*")
                print("  - protogen/fins/launcher/stop/*")
                print("  - protogen/fins/launcher/kill/*")
                print("  - protogen/fins/launcher/config/reload")
                print("  - protogen/fins/launcher/input/exec")
                print("  - protogen/fins/launcher/volume/set")
                print("  - protogen/fins/launcher/audio/device/set")
                print("  - protogen/fins/bluetoothbridge/status/audio_devices")
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
        self.publish_volume_status()
        
        # Initialize audio device status
        self.publish_audio_devices_status()
        self.publish_current_audio_device()
        
        # Wait a moment for retained message about last audio device
        print("[Launcher] Waiting for retained audio device preference...")
        import time
        time.sleep(0.5)

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

            # Input handling for exec
            elif topic == "protogen/fins/launcher/input/exec":
                if self.exec_launcher:
                    self.exec_launcher.handle_input_message(payload)

            # Volume control
            elif topic == "protogen/fins/launcher/volume/set":
                self.handle_volume_set(payload)

            # Audio device management
            elif topic == "protogen/fins/launcher/audio/device/set":
                self.handle_audio_device_set(payload)
            elif topic == "protogen/fins/bluetoothbridge/status/audio_devices":
                self.handle_bt_audio_devices_update(payload)
            elif topic == "protogen/fins/launcher/status/audio_device/current":
                self._restore_audio_device_preference(payload)

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
                mqtt_client=self.mqtt_client,
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
        # Same as stop for now
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

    def get_current_volume(self) -> int:
        """Get current volume from PulseAudio/PipeWire"""
        try:
            # Get default sink volume
            result = subprocess.run(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                capture_output=True,
                text=True,
                timeout=2,
                env={**os.environ, 'XDG_RUNTIME_DIR': '/run/user/1000'}
            )

            if result.returncode == 0:
                # Parse output: "Volume: front-left: 49152 /  75% / -7.32 dB,   front-right: 49152 /  75% / -7.32 dB"
                match = re.search(r'/\s+(\d+)%', result.stdout)
                if match:
                    volume = int(match.group(1))
                    print(f"[Launcher] Current volume: {volume}%")
                    return volume

            print(f"[Launcher] Could not get current volume, using default: {self.default_volume}%")
            return self.default_volume

        except Exception as e:
            print(f"[Launcher] Error getting volume: {e}")
            return self.default_volume

    def set_volume(self, percentage: int):
        """Set volume using PulseAudio/PipeWire"""
        try:
            # Clamp volume to configured range
            percentage = max(self.volume_min, min(self.volume_max, percentage))

            # Set volume on default sink
            result = subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percentage}%"],
                capture_output=True,
                text=True,
                timeout=2,
                env={**os.environ, 'XDG_RUNTIME_DIR': '/run/user/1000'}
            )

            if result.returncode == 0:
                print(f"[Launcher] Volume set to {percentage}%")
                return True
            else:
                print(f"[Launcher] Failed to set volume: {result.stderr}")
                return False

        except Exception as e:
            print(f"[Launcher] Error setting volume: {e}")
            import traceback
            traceback.print_exc()
            return False

    def publish_volume_status(self):
        """Publish volume status to MQTT"""
        if not self.mqtt_client:
            return

        try:
            volume = self.get_current_volume()
            status = {
                "volume": volume,
                "min": self.volume_min,
                "max": self.volume_max
            }

            self.mqtt_client.publish(
                "protogen/fins/launcher/status/volume",
                json.dumps(status),
                retain=True
            )
            print(f"[Launcher] Published volume status: {volume}%")
        except Exception as e:
            print(f"[Launcher] Error publishing volume status: {e}")

    def handle_volume_set(self, payload: str):
        """Handle volume set command"""
        try:
            # Parse JSON payload
            if payload.startswith("{"):
                data = json.loads(payload)
                volume = data.get("volume")
            else:
                # Accept plain number as well
                volume = int(payload)

            if volume is not None:
                print(f"[Launcher] Setting volume to {volume}%")
                if self.set_volume(volume):
                    # Publish updated status
                    self.publish_volume_status()
            else:
                print("[Launcher] Invalid volume value in payload")

        except Exception as e:
            print(f"[Launcher] Error handling volume set: {e}")
            import traceback
            traceback.print_exc()

    def _set_default_volume_for_bt_device(self, sink_name: str):
        """Set volume to default when a BT audio device connects"""
        try:
            print(f"[Launcher] Setting BT device volume to {self.default_volume}%")
            result = subprocess.run(
                ["pactl", "set-sink-volume", sink_name, f"{self.default_volume}%"],
                capture_output=True,
                text=True,
                timeout=5,
                env={**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
            )
            if result.returncode == 0:
                print(f"[Launcher] ✓ BT device volume set to {self.default_volume}%")
                self.publish_volume_status()
            else:
                print(f"[Launcher] ⚠ Failed to set BT volume: {result.stderr}")
        except Exception as e:
            print(f"[Launcher] Error setting BT device volume: {e}")

    def handle_audio_device_set(self, payload: str):
        """Handle manual audio device selection"""
        try:
            data = json.loads(payload)
            device_name = data.get("device")
            
            if not device_name:
                print("[Launcher] No device specified in payload")
                return

            print(f"[Launcher] Manual audio device selection: {device_name}")
            
            if self.audio_device_manager.set_default_device(device_name):
                # Store as last selected
                self.last_selected_device = device_name
                
                # Publish updated status
                self.publish_current_audio_device()
                print(f"[Launcher] ✓ Audio output switched to {device_name}")
            else:
                print(f"[Launcher] Failed to switch audio device to {device_name}")

        except Exception as e:
            print(f"[Launcher] Error handling audio device set: {e}")
            import traceback
            traceback.print_exc()

    def handle_bt_audio_devices_update(self, payload: str):
        """Handle Bluetooth audio device connection changes from bluetoothbridge"""
        try:
            bt_audio_devices = json.loads(payload)
            
            # Check for devices that were removed (unpaired)
            current_macs = {d.get("mac") for d in bt_audio_devices}
            removed_macs = set(self.bt_device_mac_to_sink.keys()) - current_macs
            
            for mac in removed_macs:
                sink_name = self.bt_device_mac_to_sink.get(mac)
                current_device = self.audio_device_manager.get_current_device()
                print(f"[Launcher] BT audio device removed (unpaired): {mac}")
                
                # Check if this was the current device
                mac_normalized = mac.replace(":", "_").upper()
                was_current = (current_device == sink_name) or (current_device and mac_normalized in current_device.upper())
                
                if was_current and self.fallback_to_non_hdmi:
                    print("[Launcher] Current device was unpaired, falling back...")
                    # Exclude the unpaired device from fallback (PulseAudio may still show it briefly)
                    fallback = self.audio_device_manager.get_non_hdmi_fallback(exclude_mac=mac)
                    if fallback:
                        if self.audio_device_manager.set_default_device(fallback):
                            print(f"[Launcher] ✓ Fell back to {fallback}")
                    else:
                        print("[Launcher] ⚠ No fallback device available")
                
                del self.bt_device_mac_to_sink[mac]
                # Skip immediate publish - PulseAudio still shows old device
                self.publish_current_audio_device(exclude_mac=mac)
            
            # If devices were removed, publish status excluding them (PulseAudio may still show them)
            if removed_macs:
                self.publish_audio_devices_status(exclude_macs=removed_macs)
                # Schedule delayed refresh after PulseAudio catches up
                def delayed_refresh():
                    self.publish_audio_devices_status()
                    self.publish_current_audio_device()
                threading.Timer(3.0, delayed_refresh).start()
                return  # Skip the normal publish at the end
            
            # Update our tracking of BT device MAC -> sink mappings
            for device in bt_audio_devices:
                mac = device.get("mac")
                connected = device.get("connected", False)
                sink_name = None  # Initialize at the start of each loop iteration
                
                if connected:
                    # Wait a moment for PulseAudio to detect the device
                    import time
                    print(f"[Launcher] Waiting for PulseAudio to create Bluetooth sink...")
                    time.sleep(2)
                    
                    # Check and set A2DP profile for high-quality audio
                    current_profile = self.audio_device_manager.get_bluetooth_card_profile(mac)
                    if current_profile:
                        if "a2dp" not in current_profile.lower():
                            print(f"[Launcher] ⚠ BT device using low-quality profile: {current_profile}")
                            print(f"[Launcher] Switching to A2DP for better audio quality...")
                            self.audio_device_manager.set_bluetooth_profile_a2dp(mac)
                            # Wait for profile change and sink creation
                            time.sleep(2)
                        else:
                            print(f"[Launcher] ✓ BT device already using A2DP profile")
                    
                    # Device connected - find its sink with retries (longer waits)
                    sink_name = None
                    for attempt in range(5):  # More retries
                        sink_name = self.audio_device_manager.find_bluetooth_sink_by_mac(mac)
                        if sink_name:
                            break
                        if attempt < 4:  # Don't log on last attempt
                            print(f"[Launcher] Sink not found yet, retrying... (attempt {attempt + 1}/5)")
                            time.sleep(2)  # Longer wait between retries
                    
                    if sink_name:
                        self.bt_device_mac_to_sink[mac] = sink_name
                        print(f"[Launcher] BT audio device connected: {mac} -> {sink_name}")
                        
                        # Auto-reconnect logic: switch if this was the last selected device
                        if self.auto_reconnect and self.last_selected_device == sink_name:
                            print(f"[Launcher] Auto-reconnecting to last used BT speaker: {sink_name}")
                            self.audio_device_manager.set_default_device(sink_name)
                        
                        # Set volume to a reasonable default for BT speakers
                        self._set_default_volume_for_bt_device(sink_name)
                        
                        # Always publish current device - PulseAudio may have auto-switched
                        self.publish_current_audio_device()
                    else:
                        print(f"[Launcher] ⚠ Could not find PulseAudio sink for {mac} after 5 attempts")
                        print(f"[Launcher]   Scheduling delayed device list refresh...")
                        threading.Timer(5.0, self.publish_audio_devices_status).start()
                else:
                    # Device disconnected - fallback logic
                    current_device = self.audio_device_manager.get_current_device()
                    mac_normalized = mac.replace(":", "_").upper()
                    
                    # Check if we tracked this device or if current device contains its MAC
                    was_current = False
                    if mac in self.bt_device_mac_to_sink:
                        sink_name = self.bt_device_mac_to_sink[mac]
                        was_current = current_device == sink_name
                        print(f"[Launcher] BT audio device disconnected: {mac} ({sink_name})")
                        del self.bt_device_mac_to_sink[mac]
                    elif current_device and mac_normalized in current_device.upper():
                        was_current = True
                        print(f"[Launcher] BT audio device disconnected: {mac} (current: {current_device})")
                    else:
                        print(f"[Launcher] BT audio device disconnected: {mac}")
                    
                    # If we were using this device, fallback to non-HDMI
                    if was_current and self.fallback_to_non_hdmi:
                        print("[Launcher] Current device disconnected, falling back...")
                        fallback = self.audio_device_manager.get_non_hdmi_fallback()
                        if fallback:
                            if self.audio_device_manager.set_default_device(fallback):
                                print(f"[Launcher] ✓ Fell back to {fallback}")
                    
                    # Always publish updated current device after disconnect
                    self.publish_current_audio_device()
            
            # Always refresh device list after processing BT device changes
            self.publish_audio_devices_status()

        except Exception as e:
            print(f"[Launcher] Error handling BT audio device update: {e}")
            import traceback
            traceback.print_exc()

    def _restore_audio_device_preference(self, payload: str):
        """Restore last selected audio device from retained MQTT message"""
        try:
            if not payload:
                return
            
            data = json.loads(payload)
            device_name = data.get("device")
            
            if device_name:
                self.last_selected_device = device_name
                print(f"[Launcher] Restored audio device preference: {device_name}")

        except Exception as e:
            print(f"[Launcher] Error restoring audio device preference: {e}")

    def publish_audio_devices_status(self, exclude_macs: set = None):
        """Publish available audio output devices
        
        Args:
            exclude_macs: Optional set of MAC addresses to exclude (for recently unpaired devices)
        """
        if not self.mqtt_client:
            return

        try:
            devices = self.audio_device_manager.list_devices()
            
            # If we got no devices, PulseAudio might not be ready yet
            if not devices:
                print("[Launcher] ⚠ No audio devices found - PulseAudio may not be ready yet")
                return
            
            # Filter out HDMI devices if configured
            if self.exclude_hdmi:
                devices = [d for d in devices if not self.audio_device_manager.is_hdmi_device(d["name"])]
            
            # Filter out excluded MACs (recently unpaired devices that PulseAudio still shows)
            if exclude_macs:
                def should_exclude(device_name):
                    for mac in exclude_macs:
                        mac_pattern = mac.replace(":", "_").upper()
                        if mac_pattern in device_name.upper():
                            print(f"[Launcher] Excluding recently unpaired device: {device_name}")
                            return True
                    return False
                devices = [d for d in devices if not should_exclude(d["name"])]
            
            # Don't publish if filtering removed everything
            if not devices:
                print("[Launcher] ⚠ All devices filtered out (only HDMI found)")
                # Still publish empty list so web UI knows
            
            self.mqtt_client.publish(
                "protogen/fins/launcher/status/audio_devices",
                json.dumps(devices),
                retain=True
            )
            print(f"[Launcher] Published {len(devices)} audio devices")

        except Exception as e:
            print(f"[Launcher] Error publishing audio devices: {e}")

    def publish_current_audio_device(self, exclude_mac: str = None):
        """Publish current audio output device
        
        Args:
            exclude_mac: Optional MAC to exclude (for recently unpaired devices)
        """
        if not self.mqtt_client:
            return

        try:
            current_sink = self.audio_device_manager.get_current_device()
            
            # Check if current device matches excluded MAC (recently unpaired)
            if exclude_mac and current_sink:
                mac_pattern = exclude_mac.replace(":", "_").upper()
                if mac_pattern in current_sink.upper():
                    print(f"[Launcher] Current device {current_sink} was just unpaired, skipping publish")
                    return
            
            if current_sink:
                device_info = self.audio_device_manager.get_device_info(current_sink)
                
                status = {
                    "device": current_sink,
                    "description": device_info["description"] if device_info else current_sink,
                    "type": device_info["type"] if device_info else "unknown"
                }
                
                self.mqtt_client.publish(
                    "protogen/fins/launcher/status/audio_device/current",
                    json.dumps(status),
                    retain=True
                )
                print(f"[Launcher] Published current audio device: {current_sink}")

        except Exception as e:
            print(f"[Launcher] Error publishing current audio device: {e}")

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

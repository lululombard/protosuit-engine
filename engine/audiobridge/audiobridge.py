"""
AudioBridge - Audio Device and Volume Management Service
Manages PulseAudio sinks, volume control, BT audio tracking, and device switching via MQTT.
"""

import paho.mqtt.client as mqtt
import pulsectl
import signal
import json
import subprocess
import threading
import time
import os
import sys
from typing import Optional, Dict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from utils.mqtt_client import create_mqtt_client
from utils.notifications import publish_notification
from audiobridge.audio_device_manager import AudioDeviceManager


class AudioBridge:
    """
    Audio Device and Volume Management Service

    Subscribes to:
        - protogen/fins/bluetoothbridge/status/audio_devices
        - protogen/fins/audiobridge/volume/set
        - protogen/fins/audiobridge/audio/device/set
        - protogen/fins/audiobridge/status/audio_device/current  (retained restore)

    Publishes:
        - protogen/fins/audiobridge/status/volume
        - protogen/fins/audiobridge/status/audio_devices
        - protogen/fins/audiobridge/status/audio_device/current
        - protogen/global/notifications
    """

    def __init__(self):
        self.running = True
        self.config_loader = ConfigLoader()

        # MQTT client
        self.mqtt_client: Optional[mqtt.Client] = None

        # Audio device manager (pactl wrapper)
        self.audio_device_manager = AudioDeviceManager()

        # Config
        audio_config = self.config_loader.config.get("audiobridge", {})
        volume_config = audio_config.get("volume", {})
        self.default_volume = volume_config.get("default", 50)
        self.volume_min = volume_config.get("min", 0)
        self.volume_max = volume_config.get("max", 100)

        device_config = audio_config.get("audio_device", {})
        self.auto_reconnect = device_config.get("auto_reconnect", True)
        self.fallback_to_non_hdmi = device_config.get("fallback_to_non_hdmi", True)
        self.exclude_hdmi = device_config.get("exclude_hdmi", True)

        # State
        self.last_selected_device: Optional[str] = None  # Restored from retained MQTT
        self.bt_device_mac_to_sink: Dict[str, str] = {}  # BT MAC → sink name
        self._last_published_volume: Optional[int] = None  # Dedup external changes

        print("[AudioBridge] Initialized")

    # ======== PulseAudio Init ========

    def _wait_for_audio_system_ready(self, max_seconds: int = 30) -> bool:
        """Wait for PulseAudio to be ready."""
        for attempt in range(max_seconds):
            try:
                result = subprocess.run(
                    ["pactl", "info"],
                    capture_output=True,
                    timeout=2,
                    env={**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
                )
                if result.returncode == 0 and b"Server Name:" in result.stdout:
                    if attempt > 0:
                        print(f"[AudioBridge] Audio system ready after {attempt + 1}s")
                    return True
            except Exception:
                pass
            time.sleep(1)
        print(f"[AudioBridge] Audio system not ready after {max_seconds}s")
        return False

    def _reload_pulseaudio_bluetooth(self) -> bool:
        """Reload PulseAudio Bluetooth module to fix profile issues."""
        print("[AudioBridge] Reloading PulseAudio Bluetooth module...")
        try:
            env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
            subprocess.run(["pactl", "unload-module", "module-bluetooth-discover"],
                           capture_output=True, timeout=5, env=env)
            time.sleep(1)
            result = subprocess.run(["pactl", "load-module", "module-bluetooth-discover"],
                                    capture_output=True, timeout=5, env=env)
            if result.returncode == 0:
                print("[AudioBridge] PulseAudio Bluetooth module reloaded")
                time.sleep(2)
                return True
            else:
                print(f"[AudioBridge] Failed to reload module: {result.stderr.decode()}")
                return False
        except Exception as e:
            print(f"[AudioBridge] Error reloading PulseAudio module: {e}")
            return False

    def _init_pulseaudio(self):
        """Initialize PulseAudio and ensure default device isn't HDMI."""
        print("[AudioBridge] Setting up PulseAudio...")
        try:
            check_result = subprocess.run(
                ["pactl", "info"],
                capture_output=True, text=True, timeout=2
            )

            if check_result.returncode == 0:
                print("[AudioBridge] PulseAudio is running")
            else:
                print("[AudioBridge] Starting PulseAudio...")
                subprocess.run(["pulseaudio", "--start"],
                               capture_output=True, text=True, timeout=5)
                time.sleep(3)

            # If default is HDMI, switch to non-HDMI
            current = self.audio_device_manager.get_current_device()
            if current:
                if self.audio_device_manager.is_hdmi_device(current):
                    print("[AudioBridge] Default device is HDMI, switching...")
                    fallback = self.audio_device_manager.get_non_hdmi_fallback()
                    if fallback:
                        self.audio_device_manager.set_default_device(fallback)
                        print(f"[AudioBridge] Switched to {fallback}")
                else:
                    print(f"[AudioBridge] Default device: {current}")

        except Exception as e:
            print(f"[AudioBridge] Error initializing PulseAudio: {e}")

    # ======== MQTT ========

    def init_mqtt(self):
        """Initialize MQTT connection and subscriptions."""
        print("[AudioBridge] Initializing MQTT...")

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                print("[AudioBridge] Connected to MQTT broker")
                # BT audio device updates from bluetoothbridge
                client.subscribe("protogen/fins/bluetoothbridge/status/audio_devices")
                # Volume control
                client.subscribe("protogen/fins/audiobridge/volume/set")
                # Audio device selection
                client.subscribe("protogen/fins/audiobridge/audio/device/set")
                # Restore last selected device from retained message
                client.subscribe("protogen/fins/audiobridge/status/audio_device/current")
                # Config reload
                client.subscribe("protogen/fins/config/reload")
                client.subscribe("protogen/fins/audiobridge/config/reload")
            else:
                print(f"[AudioBridge] Failed to connect to MQTT: {rc}")

        def on_message(client, userdata, msg):
            self.on_mqtt_message(msg.topic, msg.payload.decode())

        self.mqtt_client = create_mqtt_client(self.config_loader)
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_message = on_message
        self.mqtt_client.loop_start()

        # Publish initial status
        self.publish_volume_status()
        self.publish_audio_devices_status()
        self.publish_current_audio_device()

        # Wait briefly for retained messages
        time.sleep(0.5)

    def on_mqtt_message(self, topic: str, payload: str):
        """Handle incoming MQTT messages."""
        try:
            if topic == "protogen/fins/audiobridge/volume/set":
                self.handle_volume_set(payload)
            elif topic == "protogen/fins/audiobridge/audio/device/set":
                self.handle_audio_device_set(payload)
            elif topic == "protogen/fins/bluetoothbridge/status/audio_devices":
                self.handle_bt_audio_devices_update(payload)
            elif topic == "protogen/fins/audiobridge/status/audio_device/current":
                self._restore_audio_device_preference(payload)
            elif topic in ("protogen/fins/config/reload", "protogen/fins/audiobridge/config/reload"):
                self.handle_config_reload()
        except Exception as e:
            print(f"[AudioBridge] Error handling {topic}: {e}")
            import traceback
            traceback.print_exc()

    def handle_config_reload(self):
        """Reload configuration from file."""
        print("[AudioBridge] Reloading configuration...")
        self.config_loader.reload()
        audio_config = self.config_loader.config.get("audiobridge", {})
        volume_config = audio_config.get("volume", {})
        self.default_volume = volume_config.get("default", 50)
        self.volume_min = volume_config.get("min", 0)
        self.volume_max = volume_config.get("max", 100)
        device_config = audio_config.get("audio_device", {})
        self.auto_reconnect = device_config.get("auto_reconnect", True)
        self.fallback_to_non_hdmi = device_config.get("fallback_to_non_hdmi", True)
        self.exclude_hdmi = device_config.get("exclude_hdmi", True)
        print("[AudioBridge] Configuration reloaded")

    # ======== Volume Control ========

    def get_current_volume(self) -> int:
        """Get current volume from PulseAudio."""
        vol = self.audio_device_manager.get_current_volume()
        if vol is not None:
            return vol
        print(f"[AudioBridge] Could not read volume, using default: {self.default_volume}%")
        return self.default_volume

    def set_volume(self, percentage: int) -> bool:
        """Set volume, clamped to configured range."""
        percentage = max(self.volume_min, min(self.volume_max, percentage))
        if self.audio_device_manager.set_volume(percentage):
            print(f"[AudioBridge] Volume set to {percentage}%")
            return True
        print(f"[AudioBridge] Failed to set volume to {percentage}%")
        return False

    def publish_volume_status(self):
        """Publish current volume status to MQTT."""
        if not self.mqtt_client:
            return
        try:
            volume = self.get_current_volume()
            self._last_published_volume = volume
            status = {
                "volume": volume,
                "min": self.volume_min,
                "max": self.volume_max,
            }
            self.mqtt_client.publish(
                "protogen/fins/audiobridge/status/volume",
                json.dumps(status),
                retain=True,
            )
        except Exception as e:
            print(f"[AudioBridge] Error publishing volume: {e}")

    def handle_volume_set(self, payload: str):
        """Handle volume set command from MQTT."""
        try:
            if payload.startswith("{"):
                data = json.loads(payload)
                volume = data.get("volume")
            else:
                volume = int(payload)

            if volume is not None:
                if self.set_volume(volume):
                    self.publish_volume_status()
        except Exception as e:
            print(f"[AudioBridge] Error handling volume set: {e}")

    # ======== PulseAudio Event Monitor ========

    def _start_volume_monitor(self):
        """Start background thread monitoring PulseAudio for external volume changes."""
        thread = threading.Thread(target=self._volume_monitor_loop, daemon=True)
        thread.start()

    def _volume_monitor_loop(self):
        """Listen for PulseAudio sink change events and republish volume."""
        while self.running:
            try:
                with pulsectl.Pulse('audiobridge-monitor') as pulse:
                    pulse.event_mask_set('sink')
                    pulse.event_callback_set(self._on_pulse_event)
                    while self.running:
                        pulse.event_listen(timeout=1)
            except Exception as e:
                print(f"[AudioBridge] Volume monitor error: {e}, restarting in 3s...")
                time.sleep(3)

    def _on_pulse_event(self, ev):
        """Handle PulseAudio sink events — republish if volume changed externally."""
        if ev.t == 'change':
            volume = self.get_current_volume()
            if volume != self._last_published_volume:
                self.publish_volume_status()
        # Keep listening
        raise pulsectl.PulseLoopStop

    # ======== Audio Device Selection ========

    def handle_audio_device_set(self, payload: str):
        """Handle manual audio device selection from web UI."""
        try:
            data = json.loads(payload)
            device_name = data.get("device")
            if not device_name:
                return

            print(f"[AudioBridge] Manual device selection: {device_name}")
            if self.audio_device_manager.set_default_device(device_name):
                self.last_selected_device = device_name
                self.publish_current_audio_device()
                print(f"[AudioBridge] Audio output switched to {device_name}")
        except Exception as e:
            print(f"[AudioBridge] Error handling device set: {e}")

    def _restore_audio_device_preference(self, payload: str):
        """Restore last selected audio device from retained MQTT message."""
        try:
            if not payload:
                return
            data = json.loads(payload)
            device_name = data.get("device")
            if device_name:
                self.last_selected_device = device_name
                print(f"[AudioBridge] Restored audio device preference: {device_name}")
        except Exception as e:
            print(f"[AudioBridge] Error restoring device preference: {e}")

    # ======== BT Audio Device Tracking ========

    def handle_bt_audio_devices_update(self, payload: str):
        """Handle Bluetooth audio device changes from bluetoothbridge."""
        try:
            bt_audio_devices = json.loads(payload)

            # Check for devices that were removed (unpaired)
            current_macs = {d.get("mac") for d in bt_audio_devices}
            removed_macs = set(self.bt_device_mac_to_sink.keys()) - current_macs

            for mac in removed_macs:
                sink_name = self.bt_device_mac_to_sink.get(mac)
                current_device = self.audio_device_manager.get_current_device()
                print(f"[AudioBridge] BT audio device removed (unpaired): {mac}")

                mac_normalized = mac.replace(":", "_").upper()
                was_current = (current_device == sink_name) or \
                              (current_device and mac_normalized in current_device.upper())

                if was_current and self.fallback_to_non_hdmi:
                    print("[AudioBridge] Current device was unpaired, falling back...")
                    fallback = self.audio_device_manager.get_non_hdmi_fallback(exclude_mac=mac)
                    if fallback:
                        if self.audio_device_manager.set_default_device(fallback):
                            print(f"[AudioBridge] Fell back to {fallback}")

                del self.bt_device_mac_to_sink[mac]
                self.publish_current_audio_device(exclude_mac=mac)

                publish_notification(self.mqtt_client, "audio", "disconnected", "speaker",
                                     f"Speaker removed: {mac}")

            if removed_macs:
                self.publish_audio_devices_status(exclude_macs=removed_macs)

                def delayed_refresh():
                    self.publish_audio_devices_status()
                    self.publish_current_audio_device()
                threading.Timer(3.0, delayed_refresh).start()
                return

            # Process connected/disconnected devices
            for device in bt_audio_devices:
                mac = device.get("mac")
                name = device.get("name", mac)
                connected = device.get("connected", False)

                if connected:
                    self._handle_bt_device_connected(mac, name)
                else:
                    self._handle_bt_device_disconnected(mac, name)

            # Refresh device list
            self.publish_audio_devices_status()

        except Exception as e:
            print(f"[AudioBridge] Error handling BT audio update: {e}")
            import traceback
            traceback.print_exc()

    def _handle_bt_device_connected(self, mac: str, name: str):
        """Handle a BT audio device connecting."""
        print(f"[AudioBridge] BT audio device connected: {name} ({mac})")

        # Wait for PulseAudio to detect the device
        time.sleep(2)

        # Ensure A2DP profile for high-quality audio
        current_profile = self.audio_device_manager.get_bluetooth_card_profile(mac)
        if current_profile and "a2dp" not in current_profile.lower():
            print(f"[AudioBridge] Switching {name} to A2DP profile...")
            self.audio_device_manager.set_bluetooth_profile_a2dp(mac)
            time.sleep(2)

        # Find the PulseAudio sink with retries
        sink_name = None
        for attempt in range(5):
            sink_name = self.audio_device_manager.find_bluetooth_sink_by_mac(mac)
            if sink_name:
                break
            if attempt < 4:
                print(f"[AudioBridge] Sink not found yet, retrying... ({attempt + 1}/5)")
                time.sleep(2)

        if sink_name:
            self.bt_device_mac_to_sink[mac] = sink_name
            print(f"[AudioBridge] BT sink mapped: {mac} -> {sink_name}")

            # Auto-reconnect: switch if this was the last used device
            if self.auto_reconnect and self.last_selected_device == sink_name:
                print(f"[AudioBridge] Auto-reconnecting to last used speaker: {sink_name}")
                self.audio_device_manager.set_default_device(sink_name)

            # Read and publish current volume (don't force to default)
            self.publish_volume_status()
            self.publish_current_audio_device()

            publish_notification(self.mqtt_client, "audio", "connected", "speaker",
                                 f"Speaker connected: {name}")
        else:
            print(f"[AudioBridge] Could not find sink for {mac} after 5 attempts")
            threading.Timer(5.0, self.publish_audio_devices_status).start()

    def _handle_bt_device_disconnected(self, mac: str, name: str):
        """Handle a BT audio device disconnecting."""
        current_device = self.audio_device_manager.get_current_device()
        mac_normalized = mac.replace(":", "_").upper()

        was_current = False
        if mac in self.bt_device_mac_to_sink:
            sink_name = self.bt_device_mac_to_sink[mac]
            was_current = current_device == sink_name
            print(f"[AudioBridge] BT audio device disconnected: {name} ({sink_name})")
            del self.bt_device_mac_to_sink[mac]
        elif current_device and mac_normalized in current_device.upper():
            was_current = True
            print(f"[AudioBridge] BT audio device disconnected: {name} (current: {current_device})")
        else:
            print(f"[AudioBridge] BT audio device disconnected: {name}")

        # Fallback to non-HDMI if we were using this device
        if was_current and self.fallback_to_non_hdmi:
            print("[AudioBridge] Current device disconnected, falling back...")
            fallback = self.audio_device_manager.get_non_hdmi_fallback()
            if fallback:
                if self.audio_device_manager.set_default_device(fallback):
                    print(f"[AudioBridge] Fell back to {fallback}")

        self.publish_current_audio_device()

        publish_notification(self.mqtt_client, "audio", "disconnected", "speaker",
                             f"Speaker disconnected: {name}")

    # ======== Status Publishing ========

    def publish_audio_devices_status(self, exclude_macs: set = None):
        """Publish available audio output devices."""
        if not self.mqtt_client:
            return
        try:
            devices = self.audio_device_manager.list_devices()
            if not devices:
                print("[AudioBridge] No audio devices found")

            # Filter HDMI if configured
            if self.exclude_hdmi:
                devices = [d for d in devices if not self.audio_device_manager.is_hdmi_device(d["name"])]

            # Filter recently unpaired devices
            if exclude_macs:
                def should_exclude(device_name):
                    for mac in exclude_macs:
                        mac_pattern = mac.replace(":", "_").upper()
                        if mac_pattern in device_name.upper():
                            return True
                    return False
                devices = [d for d in devices if not should_exclude(d["name"])]

            self.mqtt_client.publish(
                "protogen/fins/audiobridge/status/audio_devices",
                json.dumps(devices),
                retain=True,
            )
            print(f"[AudioBridge] Published {len(devices)} audio devices")

        except Exception as e:
            print(f"[AudioBridge] Error publishing audio devices: {e}")

    def publish_current_audio_device(self, exclude_mac: str = None):
        """Publish current audio output device."""
        if not self.mqtt_client:
            return
        try:
            current_sink = self.audio_device_manager.get_current_device()

            # Skip if current device was just unpaired
            if exclude_mac and current_sink:
                mac_pattern = exclude_mac.replace(":", "_").upper()
                if mac_pattern in current_sink.upper():
                    return

            if current_sink:
                device_info = self.audio_device_manager.get_device_info(current_sink)
                status = {
                    "device": current_sink,
                    "description": device_info["description"] if device_info else current_sink,
                    "type": device_info["type"] if device_info else "unknown",
                }
                self.mqtt_client.publish(
                    "protogen/fins/audiobridge/status/audio_device/current",
                    json.dumps(status),
                    retain=True,
                )

        except Exception as e:
            print(f"[AudioBridge] Error publishing current device: {e}")

    # ======== Lifecycle ========

    def cleanup(self):
        """Clean up resources."""
        print("[AudioBridge] Cleaning up...")
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

    def run(self):
        """Main run loop."""
        print("[AudioBridge] Starting...")

        # Wait for PulseAudio
        self._wait_for_audio_system_ready()
        self._init_pulseaudio()

        # Initialize MQTT
        self.init_mqtt()

        # Monitor PulseAudio for external volume changes (BT speaker buttons, etc.)
        self._start_volume_monitor()

        print("[AudioBridge] Running. Press Ctrl+C to stop.")

        # Wait for shutdown signal
        while self.running:
            time.sleep(1)

        self.cleanup()
        print("[AudioBridge] Stopped.")

    def _signal_handler(self, signum, frame):
        print(f"\n[AudioBridge] Received signal {signum}, shutting down...")
        self.running = False


def main():
    bridge = AudioBridge()
    signal.signal(signal.SIGINT, bridge._signal_handler)
    signal.signal(signal.SIGTERM, bridge._signal_handler)
    bridge.run()


if __name__ == "__main__":
    main()

"""
Bluetoothbridge - Bluetooth Gamepad Management Service
Manages Bluetooth gamepad connections and forwards inputs to launcher via MQTT
"""

import paho.mqtt.client as mqtt
import signal
import json
import subprocess
import threading
import time
import re
import sys
import os
from typing import Optional, Dict, List
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from utils.mqtt_client import create_mqtt_client

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError as e:
    EVDEV_AVAILABLE = False
    print(f"[BluetoothBridge] Warning: evdev not available: {e}")
    print("[BluetoothBridge] Install with: pip install evdev")
except Exception as e:
    EVDEV_AVAILABLE = False
    print(f"[BluetoothBridge] Error loading evdev: {e}")
    print("[BluetoothBridge] You may need to install system dependencies: sudo apt install python3-evdev")


class BluetoothBridge:
    """
    Bluetooth Gamepad Management Service

    Subscribes to:
        - protogen/fins/bluetoothbridge/scan/start
        - protogen/fins/bluetoothbridge/scan/stop
        - protogen/fins/bluetoothbridge/connect
        - protogen/fins/bluetoothbridge/disconnect
        - protogen/fins/bluetoothbridge/assign

    Publishes:
        - protogen/fins/bluetoothbridge/status/scanning
        - protogen/fins/bluetoothbridge/status/devices
        - protogen/fins/bluetoothbridge/status/assignments
        - protogen/fins/launcher/input/exec (gamepad inputs)
    """

    def __init__(self):
        """Initialize bluetooth bridge"""
        self.config_loader = ConfigLoader()
        self.mqtt_client = None
        self.running = False
        self.startup_complete = False  # Track if initial startup is complete

        # Bluetooth state
        self.scanning = False
        self.scan_process = None
        self.scan_thread = None
        self.monitor_process = None
        self.monitor_thread = None

        # Device tracking
        self.discovered_devices: Dict[str, Dict] = {}  # {mac: {name, paired, connected}}
        self.connected_devices: Dict[str, Dict] = {}   # {mac: {name, evdev_path, device}}
        self.assignments: Dict[str, Optional[str]] = {"left": None, "right": None}  # {display: mac}

        # Audio device tracking (Bluetooth speakers, headphones, etc.)
        self.audio_devices: Dict[str, Dict] = {}  # {mac: {name, paired, connected, type}}
        self.last_audio_device_to_restore: Optional[Dict] = None  # Stored from retained message

        # Input reading threads
        self.input_threads: Dict[str, threading.Thread] = {}  # {mac: thread}
        self.input_stop_events: Dict[str, threading.Event] = {}  # {mac: stop_event}

        # Button mapping configuration
        self.button_mapping = self._load_button_mapping()

        # Bluetooth adapter configuration
        self.gamepad_adapter, self.audio_adapter = self._load_adapter_config()

        print("[BluetoothBridge] Initialized")
        print(f"[BluetoothBridge] Gamepad adapter: {self.gamepad_adapter}")
        print(f"[BluetoothBridge] Audio adapter: {self.audio_adapter}")

    def _load_button_mapping(self) -> Dict:
        """Load button mapping from config"""
        try:
            config = self.config_loader.config
            if 'bluetoothbridge' in config and 'button_mapping' in config['bluetoothbridge']:
                return config['bluetoothbridge']['button_mapping']
        except Exception as e:
            print(f"[BluetoothBridge] Error loading button mapping: {e}")

        # Default mapping
        return {
            "BTN_SOUTH": "a",      # A button (PlayStation X, Xbox A)
            "BTN_EAST": "b",       # B button (PlayStation Circle, Xbox B)
            "ABS_HAT0X": "dpad_x", # D-pad X axis
            "ABS_HAT0Y": "dpad_y"  # D-pad Y axis
        }

    def _load_adapter_config(self) -> tuple:
        """Load Bluetooth adapter configuration from config

        Returns:
            (gamepad_adapter, audio_adapter) - adapter names like "hci0", "hci1"
        """
        try:
            config = self.config_loader.config
            if 'bluetoothbridge' in config and 'adapters' in config['bluetoothbridge']:
                adapters = config['bluetoothbridge']['adapters']
                gamepad_adapter = adapters.get('gamepads', 'hci0')
                audio_adapter = adapters.get('audio', 'hci1')
                return gamepad_adapter, audio_adapter
        except Exception as e:
            print(f"[BluetoothBridge] Error loading adapter config: {e}")

        # Default: gamepads on built-in (hci0), audio on USB dongle (hci1)
        return 'hci0', 'hci1'

    def _get_adapter_for_device(self, mac: str) -> str:
        """Get the appropriate Bluetooth adapter for a device based on its type

        Args:
            mac: Device MAC address

        Returns:
            Adapter name (e.g., "hci0", "hci1")
        """
        # Check if it's an audio device
        if mac in self.audio_devices:
            return self.audio_adapter

        # Check if it's a gamepad
        if mac in self.discovered_devices:
            return self.gamepad_adapter

        # Default to gamepad adapter for unknown devices
        return self.gamepad_adapter

    def _get_adapter_mac(self, adapter_name: str) -> Optional[str]:
        """Get the MAC address of a Bluetooth adapter

        Args:
            adapter_name: Adapter name (e.g., "hci0", "hci1")

        Returns:
            Adapter MAC address or None if not found
        """
        try:
            # Use hciconfig to get the adapter's MAC address
            result = subprocess.run(
                ["hciconfig", adapter_name],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                print(f"[BluetoothBridge] ⚠ Adapter {adapter_name} not found")
                return None

            # Parse output for "BD Address: XX:XX:XX:XX:XX:XX"
            for line in result.stdout.splitlines():
                if "BD Address:" in line:
                    match = re.search(r'BD Address:\s+([0-9A-F:]+)', line, re.IGNORECASE)
                    if match:
                        mac = match.group(1)
                        print(f"[BluetoothBridge] ✓ {adapter_name} MAC: {mac}")
                        return mac

            print(f"[BluetoothBridge] ⚠ Could not parse MAC for adapter {adapter_name}")
            return None

        except Exception as e:
            print(f"[BluetoothBridge] Error getting adapter MAC: {e}")
            return None

    def init_mqtt(self):
        """Initialize MQTT connection and subscriptions"""
        self.mqtt_client = create_mqtt_client(self.config_loader)

        def on_connect(client, userdata, flags, rc, properties=None):
            print(f"[BluetoothBridge] Connected to MQTT broker (rc: {rc})")

            # Subscribe to control topics
            topics = [
                "protogen/fins/bluetoothbridge/scan/start",
                "protogen/fins/bluetoothbridge/scan/stop",
                "protogen/fins/bluetoothbridge/connect",
                "protogen/fins/bluetoothbridge/disconnect",
                "protogen/fins/bluetoothbridge/unpair",
                "protogen/fins/bluetoothbridge/assign",
                "protogen/fins/bluetoothbridge/bluetooth/restart",
                "protogen/fins/bluetoothbridge/status/assignments",  # Subscribe to our own status to restore
                "protogen/fins/bluetoothbridge/status/last_audio_device",  # Subscribe to restore last audio device
            ]

            for topic in topics:
                client.subscribe(topic)
                print(f"[BluetoothBridge] Subscribed to {topic}")

        def on_message(client, userdata, msg):
            topic = msg.topic
            payload = msg.payload.decode("utf-8") if msg.payload else ""
            self.on_mqtt_message(topic, payload)

        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_message = on_message
        self.mqtt_client.loop_start()

        # Wait for MQTT connection and retained message
        print("[BluetoothBridge] Waiting for MQTT connection...")
        time.sleep(1.5)

        # Load already-paired devices on startup (this will detect them but NOT start input reading yet)
        print("[BluetoothBridge] Loading paired devices...")
        self._update_paired_devices(start_input_threads=False)

        # Wait a bit more for retained assignments message to be processed
        print("[BluetoothBridge] Waiting for retained assignments...")
        time.sleep(0.5)

        # NOW start input reading with correct assignments
        print("[BluetoothBridge] Starting input reading threads...")
        print(f"[BluetoothBridge] Current assignments: {self.assignments}")
        for mac in list(self.connected_devices.keys()):
            self._start_input_reading(mac)

        # Mark startup as complete
        self.startup_complete = True

        # Start monitoring for automatic controller connections/disconnections
        self._start_monitor()

        # Publish initial status (will include restored assignments if any)
        print("[BluetoothBridge] Publishing initial status...")
        self.publish_all_status()

    def on_mqtt_message(self, topic: str, payload: str):
        """Handle incoming MQTT messages"""
        try:
            if topic == "protogen/fins/bluetoothbridge/scan/start":
                self.start_scan()
            elif topic == "protogen/fins/bluetoothbridge/scan/stop":
                self.stop_scan()
            elif topic == "protogen/fins/bluetoothbridge/connect":
                data = json.loads(payload)
                mac = data.get("mac")
                if mac:
                    self.connect_device(mac)
            elif topic == "protogen/fins/bluetoothbridge/disconnect":
                data = json.loads(payload)
                mac = data.get("mac")
                if mac:
                    self.disconnect_device(mac)
            elif topic == "protogen/fins/bluetoothbridge/unpair":
                data = json.loads(payload)
                mac = data.get("mac")
                if mac:
                    self.unpair_device(mac)
            elif topic == "protogen/fins/bluetoothbridge/assign":
                data = json.loads(payload)
                mac = data.get("mac")
                display = data.get("display")
                if display in ["left", "right"]:
                    self.assign_display(mac, display)
            elif topic == "protogen/fins/bluetoothbridge/bluetooth/restart":
                self.restart_bluetooth()
            elif topic == "protogen/fins/bluetoothbridge/status/assignments":
                # Restore assignments from retained message
                self._restore_assignments(payload)
            elif topic == "protogen/fins/bluetoothbridge/status/last_audio_device":
                # Restore last audio device from retained message
                self._restore_last_audio_device(payload)
        except Exception as e:
            print(f"[BluetoothBridge] Error handling MQTT message: {e}")

    def start_scan(self):
        """Start Bluetooth scanning"""
        if self.scanning:
            print("[BluetoothBridge] Already scanning")
            return

        print("[BluetoothBridge] Starting Bluetooth scan...")
        self.scanning = True
        self.publish_scanning_status()

        # Start scan in background thread
        self.scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
        self.scan_thread.start()

    def _scan_worker(self):
        """Background worker for Bluetooth scanning on both adapters"""
        try:
            # Get both adapter MACs
            gamepad_adapter_mac = self._get_adapter_mac(self.gamepad_adapter)
            audio_adapter_mac = self._get_adapter_mac(self.audio_adapter)

            print(f"[BluetoothBridge] Scanning on both adapters:")
            print(f"[BluetoothBridge]   {self.gamepad_adapter} ({gamepad_adapter_mac}) - for gamepads")
            print(f"[BluetoothBridge]   {self.audio_adapter} ({audio_adapter_mac}) - for audio")

            # Start bluetoothctl processes for each adapter
            scan_processes = []

            # Start gamepad adapter scan
            if gamepad_adapter_mac:
                proc = subprocess.Popen(
                    ["bluetoothctl"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                proc.stdin.write(f"select {gamepad_adapter_mac}\n")
                proc.stdin.write("scan on\n")
                proc.stdin.flush()
                scan_processes.append(('gamepad', proc))

            # Start audio adapter scan (if different from gamepad adapter)
            if audio_adapter_mac and audio_adapter_mac != gamepad_adapter_mac:
                proc = subprocess.Popen(
                    ["bluetoothctl"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                proc.stdin.write(f"select {audio_adapter_mac}\n")
                proc.stdin.write("scan on\n")
                proc.stdin.flush()
                scan_processes.append(('audio', proc))

            # Store for cleanup
            self.scan_process = scan_processes

            # Also get list of paired devices
            self._update_paired_devices()

            # Parse scan output from all processes
            import select
            while self.scanning and scan_processes:
                # Check all processes for output
                for adapter_type, proc in scan_processes:
                    if proc.poll() is not None:
                        # Process exited
                        continue

                    # Non-blocking read
                    r, _, _ = select.select([proc.stdout], [], [], 0.01)
                    if not r:
                        continue

                    line = proc.stdout.readline()
                    if not line:
                        continue

                    # Strip ANSI escape codes (color codes from bluetoothctl)
                    line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                    line = line.rstrip()

                    # Skip empty lines and bluetoothctl prompts
                    if not line or line.startswith('[bluetoothctl]'):
                        continue

                    # Parse device discovery: [NEW] Device AA:BB:CC:DD:EE:FF Device Name
                    # Only process lines that start with [NEW] or [CHG] and contain "Device"
                    if ('[NEW]' in line or '[CHG]' in line) and 'Device' in line:
                        match = re.search(r'\[(?:NEW|CHG)\]\s+Device\s+([0-9A-F:]+)\s+(.+)', line, re.IGNORECASE)
                        if match:
                            mac = match.group(1).upper()
                            name = match.group(2).strip()

                            # Check if it's a gamepad/joystick
                            if self._is_gamepad_device(name):
                                self.discovered_devices[mac] = {
                                    "mac": mac,
                                    "name": name,
                                    "paired": False,
                                    "connected": False
                                }
                                print(f"[BluetoothBridge] ✓ Added gamepad: {name} ({mac}) [from {adapter_type} adapter]")
                                self.publish_devices_status()
                            # Check if it's an audio device (speaker, headphones, etc.)
                            elif self._is_audio_device(name):
                                self.audio_devices[mac] = {
                                    "mac": mac,
                                    "name": name,
                                    "paired": False,
                                    "connected": False,
                                    "type": "audio"
                                }
                                print(f"[BluetoothBridge] ✓ Added audio device: {name} ({mac}) [from {adapter_type} adapter]")
                                self.publish_audio_devices_status()
                            else:
                                print(f"[BluetoothBridge] Filtered out (not a gamepad or audio device): {name}")

                time.sleep(0.01)  # Small delay to prevent CPU spinning

        except Exception as e:
            print(f"[BluetoothBridge] Scan error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.scanning = False
            self.publish_scanning_status()

    def _start_monitor(self):
        """Start monitoring for Bluetooth connection state changes"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            print("[BluetoothBridge] Monitor already running")
            return

        print("[BluetoothBridge] Starting Bluetooth connection monitor...")
        self.monitor_thread = threading.Thread(target=self._monitor_worker, daemon=True)
        self.monitor_thread.start()

    def _monitor_worker(self):
        """Background worker for monitoring Bluetooth connection state changes via polling"""
        print("[BluetoothBridge] Monitor worker started (polling mode)")

        poll_count = 0

        while self.running:
            try:
                poll_count += 1

                # Get currently connected BT devices from bluetoothctl (for gamepads)
                result = subprocess.run(
                    ["bluetoothctl", "devices", "Connected"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                bt_connected = set()
                for line in result.stdout.splitlines():
                    match = re.search(r'Device\s+([0-9A-F:]+)', line, re.IGNORECASE)
                    if match:
                        bt_connected.add(match.group(1).upper())

                # Get connected audio devices from PulseAudio (more reliable for audio)
                audio_connected = set()
                try:
                    env = {**os.environ, 'XDG_RUNTIME_DIR': '/run/user/1000'}
                    pa_result = subprocess.run(
                        ["pactl", "list", "sinks", "short"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        env=env
                    )
                    for line in pa_result.stdout.splitlines():
                        if "bluez_sink." in line:
                            # Extract MAC from sink name like bluez_sink.FC_58_FA_75_DB_56.a2dp_sink
                            match = re.search(r'bluez_sink\.([0-9A-Fa-f_]+)\.', line)
                            if match:
                                mac = match.group(1).replace("_", ":").upper()
                                audio_connected.add(mac)
                except Exception as e:
                    pass  # PulseAudio check failed, skip

                # Log every 10th poll
                if poll_count % 10 == 1:
                    print(f"[BluetoothBridge] Monitor poll #{poll_count}, BT: {bt_connected}, Audio: {audio_connected}")

                # Check gamepads - use bluetoothctl state
                for mac in bt_connected:
                    if mac in self.discovered_devices:
                        if not self.discovered_devices[mac].get("connected"):
                            print(f"[BluetoothBridge] 🎮 Controller reconnected: {mac}")
                            self._handle_controller_connected(mac)

                for mac, info in list(self.discovered_devices.items()):
                    if info.get("connected") and mac not in bt_connected:
                        print(f"[BluetoothBridge] 🎮 Controller disconnected (poll): {mac}")
                        self._handle_controller_disconnected(mac)

                # Check audio devices - use PulseAudio state
                for mac in audio_connected:
                    if mac in self.audio_devices:
                        if not self.audio_devices[mac].get("connected"):
                            print(f"[BluetoothBridge] 🔊 Audio device reconnected: {mac}")
                            self._handle_audio_device_connected(mac)

                for mac, info in list(self.audio_devices.items()):
                    if info.get("connected") and mac not in audio_connected:
                        print(f"[BluetoothBridge] 🔊 Audio device disconnected (poll): {mac}")
                        self._handle_audio_device_disconnected(mac)

                # Poll every 2 seconds
                time.sleep(2)

            except Exception as e:
                print(f"[BluetoothBridge] Monitor poll error: {e}")
                time.sleep(5)  # Wait longer on error

    def _handle_controller_connected(self, mac: str):
        """Handle a controller connecting automatically"""
        try:
            # Wait a moment for device to appear in /dev/input
            time.sleep(3)

            # Find the evdev device
            evdev_path = self._find_evdev_device(mac)
            if evdev_path:
                device_info = self.discovered_devices.get(mac, {})
                self.connected_devices[mac] = {
                    "mac": mac,
                    "name": device_info.get("name", "Unknown"),
                    "evdev_path": evdev_path,
                    "device": None
                }

                # Update discovered devices
                if mac in self.discovered_devices:
                    self.discovered_devices[mac]["connected"] = True

                # Start input reading (only if startup is complete to avoid race conditions)
                if self.startup_complete:
                    self._start_input_reading(mac)

                self.publish_devices_status()
                self.publish_assignments_status()

                print(f"[BluetoothBridge] ✓ Controller ready: {mac}")
            else:
                print(f"[BluetoothBridge] Could not find evdev device for {mac}")

        except Exception as e:
            print(f"[BluetoothBridge] Error handling connected controller: {e}")
            import traceback
            traceback.print_exc()

    def _handle_controller_disconnected(self, mac: str):
        """Handle a controller disconnecting automatically"""
        try:
            # Stop input reading
            if mac in self.input_threads:
                self._stop_input_reading(mac)

            # Remove from connected devices
            if mac in self.connected_devices:
                del self.connected_devices[mac]

            # Update discovered devices
            if mac in self.discovered_devices:
                self.discovered_devices[mac]["connected"] = False

            self.publish_devices_status()
            self.publish_assignments_status()

            print(f"[BluetoothBridge] ✓ Controller cleaned up: {mac}")

        except Exception as e:
            print(f"[BluetoothBridge] Error handling disconnected controller: {e}")

    def _handle_audio_device_connected(self, mac: str):
        """Handle an audio device connecting automatically"""
        try:
            # Update audio devices state
            if mac in self.audio_devices:
                self.audio_devices[mac]["connected"] = True

            self.publish_audio_devices_status()

            # Remember this as the last connected audio device (for auto-reconnect)
            self.publish_last_audio_device(mac)

            print(f"[BluetoothBridge] ✓ Audio device ready: {mac}")

        except Exception as e:
            print(f"[BluetoothBridge] Error handling connected audio device: {e}")
            import traceback
            traceback.print_exc()

    def _handle_audio_device_disconnected(self, mac: str):
        """Handle an audio device disconnecting automatically"""
        try:
            # Update audio devices state
            if mac in self.audio_devices:
                self.audio_devices[mac]["connected"] = False

            self.publish_audio_devices_status()
            print(f"[BluetoothBridge] ✓ Audio device cleaned up: {mac}")

        except Exception as e:
            print(f"[BluetoothBridge] Error handling disconnected audio device: {e}")

    def _is_gamepad_device(self, name: str) -> bool:
        """Check if device name suggests it's a gamepad"""
        keywords = ['controller', 'gamepad', 'joystick', 'xbox', 'playstation',
                   'ps4', 'ps5', 'dualshock', 'dualsense', 'switch', 'pro controller',
                   '8bitdo', 'nintendo']
        name_lower = name.lower()
        return any(keyword in name_lower for keyword in keywords)

    def _is_audio_device(self, name: str) -> bool:
        """Check if device name suggests it's an audio device"""
        keywords = ['speaker', 'headphone', 'headset', 'earphone', 'earbud',
                   'soundbar', 'audio', 'buds', 'airpods', 'airpod', 'beats',
                   'bose', 'sony', 'jbl', 'marshall', 'harman', 'tronsmart',
                   'anker', 'soundcore', 'ue boom', 'megaboom', 'wonderboom']
        name_lower = name.lower()
        # Don't match devices that are clearly gamepads
        if self._is_gamepad_device(name):
            return False
        return any(keyword in name_lower for keyword in keywords)

    def _wait_for_audio_system_ready(self, max_seconds: int = 30) -> bool:
        """Wait for PulseAudio to be ready

        Returns:
            True if ready, False if timeout
        """
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
                        print(f"[BluetoothBridge] ✓ Audio system ready after {attempt + 1}s")
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def _reload_pulseaudio_bluetooth(self) -> bool:
        """Reload PulseAudio Bluetooth module to fix profile issues

        Returns:
            True if successful
        """
        print("[BluetoothBridge] Reloading PulseAudio Bluetooth module...")
        try:
            env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}

            # Unload and reload bluetooth modules
            subprocess.run(["pactl", "unload-module", "module-bluetooth-discover"],
                         capture_output=True, timeout=5, env=env)
            time.sleep(1)
            result = subprocess.run(["pactl", "load-module", "module-bluetooth-discover"],
                                   capture_output=True, timeout=5, env=env)

            if result.returncode == 0:
                print("[BluetoothBridge] ✓ PulseAudio Bluetooth module reloaded")
                time.sleep(2)  # Give it time to discover devices
                return True
            else:
                print(f"[BluetoothBridge] ⚠ Failed to reload module: {result.stderr.decode()}")
                return False
        except Exception as e:
            print(f"[BluetoothBridge] Error reloading PulseAudio module: {e}")
            return False

    def _update_pulseaudio_audio_devices(self):
        """Discover Bluetooth audio devices from PulseAudio

        This catches devices that PulseAudio knows about but bluetoothctl may not show.
        """
        try:
            env = {**os.environ, 'XDG_RUNTIME_DIR': '/run/user/1000'}
            result = subprocess.run(
                ["pactl", "list", "sinks"],
                capture_output=True,
                text=True,
                timeout=5,
                env=env
            )

            if result.returncode != 0:
                return

            # Parse pactl output to find Bluetooth sinks
            current_sink = {}
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Name:"):
                    current_sink = {"name": line.split(":", 1)[1].strip()}
                elif line.startswith("Description:") and current_sink:
                    current_sink["description"] = line.split(":", 1)[1].strip()
                elif "device.string" in line and current_sink:
                    # Extract MAC address
                    match = re.search(r'"([0-9A-Fa-f:]{17})"', line)
                    if match:
                        current_sink["mac"] = match.group(1).upper()
                elif line.startswith("Sink #") or line == "":
                    # End of sink, process if it's Bluetooth
                    if current_sink.get("name", "").startswith("bluez_sink."):
                        mac = current_sink.get("mac")
                        if not mac:
                            # Try to extract MAC from sink name (bluez_sink.FC_58_FA_75_DB_56.a2dp_sink)
                            match = re.search(r'bluez_sink\.([0-9A-Fa-f_]+)\.', current_sink["name"])
                            if match:
                                mac = match.group(1).replace("_", ":").upper()

                        if mac and mac not in self.audio_devices:
                            device_name = current_sink.get("description", f"Bluetooth Audio ({mac})")
                            self.audio_devices[mac] = {
                                "mac": mac,
                                "name": device_name,
                                "paired": True,  # If PulseAudio has it, it's paired
                                "connected": True,  # If it's a sink, it's connected
                                "type": "audio"
                            }
                            print(f"[BluetoothBridge] ✓ Found audio device from PulseAudio: {device_name} ({mac})")
                        elif mac and mac in self.audio_devices:
                            # Update as connected
                            self.audio_devices[mac]["connected"] = True
                    current_sink = {}

            # Handle last sink if output doesn't end with empty line
            if current_sink.get("name", "").startswith("bluez_sink."):
                mac = current_sink.get("mac")
                if not mac:
                    match = re.search(r'bluez_sink\.([0-9A-Fa-f_]+)\.', current_sink["name"])
                    if match:
                        mac = match.group(1).replace("_", ":").upper()

                if mac and mac not in self.audio_devices:
                    device_name = current_sink.get("description", f"Bluetooth Audio ({mac})")
                    self.audio_devices[mac] = {
                        "mac": mac,
                        "name": device_name,
                        "paired": True,
                        "connected": True,
                        "type": "audio"
                    }
                    print(f"[BluetoothBridge] ✓ Found audio device from PulseAudio: {device_name} ({mac})")
                elif mac and mac in self.audio_devices:
                    self.audio_devices[mac]["connected"] = True

        except Exception as e:
            print(f"[BluetoothBridge] Error checking PulseAudio devices: {e}")

    def _update_paired_devices(self, start_input_threads=True):
        """Update paired device status and load paired gamepads

        Args:
            start_input_threads: If True, starts input reading threads for connected devices
        """
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices", "Paired"],
                capture_output=True,
                text=True,
                timeout=5
            )

            paired_count = 0
            audio_count = 0
            for line in result.stdout.splitlines():
                match = re.search(r'Device\s+([0-9A-F:]+)\s+(.+)', line, re.IGNORECASE)
                if match:
                    mac = match.group(1).upper()
                    name = match.group(2).strip()

                    # Check if it's a gamepad
                    if self._is_gamepad_device(name):
                        # Check if device is connected
                        is_connected = self._check_device_connected(mac)

                        if mac in self.discovered_devices:
                            self.discovered_devices[mac]["paired"] = True
                            self.discovered_devices[mac]["connected"] = is_connected
                        else:
                            self.discovered_devices[mac] = {
                                "mac": mac,
                                "name": name,
                                "paired": True,
                                "connected": is_connected
                            }

                        # If already connected, set up evdev
                        if is_connected:
                            evdev_path = self._find_evdev_device(mac)
                            if evdev_path:
                                self.connected_devices[mac] = {
                                    "mac": mac,
                                    "name": name,
                                    "evdev_path": evdev_path,
                                    "device": None
                                }
                                if start_input_threads:
                                    self._start_input_reading(mac)
                                print(f"[BluetoothBridge] ✓ Loaded connected gamepad: {name} ({mac})")
                            else:
                                print(f"[BluetoothBridge] Found paired gamepad (no evdev yet): {name} ({mac})")
                        else:
                            print(f"[BluetoothBridge] Found paired gamepad (not connected): {name} ({mac})")

                        paired_count += 1

                    # Check if it's an audio device
                    elif self._is_audio_device(name):
                        # Check if device is connected
                        is_connected = self._check_device_connected(mac)

                        if mac in self.audio_devices:
                            self.audio_devices[mac]["paired"] = True
                            self.audio_devices[mac]["connected"] = is_connected
                        else:
                            self.audio_devices[mac] = {
                                "mac": mac,
                                "name": name,
                                "paired": True,
                                "connected": is_connected,
                                "type": "audio"
                            }

                        if is_connected:
                            print(f"[BluetoothBridge] ✓ Loaded connected audio device: {name} ({mac})")
                        else:
                            print(f"[BluetoothBridge] Found paired audio device (not connected): {name} ({mac})")

                        audio_count += 1

            if paired_count > 0:
                self.publish_devices_status()

            # Also check PulseAudio for connected Bluetooth audio devices
            # (catches devices that PulseAudio knows but bluetoothctl may not show)
            self._update_pulseaudio_audio_devices()

            if audio_count > 0 or len(self.audio_devices) > 0:
                self.publish_audio_devices_status()

        except Exception as e:
            print(f"[BluetoothBridge] Error updating paired devices: {e}")

    def _check_device_connected(self, mac: str) -> bool:
        """Check if a Bluetooth device is currently connected"""
        try:
            result = subprocess.run(
                ["bluetoothctl", "info", mac],
                capture_output=True,
                text=True,
                timeout=5
            )
            return "Connected: yes" in result.stdout
        except Exception as e:
            print(f"[BluetoothBridge] Error checking connection for {mac}: {e}")
            return False

    def stop_scan(self):
        """Stop Bluetooth scanning"""
        if not self.scanning:
            return

        print("[BluetoothBridge] Stopping Bluetooth scan...")
        self.scanning = False

        if self.scan_process:
            # Handle both single process (legacy) and list of processes (new multi-adapter)
            processes = self.scan_process if isinstance(self.scan_process, list) else [('default', self.scan_process)]

            for adapter_type, proc in processes:
                try:
                    # Send scan off command to interactive bluetoothctl
                    if proc.poll() is None:
                        proc.stdin.write("scan off\n")
                        proc.stdin.write("quit\n")
                        proc.stdin.flush()
                        proc.wait(timeout=2)
                except Exception as e:
                    print(f"[BluetoothBridge] Error stopping {adapter_type} scan: {e}")
                    try:
                        proc.terminate()
                        proc.wait(timeout=1)
                    except:
                        proc.kill()

            self.scan_process = None

        self.publish_scanning_status()

    def _reconnect_device(self, mac: str):
        """Reconnect to an already-paired device (internal helper for restart)"""
        try:
            adapter = self._get_adapter_for_device(mac)
            adapter_mac = self._get_adapter_mac(adapter)

            if not adapter_mac:
                print(f"[BluetoothBridge] ✗ Cannot reconnect {mac}: adapter not found")
                return

            # Use bluetoothctl to connect (device is already paired/trusted)
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            proc.stdin.write(f"select {adapter_mac}\n")
            proc.stdin.flush()
            time.sleep(0.3)

            proc.stdin.write(f"connect {mac}\n")
            proc.stdin.flush()

            # Wait for response
            success, output = self._wait_for_bluetoothctl_response(
                proc,
                success_patterns=["connection successful", "already connected"],
                failure_patterns=["failed to connect", "not available", "org.bluez.error"],
                timeout=10
            )

            proc.stdin.write("quit\n")
            proc.stdin.flush()
            try:
                proc.wait(timeout=2)
            except:
                proc.kill()

            if success:
                print(f"[BluetoothBridge] ✓ Reconnected: {mac}")
                # Update device status
                if mac in self.audio_devices:
                    self.audio_devices[mac]["connected"] = True
                    self.publish_audio_devices_status()
                    self.publish_last_audio_device(mac)
                elif mac in self.discovered_devices:
                    self.discovered_devices[mac]["connected"] = True
                    self._handle_controller_connected(mac)
            else:
                print(f"[BluetoothBridge] ⚠ Reconnect failed for {mac}: {output}")

        except Exception as e:
            print(f"[BluetoothBridge] Error reconnecting {mac}: {e}")

    def _wait_for_bluetoothctl_response(self, proc, success_patterns: list, failure_patterns: list, timeout: float = 10) -> tuple:
        """Wait for bluetoothctl response by reading output in real-time

        Args:
            proc: The bluetoothctl subprocess
            success_patterns: List of strings that indicate success
            failure_patterns: List of strings that indicate failure
            timeout: Maximum time to wait in seconds

        Returns:
            (success: bool, output: str)
        """
        import select
        output_lines = []
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check if there's data to read
            r, _, _ = select.select([proc.stdout], [], [], 0.1)
            if not r:
                continue

            line = proc.stdout.readline()
            if not line:
                continue

            # Strip ANSI codes
            line = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
            if line:
                output_lines.append(line)

                # Check for success
                for pattern in success_patterns:
                    if pattern.lower() in line.lower():
                        return True, '\n'.join(output_lines)

                # Check for failure
                for pattern in failure_patterns:
                    if pattern.lower() in line.lower():
                        return False, '\n'.join(output_lines)

        # Timeout - return what we have
        return None, '\n'.join(output_lines)

    def connect_device(self, mac: str):
        """Connect to a Bluetooth device (runs in background thread)"""
        print(f"[BluetoothBridge] Connecting to {mac}...")

        # Stop scanning while connecting
        if self.scanning:
            print("[BluetoothBridge] Stopping scan for connection...")
            self.stop_scan()

        # Publish connecting status immediately
        self.publish_connection_status(mac, "connecting")

        # Run connection in background thread so MQTT loop can send the status
        threading.Thread(target=self._connect_device_worker, args=(mac,), daemon=True).start()

    def _connect_device_worker(self, mac: str):
        """Background worker for device connection"""
        try:
            # Get the appropriate adapter for this device
            adapter = self._get_adapter_for_device(mac)
            adapter_mac = self._get_adapter_mac(adapter)
            print(f"[BluetoothBridge] Using adapter: {adapter} ({adapter_mac})")

            # Start bluetoothctl in interactive mode
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Select adapter
            proc.stdin.write(f"select {adapter_mac}\n")
            proc.stdin.flush()
            time.sleep(0.3)

            # Check if device is already paired
            already_paired = False
            if mac in self.discovered_devices and self.discovered_devices[mac].get("paired"):
                already_paired = True
            elif mac in self.audio_devices and self.audio_devices[mac].get("paired"):
                already_paired = True

            if not already_paired:
                # Trust device
                proc.stdin.write(f"trust {mac}\n")
                proc.stdin.flush()
                success, output = self._wait_for_bluetoothctl_response(
                    proc,
                    success_patterns=["trust succeeded", "Changing", "trusted: yes"],
                    failure_patterns=["not available"],
                    timeout=3
                )

                # Pair device
                print(f"[BluetoothBridge] Pairing to {mac}...")
                proc.stdin.write(f"pair {mac}\n")
                proc.stdin.flush()
                success, output = self._wait_for_bluetoothctl_response(
                    proc,
                    success_patterns=["pairing successful", "paired: yes", "alreadyexists"],
                    failure_patterns=["org.bluez.error.authenticationfailed", "org.bluez.error.authenticationcanceled"],
                    timeout=10
                )
                if success is False:
                    print(f"[BluetoothBridge] ⚠ Pairing issue: {output}")
            else:
                print(f"[BluetoothBridge] Device already paired, skipping trust/pair")

            # Connect device
            print(f"[BluetoothBridge] Connecting to {mac}...")
            proc.stdin.write(f"connect {mac}\n")
            proc.stdin.flush()
            success, output = self._wait_for_bluetoothctl_response(
                proc,
                success_patterns=["connection successful", "already connected"],
                failure_patterns=["failed to connect", "not available", "org.bluez.error"],
                timeout=15
            )

            # Quit
            proc.stdin.write("quit\n")
            proc.stdin.flush()
            try:
                proc.wait(timeout=2)
            except:
                proc.kill()

            # Combine all output for error checking
            full_output = output

            # Check for common Bluetooth errors
            if "org.bluez.Error.NotReady" in full_output:
                print("[BluetoothBridge] ✗ Bluetooth service is not ready!")
                print("[BluetoothBridge] → Try restarting Bluetooth via the web interface or MQTT:")
                print("[BluetoothBridge]   mosquitto_pub -t 'protogen/fins/bluetoothbridge/bluetooth/restart' -m ''")
                self.publish_connection_status(mac, "failed", "Bluetooth service not ready")
                return

            # Check for audio profile issues
            if "br-connection-profile-unavailable" in full_output or "profile unavailable" in full_output.lower():
                print("[BluetoothBridge] ⚠ Bluetooth profile unavailable, attempting to reload audio modules...")

                # Try to reload PulseAudio Bluetooth module
                if self._reload_pulseaudio_bluetooth():
                    # Wait for audio system to be ready
                    if self._wait_for_audio_system_ready(max_seconds=10):
                        # Retry connection
                        print(f"[BluetoothBridge] Retrying connection to {mac}...")
                        retry_result = subprocess.run(
                            ["bluetoothctl"],
                            input=f"select {adapter_mac}\nconnect {mac}\nquit\n" if adapter_mac else f"connect {mac}\nquit\n",
                            capture_output=True,
                            text=True,
                            timeout=15
                        )
                        retry_output = retry_result.stdout + retry_result.stderr

                        if "connection successful" in retry_output.lower():
                            print(f"[BluetoothBridge] ✓ Connected to {mac} after reload")
                            # Mark as audio device and publish status
                            if mac not in self.audio_devices:
                                self.audio_devices[mac] = {
                                    "mac": mac,
                                    "name": self.discovered_devices.get(mac, {}).get("name", "Bluetooth Audio"),
                                    "paired": True,
                                    "connected": True,
                                    "type": "audio"
                                }
                            else:
                                self.audio_devices[mac]["connected"] = True
                            self.publish_audio_devices_status()
                            self.publish_last_audio_device(mac)
                            self.publish_connection_status(mac, "connected")
                            return

                print("[BluetoothBridge] ✗ Failed to connect after reload")
                print("[BluetoothBridge] → PulseAudio/PipeWire Bluetooth modules may need manual restart")
                self.publish_connection_status(mac, "failed", "Bluetooth profile unavailable")
                return

            # Check if connection succeeded or was already established
            if success or "connection successful" in full_output.lower() or "already connected" in full_output.lower():
                if "already connected" in output.lower():
                    print(f"[BluetoothBridge] ✓ Device {mac} was already connected")
                else:
                    print(f"[BluetoothBridge] ✓ Connected to {mac} ({full_output})")

                # Check if this is an audio device or gamepad
                is_audio = mac in self.audio_devices
                is_gamepad = mac in self.discovered_devices

                if is_audio:
                    # Audio device - just update status
                    if mac in self.audio_devices:
                        self.audio_devices[mac]["connected"] = True
                        self.audio_devices[mac]["paired"] = True
                    print(f"[BluetoothBridge] ✓ Audio device connected: {self.audio_devices[mac].get('name', mac)}")
                    self.publish_audio_devices_status()
                    self.publish_connection_status(mac, "connected")

                elif is_gamepad:
                    # Gamepad - find evdev device and start input reading
                    # Wait a moment for device to appear in /dev/input
                    time.sleep(2)

                    evdev_path = self._find_evdev_device(mac)
                    if evdev_path:
                        device_info = self.discovered_devices.get(mac, {})
                        self.connected_devices[mac] = {
                            "mac": mac,
                            "name": device_info.get("name", "Unknown"),
                            "evdev_path": evdev_path,
                            "device": None
                        }

                        # Update discovered devices
                        if mac in self.discovered_devices:
                            self.discovered_devices[mac]["connected"] = True
                            self.discovered_devices[mac]["paired"] = True

                        # Start input reading
                        self._start_input_reading(mac)

                        self.publish_devices_status()
                        self.publish_assignments_status()
                        self.publish_connection_status(mac, "connected")
                        print(f"[BluetoothBridge] ✓ Gamepad ready: {device_info.get('name', mac)}")
                    else:
                        print(f"[BluetoothBridge] ✗ Could not find evdev device for {mac}")
                        self.publish_connection_status(mac, "failed", "Could not find input device")
                else:
                    print(f"[BluetoothBridge] ⚠ Unknown device type for {mac}")
                    self.publish_connection_status(mac, "failed", "Unknown device type")

            else:
                error_msg = output.strip()[:200]  # Limit error message length
                print(f"[BluetoothBridge] ✗ Failed to connect:")
                print(f"[BluetoothBridge]   Output: {output.strip()}")
                self.publish_connection_status(mac, "failed", error_msg)

        except Exception as e:
            print(f"[BluetoothBridge] Connection error: {e}")
            self.publish_connection_status(mac, "failed", str(e))

    def _find_evdev_device(self, mac: str) -> Optional[str]:
        """Find evdev device path for a Bluetooth MAC address"""
        if not EVDEV_AVAILABLE:
            return None

        try:
            # List all input devices
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

            # Get list of already-assigned evdev paths to avoid duplicates
            already_assigned = set(
                info["evdev_path"]
                for info in self.connected_devices.values()
                if "evdev_path" in info
            )

            # Get the expected device name from our discovered devices
            expected_name = None
            if mac in self.discovered_devices:
                expected_name = self.discovered_devices[mac].get("name", "").lower()

            print(f"[BluetoothBridge] Looking for evdev device for MAC {mac} (name: {expected_name})")
            print(f"[BluetoothBridge] Already assigned devices: {already_assigned}")

            # First pass: try to match by MAC in phys field
            for device in devices:
                if device.path in already_assigned:
                    continue

                caps = device.capabilities()
                has_buttons = ecodes.EV_KEY in caps
                has_abs = ecodes.EV_ABS in caps

                if has_buttons or has_abs:
                    phys = device.phys
                    print(f"[BluetoothBridge]   Checking {device.path} ({device.name}), phys: {phys}")
                    if phys and mac.replace(":", "").lower() in phys.lower().replace(":", ""):
                        print(f"[BluetoothBridge] ✓ Found evdev device by MAC: {device.path} ({device.name})")
                        return device.path

            # Second pass: try to match by device name (exact match only)
            if expected_name:
                print(f"[BluetoothBridge] Could not find by MAC, trying exact name match...")
                for device in devices:
                    if device.path in already_assigned:
                        continue

                    caps = device.capabilities()
                    has_buttons = ecodes.EV_KEY in caps
                    has_abs = ecodes.EV_ABS in caps

                    if has_buttons and has_abs:
                        device_name_lower = device.name.lower()
                        # Check if device names match exactly (case-insensitive)
                        if expected_name == device_name_lower:
                            print(f"[BluetoothBridge] ✓ Found evdev device by exact name: {device.path} ({device.name})")
                            return device.path

            # Last resort fallback: only if there's exactly ONE unassigned gamepad
            print(f"[BluetoothBridge] Could not find by name, checking for single unassigned gamepad...")
            unassigned_gamepads = []
            for device in devices:
                if device.path in already_assigned:
                    continue

                caps = device.capabilities()
                has_buttons = ecodes.EV_KEY in caps
                has_abs = ecodes.EV_ABS in caps

                if has_buttons and has_abs:
                    if ecodes.EV_KEY in caps:
                        keys = caps[ecodes.EV_KEY]
                        if ecodes.BTN_SOUTH in keys or ecodes.BTN_GAMEPAD in keys:
                            unassigned_gamepads.append(device)

            if len(unassigned_gamepads) == 1:
                device = unassigned_gamepads[0]
                print(f"[BluetoothBridge] ✓ Found single unassigned gamepad: {device.path} ({device.name})")
                return device.path
            elif len(unassigned_gamepads) > 1:
                print(f"[BluetoothBridge] ⚠ Multiple unassigned gamepads found, cannot determine which one: {[d.name for d in unassigned_gamepads]}")

            print(f"[BluetoothBridge] ✗ No evdev device found for {mac}")

        except Exception as e:
            print(f"[BluetoothBridge] Error finding evdev device: {e}")

        return None

    def disconnect_device(self, mac: str):
        """Disconnect a Bluetooth device (preserves assignments)"""
        print(f"[BluetoothBridge] Disconnecting {mac}...")

        # Publish disconnecting status immediately
        self.publish_connection_status(mac, "disconnecting")

        # Run disconnection in background thread so MQTT loop can send the status
        threading.Thread(target=self._disconnect_device_worker, args=(mac,), daemon=True).start()

    def _disconnect_device_worker(self, mac: str):
        """Background worker for device disconnection"""
        try:
            # Check device type
            is_audio = mac in self.audio_devices
            is_gamepad = mac in self.discovered_devices

            # Stop input reading for gamepads
            if is_gamepad:
                self._stop_input_reading(mac)

            # Get the appropriate adapter for this device
            adapter = self._get_adapter_for_device(mac)
            adapter_mac = self._get_adapter_mac(adapter)

            # Disconnect via bluetoothctl with proper waiting
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            if adapter_mac:
                proc.stdin.write(f"select {adapter_mac}\n")
                proc.stdin.flush()
                time.sleep(0.3)

            proc.stdin.write(f"disconnect {mac}\n")
            proc.stdin.flush()

            # Wait for disconnect response
            success, output = self._wait_for_bluetoothctl_response(
                proc,
                success_patterns=["successful disconnection", "disconnected"],
                failure_patterns=["not connected", "failed"],
                timeout=5
            )

            proc.stdin.write("quit\n")
            proc.stdin.flush()
            try:
                proc.wait(timeout=2)
            except:
                proc.kill()

            if success:
                print(f"[BluetoothBridge] ✓ Disconnected {mac}")
                self.publish_connection_status(mac, "disconnected")
            else:
                print(f"[BluetoothBridge] ⚠ Disconnect status unclear for {mac}")
                self.publish_connection_status(mac, "disconnected")  # Still update UI

            # Update state for gamepads
            if mac in self.connected_devices:
                del self.connected_devices[mac]

            if mac in self.discovered_devices:
                self.discovered_devices[mac]["connected"] = False

            # Update state for audio devices
            if mac in self.audio_devices:
                self.audio_devices[mac]["connected"] = False

            # NOTE: Assignments are preserved on disconnect - they'll be used when device reconnects

            # Publish appropriate status
            if is_gamepad:
                self.publish_devices_status()
                self.publish_assignments_status()
                print(f"[BluetoothBridge] ✓ Gamepad disconnected: {mac}")

            if is_audio:
                self.publish_audio_devices_status()
                print(f"[BluetoothBridge] ✓ Audio device disconnected: {mac}")

        except Exception as e:
            print(f"[BluetoothBridge] Disconnect error: {e}")

    def unpair_device(self, mac: str):
        """Unpair (remove) a Bluetooth device"""
        print(f"[BluetoothBridge] Unpairing {mac}...")

        try:
            # Check device type
            is_audio = mac in self.audio_devices
            is_gamepad = mac in self.discovered_devices

            # First disconnect if connected
            if mac in self.connected_devices or (is_audio and self.audio_devices.get(mac, {}).get("connected")):
                self.disconnect_device(mac)
                time.sleep(0.5)  # Wait for disconnect

            # Get the appropriate adapter for this device based on type we already determined
            if is_audio:
                adapter = self.audio_adapter
            else:
                adapter = self.gamepad_adapter
            adapter_mac = self._get_adapter_mac(adapter)
            print(f"[BluetoothBridge] Using adapter {adapter} ({adapter_mac}) for unpair")

            # Remove/unpair via bluetoothctl using interactive mode (more reliable)
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Select adapter if available
            if adapter_mac:
                proc.stdin.write(f"select {adapter_mac}\n")
                proc.stdin.flush()
                time.sleep(0.3)

            # Untrust and remove the device
            proc.stdin.write(f"untrust {mac}\n")
            proc.stdin.flush()
            time.sleep(0.3)

            proc.stdin.write(f"remove {mac}\n")
            proc.stdin.flush()
            time.sleep(0.5)

            proc.stdin.write("quit\n")
            proc.stdin.flush()

            try:
                output, _ = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                output = ""

            success = "Device has been removed" in output or "not available" in output.lower()

            if success:
                print(f"[BluetoothBridge] ✓ Unpaired {mac}")
            else:
                print(f"[BluetoothBridge] ⚠ Unpair command sent (output: {output.strip()[:100]})")

            # Always remove from local state regardless of bluetoothctl output
            # (the device might already be gone)
            if mac in self.discovered_devices:
                del self.discovered_devices[mac]
                self.publish_devices_status()

            if mac in self.audio_devices:
                del self.audio_devices[mac]
                self.publish_audio_devices_status()

            if mac in self.connected_devices:
                del self.connected_devices[mac]

        except Exception as e:
            print(f"[BluetoothBridge] Unpair error: {e}")
            import traceback
            traceback.print_exc()

    def _auto_reconnect_devices(self):
        """Auto-reconnect to previously connected devices"""
        print("[BluetoothBridge] Auto-reconnecting previously connected devices...")

        # Track devices we're reconnecting to avoid duplicates
        reconnecting = set()

        # Refresh PulseAudio devices first - this catches devices already connected
        self._update_pulseaudio_audio_devices()

        # Check if we have a last audio device to restore from retained message
        if self.last_audio_device_to_restore:
            mac = self.last_audio_device_to_restore["mac"]
            name = self.last_audio_device_to_restore["name"]

            # Check if already connected (PulseAudio might have auto-connected)
            if mac in self.audio_devices and self.audio_devices[mac].get("connected"):
                print(f"[BluetoothBridge] Last audio device already connected: {name} ({mac})")
            else:
                # Add to audio_devices if not present
                if mac not in self.audio_devices:
                    self.audio_devices[mac] = {
                        "mac": mac,
                        "name": name,
                        "paired": True,
                        "connected": False,
                        "type": "audio"
                    }

                # Wait for PulseAudio to be fully ready at boot
                print(f"[BluetoothBridge] Waiting for audio system to be ready...")
                if not self._wait_for_audio_system_ready(max_seconds=30):
                    print(f"[BluetoothBridge] ⚠ Audio system not ready after 30s, attempting anyway...")

                print(f"[BluetoothBridge] Reconnecting to last audio device: {name} ({mac})")
                reconnecting.add(mac)
                threading.Thread(
                    target=self._reconnect_device,
                    args=(mac,),
                    daemon=True
                ).start()
                time.sleep(1)

            self.last_audio_device_to_restore = None  # Clear after processing

        # Reconnect other audio devices that are paired but not connected (skip already reconnecting)
        for mac, device_info in list(self.audio_devices.items()):
            if mac not in reconnecting and device_info.get("paired") and not device_info.get("connected"):
                print(f"[BluetoothBridge] Reconnecting audio device: {device_info.get('name', mac)}")
                reconnecting.add(mac)
                threading.Thread(
                    target=self._reconnect_device,
                    args=(mac,),
                    daemon=True
                ).start()
                time.sleep(1)  # Stagger reconnections

        # Reconnect gamepads that have assignments (skip already reconnecting)
        for display, mac in self.assignments.items():
            if mac and mac not in reconnecting and mac in self.discovered_devices:
                device_info = self.discovered_devices[mac]
                if device_info.get("paired") and not device_info.get("connected"):
                    print(f"[BluetoothBridge] Reconnecting gamepad: {device_info.get('name', mac)} (assigned to {display})")
                    reconnecting.add(mac)
                    threading.Thread(
                        target=self._reconnect_device,
                        args=(mac,),
                        daemon=True
                    ).start()
                    time.sleep(1)  # Stagger reconnections

        # Publish updated audio devices status
        if self.audio_devices:
            self.publish_audio_devices_status()

    def restart_bluetooth(self):
        """Restart the Bluetooth service to fix org.bluez.Error.NotReady and similar issues"""
        print("[BluetoothBridge] Restarting Bluetooth service...")

        try:
            # Stop scanning first
            if self.scanning:
                self.stop_scan()

            # Stop monitor
            if self.monitor_process:
                try:
                    self.monitor_process.stdin.write("quit\n")
                    self.monitor_process.stdin.flush()
                    self.monitor_process.terminate()
                    self.monitor_process.wait(timeout=2)
                except Exception:
                    if self.monitor_process:
                        self.monitor_process.kill()
                self.monitor_process = None

            # Stop all input reading
            for mac in list(self.input_threads.keys()):
                self._stop_input_reading(mac)

            # Save state before clearing
            old_assignments = dict(self.assignments)

            # Clear device state
            self.connected_devices.clear()

            # Restart Bluetooth service
            print("[BluetoothBridge] Executing: sudo systemctl restart bluetooth")
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "bluetooth"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                print("[BluetoothBridge] ✓ Bluetooth service restarted successfully")

                # Wait for service to be ready
                time.sleep(3)

                # Restore assignments
                self.assignments = old_assignments

                # Reload paired devices
                print("[BluetoothBridge] Reloading paired devices...")
                self._update_paired_devices(start_input_threads=False)

                # Auto-reconnect devices
                self._auto_reconnect_devices()

                # Wait for reconnections to complete
                time.sleep(2)

                # Restart input threads for connected devices
                for mac in list(self.connected_devices.keys()):
                    self._start_input_reading(mac)

                # Restart the monitor
                self._start_monitor()

                self.publish_devices_status()
                self.publish_assignments_status()
                self.publish_audio_devices_status()

                print("[BluetoothBridge] ✓ Bluetooth restart complete")
            else:
                print(f"[BluetoothBridge] ✗ Failed to restart Bluetooth: {result.stderr}")
                print("[BluetoothBridge] Note: You may need to configure passwordless sudo for bluetooth restart")
                print("[BluetoothBridge] Run: sudo visudo")
                print("[BluetoothBridge] Add line: proto ALL=(ALL) NOPASSWD: /bin/systemctl restart bluetooth")

        except Exception as e:
            print(f"[BluetoothBridge] Bluetooth restart error: {e}")
            import traceback
            traceback.print_exc()

    def assign_display(self, mac: str, display: str):
        """Assign a controller to a display (or remove if mac is None)"""
        if mac is None:
            # Remove assignment - find which MAC was assigned and restart its input thread
            old_mac = self.assignments.get(display)
            self.assignments[display] = None
            print(f"[BluetoothBridge] Removed assignment for {display} display")

            # Restart input reading for the old device so it updates its assignment
            if old_mac and old_mac in self.connected_devices:
                self._stop_input_reading(old_mac)
                self._start_input_reading(old_mac)

            self.publish_assignments_status()
            return

        if mac not in self.connected_devices:
            print(f"[BluetoothBridge] Cannot assign {mac}: not connected")
            return

        # Check if this MAC was assigned elsewhere and clear that
        for d, m in list(self.assignments.items()):
            if m == mac and d != display:
                self.assignments[d] = None
                print(f"[BluetoothBridge] Cleared old assignment from {d}")

        # Assign controller to display
        self.assignments[display] = mac
        print(f"[BluetoothBridge] Assigned {mac} to {display} display")

        # Restart input reading thread with new assignment
        if mac in self.input_threads:
            print(f"[BluetoothBridge] Restarting input thread for {mac} with new assignment")
            self._stop_input_reading(mac)
            self._start_input_reading(mac)

        self.publish_assignments_status()

    def _restore_assignments(self, payload: str):
        """Restore assignments from retained MQTT message"""
        try:
            if not payload:
                print("[BluetoothBridge] No retained assignments to restore")
                return

            print(f"[BluetoothBridge] Attempting to restore assignments from: {payload}")
            data = json.loads(payload)
            restored_count = 0

            for display in ["left", "right"]:
                if display in data and data[display]:
                    mac = data[display].get("mac")
                    if mac:
                        # Restore assignment regardless of connection status
                        # The device will use this assignment when it connects
                        self.assignments[display] = mac
                        restored_count += 1
                        is_connected = mac in self.connected_devices
                        status = "connected" if is_connected else "not connected yet"
                        print(f"[BluetoothBridge] ✓ Restored assignment: {mac} -> {display} ({status})")

            if restored_count > 0:
                print(f"[BluetoothBridge] Successfully restored {restored_count} controller assignment(s)")
            else:
                print("[BluetoothBridge] No assignments to restore")

        except Exception as e:
            print(f"[BluetoothBridge] Error restoring assignments: {e}")
            import traceback
            traceback.print_exc()

    def _restore_last_audio_device(self, payload: str):
        """Store last audio device from retained MQTT message for later reconnection"""
        try:
            if not payload:
                return

            data = json.loads(payload)
            mac = data.get("mac")
            name = data.get("name", mac)

            if not mac:
                return

            # Store for later reconnection in _auto_reconnect_devices
            self.last_audio_device_to_restore = {"mac": mac, "name": name}
            print(f"[BluetoothBridge] Will attempt to reconnect to last audio device: {name} ({mac})")

        except Exception as e:
            print(f"[BluetoothBridge] Error parsing last audio device: {e}")

    def _start_input_reading(self, mac: str):
        """Start reading input from a gamepad"""
        if not EVDEV_AVAILABLE:
            print("[BluetoothBridge] evdev not available")
            return

        if mac in self.input_threads and self.input_threads[mac].is_alive():
            print(f"[BluetoothBridge] Input reading already active for {mac}")
            return

        device_info = self.connected_devices.get(mac)
        if not device_info:
            return

        # Check current assignment
        assigned_display = None
        for disp, assigned_mac in self.assignments.items():
            if assigned_mac == mac:
                assigned_display = disp
                break

        # Create stop event
        stop_event = threading.Event()
        self.input_stop_events[mac] = stop_event

        # Start input reading thread
        thread = threading.Thread(
            target=self._input_reading_worker,
            args=(mac, device_info["evdev_path"], stop_event),
            daemon=True
        )
        self.input_threads[mac] = thread
        thread.start()

        if assigned_display:
            print(f"[BluetoothBridge] Started input reading for {mac} -> assigned to '{assigned_display}' display")
        else:
            print(f"[BluetoothBridge] Started input reading for {mac} -> not assigned yet")

    def _stop_input_reading(self, mac: str):
        """Stop reading input from a gamepad"""
        if mac in self.input_stop_events:
            self.input_stop_events[mac].set()

        if mac in self.input_threads:
            thread = self.input_threads[mac]
            thread.join(timeout=2)
            del self.input_threads[mac]

        if mac in self.input_stop_events:
            del self.input_stop_events[mac]

    def _input_reading_worker(self, mac: str, evdev_path: str, stop_event: threading.Event):
        """Worker thread for reading gamepad input"""
        try:
            device = evdev.InputDevice(evdev_path)
            print(f"[BluetoothBridge] Reading input from {device.name} at {evdev_path}")

            # Track button states to send proper keyup/keydown
            button_states = {}
            dpad_x_state = 0
            dpad_y_state = 0

            # Track previous assignment to detect when device gets assigned
            was_assigned = False

            # Use select for non-blocking reads with timeout
            import select

            while not stop_event.is_set():
                # Use select to wait for events with 10ms timeout
                r, w, x = select.select([device.fd], [], [], 0.01)

                if not r:
                    # No events available
                    continue

                # Read all available events
                try:
                    events = list(device.read())  # Convert to list so we can discard
                except (BlockingIOError, OSError):
                    continue

                if not events:
                    continue

                # Find which display this controller is assigned to
                display = None
                for disp, assigned_mac in self.assignments.items():
                    if assigned_mac == mac:
                        display = disp
                        break

                if not display:
                    was_assigned = False
                    continue  # Not assigned to any display

                # If we just got assigned, discard buffered events to avoid input dump
                if not was_assigned:
                    print(f"[BluetoothBridge] Controller {mac} assigned to {display}, discarding {len(events)} buffered events")
                    was_assigned = True
                    continue  # Skip these events, they were from before assignment

                # Process all available events
                for event in events:

                    # Handle button events
                    if event.type == ecodes.EV_KEY:
                        button_names = ecodes.BTN[event.code] if event.code in ecodes.BTN else None

                        if button_names:
                            # button_names can be a string or tuple of strings
                            if isinstance(button_names, str):
                                names_to_check = [button_names]
                            else:
                                names_to_check = button_names

                            # Check if any of the button names match our mapping
                            mapped_key = None
                            for name in names_to_check:
                                if name in self.button_mapping:
                                    mapped_key = self.button_mapping[name]
                                    break

                            if mapped_key:
                                action = "keydown" if event.value == 1 else "keyup"
                                self._send_input(mapped_key, action, display)

                    # Handle D-pad (absolute axis events)
                    elif event.type == ecodes.EV_ABS:
                        abs_names = ecodes.ABS[event.code] if event.code in ecodes.ABS else None

                        # Handle tuple or string names
                        if isinstance(abs_names, str):
                            abs_name = abs_names
                        elif isinstance(abs_names, tuple):
                            abs_name = abs_names[0]  # Use first name
                        else:
                            abs_name = None

                        # D-pad X axis (Left/Right)
                        if abs_name == "ABS_HAT0X":
                            old_state = dpad_x_state
                            dpad_x_state = event.value

                            # Release old key
                            if old_state == -1:
                                self._send_input("Left", "keyup", display)
                            elif old_state == 1:
                                self._send_input("Right", "keyup", display)

                            # Press new key
                            if dpad_x_state == -1:
                                self._send_input("Left", "keydown", display)
                            elif dpad_x_state == 1:
                                self._send_input("Right", "keydown", display)

                        # D-pad Y axis (Up/Down)
                        elif abs_name == "ABS_HAT0Y":
                            old_state = dpad_y_state
                            dpad_y_state = event.value

                            # Release old key
                            if old_state == -1:
                                self._send_input("Up", "keyup", display)
                            elif old_state == 1:
                                self._send_input("Down", "keyup", display)

                            # Press new key
                            if dpad_y_state == -1:
                                self._send_input("Up", "keydown", display)
                            elif dpad_y_state == 1:
                                self._send_input("Down", "keydown", display)

        except Exception as e:
            print(f"[BluetoothBridge] Input reading error for {mac}: {e}")

    def _send_input(self, key: str, action: str, display: str):
        """Send input to launcher via MQTT"""
        message = {
            "key": key,
            "action": action,
            "display": display
        }

        # Use QoS 0 for lowest latency (fire and forget)
        self.mqtt_client.publish(
            "protogen/fins/launcher/input/exec",
            json.dumps(message),
            qos=0
        )

        # Only log keydown to reduce console spam
        if action == "keydown":
            print(f"[BluetoothBridge] {key} -> {display}")

    def publish_scanning_status(self):
        """Publish scanning status"""
        self.mqtt_client.publish(
            "protogen/fins/bluetoothbridge/status/scanning",
            json.dumps(self.scanning),
            retain=True
        )

    def publish_devices_status(self):
        """Publish discovered devices list"""
        devices_list = list(self.discovered_devices.values())
        self.mqtt_client.publish(
            "protogen/fins/bluetoothbridge/status/devices",
            json.dumps(devices_list),
            retain=True
        )

    def publish_assignments_status(self):
        """Publish controller assignments"""
        assignments = {}
        for display, mac in self.assignments.items():
            if mac:
                # Always publish the assignment, even if device is not currently connected
                # This allows assignments to persist across disconnects
                device_info = self.connected_devices.get(mac) or self.discovered_devices.get(mac)
                assignments[display] = {
                    "mac": mac,
                    "name": device_info["name"] if device_info else mac,
                    "connected": mac in self.connected_devices
                }
            else:
                assignments[display] = None

        self.mqtt_client.publish(
            "protogen/fins/bluetoothbridge/status/assignments",
            json.dumps(assignments),
            retain=True
        )

    def publish_audio_devices_status(self):
        """Publish Bluetooth audio devices list"""
        audio_devices_list = list(self.audio_devices.values())
        self.mqtt_client.publish(
            "protogen/fins/bluetoothbridge/status/audio_devices",
            json.dumps(audio_devices_list),
            retain=True
        )

    def publish_last_audio_device(self, mac: str):
        """Publish last connected audio device (for auto-reconnect after reboot)"""
        device_info = self.audio_devices.get(mac)
        if device_info:
            last_device = {
                "mac": mac,
                "name": device_info.get("name", mac),
                "timestamp": time.time()
            }
            self.mqtt_client.publish(
                "protogen/fins/bluetoothbridge/status/last_audio_device",
                json.dumps(last_device),
                retain=True
            )
            print(f"[BluetoothBridge] Saved last audio device: {device_info.get('name', mac)}")

    def publish_connection_status(self, mac: str, status: str, error: str = None):
        """Publish connection status for a device

        Args:
            mac: Device MAC address
            status: "connecting", "connected", or "failed"
            error: Optional error message if status is "failed"
        """
        device_info = self.discovered_devices.get(mac) or self.audio_devices.get(mac)
        connection_status = {
            "mac": mac,
            "name": device_info.get("name", mac) if device_info else mac,
            "status": status,
            "timestamp": time.time()
        }
        if error:
            connection_status["error"] = error

        # Non-retained message (ephemeral status)
        self.mqtt_client.publish(
            "protogen/fins/bluetoothbridge/status/connection",
            json.dumps(connection_status),
            retain=False
        )

    def publish_all_status(self):
        """Publish all status topics"""
        self.publish_scanning_status()
        self.publish_devices_status()
        self.publish_assignments_status()
        self.publish_audio_devices_status()

    def cleanup(self):
        """Clean up all resources"""
        print("[BluetoothBridge] Cleaning up...")

        # Stop scanning
        self.stop_scan()

        # Stop monitor
        if self.monitor_process:
            try:
                self.monitor_process.stdin.write("quit\n")
                self.monitor_process.stdin.flush()
                self.monitor_process.terminate()
                self.monitor_process.wait(timeout=2)
            except Exception as e:
                print(f"[BluetoothBridge] Error stopping monitor: {e}")
                if self.monitor_process:
                    self.monitor_process.kill()

        # Stop all input reading
        for mac in list(self.input_threads.keys()):
            self._stop_input_reading(mac)

        # Disconnect MQTT
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

        print("[BluetoothBridge] Cleanup complete")

    def run(self):
        """Main run loop"""
        print("[BluetoothBridge] Starting bluetooth bridge...")

        if not EVDEV_AVAILABLE:
            print("[BluetoothBridge] ERROR: evdev library not installed!")
            print("[BluetoothBridge] Install with: pip install evdev")
            return

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Always restart Bluetooth service on startup for clean state
        print("[BluetoothBridge] Restarting Bluetooth service on startup...")
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "bluetooth"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print("[BluetoothBridge] ✓ Bluetooth service restarted successfully")
                time.sleep(3)  # Wait for Bluetooth to stabilize
            else:
                print(f"[BluetoothBridge] ⚠ Failed to restart Bluetooth: {result.stderr}")
        except Exception as e:
            print(f"[BluetoothBridge] ⚠ Error restarting Bluetooth on startup: {e}")

        # Unblock and power on all Bluetooth adapters
        print("[BluetoothBridge] Ensuring Bluetooth adapters are ready...")
        try:
            # Unblock Bluetooth via rfkill
            subprocess.run(["sudo", "rfkill", "unblock", "bluetooth"], capture_output=True, timeout=5)
            time.sleep(0.5)

            # Power on both adapters via hciconfig
            for adapter in ["hci0", "hci1"]:
                result = subprocess.run(
                    ["sudo", "hciconfig", adapter, "up"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    print(f"[BluetoothBridge] ✓ {adapter} powered on")
                else:
                    # Not an error if adapter doesn't exist
                    if "No such device" not in result.stderr:
                        print(f"[BluetoothBridge] ⚠ {adapter}: {result.stderr.strip()}")
        except Exception as e:
            print(f"[BluetoothBridge] ⚠ Error powering on adapters: {e}")

        # Set running flag before starting any threads
        self.running = True

        # Initialize MQTT
        self.init_mqtt()

        # Auto-reconnect to previously paired devices after initialization
        self._auto_reconnect_devices()

        print("[BluetoothBridge] Bluetooth bridge is running. Press Ctrl+C to exit.")

        # Keep running
        try:
            while self.running:
                signal.pause()
        except KeyboardInterrupt:
            print("\n[BluetoothBridge] Keyboard interrupt received")

        self.cleanup()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n[BluetoothBridge] Received signal {signum}, shutting down...")
        self.running = False


def main():
    """Main entry point"""
    bridge = BluetoothBridge()
    bridge.run()


if __name__ == "__main__":
    main()

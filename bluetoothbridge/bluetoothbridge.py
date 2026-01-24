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
        """Background worker for monitoring Bluetooth connection state changes"""
        try:
            # Start bluetoothctl in interactive mode
            self.monitor_process = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            print("[BluetoothBridge] Monitor worker started")

            # Parse bluetoothctl output for connection changes
            while self.running and self.monitor_process and self.monitor_process.poll() is None:
                line = self.monitor_process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                # Strip ANSI escape codes
                line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                line = line.rstrip()

                # Skip empty lines and bluetoothctl prompts
                if not line or line.startswith('[bluetoothctl]'):
                    continue

                # Parse connection state changes: [CHG] Device AA:BB:CC:DD:EE:FF Connected: yes/no
                if '[CHG]' in line and 'Connected:' in line:
                    match = re.search(r'\[CHG\]\s+Device\s+([0-9A-F:]+)\s+Connected:\s+(yes|no)', line, re.IGNORECASE)
                    if match:
                        mac = match.group(1).upper()
                        connected = match.group(2).lower() == 'yes'

                        # Process known gamepads
                        if mac in self.discovered_devices:
                            if connected:
                                print(f"[BluetoothBridge] 🎮 Controller connected: {mac}")
                                self._handle_controller_connected(mac)
                            else:
                                print(f"[BluetoothBridge] 🎮 Controller disconnected: {mac}")
                                self._handle_controller_disconnected(mac)
                        
                        # Process known audio devices
                        elif mac in self.audio_devices:
                            if connected:
                                print(f"[BluetoothBridge] 🔊 Audio device connected: {mac}")
                                self._handle_audio_device_connected(mac)
                            else:
                                print(f"[BluetoothBridge] 🔊 Audio device disconnected: {mac}")
                                self._handle_audio_device_disconnected(mac)

        except Exception as e:
            print(f"[BluetoothBridge] Monitor error: {e}")
            import traceback
            traceback.print_exc()

    def _handle_controller_connected(self, mac: str):
        """Handle a controller connecting automatically"""
        try:
            # Wait a moment for device to appear in /dev/input
            time.sleep(2)

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
            if audio_count > 0:
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
            time.sleep(0.5)
            
            proc.stdin.write(f"connect {mac}\n")
            proc.stdin.flush()
            time.sleep(3)
            
            proc.stdin.write("quit\n")
            proc.stdin.flush()
            
            output, _ = proc.communicate(timeout=5)
            
            if "Connection successful" in output or "already connected" in output.lower():
                print(f"[BluetoothBridge] ✓ Reconnected: {mac}")
            else:
                print(f"[BluetoothBridge] ⚠ Reconnect may have failed for {mac}")
                
        except Exception as e:
            print(f"[BluetoothBridge] Error reconnecting {mac}: {e}")

    def connect_device(self, mac: str):
        """Connect to a Bluetooth device"""
        print(f"[BluetoothBridge] Connecting to {mac}...")

        try:
            # Get the appropriate adapter for this device
            adapter = self._get_adapter_for_device(mac)
            adapter_mac = self._get_adapter_mac(adapter)
            print(f"[BluetoothBridge] Using adapter: {adapter} ({adapter_mac})")

            # Start bluetoothctl in interactive mode and keep it running
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
            time.sleep(0.5)
            
            # Trust device
            proc.stdin.write(f"trust {mac}\n")
            proc.stdin.flush()
            time.sleep(0.5)
            
            # Pair device
            print(f"[BluetoothBridge] Pairing to {mac}...")
            proc.stdin.write(f"pair {mac}\n")
            proc.stdin.flush()
            time.sleep(5)  # Wait for pairing to complete
            
            # Connect device
            print(f"[BluetoothBridge] Connecting to {mac}...")
            proc.stdin.write(f"connect {mac}\n")
            proc.stdin.flush()
            time.sleep(5)  # Wait for connection to complete
            
            # Quit
            proc.stdin.write("quit\n")
            proc.stdin.flush()
            
            # Get output
            output, _ = proc.communicate(timeout=5)
            result = type('obj', (object,), {'stdout': output, 'stderr': '', 'returncode': proc.returncode})()

            # Combine stdout and stderr for checking
            output = result.stdout + result.stderr
            
            # Check for common Bluetooth errors
            if "org.bluez.Error.NotReady" in output:
                print("[BluetoothBridge] ✗ Bluetooth service is not ready!")
                print("[BluetoothBridge] → Try restarting Bluetooth via the web interface or MQTT:")
                print("[BluetoothBridge]   mosquitto_pub -t 'protogen/fins/bluetoothbridge/bluetooth/restart' -m ''")
                return
            
            # Check for audio profile issues
            if "br-connection-profile-unavailable" in output or "profile unavailable" in output.lower():
                print("[BluetoothBridge] ✗ Bluetooth profile unavailable!")
                print("[BluetoothBridge] → This usually means PulseAudio/PipeWire Bluetooth modules aren't loaded.")
                print("[BluetoothBridge] → Try these fixes:")
                print("[BluetoothBridge]   1. Restart PulseAudio: pulseaudio -k && pulseaudio --start")
                print("[BluetoothBridge]   2. Or restart PipeWire: systemctl --user restart pipewire pipewire-pulse")
                print("[BluetoothBridge]   3. Install bluetooth packages: sudo apt install pulseaudio-module-bluetooth pipewire-audio-modules")
                return

            # Check if connection succeeded or was already established
            if result.returncode == 0 or "Connection successful" in output or "already connected" in output.lower():
                if "already connected" in output.lower():
                    print(f"[BluetoothBridge] ✓ Device {mac} was already connected")
                else:
                    print(f"[BluetoothBridge] ✓ Connected to {mac}")

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
                        print(f"[BluetoothBridge] ✓ Gamepad ready: {device_info.get('name', mac)}")
                    else:
                        print(f"[BluetoothBridge] ✗ Could not find evdev device for {mac}")
                else:
                    print(f"[BluetoothBridge] ⚠ Unknown device type for {mac}")

            else:
                print(f"[BluetoothBridge] ✗ Failed to connect:")
                print(f"[BluetoothBridge]   Output: {output.strip()}")

        except Exception as e:
            print(f"[BluetoothBridge] Connection error: {e}")

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

            print(f"[BluetoothBridge] Looking for evdev device for MAC {mac}")
            print(f"[BluetoothBridge] Already assigned devices: {already_assigned}")

            for device in devices:
                # Skip if this device is already assigned to another controller
                if device.path in already_assigned:
                    continue

                # Check if device has gamepad capabilities
                caps = device.capabilities()
                has_buttons = ecodes.EV_KEY in caps
                has_abs = ecodes.EV_ABS in caps

                if has_buttons or has_abs:
                    # Check if physical address matches (Bluetooth devices have phys with MAC)
                    phys = device.phys
                    print(f"[BluetoothBridge]   Checking {device.path} ({device.name}), phys: {phys}")
                    if phys and mac.replace(":", "").lower() in phys.lower().replace(":", ""):
                        print(f"[BluetoothBridge] ✓ Found evdev device by MAC: {device.path} ({device.name})")
                        return device.path

            # If not found by MAC, look for unassigned gamepad devices
            print(f"[BluetoothBridge] Could not find device by MAC, trying fallback...")
            for device in devices:
                # Skip if already assigned
                if device.path in already_assigned:
                    continue

                caps = device.capabilities()
                has_buttons = ecodes.EV_KEY in caps
                has_abs = ecodes.EV_ABS in caps

                if has_buttons and has_abs:
                    # Check for typical gamepad buttons
                    if ecodes.EV_KEY in caps:
                        keys = caps[ecodes.EV_KEY]
                        if ecodes.BTN_SOUTH in keys or ecodes.BTN_GAMEPAD in keys:
                            print(f"[BluetoothBridge] ✓ Found unassigned gamepad device: {device.path} ({device.name})")
                            return device.path

            print(f"[BluetoothBridge] ✗ No evdev device found for {mac}")

        except Exception as e:
            print(f"[BluetoothBridge] Error finding evdev device: {e}")

        return None

    def disconnect_device(self, mac: str):
        """Disconnect a Bluetooth device"""
        print(f"[BluetoothBridge] Disconnecting {mac}...")

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

            # Disconnect via bluetoothctl
            if adapter_mac:
                commands = f"select {adapter_mac}\ndisconnect {mac}\nquit\n"
                subprocess.run(
                    ["bluetoothctl"],
                    input=commands,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                # Fallback to default adapter
                subprocess.run(["bluetoothctl", "disconnect", mac], timeout=10)

            # Update state for gamepads
            if mac in self.connected_devices:
                del self.connected_devices[mac]

            if mac in self.discovered_devices:
                self.discovered_devices[mac]["connected"] = False

            # Update state for audio devices
            if mac in self.audio_devices:
                self.audio_devices[mac]["connected"] = False

            # Clear gamepad assignment
            for display, assigned_mac in self.assignments.items():
                if assigned_mac == mac:
                    self.assignments[display] = None

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

            # Get the appropriate adapter for this device
            adapter = self._get_adapter_for_device(mac)
            adapter_mac = self._get_adapter_mac(adapter)

            # Remove/unpair via bluetoothctl
            if adapter_mac:
                commands = f"select {adapter_mac}\nremove {mac}\nquit\n"
                result = subprocess.run(
                    ["bluetoothctl"],
                    input=commands,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                # Fallback to default adapter
                result = subprocess.run(
                    ["bluetoothctl", "remove", mac],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

            if result.returncode == 0 or "Device has been removed" in result.stdout:
                print(f"[BluetoothBridge] ✓ Unpaired {mac}")

                # Remove from discovered gamepad devices
                if mac in self.discovered_devices:
                    del self.discovered_devices[mac]
                    self.publish_devices_status()

                # Remove from audio devices
                if mac in self.audio_devices:
                    del self.audio_devices[mac]
                    self.publish_audio_devices_status()

            else:
                print(f"[BluetoothBridge] ✗ Failed to unpair: {result.stderr}")

        except Exception as e:
            print(f"[BluetoothBridge] Unpair error: {e}")

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

            # Clear device state
            old_assignments = dict(self.assignments)  # Save assignments
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

                # Auto-reconnect to previously connected devices
                print("[BluetoothBridge] Auto-reconnecting previously connected devices...")
                
                # Reconnect audio devices that were connected before restart
                for mac, device_info in list(self.audio_devices.items()):
                    if device_info.get("paired"):
                        print(f"[BluetoothBridge] Reconnecting audio device: {device_info.get('name', mac)}")
                        threading.Thread(
                            target=self._reconnect_device,
                            args=(mac,),
                            daemon=True
                        ).start()
                        time.sleep(1)  # Stagger reconnections

                # Reconnect gamepads that have assignments
                for display, mac in old_assignments.items():
                    if mac and mac in self.discovered_devices:
                        device_info = self.discovered_devices[mac]
                        if device_info.get("paired") and not device_info.get("connected"):
                            print(f"[BluetoothBridge] Reconnecting gamepad: {device_info.get('name', mac)} (assigned to {display})")
                            threading.Thread(
                                target=self._reconnect_device,
                                args=(mac,),
                                daemon=True
                            ).start()
                            time.sleep(1)  # Stagger reconnections

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
            # Remove assignment
            self.assignments[display] = None
            print(f"[BluetoothBridge] Removed assignment for {display} display")
            self.publish_assignments_status()
            return

        if mac not in self.connected_devices:
            print(f"[BluetoothBridge] Cannot assign {mac}: not connected")
            return

        # Assign controller to display
        self.assignments[display] = mac

        print(f"[BluetoothBridge] Assigned {mac} to {display} display")
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
                    events = device.read()
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
                    continue  # Not assigned to any display

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

        # Initialize MQTT
        self.init_mqtt()

        self.running = True
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

"""
ControllerBridge - Gamepad Input Management Service
Monitors Bluetooth gamepad connections, reads evdev input, and forwards to launcher via MQTT.
"""

import paho.mqtt.client as mqtt
import signal
import json
import select
import threading
import time
import sys
import os
from typing import Optional, Dict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from utils.mqtt_client import create_mqtt_client
from utils.notifications import publish_notification


try:
    import evdev
    from evdev import InputDevice, ecodes
    EVDEV_AVAILABLE = True
except ImportError as e:
    EVDEV_AVAILABLE = False
    print(f"[ControllerBridge] Warning: evdev not available: {e}")
    print("[ControllerBridge] Install with: pip install evdev")
except Exception as e:
    EVDEV_AVAILABLE = False
    print(f"[ControllerBridge] Error loading evdev: {e}")


class ControllerBridge:
    """
    Gamepad Input Management Service

    Reacts to bluetoothbridge device status to detect gamepad connections,
    manages evdev input reading, and forwards input to launcher.

    Subscribes to:
        - protogen/fins/bluetoothbridge/status/devices
        - protogen/fins/controllerbridge/assign
        - protogen/fins/controllerbridge/status/assignments  (retained restore)

    Publishes:
        - protogen/fins/controllerbridge/status/assignments
        - protogen/fins/launcher/input/exec
        - protogen/global/notifications
    """

    def __init__(self):
        self.running = True
        self.config_loader = ConfigLoader()
        self.mqtt_client: Optional[mqtt.Client] = None

        # Device tracking
        self.known_devices: Dict[str, Dict] = {}      # {mac: {name, connected}} from bluetoothbridge
        self.connected_devices: Dict[str, Dict] = {}   # {mac: {name, evdev_path}}
        self.assignments: Dict[str, Optional[str]] = {"left": None, "right": None}

        # Input reading threads
        self.input_threads: Dict[str, threading.Thread] = {}
        self.input_stop_events: Dict[str, threading.Event] = {}

        # Button mapping
        self.button_mapping = self._load_button_mapping()

        print("[ControllerBridge] Initialized")

    def _load_button_mapping(self) -> Dict:
        """Load button mapping from config."""
        try:
            config = self.config_loader.config
            cb_config = config.get("controllerbridge", config.get("bluetoothbridge", {}))
            if "button_mapping" in cb_config:
                return cb_config["button_mapping"]
        except Exception as e:
            print(f"[ControllerBridge] Error loading button mapping: {e}")

        return {
            "BTN_SOUTH": "a",
            "BTN_EAST": "b",
            "ABS_HAT0X": "dpad_x",
            "ABS_HAT0Y": "dpad_y",
        }

    # ======== MQTT ========

    def init_mqtt(self):
        """Initialize MQTT connection and subscriptions."""
        print("[ControllerBridge] Initializing MQTT...")

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                print("[ControllerBridge] Connected to MQTT broker")
                client.subscribe("protogen/fins/bluetoothbridge/status/devices")
                client.subscribe("protogen/fins/controllerbridge/assign")
                client.subscribe("protogen/fins/controllerbridge/status/assignments")
                client.subscribe("protogen/fins/config/reload")
                client.subscribe("protogen/fins/controllerbridge/config/reload")
            else:
                print(f"[ControllerBridge] Failed to connect to MQTT: {rc}")

        def on_message(client, userdata, msg):
            self.on_mqtt_message(msg.topic, msg.payload.decode())

        self.mqtt_client = create_mqtt_client(self.config_loader)
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_message = on_message
        self.mqtt_client.loop_start()

        # Wait briefly for retained assignments
        time.sleep(0.5)

    def on_mqtt_message(self, topic: str, payload: str):
        """Handle incoming MQTT messages."""
        try:
            if topic == "protogen/fins/bluetoothbridge/status/devices":
                self._handle_devices_update(payload)
            elif topic == "protogen/fins/controllerbridge/assign":
                self._handle_assign(payload)
            elif topic == "protogen/fins/controllerbridge/status/assignments":
                self._restore_assignments(payload)
            elif topic in ("protogen/fins/config/reload", "protogen/fins/controllerbridge/config/reload"):
                self.handle_config_reload()
        except Exception as e:
            print(f"[ControllerBridge] Error handling {topic}: {e}")
            import traceback
            traceback.print_exc()

    def handle_config_reload(self):
        """Reload configuration from file."""
        print("[ControllerBridge] Reloading configuration...")
        self.config_loader.reload()
        self._load_button_mapping()
        print("[ControllerBridge] Configuration reloaded")

    # ======== Device Tracking ========

    def _handle_devices_update(self, payload: str):
        """Handle gamepad device list updates from bluetoothbridge."""
        try:
            devices = json.loads(payload)
            current_macs = set()

            for device in devices:
                mac = device.get("mac")
                name = device.get("name", mac)
                connected = device.get("connected", False)
                current_macs.add(mac)

                was_connected = mac in self.connected_devices

                if connected and not was_connected:
                    # New connection — find evdev and start reading
                    self.known_devices[mac] = {"name": name, "connected": True}
                    self._handle_controller_connected(mac, name)
                elif not connected and was_connected:
                    # Disconnected
                    self._handle_controller_disconnected(mac, name)
                    if mac in self.known_devices:
                        self.known_devices[mac]["connected"] = False

            # Handle devices that disappeared entirely (unpaired)
            for mac in list(self.connected_devices.keys()):
                if mac not in current_macs:
                    name = self.connected_devices[mac].get("name", mac)
                    self._handle_controller_disconnected(mac, name)

        except Exception as e:
            print(f"[ControllerBridge] Error handling devices update: {e}")

    def _handle_controller_connected(self, mac: str, name: str):
        """Handle a gamepad connecting."""
        if not EVDEV_AVAILABLE:
            print("[ControllerBridge] evdev not available, cannot read input")
            return

        try:
            # Retry evdev discovery — kernel may need time to create the input device
            evdev_path = None
            for attempt in range(5):
                time.sleep(2)
                evdev_path = self._find_evdev_device(mac, name)
                if evdev_path:
                    break
                print(f"[ControllerBridge] evdev not found for {mac}, retrying ({attempt + 1}/5)...")

            if evdev_path:
                self.connected_devices[mac] = {
                    "name": name,
                    "evdev_path": evdev_path,
                }
                self._start_input_reading(mac)
                self.publish_assignments_status()
                print(f"[ControllerBridge] Controller ready: {name} ({mac})")
            else:
                print(f"[ControllerBridge] Could not find evdev device for {mac} after 5 attempts")

        except Exception as e:
            print(f"[ControllerBridge] Error handling connected controller: {e}")

    def _handle_controller_disconnected(self, mac: str, name: str):
        """Handle a gamepad disconnecting."""
        try:
            if mac in self.input_threads:
                self._stop_input_reading(mac)

            if mac in self.connected_devices:
                del self.connected_devices[mac]

            self.publish_assignments_status()
            print(f"[ControllerBridge] Controller disconnected: {name} ({mac})")

        except Exception as e:
            print(f"[ControllerBridge] Error handling disconnected controller: {e}")

    # ======== evdev Device Matching ========

    def _find_evdev_device(self, mac: str, name: str = None) -> Optional[str]:
        """Find evdev device path for a Bluetooth MAC address.

        Three-pass matching:
        1. MAC in phys field (most reliable)
        2. Exact device name match
        3. Single unassigned gamepad fallback
        """
        if not EVDEV_AVAILABLE:
            return None

        try:
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

            already_assigned = set(
                info["evdev_path"]
                for info in self.connected_devices.values()
                if "evdev_path" in info
            )

            expected_name = (name or "").lower()
            print(f"[ControllerBridge] Looking for evdev device for {mac} (name: {expected_name})")
            for d in devices:
                caps = d.capabilities()
                has_keys = ecodes.EV_KEY in caps
                has_abs = ecodes.EV_ABS in caps
                if has_keys or has_abs:
                    print(f"[ControllerBridge]   evdev: {d.path} name={d.name!r} phys={d.phys!r}")

            # Pass 1: MAC in uniq field (device's actual BT address)
            # Require gamepad buttons to avoid matching touchpad/motion event devices
            mac_normalized = mac.replace(":", "").lower()
            for device in devices:
                if device.path in already_assigned:
                    continue
                caps = device.capabilities()
                if ecodes.EV_KEY in caps and ecodes.EV_ABS in caps:
                    keys = caps[ecodes.EV_KEY]
                    if ecodes.BTN_SOUTH in keys or ecodes.BTN_GAMEPAD in keys:
                        uniq = device.uniq
                        if uniq and mac_normalized == uniq.replace(":", "").lower():
                            print(f"[ControllerBridge] Found by MAC (uniq): {device.path} ({device.name})")
                            return device.path

            # Pass 2: exact name match, then substring
            if expected_name:
                substring_match = None
                for device in devices:
                    if device.path in already_assigned:
                        continue
                    caps = device.capabilities()
                    if ecodes.EV_KEY in caps and ecodes.EV_ABS in caps:
                        dev_name = device.name.lower()
                        if expected_name == dev_name:
                            print(f"[ControllerBridge] Found by exact name: {device.path} ({device.name})")
                            return device.path
                        if not substring_match and (expected_name in dev_name or dev_name in expected_name):
                            substring_match = device

                if substring_match:
                    print(f"[ControllerBridge] Found by substring name: {substring_match.path} ({substring_match.name})")
                    return substring_match.path

            # Pass 3: single unassigned gamepad fallback
            unassigned = []
            for device in devices:
                if device.path in already_assigned:
                    continue
                caps = device.capabilities()
                if ecodes.EV_KEY in caps and ecodes.EV_ABS in caps:
                    keys = caps[ecodes.EV_KEY]
                    if ecodes.BTN_SOUTH in keys or ecodes.BTN_GAMEPAD in keys:
                        unassigned.append(device)

            if len(unassigned) == 1:
                device = unassigned[0]
                print(f"[ControllerBridge] Found single unassigned gamepad: {device.path} ({device.name})")
                return device.path
            elif len(unassigned) > 1:
                print(f"[ControllerBridge] Multiple unassigned gamepads, cannot determine: "
                      f"{[d.name for d in unassigned]}")

            print(f"[ControllerBridge] No evdev device found for {mac}")

        except Exception as e:
            print(f"[ControllerBridge] Error finding evdev device: {e}")

        return None

    # ======== Input Reading ========

    def _start_input_reading(self, mac: str):
        """Start reading input from a gamepad."""
        if not EVDEV_AVAILABLE:
            return

        if mac in self.input_threads and self.input_threads[mac].is_alive():
            return

        device_info = self.connected_devices.get(mac)
        if not device_info:
            return

        stop_event = threading.Event()
        self.input_stop_events[mac] = stop_event

        thread = threading.Thread(
            target=self._input_reading_worker,
            args=(mac, device_info["evdev_path"], stop_event),
            daemon=True,
        )
        self.input_threads[mac] = thread
        thread.start()

        # Log assignment state
        assigned_display = None
        for disp, assigned_mac in self.assignments.items():
            if assigned_mac == mac:
                assigned_display = disp
                break
        if assigned_display:
            print(f"[ControllerBridge] Input reading started for {mac} -> {assigned_display}")
        else:
            print(f"[ControllerBridge] Input reading started for {mac} (not assigned)")

    def _stop_input_reading(self, mac: str):
        """Stop reading input from a gamepad."""
        if mac in self.input_stop_events:
            self.input_stop_events[mac].set()

        if mac in self.input_threads:
            self.input_threads[mac].join(timeout=2)
            del self.input_threads[mac]

        if mac in self.input_stop_events:
            del self.input_stop_events[mac]

    def _input_reading_worker(self, mac: str, evdev_path: str, stop_event: threading.Event):
        """Worker thread for reading gamepad input."""
        try:
            device = evdev.InputDevice(evdev_path)
            print(f"[ControllerBridge] Reading from {device.name} at {evdev_path}")

            button_states = {}
            dpad_x_state = 0
            dpad_y_state = 0
            was_assigned = False

            while not stop_event.is_set():
                r, _, _ = select.select([device.fd], [], [], 0.01)
                if not r:
                    continue

                try:
                    events = list(device.read())
                except (BlockingIOError, OSError):
                    continue

                if not events:
                    continue

                # Find assignment
                display = None
                for disp, assigned_mac in self.assignments.items():
                    if assigned_mac == mac:
                        display = disp
                        break

                if not display:
                    was_assigned = False
                    continue

                # Discard buffered events on first assignment
                if not was_assigned:
                    print(f"[ControllerBridge] {mac} assigned to {display}, discarding {len(events)} buffered events")
                    was_assigned = True
                    continue

                for event in events:
                    if event.type == ecodes.EV_KEY:
                        button_names = ecodes.BTN.get(event.code)
                        if button_names:
                            if isinstance(button_names, str):
                                names_to_check = [button_names]
                            else:
                                names_to_check = button_names

                            mapped_key = None
                            for name in names_to_check:
                                if name in self.button_mapping:
                                    mapped_key = self.button_mapping[name]
                                    break

                            if mapped_key:
                                action = "keydown" if event.value == 1 else "keyup"
                                self._send_input(mapped_key, action, display)

                    elif event.type == ecodes.EV_ABS:
                        abs_names = ecodes.ABS.get(event.code)
                        if isinstance(abs_names, str):
                            abs_name = abs_names
                        elif isinstance(abs_names, tuple):
                            abs_name = abs_names[0]
                        else:
                            abs_name = None

                        if abs_name == "ABS_HAT0X":
                            old = dpad_x_state
                            dpad_x_state = event.value
                            if old == -1:
                                self._send_input("Left", "keyup", display)
                            elif old == 1:
                                self._send_input("Right", "keyup", display)
                            if dpad_x_state == -1:
                                self._send_input("Left", "keydown", display)
                            elif dpad_x_state == 1:
                                self._send_input("Right", "keydown", display)

                        elif abs_name == "ABS_HAT0Y":
                            old = dpad_y_state
                            dpad_y_state = event.value
                            if old == -1:
                                self._send_input("Up", "keyup", display)
                            elif old == 1:
                                self._send_input("Down", "keyup", display)
                            if dpad_y_state == -1:
                                self._send_input("Up", "keydown", display)
                            elif dpad_y_state == 1:
                                self._send_input("Down", "keydown", display)

        except Exception as e:
            print(f"[ControllerBridge] Input reading error for {mac}: {e}")

    def _send_input(self, key: str, action: str, display: str):
        """Send input to launcher via MQTT (QoS 0 for low latency)."""
        message = {"key": key, "action": action, "display": display}
        self.mqtt_client.publish("protogen/fins/launcher/input/exec", json.dumps(message), qos=0)
        if action == "keydown":
            print(f"[ControllerBridge] {key} -> {display}")

    # ======== Assignments ========

    def _handle_assign(self, payload: str):
        """Handle assignment command from web UI."""
        try:
            data = json.loads(payload)
            mac = data.get("mac")
            display = data.get("display")
            if display:
                self.assign_display(mac, display)
        except Exception as e:
            print(f"[ControllerBridge] Error handling assign: {e}")

    def assign_display(self, mac: Optional[str], display: str):
        """Assign a controller to a display (or remove if mac is None)."""
        if mac is None:
            old_mac = self.assignments.get(display)
            self.assignments[display] = None
            print(f"[ControllerBridge] Removed assignment for {display}")

            if old_mac and old_mac in self.connected_devices:
                self._stop_input_reading(old_mac)
                self._start_input_reading(old_mac)

            self.publish_assignments_status()
            return

        if mac not in self.connected_devices:
            print(f"[ControllerBridge] Cannot assign {mac}: not connected")
            return

        # Clear old assignment for this MAC
        for d, m in list(self.assignments.items()):
            if m == mac and d != display:
                self.assignments[d] = None

        self.assignments[display] = mac
        name = self.connected_devices[mac].get("name", mac)
        print(f"[ControllerBridge] Assigned {mac} to {display}")
        publish_notification(self.mqtt_client, "controller", "assigned",
                             "gamepad", f"{name} -> {display} display")

        # Restart input thread with new assignment
        if mac in self.input_threads:
            self._stop_input_reading(mac)
            self._start_input_reading(mac)

        self.publish_assignments_status()

    def _restore_assignments(self, payload: str):
        """Restore assignments from retained MQTT message."""
        try:
            if not payload:
                return
            data = json.loads(payload)
            for display in ["left", "right"]:
                if display in data and data[display]:
                    mac = data[display].get("mac")
                    if mac:
                        self.assignments[display] = mac
                        print(f"[ControllerBridge] Restored assignment: {mac} -> {display}")
        except Exception as e:
            print(f"[ControllerBridge] Error restoring assignments: {e}")

    # ======== Status Publishing ========

    def publish_assignments_status(self):
        """Publish controller assignments."""
        if not self.mqtt_client:
            return

        assignments = {}
        for display, mac in self.assignments.items():
            if mac:
                device_info = self.connected_devices.get(mac, self.known_devices.get(mac, {}))
                assignments[display] = {
                    "mac": mac,
                    "name": device_info.get("name", "Unknown"),
                    "connected": mac in self.connected_devices,
                }
            else:
                assignments[display] = None

        self.mqtt_client.publish(
            "protogen/fins/controllerbridge/status/assignments",
            json.dumps(assignments),
            retain=True,
        )

    # ======== Lifecycle ========

    def cleanup(self):
        """Clean up resources."""
        print("[ControllerBridge] Cleaning up...")

        # Stop all input threads
        for mac in list(self.input_threads.keys()):
            self._stop_input_reading(mac)

        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

    def run(self):
        """Main run loop."""
        print("[ControllerBridge] Starting...")

        if not EVDEV_AVAILABLE:
            print("[ControllerBridge] WARNING: evdev not available, input reading disabled")

        self.init_mqtt()
        print("[ControllerBridge] Running. Press Ctrl+C to stop.")

        while self.running:
            time.sleep(1)

        self.cleanup()
        print("[ControllerBridge] Stopped.")

    def _signal_handler(self, signum, frame):
        print(f"\n[ControllerBridge] Received signal {signum}, shutting down...")
        self.running = False


def main():
    bridge = ControllerBridge()
    signal.signal(signal.SIGINT, bridge._signal_handler)
    signal.signal(signal.SIGTERM, bridge._signal_handler)
    bridge.run()


if __name__ == "__main__":
    main()

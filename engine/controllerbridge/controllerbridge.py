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
        self.assignments: Dict[str, Optional[str]] = {"left": None, "right": None, "presets": None}

        # Input reading threads
        self.input_threads: Dict[str, threading.Thread] = {}
        self.input_stop_events: Dict[str, threading.Event] = {}

        # Button mapping
        self.button_mapping = self._load_button_mapping()

        # Preset combo detection
        self.preset_combos: Dict = {}       # {frozenset(btn_names): preset_name}
        self.combo_cooldown: Dict[str, float] = {}  # {mac: last_combo_time}

        # Assignment combo keys (e.g. PS+L1 -> left display)
        self.assignment_combos: Dict[str, frozenset] = {}
        self.assignment_colors: Dict[str, tuple] = {}
        self._load_assignment_config()

        # System action combos (detected on presets controller, restored from retained MQTT)
        self.action_combos: Dict[str, frozenset] = {}  # {action_id: frozenset(buttons)}
        self._pending_dangerous: Dict[str, float] = {}  # {action: timestamp} for double-tap safety

        # State tracking for toggle actions
        self.service_states = {"airplay": False, "spotify": False, "ap": False}
        self._current_volume = 50  # Tracked from audiobridge status

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

    def _load_assignment_config(self):
        """Load assignment combo keys and LED colors from config."""
        try:
            config = self.config_loader.config
            cb_config = config.get("controllerbridge", {})

            # Load assignment combos
            combos = cb_config.get("assignment_combos", {})
            self.assignment_combos = {}
            for slot, buttons in combos.items():
                if isinstance(buttons, list) and len(buttons) > 0:
                    self.assignment_combos[slot] = frozenset(buttons)
            if self.assignment_combos:
                print(f"[ControllerBridge] Loaded assignment combos: "
                      f"{', '.join(f'{s}={list(b)}' for s, b in self.assignment_combos.items())}")

            # Load assignment colors
            colors = cb_config.get("assignment_colors", {})
            self.assignment_colors = {}
            for slot, rgb in colors.items():
                if isinstance(rgb, list) and len(rgb) == 3:
                    self.assignment_colors[slot] = tuple(rgb)
            if self.assignment_colors:
                print(f"[ControllerBridge] Loaded assignment colors: "
                      f"{', '.join(f'{s}={c}' for s, c in self.assignment_colors.items())}")

        except Exception as e:
            print(f"[ControllerBridge] Error loading assignment config: {e}")

    # ======== LED Control ========

    def _find_led_path(self, evdev_path: str) -> Optional[str]:
        """Resolve evdev path to sysfs LED base path for DS4 controllers.

        Maps /dev/input/eventN -> /sys/class/leds/inputM: (N and M may differ).
        Returns the base path prefix (e.g. '/sys/class/leds/input15:') or None.
        """
        try:
            event_name = os.path.basename(evdev_path)  # "event6"
            sysfs_device = f"/sys/class/input/{event_name}/device"
            if not os.path.exists(sysfs_device):
                return None
            device_path = os.path.realpath(sysfs_device)
            input_name = os.path.basename(device_path)  # "input15"
            led_base = f"/sys/class/leds/{input_name}:"

            # Verify DS4 LEDs exist
            if os.path.exists(f"{led_base}red/brightness"):
                print(f"[ControllerBridge] Found LED path: {led_base}")
                return led_base
        except Exception as e:
            print(f"[ControllerBridge] Error finding LED path for {evdev_path}: {e}")
        return None

    def _set_led_color(self, mac: str, r: int, g: int, b: int):
        """Set DS4 light bar color via sysfs. Fails gracefully for non-DS4 controllers."""
        device_info = self.connected_devices.get(mac)
        if not device_info:
            return

        led_path = device_info.get("led_path")
        if not led_path:
            return

        try:
            for color, value in [("red", r), ("green", g), ("blue", b)]:
                with open(f"{led_path}{color}/brightness", "w") as f:
                    f.write(str(max(0, min(255, value))))
            print(f"[ControllerBridge] LED {mac}: ({r}, {g}, {b})")
        except (IOError, OSError) as e:
            print(f"[ControllerBridge] LED write failed for {mac}: {e}")

    def _set_led_for_slot(self, mac: str, slot: Optional[str]):
        """Set DS4 LED to the configured color for a given assignment slot."""
        if slot and slot in self.assignment_colors:
            r, g, b = self.assignment_colors[slot]
        elif "unassigned" in self.assignment_colors:
            r, g, b = self.assignment_colors["unassigned"]
        else:
            return
        self._set_led_color(mac, r, g, b)

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
                client.subscribe("protogen/fins/controllerbridge/combo/set")
                client.subscribe("protogen/fins/controllerbridge/color/set")
                client.subscribe("protogen/fins/controllerbridge/action_combo/set")
                client.subscribe("protogen/fins/controllerbridge/status/combo_config")
                client.subscribe("protogen/fins/controllerbridge/status/color_config")
                client.subscribe("protogen/fins/controllerbridge/status/action_combo_config")
                client.subscribe("protogen/fins/launcher/status/presets")
                client.subscribe("protogen/fins/config/reload")
                client.subscribe("protogen/fins/controllerbridge/config/reload")
                # Service state topics for toggle actions
                client.subscribe("protogen/fins/castbridge/status/airplay/health")
                client.subscribe("protogen/fins/castbridge/status/spotify/health")
                client.subscribe("protogen/fins/networkingbridge/status/ap")
                client.subscribe("protogen/fins/audiobridge/status/volume")
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

        # Combos, colors, and action combos all restored from retained MQTT messages.
        # Config.yaml provides defaults (loaded in __init__), overridden by retained msgs.

    def on_mqtt_message(self, topic: str, payload: str):
        """Handle incoming MQTT messages."""
        try:
            if topic == "protogen/fins/bluetoothbridge/status/devices":
                self._handle_devices_update(payload)
            elif topic == "protogen/fins/controllerbridge/assign":
                self._handle_assign(payload)
            elif topic == "protogen/fins/controllerbridge/status/assignments":
                self._restore_assignments(payload)
            elif topic == "protogen/fins/controllerbridge/combo/set":
                self._handle_combo_set(payload)
            elif topic == "protogen/fins/controllerbridge/color/set":
                self._handle_color_set(payload)
            elif topic == "protogen/fins/controllerbridge/action_combo/set":
                self._handle_action_combo_set(payload)
            elif topic == "protogen/fins/controllerbridge/status/combo_config":
                self._restore_combos(payload)
            elif topic == "protogen/fins/controllerbridge/status/color_config":
                self._restore_colors(payload)
            elif topic == "protogen/fins/controllerbridge/status/action_combo_config":
                self._restore_action_combos(payload)
            elif topic == "protogen/fins/launcher/status/presets":
                self._update_preset_combos(payload)
            elif topic == "protogen/fins/castbridge/status/airplay/health":
                self._update_service_state("airplay", payload)
            elif topic == "protogen/fins/castbridge/status/spotify/health":
                self._update_service_state("spotify", payload)
            elif topic == "protogen/fins/networkingbridge/status/ap":
                self._update_service_state("ap", payload)
            elif topic == "protogen/fins/audiobridge/status/volume":
                self._update_volume_state(payload)
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
                led_path = self._find_led_path(evdev_path)
                self.connected_devices[mac] = {
                    "name": name,
                    "evdev_path": evdev_path,
                    "led_path": led_path,
                }
                self._start_input_reading(mac)
                self.publish_assignments_status()

                # Set LED to assignment color (or unassigned)
                current_slot = None
                for slot, assigned_mac in self.assignments.items():
                    if assigned_mac == mac:
                        current_slot = slot
                        break
                self._set_led_for_slot(mac, current_slot)

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

    def _update_pressed_buttons(self, pressed_buttons: set, events) -> bool:
        """Update pressed button set from evdev events. Returns True if any button was pressed."""
        changed = False
        for event in events:
            if event.type == ecodes.EV_KEY:
                btn_names = ecodes.BTN.get(event.code)
                if btn_names:
                    if isinstance(btn_names, str):
                        btn_names = [btn_names]
                    for btn_name in btn_names:
                        if event.value == 1:
                            pressed_buttons.add(btn_name)
                            changed = True
                        elif event.value == 0:
                            pressed_buttons.discard(btn_name)

            elif event.type == ecodes.EV_ABS:
                abs_names = ecodes.ABS.get(event.code)
                if isinstance(abs_names, tuple):
                    abs_name = abs_names[0]
                elif isinstance(abs_names, str):
                    abs_name = abs_names
                else:
                    continue

                if abs_name == "ABS_HAT0X":
                    pressed_buttons.discard("DPAD_LEFT")
                    pressed_buttons.discard("DPAD_RIGHT")
                    if event.value == -1:
                        pressed_buttons.add("DPAD_LEFT")
                        changed = True
                    elif event.value == 1:
                        pressed_buttons.add("DPAD_RIGHT")
                        changed = True
                elif abs_name == "ABS_HAT0Y":
                    pressed_buttons.discard("DPAD_UP")
                    pressed_buttons.discard("DPAD_DOWN")
                    if event.value == -1:
                        pressed_buttons.add("DPAD_UP")
                        changed = True
                    elif event.value == 1:
                        pressed_buttons.add("DPAD_DOWN")
                        changed = True
                elif abs_name == "ABS_Z":
                    if event.value > 128:
                        if "ABS_Z" not in pressed_buttons:
                            pressed_buttons.add("ABS_Z")
                            changed = True
                    else:
                        pressed_buttons.discard("ABS_Z")
                elif abs_name == "ABS_RZ":
                    if event.value > 128:
                        if "ABS_RZ" not in pressed_buttons:
                            pressed_buttons.add("ABS_RZ")
                            changed = True
                    else:
                        pressed_buttons.discard("ABS_RZ")
        return changed

    def _input_reading_worker(self, mac: str, evdev_path: str, stop_event: threading.Event):
        """Worker thread for reading gamepad input."""
        try:
            device = evdev.InputDevice(evdev_path)
            print(f"[ControllerBridge] Reading from {device.name} at {evdev_path}")

            dpad_x_state = 0
            dpad_y_state = 0
            was_assigned = False
            pressed_buttons = set()  # Raw button names for combo detection
            first_read = True  # Discard first batch of buffered events

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

                # Discard initial buffered events from before we started reading
                if first_read:
                    first_read = False
                    pressed_buttons.clear()
                    continue

                # Always track pressed buttons (for assignment combos)
                combo_changed = self._update_pressed_buttons(pressed_buttons, events)

                # Check assignment combos (works regardless of current slot)
                if combo_changed and self.assignment_combos:
                    # Sort by length descending: PS+L1+R1 (3) before PS+L1 (2)
                    for slot, combo_set in sorted(
                        self.assignment_combos.items(),
                        key=lambda x: len(x[1]),
                        reverse=True
                    ):
                        if combo_set.issubset(pressed_buttons):
                            # Don't re-assign if already on this slot
                            current_slot = None
                            for s, m in self.assignments.items():
                                if m == mac:
                                    current_slot = s
                                    break
                            if current_slot != slot:
                                print(f"[ControllerBridge] Assignment combo: {mac} -> {slot}")
                                self.assign_display(mac, slot)
                            break

                # Find current assignment
                assigned_slot = None
                for slot, assigned_mac in self.assignments.items():
                    if assigned_mac == mac:
                        assigned_slot = slot
                        break

                if not assigned_slot:
                    was_assigned = False
                    continue

                # Discard buffered events on first assignment
                if not was_assigned:
                    print(f"[ControllerBridge] {mac} assigned to {assigned_slot}, discarding buffered events")
                    was_assigned = True
                    continue

                # Presets controller: preset combo + action combo detection, no input forwarding
                if assigned_slot == "presets":
                    if combo_changed and self.preset_combos:
                        now = time.time()
                        cooldown = self.combo_cooldown.get(mac, 0)
                        if now - cooldown >= 1.0:
                            # Sort by length descending so L1+DPAD_UP matches before DPAD_UP alone
                            for combo_set, preset_name in sorted(
                                self.preset_combos.items(),
                                key=lambda x: len(x[0]),
                                reverse=True
                            ):
                                if combo_set.issubset(pressed_buttons):
                                    print(f"[ControllerBridge] Combo matched: {preset_name}")
                                    self.combo_cooldown[mac] = now
                                    self.mqtt_client.publish(
                                        "protogen/fins/launcher/preset/activate",
                                        json.dumps({"name": preset_name}),
                                        qos=0
                                    )
                                    break
                    # Check system action combos
                    if combo_changed and self.action_combos:
                        for action_id, buttons in sorted(
                            self.action_combos.items(),
                            key=lambda x: len(x[1]),
                            reverse=True
                        ):
                            if buttons.issubset(pressed_buttons):
                                print(f"[ControllerBridge] Action combo matched: {action_id}")
                                self._execute_action(action_id)
                                break
                    continue

                # Left/right display: forward input to launcher
                display = assigned_slot
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
                self._set_led_for_slot(old_mac, None)
                self._restart_input_thread_if_safe(old_mac)

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

        # Set LED color for new assignment
        self._set_led_for_slot(mac, display)

        # Restart input thread (skip if called from within the input thread itself)
        self._restart_input_thread_if_safe(mac)

        self.publish_assignments_status()

    def _restart_input_thread_if_safe(self, mac: str):
        """Restart input thread unless we're being called from that thread (avoids deadlock)."""
        if mac in self.input_threads:
            if self.input_threads[mac] is threading.current_thread():
                # Called from combo within the input worker — thread picks up new slot naturally
                return
            self._stop_input_reading(mac)
            self._start_input_reading(mac)

    def _restore_assignments(self, payload: str):
        """Restore assignments from retained MQTT message."""
        try:
            if not payload:
                return
            data = json.loads(payload)
            for slot in ["left", "right", "presets"]:
                if slot in data and data[slot]:
                    mac = data[slot].get("mac")
                    if mac:
                        self.assignments[slot] = mac
                        print(f"[ControllerBridge] Restored assignment: {mac} -> {slot}")
        except Exception as e:
            print(f"[ControllerBridge] Error restoring assignments: {e}")

    def _update_preset_combos(self, payload: str):
        """Update preset combo lookup from launcher presets status."""
        try:
            data = json.loads(payload)
            combos = {}
            for preset in data.get("presets", []):
                combo = preset.get("gamepad_combo")
                if combo and len(combo) > 0:
                    key = frozenset(combo)
                    combos[key] = preset["name"]
            self.preset_combos = combos
            if combos:
                print(f"[ControllerBridge] Loaded {len(combos)} preset combos")
        except Exception as e:
            print(f"[ControllerBridge] Error updating preset combos: {e}")

    # ======== Assignment Combo Config ========

    def _handle_combo_set(self, payload: str):
        """Handle combo config update from web UI."""
        try:
            data = json.loads(payload)
            slot = data.get("slot")
            buttons = data.get("buttons")
            if not slot or slot not in ("left", "right", "presets"):
                return
            if not isinstance(buttons, list) or len(buttons) == 0:
                # Remove combo for this slot
                self.assignment_combos.pop(slot, None)
            else:
                self.assignment_combos[slot] = frozenset(buttons)

            print(f"[ControllerBridge] Updated assignment combo: {slot} = {buttons}")
            self.publish_combo_config()
        except Exception as e:
            print(f"[ControllerBridge] Error handling combo set: {e}")

    def _restore_combos(self, payload: str):
        """Restore assignment combos from retained MQTT message (overrides config defaults)."""
        try:
            if not payload:
                return
            data = json.loads(payload)
            restored = {}
            for slot, buttons in data.items():
                if slot in ("left", "right", "presets") and isinstance(buttons, list) and buttons:
                    restored[slot] = frozenset(buttons)
            if restored:
                self.assignment_combos = restored
                print(f"[ControllerBridge] Restored {len(restored)} assignment combos from MQTT")
        except Exception as e:
            print(f"[ControllerBridge] Error restoring assignment combos: {e}")

    def publish_combo_config(self):
        """Publish current assignment combo config via MQTT (retained)."""
        if not self.mqtt_client:
            return
        config = {}
        for slot, combo_set in self.assignment_combos.items():
            config[slot] = sorted(combo_set)
        self.mqtt_client.publish(
            "protogen/fins/controllerbridge/status/combo_config",
            json.dumps(config),
            retain=True,
        )

    # ======== Assignment Color Config ========

    def _handle_color_set(self, payload: str):
        """Handle color config update from web UI."""
        try:
            data = json.loads(payload)
            slot = data.get("slot")
            color = data.get("color")
            if not slot or slot not in ("left", "right", "presets", "unassigned"):
                return
            if not isinstance(color, list) or len(color) != 3:
                return
            rgb = tuple(max(0, min(255, int(c))) for c in color)
            self.assignment_colors[slot] = rgb

            print(f"[ControllerBridge] Updated assignment color: {slot} = {rgb}")

            # Apply immediately to controllers on this slot
            for s, mac in self.assignments.items():
                if s == slot and mac:
                    self._set_led_color(mac, *rgb)

            # For "unassigned", apply to all unassigned controllers
            if slot == "unassigned":
                assigned_macs = set(m for m in self.assignments.values() if m)
                for mac in self.connected_devices:
                    if mac not in assigned_macs:
                        self._set_led_color(mac, *rgb)

            self.publish_color_config()
        except Exception as e:
            print(f"[ControllerBridge] Error handling color set: {e}")

    def _restore_colors(self, payload: str):
        """Restore assignment colors from retained MQTT message (overrides config defaults)."""
        try:
            if not payload:
                return
            data = json.loads(payload)
            restored = {}
            for slot, rgb in data.items():
                if slot in ("left", "right", "presets", "unassigned") and isinstance(rgb, list) and len(rgb) == 3:
                    restored[slot] = tuple(int(c) for c in rgb)
            if restored:
                self.assignment_colors = restored
                print(f"[ControllerBridge] Restored {len(restored)} assignment colors from MQTT")
        except Exception as e:
            print(f"[ControllerBridge] Error restoring assignment colors: {e}")

    def publish_color_config(self):
        """Publish current assignment color config via MQTT (retained)."""
        if not self.mqtt_client:
            return
        config = {}
        for slot, rgb in self.assignment_colors.items():
            config[slot] = list(rgb)
        self.mqtt_client.publish(
            "protogen/fins/controllerbridge/status/color_config",
            json.dumps(config),
            retain=True,
        )

    # ======== System Action Combos ========

    # Action dispatch map: action_id -> (mqtt_topic, toggle_key_or_None)
    ACTION_DISPATCH = {
        "airplay_toggle": ("protogen/fins/castbridge/airplay/enable", "airplay"),
        "spotify_toggle": ("protogen/fins/castbridge/spotify/enable", "spotify"),
        "reboot":         ("protogen/fins/systembridge/power/reboot", None),
        "shutdown":       ("protogen/fins/systembridge/power/shutdown", None),
        "ap_toggle":      ("protogen/fins/networkingbridge/ap/enable", "ap"),
        "esp_restart":    ("protogen/visor/esp/restart", None),
    }

    # Volume actions: action_id -> step delta
    VOLUME_ACTIONS = {
        "volume_up_1":   1,  "volume_down_1":   -1,
        "volume_up_5":   5,  "volume_down_5":   -5,
        "volume_up_10":  10, "volume_down_10":  -10,
    }

    DANGEROUS_ACTIONS = {"reboot", "shutdown"}

    def _update_service_state(self, service: str, payload: str):
        """Track service enabled state for toggle actions."""
        try:
            data = json.loads(payload)
            # castbridge health uses is_enabled, networkingbridge ap uses enabled
            enabled = data.get("is_enabled", data.get("enabled", False))
            self.service_states[service] = bool(enabled)
        except Exception:
            pass

    def _update_volume_state(self, payload: str):
        """Track current volume from audiobridge status."""
        try:
            data = json.loads(payload)
            self._current_volume = int(data.get("volume", self._current_volume))
        except Exception:
            pass

    def _execute_action(self, action: str):
        """Execute a system action triggered by a gamepad combo."""
        if not self.mqtt_client:
            return

        # Volume adjust actions
        step = self.VOLUME_ACTIONS.get(action)
        if step is not None:
            new_vol = max(0, min(100, self._current_volume + step))
            self.mqtt_client.publish(
                "protogen/fins/audiobridge/volume/set",
                json.dumps({"volume": new_vol}),
            )
            print(f"[ControllerBridge] Volume {'+' if step > 0 else ''}{step}% -> {new_vol}%")
            return

        dispatch = self.ACTION_DISPATCH.get(action)
        if not dispatch:
            print(f"[ControllerBridge] Unknown action: {action}")
            return

        topic, toggle_key = dispatch

        # Double-tap safety for dangerous actions
        if action in self.DANGEROUS_ACTIONS:
            now = time.time()
            pending_time = self._pending_dangerous.get(action, 0)
            if now - pending_time <= 3.0:
                # Second press within 3s — confirmed, execute
                self._pending_dangerous.pop(action, None)
                print(f"[ControllerBridge] Action confirmed: {action}")
                publish_notification(self.mqtt_client, "controller", "action",
                                     "gamepad", f"System {action} confirmed")
                self.mqtt_client.publish(topic, "")
            else:
                # First press — warn
                self._pending_dangerous[action] = now
                print(f"[ControllerBridge] Action pending confirmation: {action}")
                publish_notification(self.mqtt_client, "controller", "warning",
                                     "gamepad", f"Press again within 3s to {action}")
            return

        if toggle_key:
            # Toggle action — invert current state
            current = self.service_states.get(toggle_key, False)
            new_state = not current
            payload = json.dumps({"enable": new_state})
            self.mqtt_client.publish(topic, payload)
            state_word = "enabled" if new_state else "disabled"
            print(f"[ControllerBridge] Action: {action} -> {state_word}")
            publish_notification(self.mqtt_client, "controller", "action",
                                 "gamepad", f"{toggle_key.title()} {state_word}")
        else:
            # One-shot action (esp_restart)
            print(f"[ControllerBridge] Action: {action}")
            publish_notification(self.mqtt_client, "controller", "action",
                                 "gamepad", f"{action.replace('_', ' ').title()}")
            self.mqtt_client.publish(topic, "")

    def _handle_action_combo_set(self, payload: str):
        """Handle action combo config update from web UI."""
        try:
            data = json.loads(payload)
            action = data.get("action")
            if not action:
                return

            if data.get("delete"):
                self.action_combos.pop(action, None)
                print(f"[ControllerBridge] Deleted action combo: {action}")
            else:
                buttons = data.get("buttons", [])
                if isinstance(buttons, list) and len(buttons) > 0:
                    self.action_combos[action] = frozenset(buttons)
                    print(f"[ControllerBridge] Updated action combo: {action} = {buttons}")
                else:
                    self.action_combos.pop(action, None)

            self.publish_action_combo_config()
        except Exception as e:
            print(f"[ControllerBridge] Error handling action combo set: {e}")

    def _restore_action_combos(self, payload: str):
        """Restore action combos from retained MQTT message."""
        try:
            if not payload:
                return
            data = json.loads(payload)
            self.action_combos = {}
            for action_id, buttons in data.items():
                if isinstance(buttons, list) and len(buttons) > 0:
                    self.action_combos[action_id] = frozenset(buttons)
            if self.action_combos:
                print(f"[ControllerBridge] Restored {len(self.action_combos)} action combos from MQTT")
        except Exception as e:
            print(f"[ControllerBridge] Error restoring action combos: {e}")

    def publish_action_combo_config(self):
        """Publish current action combo config via MQTT (retained)."""
        if not self.mqtt_client:
            return
        config = {}
        for action_id, buttons in self.action_combos.items():
            config[action_id] = sorted(buttons)
        self.mqtt_client.publish(
            "protogen/fins/controllerbridge/status/action_combo_config",
            json.dumps(config),
            retain=True,
        )

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

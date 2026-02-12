"""
BlueZ D-Bus wrapper for Protosuit Engine.
Provides Pythonic access to BlueZ Bluetooth management via pydbus.
Replaces all bluetoothctl subprocess calls with direct D-Bus API.
"""

import threading
import logging
from typing import Optional, Callable, Dict, List

from pydbus import SystemBus
from gi.repository import GLib, Gio

logger = logging.getLogger(__name__)

# BlueZ D-Bus constants
BLUEZ_SERVICE = "org.bluez"
BLUEZ_ADAPTER_IFACE = "org.bluez.Adapter1"
BLUEZ_DEVICE_IFACE = "org.bluez.Device1"
OBJECT_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
AGENT_PATH = "/org/bluez/protosuit_agent"

# Agent1 introspection XML — auto-accept all pairing requests
AGENT_XML = """
<node>
  <interface name="org.bluez.Agent1">
    <method name="Release"/>
    <method name="RequestPinCode">
      <arg direction="in" type="o" name="device"/>
      <arg direction="out" type="s"/>
    </method>
    <method name="DisplayPinCode">
      <arg direction="in" type="o" name="device"/>
      <arg direction="in" type="s" name="pincode"/>
    </method>
    <method name="RequestPasskey">
      <arg direction="in" type="o" name="device"/>
      <arg direction="out" type="u"/>
    </method>
    <method name="DisplayPasskey">
      <arg direction="in" type="o" name="device"/>
      <arg direction="in" type="u" name="passkey"/>
      <arg direction="in" type="q" name="entered"/>
    </method>
    <method name="RequestConfirmation">
      <arg direction="in" type="o" name="device"/>
      <arg direction="in" type="u" name="passkey"/>
    </method>
    <method name="RequestAuthorization">
      <arg direction="in" type="o" name="device"/>
    </method>
    <method name="AuthorizeService">
      <arg direction="in" type="o" name="device"/>
      <arg direction="in" type="s" name="uuid"/>
    </method>
    <method name="Cancel"/>
  </interface>
</node>
"""


def _agent_method_call(connection, sender, object_path, interface_name,
                       method_name, parameters, invocation):
    """Handle Agent1 method calls — auto-accept everything."""
    logger.info(f"Agent: {method_name}")
    if method_name == "RequestPinCode":
        invocation.return_value(GLib.Variant("(s)", ("0000",)))
    elif method_name == "RequestPasskey":
        invocation.return_value(GLib.Variant("(u)", (0,)))
    else:
        invocation.return_value(None)
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"

# Device categorization keywords
GAMEPAD_KEYWORDS = [
    "controller", "gamepad", "joystick", "xbox", "ps4", "ps5",
    "dualshock", "dualsense", "switch", "8bitdo", "nintendo",
    "pro controller", "wireless controller",
]

AUDIO_KEYWORDS = [
    "speaker", "headphone", "headset", "earphone", "earbud",
    "soundbar", "airpods", "beats", "bose", "jbl", "sony wh",
    "sony wf", "samsung buds", "galaxy buds", "audio",
    "soundcore", "anker", "marshall", "harman", "bang",
]


def is_gamepad(name: str, icon: str = "") -> bool:
    """Check if a device is a gamepad based on name and BlueZ icon property."""
    if not name:
        return False
    name_lower = name.lower()
    if icon and icon == "input-gaming":
        return True
    return any(kw in name_lower for kw in GAMEPAD_KEYWORDS)


def is_audio_device(name: str, icon: str = "") -> bool:
    """Check if a device is an audio device based on name and BlueZ icon property."""
    if not name:
        return False
    # Gamepads take priority — some controllers have "audio" in metadata
    if is_gamepad(name, icon):
        return False
    name_lower = name.lower()
    if icon and icon in ("audio-card", "audio-headphones", "audio-headset"):
        return True
    return any(kw in name_lower for kw in AUDIO_KEYWORDS)


def mac_to_dbus_path(adapter: str, mac: str) -> str:
    """Convert MAC address to BlueZ D-Bus object path."""
    return f"/org/bluez/{adapter}/dev_{mac.replace(':', '_')}"


def dbus_path_to_mac(path: str) -> Optional[str]:
    """Extract MAC address from BlueZ D-Bus object path."""
    # /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF → AA:BB:CC:DD:EE:FF
    parts = path.split("/")
    for part in parts:
        if part.startswith("dev_"):
            return part[4:].replace("_", ":")
    return None


def dbus_path_adapter(path: str) -> Optional[str]:
    """Extract adapter name from BlueZ D-Bus object path."""
    # /org/bluez/hci0/dev_... → hci0
    parts = path.split("/")
    if len(parts) >= 4 and parts[2] == "bluez":
        return parts[3]
    return None


class BluezAdapter:
    """Wrapper around a BlueZ Bluetooth adapter via D-Bus."""

    def __init__(self, bus: SystemBus, adapter_name: str = "hci0"):
        self.bus = bus
        self.name = adapter_name
        self.path = f"/org/bluez/{adapter_name}"
        self._proxy = None

    def _get_proxy(self):
        """Get or refresh the adapter D-Bus proxy."""
        if self._proxy is None:
            try:
                self._proxy = self.bus.get(BLUEZ_SERVICE, self.path)
            except Exception as e:
                logger.error(f"[{self.name}] Failed to get adapter proxy: {e}")
                raise
        return self._proxy

    @property
    def address(self) -> str:
        """Get adapter Bluetooth address (MAC)."""
        return self._get_proxy().Address

    @property
    def powered(self) -> bool:
        return self._get_proxy().Powered

    def power_on(self):
        """Power on the adapter."""
        proxy = self._get_proxy()
        if not proxy.Powered:
            proxy.Powered = True
            logger.info(f"[{self.name}] Powered on")

    def power_off(self):
        """Power off the adapter."""
        proxy = self._get_proxy()
        if proxy.Powered:
            proxy.Powered = False
            logger.info(f"[{self.name}] Powered off")

    def start_discovery(self):
        """Start Bluetooth device discovery (scanning)."""
        try:
            proxy = self._get_proxy()
            if not proxy.Discovering:
                proxy.StartDiscovery()
                logger.info(f"[{self.name}] Discovery started")
        except GLib.Error as e:
            if "InProgress" in str(e):
                logger.debug(f"[{self.name}] Discovery already in progress")
            else:
                logger.error(f"[{self.name}] Failed to start discovery: {e}")
                raise

    def stop_discovery(self):
        """Stop Bluetooth device discovery."""
        try:
            proxy = self._get_proxy()
            if proxy.Discovering:
                proxy.StopDiscovery()
                logger.info(f"[{self.name}] Discovery stopped")
        except GLib.Error as e:
            if "NotReady" in str(e) or "NotAuthorized" in str(e):
                logger.debug(f"[{self.name}] Discovery was not running")
            else:
                logger.error(f"[{self.name}] Failed to stop discovery: {e}")

    def remove_device(self, mac: str):
        """Remove (unpair) a device from this adapter."""
        device_path = mac_to_dbus_path(self.name, mac)
        try:
            self._get_proxy().RemoveDevice(device_path)
            logger.info(f"[{self.name}] Removed device {mac}")
        except GLib.Error as e:
            if "DoesNotExist" in str(e):
                logger.debug(f"[{self.name}] Device {mac} already removed")
            else:
                logger.error(f"[{self.name}] Failed to remove {mac}: {e}")
                raise


class BluezDevice:
    """Wrapper around a BlueZ Bluetooth device via D-Bus."""

    def __init__(self, bus: SystemBus, adapter_name: str, mac: str):
        self.bus = bus
        self.adapter_name = adapter_name
        self.mac = mac
        self.path = mac_to_dbus_path(adapter_name, mac)
        self._proxy = None

    def _get_proxy(self):
        """Get or refresh the device D-Bus proxy."""
        if self._proxy is None:
            try:
                self._proxy = self.bus.get(BLUEZ_SERVICE, self.path)
            except Exception as e:
                logger.error(f"[{self.mac}] Failed to get device proxy: {e}")
                raise
        return self._proxy

    @property
    def name(self) -> str:
        try:
            return self._get_proxy().Name
        except Exception:
            return self.mac

    @property
    def address(self) -> str:
        return self._get_proxy().Address

    @property
    def paired(self) -> bool:
        try:
            return self._get_proxy().Paired
        except Exception:
            return False

    @property
    def connected(self) -> bool:
        try:
            return self._get_proxy().Connected
        except Exception:
            return False

    @property
    def trusted(self) -> bool:
        try:
            return self._get_proxy().Trusted
        except Exception:
            return False

    @property
    def icon(self) -> str:
        """BlueZ icon hint (e.g. 'input-gaming', 'audio-card')."""
        try:
            return self._get_proxy().Icon
        except Exception:
            return ""

    def trust(self):
        """Mark device as trusted."""
        self._get_proxy().Trusted = True
        logger.info(f"[{self.mac}] Trusted")

    def untrust(self):
        """Mark device as untrusted."""
        self._get_proxy().Trusted = False
        logger.info(f"[{self.mac}] Untrusted")

    def pair(self, timeout: float = 15.0):
        """Initiate pairing with the device."""
        if self.paired:
            logger.debug(f"[{self.mac}] Already paired")
            return
        logger.info(f"[{self.mac}] Pairing...")
        self._get_proxy().Pair()
        logger.info(f"[{self.mac}] Paired")

    def connect(self, timeout: float = 15.0):
        """Connect to the device."""
        logger.info(f"[{self.mac}] Connecting...")
        self._get_proxy().Connect()
        logger.info(f"[{self.mac}] Connected")

    def disconnect(self):
        """Disconnect from the device."""
        logger.info(f"[{self.mac}] Disconnecting...")
        self._get_proxy().Disconnect()
        logger.info(f"[{self.mac}] Disconnected")


class BluezManager:
    """
    Manages BlueZ D-Bus interactions with signal-driven state tracking.

    Runs a GLib main loop in a background thread for D-Bus signal delivery.
    Provides callbacks for device discovery, connection changes, and removal.
    """

    def __init__(self):
        self.bus = SystemBus()
        self._loop = GLib.MainLoop()
        self._loop_thread: Optional[threading.Thread] = None
        self._subscriptions: List = []
        self._adapters: Dict[str, BluezAdapter] = {}
        self._agent_reg_id = None

    def register_agent(self):
        """Register a NoInputNoOutput pairing agent with BlueZ."""
        try:
            node_info = Gio.DBusNodeInfo.new_for_xml(AGENT_XML)
            self._agent_reg_id = self.bus.con.register_object(
                AGENT_PATH,
                node_info.interfaces[0],
                _agent_method_call,
            )
            agent_manager = self.bus.get(BLUEZ_SERVICE, "/org/bluez")
            agent_manager.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
            agent_manager.RequestDefaultAgent(AGENT_PATH)
            logger.info("Pairing agent registered")
        except Exception as e:
            logger.error(f"Failed to register pairing agent: {e}")

    def get_adapter(self, name: str = "hci0") -> BluezAdapter:
        """Get or create an adapter wrapper."""
        if name not in self._adapters:
            self._adapters[name] = BluezAdapter(self.bus, name)
        return self._adapters[name]

    def get_device(self, adapter_name: str, mac: str) -> BluezDevice:
        """Create a device wrapper."""
        return BluezDevice(self.bus, adapter_name, mac)

    def get_managed_objects(self) -> Dict:
        """Get all BlueZ managed objects from ObjectManager."""
        try:
            obj_manager = self.bus.get(BLUEZ_SERVICE, "/")
            return obj_manager.GetManagedObjects()
        except Exception as e:
            logger.error(f"Failed to get managed objects: {e}")
            return {}

    def get_devices_on_adapter(self, adapter_name: str, paired_only: bool = False,
                                connected_only: bool = False) -> List[Dict]:
        """
        Get devices on a specific adapter by querying ObjectManager.

        Returns list of dicts with: mac, name, paired, connected, trusted, icon, path
        """
        objects = self.get_managed_objects()
        adapter_prefix = f"/org/bluez/{adapter_name}/dev_"
        devices = []

        for path, interfaces in objects.items():
            if not path.startswith(adapter_prefix):
                continue
            if BLUEZ_DEVICE_IFACE not in interfaces:
                continue

            props = interfaces[BLUEZ_DEVICE_IFACE]
            is_paired = bool(props.get("Paired", False))
            is_connected = bool(props.get("Connected", False))

            if paired_only and not is_paired:
                continue
            if connected_only and not is_connected:
                continue

            mac = dbus_path_to_mac(path) or props.get("Address", "")
            devices.append({
                "mac": mac,
                "name": str(props.get("Name", props.get("Alias", mac))),
                "paired": is_paired,
                "connected": is_connected,
                "trusted": bool(props.get("Trusted", False)),
                "icon": str(props.get("Icon", "")),
                "path": path,
            })

        return devices

    def subscribe_interfaces_added(self, callback: Callable):
        """
        Subscribe to InterfacesAdded signal (new devices discovered during scan).

        callback(path: str, interfaces: dict) — called when a new object appears.
        The callback receives the D-Bus object path and a dict of interface→properties.
        """
        try:
            obj_manager = self.bus.get(BLUEZ_SERVICE, "/")
            sub = obj_manager.InterfacesAdded.connect(callback)
            self._subscriptions.append(("InterfacesAdded", sub))
            logger.debug("Subscribed to InterfacesAdded")
        except Exception as e:
            logger.error(f"Failed to subscribe InterfacesAdded: {e}")

    def subscribe_interfaces_removed(self, callback: Callable):
        """
        Subscribe to InterfacesRemoved signal (device removed).

        callback(path: str, interfaces: list) — called when an object is removed.
        """
        try:
            obj_manager = self.bus.get(BLUEZ_SERVICE, "/")
            sub = obj_manager.InterfacesRemoved.connect(callback)
            self._subscriptions.append(("InterfacesRemoved", sub))
            logger.debug("Subscribed to InterfacesRemoved")
        except Exception as e:
            logger.error(f"Failed to subscribe InterfacesRemoved: {e}")

    def subscribe_properties_changed(self, callback: Callable):
        """
        Subscribe to PropertiesChanged signal on all BlueZ objects.

        callback(sender, obj, iface, signal, params) — raw signal handler.
        params is (interface_name, changed_properties, invalidated_properties).

        Use this to detect connection state changes, name updates, etc.
        """
        try:
            sub = self.bus.con.signal_subscribe(
                BLUEZ_SERVICE,          # sender
                PROPERTIES_IFACE,       # interface
                "PropertiesChanged",    # signal name
                None,                   # object path (None = all)
                None,                   # arg0 filter
                0,                      # flags
                callback,
            )
            self._subscriptions.append(("PropertiesChanged", sub))
            logger.debug("Subscribed to PropertiesChanged")
        except Exception as e:
            logger.error(f"Failed to subscribe PropertiesChanged: {e}")

    def start(self):
        """Start the GLib main loop in a background thread for signal delivery."""
        if self._loop_thread and self._loop_thread.is_alive():
            return

        def run_loop():
            logger.debug("GLib main loop starting")
            self._loop.run()
            logger.debug("GLib main loop stopped")

        self._loop_thread = threading.Thread(target=run_loop, daemon=True, name="bluez-glib")
        self._loop_thread.start()
        logger.info("BluezManager started (GLib loop running)")

    def stop(self):
        """Stop the GLib main loop and clean up subscriptions."""
        # Unsubscribe PropertiesChanged (raw signal subscriptions)
        for name, sub in self._subscriptions:
            try:
                if name == "PropertiesChanged":
                    self.bus.con.signal_unsubscribe(sub)
                # InterfacesAdded/Removed are handled by pydbus disconnect — no explicit unsub needed
            except Exception:
                pass
        self._subscriptions.clear()

        if self._loop.is_running():
            self._loop.quit()

        if self._loop_thread:
            self._loop_thread.join(timeout=2)
            self._loop_thread = None

        self._adapters.clear()
        logger.info("BluezManager stopped")

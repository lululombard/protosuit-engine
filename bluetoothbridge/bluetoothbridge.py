"""
BluetoothBridge - Bluetooth Connection Management Service
Manages scanning, pairing, connecting, and disconnecting Bluetooth devices via BlueZ D-Bus API.
Publishes device state for controllerbridge (gamepads) and audiobridge (speakers) to consume.
"""

import paho.mqtt.client as mqtt
import signal
import json
import subprocess
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
from utils.bluez_dbus import (
    BluezManager, BluezDevice, BluezAdapter,
    is_gamepad, is_audio_device,
    dbus_path_to_mac, dbus_path_adapter,
    BLUEZ_DEVICE_IFACE,
)

from gi.repository import GLib


class BluetoothBridge:
    """
    Bluetooth Connection Management Service

    Uses BlueZ D-Bus API (via pydbus) for all Bluetooth operations.
    Publishes device lists for controllerbridge and audiobridge to react to.

    Subscribes to:
        - protogen/fins/bluetoothbridge/scan/start
        - protogen/fins/bluetoothbridge/scan/stop
        - protogen/fins/bluetoothbridge/connect
        - protogen/fins/bluetoothbridge/disconnect
        - protogen/fins/bluetoothbridge/unpair
        - protogen/fins/bluetoothbridge/bluetooth/restart
        - protogen/fins/bluetoothbridge/status/last_audio_device  (retained restore)

    Publishes:
        - protogen/fins/bluetoothbridge/status/scanning
        - protogen/fins/bluetoothbridge/status/devices
        - protogen/fins/bluetoothbridge/status/audio_devices
        - protogen/fins/bluetoothbridge/status/connection
        - protogen/fins/bluetoothbridge/status/last_audio_device
        - protogen/visor/notifications
    """

    def __init__(self):
        self.config_loader = ConfigLoader()
        self.mqtt_client: Optional[mqtt.Client] = None
        self.running = False

        # BlueZ D-Bus manager
        self.bluez = BluezManager()

        # Bluetooth state
        self.scanning = False

        # Device tracking
        self.discovered_devices: Dict[str, Dict] = {}  # gamepads: {mac: {name, paired, connected}}
        self.audio_devices: Dict[str, Dict] = {}        # audio: {mac: {name, paired, connected, type}}
        self.last_audio_device_to_restore: Optional[Dict] = None

        # State lock for signal-driven updates
        self._state_lock = threading.Lock()

        # Adapter config
        self.gamepad_adapter, self.audio_adapter = self._load_adapter_config()

        print(f"[BluetoothBridge] Initialized (gamepads: {self.gamepad_adapter}, audio: {self.audio_adapter})")

    def _load_adapter_config(self) -> tuple:
        """Load Bluetooth adapter configuration."""
        try:
            config = self.config_loader.config
            if "bluetoothbridge" in config and "adapters" in config["bluetoothbridge"]:
                adapters = config["bluetoothbridge"]["adapters"]
                return adapters.get("gamepads", "hci0"), adapters.get("audio", "hci1")
        except Exception as e:
            print(f"[BluetoothBridge] Error loading adapter config: {e}")
        return "hci0", "hci1"

    def _get_adapter_for_device(self, mac: str) -> str:
        """Route device to the correct adapter based on type."""
        if mac in self.audio_devices:
            return self.audio_adapter
        return self.gamepad_adapter

    # ======== D-Bus Signal Handlers ========

    def _on_interfaces_added(self, path: str, interfaces: dict):
        """Handle new device discovered during scan (InterfacesAdded signal)."""
        if BLUEZ_DEVICE_IFACE not in interfaces:
            return

        props = interfaces[BLUEZ_DEVICE_IFACE]
        mac = dbus_path_to_mac(path)
        if not mac:
            return

        name = str(props.get("Name", props.get("Alias", mac)))
        paired = bool(props.get("Paired", False))
        connected = bool(props.get("Connected", False))
        icon = str(props.get("Icon", ""))

        with self._state_lock:
            if is_gamepad(name, icon):
                if mac not in self.discovered_devices:
                    self.discovered_devices[mac] = {
                        "mac": mac, "name": name,
                        "paired": paired, "connected": connected,
                    }
                    print(f"[BluetoothBridge] Discovered gamepad: {name} ({mac})")
                    self.publish_devices_status()

            elif is_audio_device(name, icon):
                if mac not in self.audio_devices:
                    self.audio_devices[mac] = {
                        "mac": mac, "name": name,
                        "paired": paired, "connected": connected,
                        "type": "audio",
                    }
                    print(f"[BluetoothBridge] Discovered audio device: {name} ({mac})")
                    self.publish_audio_devices_status()

    def _on_interfaces_removed(self, path: str, interfaces: list):
        """Handle device removed (InterfacesRemoved signal)."""
        if BLUEZ_DEVICE_IFACE not in interfaces:
            return

        mac = dbus_path_to_mac(path)
        if not mac:
            return

        with self._state_lock:
            if mac in self.discovered_devices:
                print(f"[BluetoothBridge] Device removed: {mac}")
                del self.discovered_devices[mac]
                self.publish_devices_status()

            if mac in self.audio_devices:
                print(f"[BluetoothBridge] Audio device removed: {mac}")
                del self.audio_devices[mac]
                self.publish_audio_devices_status()

    def _on_properties_changed(self, sender, obj, iface, signal_name, params):
        """Handle PropertiesChanged signal (connection state, name updates)."""
        iface_name, changed, invalidated = params

        if iface_name != BLUEZ_DEVICE_IFACE:
            return

        path = obj
        mac = dbus_path_to_mac(path)
        if not mac:
            return

        with self._state_lock:
            # Handle connection state changes
            if "Connected" in changed:
                connected = bool(changed["Connected"])

                if mac in self.discovered_devices:
                    old_state = self.discovered_devices[mac].get("connected", False)
                    self.discovered_devices[mac]["connected"] = connected
                    if connected != old_state:
                        name = self.discovered_devices[mac].get("name", mac)
                        if connected:
                            print(f"[BluetoothBridge] Gamepad connected: {name} ({mac})")
                            publish_notification(self.mqtt_client, "bluetooth", "connected",
                                                 "gamepad", f"Controller connected: {name}")
                        else:
                            print(f"[BluetoothBridge] Gamepad disconnected: {name} ({mac})")
                            publish_notification(self.mqtt_client, "bluetooth", "disconnected",
                                                 "gamepad", f"Controller disconnected: {name}")
                        self.publish_devices_status()

                if mac in self.audio_devices:
                    old_state = self.audio_devices[mac].get("connected", False)
                    self.audio_devices[mac]["connected"] = connected
                    if connected != old_state:
                        name = self.audio_devices[mac].get("name", mac)
                        if connected:
                            print(f"[BluetoothBridge] Audio device connected: {name} ({mac})")
                            self.publish_last_audio_device(mac)
                            publish_notification(self.mqtt_client, "bluetooth", "connected",
                                                 "speaker", f"Speaker connected: {name}")
                        else:
                            print(f"[BluetoothBridge] Audio device disconnected: {name} ({mac})")
                            publish_notification(self.mqtt_client, "bluetooth", "disconnected",
                                                 "speaker", f"Speaker disconnected: {name}")
                        self.publish_audio_devices_status()

            # Handle name updates
            if "Name" in changed:
                new_name = str(changed["Name"])
                if mac in self.discovered_devices:
                    self.discovered_devices[mac]["name"] = new_name
                if mac in self.audio_devices:
                    self.audio_devices[mac]["name"] = new_name

            # Handle paired state
            if "Paired" in changed:
                paired = bool(changed["Paired"])
                if mac in self.discovered_devices:
                    self.discovered_devices[mac]["paired"] = paired
                    self.publish_devices_status()
                if mac in self.audio_devices:
                    self.audio_devices[mac]["paired"] = paired
                    self.publish_audio_devices_status()

    # ======== MQTT ========

    def init_mqtt(self):
        """Initialize MQTT connection and subscriptions."""
        print("[BluetoothBridge] Initializing MQTT...")

        self.mqtt_client = create_mqtt_client(self.config_loader)

        def on_connect(client, userdata, flags, rc, properties=None):
            print(f"[BluetoothBridge] Connected to MQTT (rc: {rc})")
            topics = [
                "protogen/fins/bluetoothbridge/scan/start",
                "protogen/fins/bluetoothbridge/scan/stop",
                "protogen/fins/bluetoothbridge/connect",
                "protogen/fins/bluetoothbridge/disconnect",
                "protogen/fins/bluetoothbridge/unpair",
                "protogen/fins/bluetoothbridge/bluetooth/restart",
                "protogen/fins/bluetoothbridge/status/last_audio_device",
            ]
            for topic in topics:
                client.subscribe(topic)

        def on_message(client, userdata, msg):
            self.on_mqtt_message(msg.topic, msg.payload.decode("utf-8") if msg.payload else "")

        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_message = on_message
        self.mqtt_client.loop_start()

        time.sleep(1)

    def on_mqtt_message(self, topic: str, payload: str):
        """Handle incoming MQTT messages."""
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
            elif topic == "protogen/fins/bluetoothbridge/bluetooth/restart":
                self.restart_bluetooth()
            elif topic == "protogen/fins/bluetoothbridge/status/last_audio_device":
                self._restore_last_audio_device(payload)
        except Exception as e:
            print(f"[BluetoothBridge] Error handling MQTT: {e}")

    # ======== Scanning ========

    def start_scan(self):
        """Start Bluetooth discovery on both adapters."""
        if self.scanning:
            return
        print("[BluetoothBridge] Starting scan...")
        self.scanning = True
        self.publish_scanning_status()

        try:
            gamepad_adapter = self.bluez.get_adapter(self.gamepad_adapter)
            gamepad_adapter.start_discovery()
        except Exception as e:
            print(f"[BluetoothBridge] Gamepad adapter scan error: {e}")

        try:
            if self.audio_adapter != self.gamepad_adapter:
                audio_adapter = self.bluez.get_adapter(self.audio_adapter)
                audio_adapter.start_discovery()
        except Exception as e:
            print(f"[BluetoothBridge] Audio adapter scan error: {e}")

        publish_notification(self.mqtt_client, "bluetooth", "scan_started",
                             "bluetooth", "Bluetooth scan started")

    def stop_scan(self):
        """Stop Bluetooth discovery on both adapters."""
        if not self.scanning:
            return
        print("[BluetoothBridge] Stopping scan...")

        try:
            self.bluez.get_adapter(self.gamepad_adapter).stop_discovery()
        except Exception:
            pass

        try:
            if self.audio_adapter != self.gamepad_adapter:
                self.bluez.get_adapter(self.audio_adapter).stop_discovery()
        except Exception:
            pass

        self.scanning = False
        self.publish_scanning_status()

    # ======== Connect / Disconnect / Unpair ========

    def connect_device(self, mac: str):
        """Connect to a device (runs in background thread)."""
        self.publish_connection_status(mac, "connecting")
        threading.Thread(target=self._connect_device_worker, args=(mac,), daemon=True).start()

    def _connect_device_worker(self, mac: str):
        """Worker thread for connecting a device via D-Bus."""
        adapter_name = self._get_adapter_for_device(mac)
        try:
            device = self.bluez.get_device(adapter_name, mac)

            # Trust first
            if not device.trusted:
                device.trust()

            # Pair if needed
            if not device.paired:
                device.pair()
                time.sleep(1)

            # Connect
            device.connect()

            # Update state
            name = device.name
            with self._state_lock:
                icon = device.icon
                if is_audio_device(name, icon):
                    self.audio_devices[mac] = {
                        "mac": mac, "name": name,
                        "paired": True, "connected": True, "type": "audio",
                    }
                    self.publish_audio_devices_status()
                    self.publish_last_audio_device(mac)
                else:
                    self.discovered_devices[mac] = {
                        "mac": mac, "name": name,
                        "paired": True, "connected": True,
                    }
                    self.publish_devices_status()

            self.publish_connection_status(mac, "connected")
            print(f"[BluetoothBridge] Connected: {name} ({mac})")

            publish_notification(self.mqtt_client, "bluetooth", "connected",
                                 "device", f"Connected: {name}")

        except GLib.Error as e:
            error_msg = str(e)
            print(f"[BluetoothBridge] Connection failed for {mac}: {error_msg}")
            self.publish_connection_status(mac, "failed", error_msg)

            publish_notification(self.mqtt_client, "bluetooth", "error",
                                 "device", f"Connection failed: {mac}")
        except Exception as e:
            print(f"[BluetoothBridge] Connection error for {mac}: {e}")
            self.publish_connection_status(mac, "failed", str(e))

    def disconnect_device(self, mac: str):
        """Disconnect a device (runs in background thread)."""
        self.publish_connection_status(mac, "disconnecting")
        threading.Thread(target=self._disconnect_device_worker, args=(mac,), daemon=True).start()

    def _disconnect_device_worker(self, mac: str):
        """Worker thread for disconnecting a device via D-Bus."""
        adapter_name = self._get_adapter_for_device(mac)
        try:
            device = self.bluez.get_device(adapter_name, mac)
            device.disconnect()

            with self._state_lock:
                if mac in self.discovered_devices:
                    self.discovered_devices[mac]["connected"] = False
                    self.publish_devices_status()
                if mac in self.audio_devices:
                    self.audio_devices[mac]["connected"] = False
                    self.publish_audio_devices_status()

            self.publish_connection_status(mac, "disconnected")

        except Exception as e:
            print(f"[BluetoothBridge] Disconnect error for {mac}: {e}")
            self.publish_connection_status(mac, "failed", str(e))

    def unpair_device(self, mac: str):
        """Unpair (remove) a device."""
        adapter_name = self._get_adapter_for_device(mac)
        try:
            # Disconnect first if connected
            try:
                device = self.bluez.get_device(adapter_name, mac)
                if device.connected:
                    device.disconnect()
                    time.sleep(0.5)
            except Exception:
                pass

            # Remove from adapter
            adapter = self.bluez.get_adapter(adapter_name)
            adapter.remove_device(mac)

            with self._state_lock:
                if mac in self.discovered_devices:
                    del self.discovered_devices[mac]
                    self.publish_devices_status()
                if mac in self.audio_devices:
                    del self.audio_devices[mac]
                    self.publish_audio_devices_status()

            print(f"[BluetoothBridge] Unpaired: {mac}")
            publish_notification(self.mqtt_client, "bluetooth", "unpaired",
                                 "device", f"Device unpaired: {mac}")

        except Exception as e:
            print(f"[BluetoothBridge] Unpair error for {mac}: {e}")

    # ======== Auto-reconnect ========

    def _load_paired_devices(self):
        """Load already-paired devices from BlueZ into our state dicts."""
        for adapter_name in [self.gamepad_adapter, self.audio_adapter]:
            try:
                devices = self.bluez.get_devices_on_adapter(adapter_name, paired_only=True)
                for dev in devices:
                    mac = dev["mac"]
                    name = dev["name"]
                    icon = dev["icon"]
                    connected = dev["connected"]

                    if is_gamepad(name, icon):
                        self.discovered_devices[mac] = {
                            "mac": mac, "name": name,
                            "paired": True, "connected": connected,
                        }
                    elif is_audio_device(name, icon):
                        self.audio_devices[mac] = {
                            "mac": mac, "name": name,
                            "paired": True, "connected": connected,
                            "type": "audio",
                        }
            except Exception as e:
                print(f"[BluetoothBridge] Error loading paired devices from {adapter_name}: {e}")

    def _auto_reconnect_devices(self):
        """Auto-reconnect to previously connected devices."""
        print("[BluetoothBridge] Auto-reconnecting...")

        reconnecting = set()

        # Reconnect last audio device from retained message
        if self.last_audio_device_to_restore:
            mac = self.last_audio_device_to_restore["mac"]
            name = self.last_audio_device_to_restore["name"]

            if mac in self.audio_devices and self.audio_devices[mac].get("connected"):
                print(f"[BluetoothBridge] Last audio device already connected: {name}")
            else:
                if mac not in self.audio_devices:
                    self.audio_devices[mac] = {
                        "mac": mac, "name": name,
                        "paired": True, "connected": False, "type": "audio",
                    }
                print(f"[BluetoothBridge] Reconnecting last audio device: {name} ({mac})")
                reconnecting.add(mac)
                threading.Thread(target=self._reconnect_device, args=(mac,), daemon=True).start()
                time.sleep(1)

            self.last_audio_device_to_restore = None

        # Reconnect other paired audio devices
        for mac, info in list(self.audio_devices.items()):
            if mac not in reconnecting and info.get("paired") and not info.get("connected"):
                print(f"[BluetoothBridge] Reconnecting audio: {info.get('name', mac)}")
                reconnecting.add(mac)
                threading.Thread(target=self._reconnect_device, args=(mac,), daemon=True).start()
                time.sleep(1)

        # Reconnect paired gamepads
        for mac, info in list(self.discovered_devices.items()):
            if mac not in reconnecting and info.get("paired") and not info.get("connected"):
                print(f"[BluetoothBridge] Reconnecting gamepad: {info.get('name', mac)}")
                reconnecting.add(mac)
                threading.Thread(target=self._reconnect_device, args=(mac,), daemon=True).start()
                time.sleep(1)

        # Publish status
        self.publish_devices_status()
        self.publish_audio_devices_status()

    def _reconnect_device(self, mac: str):
        """Reconnect to an already-paired device."""
        adapter_name = self._get_adapter_for_device(mac)
        try:
            device = self.bluez.get_device(adapter_name, mac)
            if not device.trusted:
                device.trust()
            device.connect()
            print(f"[BluetoothBridge] Reconnected: {mac}")
        except Exception as e:
            print(f"[BluetoothBridge] Reconnect failed for {mac}: {e}")

    def _restore_last_audio_device(self, payload: str):
        """Store last audio device from retained MQTT for auto-reconnect."""
        try:
            if not payload:
                return
            data = json.loads(payload)
            mac = data.get("mac")
            name = data.get("name", mac)
            if mac:
                self.last_audio_device_to_restore = {"mac": mac, "name": name}
                print(f"[BluetoothBridge] Will reconnect to: {name} ({mac})")
        except Exception as e:
            print(f"[BluetoothBridge] Error parsing last audio device: {e}")

    # ======== Bluetooth Restart ========

    def restart_bluetooth(self):
        """Restart the Bluetooth service to fix errors."""
        print("[BluetoothBridge] Restarting Bluetooth service...")
        try:
            if self.scanning:
                self.stop_scan()

            # Restart via systemd
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "bluetooth"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                print("[BluetoothBridge] Bluetooth service restarted")
                time.sleep(3)

                # Reload paired devices
                self._load_paired_devices()
                self._auto_reconnect_devices()
                self.publish_all_status()
            else:
                print(f"[BluetoothBridge] Restart failed: {result.stderr}")

        except Exception as e:
            print(f"[BluetoothBridge] Restart error: {e}")

    # ======== Status Publishing ========

    def publish_scanning_status(self):
        if self.mqtt_client:
            self.mqtt_client.publish(
                "protogen/fins/bluetoothbridge/status/scanning",
                json.dumps(self.scanning), retain=True,
            )

    def publish_devices_status(self):
        if self.mqtt_client:
            self.mqtt_client.publish(
                "protogen/fins/bluetoothbridge/status/devices",
                json.dumps(list(self.discovered_devices.values())), retain=True,
            )

    def publish_audio_devices_status(self):
        if self.mqtt_client:
            self.mqtt_client.publish(
                "protogen/fins/bluetoothbridge/status/audio_devices",
                json.dumps(list(self.audio_devices.values())), retain=True,
            )

    def publish_last_audio_device(self, mac: str):
        if self.mqtt_client and mac in self.audio_devices:
            info = self.audio_devices[mac]
            self.mqtt_client.publish(
                "protogen/fins/bluetoothbridge/status/last_audio_device",
                json.dumps({"mac": mac, "name": info.get("name", mac), "timestamp": time.time()}),
                retain=True,
            )

    def publish_connection_status(self, mac: str, status: str, error: str = None):
        if not self.mqtt_client:
            return
        info = self.discovered_devices.get(mac) or self.audio_devices.get(mac, {})
        payload = {
            "mac": mac,
            "name": info.get("name", mac),
            "status": status,
            "timestamp": time.time(),
        }
        if error:
            payload["error"] = error
        self.mqtt_client.publish(
            "protogen/fins/bluetoothbridge/status/connection",
            json.dumps(payload), retain=False,
        )

    def publish_all_status(self):
        self.publish_scanning_status()
        self.publish_devices_status()
        self.publish_audio_devices_status()

    # ======== Lifecycle ========

    def cleanup(self):
        """Clean up all resources."""
        print("[BluetoothBridge] Cleaning up...")
        self.stop_scan()
        self.bluez.stop()
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        print("[BluetoothBridge] Cleanup complete")

    def run(self):
        """Main run loop."""
        print("[BluetoothBridge] Starting...")

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Restart Bluetooth for clean state
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "bluetooth"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                print("[BluetoothBridge] Bluetooth service restarted")
                time.sleep(3)
        except Exception as e:
            print(f"[BluetoothBridge] Bluetooth restart warning: {e}")

        # Unblock and power on adapters via D-Bus
        try:
            subprocess.run(["sudo", "rfkill", "unblock", "bluetooth"],
                           capture_output=True, timeout=5)
            time.sleep(0.5)

            for adapter_name in [self.gamepad_adapter, self.audio_adapter]:
                try:
                    adapter = self.bluez.get_adapter(adapter_name)
                    adapter.power_on()
                    print(f"[BluetoothBridge] {adapter_name} powered on (MAC: {adapter.address})")
                except Exception as e:
                    print(f"[BluetoothBridge] {adapter_name} power on warning: {e}")
        except Exception as e:
            print(f"[BluetoothBridge] Adapter setup warning: {e}")

        self.running = True

        # Subscribe to D-Bus signals
        self.bluez.subscribe_interfaces_added(self._on_interfaces_added)
        self.bluez.subscribe_interfaces_removed(self._on_interfaces_removed)
        self.bluez.subscribe_properties_changed(self._on_properties_changed)
        self.bluez.start()

        # Initialize MQTT
        self.init_mqtt()

        # Load paired devices
        self._load_paired_devices()

        # Auto-reconnect
        self._auto_reconnect_devices()

        # Publish initial status
        self.publish_all_status()

        print("[BluetoothBridge] Running. Press Ctrl+C to exit.")

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

        self.cleanup()

    def _signal_handler(self, signum, frame):
        print(f"\n[BluetoothBridge] Signal {signum}, shutting down...")
        self.running = False


def main():
    bridge = BluetoothBridge()
    bridge.run()


if __name__ == "__main__":
    main()

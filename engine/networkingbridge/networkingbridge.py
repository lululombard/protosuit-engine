"""
Networking Bridge - Systemd-First Wi-Fi Management
Manages Wi-Fi client via NetworkManager D-Bus and AP mode via hostapd/dnsmasq
systemd services controlled through ServiceController (D-Bus).
"""

import os
import sys
import json
import re
import time
import threading
import io
import base64
import signal
from dataclasses import dataclass, asdict, field
from typing import List, Dict

import qrcode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from utils.mqtt_client import create_mqtt_client
from utils.logger import setup_logger, get_logger
from utils.service_controller import ServiceController
from utils.notifications import publish_notification
from utils.nm_dbus import NetworkManagerDbus, get_ap_clients

try:
    from networkingbridge.oui_lookup import get_oui_lookup
except ImportError:
    from oui_lookup import get_oui_lookup

logger = get_logger("networkingbridge")

HOSTAPD_CONFIG_PATH = "/etc/hostapd/hostapd.conf"
DNSMASQ_CONFIG_PATH = "/etc/dnsmasq.d/ap.conf"
AP_ENV_PATH = "/etc/protosuit/ap.env"


@dataclass
class InterfaceInfo:
    name: str
    mode: str  # 'client' or 'ap'
    detected: bool
    enabled: bool


@dataclass
class ClientStatus:
    connected: bool
    ssid: str = ""
    ip_address: str = ""
    cidr: int = 24
    router: str = ""
    signal_dbm: int = -100
    signal_percent: int = 0


@dataclass
class APClient:
    ip: str
    mac: str
    hostname: str = ""
    vendor: str = ""


@dataclass
class APStatus:
    enabled: bool = False
    running: bool = False
    ssid: str = "Protosuit"
    security: str = "wpa"
    password: str = "BeepBoop"
    ip_cidr: str = "192.168.50.1/24"
    clients: List[APClient] = field(default_factory=list)


@dataclass
class Network:
    ssid: str
    security: str
    signal_dbm: int
    signal_percent: int
    frequency: str
    connected: bool = False


class NetworkingBridge:
    def __init__(self, config, mqtt_client):
        self.config = config
        self.mqtt = mqtt_client
        self.running = False

        # Interface names from config
        self.client_interface = config["networking"]["client"]["interface"]
        self.ap_interface = config["networking"]["ap"]["interface"]

        # Service controllers (D-Bus/systemd)
        self._hostapd_svc = ServiceController("hostapd")
        self._dnsmasq_svc = ServiceController("dnsmasq")

        # NetworkManager D-Bus wrapper
        self._nm = NetworkManagerDbus()

        # Resolve device paths
        self._client_dev_path = self._nm.get_wifi_device(self.client_interface)
        self._ap_dev_path = self._nm.get_wifi_device(self.ap_interface)

        # OUI lookup for vendor names
        self._oui = get_oui_lookup()

        # State
        self.interfaces = {}
        self.client_status = ClientStatus(connected=False)
        self.ap_status = APStatus()
        self.scan_results = []
        self.scanning = False

        # Load AP config defaults from config.yaml
        self._load_ap_config()

    def _load_ap_config(self):
        """Load AP configuration defaults from config.yaml."""
        ap_config = self.config["networking"].get("ap", {})
        self.ap_status.ssid = ap_config.get("ssid", "Protosuit")
        self.ap_status.security = ap_config.get("security", "wpa")
        self.ap_status.password = ap_config.get("password", "BeepBoop")
        self.ap_status.ip_cidr = ap_config.get("ip_cidr", "192.168.50.1/24")

    # ======== Startup ========

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT (re)connection — re-subscribe to all topics."""
        logger.info(f"MQTT connected (reason={reason_code}), subscribing to topics")
        self._subscribe_mqtt()
        if self.running:
            self._sync_service_state()

    def start(self):
        """Start the networking bridge."""
        logger.info("Starting...")
        self.running = True

        # Set on_connect handler for (re)connection resilience
        self.mqtt.on_connect = self._on_connect

        # Systemd is the source of truth for AP state
        self._sync_service_state()

        # Subscribe to MQTT topics (also re-done in on_connect for reconnects)
        self._subscribe_mqtt()

        # Start polling loop
        threading.Thread(target=self._poll_loop, daemon=True).start()

        logger.info("Started successfully")

    def _sync_service_state(self):
        """Read systemd state at startup — systemd is the source of truth."""
        hostapd_health = self._hostapd_svc.get_health()
        self.ap_status.enabled = hostapd_health.is_enabled
        self.ap_status.running = hostapd_health.is_active
        logger.info(
            f"hostapd: enabled={hostapd_health.is_enabled}, "
            f"active={hostapd_health.is_active}, "
            f"state={hostapd_health.active_state}/{hostapd_health.sub_state}"
        )

        dnsmasq_health = self._dnsmasq_svc.get_health()
        logger.info(
            f"dnsmasq: enabled={dnsmasq_health.is_enabled}, "
            f"active={dnsmasq_health.is_active}, "
            f"state={dnsmasq_health.active_state}/{dnsmasq_health.sub_state}"
        )

        # Parse config files to recover AP settings
        self._parse_hostapd_config()

        # Publish initial status + health
        self._publish_ap_status()
        self._publish_service_health("hostapd", hostapd_health)
        self._publish_service_health("dnsmasq", dnsmasq_health)

    def _parse_hostapd_config(self):
        """Parse /etc/hostapd/hostapd.conf to recover AP settings."""
        content = self._hostapd_svc.read_config(HOSTAPD_CONFIG_PATH)
        if content is None:
            return

        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key == "ssid":
                self.ap_status.ssid = value
            elif key == "wpa":
                if value == "1":
                    self.ap_status.security = "wpa"
                elif value == "2":
                    self.ap_status.security = "wpa2"
            elif key == "wpa_passphrase":
                self.ap_status.password = value

        # Check for open security (no wpa key in config)
        if "wpa=" not in (content or ""):
            # Only override if we actually read a valid config
            if "ssid=" in (content or ""):
                self.ap_status.security = "open"
                self.ap_status.password = ""

    def stop(self):
        """Stop the networking bridge."""
        logger.info("Stopping...")
        self.running = False

    # ======== Polling Loop ========

    def _poll_loop(self):
        """Poll status every 10 seconds."""
        # Publish initial status on startup
        self._publish_interfaces()
        self._publish_client_status()
        self._publish_ap_status()

        while self.running:
            try:
                self._update_interfaces()
                self._update_client_status()
                self._update_ap_status()
                self._update_ap_clients()
            except Exception as e:
                logger.error(f"Error in poll loop: {e}")
            time.sleep(10)

    # ======== AP Management ========

    def _configure_ap(self) -> bool:
        """Write hostapd config file via ServiceController."""
        logger.info(
            f"Configuring AP: SSID={self.ap_status.ssid}, "
            f"Security={self.ap_status.security}"
        )

        config = f"""interface={self.ap_interface}
driver=nl80211
ssid={self.ap_status.ssid}
hw_mode=g
channel=11
ieee80211n=1
wmm_enabled=1
ap_isolate=0
ignore_broadcast_ssid=0

# HT capabilities for 802.11n
ht_capab=[SHORT-GI-20][DSSS_CCK-40]

# QoS settings
wmm_ac_bk_cwmin=4
wmm_ac_bk_cwmax=10
wmm_ac_bk_aifs=7
wmm_ac_bk_txop_limit=0

wmm_ac_be_cwmin=4
wmm_ac_be_cwmax=6
wmm_ac_be_aifs=3
wmm_ac_be_txop_limit=0

wmm_ac_vi_cwmin=3
wmm_ac_vi_cwmax=4
wmm_ac_vi_aifs=2
wmm_ac_vi_txop_limit=94

wmm_ac_vo_cwmin=2
wmm_ac_vo_cwmax=3
wmm_ac_vo_aifs=2
wmm_ac_vo_txop_limit=47
"""

        # Add security config
        if self.ap_status.security == "wpa":
            config += f"""wpa=1
wpa_passphrase={self.ap_status.password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
"""
        elif self.ap_status.security == "wpa2":
            config += f"""wpa=2
wpa_passphrase={self.ap_status.password}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
"""
        # For "open" security, no wpa config needed

        if not self._hostapd_svc.write_config(HOSTAPD_CONFIG_PATH, config):
            logger.error("Failed to write hostapd config")
            return False

        logger.info("hostapd config written")
        return True

    def _configure_dnsmasq(self) -> bool:
        """Write dnsmasq config file via ServiceController."""
        ip, cidr = self.ap_status.ip_cidr.split("/")
        network_parts = ip.split(".")
        network_base = ".".join(network_parts[:3])
        dhcp_start = f"{network_base}.50"
        dhcp_end = f"{network_base}.150"

        config = f"""interface={self.ap_interface}
dhcp-range={dhcp_start},{dhcp_end},12h
bind-interfaces
dhcp-option=3,{ip}
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
server=8.8.4.4
"""

        if not self._dnsmasq_svc.write_config(DNSMASQ_CONFIG_PATH, config):
            logger.error("Failed to write dnsmasq config")
            return False

        logger.info("dnsmasq config written")
        return True

    def _write_ap_env(self) -> bool:
        """Write AP environment file for systemd ExecStartPre/Post scripts."""
        ip, cidr = self.ap_status.ip_cidr.split("/")
        network_parts = ip.split(".")
        network = f"{network_parts[0]}.{network_parts[1]}.{network_parts[2]}.0/{cidr}"

        env_content = f"""# AP environment - written by networkingbridge
AP_INTERFACE={self.ap_interface}
AP_IP_CIDR={self.ap_status.ip_cidr}
AP_NETWORK={network}
CLIENT_INTERFACE={self.client_interface}
"""

        if not self._hostapd_svc.write_config(AP_ENV_PATH, env_content):
            logger.error("Failed to write AP env file")
            return False

        return True

    def _enable_ap(self, enable: bool) -> bool:
        """Enable or disable AP via systemd."""
        logger.info(f"{'Enabling' if enable else 'Disabling'} AP...")

        if enable:
            # Write config files
            if not self._configure_ap():
                publish_notification(
                    self.mqtt, "network", "error", "hotspot",
                    "Failed to configure hostapd",
                )
                return False

            if not self._configure_dnsmasq():
                publish_notification(
                    self.mqtt, "network", "error", "hotspot",
                    "Failed to configure dnsmasq",
                )
                return False

            if not self._write_ap_env():
                publish_notification(
                    self.mqtt, "network", "error", "hotspot",
                    "Failed to write AP environment",
                )
                return False

            # Enable and start via systemd (ExecStartPre handles interface setup,
            # ExecStartPost handles routing, dnsmasq auto-starts via BindsTo)
            if not self._hostapd_svc.enable():
                logger.error("Failed to enable hostapd")
                publish_notification(
                    self.mqtt, "network", "error", "hotspot",
                    "Failed to enable hotspot",
                )
                return False

            logger.info("AP enabled successfully")
            self.ap_status.enabled = True
            self.ap_status.running = True
            publish_notification(
                self.mqtt, "network", "enabled", "hotspot",
                f"Hotspot '{self.ap_status.ssid}' enabled",
            )
        else:
            # Disable and stop via systemd (ExecStopPost handles routing teardown
            # and interface cleanup, dnsmasq auto-stops via BindsTo)
            if not self._hostapd_svc.disable():
                logger.error("Failed to disable hostapd")
                return False

            logger.info("AP disabled successfully")
            self.ap_status.enabled = False
            self.ap_status.running = False
            self.ap_status.clients = []
            publish_notification(
                self.mqtt, "network", "disabled", "hotspot",
                "Hotspot disabled",
            )

        self._publish_ap_status()
        return True

    # ======== Client Management ========

    def _connect_to_network(self, ssid: str, password: str = "") -> bool:
        """Connect to a Wi-Fi network via NM D-Bus."""
        logger.info(f"Connecting to network: {ssid}")

        if not self._client_dev_path:
            self._client_dev_path = self._nm.get_wifi_device(self.client_interface)
            if not self._client_dev_path:
                logger.error(f"Client device {self.client_interface} not found")
                self._publish_connection_result(ssid, False)
                return False

        success = self._nm.connect(self._client_dev_path, ssid, password)

        if success:
            logger.info(f"Connected to {ssid}")
        else:
            logger.error(f"Failed to connect to {ssid}")

        self._publish_connection_result(ssid, success)
        return success

    def _disconnect_from_network(self) -> bool:
        """Disconnect from current Wi-Fi network via NM D-Bus."""
        logger.info("Disconnecting from network...")

        if not self._client_dev_path:
            logger.warning("No client device path")
            return False

        success = self._nm.disconnect(self._client_dev_path)

        if success:
            logger.info("Disconnected successfully")
        else:
            logger.error("Failed to disconnect")

        return success

    def _scan_networks(self) -> List[Network]:
        """Scan for available Wi-Fi networks via NM D-Bus."""
        logger.info("Scanning for networks...")
        self.scanning = True
        self._publish_scanning(True)

        if not self._client_dev_path:
            self._client_dev_path = self._nm.get_wifi_device(self.client_interface)

        networks = []
        if self._client_dev_path:
            raw = self._nm.scan_networks(self._client_dev_path)
            networks = [
                Network(
                    ssid=n["ssid"],
                    security=n["security"],
                    signal_percent=n["signal_percent"],
                    signal_dbm=n["signal_dbm"],
                    frequency=n["frequency"],
                    connected=n["connected"],
                )
                for n in raw
            ]

        self.scan_results = networks
        self.scanning = False
        self._publish_scan_results()
        self._publish_scanning(False)

        logger.info(f"Found {len(networks)} networks")
        return networks

    # ======== Status Polling ========

    def _update_interfaces(self):
        """Check which interfaces are detected via NM D-Bus."""
        self.interfaces = {
            "client": InterfaceInfo(
                name=self.client_interface,
                mode="client",
                detected=self._nm.is_device_present(self.client_interface),
                enabled=True,
            ),
            "ap": InterfaceInfo(
                name=self.ap_interface,
                mode="ap",
                detected=self._nm.is_device_present(self.ap_interface),
                enabled=self.ap_status.enabled,
            ),
        }
        self._publish_interfaces()

    def _update_client_status(self):
        """Update client connection status via NM D-Bus."""
        if not self._client_dev_path:
            self._client_dev_path = self._nm.get_wifi_device(self.client_interface)
            if not self._client_dev_path:
                return

        details = self._nm.get_connection_details(self._client_dev_path)
        if details is None:
            return

        was_connected = self.client_status.connected
        self.client_status.connected = details["connected"]
        self.client_status.ssid = details["ssid"]
        self.client_status.ip_address = details["ip_address"]
        self.client_status.cidr = details["cidr"]
        self.client_status.router = details["router"]
        self.client_status.signal_percent = details["signal_percent"]
        self.client_status.signal_dbm = details["signal_dbm"]

        if details["connected"] != was_connected:
            self._publish_client_status()

    def _update_ap_status(self):
        """Update AP status from systemd health."""
        hostapd_health = self._hostapd_svc.get_health()
        dnsmasq_health = self._dnsmasq_svc.get_health()
        changed = False

        if hostapd_health.is_active != self.ap_status.running:
            self.ap_status.running = hostapd_health.is_active
            changed = True
            if not hostapd_health.is_active and self.ap_status.enabled:
                publish_notification(
                    self.mqtt, "network", "stopped", "hotspot",
                    f"Hotspot stopped unexpectedly "
                    f"({hostapd_health.active_state}/{hostapd_health.sub_state})",
                )

        if hostapd_health.is_enabled != self.ap_status.enabled:
            self.ap_status.enabled = hostapd_health.is_enabled
            changed = True

        if changed:
            self._publish_ap_status()

        # Always publish health for monitoring
        self._publish_service_health("hostapd", hostapd_health)
        self._publish_service_health("dnsmasq", dnsmasq_health)

    def _update_ap_clients(self):
        """Update list of connected AP clients from /proc/net/arp."""
        if not self.ap_status.running:
            if len(self.ap_status.clients) > 0:
                self.ap_status.clients = []
                self._publish_ap_status()
            return

        raw_clients = get_ap_clients(self.ap_interface)
        clients = [
            APClient(
                ip=c["ip"],
                mac=c["mac"],
                vendor=self._oui.lookup(c["mac"]),
            )
            for c in raw_clients
        ]

        # Only publish if changed
        if len(clients) != len(self.ap_status.clients):
            self.ap_status.clients = clients
            self._publish_ap_status()

    # ======== MQTT Interface ========

    def _subscribe_mqtt(self):
        """Subscribe to command topics."""
        topics = [
            "protogen/fins/networkingbridge/scan/start",
            "protogen/fins/networkingbridge/client/enable",
            "protogen/fins/networkingbridge/client/connect",
            "protogen/fins/networkingbridge/client/disconnect",
            "protogen/fins/networkingbridge/ap/enable",
            "protogen/fins/networkingbridge/ap/config",
            "protogen/fins/networkingbridge/qrcode/generate",
        ]

        for topic in topics:
            self.mqtt.subscribe(topic)
            logger.debug(f"Subscribed to {topic}")

        # Set up message callbacks
        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/scan/start",
            lambda c, u, m: threading.Thread(
                target=self._scan_networks, daemon=True
            ).start(),
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/client/enable",
            lambda c, u, m: self._handle_client_enable(json.loads(m.payload)),
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/client/connect",
            lambda c, u, m: threading.Thread(
                target=self._handle_client_connect,
                args=(json.loads(m.payload),),
                daemon=True,
            ).start(),
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/client/disconnect",
            lambda c, u, m: self._disconnect_from_network(),
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/ap/enable",
            lambda c, u, m: threading.Thread(
                target=self._enable_ap,
                args=(json.loads(m.payload)["enable"],),
                daemon=True,
            ).start(),
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/ap/config",
            lambda c, u, m: self._handle_ap_config(json.loads(m.payload)),
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/qrcode/generate",
            lambda c, u, m: self._generate_qrcode(),
        )

    def _handle_client_enable(self, data: Dict):
        """Handle client enable/disable."""
        enable = data.get("enable", True)
        logger.info(f"Client enable={enable} (not implemented)")

    def _handle_client_connect(self, data: Dict):
        """Handle client connection request."""
        ssid = data.get("ssid", "")
        password = data.get("password", "")
        self._connect_to_network(ssid, password)

    def _handle_ap_config(self, data: Dict):
        """Handle AP configuration update."""
        logger.info(f"Updating AP config: {data}")

        self.ap_status.ssid = data.get("ssid", self.ap_status.ssid)
        self.ap_status.security = data.get("security", self.ap_status.security)
        self.ap_status.password = data.get("password", self.ap_status.password)
        self.ap_status.ip_cidr = data.get("ip_cidr", self.ap_status.ip_cidr)

        if self.ap_status.running:
            logger.info("Restarting AP with new config...")
            self._configure_ap()
            self._configure_dnsmasq()
            self._write_ap_env()
            self._hostapd_svc.restart()
            publish_notification(
                self.mqtt, "network", "restarted", "hotspot",
                f"Hotspot restarted with new config (SSID: {self.ap_status.ssid})",
            )
        else:
            self._publish_ap_status()

    def _generate_qrcode(self):
        """Generate Wi-Fi QR code."""
        logger.info("Generating QR code...")

        if self.ap_status.security == "open":
            wifi_str = f"WIFI:T:nopass;S:{self.ap_status.ssid};;"
        else:
            wifi_str = (
                f"WIFI:T:WPA;S:{self.ap_status.ssid};"
                f"P:{self.ap_status.password};;"
            )

        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(wifi_str)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.read()).decode()
        data_url = f"data:image/png;base64,{img_base64}"

        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/qrcode",
            json.dumps({"qrcode": data_url}),
            retain=True,
        )

        logger.info("QR code generated and published")

    # ======== MQTT Publishers ========

    def _publish_interfaces(self):
        """Publish interface status."""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/interfaces",
            json.dumps({k: asdict(v) for k, v in self.interfaces.items()}),
            retain=True,
        )

    def _publish_client_status(self):
        """Publish client status."""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/client",
            json.dumps(asdict(self.client_status)),
            retain=True,
        )

    def _publish_ap_status(self):
        """Publish AP status."""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/ap",
            json.dumps(asdict(self.ap_status)),
            retain=True,
        )

    def _publish_scan_results(self):
        """Publish scan results."""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/scan",
            json.dumps([asdict(n) for n in self.scan_results]),
            retain=True,
        )

    def _publish_scanning(self, scanning: bool):
        """Publish scanning state."""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/scanning",
            json.dumps(scanning),
        )

    def _publish_connection_result(self, ssid: str, success: bool):
        """Publish connection result."""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/connection",
            json.dumps({"ssid": ssid, "success": success}),
        )

    def _publish_service_health(self, service: str, health):
        """Publish systemd service health."""
        self.mqtt.publish(
            f"protogen/fins/networkingbridge/status/{service}/health",
            json.dumps(health.to_dict()),
            retain=True,
        )

    # ======== Lifecycle ========

    def cleanup(self):
        """Cleanup on shutdown."""
        logger.info("Stopping...")
        self.running = False
        self.mqtt.loop_stop()
        self.mqtt.disconnect()
        logger.info("Stopped")

    def run(self):
        """Main run loop."""
        logger.info("Starting networking bridge...")

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.start()

        logger.info("Networking bridge is running")

        try:
            while self.running:
                signal.pause()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")

        self.cleanup()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        self.running = False


def main():
    """Main entry point."""
    setup_logger("networkingbridge")

    config_loader = ConfigLoader()
    config = config_loader.config

    mqtt_client = create_mqtt_client(config_loader)
    mqtt_client.loop_start()

    bridge = NetworkingBridge(config, mqtt_client)
    bridge.run()


if __name__ == "__main__":
    main()

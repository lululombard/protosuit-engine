"""
Networking Bridge - Simple and Reliable Implementation
Manages Wi-Fi client and AP modes via NetworkManager (nmcli)
"""

import subprocess
import json
import time
import threading
import ipaddress
import io
import base64
import signal
import yaml
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict
import paho.mqtt.client as mqtt
import qrcode


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
    ssid: str = "Protosuit"
    security: str = "wpa"
    password: str = "BeepBoop"
    ip_cidr: str = "192.168.50.1/24"
    routing_enabled: bool = True
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
        self.client_interface = config['networking']['client']['interface']  # wlan1
        self.ap_interface = config['networking']['ap']['interface']  # wlan0

        # State
        self.interfaces = {}
        self.client_status = ClientStatus(connected=False)
        self.ap_status = APStatus()
        self.scan_results = []
        self.scanning = False

        # Lock to prevent concurrent AP enable/disable operations
        self.ap_lock = threading.Lock()

        # Load AP config from file
        self._load_ap_config()

    def _load_ap_config(self):
        """Load AP configuration from config file"""
        ap_config = self.config['networking'].get('ap', {})
        self.ap_status.ssid = ap_config.get('ssid', 'Protosuit')
        self.ap_status.security = ap_config.get('security', 'wpa')
        self.ap_status.password = ap_config.get('password', 'BeepBoop')
        self.ap_status.ip_cidr = ap_config.get('ip_cidr', '192.168.50.1/24')

        routing_config = self.config['networking'].get('routing', {})
        self.ap_status.routing_enabled = routing_config.get('enabled', True)

    def start(self):
        """Start the networking bridge"""
        print("[NetworkingBridge] Starting...")
        self.running = True

        # Subscribe to MQTT topics
        self._subscribe_mqtt()

        # Restore AP state from retained MQTT message
        self._restore_ap_state()

        # Start polling loop
        threading.Thread(target=self._poll_loop, daemon=True).start()

        print("[NetworkingBridge] Started successfully")

    def _restore_ap_state(self):
        """Restore AP state from retained MQTT message"""
        # Subscribe to get retained messages for AP config
        self.mqtt.subscribe("protogen/fins/networkingbridge/ap/config")

        # Give MQTT a moment to receive retained messages
        time.sleep(0.5)

    def stop(self):
        """Stop the networking bridge"""
        print("[NetworkingBridge] Stopping...")
        self.running = False

    # ======== Polling Loop ========

    def _poll_loop(self):
        """Simple polling loop - check status every 2 seconds"""
        while self.running:
            try:
                self._update_interfaces()
                self._update_client_status()
                self._update_ap_status()
                self._update_ap_clients()
            except Exception as e:
                print(f"[NetworkingBridge] Error in poll loop: {e}")
            time.sleep(2)

    # ======== AP Management ========

    def _configure_ap(self) -> bool:
        """Configure AP using hostapd"""
        print(f"[NetworkingBridge] Configuring AP: SSID={self.ap_status.ssid}, Security={self.ap_status.security}")

        # Remove wlan0 from NetworkManager control
        subprocess.run(
            ["sudo", "nmcli", "device", "set", self.ap_interface, "managed", "no"],
            capture_output=True
        )

        # Bring interface down
        subprocess.run(["sudo", "ip", "link", "set", self.ap_interface, "down"], capture_output=True)
        time.sleep(0.5)

        # Bring interface up
        subprocess.run(["sudo", "ip", "link", "set", self.ap_interface, "up"], capture_output=True)
        time.sleep(0.5)

        # Disable power save - critical for performance
        subprocess.run(["sudo", "iw", "dev", self.ap_interface, "set", "power_save", "off"], capture_output=True)

        # Set IP address
        ip, cidr = self.ap_status.ip_cidr.split('/')
        subprocess.run(
            ["sudo", "ip", "addr", "flush", "dev", self.ap_interface],
            capture_output=True
        )
        subprocess.run(
            ["sudo", "ip", "addr", "add", self.ap_status.ip_cidr, "dev", self.ap_interface],
            capture_output=True
        )

        # Create hostapd config with performance optimizations
        config = f"""interface={self.ap_interface}
driver=nl80211
ssid={self.ap_status.ssid}
hw_mode=g
channel=1
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

        # Write hostapd config
        config_path = "/tmp/hostapd-ap.conf"
        try:
            with open(config_path, 'w') as f:
                f.write(config)
        except Exception as e:
            print(f"[NetworkingBridge] Failed to write hostapd config: {e}")
            return False

        print("[NetworkingBridge] AP configured successfully")
        return True

    def _start_dnsmasq(self) -> bool:
        """Start dnsmasq for DHCP"""
        print("[NetworkingBridge] Starting dnsmasq...")

        # First, stop any existing dnsmasq instance
        self._stop_dnsmasq()

        # Parse IP/CIDR
        ip, cidr = self.ap_status.ip_cidr.split('/')

        # Calculate DHCP range: .50 to .150
        network_parts = ip.split('.')
        network_base = '.'.join(network_parts[:3])
        dhcp_start = f"{network_base}.50"
        dhcp_end = f"{network_base}.150"

        # Create dnsmasq config with DNS and gateway
        config = f"""interface={self.ap_interface}
dhcp-range={dhcp_start},{dhcp_end},12h
bind-interfaces
dhcp-option=3,{ip}
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
server=8.8.4.4
"""

        # Write config
        config_path = "/tmp/dnsmasq-ap.conf"
        try:
            with open(config_path, 'w') as f:
                f.write(config)
        except Exception as e:
            print(f"[NetworkingBridge] Failed to write dnsmasq config: {e}")
            return False

        # Start dnsmasq
        result = subprocess.run(
            ["sudo", "dnsmasq", f"--conf-file={config_path}", f"--pid-file=/tmp/dnsmasq-ap.pid"],
            capture_output=True, text=True
        )

        if result.returncode != 0:
            print(f"[NetworkingBridge] Failed to start dnsmasq: {result.stderr}")
            return False

        print("[NetworkingBridge] dnsmasq started successfully")
        return True

    def _stop_dnsmasq(self):
        """Stop dnsmasq"""
        print("[NetworkingBridge] Stopping dnsmasq...")
        subprocess.run(
            ["sudo", "pkill", "-f", "dnsmasq.*dnsmasq-ap"],
            capture_output=True
        )
        time.sleep(0.5)  # Wait for it to actually stop

    def _enable_ap(self, enable: bool) -> bool:
        """Enable or disable AP"""
        with self.ap_lock:
            print(f"[NetworkingBridge] {'Enabling' if enable else 'Disabling'} AP...")

            if enable:
                # Stop any existing hostapd
                subprocess.run(["sudo", "pkill", "hostapd"], capture_output=True)
                time.sleep(0.5)

                # Configure first
                if not self._configure_ap():
                    return False

                # Start hostapd in background
                result = subprocess.Popen(
                    ["sudo", "/usr/sbin/hostapd", "-B", "/tmp/hostapd-ap.conf"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                time.sleep(2)  # Wait for hostapd to start

                # Check if hostapd is running
                check = subprocess.run(
                    ["pgrep", "-f", "/usr/sbin/hostapd"],
                    capture_output=True
                )

                if check.returncode != 0:
                    print("[NetworkingBridge] Failed to start hostapd")
                    return False

                # Start dnsmasq
                if not self._start_dnsmasq():
                    # Failed to start dnsmasq, stop hostapd
                    subprocess.run(["sudo", "pkill", "hostapd"], capture_output=True)
                    return False

                # Enable routing if configured
                if self.ap_status.routing_enabled:
                    self._enable_routing(True)

                print("[NetworkingBridge] AP enabled successfully")
                self.ap_status.enabled = True
                self._publish_ap_status()
                return True
            else:
                # Stop hostapd
                subprocess.run(["sudo", "pkill", "hostapd"], capture_output=True)

                # Stop dnsmasq
                self._stop_dnsmasq()

                # Disable routing
                self._enable_routing(False)

                # Give wlan0 back to NetworkManager
                subprocess.run(
                    ["sudo", "nmcli", "device", "set", self.ap_interface, "managed", "yes"],
                    capture_output=True
                )

                # Flush IP address
                subprocess.run(
                    ["sudo", "ip", "addr", "flush", "dev", self.ap_interface],
                    capture_output=True
                )

                print("[NetworkingBridge] AP disabled successfully")
                self.ap_status.enabled = False
                self._publish_ap_status()
                return True

    # ======== Routing (NAT) ========

    def _enable_routing(self, enable: bool):
        """Enable/disable NAT routing from AP to client"""
        print(f"[NetworkingBridge] {'Enabling' if enable else 'Disabling'} routing...")

        if enable:
            # Enable IP forwarding
            subprocess.run(
                ["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"],
                capture_output=True
            )

            # Get AP network
            ip, cidr = self.ap_status.ip_cidr.split('/')
            network_parts = ip.split('.')
            network = f"{network_parts[0]}.{network_parts[1]}.{network_parts[2]}.0/{cidr}"

            # Add iptables rules - use source network instead of interface
            # MASQUERADE rule for AP network going out any interface
            if subprocess.run([
                "sudo", "iptables", "-t", "nat", "-C", "POSTROUTING",
                "-s", network, "!", "-d", network, "-j", "MASQUERADE"
            ], capture_output=True).returncode != 0:
                subprocess.run([
                    "sudo", "iptables", "-t", "nat", "-A", "POSTROUTING",
                    "-s", network, "!", "-d", network, "-j", "MASQUERADE"
                ], capture_output=True)

            # Forward from AP to anywhere
            if subprocess.run([
                "sudo", "iptables", "-C", "FORWARD",
                "-i", self.ap_interface, "-s", network,
                "-j", "ACCEPT"
            ], capture_output=True).returncode != 0:
                subprocess.run([
                    "sudo", "iptables", "-A", "FORWARD",
                    "-i", self.ap_interface, "-s", network,
                    "-j", "ACCEPT"
                ], capture_output=True)

            # Forward to AP (established connections)
            if subprocess.run([
                "sudo", "iptables", "-C", "FORWARD",
                "-o", self.ap_interface, "-d", network,
                "-m", "state", "--state", "RELATED,ESTABLISHED",
                "-j", "ACCEPT"
            ], capture_output=True).returncode != 0:
                subprocess.run([
                    "sudo", "iptables", "-A", "FORWARD",
                    "-o", self.ap_interface, "-d", network,
                    "-m", "state", "--state", "RELATED,ESTABLISHED",
                    "-j", "ACCEPT"
                ], capture_output=True)

            print("[NetworkingBridge] Routing enabled")
            self.ap_status.routing_enabled = True
        else:
            # Get AP network
            ip, cidr = self.ap_status.ip_cidr.split('/')
            network_parts = ip.split('.')
            network = f"{network_parts[0]}.{network_parts[1]}.{network_parts[2]}.0/{cidr}"

            # Remove iptables rules
            subprocess.run([
                "sudo", "iptables", "-t", "nat", "-D", "POSTROUTING",
                "-s", network, "!", "-d", network, "-j", "MASQUERADE"
            ], capture_output=True)

            subprocess.run([
                "sudo", "iptables", "-D", "FORWARD",
                "-i", self.ap_interface, "-s", network,
                "-j", "ACCEPT"
            ], capture_output=True)

            subprocess.run([
                "sudo", "iptables", "-D", "FORWARD",
                "-o", self.ap_interface, "-d", network,
                "-m", "state", "--state", "RELATED,ESTABLISHED",
                "-j", "ACCEPT"
            ], capture_output=True)

            print("[NetworkingBridge] Routing disabled")
            self.ap_status.routing_enabled = False

        self._publish_ap_status()

    # ======== Client Management ========

    def _connect_to_network(self, ssid: str, password: str = "") -> bool:
        """Connect to a network"""
        print(f"[NetworkingBridge] Connecting to network: {ssid}")

        # Create connection
        cmd = [
            "sudo", "nmcli", "device", "wifi", "connect", ssid,
            "ifname", self.client_interface  # wlan1
        ]

        if password:
            cmd.extend(["password", password])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        success = result.returncode == 0

        if success:
            print(f"[NetworkingBridge] Connected to {ssid}")
        else:
            print(f"[NetworkingBridge] Failed to connect to {ssid}: {result.stderr}")

        # Publish result
        self._publish_connection_result(ssid, success)

        return success

    def _disconnect_from_network(self) -> bool:
        """Disconnect from current network"""
        print("[NetworkingBridge] Disconnecting from network...")

        result = subprocess.run(
            ["sudo", "nmcli", "device", "disconnect", self.client_interface],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            print("[NetworkingBridge] Disconnected successfully")
            return True
        else:
            print(f"[NetworkingBridge] Failed to disconnect: {result.stderr}")
            return False

    def _scan_networks(self) -> List[Network]:
        """Scan for available networks"""
        print("[NetworkingBridge] Scanning for networks...")
        self.scanning = True
        self._publish_scanning(True)

        # Trigger scan
        subprocess.run(
            ["sudo", "nmcli", "device", "wifi", "rescan", "ifname", self.client_interface],
            capture_output=True
        )

        time.sleep(3)  # Wait for scan

        # Get results
        result = subprocess.run(
            ["sudo", "nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL,FREQ,ACTIVE",
             "device", "wifi", "list", "ifname", self.client_interface],
            capture_output=True, text=True
        )

        networks = []
        seen_ssids = set()

        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            parts = line.split(':')
            if len(parts) >= 5:
                ssid = parts[0]

                # Skip empty SSIDs and duplicates
                if not ssid or ssid in seen_ssids:
                    continue

                seen_ssids.add(ssid)

                security = parts[1] if parts[1] else "Open"
                signal = int(parts[2]) if parts[2] else 0
                freq = parts[3]
                active = parts[4] == 'yes'

                # Convert signal to dBm (approximate)
                signal_dbm = -100 + signal

                networks.append(Network(
                    ssid=ssid,
                    security=security,
                    signal_percent=signal,
                    signal_dbm=signal_dbm,
                    frequency=freq,
                    connected=active
                ))

        self.scan_results = networks
        self.scanning = False
        self._publish_scan_results()
        self._publish_scanning(False)

        print(f"[NetworkingBridge] Found {len(networks)} networks")
        return networks

    # ======== Status Polling ========

    def _update_interfaces(self):
        """Check which interfaces are detected"""
        result = subprocess.run(
            ["ip", "link", "show"],
            capture_output=True, text=True
        )

        self.interfaces = {
            'client': InterfaceInfo(
                name=self.client_interface,
                mode='client',
                detected=self.client_interface in result.stdout,
                enabled=True
            ),
            'ap': InterfaceInfo(
                name=self.ap_interface,
                mode='ap',
                detected=self.ap_interface in result.stdout,
                enabled=self.ap_status.enabled
            )
        }

        self._publish_interfaces()

    def _update_client_status(self):
        """Update client connection status"""
        result = subprocess.run(
            ["sudo", "nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION",
             "device", "status"],
            capture_output=True, text=True
        )

        connected = False
        for line in result.stdout.split('\n'):
            if line.startswith(self.client_interface):
                parts = line.split(':')
                if len(parts) >= 2 and parts[1] == 'connected':
                    connected = True
                    break

        was_connected = self.client_status.connected
        self.client_status.connected = connected

        if connected:
            # Get connection details
            self._update_client_details()
        else:
            # Clear details
            self.client_status.ssid = ""
            self.client_status.ip_address = ""
            self.client_status.router = ""
            self.client_status.signal_dbm = -100
            self.client_status.signal_percent = 0

        # Publish if status changed
        if connected != was_connected:
            self._publish_client_status()

    def _update_client_details(self):
        """Get detailed client connection info"""
        # Get SSID and signal
        result = subprocess.run(
            ["sudo", "nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL",
             "device", "wifi", "list", "ifname", self.client_interface],
            capture_output=True, text=True
        )

        for line in result.stdout.split('\n'):
            if line.startswith('yes:'):
                parts = line.split(':')
                if len(parts) >= 3:
                    self.client_status.ssid = parts[1]
                    signal = int(parts[2]) if parts[2] else 0
                    self.client_status.signal_percent = signal
                    self.client_status.signal_dbm = -100 + signal
                    break

        # Get IP address
        result = subprocess.run(
            ["ip", "-4", "addr", "show", self.client_interface],
            capture_output=True, text=True
        )

        for line in result.stdout.split('\n'):
            if 'inet ' in line:
                parts = line.strip().split()
                if len(parts) >= 2:
                    ip_cidr = parts[1]
                    ip, cidr = ip_cidr.split('/')
                    self.client_status.ip_address = ip
                    self.client_status.cidr = int(cidr)
                    break

        # Get router (gateway)
        result = subprocess.run(
            ["ip", "route", "show", "dev", self.client_interface],
            capture_output=True, text=True
        )

        for line in result.stdout.split('\n'):
            if 'default via' in line:
                parts = line.split()
                if len(parts) >= 3:
                    self.client_status.router = parts[2]
                    break

        self._publish_client_status()

    def _update_ap_status(self):
        """Update AP status - check if hostapd is running"""
        result = subprocess.run(
            ["pgrep", "-f", "/usr/sbin/hostapd"],
            capture_output=True
        )

        is_active = result.returncode == 0

        if is_active != self.ap_status.enabled:
            self.ap_status.enabled = is_active
            self._publish_ap_status()

    def _update_ap_clients(self):
        """Update list of connected AP clients"""
        if not self.ap_status.enabled:
            if len(self.ap_status.clients) > 0:
                self.ap_status.clients = []
                self._publish_ap_status()
            return

        # Parse arp table for connected clients
        result = subprocess.run(
            ["ip", "neigh", "show", "dev", self.ap_interface],
            capture_output=True, text=True
        )

        clients = []
        for line in result.stdout.split('\n'):
            if "REACHABLE" in line or "STALE" in line:
                parts = line.split()
                if len(parts) >= 5:
                    ip = parts[0]
                    mac = parts[4]
                    clients.append(APClient(ip=ip, mac=mac))

        # Only publish if changed
        if len(clients) != len(self.ap_status.clients):
            self.ap_status.clients = clients
            self._publish_ap_status()

    # ======== MQTT Interface ========

    def _subscribe_mqtt(self):
        """Subscribe to command topics"""
        topics = [
            "protogen/fins/networkingbridge/scan/start",
            "protogen/fins/networkingbridge/client/enable",
            "protogen/fins/networkingbridge/client/connect",
            "protogen/fins/networkingbridge/client/disconnect",
            "protogen/fins/networkingbridge/ap/enable",
            "protogen/fins/networkingbridge/ap/config",
            "protogen/fins/networkingbridge/routing/enable",
            "protogen/fins/networkingbridge/qrcode/generate",
        ]

        for topic in topics:
            self.mqtt.subscribe(topic)
            print(f"[NetworkingBridge] Subscribed to {topic}")

        # Set up message callbacks
        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/scan/start",
            lambda client, userdata, msg: threading.Thread(target=self._scan_networks, daemon=True).start()
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/client/enable",
            lambda client, userdata, msg: self._handle_client_enable(json.loads(msg.payload))
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/client/connect",
            lambda client, userdata, msg: threading.Thread(
                target=self._handle_client_connect, args=(json.loads(msg.payload),), daemon=True
            ).start()
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/client/disconnect",
            lambda client, userdata, msg: self._disconnect_from_network()
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/ap/enable",
            lambda client, userdata, msg: threading.Thread(
                target=self._enable_ap, args=(json.loads(msg.payload)['enable'],), daemon=True
            ).start()
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/ap/config",
            lambda client, userdata, msg: self._handle_ap_config(json.loads(msg.payload))
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/routing/enable",
            lambda client, userdata, msg: self._enable_routing(json.loads(msg.payload)['enable'])
        )

        self.mqtt.message_callback_add(
            "protogen/fins/networkingbridge/qrcode/generate",
            lambda client, userdata, msg: self._generate_qrcode()
        )

    def _handle_client_enable(self, data: Dict):
        """Handle client enable/disable"""
        enable = data.get('enable', True)
        # For now, just log - client is always enabled
        print(f"[NetworkingBridge] Client enable={enable} (not implemented)")

    def _handle_client_connect(self, data: Dict):
        """Handle client connection request"""
        ssid = data.get('ssid', '')
        password = data.get('password', '')
        self._connect_to_network(ssid, password)

    def _handle_ap_config(self, data: Dict):
        """Handle AP configuration update"""
        print(f"[NetworkingBridge] Updating AP config: {data}")

        # Update configuration
        self.ap_status.ssid = data.get('ssid', self.ap_status.ssid)
        self.ap_status.security = data.get('security', self.ap_status.security)
        self.ap_status.password = data.get('password', self.ap_status.password)
        self.ap_status.ip_cidr = data.get('ip_cidr', self.ap_status.ip_cidr)

        # If AP is currently enabled, restart it with new config
        if self.ap_status.enabled:
            print("[NetworkingBridge] Restarting AP with new config...")
            # Save routing state before disabling
            routing_was_enabled = self.ap_status.routing_enabled
            self._enable_ap(False)
            # Restore routing state
            self.ap_status.routing_enabled = routing_was_enabled
            time.sleep(1)
            self._enable_ap(True)
        else:
            # Just publish the updated config
            self._publish_ap_status()

    def _generate_qrcode(self):
        """Generate Wi-Fi QR code"""
        print("[NetworkingBridge] Generating QR code...")

        # Create Wi-Fi QR code string
        # Format: WIFI:T:WPA;S:SSID;P:password;;
        if self.ap_status.security == "open":
            wifi_str = f"WIFI:T:nopass;S:{self.ap_status.ssid};;"
        else:
            # Use WPA for both wpa and wpa2
            wifi_str = f"WIFI:T:WPA;S:{self.ap_status.ssid};P:{self.ap_status.password};;"

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(wifi_str)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.read()).decode()
        data_url = f"data:image/png;base64,{img_base64}"

        # Publish QR code
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/qrcode",
            json.dumps({"qrcode": data_url})
        )

        print("[NetworkingBridge] QR code generated and published")

    # ======== MQTT Publishers ========

    def _publish_interfaces(self):
        """Publish interface status"""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/interfaces",
            json.dumps({k: asdict(v) for k, v in self.interfaces.items()})
        )

    def _publish_client_status(self):
        """Publish client status"""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/client",
            json.dumps(asdict(self.client_status))
        )

    def _publish_ap_status(self):
        """Publish AP status"""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/ap",
            json.dumps(asdict(self.ap_status))
        )

    def _publish_scan_results(self):
        """Publish scan results"""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/scan",
            json.dumps([asdict(n) for n in self.scan_results])
        )

    def _publish_scanning(self, scanning: bool):
        """Publish scanning state"""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/scanning",
            json.dumps(scanning)
        )

    def _publish_connection_result(self, ssid: str, success: bool):
        """Publish connection result"""
        self.mqtt.publish(
            "protogen/fins/networkingbridge/status/connection",
            json.dumps({"ssid": ssid, "success": success})
        )

    def cleanup(self):
        """Cleanup on shutdown"""
        print("[NetworkingBridge] Stopping...")
        self.running = False
        self.mqtt.loop_stop()
        self.mqtt.disconnect()
        print("[NetworkingBridge] Stopped")

    def run(self):
        """Main run loop"""
        print("[NetworkingBridge] Starting networking bridge...")

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start the bridge
        self.start()

        print("[NetworkingBridge] Networking bridge is running. Press Ctrl+C to exit.")

        # Keep running
        try:
            while self.running:
                signal.pause()
        except KeyboardInterrupt:
            print("\n[NetworkingBridge] Keyboard interrupt received")

        self.cleanup()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n[NetworkingBridge] Received signal {signum}")
        self.running = False


def main():
    """Main entry point"""
    # Load config
    with open('/home/proto/protosuit-engine/config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Create MQTT client
    mqtt_client = mqtt.Client(
        client_id="protosuit-networkingbridge",
        clean_session=True
    )

    # Connect to MQTT broker
    mqtt_config = config['mqtt']
    mqtt_client.connect(
        mqtt_config['broker'],
        mqtt_config['port'],
        mqtt_config['keepalive']
    )

    # Start MQTT loop
    mqtt_client.loop_start()

    # Create and run bridge
    bridge = NetworkingBridge(config, mqtt_client)
    bridge.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Networking Bridge - Wi-Fi Management Service
Manages integrated Wi-Fi (client mode) and USB Wi-Fi (AP mode)
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
import ipaddress
import base64
import io
from typing import Optional, Dict, List, Any
from pathlib import Path
from dataclasses import dataclass, asdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from utils.mqtt_client import create_mqtt_client
from networkingbridge.oui_lookup import get_oui_lookup

# Try to import qrcode for QR generation
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    print("[NetworkingBridge] Warning: qrcode not available, QR code generation disabled")
    print("[NetworkingBridge] Install with: pip install qrcode[pil]")


@dataclass
class InterfaceStatus:
    """Status of a Wi-Fi interface"""
    name: str
    detected: bool
    enabled: bool
    mode: str  # "client" or "ap"
    driver: str = ""
    mac_address: str = ""


@dataclass
class ClientStatus:
    """Status of client mode Wi-Fi"""
    connected: bool
    ssid: str = ""
    ip_address: str = ""
    cidr: int = 24
    router: str = ""
    signal_dbm: int = 0
    signal_percent: int = 0
    frequency: str = ""


@dataclass 
class APClient:
    """A client connected to the access point"""
    mac: str
    ip: str
    hostname: str = ""
    vendor: str = ""


@dataclass
class APStatus:
    """Status of access point mode Wi-Fi"""
    enabled: bool
    ssid: str = ""
    security: str = "wpa2"  # none, wep, wpa2
    password: str = ""
    ip_cidr: str = ""
    channel: int = 6
    clients: List[APClient] = None
    routing_enabled: bool = False
    captive_portal_enabled: bool = False
    
    def __post_init__(self):
        if self.clients is None:
            self.clients = []


@dataclass
class ScanResult:
    """A Wi-Fi network found during scanning"""
    ssid: str
    bssid: str
    signal_dbm: int
    signal_percent: int
    frequency: str
    security: str  # "Open", "WEP", "WPA", "WPA2", "WPA3"
    connected: bool = False


class NetworkingBridge:
    """
    Wi-Fi Management Service
    
    Manages dual Wi-Fi interfaces:
    - Integrated Wi-Fi (wlan0): Client mode for internet connectivity
    - USB Wi-Fi (wlan1): Access Point mode for device connectivity
    
    Subscribes to:
        - protogen/fins/networkingbridge/scan/start
        - protogen/fins/networkingbridge/client/connect
        - protogen/fins/networkingbridge/client/disconnect
        - protogen/fins/networkingbridge/client/enable
        - protogen/fins/networkingbridge/ap/config
        - protogen/fins/networkingbridge/ap/enable
        - protogen/fins/networkingbridge/routing/enable
        - protogen/fins/networkingbridge/captive/enable
        
    Publishes to:
        - protogen/fins/networkingbridge/status/interfaces
        - protogen/fins/networkingbridge/status/client
        - protogen/fins/networkingbridge/status/ap
        - protogen/fins/networkingbridge/status/scan
        - protogen/fins/networkingbridge/status/qrcode
    """
    
    def __init__(self):
        """Initialize networking bridge"""
        self.config_loader = ConfigLoader()
        self.mqtt_client = None
        self.running = False
        
        # OUI lookup for MAC vendor identification
        self.oui_lookup = get_oui_lookup()
        
        # Interface configuration
        self.client_interface = "wlan0"  # Default, can be overridden by config
        self.ap_interface = "wlan1"      # Default, can be overridden by config
        
        # State tracking (must be before _load_interface_config)
        self.client_status = ClientStatus(connected=False)
        self.ap_status = APStatus(enabled=False)
        
        # Load interface config (after state tracking is initialized)
        self._load_interface_config()
        self.interfaces: Dict[str, InterfaceStatus] = {}
        self.scan_results: List[ScanResult] = []
        self.scanning = False
        
        # Threads
        self.monitor_thread: Optional[threading.Thread] = None
        self.scan_thread: Optional[threading.Thread] = None
        
        # hostapd/dnsmasq config paths
        self.hostapd_conf = "/etc/hostapd/hostapd.conf"
        self.dnsmasq_conf = "/etc/dnsmasq.d/protosuit-ap.conf"
        
        # Flag to track if we've received retained state
        self._state_restored = False
        
        print("[NetworkingBridge] Initialized")
        print(f"[NetworkingBridge] Client interface: {self.client_interface}")
        print(f"[NetworkingBridge] AP interface: {self.ap_interface}")
    
    def _load_interface_config(self) -> None:
        """Load interface configuration from config file"""
        try:
            config = self.config_loader.config
            if 'networkingbridge' in config:
                nb_config = config['networkingbridge']
                if 'interfaces' in nb_config:
                    self.client_interface = nb_config['interfaces'].get('client', 'wlan0')
                    self.ap_interface = nb_config['interfaces'].get('ap', 'wlan1')
                
                # Load AP defaults
                if 'ap' in nb_config:
                    ap_config = nb_config['ap']
                    self.ap_status.ssid = ap_config.get('ssid', 'Protosuit-AP')
                    self.ap_status.security = ap_config.get('security', 'wpa2')
                    self.ap_status.password = ap_config.get('password', 'protosuit123')
                    self.ap_status.ip_cidr = ap_config.get('ip_cidr', '192.168.50.1/24')
                
                # Load routing/captive portal defaults
                if 'routing' in nb_config:
                    self.ap_status.routing_enabled = nb_config['routing'].get('enabled', False)
                if 'captive_portal' in nb_config:
                    self.ap_status.captive_portal_enabled = nb_config['captive_portal'].get('enabled', False)
                    
        except Exception as e:
            print(f"[NetworkingBridge] Error loading config: {e}")
    
    def _publish_retained_state(self) -> None:
        """Publish current state as retained MQTT message"""
        if not self.mqtt_client:
            return
        
        state = {
            'ap': {
                'ssid': self.ap_status.ssid,
                'security': self.ap_status.security,
                'password': self.ap_status.password,
                'ip_cidr': self.ap_status.ip_cidr,
                'enabled': self.ap_status.enabled,
                'routing_enabled': self.ap_status.routing_enabled,
                'captive_portal_enabled': self.ap_status.captive_portal_enabled,
            }
        }
        
        self.mqtt_client.publish(
            'protogen/fins/networkingbridge/state',
            json.dumps(state),
            retain=True
        )
    
    def _restore_from_retained_state(self, state: dict) -> None:
        """Restore AP state from retained MQTT message"""
        if self._state_restored:
            return
        
        self._state_restored = True
        
        if 'ap' not in state:
            return
        
        ap = state['ap']
        
        # Restore config values
        self.ap_status.ssid = ap.get('ssid', self.ap_status.ssid)
        self.ap_status.security = ap.get('security', self.ap_status.security)
        self.ap_status.password = ap.get('password', self.ap_status.password)
        self.ap_status.ip_cidr = ap.get('ip_cidr', self.ap_status.ip_cidr)
        
        # Check if AP should be enabled
        should_enable_ap = ap.get('enabled', False)
        should_enable_routing = ap.get('routing_enabled', False)
        should_enable_captive = ap.get('captive_portal_enabled', False)
        
        if should_enable_ap:
            print("[NetworkingBridge] Restoring AP from retained state...")
            if self._enable_ap(True):
                print("[NetworkingBridge] AP restored successfully")
                if should_enable_routing:
                    self._enable_routing(True)
                if should_enable_captive:
                    self._enable_captive_portal(True)
            else:
                print("[NetworkingBridge] Failed to restore AP")
    
    def _detect_interfaces(self) -> None:
        """Detect Wi-Fi interfaces and their capabilities"""
        self.interfaces.clear()
        
        try:
            # List all network interfaces
            net_path = Path("/sys/class/net")
            
            for iface_path in net_path.iterdir():
                iface_name = iface_path.name
                
                # Check if it's a wireless interface
                wireless_path = iface_path / "wireless"
                if not wireless_path.exists():
                    continue
                
                # Get driver info
                driver = ""
                driver_link = iface_path / "device" / "driver"
                if driver_link.exists():
                    try:
                        driver = driver_link.resolve().name
                    except:
                        pass
                
                # Get MAC address
                mac_address = ""
                address_path = iface_path / "address"
                if address_path.exists():
                    try:
                        mac_address = address_path.read_text().strip()
                    except:
                        pass
                
                # Check if interface is up
                operstate_path = iface_path / "operstate"
                enabled = False
                if operstate_path.exists():
                    try:
                        state = operstate_path.read_text().strip()
                        enabled = state in ("up", "unknown")  # unknown often means up but not connected
                    except:
                        pass
                
                # Determine mode based on interface name
                if iface_name == self.client_interface:
                    mode = "client"
                elif iface_name == self.ap_interface:
                    mode = "ap"
                else:
                    # Auto-detect: integrated (brcmfmac) = client, USB = ap
                    if driver in ("brcmfmac", "brcmsmac"):
                        mode = "client"
                    else:
                        mode = "ap"
                
                self.interfaces[iface_name] = InterfaceStatus(
                    name=iface_name,
                    detected=True,
                    enabled=enabled,
                    mode=mode,
                    driver=driver,
                    mac_address=mac_address
                )
            
            # Ensure we have entries for configured interfaces even if not detected
            if self.client_interface not in self.interfaces:
                self.interfaces[self.client_interface] = InterfaceStatus(
                    name=self.client_interface,
                    detected=False,
                    enabled=False,
                    mode="client"
                )
            
            if self.ap_interface not in self.interfaces:
                self.interfaces[self.ap_interface] = InterfaceStatus(
                    name=self.ap_interface,
                    detected=False,
                    enabled=False,
                    mode="ap"
                )
                
        except Exception as e:
            print(f"[NetworkingBridge] Error detecting interfaces: {e}")
    
    def _get_client_status(self) -> None:
        """Update client interface connection status using nmcli"""
        try:
            iface = self.client_interface
            
            # Check if interface exists and is managed
            if iface not in self.interfaces or not self.interfaces[iface].detected:
                self.client_status = ClientStatus(connected=False)
                return
            
            # Get connection status using nmcli
            result = subprocess.run(
                ["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"],
                capture_output=True, text=True, timeout=5
            )
            
            connected = False
            connection_name = ""
            
            for line in result.stdout.strip().split('\n'):
                parts = line.split(':')
                if len(parts) >= 3 and parts[0] == iface:
                    connected = parts[1] == "connected"
                    connection_name = parts[2] if connected else ""
                    break
            
            if not connected:
                self.client_status = ClientStatus(connected=False)
                return
            
            # Get detailed connection info
            result = subprocess.run(
                ["nmcli", "-t", "-f", "IP4.ADDRESS,IP4.GATEWAY,GENERAL.HWADDR,WIFI.SSID,WIFI.SIGNAL,WIFI.FREQ",
                 "device", "show", iface],
                capture_output=True, text=True, timeout=5
            )
            
            ssid = ""
            ip_address = ""
            cidr = 24
            router = ""
            signal_percent = 0
            frequency = ""
            
            for line in result.stdout.strip().split('\n'):
                if ':' not in line:
                    continue
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip()
                
                if key == "WIFI.SSID":
                    ssid = value
                elif key == "IP4.ADDRESS[1]":
                    # Format: 192.168.1.100/24
                    if '/' in value:
                        ip_address, cidr_str = value.split('/')
                        cidr = int(cidr_str)
                    else:
                        ip_address = value
                elif key == "IP4.GATEWAY":
                    router = value
                elif key == "WIFI.SIGNAL":
                    try:
                        signal_percent = int(value)
                    except:
                        pass
                elif key == "WIFI.FREQ":
                    frequency = value
            
            # Convert signal percent to approximate dBm
            # Rough formula: dBm ≈ (signal_percent / 2) - 100
            signal_dbm = int((signal_percent / 2) - 100) if signal_percent > 0 else -100
            
            self.client_status = ClientStatus(
                connected=True,
                ssid=ssid,
                ip_address=ip_address,
                cidr=cidr,
                router=router,
                signal_dbm=signal_dbm,
                signal_percent=signal_percent,
                frequency=frequency
            )
            
        except subprocess.TimeoutExpired:
            print("[NetworkingBridge] Timeout getting client status")
        except Exception as e:
            print(f"[NetworkingBridge] Error getting client status: {e}")
    
    def _get_ap_status(self) -> None:
        """Update access point status"""
        try:
            iface = self.ap_interface
            
            # Check if interface exists
            if iface not in self.interfaces or not self.interfaces[iface].detected:
                self.ap_status.enabled = False
                self.ap_status.clients = []
                return
            
            # Check if hostapd is running
            result = subprocess.run(
                ["systemctl", "is-active", "hostapd"],
                capture_output=True, text=True, timeout=5
            )
            
            self.ap_status.enabled = result.stdout.strip() == "active"
            
            if self.ap_status.enabled:
                # Get connected clients from DHCP leases
                self._update_ap_clients()
                
                # Get AP IP address
                result = subprocess.run(
                    ["ip", "-4", "addr", "show", iface],
                    capture_output=True, text=True, timeout=5
                )
                
                # Parse IP address from output
                match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+/\d+)', result.stdout)
                if match:
                    self.ap_status.ip_cidr = match.group(1)
            else:
                self.ap_status.clients = []
                
        except Exception as e:
            print(f"[NetworkingBridge] Error getting AP status: {e}")
    
    def _update_ap_clients(self) -> None:
        """Update list of clients connected to the access point"""
        clients = []
        
        try:
            # Read DHCP leases file
            leases_file = "/var/lib/misc/dnsmasq.leases"
            if not os.path.exists(leases_file):
                leases_file = "/var/lib/dnsmasq/dnsmasq.leases"
            
            if os.path.exists(leases_file):
                with open(leases_file, 'r') as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 4:
                            # Format: timestamp mac ip hostname client-id
                            mac = parts[1]
                            ip = parts[2]
                            hostname = parts[3] if parts[3] != "*" else ""
                            
                            # Lookup vendor from MAC
                            vendor = self.oui_lookup.lookup(mac)
                            
                            clients.append(APClient(
                                mac=mac,
                                ip=ip,
                                hostname=hostname,
                                vendor=vendor
                            ))
            
            # Also check arp table for connected devices
            result = subprocess.run(
                ["ip", "neigh", "show", "dev", self.ap_interface],
                capture_output=True, text=True, timeout=5
            )
            
            # Add any devices from ARP that aren't in DHCP leases
            existing_macs = {c.mac.lower() for c in clients}
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    ip = parts[0]
                    mac = parts[4] if len(parts) > 4 else ""
                    
                    if mac and mac.lower() not in existing_macs:
                        vendor = self.oui_lookup.lookup(mac)
                        clients.append(APClient(
                            mac=mac,
                            ip=ip,
                            hostname="",
                            vendor=vendor
                        ))
                        existing_macs.add(mac.lower())
            
        except Exception as e:
            print(f"[NetworkingBridge] Error updating AP clients: {e}")
        
        self.ap_status.clients = clients
    
    def _scan_networks(self) -> None:
        """Scan for available Wi-Fi networks"""
        self.scanning = True
        self._publish_scanning_status()
        
        try:
            iface = self.client_interface
            
            # Use nmcli to scan
            # First, trigger a rescan
            subprocess.run(
                ["nmcli", "device", "wifi", "rescan", "ifname", iface],
                capture_output=True, timeout=10
            )
            
            # Wait a moment for scan to complete
            time.sleep(2)
            
            # Get scan results
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,FREQ,SECURITY,IN-USE",
                 "device", "wifi", "list", "ifname", iface],
                capture_output=True, text=True, timeout=10
            )
            
            scan_results = []
            seen_ssids = set()
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                
                # nmcli uses : as separator, but BSSID also contains :
                # Format: SSID:BSSID:SIGNAL:FREQ:SECURITY:IN-USE
                # We need to parse carefully
                parts = line.split(':')
                
                if len(parts) < 6:
                    continue
                
                # SSID is first part
                ssid = parts[0].strip()
                
                # BSSID is parts 1-6 (MAC address)
                bssid = ':'.join(parts[1:7])
                
                # Rest of the fields
                try:
                    signal_percent = int(parts[7]) if len(parts) > 7 else 0
                except:
                    signal_percent = 0
                
                freq = parts[8] if len(parts) > 8 else ""
                security = parts[9] if len(parts) > 9 else ""
                in_use = parts[10] if len(parts) > 10 else ""
                
                # Skip empty SSIDs and duplicates
                if not ssid or ssid in seen_ssids:
                    continue
                seen_ssids.add(ssid)
                
                # Convert signal to dBm
                signal_dbm = int((signal_percent / 2) - 100) if signal_percent > 0 else -100
                
                # Simplify security string
                if "WPA3" in security:
                    security_simple = "WPA3"
                elif "WPA2" in security:
                    security_simple = "WPA2"
                elif "WPA" in security:
                    security_simple = "WPA"
                elif "WEP" in security:
                    security_simple = "WEP"
                elif security == "" or security == "--":
                    security_simple = "Open"
                else:
                    security_simple = security
                
                scan_results.append(ScanResult(
                    ssid=ssid,
                    bssid=bssid,
                    signal_dbm=signal_dbm,
                    signal_percent=signal_percent,
                    frequency=freq,
                    security=security_simple,
                    connected=(in_use == "*")
                ))
            
            # Sort by signal strength (strongest first)
            scan_results.sort(key=lambda x: x.signal_percent, reverse=True)
            
            self.scan_results = scan_results
            
        except subprocess.TimeoutExpired:
            print("[NetworkingBridge] Timeout during Wi-Fi scan")
        except Exception as e:
            print(f"[NetworkingBridge] Error scanning networks: {e}")
        
        self.scanning = False
        self._publish_scan_results()
        self._publish_scanning_status()
    
    def _connect_to_network(self, ssid: str, password: str = "") -> bool:
        """
        Connect to a Wi-Fi network.
        
        Args:
            ssid: Network SSID
            password: Network password (empty for open networks)
        
        Returns:
            True if connection initiated successfully
        """
        try:
            iface = self.client_interface
            
            print(f"[NetworkingBridge] Connecting to '{ssid}'...")
            
            # Build nmcli command
            cmd = ["nmcli", "device", "wifi", "connect", ssid]
            
            if password:
                cmd.extend(["password", password])
            
            cmd.extend(["ifname", iface])
            
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                print(f"[NetworkingBridge] Successfully connected to '{ssid}'")
                return True
            else:
                print(f"[NetworkingBridge] Failed to connect: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("[NetworkingBridge] Connection timeout")
            return False
        except Exception as e:
            print(f"[NetworkingBridge] Error connecting: {e}")
            return False
    
    def _disconnect_from_network(self) -> bool:
        """
        Disconnect from current Wi-Fi network.
        
        Returns:
            True if disconnection successful
        """
        try:
            iface = self.client_interface
            
            result = subprocess.run(
                ["nmcli", "device", "disconnect", iface],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                print(f"[NetworkingBridge] Disconnected from network")
                return True
            else:
                print(f"[NetworkingBridge] Failed to disconnect: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"[NetworkingBridge] Error disconnecting: {e}")
            return False
    
    def _enable_interface(self, iface: str, enable: bool) -> bool:
        """Enable or disable a network interface"""
        try:
            action = "up" if enable else "down"
            result = subprocess.run(
                ["sudo", "ip", "link", "set", iface, action],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except Exception as e:
            print(f"[NetworkingBridge] Error setting interface {iface} {action}: {e}")
            return False
    
    def _configure_ap(self, ssid: str = None, security: str = None, 
                      password: str = None, ip_cidr: str = None) -> bool:
        """
        Configure access point settings.
        
        Args:
            ssid: Network name
            security: Security type (none, wep, wpa2)
            password: Network password
            ip_cidr: IP address with CIDR notation
        
        Returns:
            True if configuration successful
        """
        try:
            # Update stored config
            if ssid is not None:
                self.ap_status.ssid = ssid
            if security is not None:
                self.ap_status.security = security
            if password is not None:
                self.ap_status.password = password
            if ip_cidr is not None:
                self.ap_status.ip_cidr = ip_cidr
            
            # Generate hostapd config
            hostapd_config = self._generate_hostapd_config()
            
            # Write hostapd config
            with open("/tmp/hostapd.conf", 'w') as f:
                f.write(hostapd_config)
            
            subprocess.run(
                ["sudo", "cp", "/tmp/hostapd.conf", self.hostapd_conf],
                check=True, timeout=5
            )
            
            # Generate dnsmasq config
            dnsmasq_config = self._generate_dnsmasq_config()
            
            # Write dnsmasq config
            with open("/tmp/protosuit-ap.conf", 'w') as f:
                f.write(dnsmasq_config)
            
            subprocess.run(
                ["sudo", "cp", "/tmp/protosuit-ap.conf", self.dnsmasq_conf],
                check=True, timeout=5
            )
            
            print("[NetworkingBridge] AP configuration updated")
            self._publish_retained_state()  # Persist to MQTT
            return True
            
        except Exception as e:
            print(f"[NetworkingBridge] Error configuring AP: {e}")
            return False
    
    def _generate_hostapd_config(self) -> str:
        """Generate hostapd configuration file content"""
        config = f"""# Protosuit AP Configuration
# Generated by networkingbridge

interface={self.ap_interface}
driver=nl80211
ssid={self.ap_status.ssid}
hw_mode=g
channel={self.ap_status.channel}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
"""
        
        if self.ap_status.security == "wpa2":
            config += f"""wpa=2
wpa_passphrase={self.ap_status.password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
        elif self.ap_status.security == "wep":
            # WEP keys must be 5 or 13 ASCII chars (quoted)
            config += f"""wep_default_key=0
wep_key0="{self.ap_status.password}"
"""
        # For "none", no additional security config needed
        
        return config
    
    def _generate_dnsmasq_config(self) -> str:
        """Generate dnsmasq configuration file content"""
        # Parse IP and network from CIDR
        try:
            network = ipaddress.ip_network(self.ap_status.ip_cidr, strict=False)
            ip = self.ap_status.ip_cidr.split('/')[0]
            
            # Calculate DHCP range (skip first 10 IPs for static assignments)
            hosts = list(network.hosts())
            if len(hosts) > 20:
                dhcp_start = str(hosts[10])
                dhcp_end = str(hosts[-10])
            else:
                dhcp_start = str(hosts[1])
                dhcp_end = str(hosts[-1])
            
        except Exception:
            ip = "192.168.50.1"
            dhcp_start = "192.168.50.10"
            dhcp_end = "192.168.50.100"
        
        config = f"""# Protosuit AP DHCP Configuration
# Generated by networkingbridge

interface={self.ap_interface}
dhcp-range={dhcp_start},{dhcp_end},255.255.255.0,24h
dhcp-option=option:router,{ip}
dhcp-option=option:dns-server,{ip}
"""
        
        return config
    
    def _enable_ap(self, enable: bool) -> bool:
        """Enable or disable the access point"""
        try:
            if enable:
                # Configure AP first (writes hostapd.conf and dnsmasq.conf)
                self._configure_ap()
                
                # Start hostapd first - it will bring up the interface in AP mode
                subprocess.run(
                    ["sudo", "systemctl", "start", "hostapd"],
                    check=True, timeout=15
                )
                
                # Wait for interface to come up
                time.sleep(2)
                
                # Set IP address on interface (after hostapd brings it up)
                ip_cidr = self.ap_status.ip_cidr or "192.168.50.1/24"
                subprocess.run(
                    ["sudo", "ip", "addr", "flush", "dev", self.ap_interface],
                    timeout=5
                )
                subprocess.run(
                    ["sudo", "ip", "addr", "add", ip_cidr, "dev", self.ap_interface],
                    check=True, timeout=5
                )
                
                # Start dnsmasq for DHCP
                subprocess.run(
                    ["sudo", "systemctl", "restart", "dnsmasq"],
                    check=True, timeout=10
                )
                
                print("[NetworkingBridge] Access point enabled")
                
            else:
                # Stop services
                subprocess.run(
                    ["sudo", "systemctl", "stop", "hostapd"],
                    timeout=10
                )
                
                # Bring down interface
                subprocess.run(
                    ["sudo", "ip", "link", "set", self.ap_interface, "down"],
                    timeout=5
                )
                
                print("[NetworkingBridge] Access point disabled")
            
            self.ap_status.enabled = enable
            self._publish_retained_state()  # Persist to MQTT
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"[NetworkingBridge] Error {'enabling' if enable else 'disabling'} AP: {e}")
            return False
        except Exception as e:
            print(f"[NetworkingBridge] Error with AP: {e}")
            return False
    
    def _enable_routing(self, enable: bool) -> bool:
        """Enable or disable NAT routing from AP to client interface"""
        try:
            if enable:
                # Enable IP forwarding
                subprocess.run(
                    ["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"],
                    check=True, timeout=5
                )
                
                # Add iptables NAT rule
                subprocess.run(
                    ["sudo", "iptables", "-t", "nat", "-A", "POSTROUTING",
                     "-o", self.client_interface, "-j", "MASQUERADE"],
                    check=True, timeout=5
                )
                
                # Allow forwarding from AP to client (outbound internet)
                subprocess.run(
                    ["sudo", "iptables", "-A", "FORWARD",
                     "-i", self.ap_interface, "-o", self.client_interface,
                     "-j", "ACCEPT"],
                    check=True, timeout=5
                )
                # Allow return traffic from client to AP
                subprocess.run(
                    ["sudo", "iptables", "-A", "FORWARD",
                     "-i", self.client_interface, "-o", self.ap_interface,
                     "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
                    check=True, timeout=5
                )
                
                print("[NetworkingBridge] Routing enabled")
                
            else:
                # Remove iptables rules (best effort)
                subprocess.run(
                    ["sudo", "iptables", "-t", "nat", "-D", "POSTROUTING",
                     "-o", self.client_interface, "-j", "MASQUERADE"],
                    timeout=5
                )
                subprocess.run(
                    ["sudo", "iptables", "-D", "FORWARD",
                     "-i", self.ap_interface, "-o", self.client_interface,
                     "-j", "ACCEPT"],
                    timeout=5
                )
                subprocess.run(
                    ["sudo", "iptables", "-D", "FORWARD",
                     "-i", self.client_interface, "-o", self.ap_interface,
                     "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
                    timeout=5
                )
                
                # Disable IP forwarding
                subprocess.run(
                    ["sudo", "sysctl", "-w", "net.ipv4.ip_forward=0"],
                    timeout=5
                )
                
                print("[NetworkingBridge] Routing disabled")
            
            self.ap_status.routing_enabled = enable
            self._publish_retained_state()  # Persist to MQTT
            return True
            
        except Exception as e:
            print(f"[NetworkingBridge] Error configuring routing: {e}")
            return False
    
    def _enable_captive_portal(self, enable: bool) -> bool:
        """Enable or disable captive portal (redirect HTTP to web UI)"""
        try:
            web_port = 5000  # Default Flask port
            
            if enable:
                # Redirect HTTP traffic to web UI
                subprocess.run(
                    ["sudo", "iptables", "-t", "nat", "-A", "PREROUTING",
                     "-i", self.ap_interface, "-p", "tcp", "--dport", "80",
                     "-j", "REDIRECT", "--to-port", str(web_port)],
                    check=True, timeout=5
                )
                print("[NetworkingBridge] Captive portal enabled")
                
            else:
                # Remove redirect rule
                subprocess.run(
                    ["sudo", "iptables", "-t", "nat", "-D", "PREROUTING",
                     "-i", self.ap_interface, "-p", "tcp", "--dport", "80",
                     "-j", "REDIRECT", "--to-port", str(web_port)],
                    timeout=5
                )
                print("[NetworkingBridge] Captive portal disabled")
            
            self.ap_status.captive_portal_enabled = enable
            self._publish_retained_state()  # Persist to MQTT
            return True
            
        except Exception as e:
            print(f"[NetworkingBridge] Error configuring captive portal: {e}")
            return False
    
    def _generate_qr_code(self) -> Optional[str]:
        """
        Generate QR code for AP Wi-Fi credentials.
        
        Returns:
            Base64 encoded PNG image, or None if generation fails
        """
        if not QRCODE_AVAILABLE:
            return None
        
        try:
            # Wi-Fi QR code format: WIFI:T:<security>;S:<ssid>;P:<password>;;
            security_type = "WPA" if self.ap_status.security in ("wpa", "wpa2") else "nopass"
            
            if security_type == "nopass":
                wifi_string = f"WIFI:T:nopass;S:{self.ap_status.ssid};;"
            else:
                wifi_string = f"WIFI:T:WPA;S:{self.ap_status.ssid};P:{self.ap_status.password};;"
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(wifi_string)
            qr.make(fit=True)
            
            # Create image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            base64_img = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return f"data:image/png;base64,{base64_img}"
            
        except Exception as e:
            print(f"[NetworkingBridge] Error generating QR code: {e}")
            return None
    
    # MQTT handling
    
    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT connection"""
        print("[NetworkingBridge] Connected to MQTT broker")
        
        # Subscribe to command topics
        topics = [
            "protogen/fins/networkingbridge/scan/start",
            "protogen/fins/networkingbridge/client/connect",
            "protogen/fins/networkingbridge/client/disconnect",
            "protogen/fins/networkingbridge/client/enable",
            "protogen/fins/networkingbridge/ap/config",
            "protogen/fins/networkingbridge/ap/enable",
            "protogen/fins/networkingbridge/routing/enable",
            "protogen/fins/networkingbridge/captive/enable",
            "protogen/fins/networkingbridge/qrcode/generate",
            "protogen/fins/networkingbridge/state",  # Retained state for restoration
        ]
        
        for topic in topics:
            client.subscribe(topic)
            print(f"[NetworkingBridge] Subscribed to {topic}")
        
        # Publish initial status (delay slightly to allow retained state to arrive first)
        threading.Timer(0.5, self._publish_all_status).start()
    
    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        topic = msg.topic
        
        try:
            payload = msg.payload.decode('utf-8')
            data = json.loads(payload) if payload else {}
        except:
            data = {}
        
        print(f"[NetworkingBridge] Received: {topic}")
        
        if topic == "protogen/fins/networkingbridge/scan/start":
            # Start Wi-Fi scan in background thread
            if not self.scanning and self.scan_thread is None:
                self.scan_thread = threading.Thread(target=self._scan_networks, daemon=True)
                self.scan_thread.start()
        
        elif topic == "protogen/fins/networkingbridge/client/connect":
            ssid = data.get("ssid", "")
            password = data.get("password", "")
            if ssid:
                threading.Thread(
                    target=self._handle_connect,
                    args=(ssid, password),
                    daemon=True
                ).start()
        
        elif topic == "protogen/fins/networkingbridge/client/disconnect":
            self._disconnect_from_network()
            self._get_client_status()
            self._publish_client_status()
        
        elif topic == "protogen/fins/networkingbridge/client/enable":
            enable = data.get("enable", True)
            self._enable_interface(self.client_interface, enable)
            self._detect_interfaces()
            self._publish_interface_status()
        
        elif topic == "protogen/fins/networkingbridge/ap/config":
            self._configure_ap(
                ssid=data.get("ssid"),
                security=data.get("security"),
                password=data.get("password"),
                ip_cidr=data.get("ip_cidr")
            )
            if self.ap_status.enabled:
                # Restart AP to apply changes
                self._enable_ap(False)
                self._enable_ap(True)
            self._publish_ap_status()
        
        elif topic == "protogen/fins/networkingbridge/ap/enable":
            enable = data.get("enable", True)
            self._enable_ap(enable)
            self._get_ap_status()
            self._publish_ap_status()
        
        elif topic == "protogen/fins/networkingbridge/routing/enable":
            enable = data.get("enable", True)
            self._enable_routing(enable)
            self._publish_ap_status()
        
        elif topic == "protogen/fins/networkingbridge/captive/enable":
            enable = data.get("enable", True)
            self._enable_captive_portal(enable)
            self._publish_ap_status()
        
        elif topic == "protogen/fins/networkingbridge/qrcode/generate":
            qr_data = self._generate_qr_code()
            if qr_data:
                self.mqtt_client.publish(
                    "protogen/fins/networkingbridge/status/qrcode",
                    json.dumps({"qrcode": qr_data})
                )
        
        elif topic == "protogen/fins/networkingbridge/state":
            # Retained state message - restore AP if it was enabled
            self._restore_from_retained_state(data)
    
    def _handle_connect(self, ssid: str, password: str):
        """Handle connection attempt in background"""
        success = self._connect_to_network(ssid, password)
        time.sleep(2)  # Wait for connection to establish
        self._get_client_status()
        self._publish_client_status()
        
        # Publish connection result
        self.mqtt_client.publish(
            "protogen/fins/networkingbridge/status/connection",
            json.dumps({"success": success, "ssid": ssid})
        )
    
    def _publish_all_status(self):
        """Publish all status updates"""
        self._detect_interfaces()
        self._get_client_status()
        self._get_ap_status()
        
        self._publish_interface_status()
        self._publish_client_status()
        self._publish_ap_status()
    
    def _publish_interface_status(self):
        """Publish interface detection status"""
        if not self.mqtt_client:
            return
        
        status = {
            name: asdict(iface)
            for name, iface in self.interfaces.items()
        }
        
        self.mqtt_client.publish(
            "protogen/fins/networkingbridge/status/interfaces",
            json.dumps(status)
        )
    
    def _publish_client_status(self):
        """Publish client mode status"""
        if not self.mqtt_client:
            return
        
        self.mqtt_client.publish(
            "protogen/fins/networkingbridge/status/client",
            json.dumps(asdict(self.client_status))
        )
    
    def _publish_ap_status(self):
        """Publish access point status"""
        if not self.mqtt_client:
            return
        
        # Convert APClient objects to dicts
        status = asdict(self.ap_status)
        
        self.mqtt_client.publish(
            "protogen/fins/networkingbridge/status/ap",
            json.dumps(status)
        )
    
    def _publish_scan_results(self):
        """Publish Wi-Fi scan results"""
        if not self.mqtt_client:
            return
        
        results = [asdict(r) for r in self.scan_results]
        
        self.mqtt_client.publish(
            "protogen/fins/networkingbridge/status/scan",
            json.dumps(results)
        )
    
    def _publish_scanning_status(self):
        """Publish scanning status"""
        if not self.mqtt_client:
            return
        
        self.mqtt_client.publish(
            "protogen/fins/networkingbridge/status/scanning",
            json.dumps(self.scanning)
        )
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self.running:
            try:
                # Update status periodically
                self._detect_interfaces()
                self._get_client_status()
                self._get_ap_status()
                
                # Publish updates
                self._publish_interface_status()
                self._publish_client_status()
                self._publish_ap_status()
                
            except Exception as e:
                print(f"[NetworkingBridge] Monitor error: {e}")
            
            # Wait before next update
            time.sleep(5)
    
    def run(self):
        """Run the networking bridge service"""
        print("[NetworkingBridge] Starting...")
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Connect to MQTT
        self.mqtt_client = create_mqtt_client(self.config_loader)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        
        # Start MQTT loop in background
        self.mqtt_client.loop_start()
        
        # Start monitoring thread
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        print("[NetworkingBridge] Running. Press Ctrl+C to stop.")
        
        # Main loop
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
        self.stop()
    
    def stop(self):
        """Stop the service"""
        print("[NetworkingBridge] Stopping...")
        self.running = False
        
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        print("[NetworkingBridge] Stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n[NetworkingBridge] Received signal {signum}")
        self.running = False


def main():
    """Main entry point"""
    print("=" * 60)
    print("Protosuit Engine Networking Bridge")
    print("=" * 60)
    
    bridge = NetworkingBridge()
    bridge.run()


if __name__ == "__main__":
    main()

"""
NetworkManager D-Bus Wrapper
Replaces nmcli/ip subprocess calls with direct D-Bus API via pydbus.
"""

import socket
import struct
import time
import logging
from typing import Optional, List, Dict

from pydbus import SystemBus

logger = logging.getLogger(__name__)

NM_SERVICE = "org.freedesktop.NetworkManager"

# Device types
NM_DEVICE_TYPE_WIFI = 2

# Device states
NM_DEVICE_STATE_ACTIVATED = 100

# AP security flag bits
_SEC_PAIR_CCMP = 1 << 3
_SEC_KEY_MGMT_PSK = 1 << 8
_SEC_KEY_MGMT_802_1X = 1 << 9

# ActiveConnection states
_AC_STATE_ACTIVATED = 2
_AC_STATE_DEACTIVATED = 4


def _ip4_int_to_str(ip_int: int) -> str:
    """Convert NM's little-endian uint32 IPv4 to dotted string."""
    return socket.inet_ntoa(struct.pack("<I", ip_int))


class NetworkManagerDbus:
    """NetworkManager D-Bus wrapper for Wi-Fi operations."""

    def __init__(self):
        self._bus = SystemBus()
        self._nm = None

    @property
    def nm(self):
        """Lazy-init NM manager proxy."""
        if self._nm is None:
            self._nm = self._bus.get(NM_SERVICE, "/org/freedesktop/NetworkManager")
        return self._nm

    # ---- Device discovery ----

    def get_wifi_device(self, iface_name: str) -> Optional[str]:
        """Find Wi-Fi device object path by interface name. Returns None if not found."""
        try:
            for dev_path in self.nm.GetDevices():
                dev = self._bus.get(NM_SERVICE, dev_path)
                if dev.Interface == iface_name and dev.DeviceType == NM_DEVICE_TYPE_WIFI:
                    return dev_path
        except Exception as e:
            logger.error(f"get_wifi_device({iface_name}): {e}")
        return None

    def is_device_present(self, iface_name: str) -> bool:
        """Check if a network device with the given interface name exists."""
        try:
            for dev_path in self.nm.GetDevices():
                dev = self._bus.get(NM_SERVICE, dev_path)
                if dev.Interface == iface_name:
                    return True
        except Exception as e:
            logger.error(f"is_device_present({iface_name}): {e}")
        return False

    def get_device_state(self, device_path: str) -> int:
        """Get device state (NM_DEVICE_STATE_* constant)."""
        try:
            dev = self._bus.get(NM_SERVICE, device_path)
            return dev.State
        except Exception as e:
            logger.error(f"get_device_state: {e}")
            return 0

    # ---- Wi-Fi scanning ----

    def scan_networks(self, device_path: str, wait: float = 3.0) -> List[Dict]:
        """
        Trigger a Wi-Fi scan and return discovered networks.

        Returns list of dicts with keys: ssid, security, signal_percent,
        signal_dbm, frequency, connected.
        """
        networks = []
        seen_ssids = set()

        try:
            dev = self._bus.get(NM_SERVICE, device_path)

            # Trigger scan (may raise if already scanning — that's fine)
            try:
                dev.RequestScan({})
            except Exception:
                pass  # scan already in progress

            time.sleep(wait)

            # Check which AP is currently active
            active_ap_path = None
            try:
                active_ap_path = dev.ActiveAccessPoint
                if active_ap_path == "/":
                    active_ap_path = None
            except Exception:
                pass

            for ap_path in dev.GetAccessPoints():
                try:
                    ap = self._bus.get(NM_SERVICE, ap_path)
                    ssid_bytes = bytes(ap.Ssid)
                    if not ssid_bytes:
                        continue
                    ssid = ssid_bytes.decode("utf-8", errors="ignore")
                    if not ssid or ssid in seen_ssids:
                        continue
                    seen_ssids.add(ssid)

                    strength = ap.Strength  # 0-100
                    freq = ap.Frequency  # MHz
                    security = self._decode_security(
                        ap.Flags, ap.WpaFlags, ap.RsnFlags
                    )

                    networks.append({
                        "ssid": ssid,
                        "security": security,
                        "signal_percent": strength,
                        "signal_dbm": -100 + strength,
                        "frequency": str(freq),
                        "connected": ap_path == active_ap_path,
                    })
                except Exception as e:
                    logger.debug(f"Error reading AP {ap_path}: {e}")

        except Exception as e:
            logger.error(f"scan_networks: {e}")

        return networks

    @staticmethod
    def _decode_security(flags: int, wpa_flags: int, rsn_flags: int) -> str:
        """Decode AP security type from NM flag bitmasks."""
        if rsn_flags & _SEC_KEY_MGMT_802_1X:
            return "WPA2-Enterprise"
        if rsn_flags & _SEC_PAIR_CCMP:
            return "WPA2"
        if wpa_flags & _SEC_KEY_MGMT_802_1X:
            return "WPA-Enterprise"
        if wpa_flags & _SEC_PAIR_CCMP or wpa_flags & _SEC_KEY_MGMT_PSK:
            return "WPA"
        if flags & 0x1:  # NM_802_11_AP_FLAGS_PRIVACY (WEP)
            return "WEP"
        return "Open"

    # ---- Connection management ----

    def connect(
        self, device_path: str, ssid: str, password: str = "", timeout: int = 30
    ) -> bool:
        """
        Connect to a Wi-Fi network. Creates a new connection profile and activates it.
        Returns True on success.
        """
        try:
            settings = {
                "connection": {
                    "id": ssid,
                    "type": "802-11-wireless",
                    "autoconnect": True,
                },
                "802-11-wireless": {
                    "ssid": ssid.encode("utf-8"),
                    "mode": "infrastructure",
                },
                "ipv4": {"method": "auto"},
                "ipv6": {"method": "auto"},
            }

            if password:
                settings["802-11-wireless-security"] = {
                    "key-mgmt": "wpa-psk",
                    "psk": password,
                }

            _conn_path, active_path = self.nm.AddAndActivateConnection(
                settings, device_path, "/"
            )

            # Wait for activation
            for _ in range(timeout):
                try:
                    active = self._bus.get(NM_SERVICE, active_path)
                    state = active.State
                    if state == _AC_STATE_ACTIVATED:
                        return True
                    if state == _AC_STATE_DEACTIVATED:
                        return False
                except Exception:
                    pass
                time.sleep(1)

            logger.warning(f"connect({ssid}): timed out after {timeout}s")
            return False

        except Exception as e:
            logger.error(f"connect({ssid}): {e}")
            return False

    def disconnect(self, device_path: str) -> bool:
        """Disconnect device from current network."""
        try:
            dev = self._bus.get(NM_SERVICE, device_path)
            dev.Disconnect()
            return True
        except Exception as e:
            logger.error(f"disconnect: {e}")
            return False

    # ---- Status queries ----

    def get_connection_details(self, device_path: str) -> Optional[Dict]:
        """
        Get details of the current connection on a device.

        Returns dict with keys: connected, ssid, ip_address, cidr, router,
        signal_percent, signal_dbm. Returns None on error.
        """
        try:
            dev = self._bus.get(NM_SERVICE, device_path)

            if dev.State != NM_DEVICE_STATE_ACTIVATED:
                return {
                    "connected": False,
                    "ssid": "",
                    "ip_address": "",
                    "cidr": 24,
                    "router": "",
                    "signal_percent": 0,
                    "signal_dbm": -100,
                }

            result = {
                "connected": True,
                "ssid": "",
                "ip_address": "",
                "cidr": 24,
                "router": "",
                "signal_percent": 0,
                "signal_dbm": -100,
            }

            # SSID from active access point
            try:
                ap_path = dev.ActiveAccessPoint
                if ap_path and ap_path != "/":
                    ap = self._bus.get(NM_SERVICE, ap_path)
                    ssid_bytes = bytes(ap.Ssid)
                    result["ssid"] = ssid_bytes.decode("utf-8", errors="ignore")
                    result["signal_percent"] = ap.Strength
                    result["signal_dbm"] = -100 + ap.Strength
            except Exception:
                pass

            # IP address and gateway from Ip4Config
            ip4_path = dev.Ip4Config
            if ip4_path and ip4_path != "/":
                try:
                    ip4 = self._bus.get(NM_SERVICE, ip4_path)

                    # AddressData is a list of dicts with 'address' and 'prefix'
                    if ip4.AddressData:
                        addr = ip4.AddressData[0]
                        result["ip_address"] = str(addr.get("address", ""))
                        result["cidr"] = int(addr.get("prefix", 24))

                    # Gateway
                    gw = ip4.Gateway
                    if gw:
                        result["router"] = str(gw)
                except Exception:
                    pass

            return result

        except Exception as e:
            logger.error(f"get_connection_details: {e}")
            return None

    # ---- Device management ----

    def set_managed(self, device_path: str, managed: bool) -> bool:
        """Set device as managed/unmanaged by NetworkManager."""
        try:
            dev = self._bus.get(NM_SERVICE, device_path)
            dev.Managed = managed
            return True
        except Exception as e:
            logger.error(f"set_managed({managed}): {e}")
            return False


def get_ap_clients(ap_interface: str) -> List[Dict]:
    """
    Read connected AP clients from /proc/net/arp.
    Returns list of dicts with 'ip' and 'mac' keys.
    """
    clients = []
    try:
        with open("/proc/net/arp", "r") as f:
            for line in f.readlines()[1:]:  # skip header
                parts = line.split()
                if len(parts) >= 6 and parts[5] == ap_interface and parts[2] != "0x0":
                    clients.append({"ip": parts[0], "mac": parts[3]})
    except Exception as e:
        logger.error(f"get_ap_clients: {e}")
    return clients

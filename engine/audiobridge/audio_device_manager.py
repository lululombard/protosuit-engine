"""
Audio Device Manager - Manages audio output device selection
Handles PulseAudio sink management via pulsectl (native protocol)
"""

import pulsectl
from typing import List, Dict, Optional


class AudioDeviceManager:
    """Manager for audio output devices using pulsectl"""

    def __init__(self):
        """Initialize audio device manager"""
        self.cached_devices = []

    def _pulse(self) -> pulsectl.Pulse:
        """Create a fresh PulseAudio connection (short-lived to avoid stale state)."""
        return pulsectl.Pulse("audiobridge")

    def list_devices(self) -> List[Dict]:
        """
        List available audio output devices.

        Returns:
            List of devices with format:
            [{"name": "sink_name", "description": "Device Description", "type": "bluetooth|hdmi|analog|usb"}]
        """
        try:
            with self._pulse() as pulse:
                sinks = pulse.sink_list()

            devices = []
            for sink in sinks:
                devices.append({
                    "name": sink.name,
                    "description": sink.description or sink.name,
                    "type": self._detect_device_type(sink.name),
                })

            self.cached_devices = devices
            print(f"[AudioDeviceManager] Found {len(devices)} audio devices:")
            for d in devices:
                print(f"[AudioDeviceManager]   - {d['name']} ({d['type']}) - {d.get('description', 'N/A')}")
            return devices

        except Exception as e:
            print(f"[AudioDeviceManager] Error listing devices: {e}")
            return []

    def _detect_device_type(self, sink_name: str) -> str:
        """Detect the type of audio device based on sink name."""
        name_lower = sink_name.lower()

        if "bluez" in name_lower or "bluetooth" in name_lower:
            return "bluetooth"
        elif "hdmi" in name_lower:
            return "hdmi"
        elif "usb" in name_lower:
            return "usb"
        else:
            return "analog"

    def get_current_device(self) -> Optional[str]:
        """Get current default audio output device sink name."""
        try:
            with self._pulse() as pulse:
                info = pulse.server_info()
                return info.default_sink_name
        except Exception as e:
            print(f"[AudioDeviceManager] Error getting current device: {e}")
            return None

    def set_default_device(self, sink_name: str) -> bool:
        """Set default audio output device and move existing streams."""
        try:
            print(f"[AudioDeviceManager] Setting default device to: {sink_name}")
            with self._pulse() as pulse:
                pulse.sink_default_set(sink_name)

                # Move all existing streams to the new sink
                sink = None
                for s in pulse.sink_list():
                    if s.name == sink_name:
                        sink = s
                        break

                if sink:
                    for si in pulse.sink_input_list():
                        try:
                            pulse.sink_input_move(si.index, sink.index)
                        except pulsectl.PulseOperationFailed:
                            pass
                    print(f"[AudioDeviceManager] Moved existing streams to {sink_name}")

            print(f"[AudioDeviceManager] Successfully set default device to {sink_name}")
            return True

        except Exception as e:
            print(f"[AudioDeviceManager] Error setting device: {e}")
            return False

    def is_hdmi_device(self, sink_name: str) -> bool:
        """Check if a device is an HDMI output."""
        return "hdmi" in sink_name.lower()

    def is_bluetooth_device(self, sink_name: str) -> bool:
        """Check if a device is a Bluetooth output."""
        name_lower = sink_name.lower()
        return "bluez" in name_lower or "bluetooth" in name_lower

    def get_non_hdmi_fallback(self, exclude_mac: str = None) -> Optional[str]:
        """Find first non-HDMI device for fallback."""
        devices = self.list_devices()
        exclude_pattern = exclude_mac.replace(":", "_").upper() if exclude_mac else None

        for device in devices:
            if self.is_hdmi_device(device["name"]):
                continue
            if exclude_pattern and exclude_pattern in device["name"].upper():
                continue
            print(f"[AudioDeviceManager] Found non-HDMI fallback: {device['name']} ({device.get('description', '')})")
            return device["name"]

        print("[AudioDeviceManager] No non-HDMI fallback device found")
        return None

    def find_bluetooth_sink_by_mac(self, mac: str) -> Optional[str]:
        """Find Bluetooth sink name by MAC address."""
        devices = self.list_devices()
        mac_clean = mac.replace(":", "_").lower()

        for device in devices:
            if self.is_bluetooth_device(device["name"]):
                if mac_clean in device["name"].lower():
                    print(f"[AudioDeviceManager] Found BT sink for {mac}: {device['name']}")
                    return device["name"]

        print(f"[AudioDeviceManager] No BT sink found for {mac}")
        return None

    def get_device_info(self, sink_name: str) -> Optional[Dict]:
        """Get detailed information about a device."""
        devices = self.list_devices()
        for device in devices:
            if device["name"] == sink_name:
                return device
        return None

    def get_bluetooth_card_profile(self, mac: str) -> Optional[str]:
        """Get the current Bluetooth profile for a device."""
        try:
            mac_clean = mac.replace(":", "_").lower()
            with self._pulse() as pulse:
                for card in pulse.card_list():
                    if "bluez_card" in card.name.lower() and mac_clean in card.name.lower():
                        profile = card.profile_active
                        if profile:
                            print(f"[AudioDeviceManager] BT device {mac} profile: {profile.name}")
                            return profile.name
            return None
        except Exception as e:
            print(f"[AudioDeviceManager] Error getting BT profile: {e}")
            return None

    def set_bluetooth_profile_a2dp(self, mac: str) -> bool:
        """Set Bluetooth device to A2DP (high-quality audio) profile."""
        try:
            mac_clean = mac.replace(":", "_").lower()
            with self._pulse() as pulse:
                for card in pulse.card_list():
                    if "bluez_card" in card.name.lower() and mac_clean in card.name.lower():
                        # Find A2DP profile
                        for profile in card.profile_list:
                            if "a2dp" in profile.name.lower() and profile.available != 0:
                                print(f"[AudioDeviceManager] Setting {card.name} to {profile.name}...")
                                pulse.card_profile_set(card, profile)
                                print(f"[AudioDeviceManager] Set {mac} to A2DP (high-quality audio)")
                                return True
                        print(f"[AudioDeviceManager] No available A2DP profile found for {mac}")
                        return False

            print(f"[AudioDeviceManager] Could not find BT card for {mac}")
            return False

        except Exception as e:
            print(f"[AudioDeviceManager] Error setting BT profile: {e}")
            return False

    def get_current_volume(self) -> Optional[int]:
        """Get current volume from PulseAudio.

        Returns:
            Volume percentage (0-100) or None if unable to read.
        """
        try:
            with self._pulse() as pulse:
                info = pulse.server_info()
                for sink in pulse.sink_list():
                    if sink.name == info.default_sink_name:
                        return round(pulse.volume_get_all_chans(sink) * 100)
            return None
        except Exception:
            return None

    def set_volume(self, percentage: int) -> bool:
        """Set volume on the default sink.

        Args:
            percentage: Volume level 0-100

        Returns:
            True if successful.
        """
        try:
            with self._pulse() as pulse:
                info = pulse.server_info()
                for sink in pulse.sink_list():
                    if sink.name == info.default_sink_name:
                        pulse.volume_set_all_chans(sink, percentage / 100.0)
                        return True
            return False
        except Exception:
            return False

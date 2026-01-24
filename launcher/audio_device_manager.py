"""
Audio Device Manager - Manages audio output device selection
Handles PipeWire/PulseAudio sink management via pactl
"""

import subprocess
import re
from typing import List, Dict, Optional


class AudioDeviceManager:
    """Manager for audio output devices using pactl/PipeWire"""

    def __init__(self):
        """Initialize audio device manager"""
        self.cached_devices = []

    def list_devices(self) -> List[Dict]:
        """
        List available audio output devices via pactl
        
        Returns:
            List of devices with format:
            [{"name": "sink_name", "description": "Device Description", "type": "bluetooth|hdmi|analog|usb"}]
        """
        try:
            # Run pactl to list sinks
            result = subprocess.run(
                ["pactl", "list", "sinks"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                print(f"[AudioDeviceManager] Failed to list devices: {result.stderr}")
                return []

            devices = []
            current_sink = {}
            
            for line in result.stdout.splitlines():
                line = line.strip()
                
                # Start of a new sink
                if line.startswith("Sink #"):
                    if current_sink and "name" in current_sink:
                        devices.append(current_sink)
                    current_sink = {}
                
                # Parse sink name
                elif line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                    current_sink["name"] = name
                    current_sink["type"] = self._detect_device_type(name)
                
                # Parse sink description
                elif line.startswith("Description:"):
                    desc = line.split(":", 1)[1].strip()
                    current_sink["description"] = desc
            
            # Add last sink
            if current_sink and "name" in current_sink:
                devices.append(current_sink)

            self.cached_devices = devices
            print(f"[AudioDeviceManager] Found {len(devices)} audio devices:")
            for d in devices:
                print(f"[AudioDeviceManager]   - {d['name']} ({d['type']}) - {d.get('description', 'N/A')}")
            return devices

        except Exception as e:
            print(f"[AudioDeviceManager] Error listing devices: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _detect_device_type(self, sink_name: str) -> str:
        """
        Detect the type of audio device based on sink name
        
        Args:
            sink_name: PulseAudio/PipeWire sink name
            
        Returns:
            Device type: "bluetooth", "hdmi", "usb", or "analog"
        """
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
        """
        Get current default audio output device
        
        Returns:
            Sink name of current default device, or None if not found
        """
        try:
            result = subprocess.run(
                ["pactl", "get-default-sink"],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                sink_name = result.stdout.strip()
                print(f"[AudioDeviceManager] Current device: {sink_name}")
                return sink_name
            else:
                print(f"[AudioDeviceManager] Failed to get current device: {result.stderr}")
                return None

        except Exception as e:
            print(f"[AudioDeviceManager] Error getting current device: {e}")
            return None

    def set_default_device(self, sink_name: str) -> bool:
        """
        Set default audio output device
        
        Args:
            sink_name: PulseAudio/PipeWire sink name to set as default
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"[AudioDeviceManager] Setting default device to: {sink_name}")
            
            result = subprocess.run(
                ["pactl", "set-default-sink", sink_name],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                print(f"[AudioDeviceManager] ✓ Successfully set default device to {sink_name}")
                
                # Move all existing streams to new sink
                self._move_streams_to_sink(sink_name)
                
                return True
            else:
                print(f"[AudioDeviceManager] Failed to set device: {result.stderr}")
                return False

        except Exception as e:
            print(f"[AudioDeviceManager] Error setting device: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _move_streams_to_sink(self, sink_name: str):
        """
        Move all existing audio streams to the specified sink
        
        Args:
            sink_name: Target sink name
        """
        try:
            # Get list of sink inputs (active audio streams)
            result = subprocess.run(
                ["pactl", "list", "short", "sink-inputs"],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.splitlines():
                    # Format: INDEX	SINK	...
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        stream_index = parts[0]
                        # Move this stream to the new sink
                        subprocess.run(
                            ["pactl", "move-sink-input", stream_index, sink_name],
                            timeout=2,
                            check=False
                        )
                print(f"[AudioDeviceManager] Moved existing streams to {sink_name}")

        except Exception as e:
            print(f"[AudioDeviceManager] Error moving streams: {e}")

    def is_hdmi_device(self, sink_name: str) -> bool:
        """
        Check if a device is an HDMI output
        
        Args:
            sink_name: Sink name to check
            
        Returns:
            True if device is HDMI, False otherwise
        """
        return "hdmi" in sink_name.lower()

    def is_bluetooth_device(self, sink_name: str) -> bool:
        """
        Check if a device is a Bluetooth output
        
        Args:
            sink_name: Sink name to check
            
        Returns:
            True if device is Bluetooth, False otherwise
        """
        name_lower = sink_name.lower()
        return "bluez" in name_lower or "bluetooth" in name_lower

    def get_non_hdmi_fallback(self) -> Optional[str]:
        """
        Find first non-HDMI device for fallback
        
        Returns:
            Sink name of first non-HDMI device, or None if not found
        """
        devices = self.list_devices()
        
        for device in devices:
            if not self.is_hdmi_device(device["name"]):
                print(f"[AudioDeviceManager] Found non-HDMI fallback: {device['name']} ({device['description']})")
                return device["name"]
        
        print("[AudioDeviceManager] No non-HDMI fallback device found")
        return None

    def find_bluetooth_sink_by_mac(self, mac: str) -> Optional[str]:
        """
        Find Bluetooth sink name by MAC address
        
        Args:
            mac: Bluetooth MAC address (e.g., "AA:BB:CC:DD:EE:FF")
            
        Returns:
            Sink name if found, None otherwise
        """
        devices = self.list_devices()
        
        # Clean MAC address for matching (remove colons, convert to lowercase)
        mac_clean = mac.replace(":", "_").lower()
        
        for device in devices:
            if self.is_bluetooth_device(device["name"]):
                # Check if MAC is in sink name
                if mac_clean in device["name"].lower():
                    print(f"[AudioDeviceManager] Found BT sink for {mac}: {device['name']}")
                    return device["name"]
        
        print(f"[AudioDeviceManager] No BT sink found for {mac}")
        return None

    def get_device_info(self, sink_name: str) -> Optional[Dict]:
        """
        Get detailed information about a device
        
        Args:
            sink_name: Sink name
            
        Returns:
            Device info dict or None if not found
        """
        devices = self.list_devices()
        
        for device in devices:
            if device["name"] == sink_name:
                return device
        
        return None

    def get_bluetooth_card_profile(self, mac: str) -> Optional[str]:
        """
        Get the current Bluetooth profile for a device
        
        Args:
            mac: Bluetooth MAC address
            
        Returns:
            Current profile name (e.g., "a2dp_sink", "headset_head_unit") or None
        """
        try:
            result = subprocess.run(
                ["pactl", "list", "cards"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            # Clean MAC for matching
            mac_clean = mac.replace(":", "_").lower()
            in_bt_card = False
            current_profile = None
            
            for line in result.stdout.splitlines():
                line_stripped = line.strip()
                
                # Check if this is our Bluetooth device's card
                if "bluez_card" in line_stripped.lower() and mac_clean in line_stripped.lower():
                    in_bt_card = True
                elif line.startswith("Card #") and in_bt_card:
                    # Moved to next card
                    break
                elif in_bt_card and line_stripped.startswith("Active Profile:"):
                    current_profile = line_stripped.split(":", 1)[1].strip()
                    break
            
            if current_profile:
                print(f"[AudioDeviceManager] BT device {mac} profile: {current_profile}")
            return current_profile
            
        except Exception as e:
            print(f"[AudioDeviceManager] Error getting BT profile: {e}")
            return None

    def set_bluetooth_profile_a2dp(self, mac: str) -> bool:
        """
        Set Bluetooth device to A2DP (high-quality audio) profile
        
        Args:
            mac: Bluetooth MAC address
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Find the card name
            result = subprocess.run(
                ["pactl", "list", "cards", "short"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False
            
            # Clean MAC for matching
            mac_clean = mac.replace(":", "_").lower()
            card_name = None
            
            for line in result.stdout.splitlines():
                if "bluez_card" in line.lower() and mac_clean in line.lower():
                    card_name = line.split()[0]
                    break
            
            if not card_name:
                print(f"[AudioDeviceManager] Could not find BT card for {mac}")
                return False
            
            print(f"[AudioDeviceManager] Setting {card_name} to A2DP profile...")
            
            # Set to A2DP sink profile
            result = subprocess.run(
                ["pactl", "set-card-profile", card_name, "a2dp_sink"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                print(f"[AudioDeviceManager] ✓ Set {mac} to A2DP (high-quality audio)")
                return True
            else:
                print(f"[AudioDeviceManager] ✗ Failed to set A2DP profile: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"[AudioDeviceManager] Error setting BT profile: {e}")
            import traceback
            traceback.print_exc()
            return False

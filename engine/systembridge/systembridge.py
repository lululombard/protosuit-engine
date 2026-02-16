"""
SystemBridge - System Metrics, Fan/Thermal Control, and Power Management Service
Exposes RPi 5 system health data and hardware controls via MQTT.
"""

import glob
import json
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil
from pydbus import SystemBus

from config.loader import ConfigLoader
from utils.mqtt_client import create_mqtt_client
from utils.notifications import publish_notification


class SystemBridge:
    """
    System Metrics, Fan/Thermal Control, and Power Management Service

    Subscribes to:
        - protogen/fins/systembridge/fan_curve/set
        - protogen/fins/systembridge/throttle_temp/set
        - protogen/fins/systembridge/power/reboot
        - protogen/fins/systembridge/power/shutdown

    Publishes:
        - protogen/fins/systembridge/status/metrics
        - protogen/fins/systembridge/status/fan_curve
        - protogen/fins/systembridge/status/throttle_temp
        - protogen/global/notifications
    """

    THERMAL_ZONE = "/sys/class/thermal/thermal_zone0"
    CPU_FREQ_PATH = "/sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq"
    BOOT_CONFIG = "/boot/firmware/config.txt"
    # Trip points 1-4 are active (fan curve), trip_point_0 is critical (110°C) — never touch
    FAN_TRIP_INDICES = [1, 2, 3, 4]

    def __init__(self):
        self.running = True
        self.config_loader = ConfigLoader()
        self.mqtt_client = None
        self._bus = SystemBus()

        # Config
        sb_config = self.config_loader.config.get("systembridge", {})
        self.publish_interval = sb_config.get("publish_interval", 5)

        fan_config = sb_config.get("fan_curve", {})
        self.fan_curve_defaults = {
            "trip_1": fan_config.get("trip_1", 50),
            "trip_2": fan_config.get("trip_2", 60),
            "trip_3": fan_config.get("trip_3", 67.5),
            "trip_4": fan_config.get("trip_4", 75),
        }

        # Discover fan hwmon path (hwmon number can change across reboots)
        self._fan_hwmon_path = self._discover_fan_hwmon()

        print("[SystemBridge] Initialized")

    # ======== Hardware Discovery ========

    def _discover_fan_hwmon(self) -> Optional[str]:
        """Find the fan hwmon sysfs path by globbing for fan1_input."""
        matches = glob.glob("/sys/devices/platform/cooling_fan/hwmon/hwmon*/fan1_input")
        if matches:
            path = os.path.dirname(matches[0])
            print(f"[SystemBridge] Fan hwmon discovered: {path}")
            return path
        print("[SystemBridge] No fan hwmon found (no cooling fan?)")
        return None

    # ======== Sysfs I/O ========

    def _read_sysfs(self, path: str) -> Optional[str]:
        """Read a sysfs file, returning None on error."""
        try:
            with open(path) as f:
                return f.read().strip()
        except Exception:
            return None

    def _write_sysfs(self, path: str, value: str) -> bool:
        """Write to a sysfs file via sudo tee (same pattern as ServiceController)."""
        try:
            result = subprocess.run(
                ["sudo", "tee", path],
                input=value,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"[SystemBridge] Error writing {path}: {e}")
            return False

    # ======== Metrics Collection ========

    def _collect_metrics(self) -> Dict[str, Any]:
        """Collect all system metrics into a single dict."""
        metrics: Dict[str, Any] = {}

        # CPU / memory / disk via psutil
        metrics["cpu_percent"] = psutil.cpu_percent(interval=None)

        mem = psutil.virtual_memory()
        metrics["memory_percent"] = mem.percent
        metrics["memory_used_gb"] = round(mem.used / (1024 ** 3), 1)
        metrics["memory_total_gb"] = round(mem.total / (1024 ** 3), 1)

        disk = psutil.disk_usage("/")
        metrics["disk_percent"] = disk.percent
        metrics["disk_free_gb"] = round(disk.free / (1024 ** 3), 1)
        metrics["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)

        # Temperature from thermal zone
        raw = self._read_sysfs(f"{self.THERMAL_ZONE}/temp")
        metrics["temperature"] = round(int(raw) / 1000, 1) if raw else None

        # CPU frequency — actual clock from vcgencmd + governor target from sysfs
        try:
            result = subprocess.run(
                ["vcgencmd", "measure_clock", "arm"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                # Output: "frequency(48)=1500000000"
                hz = int(result.stdout.strip().split("=")[1])
                metrics["cpu_freq_mhz"] = round(hz / 1_000_000)
            else:
                metrics["cpu_freq_mhz"] = None
        except Exception:
            metrics["cpu_freq_mhz"] = None

        raw = self._read_sysfs(self.CPU_FREQ_PATH)
        metrics["cpu_freq_target_mhz"] = round(int(raw) / 1000) if raw else None

        # Fan speed and PWM
        if self._fan_hwmon_path:
            raw = self._read_sysfs(f"{self._fan_hwmon_path}/fan1_input")
            metrics["fan_rpm"] = int(raw) if raw else None
            raw = self._read_sysfs(f"{self._fan_hwmon_path}/pwm1")
            if raw:
                pwm = int(raw)
                metrics["fan_pwm"] = pwm
                metrics["fan_percent"] = round(pwm / 255 * 100)
            else:
                metrics["fan_pwm"] = None
                metrics["fan_percent"] = None
        else:
            metrics["fan_rpm"] = None
            metrics["fan_pwm"] = None
            metrics["fan_percent"] = None

        # Uptime
        metrics["uptime_seconds"] = round(time.time() - psutil.boot_time())

        # Throttle status via vcgencmd
        try:
            result = subprocess.run(
                ["vcgencmd", "get_throttled"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                # Output: "throttled=0xe0008"
                hex_str = result.stdout.strip().split("=")[1]
                flags = int(hex_str, 16)
                metrics["throttle_hex"] = hex_str
                metrics["throttle_flags"] = {
                    "under_voltage_now": bool(flags & 0x1),
                    "freq_capped_now": bool(flags & 0x2),
                    "throttled_now": bool(flags & 0x4),
                    "soft_temp_limit_now": bool(flags & 0x8),
                    "under_voltage_occurred": bool(flags & 0x10000),
                    "freq_capped_occurred": bool(flags & 0x20000),
                    "throttled_occurred": bool(flags & 0x40000),
                    "soft_temp_limit_occurred": bool(flags & 0x80000),
                }
        except Exception:
            metrics["throttle_hex"] = None
            metrics["throttle_flags"] = None

        return metrics

    # ======== Fan Curve ========

    def _read_fan_curve(self) -> Dict[str, float]:
        """Read current fan curve trip point temperatures from sysfs."""
        curve = {}
        for i, idx in enumerate(self.FAN_TRIP_INDICES, start=1):
            raw = self._read_sysfs(f"{self.THERMAL_ZONE}/trip_point_{idx}_temp")
            curve[f"trip_{i}"] = int(raw) / 1000 if raw else None
        return curve

    def _validate_fan_curve(self, curve: Dict[str, float]) -> Optional[str]:
        """Validate fan curve values. Returns error message or None if valid."""
        keys = ["trip_1", "trip_2", "trip_3", "trip_4"]
        temps = []
        for key in keys:
            val = curve.get(key)
            if val is None:
                return f"Missing {key}"
            try:
                val = float(val)
            except (TypeError, ValueError):
                return f"Invalid value for {key}: {val}"
            if val < 30 or val > 100:
                return f"{key} must be between 30 and 100 (got {val})"
            temps.append(val)

        for i in range(len(temps) - 1):
            if temps[i + 1] - temps[i] < 5:
                return f"trip_{i + 2} must be at least 5°C above trip_{i + 1}"

        return None

    def _write_fan_curve(self, curve: Dict[str, float]) -> bool:
        """Write fan curve to sysfs and persist to config.yaml."""
        error = self._validate_fan_curve(curve)
        if error:
            print(f"[SystemBridge] Fan curve validation failed: {error}")
            return False

        keys = ["trip_1", "trip_2", "trip_3", "trip_4"]
        for i, idx in enumerate(self.FAN_TRIP_INDICES):
            millidegrees = str(int(float(curve[keys[i]]) * 1000))
            path = f"{self.THERMAL_ZONE}/trip_point_{idx}_temp"
            if not self._write_sysfs(path, millidegrees):
                print(f"[SystemBridge] Failed to write trip_point_{idx}")
                return False

        print(f"[SystemBridge] Fan curve applied: {curve}")
        self._save_fan_curve_to_config(curve)
        return True

    def _save_fan_curve_to_config(self, curve: Dict[str, float]):
        """Persist fan curve to config.yaml using targeted line replacement (preserves comments)."""
        try:
            import re
            config_path = os.path.join(os.getcwd(), "config.yaml")
            with open(config_path) as f:
                content = f.read()

            for key in ["trip_1", "trip_2", "trip_3", "trip_4"]:
                val = float(curve[key])
                # Format as int if whole number, else float
                val_str = str(int(val)) if val == int(val) else str(val)
                content = re.sub(
                    rf"^(\s*{key}:\s*)[\d.]+",
                    rf"\g<1>{val_str}",
                    content,
                    count=1,
                    flags=re.MULTILINE,
                )

            with open(config_path, "w") as f:
                f.write(content)
            print("[SystemBridge] Fan curve saved to config.yaml")
        except Exception as e:
            print(f"[SystemBridge] Error saving fan curve to config: {e}")

    def _apply_saved_fan_curve(self):
        """Apply fan curve from config.yaml to sysfs on startup."""
        print(f"[SystemBridge] Applying saved fan curve: {self.fan_curve_defaults}")
        error = self._validate_fan_curve(self.fan_curve_defaults)
        if error:
            print(f"[SystemBridge] Saved fan curve invalid ({error}), using hardware defaults")
            return

        keys = ["trip_1", "trip_2", "trip_3", "trip_4"]
        for i, idx in enumerate(self.FAN_TRIP_INDICES):
            millidegrees = str(int(float(self.fan_curve_defaults[keys[i]]) * 1000))
            path = f"{self.THERMAL_ZONE}/trip_point_{idx}_temp"
            if not self._write_sysfs(path, millidegrees):
                print(f"[SystemBridge] Failed to apply trip_point_{idx}, skipping rest")
                return

        print("[SystemBridge] Fan curve applied from config")

    # ======== Throttle Temperature ========

    def _read_throttle_temp(self) -> Optional[int]:
        """Read temp_limit from /boot/firmware/config.txt (Pi 5 throttle parameter)."""
        try:
            with open(self.BOOT_CONFIG) as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("temp_limit="):
                        return int(stripped.split("=")[1])
        except Exception as e:
            print(f"[SystemBridge] Error reading throttle temp: {e}")
        return None  # Not set = RPi default (85°C)

    def _write_throttle_temp(self, temp: int) -> bool:
        """Write temp_limit to /boot/firmware/config.txt (reboot required)."""
        if temp < 60 or temp > 90:
            print(f"[SystemBridge] Throttle temp must be 60-90 (got {temp})")
            return False

        try:
            with open(self.BOOT_CONFIG) as f:
                lines = f.readlines()

            # Replace existing temp_limit or append under [all]
            found = False
            new_lines = []
            for line in lines:
                stripped = line.strip()
                # Remove any stale temp_soft_limit entries
                if stripped.startswith("temp_soft_limit="):
                    continue
                if stripped.startswith("temp_limit="):
                    new_lines.append(f"temp_limit={temp}\n")
                    found = True
                else:
                    new_lines.append(line)

            if not found:
                new_lines.append(f"temp_limit={temp}\n")

            content = "".join(new_lines)
            result = subprocess.run(
                ["sudo", "tee", self.BOOT_CONFIG],
                input=content,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                print(f"[SystemBridge] Throttle temp set to {temp}°C (reboot required)")
                return True
            print(f"[SystemBridge] Failed to write config.txt: {result.stderr}")
            return False
        except Exception as e:
            print(f"[SystemBridge] Error writing throttle temp: {e}")
            return False

    # ======== Power Controls ========

    def _do_reboot(self):
        """Reboot the system via logind D-Bus."""
        publish_notification(
            self.mqtt_client, "system", "reboot", "power", "System rebooting..."
        )
        time.sleep(0.5)
        try:
            logind = self._bus.get("org.freedesktop.login1")
            logind.Reboot(False)
        except Exception as e:
            print(f"[SystemBridge] Reboot failed: {e}")

    def _do_shutdown(self):
        """Shut down the system via logind D-Bus."""
        publish_notification(
            self.mqtt_client, "system", "shutdown", "power", "System shutting down..."
        )
        time.sleep(0.5)
        try:
            logind = self._bus.get("org.freedesktop.login1")
            logind.PowerOff(False)
        except Exception as e:
            print(f"[SystemBridge] Shutdown failed: {e}")

    # ======== MQTT ========

    def init_mqtt(self):
        """Initialize MQTT connection and subscriptions."""
        print("[SystemBridge] Initializing MQTT...")

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                print("[SystemBridge] Connected to MQTT broker")
                client.subscribe("protogen/fins/systembridge/fan_curve/set")
                client.subscribe("protogen/fins/systembridge/throttle_temp/set")
                client.subscribe("protogen/fins/systembridge/power/reboot")
                client.subscribe("protogen/fins/systembridge/power/shutdown")
                client.subscribe("protogen/fins/config/reload")
                client.subscribe("protogen/fins/systembridge/config/reload")
            else:
                print(f"[SystemBridge] Failed to connect to MQTT: {rc}")

        def on_message(client, userdata, msg):
            self._on_mqtt_message(msg.topic, msg.payload.decode())

        self.mqtt_client = create_mqtt_client(self.config_loader)
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_message = on_message
        self.mqtt_client.loop_start()

        # Publish initial state
        self._publish_fan_curve()
        self._publish_throttle_temp()

        time.sleep(0.5)

    def _on_mqtt_message(self, topic: str, payload: str):
        """Route incoming MQTT messages."""
        try:
            if topic == "protogen/fins/systembridge/fan_curve/set":
                data = json.loads(payload)
                if self._write_fan_curve(data):
                    self._publish_fan_curve()
                    publish_notification(
                        self.mqtt_client, "system", "updated",
                        "fan_curve", "Fan curve updated",
                    )
                else:
                    publish_notification(
                        self.mqtt_client, "system", "error",
                        "fan_curve", "Invalid fan curve settings",
                    )

            elif topic == "protogen/fins/systembridge/throttle_temp/set":
                data = json.loads(payload)
                temp = data.get("temp")
                if temp is not None and self._write_throttle_temp(int(temp)):
                    self._publish_throttle_temp()
                    publish_notification(
                        self.mqtt_client, "system", "updated",
                        "throttle_temp",
                        f"Throttle temp set to {temp}°C (reboot required)",
                    )
                else:
                    publish_notification(
                        self.mqtt_client, "system", "error",
                        "throttle_temp", "Invalid throttle temperature (60-90°C)",
                    )

            elif topic == "protogen/fins/systembridge/power/reboot":
                print("[SystemBridge] Reboot requested")
                threading.Thread(target=self._do_reboot, daemon=True).start()

            elif topic == "protogen/fins/systembridge/power/shutdown":
                print("[SystemBridge] Shutdown requested")
                threading.Thread(target=self._do_shutdown, daemon=True).start()

            elif topic in ("protogen/fins/config/reload", "protogen/fins/systembridge/config/reload"):
                self._handle_config_reload()

        except Exception as e:
            print(f"[SystemBridge] Error handling {topic}: {e}")

    def _handle_config_reload(self):
        """Reload configuration from file."""
        print("[SystemBridge] Reloading configuration...")
        self.config_loader.reload()
        sb_config = self.config_loader.config.get("systembridge", {})
        self.publish_interval = sb_config.get("publish_interval", 5)
        print("[SystemBridge] Configuration reloaded")

    # ======== Status Publishing ========

    def _publish_fan_curve(self):
        """Publish current fan curve trip points."""
        if not self.mqtt_client:
            return
        curve = self._read_fan_curve()
        self.mqtt_client.publish(
            "protogen/fins/systembridge/status/fan_curve",
            json.dumps(curve),
            retain=True,
        )

    def _publish_throttle_temp(self):
        """Publish current throttle temperature setting."""
        if not self.mqtt_client:
            return
        temp = self._read_throttle_temp()
        status = {
            "temp": temp if temp is not None else 85,
            "is_default": temp is None,
        }
        self.mqtt_client.publish(
            "protogen/fins/systembridge/status/throttle_temp",
            json.dumps(status),
            retain=True,
        )

    def _start_metrics_publisher(self):
        """Start background thread for periodic metrics publishing."""
        thread = threading.Thread(target=self._metrics_loop, daemon=True)
        thread.start()

    def _metrics_loop(self):
        """Periodically collect and publish system metrics."""
        # Prime psutil CPU measurement (first call always returns 0.0)
        psutil.cpu_percent(interval=None)

        while self.running:
            try:
                metrics = self._collect_metrics()
                if self.mqtt_client:
                    self.mqtt_client.publish(
                        "protogen/fins/systembridge/status/metrics",
                        json.dumps(metrics),
                        retain=True,
                    )
            except Exception as e:
                print(f"[SystemBridge] Error publishing metrics: {e}")
            time.sleep(self.publish_interval)

    # ======== Lifecycle ========

    def cleanup(self):
        """Clean up resources."""
        print("[SystemBridge] Cleaning up...")
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

    def run(self):
        """Main run loop."""
        print("[SystemBridge] Starting...")

        self._apply_saved_fan_curve()
        self.init_mqtt()
        self._start_metrics_publisher()

        print("[SystemBridge] Running. Press Ctrl+C to stop.")

        while self.running:
            time.sleep(1)

        self.cleanup()
        print("[SystemBridge] Stopped.")

    def _signal_handler(self, signum, frame):
        print(f"\n[SystemBridge] Received signal {signum}, shutting down...")
        self.running = False


def main():
    bridge = SystemBridge()
    signal.signal(signal.SIGINT, bridge._signal_handler)
    signal.signal(signal.SIGTERM, bridge._signal_handler)
    bridge.run()


if __name__ == "__main__":
    main()

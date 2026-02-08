"""
ServiceController - Generic systemd service management via D-Bus
Uses pydbus for all systemd operations (reads AND writes).
Write operations require a polkit rule granting the user authorization.
Config file writes still use subprocess (sudo tee) since there's no dbus API for that.

This class has NO MQTT dependency - it returns data for callers to publish.
"""

import subprocess
import json
import os
import threading
import logging
from dataclasses import dataclass, asdict
from typing import Optional, Callable

from pydbus import SystemBus

logger = logging.getLogger(__name__)


@dataclass
class ServiceHealth:
    """Snapshot of systemd service health properties"""
    unit_name: str
    active_state: str       # "active", "inactive", "failed", "activating", etc.
    sub_state: str          # "running", "dead", "exited", "failed", etc.
    is_enabled: bool        # UnitFileState in ("enabled", "enabled-runtime")
    is_active: bool         # active_state == "active"
    main_pid: int           # MainPID (0 if not running)
    memory_bytes: int       # MemoryCurrent (-1 if unavailable)
    n_restarts: int         # NRestarts
    state_change_timestamp: int  # StateChangeTimestampMonotonic (microseconds)

    def to_dict(self) -> dict:
        return asdict(self)


class ServiceController:
    """
    Generic systemd service controller.

    All systemd operations (start/stop/enable/disable/status) go through D-Bus
    via pydbus. A polkit rule must grant the running user authorization for
    write operations on the managed unit.

    Config file reads/writes use the filesystem directly (reads) or subprocess
    with sudo tee (writes), since D-Bus has no API for arbitrary file I/O.
    """

    def __init__(self, unit_name: str):
        """
        Args:
            unit_name: systemd unit name without .service suffix,
                       e.g. "shairport-sync" or "raspotify"
        """
        self.unit_name = unit_name
        self._full_name = f"{unit_name}.service"
        self._bus = SystemBus()
        self._systemd = self._bus.get("org.freedesktop.systemd1")
        self._unit_proxy = None
        self._log_process: Optional[subprocess.Popen] = None
        self._log_thread: Optional[threading.Thread] = None
        self._log_running = False

    # ======== D-Bus unit proxy ========

    def _get_unit(self):
        """Get or refresh the D-Bus proxy for this unit."""
        try:
            # LoadUnit ensures the unit object exists on the bus even if inactive
            unit_path = self._systemd.LoadUnit(self._full_name)
            self._unit_proxy = self._bus.get("org.freedesktop.systemd1", unit_path)
        except Exception as e:
            logger.error(f"[{self.unit_name}] Failed to get unit proxy: {e}")
            self._unit_proxy = None
        return self._unit_proxy

    # ======== Read operations ========

    def get_health(self) -> ServiceHealth:
        """
        Get comprehensive service health via D-Bus properties.
        Never raises - returns degraded data with active_state="unknown" on error.
        """
        try:
            unit = self._get_unit()
            if unit is None:
                return self._unknown_health()

            active_state = unit.ActiveState
            sub_state = unit.SubState
            is_enabled = unit.UnitFileState in ("enabled", "enabled-runtime")
            main_pid = unit.MainPID

            try:
                memory = unit.MemoryCurrent
                # systemd returns 2^64-1 (max uint64) when unavailable
                if memory >= 2**63:
                    memory = -1
            except Exception:
                memory = -1

            try:
                n_restarts = unit.NRestarts
            except Exception:
                n_restarts = 0

            try:
                state_change_ts = unit.StateChangeTimestampMonotonic
            except Exception:
                state_change_ts = 0

            return ServiceHealth(
                unit_name=self.unit_name,
                active_state=active_state,
                sub_state=sub_state,
                is_enabled=is_enabled,
                is_active=(active_state == "active"),
                main_pid=main_pid,
                memory_bytes=memory,
                n_restarts=n_restarts,
                state_change_timestamp=state_change_ts,
            )
        except Exception as e:
            logger.error(f"[{self.unit_name}] Failed to get health: {e}")
            return self._unknown_health()

    def is_active(self) -> bool:
        """Quick check: is the service currently active?"""
        try:
            unit = self._get_unit()
            return unit is not None and unit.ActiveState == "active"
        except Exception:
            return False

    def is_enabled(self) -> bool:
        """Quick check: is the service enabled (starts at boot)?"""
        try:
            unit = self._get_unit()
            if unit is None:
                return False
            return unit.UnitFileState in ("enabled", "enabled-runtime")
        except Exception:
            return False

    def _unknown_health(self) -> ServiceHealth:
        return ServiceHealth(
            unit_name=self.unit_name,
            active_state="unknown",
            sub_state="unknown",
            is_enabled=False,
            is_active=False,
            main_pid=0,
            memory_bytes=-1,
            n_restarts=0,
            state_change_timestamp=0,
        )

    # ======== Write operations (D-Bus, requires polkit authorization) ========

    def enable(self) -> bool:
        """Enable and start the service (equivalent to systemctl enable --now)."""
        try:
            # EnableUnitFiles(files, runtime, force) -> (carries_install_info, changes)
            self._systemd.EnableUnitFiles([self._full_name], False, True)
            self._systemd.Reload()
            unit = self._get_unit()
            if unit is None:
                return False
            unit.Start("replace")
            logger.info(f"[{self.unit_name}] Enabled and started")
            return True
        except Exception as e:
            logger.error(f"[{self.unit_name}] Failed to enable: {e}")
            return False

    def disable(self) -> bool:
        """Disable and stop the service (equivalent to systemctl disable --now)."""
        try:
            unit = self._get_unit()
            if unit is not None:
                unit.Stop("replace")
            # DisableUnitFiles(files, runtime) -> changes
            self._systemd.DisableUnitFiles([self._full_name], False)
            self._systemd.Reload()
            logger.info(f"[{self.unit_name}] Disabled and stopped")
            return True
        except Exception as e:
            logger.error(f"[{self.unit_name}] Failed to disable: {e}")
            return False

    def restart(self) -> bool:
        """Restart the service."""
        try:
            # Use manager-level RestartUnit instead of unit.Restart()
            # because pydbus resolves unit.Restart to the Restart= property
            self._systemd.RestartUnit(self._full_name, "replace")
            logger.info(f"[{self.unit_name}] Restarted")
            return True
        except Exception as e:
            logger.error(f"[{self.unit_name}] Failed to restart: {e}")
            return False

    def start(self) -> bool:
        """Start the service without enabling it."""
        try:
            unit = self._get_unit()
            if unit is None:
                return False
            unit.Start("replace")
            logger.info(f"[{self.unit_name}] Started")
            return True
        except Exception as e:
            logger.error(f"[{self.unit_name}] Failed to start: {e}")
            return False

    def stop(self) -> bool:
        """Stop the service without disabling it."""
        try:
            unit = self._get_unit()
            if unit is None:
                return False
            unit.Stop("replace")
            logger.info(f"[{self.unit_name}] Stopped")
            return True
        except Exception as e:
            logger.error(f"[{self.unit_name}] Failed to stop: {e}")
            return False

    # ======== Config file operations ========

    def write_config(self, path: str, content: str) -> bool:
        """Write content to a config file via sudo tee, then chmod 644 for readability."""
        try:
            result = subprocess.run(
                ["sudo", "tee", path],
                input=content,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.error(f"[{self.unit_name}] Failed to write {path}: {result.stderr.strip()}")
                return False
            # Ensure the file is readable by the service and our process
            subprocess.run(["sudo", "chmod", "644", path],
                           capture_output=True, timeout=5)
            return True
        except Exception as e:
            logger.error(f"[{self.unit_name}] Error writing {path}: {e}")
            return False

    def read_config(self, path: str) -> Optional[str]:
        """Read a config file. Falls back to sudo if permission denied."""
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return None
        except PermissionError:
            # Fall back to sudo cat for root-owned files
            try:
                result = subprocess.run(
                    ["sudo", "cat", path],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                pass
            return None
        except Exception as e:
            logger.error(f"[{self.unit_name}] Error reading {path}: {e}")
            return None

    def mkdir_p(self, path: str) -> bool:
        """Create directory with sudo mkdir -p, then chmod 755 for readability."""
        try:
            result = subprocess.run(
                ["sudo", "mkdir", "-p", path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                subprocess.run(["sudo", "chmod", "755", path],
                               capture_output=True, timeout=5)
                return True
            return False
        except Exception:
            return False

    # ======== Journal log streaming ========

    def start_log_stream(self, callback: Callable[[dict], None],
                         lines: int = 50) -> bool:
        """
        Start streaming journal logs for this service.

        Runs journalctl -f as a subprocess. Each parsed JSON log entry is
        passed to the callback. The callback receives a dict with keys like
        MESSAGE, PRIORITY, _PID, __REALTIME_TIMESTAMP, etc.
        """
        if self._log_running:
            return True

        try:
            self._log_process = subprocess.Popen(
                [
                    "journalctl", "-f",
                    "-u", self._full_name,
                    f"--lines={lines}",
                    "--output=json",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            self._log_running = True
            self._log_thread = threading.Thread(
                target=self._log_reader,
                args=(callback,),
                daemon=True,
            )
            self._log_thread.start()
            logger.info(f"[{self.unit_name}] Log stream started")
            return True
        except Exception as e:
            logger.error(f"[{self.unit_name}] Failed to start log stream: {e}")
            return False

    def stop_log_stream(self):
        """Stop the journal log stream."""
        self._log_running = False
        if self._log_process:
            try:
                self._log_process.terminate()
                self._log_process.wait(timeout=5)
            except Exception:
                try:
                    self._log_process.kill()
                except Exception:
                    pass
            self._log_process = None
        logger.info(f"[{self.unit_name}] Log stream stopped")

    def _log_reader(self, callback: Callable[[dict], None]):
        """Background thread reading journalctl JSON output."""
        try:
            for line in self._log_process.stdout:
                if not self._log_running:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    callback(entry)
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            if self._log_running:
                logger.error(f"[{self.unit_name}] Log stream error: {e}")
        finally:
            self._log_running = False

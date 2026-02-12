"""
Generic Executable Launcher - Runs .sh scripts
"""

import subprocess
import time
import os
import json
import select
from typing import Callable, Optional, Dict
from launcher.launchers.base_launcher import BaseLauncher
from utils.program_helper import ProgramHelper


class ExecLauncher(BaseLauncher):
    """
    Generic launcher for executable scripts (.sh)
    Runs the script and monitors it until completion
    """

    def __init__(
        self,
        script_path: str,
        display_config,
        system_config,
        on_exit_callback: Optional[Callable] = None,
        mqtt_client=None,
    ):
        """
        Initialize Exec Launcher

        Args:
            script_path: Full path to the .sh script to execute
            display_config: Display configuration (width, height, positions)
            system_config: System configuration (x_display, window_class)
            on_exit_callback: Function to call when script exits
            mqtt_client: MQTT client for input handling (optional)
        """
        super().__init__()
        self.script_path = script_path
        self.display_config = display_config
        self.system_config = system_config
        self.on_exit_callback = on_exit_callback
        self.mqtt_client = mqtt_client
        self.x_display = system_config.x_display
        self.monitor_thread = None
        self.script_name = os.path.basename(script_path)

        # Window tracking for input routing
        self.windows: Dict[str, str] = {}  # {"left": window_id, "right": window_id}
        self.use_window_targeting = False  # True for multi-window games like Doom, False for single-window

        # Setup signaling for scripts that need extended initialization time
        self._setup_started = False
        self._setup_topic = "protogen/fins/launcher/setup"
        self._setup_listener = None

    def launch(self) -> bool:
        """
        Launch the executable script

        Returns:
            True if launch successful, False otherwise
        """
        try:
            # Check if script exists and is executable
            if not os.path.exists(self.script_path):
                print(f"[ExecLauncher] Script not found: {self.script_path}")
                return False

            if not os.access(self.script_path, os.X_OK):
                print(f"[ExecLauncher] Script is not executable: {self.script_path}")
                return False

            # Setup environment
            env = os.environ.copy()
            env["DISPLAY"] = self.x_display
            env["PROTOSUIT_DISPLAY_WIDTH"] = str(self.display_config.width)
            env["PROTOSUIT_DISPLAY_HEIGHT"] = str(self.display_config.height)
            env["PROTOSUIT_LEFT_X"] = str(self.display_config.left_x)
            env["PROTOSUIT_RIGHT_X"] = str(self.display_config.right_x)
            env["PROTOSUIT_Y"] = str(self.display_config.y)

            print(f"[ExecLauncher] Launching script: {self.script_name}")

            # Start setup listener BEFORE launching so we don't miss "started" message
            self._start_setup_listener()

            # Execute the script
            process = subprocess.Popen(
                [self.script_path],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(self.script_path),
            )

            # Wait a moment for process to start
            time.sleep(0.5)

            # Check if process is still running
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                print(f"[ExecLauncher] Script failed with code {process.returncode}")
                if stderr:
                    print(f"[ExecLauncher] stderr: {stderr.decode()}")
                return False

            # Process is running
            self.processes.append(process)
            print(f"[ExecLauncher] Script started (PID: {process.pid})")

            # Start monitoring for exit
            self.monitor_thread = ProgramHelper.monitor_process(
                process, self._on_exec_exit
            )

            # Discover windows and subscribe to MQTT inputs
            self.discover_windows()
            self.subscribe_to_inputs()

            return True

        except Exception as e:
            print(f"[ExecLauncher] Failed to launch script: {e}")
            import traceback

            traceback.print_exc()
            return False

    def is_running(self) -> bool:
        """
        Check if the script is currently running

        Returns:
            True if process is running, False otherwise
        """
        try:
            if self.processes:
                proc = self.processes[0]
                return proc.poll() is None
            return False
        except Exception:
            return False

    def _on_exec_exit(self):
        """Callback when script process exits"""
        print(f"[ExecLauncher] Script '{self.script_name}' exited")
        time.sleep(0.5)

        # Cleanup
        self.cleanup()

        # Call user callback
        if self.on_exit_callback:
            self.on_exit_callback()

    def cleanup(self):
        """Clean up script processes and their children"""
        print(f"[ExecLauncher] Cleaning up script: {self.script_name}")

        # Stop setup listener if still running
        self._stop_setup_listener()

        # Unsubscribe from MQTT inputs
        self.unsubscribe_from_inputs()

        # Terminate processes using helper
        ProgramHelper.cleanup_processes(self.processes)

        self.processes = []
        self.window_ids = []
        self.windows = {}
        self.use_window_targeting = False

    def _start_setup_listener(self):
        """Start a mosquitto_sub process to listen for setup messages"""
        try:
            self._setup_listener = subprocess.Popen(
                ["mosquitto_sub", "-t", self._setup_topic, "-C", "2"],  # -C 2 = exit after 2 messages
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            print(f"[ExecLauncher] Started setup listener on {self._setup_topic}")
        except Exception as e:
            print(f"[ExecLauncher] Failed to start setup listener: {e}")
            self._setup_listener = None

    def _stop_setup_listener(self):
        """Stop the setup listener process"""
        if self._setup_listener:
            try:
                self._setup_listener.terminate()
                self._setup_listener.wait(timeout=1)
            except Exception:
                pass
            self._setup_listener = None

    def _wait_for_ready(self):
        """Wait for script to signal it's ready, or use default timeout"""
        if not self._setup_listener:
            print(f"[ExecLauncher] No setup listener, using default wait")
            time.sleep(1.0)
            return

        # Read messages from mosquitto_sub with timeout
        timeout_total = 30.0
        start_time = time.time()

        while time.time() - start_time < timeout_total:
            # Check if there's data to read (non-blocking)
            ready, _, _ = select.select([self._setup_listener.stdout], [], [], 0.5)
            if ready:
                line = self._setup_listener.stdout.readline().decode().strip().lower()
                if line == "started":
                    print(f"[ExecLauncher] Script signaled setup started")
                    self._setup_started = True
                elif line == "ready":
                    print(f"[ExecLauncher] Script signaled ready")
                    self._stop_setup_listener()
                    return

            # If we haven't seen "started" after 1 second, script doesn't use signaling
            if not self._setup_started and time.time() - start_time > 1.0:
                print(f"[ExecLauncher] No setup signal received, using default wait")
                self._stop_setup_listener()
                time.sleep(0.5)
                return

        print(f"[ExecLauncher] Timeout waiting for ready signal, proceeding anyway")
        self._stop_setup_listener()

    def discover_windows(self):
        """Auto-discover game windows and assign to left/right displays"""
        try:
            self._wait_for_ready()

            all_windows = []

            # Strategy 1: Search by PID tree (most reliable)
            if self.processes:
                for process in self.processes:
                    windows = ProgramHelper.find_windows_by_pid_tree(process.pid)
                    if windows:
                        all_windows.extend(windows)
                        print(f"[ExecLauncher] Found {len(windows)} window(s) by PID tree: {windows}")

            # Strategy 2: If no windows found by PID, use the active window
            if not all_windows:
                active_window = ProgramHelper.get_active_window()
                if active_window:
                    all_windows.append(active_window)
                    print(f"[ExecLauncher] Using active window: {active_window}")

            if not all_windows:
                print(f"[ExecLauncher] No windows found for {self.script_name}, inputs will not work")
                return

            # Remove duplicates
            all_windows = list(dict.fromkeys(all_windows))

            print(f"[ExecLauncher] Total {len(all_windows)} unique window(s) for {self.script_name}")

            # Get window positions to determine left vs right
            window_positions = []
            for win_id in all_windows:
                pos = ProgramHelper.get_window_position(win_id)
                if pos:
                    x, y = pos
                    window_positions.append((win_id, x, y))
                    print(f"[ExecLauncher] Window {win_id} at position ({x}, {y})")

            if not window_positions:
                # Fallback: assign windows sequentially
                if len(all_windows) == 1:
                    self.windows["left"] = all_windows[0]
                    self.windows["right"] = all_windows[0]  # Same window for both
                elif len(all_windows) >= 2:
                    self.windows["left"] = all_windows[0]
                    self.windows["right"] = all_windows[1]
            else:
                # Sort by X position to determine left vs right
                window_positions.sort(key=lambda w: w[1])  # Sort by X coordinate (ascending)

                if len(window_positions) == 1:
                    self.windows["left"] = window_positions[0][0]
                    self.windows["right"] = window_positions[0][0]
                else:
                    # Assign by physical position: leftmost window (X=0) → left, rightmost (X=720) → right
                    self.windows["left"] = window_positions[0][0]    # Leftmost window (smallest X)
                    self.windows["right"] = window_positions[-1][0]  # Rightmost window (largest X)

            # Determine if we should use window targeting
            # Check both unique window IDs AND physical positions
            unique_windows = set(self.windows.values())
            has_multiple_windows = len(unique_windows) > 1

            # Also check if windows are at significantly different X positions (for Doom)
            # If leftmost and rightmost windows are >100px apart, treat as multi-window
            if window_positions and len(window_positions) >= 2:
                leftmost_x = window_positions[0][1]
                rightmost_x = window_positions[-1][1]
                has_separate_positions = abs(rightmost_x - leftmost_x) > 100
                if has_separate_positions:
                    has_multiple_windows = True
                    print(f"[ExecLauncher] Detected separate windows at X positions: {leftmost_x} and {rightmost_x}")

            self.use_window_targeting = has_multiple_windows

            mode = "window-targeted" if self.use_window_targeting else "focused-window"
            print(f"[ExecLauncher] Window mapping: left={self.windows.get('left')}, right={self.windows.get('right')} (mode: {mode})")

        except Exception as e:
            print(f"[ExecLauncher] Error discovering windows: {e}")
            import traceback
            traceback.print_exc()

    def subscribe_to_inputs(self):
        """Subscribe to MQTT input messages (no-op, handled by parent Launcher)"""
        # The parent Launcher class handles the subscription and routes messages to us
        # via handle_input_message(), so we don't need to subscribe here
        if self.mqtt_client and self.windows:
            print(f"[ExecLauncher] Ready to receive inputs for {self.script_name}")

    def unsubscribe_from_inputs(self):
        """Unsubscribe from MQTT inputs (no-op, handled by parent Launcher)"""
        # The parent Launcher class handles the subscription lifecycle
        pass

    def handle_input_message(self, payload: str):
        """
        Handle MQTT input message and route to appropriate window

        Args:
            payload: JSON string with format {"key": "SPACE", "action": "key", "display": "left"}
        """
        try:
            # Parse JSON payload
            data = json.loads(payload)
            key = data.get("key", "")
            action = data.get("action", "key")
            display = data.get("display", "left")

            if not key:
                print("[ExecLauncher] Invalid input: missing 'key' field")
                return

            # Determine which window(s) to send input to
            target_windows = []
            if display == "both":
                # Send to all discovered windows
                target_windows = list(set(self.windows.values()))
            elif display in ["left", "right"]:
                window_id = self.windows.get(display)
                if window_id:
                    target_windows = [window_id]
            else:
                print(f"[ExecLauncher] Invalid display: {display}")
                return

            if not target_windows:
                print(f"[ExecLauncher] No window found for display '{display}'")
                return

            # Send input to target window(s)
            for window_id in target_windows:
                success = ProgramHelper.send_input(
                    window_id,
                    key,
                    action,
                    use_window_target=self.use_window_targeting
                )
                if success:
                    target_desc = f"window {window_id}" if self.use_window_targeting else "focused window"
                    print(f"[ExecLauncher] Sent {action}({key}) to {display} {target_desc}")
                else:
                    print(f"[ExecLauncher] Failed to send {action}({key}) to window {window_id}")

        except json.JSONDecodeError as e:
            print(f"[ExecLauncher] Invalid JSON in input message: {e}")
        except Exception as e:
            print(f"[ExecLauncher] Error handling input message: {e}")
            import traceback
            traceback.print_exc()

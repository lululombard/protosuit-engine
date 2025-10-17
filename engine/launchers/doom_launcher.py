"""
Doom Launcher - Launches Chocolate Doom in 1v1 deathmatch mode
"""

import subprocess
import time
import os
from typing import Callable, Optional
from engine.launchers.base_launcher import BaseLauncher
from engine.launchers.program_helper import ProgramHelper


class DoomLauncher(BaseLauncher):
    """
    Launcher for Chocolate Doom 1v1 deathmatch
    Manages server/client processes, window positioning, and auto-start
    """

    def __init__(
        self,
        config,
        display_config,
        system_config,
        on_exit_callback: Optional[Callable] = None,
    ):
        """
        Initialize Doom launcher

        Args:
            config: Doom configuration from config.yaml
            display_config: Display configuration (width, height, positions)
            system_config: System configuration (x_display, window_class)
            on_exit_callback: Function to call when Doom exits
        """
        super().__init__()
        self.config = config
        self.display_config = display_config
        self.system_config = system_config
        self.on_exit_callback = on_exit_callback
        self.doom_path = config.executable
        self.x_display = system_config.x_display
        self.window_class = system_config.window_class

        # Timing configuration (hardcoded - these rarely need tweaking)
        self.SERVER_STARTUP_DELAY = 0.1  # Wait for server to start
        self.WINDOW_POSITION_DELAY = 0.2  # Wait for windows to appear
        self.AUTO_START_DELAY = 2.0  # Wait before auto-starting game
        self.REPOSITION_INTERVAL = 0.5  # Interval for repositioning
        self.REPOSITION_COUNT = 10  # Number of times to reposition

        self.monitor_thread = None

    def launch(self) -> bool:
        """
        Launch Doom server and client

        Returns:
            True if launch successful, False otherwise
        """
        try:
            # Launch server on left fin
            server_env = os.environ.copy()
            server_env["DISPLAY"] = self.x_display

            server = subprocess.Popen(
                [
                    self.doom_path,
                    "-width",
                    str(self.display_config.width),
                    "-height",
                    str(self.display_config.height),
                    "-server",
                    "-deathmatch",
                    "-nosound",
                    "-window",
                    "-nograbmouse",
                ],
                env=server_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.processes.append(server)
            print(f"Started Doom server (PID: {server.pid})")

            time.sleep(self.SERVER_STARTUP_DELAY)

            # Launch client on right fin
            client_env = os.environ.copy()
            client_env["DISPLAY"] = self.x_display

            client = subprocess.Popen(
                [
                    self.doom_path,
                    "-width",
                    str(self.display_config.width),
                    "-height",
                    str(self.display_config.height),
                    "-connect",
                    "localhost",
                    "-nosound",
                    "-window",
                    "-nograbmouse",
                ],
                env=client_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.processes.append(client)
            print(f"Started Doom client (PID: {client.pid})")

            # Position windows
            time.sleep(self.WINDOW_POSITION_DELAY)
            self._position_windows()

            # Auto-start game
            print("Auto-starting game...")
            time.sleep(self.AUTO_START_DELAY)
            self._auto_start_game()

            # Keep repositioning for a few seconds
            print("Ensuring windows stay visible...")
            for i in range(self.REPOSITION_COUNT):
                time.sleep(self.REPOSITION_INTERVAL)
                self._position_windows()

            # Start monitoring for exit (monitor any process for exit callback)
            if self.processes:
                self.monitor_thread = ProgramHelper.monitor_process(
                    self.processes[0], self._on_doom_exit
                )

            return True
        except Exception as e:
            print(f"Failed to launch Doom: {e}")
            self.cleanup()
            return False

    def is_running(self) -> bool:
        """
        Check if Doom is currently running

        Returns:
            True if any Doom process is running, False otherwise
        """
        try:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True)

            for line in result.stdout.split("\n"):
                if "chocolate-doom" in line and "<defunct>" not in line:
                    # Check if process is not zombie
                    parts = line.split()
                    if len(parts) > 7 and "Z" not in parts[7]:
                        return True
            return False
        except Exception:
            return False

    def _on_doom_exit(self):
        """Callback when Doom process exits"""
        print("Doom processes exited")
        time.sleep(0.5)

        # Cleanup
        self.cleanup()

        # Call user callback
        if self.on_exit_callback:
            self.on_exit_callback()

    def cleanup(self):
        """Clean up Doom processes and show shader windows"""
        print("Cleaning up Doom launcher...")

        # Terminate processes using helper
        ProgramHelper.cleanup_processes(self.processes)

        # Force kill any remaining Doom processes
        try:
            subprocess.run(
                ["pkill", "-9", "chocolate-doom"],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        except:
            pass

        self.processes = []
        self.window_ids = []

    def _position_windows(self):
        """Position Doom windows using ProgramHelper"""
        try:
            # Find Doom windows
            self.window_ids = ProgramHelper.find_windows("Chocolate Doom", timeout=0.5)

            if not self.window_ids:
                return

            # Get positions from config
            pos_left = self.config.position_left
            pos_right = self.config.position_right

            if len(self.window_ids) >= 2:
                # Position both windows
                ProgramHelper.position_window(
                    self.window_ids[0],
                    pos_left[0],
                    pos_left[1],
                    self.display_config.width,
                    self.display_config.height,
                )
                print(
                    f"Positioned window {self.window_ids[0]} to left fin ({pos_left[0]},{pos_left[1]})"
                )

                ProgramHelper.position_window(
                    self.window_ids[1],
                    pos_right[0],
                    pos_right[1],
                    self.display_config.width,
                    self.display_config.height,
                )
                print(
                    f"Positioned window {self.window_ids[1]} to right fin ({pos_right[0]},{pos_right[1]})"
                )
            elif len(self.window_ids) == 1:
                # Only one window, position on left
                ProgramHelper.position_window(
                    self.window_ids[0],
                    pos_left[0],
                    pos_left[1],
                    self.display_config.width,
                    self.display_config.height,
                )
                print(
                    f"Positioned window {self.window_ids[0]} to left fin ({pos_left[0]},{pos_left[1]})"
                )
        except Exception as e:
            print(f"Failed to position Doom windows: {e}")

    def _auto_start_game(self):
        """Automatically start the game by sending Space to server"""
        try:
            if not self.window_ids:
                print("No Doom windows found for auto-start")
                return

            # Send Space to first window (server)
            if len(self.window_ids) > 0:
                server_window = self.window_ids[0]

                # Focus window
                subprocess.run(
                    ["xdotool", "windowactivate", "--sync", server_window],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    timeout=1,
                )
                time.sleep(0.5)

                # Send Space key using helper
                ProgramHelper.send_keys(server_window, "space")
                print(f"Sent Space to server window {server_window}")
        except Exception as e:
            print(f"Failed to auto-start Doom: {e}")

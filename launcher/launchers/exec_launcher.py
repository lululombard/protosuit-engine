"""
Generic Executable Launcher - Runs .sh scripts
"""

import subprocess
import time
import os
from typing import Callable, Optional
from launcher.launchers.base_launcher import BaseLauncher
from launcher.launchers.program_helper import ProgramHelper


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
    ):
        """
        Initialize Exec Launcher

        Args:
            script_path: Full path to the .sh script to execute
            display_config: Display configuration (width, height, positions)
            system_config: System configuration (x_display, window_class)
            on_exit_callback: Function to call when script exits
        """
        super().__init__()
        self.script_path = script_path
        self.display_config = display_config
        self.system_config = system_config
        self.on_exit_callback = on_exit_callback
        self.x_display = system_config.x_display
        self.monitor_thread = None
        self.script_name = os.path.basename(script_path)

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

        # Terminate processes using helper
        ProgramHelper.cleanup_processes(self.processes)

        # Force kill any processes spawned by the script
        # For doom.sh, this kills chocolate-doom processes
        # For other scripts, kills based on common process names
        try:
            # Kill chocolate-doom specifically (common case)
            subprocess.run(
                ["pkill", "-9", "chocolate-doom"],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        except:
            pass

        self.processes = []
        self.window_ids = []

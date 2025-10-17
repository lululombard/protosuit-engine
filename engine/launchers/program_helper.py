"""
Program Helper - Utilities for external program launchers
Provides common window management and process lifecycle functions
"""

import subprocess
import time
import threading
from typing import List, Optional, Callable


class ProgramHelper:
    """
    Static helper methods for managing external programs, windows, and processes
    """

    @staticmethod
    def position_window(
        window_id: str, x: int, y: int, width: int = None, height: int = None
    ):
        """
        Position a window using xdotool

        Args:
            window_id: Window ID (hex string from xdotool)
            x: X position
            y: Y position
            width: Optional width to resize to
            height: Optional height to resize to
        """
        try:
            # Move window
            subprocess.run(
                ["xdotool", "windowmove", window_id, str(x), str(y)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Resize if dimensions provided
            if width and height:
                subprocess.run(
                    ["xdotool", "windowsize", window_id, str(width), str(height)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            # Activate window (bring to front)
            subprocess.run(
                ["xdotool", "windowactivate", window_id],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            return True
        except Exception as e:
            print(f"[ProgramHelper] Error positioning window {window_id}: {e}")
            return False

    @staticmethod
    def find_windows(class_name: str, timeout: float = 5.0) -> List[str]:
        """
        Find windows by class name

        Args:
            class_name: Window class name to search for
            timeout: Maximum time to wait for windows to appear

        Returns:
            List of window IDs (hex strings)
        """
        start_time = time.time()
        windows = []

        while time.time() - start_time < timeout:
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--class", class_name],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode == 0 and result.stdout.strip():
                    windows = result.stdout.strip().split("\n")
                    if windows:
                        return windows
            except Exception as e:
                print(f"[ProgramHelper] Error finding windows: {e}")

            time.sleep(0.2)

        return []

    @staticmethod
    def monitor_process(
        process: subprocess.Popen, on_exit_callback: Optional[Callable] = None
    ) -> threading.Thread:
        """
        Monitor a process in a separate thread and call callback when it exits

        Args:
            process: Process to monitor
            on_exit_callback: Function to call when process exits

        Returns:
            Thread object (already started)
        """

        def monitor():
            process.wait()
            print(
                f"[ProgramHelper] Process {process.pid} exited with code {process.returncode}"
            )
            if on_exit_callback:
                try:
                    on_exit_callback()
                except Exception as e:
                    print(f"[ProgramHelper] Error in exit callback: {e}")

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def cleanup_processes(process_list: List[subprocess.Popen]):
        """
        Gracefully terminate a list of processes

        Args:
            process_list: List of Popen process objects
        """
        for process in process_list:
            if process and process.poll() is None:
                try:
                    print(f"[ProgramHelper] Terminating process {process.pid}")
                    process.terminate()
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    print(f"[ProgramHelper] Force killing process {process.pid}")
                    process.kill()
                    process.wait()
                except Exception as e:
                    print(f"[ProgramHelper] Error cleaning up process: {e}")

    @staticmethod
    def send_keys(window_id: str, keys: str):
        """
        Send keyboard input to a window

        Args:
            window_id: Window ID (hex string)
            keys: Keys to send (xdotool key format)
        """
        try:
            subprocess.run(
                ["xdotool", "key", "--window", window_id, keys],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            print(f"[ProgramHelper] Error sending keys to window {window_id}: {e}")
            return False

    @staticmethod
    def wait_for_window_count(
        class_name: str, expected_count: int, timeout: float = 10.0
    ) -> bool:
        """
        Wait until a specific number of windows with a given class exist

        Args:
            class_name: Window class name
            expected_count: Number of windows to wait for
            timeout: Maximum time to wait

        Returns:
            True if expected number of windows found, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            windows = ProgramHelper.find_windows(class_name, timeout=0.5)
            if len(windows) >= expected_count:
                return True
            time.sleep(0.2)

        return False

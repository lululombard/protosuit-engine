"""
Base Launcher - Abstract base class for game/emulator launchers
Provides common interface for launching external applications
"""

from abc import ABC, abstractmethod
from typing import List
import subprocess


class BaseLauncher(ABC):
    """
    Abstract base class for game and emulator launchers
    Subclasses implement specific launch logic for each game/emulator
    """

    def __init__(self):
        """Initialize launcher"""
        self.processes: List[subprocess.Popen] = []
        self.window_ids: List[str] = []

    @abstractmethod
    def launch(self) -> bool:
        """
        Launch the game/emulator

        Returns:
            True if launch successful, False otherwise
        """
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """
        Check if the game/emulator is currently running

        Returns:
            True if running, False otherwise
        """
        pass

    @abstractmethod
    def cleanup(self):
        """
        Clean up processes and resources
        Should be called when game exits or is terminated
        """
        pass

    def _position_window(self, window_id: str, x: int, y: int) -> bool:
        """
        Position a window using xdotool

        Args:
            window_id: X11 window ID
            x: X position in pixels
            y: Y position in pixels

        Returns:
            True if successful, False otherwise
        """
        try:
            subprocess.run(
                ["xdotool", "windowmove", window_id, str(x), str(y)],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                timeout=1,
            )
            return True
        except Exception as e:
            print(f"Failed to position window {window_id}: {e}")
            return False

    def _find_windows(self, window_name: str) -> List[str]:
        """
        Find windows by name using xdotool

        Args:
            window_name: Window name to search for

        Returns:
            List of window IDs
        """
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", window_name],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                window_ids = result.stdout.strip().split("\n")
                return [w for w in window_ids if w]
            return []
        except Exception as e:
            print(f"Failed to find windows '{window_name}': {e}")
            return []

    def _send_key(self, window_id: str, key: str) -> bool:
        """
        Send a key press to a window

        Args:
            window_id: X11 window ID
            key: Key to send (e.g., 'space', 'Return', 'Escape')

        Returns:
            True if successful, False otherwise
        """
        try:
            subprocess.run(
                ["xdotool", "key", "--window", window_id, key],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                timeout=1,
            )
            return True
        except Exception as e:
            print(f"Failed to send key '{key}' to window {window_id}: {e}")
            return False

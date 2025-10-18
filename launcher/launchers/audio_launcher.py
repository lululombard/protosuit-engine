"""
Audio Launcher - Launches ffplay for audio playback
"""

import subprocess
import time
import os
from typing import Callable, Optional
from launcher.launchers.base_launcher import BaseLauncher
from launcher.launchers.program_helper import ProgramHelper


class AudioLauncher(BaseLauncher):
    """
    Launcher for audio playback using ffplay
    Multiple audio files can stack/play simultaneously
    """

    def __init__(
        self,
        audio_path: str,
        system_config,
        on_exit_callback: Optional[Callable] = None,
    ):
        """
        Initialize Audio Launcher

        Args:
            audio_path: Full path to audio file to play
            system_config: System configuration (x_display)
            on_exit_callback: Function to call when audio exits
        """
        super().__init__()
        self.audio_path = audio_path
        self.system_config = system_config
        self.on_exit_callback = on_exit_callback
        self.x_display = system_config.x_display
        self.monitor_thread = None
        self._cleaned_up = False

    def launch(self) -> bool:
        """
        Launch ffplay for audio playback

        Returns:
            True if launch successful, False otherwise
        """
        try:
            # Check if audio file exists
            if not os.path.exists(self.audio_path):
                print(f"[AudioLauncher] Audio file not found: {self.audio_path}")
                return False

            env = os.environ.copy()
            env["DISPLAY"] = self.x_display

            # Audio playback using ffplay (allows stacking multiple audio files)
            ffplay_process = subprocess.Popen(
                [
                    "ffplay",
                    "-nodisp",  # No video window
                    "-autoexit",  # Exit when playback finishes
                    "-loglevel",
                    "quiet",  # Suppress output
                    self.audio_path,
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait a moment for process to start
            time.sleep(0.2)

            # Check if process is still running
            if ffplay_process.poll() is not None:
                print(
                    f"[AudioLauncher] Audio playback failed with code {ffplay_process.returncode}"
                )
                return False

            # Process is running
            self.processes.append(ffplay_process)
            print(
                f"[AudioLauncher] Started audio playback with ffplay (PID: {ffplay_process.pid})"
            )

            # Start monitoring for exit
            self.monitor_thread = ProgramHelper.monitor_process(
                ffplay_process, self._on_audio_exit
            )

            return True

        except Exception as e:
            print(f"[AudioLauncher] Failed to launch audio playback: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _on_audio_exit(self):
        """Callback when audio process exits"""
        if self._cleaned_up:
            return

        print("[AudioLauncher] Audio playback ended")
        time.sleep(0.5)

        # Cleanup
        self.cleanup()

        # Call user callback
        if self.on_exit_callback:
            self.on_exit_callback()

    def is_running(self) -> bool:
        """
        Check if audio is currently playing

        Returns:
            True if ffplay process is running, False otherwise
        """
        try:
            if self.processes:
                proc = self.processes[0]
                return proc.poll() is None
            return False
        except Exception:
            return False

    def cleanup(self):
        """Clean up audio processes"""
        if self._cleaned_up:
            return
        self._cleaned_up = True

        print("[AudioLauncher] Cleaning up audio launcher...")

        # Terminate our tracked processes using helper
        ProgramHelper.cleanup_processes(self.processes)

        self.processes = []
        self.window_ids = []

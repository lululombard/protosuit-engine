"""
Video Launcher - Launches mpv for video playback
"""

import subprocess
import time
import os
from typing import Callable, Optional
from launcher.launchers.base_launcher import BaseLauncher
from launcher.launchers.program_helper import ProgramHelper


class VideoLauncher(BaseLauncher):
    """
    Launcher for video playback using mpv
    Only one video visible at a time (kills previous video)
    """

    def __init__(
        self,
        video_path: str,
        display_config,
        system_config,
        on_exit_callback: Optional[Callable] = None,
    ):
        """
        Initialize Video Launcher

        Args:
            video_path: Full path to video file to play
            display_config: Display configuration (width, height, positions)
            system_config: System configuration (x_display)
            on_exit_callback: Function to call when video exits
        """
        super().__init__()
        self.video_path = video_path
        self.display_config = display_config
        self.system_config = system_config
        self.on_exit_callback = on_exit_callback
        self.x_display = system_config.x_display
        self.monitor_thread = None
        self._cleaned_up = False

    def launch(self) -> bool:
        """
        Launch mpv for video playback on dual displays

        Returns:
            True if launch successful, False otherwise
        """
        try:
            # Check if video file exists
            if not os.path.exists(self.video_path):
                print(f"[VideoLauncher] Video file not found: {self.video_path}")
                return False

            env = os.environ.copy()
            env["DISPLAY"] = self.x_display

            # Calculate total width (both displays side by side)
            total_width = self.display_config.width * 2
            total_height = self.display_config.height

            mpv_process = subprocess.Popen(
                [
                    "mpv",
                    "--ao=alsa",
                    "--no-osc",
                    "--no-osd-bar",
                    f"--geometry={total_width}x{total_height}+{self.display_config.left_x}+{self.display_config.y}",
                    f"--autofit={total_width}x{total_height}",
                    "--really-quiet",
                    "--external-file="
                    + self.video_path,  # Load same video as external file
                    "--lavfi-complex=[vid1][vid2]hstack[vo]",  # Stack horizontally
                    self.video_path,
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait for process to start
            time.sleep(1)

            # Check if process is still running
            if mpv_process.poll() is not None:
                stdout, stderr = mpv_process.communicate()
                print(
                    f"[VideoLauncher] Video playback failed with code {mpv_process.returncode}"
                )
                if stderr:
                    print(f"[VideoLauncher] mpv stderr: {stderr.decode()}")
                return False

            # Process is running
            self.processes.append(mpv_process)
            print(
                f"[VideoLauncher] Started video playback on dual displays (PID: {mpv_process.pid})"
            )

            # Start monitoring for exit
            self.monitor_thread = ProgramHelper.monitor_process(
                mpv_process, self._on_video_exit
            )

            return True

        except Exception as e:
            print(f"[VideoLauncher] Failed to launch video playback: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _on_video_exit(self):
        """Callback when video process exits"""
        if self._cleaned_up:
            return

        print("[VideoLauncher] Video playback ended")
        time.sleep(0.5)

        # Cleanup
        self.cleanup()

        # Call user callback
        if self.on_exit_callback:
            self.on_exit_callback()

    def is_running(self) -> bool:
        """
        Check if video is currently playing

        Returns:
            True if mpv process is running, False otherwise
        """
        try:
            if self.processes:
                proc = self.processes[0]
                return proc.poll() is None
            return False
        except Exception:
            return False

    def cleanup(self):
        """Clean up video processes"""
        if self._cleaned_up:
            return
        self._cleaned_up = True

        print("[VideoLauncher] Cleaning up video launcher...")

        # Terminate our tracked processes using helper
        ProgramHelper.cleanup_processes(self.processes)

        # Kill ALL mpv processes (only for video)
        try:
            subprocess.run(
                ["pkill", "-9", "mpv"],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        except:
            pass

        self.processes = []
        self.window_ids = []

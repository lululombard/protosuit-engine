"""
Media Launcher - Launches mpv for audio/video playback
Detects media type and routes to appropriate playback method
"""

import subprocess
import time
import os
from typing import Callable, Optional
from engine.launchers.base_launcher import BaseLauncher
from engine.launchers.program_helper import ProgramHelper
from config.loader import ConfigLoader


class MediaLauncher(BaseLauncher):
    """
    Launcher for media playback
    - Audio: Uses ffplay (allows stacking multiple audio files)
    - Video: Uses mpv (only one video visible at a time)
    """

    # Audio extensions
    AUDIO_EXTENSIONS = {
        ".mp3",
        ".wav",
        ".ogg",
        ".flac",
        ".m4a",
        ".aac",
        ".wma",
        ".opus",
    }

    # Video extensions
    VIDEO_EXTENSIONS = {
        ".mp4",
        ".mkv",
        ".avi",
        ".webm",
        ".mov",
        ".flv",
        ".wmv",
        ".m4v",
        ".mpeg",
        ".mpg",
    }

    def __init__(
        self,
        media_path: str,
        display_config,
        system_config,
        on_exit_callback: Optional[Callable] = None,
    ):
        """
        Initialize Media Launcher

        Args:
            media_path: Path to media file to play (relative to media base_path)
            display_config: Display configuration (width, height, positions)
            system_config: System configuration (x_display, window_class)
            on_exit_callback: Function to call when media exits
        """
        super().__init__()
        self.media_config = ConfigLoader().get_media_config()
        self.media_path = os.path.join(self.media_config.base_path, media_path)
        self.display_config = display_config
        self.system_config = system_config
        self.on_exit_callback = on_exit_callback
        self.x_display = system_config.x_display
        self.monitor_thread = None
        self._cleaned_up = False  # Flag to prevent double-cleanup
        self.media_type = None  # Track what type of media this launcher is handling

    def _detect_media_type(self) -> str:
        """
        Detect media type based on file extension

        Returns:
            'audio', 'video', or 'unknown'
        """
        _, ext = os.path.splitext(self.media_path.lower())

        if ext in self.AUDIO_EXTENSIONS:
            return "audio"
        elif ext in self.VIDEO_EXTENSIONS:
            return "video"
        else:
            return "unknown"

    def launch(self) -> bool:
        """
        Launch mpv with appropriate playback method based on media type

        Returns:
            True if launch successful, False otherwise
        """
        try:
            # Check if media file exists
            if not os.path.exists(self.media_path):
                print(f"Media file not found: {self.media_path}")
                return False

            # Detect media type
            self.media_type = self._detect_media_type()
            print(f"Detected media type: {self.media_type}")

            if self.media_type == "audio":
                return self.play_audio()
            elif self.media_type == "video":
                return self.play_video()
            else:
                print(f"Unknown media type for file: {self.media_path}")
                return False

        except Exception as e:
            print(f"Failed to launch media: {e}")
            import traceback

            traceback.print_exc()
            self.cleanup()
            return False

    def play_audio(self) -> bool:
        """
        Play audio file using ffplay - allows multiple audio files to stack
        No video window, shader stays visible

        Returns:
            True if launch successful, False otherwise
        """
        try:
            env = os.environ.copy()
            env["DISPLAY"] = self.x_display

            # Audio playback using ffplay (allows stacking multiple audio files)
            ffplay_process = subprocess.Popen(
                [
                    "ffplay",
                    "-nodisp",  # No video window
                    "-autoexit",  # Exit when playback finishes
                    "-loglevel", "quiet",  # Suppress output
                    self.media_path,
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait a moment for process to start
            time.sleep(0.2)

            # Check if process is still running
            if ffplay_process.poll() is not None:
                print(f"Audio playback failed with code {ffplay_process.returncode}")
                return False

            # Process is running
            self.processes.append(ffplay_process)
            print(f"Started audio playback with ffplay (PID: {ffplay_process.pid})")

            # Start monitoring for exit
            self.monitor_thread = ProgramHelper.monitor_process(
                ffplay_process, self._on_media_exit
            )

            return True

        except Exception as e:
            print(f"Failed to launch audio playback: {e}")
            import traceback

            traceback.print_exc()
            return False

    def play_video(self) -> bool:
        """
        Play video file on dual displays using mpv with lavfi-complex
        Note: display_manager cleans up old launcher before creating new one

        Returns:
            True if launch successful, False otherwise
        """
        try:
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
                    + self.media_path,  # Load same video as external file
                    "--lavfi-complex=[vid1][vid2]hstack[vo]",  # Stack horizontally
                    self.media_path,
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
                print(f"Video playback failed with code {mpv_process.returncode}")
                if stderr:
                    print(f"mpv stderr: {stderr.decode()}")
                return False

            # Process is running
            self.processes.append(mpv_process)
            print(f"Started video playback on dual displays (PID: {mpv_process.pid})")

            # Start monitoring for exit
            self.monitor_thread = ProgramHelper.monitor_process(
                mpv_process, self._on_media_exit
            )

            return True

        except Exception as e:
            print(f"Failed to launch video playback: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _on_media_exit(self):
        """Callback when media process exits"""
        # Check if already cleaned up (prevents race condition)
        if self._cleaned_up:
            return

        print("Media playback ended")
        time.sleep(0.5)

        # Cleanup
        self.cleanup()

        # Call user callback
        if self.on_exit_callback:
            self.on_exit_callback()

    def is_running(self) -> bool:
        """
        Check if mpv is currently running

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
        """Clean up media processes"""
        # Prevent double-cleanup
        if self._cleaned_up:
            return
        self._cleaned_up = True

        print("Cleaning up media launcher...")

        # Terminate our tracked processes using helper
        ProgramHelper.cleanup_processes(self.processes)

        # Only kill ALL mpv processes if this launcher is handling video
        # Audio (ffplay) processes are not affected
        if self.media_type == "video":
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

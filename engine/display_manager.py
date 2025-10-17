"""
Display Manager - Main orchestrator for base/overlay animation system
Manages shader rendering, media playback, and game launching
"""

import subprocess
import time
import os
import traceback
from typing import Optional
from config.loader import ConfigLoader
from engine.launchers.doom_launcher import DoomLauncher
from engine.launchers.media_launcher import MediaLauncher


class DisplayManager:
    """
    Main display manager with base/overlay state management
    Coordinates shader rendering, media playback, and game launching
    """

    def __init__(self):
        """Initialize display manager"""
        # Load configuration
        self.config_loader = ConfigLoader()
        if not self.config_loader.validate():
            print("Warning: Config validation failed, some features may not work")

        # State tracking
        self.current_base: Optional[str] = None  # Current base animation name
        self.previous_base: Optional[str] = (
            None  # Base animation before launching program
        )
        self.uniform_state = {}  # Track current uniform values for state sync

        # Processes for non-shader content (videos, images)
        self.current_processes = []

        # Shader directory
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.shader_dir = os.path.join(project_root, "assets", "shaders")

        # Game launchers
        self.doom_launcher: Optional[DoomLauncher] = None
        self.media_launcher: Optional[MediaLauncher] = None
        self.game_exiting = False  # Flag to prevent double exit calls
        self.overlay_exiting = False  # Flag for media exit

    def set_base_animation(
        self, name: str, store_previous: bool = True, mqtt_client=None
    ):
        """
        Set the base (persistent) animation

        Args:
            name: Animation name from config
            store_previous: Whether to store current base as previous (default: True)
            mqtt_client: Optional MQTT client for publishing updates
        """
        print(f"Setting base animation: {name}")

        # Store previous base (unless explicitly disabled)
        if store_previous and self.current_base and self.current_base != name:
            self.previous_base = self.current_base
            print(f"Stored previous base: {self.previous_base}")

        self.current_base = name

        # Show the base animation immediately
        self._show_animation(name, mqtt_client)

    def _show_animation(self, animation_name: str, mqtt_client=None):
        """
        Internal method to show an animation (base or overlay)

        Args:
            animation_name: Animation name from config
            mqtt_client: Optional MQTT client for publishing updates
        """
        # Get animation config
        anim_config = self.config_loader.get_animation(animation_name)
        if not anim_config:
            # Fall back to default
            default = self.config_loader.get_default_animation()
            print(f"Animation '{animation_name}' not found, using {default}")
            anim_config = self.config_loader.get_animation(default)
            animation_name = default

        anim_type = anim_config.get("type", "base")

        if anim_type == "base":
            # Shader-based animation
            self._show_shader_animation(animation_name, anim_config, mqtt_client)
        else:
            # Only base animations are supported
            print(f"Animation type '{anim_type}' not supported, using base animation")
            self._show_shader_animation(animation_name, anim_config, mqtt_client)

    def _show_shader_animation(
        self, animation_name: str, anim_config: dict, mqtt_client=None
    ):
        """Show a shader-based animation"""
        # Clean up any non-shader processes
        self.cleanup_processes()

        # Get shader files
        left_shader = anim_config["left_shader"]
        right_shader = anim_config["right_shader"]

        # Get transition duration
        transition_config = self.config_loader.get_transition_config()
        transition_duration = transition_config.duration

        # Load shaders
        left_shader_path = os.path.join(self.shader_dir, left_shader)
        right_shader_path = os.path.join(self.shader_dir, right_shader)

        try:
            with open(left_shader_path, "r") as f:
                left_shader_source = f.read()
            with open(right_shader_path, "r") as f:
                right_shader_source = f.read()

            # Get render scale if specified (default to 1.0)
            render_scale = anim_config.get("render_scale", 1.0)

            # Send shaders to renderer via MQTT
            # Format: display:duration:scale:shader_source
            if mqtt_client:
                mqtt_client.publish(
                    "protogen/renderer/shader",
                    f"left:{transition_duration}:{render_scale}:{left_shader_source}",
                )
                mqtt_client.publish(
                    "protogen/renderer/shader",
                    f"right:{transition_duration}:{render_scale}:{right_shader_source}",
                )

            # Apply uniforms from config
            uniforms = anim_config.get("uniforms", {})
            for uniform_name, uniform_config in uniforms.items():
                # Support per-display or both displays
                if "left" in uniform_config or "right" in uniform_config:
                    # Per-display configuration
                    if "left" in uniform_config:
                        self._set_uniform_from_config(
                            0, uniform_name, uniform_config["left"], mqtt_client
                        )
                    if "right" in uniform_config:
                        self._set_uniform_from_config(
                            1, uniform_name, uniform_config["right"], mqtt_client
                        )
                else:
                    # Both displays get the same value
                    self._set_uniform_from_config(
                        -1, uniform_name, uniform_config, mqtt_client
                    )

            print(f"Showing shader animation: {animation_name}")

            # Publish current animation to MQTT
            if mqtt_client:
                mqtt_client.publish(
                    "protogen/fins/current_animation", animation_name, retain=True
                )
        except Exception as e:
            print(f"Error loading shaders: {e}")
            traceback.print_exc()

    def _set_uniform_from_config(
        self, display_idx: int, uniform_name: str, config: dict, mqtt_client=None
    ):
        """Helper to set a uniform from config values"""
        try:
            uniform_type = config.get("type", "float")
            value = config.get("value")

            if value is not None:
                self.set_uniform(
                    uniform_name, uniform_type, value, display_idx, mqtt_client
                )
        except Exception as e:
            print(f"Error setting uniform {uniform_name}: {e}")

    def set_uniform(
        self,
        uniform_name: str,
        uniform_type: str,
        value,
        display: str = "both",
        mqtt_client=None,
    ):
        """
        Set a uniform value on the renderer

        Args:
            uniform_name: Name of the uniform
            uniform_type: Type (float, vec2, vec3, vec4)
            value: Value to set
            display: 'left', 'right', 'both', or display index (-1, 0, 1)
            mqtt_client: Optional MQTT client for publishing
        """
        # Convert display_idx to display name
        if isinstance(display, int):
            if display == -1:
                display = "both"
            elif display == 0:
                display = "left"
            elif display == 1:
                display = "right"

        # Track uniform state
        if uniform_name not in self.uniform_state:
            self.uniform_state[uniform_name] = {}
        self.uniform_state[uniform_name] = {
            "type": uniform_type,
            "value": value,
            "display": display,
        }

        # Format value for MQTT (convert lists/tuples to space-separated string)
        if isinstance(value, (list, tuple)):
            value_str = " ".join(str(v) for v in value)
        else:
            value_str = str(value)

        # Send to renderer via MQTT
        # Format: display:name:type:value
        if mqtt_client:
            mqtt_client.publish(
                "protogen/renderer/uniform",
                f"{display}:{uniform_name}:{uniform_type}:{value_str}",
            )

    def get_uniform_state(self):
        """Get current uniform state for state sync"""
        return self.uniform_state

    def play_media(self, media_path: str, fade_to_blank: bool = None):
        """
        Play a media file on both displays

        Args:
            media_path: Path to media file to play
            fade_to_blank: If True, switches to blank shader before playing media.
                          If False, plays media over current shader animation.
                          If None, uses configuration default.
        """
        # Detect the type of new media we're about to play
        _, ext = os.path.splitext(media_path.lower())
        from engine.launchers.media_launcher import MediaLauncher
        is_new_video = ext in MediaLauncher.VIDEO_EXTENSIONS

        # Only cleanup existing launcher if we're starting a new video
        # Audio can stack, so we keep video running when starting audio
        if self.media_launcher and is_new_video:
            print("Stopping existing media playback (new video starting)...")
            self.media_launcher.cleanup()
            self.media_launcher = None
            # Give processes time to fully terminate
            time.sleep(0.5)

        # Use configuration default if not specified
        if fade_to_blank is None:
            media_config = self.config_loader.get_media_config()
            fade_to_blank = media_config.fade_to_blank
        # Optionally switch to blank shader for minimal overhead during media playback
        if fade_to_blank and self.current_base != "blank":
            print(
                f"Switching to 'blank' shader for minimal overhead (was: {self.current_base})"
            )
            self.set_base_animation("blank")
        elif not fade_to_blank:
            print(f"Playing media over current shader animation: {self.current_base}")

        # Get system and display configs
        display_config = self.config_loader.get_display_config()
        system_config = self.config_loader.get_system_config()

        # Create media launcher with exit callback
        media_launcher = MediaLauncher(
            media_path,
            display_config,
            system_config,
            on_exit_callback=self._on_media_exit if is_new_video else None,
        )

        # Launch
        if media_launcher.launch():
            print(f"Media playback started: {media_path}")
            # Only track video launchers - audio launchers auto-cleanup and can stack
            if is_new_video:
                self.media_launcher = media_launcher
        else:
            print(f"Failed to start media playback: {media_path}")
            if is_new_video:
                self.media_launcher = None

    def launch_program(self, program_name: str):
        """
        Launch an external program (game, app, etc.)

        Pattern: Automatically switches to 'blank' shader for minimal overhead,
        then launches the program. When the program exits, it returns to whatever
        base animation was active before.

        Args:
            program_name: Name of program to launch (e.g., 'doom')
        """
        if program_name == "doom":
            # Switch to blank shader for minimal overhead during external programs
            # Store current base so we can restore it when program exits
            if self.current_base != "blank":
                print(
                    f"Switching to 'blank' shader for minimal overhead (was: {self.current_base})"
                )
                self.set_base_animation("blank")

            # Get Doom config
            doom_config = self.config_loader.get_game_config("doom")
            if not doom_config or not doom_config.enabled:
                print("Doom is not enabled in config")
                return

            # Create launcher with exit callback
            display_config = self.config_loader.get_display_config()
            system_config = self.config_loader.get_system_config()
            self.doom_launcher = DoomLauncher(
                doom_config,
                display_config,
                system_config,
                on_exit_callback=self._on_game_exit,
            )

            # Launch
            if self.doom_launcher.launch():
                pass  # Doom is running, launcher tracks the state
            else:
                self.doom_launcher = None
        else:
            print(f"Unknown program: {program_name}")

    def stop_overlay(self):
        """
        Stop any currently running external program/game
        """
        print("Stopping external program...")

        # Cleanup doom launcher if running
        if self.doom_launcher:
            self.doom_launcher.cleanup()
            self.doom_launcher = None

        # Cleanup media launcher if running
        if self.media_launcher:
            self.media_launcher.cleanup()
            self.media_launcher = None

        # Trigger the exit callback to restore default animation
        self._on_game_exit()

    def _on_game_exit(self):
        """
        Callback when external program (game, app) exits
        Returns to the default animation
        """
        # Prevent double-calls (from both manual stop and monitor thread)
        if self.game_exiting:
            print("Game exit already in progress, skipping duplicate call")
            return

        self.game_exiting = True
        print("External program exited, returning to default animation")

        # Always return to default animation
        default = self.config_loader.get_default_animation()
        if self.current_base != default:
            print(f"Returning to default: {default}")
            self.set_base_animation(default, store_previous=False)
            self.previous_base = None

        # Reset flag after completion (ready for next game launch)
        self.game_exiting = False

    def _on_media_exit(self):
        """
        Callback when media playback exits
        Returns to the default animation (only if not already on blank)
        """
        # Prevent double-calls (from both manual stop and monitor thread)
        if self.overlay_exiting:
            print("Media exit already in progress, skipping duplicate call")
            return

        self.overlay_exiting = True
        print("Media playback exited")

        # Reset flag after completion (ready for next media launch)
        self.overlay_exiting = False

    def cleanup_processes(self):
        """Kill all non-shader display processes"""
        for proc in self.current_processes:
            try:
                proc.terminate()
            except:
                pass
        self.current_processes = []

        # Force kill mpv and feh
        try:
            for cmd in ["mpv", "feh"]:
                subprocess.run(
                    ["pkill", "-9", cmd],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
                subprocess.run(
                    ["killall", "-9", cmd],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
        except:
            pass

    def cleanup(self):
        """Clean up all resources"""
        print("Cleaning up display manager...")

        # Cleanup processes
        self.cleanup_processes()

        # Cleanup game launcher
        if self.doom_launcher:
            self.doom_launcher.cleanup()

        # Cleanup media launcher
        if self.media_launcher:
            self.media_launcher.cleanup()

        print("Display manager cleanup complete")

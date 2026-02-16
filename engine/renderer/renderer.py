#!/usr/bin/env python3
"""
Renderer - MQTT-controlled renderer for dual displays
Consolidates left and right displays into a single process
"""
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import moderngl
import numpy as np
import time
import pygame
import paho.mqtt.client as mqtt
import json
import tempfile
from utils.mqtt_client import create_mqtt_client
from renderer.shader_compiler import (
    compile_shader,
    create_blend_shader,
    create_framebuffers,
)
from renderer.audio_capture import AudioCapture


class Renderer:
    """
    Shader renderer that handles both displays in a single process
    Controlled via MQTT for shader changes, uniform updates, and commands
    """

    def __init__(self):
        self.running = True

        # Load configuration
        from config.loader import ConfigLoader

        self.config_loader = ConfigLoader()
        display_config = self.config_loader.get_display_config()
        monitoring_config = self.config_loader.get_monitoring_config()
        transition_config = self.config_loader.get_transition_config()
        mqtt_config = self.config_loader.get_mqtt_config()

        # Display configuration
        self.display_width = display_config.width
        self.display_height = display_config.height
        self.left_x = display_config.left_x
        self.right_x = display_config.right_x
        self.display_y = display_config.y

        # Total window size (both displays side by side)
        self.total_width = self.display_width * 2
        self.total_height = self.display_height

        # Shader state for each display
        self.shaders = {
            "left": {
                "current": None,
                "current_name": None,  # Track shader name for status publishing
                "target": None,
                "target_name": None,
                "transition_start": None,
                "transition_duration": transition_config.duration,
                "pending": None,
                "queued": None,  # Queued shader waiting for current transition to finish
                "render_scale": 1.0,
                "pending_scale": None,
                "scale_changing": False,
                "scale_change_frame_count": 0,
                "uniforms": {},  # Custom uniforms for this display
            },
            "right": {
                "current": None,
                "current_name": None,
                "target": None,
                "target_name": None,
                "transition_start": None,
                "transition_duration": transition_config.duration,
                "pending": None,
                "queued": None,  # Queued shader waiting for current transition to finish
                "render_scale": 1.0,
                "pending_scale": None,
                "scale_changing": False,
                "scale_change_frame_count": 0,
                "uniforms": {},
            },
        }

        # Blur configuration
        self.blur_enabled = transition_config.blur.enabled
        self.blur_strength = transition_config.blur.strength

        # FPS monitoring
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.current_fps = 0.0
        self.fps_publish_interval = monitoring_config.fps_publish_interval
        self.fps_smoothing_frames = monitoring_config.fps_smoothing_frames
        self.monitoring_enabled = monitoring_config.enabled
        self.last_fps_publish = time.time()
        self.fps_history = []

        # OpenGL objects
        self.ctx = None
        self.fbos = {"left": [], "right": []}
        self.blend_program = None
        self.blend_vao = None
        self.audio_texture = None

        # Audio capture for FFT shaders
        self.audio_capture = AudioCapture()

        # MQTT
        self.mqtt_client = None

        # Command queue for thread-safe OpenGL operations
        from queue import Queue

        self.command_queue = Queue()

        # Performance optimization: track if executable or video is running
        self.exec_running = False
        self.video_running = False

        # Shader directory and available shaders
        self.shader_dir = os.path.join(os.getcwd(), "assets", "shaders")
        self.available_shaders = []
        self.shader_metadata = {}  # Store animation configs for each shader

        print("Renderer initialized")
        print(
            f"Display config: {self.display_width}x{self.display_height} @ ({self.left_x}, {self.right_x})"
        )

    def _mqtt_subscribe_all(self):
        """Subscribe to all MQTT topics (called on connect and reconnect)"""
        self.mqtt_client.subscribe("protogen/fins/renderer/set/shader/file")
        self.mqtt_client.subscribe("protogen/fins/renderer/set/shader/uniform")
        self.mqtt_client.subscribe("protogen/fins/renderer/config/reload")
        self.mqtt_client.subscribe("protogen/fins/config/reload")
        self.mqtt_client.subscribe("protogen/fins/launcher/status/exec")
        self.mqtt_client.subscribe("protogen/fins/launcher/status/video")

    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT (re)connection — re-subscribe to all topics"""
        print(f"[Renderer] MQTT connected (reason={reason_code}), subscribing to topics")
        self._mqtt_subscribe_all()

    def init_mqtt(self):
        """Initialize MQTT client for control and status"""
        try:
            self.mqtt_client = create_mqtt_client(self.config_loader)
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_message = self.on_mqtt_message

            # Subscribe to control and status topics
            self._mqtt_subscribe_all()

            self.mqtt_client.loop_start()

            # Scan available shaders
            self.scan_shaders()

            # Publish initial status
            self.publish_shader_status()
            # Note: Uniform status will be published after default shader loads

            print("[Renderer] MQTT client initialized")
            print("[Renderer] Subscribed to:")
            print("  - protogen/fins/renderer/set/shader/file")
            print("  - protogen/fins/renderer/set/shader/uniform")
            print("  - protogen/fins/renderer/config/reload")
            print("  - protogen/fins/launcher/status/exec (performance optimization)")
            print("  - protogen/fins/launcher/status/video (performance optimization)")
            print(f"[Renderer] Found {len(self.available_shaders)} shaders")

        except Exception as e:
            print(f"[Renderer] Failed to initialize MQTT client: {e}")
            self.mqtt_client = None

    def on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8")

            if topic == "protogen/fins/renderer/set/shader/file":
                self.handle_shader_command(payload)
            elif topic == "protogen/fins/renderer/set/shader/uniform":
                self.handle_uniform_command(payload)
            elif topic in ("protogen/fins/renderer/config/reload", "protogen/fins/config/reload"):
                self.handle_control_command("reload_config")
            elif topic == "protogen/fins/launcher/status/exec":
                self.handle_exec_status(payload)
            elif topic == "protogen/fins/launcher/status/video":
                self.handle_video_status(payload)

        except Exception as e:
            print(f"[Renderer] Error handling MQTT message: {e}")
            import traceback

            traceback.print_exc()

    def handle_exec_status(self, payload: str):
        """Handle launcher exec status updates for performance optimization"""
        try:
            data = json.loads(payload)
            # Check if any executable is running
            self.exec_running = data.get("running") is not None and data.get("running") != ""

            if self.exec_running:
                print(f"[Renderer] Executable running: {data.get('running')} - Skipping shader rendering for performance")
            else:
                print("[Renderer] No executable running - Resuming shader rendering")

        except Exception as e:
            print(f"[Renderer] Error handling exec status: {e}")

    def handle_video_status(self, payload: str):
        """Handle launcher video status updates for performance optimization"""
        try:
            data = json.loads(payload)
            # Check if any video is playing
            self.video_running = data.get("playing") is not None and data.get("playing") != ""

            if self.video_running:
                print(f"[Renderer] Video playing: {data.get('playing')} - Skipping shader rendering for performance")
            else:
                print("[Renderer] No video playing - Resuming shader rendering")

        except Exception as e:
            print(f"[Renderer] Error handling video status: {e}")

    def handle_shader_command(self, payload: str):
        """Handle shader change command (queues for main thread)

        Format: JSON {"display": "left"|"right"|"both", "name": "stars", "transition_duration": 0.75}
        """
        try:
            data = json.loads(payload)
            display = data["display"]
            anim_name = data["name"]

            # Get animation metadata from config
            if anim_name not in self.shader_metadata:
                print(f"[Renderer] Animation '{anim_name}' not found in config")
                return

            metadata = self.shader_metadata[anim_name]

            # Get transition duration
            duration = data.get(
                "transition_duration",
                self.shaders[display if display != "both" else "left"][
                    "transition_duration"
                ],
            )

            # Get render scale from config or data
            scale = data.get("scale", metadata.get("render_scale", 1.0))

            # Load shader files for left and/or right displays
            if display == "both":
                displays_to_load = ["left", "right"]
            else:
                displays_to_load = [display]

            for disp in displays_to_load:
                shader_file = metadata.get(f"{disp}_shader")
                if not shader_file:
                    print(f"[Renderer] No {disp} shader defined for '{anim_name}'")
                    continue

                shader_path = os.path.join(self.shader_dir, shader_file)
                if not os.path.exists(shader_path):
                    print(f"[Renderer] Shader file not found: {shader_path}")
                    continue

                with open(shader_path, "r") as f:
                    shader_source = f.read()

                # Queue shader load command
                self.command_queue.put(
                    ("shader", disp, shader_source, duration, scale, anim_name)
                )
                print(f"[Renderer] Loaded shader '{shader_file}' for {disp}")

            # Apply default uniforms from config
            uniforms = metadata.get("uniforms", {})
            for uniform_name, uniform_config in uniforms.items():
                # Check if per-display or both
                if isinstance(uniform_config, dict) and (
                    "left" in uniform_config or "right" in uniform_config
                ):
                    # Per-display uniforms
                    for disp in displays_to_load:
                        if disp in uniform_config:
                            self._apply_uniform(
                                disp, uniform_name, uniform_config[disp]
                            )
                else:
                    # Both displays
                    for disp in displays_to_load:
                        self._apply_uniform(disp, uniform_name, uniform_config)

            # Note: Status will be published when shader transition completes

        except Exception as e:
            print(f"[Renderer] Error handling shader command: {e}")
            import traceback

            traceback.print_exc()

    def _apply_uniform(self, display: str, uniform_name: str, uniform_config: dict):
        """Apply a uniform value to a display"""
        try:
            uniform_type = uniform_config.get("type")
            value = uniform_config.get("value")

            if value is None:
                return

            # Convert list to tuple for OpenGL
            if isinstance(value, list):
                value = tuple(value)

            self.shaders[display]["uniforms"][uniform_name] = value
            print(
                f"[Renderer] Set default uniform '{uniform_name}' = {value} on {display}"
            )

        except Exception as e:
            print(f"[Renderer] Error applying uniform '{uniform_name}': {e}")

    def handle_uniform_command(self, payload: str):
        """Handle uniform update command

        Format: JSON {"display": "left"|"right"|"both", "name": "speed", "type": "float", "value": 2.5}
        """
        try:
            data = json.loads(payload)
            display = data["display"]
            uniform_name = data["name"]
            uniform_type = data["type"]
            value = data["value"]

            # Parse value based on type
            if uniform_type == "float":
                value = float(value)
            elif uniform_type == "int":
                value = int(value)
            elif uniform_type in ["vec2", "vec3", "vec4"]:
                # Ensure it's a tuple for OpenGL
                if isinstance(value, list):
                    value = tuple(value)
                elif isinstance(value, str):
                    # Handle space or comma-separated strings
                    value = tuple(
                        float(x.strip()) for x in value.replace(",", " ").split()
                    )
            else:
                print(f"[Renderer] Unknown uniform type: {uniform_type}")
                return

            if display in ["left", "right"]:
                self.shaders[display]["uniforms"][uniform_name] = value
            elif display == "both":
                self.shaders["left"]["uniforms"][uniform_name] = value
                self.shaders["right"]["uniforms"][uniform_name] = value

            print(f"[Renderer] Set uniform '{uniform_name}' = {value} on {display}")

            # Publish updated uniform status
            self.publish_uniform_status()

        except Exception as e:
            print(f"[Renderer] Error handling uniform command: {e}")
            import traceback

            traceback.print_exc()

    def handle_control_command(self, payload: str):
        """Handle control commands (quit, reload, etc.)"""
        if payload == "quit":
            print("[Renderer] Received quit command")
            self.running = False
        elif payload == "reload_config":
            print("[Renderer] Reloading configuration...")
            self.reload_config()
        else:
            print(f"[Renderer] Unknown command: {payload}")

    def reload_config(self):
        """Reload configuration from file"""
        try:
            self.config_loader = ConfigLoader()
            transition_config = self.config_loader.get_transition_config()
            self.blur_enabled = transition_config.blur.enabled
            self.blur_strength = transition_config.blur.strength
            self.scan_shaders()
            self.publish_shader_status()
            self.publish_uniform_status()
            print("[Renderer] Configuration reloaded")
        except Exception as e:
            print(f"[Renderer] Error reloading config: {e}")

    def publish_fps_data(self):
        """Publish FPS data to MQTT"""
        if not self.monitoring_enabled or not self.mqtt_client:
            return

        try:
            current_time = time.time()
            elapsed = current_time - self.fps_start_time
            if elapsed > 0:
                instant_fps = self.fps_counter / elapsed
                self.fps_history.append(instant_fps)

                if len(self.fps_history) > self.fps_smoothing_frames:
                    self.fps_history.pop(0)

                self.current_fps = sum(self.fps_history) / len(self.fps_history)

            fps_data = {
                "fps": round(self.current_fps, 1),
                "timestamp": current_time,
                "displays": {
                    "left": {
                        "resolution": {
                            "width": int(
                                self.display_width
                                * self.shaders["left"]["render_scale"]
                            ),
                            "height": int(
                                self.display_height
                                * self.shaders["left"]["render_scale"]
                            ),
                        },
                        "scale": self.shaders["left"]["render_scale"],
                    },
                    "right": {
                        "resolution": {
                            "width": int(
                                self.display_width
                                * self.shaders["right"]["render_scale"]
                            ),
                            "height": int(
                                self.display_height
                                * self.shaders["right"]["render_scale"]
                            ),
                        },
                        "scale": self.shaders["right"]["render_scale"],
                    },
                },
            }

            self.mqtt_client.publish(
                "protogen/fins/renderer/status/performance",
                json.dumps(fps_data),
                retain=True,
            )

            # Reset counters
            self.fps_counter = 0
            self.fps_start_time = current_time
            self.last_fps_publish = current_time

        except Exception as e:
            print(f"[Renderer] Error publishing FPS data: {e}")

    def scan_shaders(self):
        """Load shaders from config with their metadata"""
        try:
            # Get animations from config
            animations = self.config_loader.config.get("animations", {})

            self.available_shaders = []
            self.shader_metadata = {}

            for anim_name, anim_config in animations.items():
                # Store metadata for this animation
                self.shader_metadata[anim_name] = {
                    "name": anim_config.get("name", anim_name),
                    "emoji": anim_config.get("emoji", ""),
                    "type": anim_config.get("type", "base"),
                    "left_shader": anim_config.get("left_shader"),
                    "right_shader": anim_config.get("right_shader"),
                    "uniforms": anim_config.get("uniforms", {}),
                    "render_scale": anim_config.get("render_scale", 1.0),
                }
                self.available_shaders.append(anim_name)

            self.available_shaders.sort()
            print(
                f"[Renderer] Loaded {len(self.available_shaders)} animations from config: {', '.join(self.available_shaders)}"
            )

        except Exception as e:
            print(f"[Renderer] Error loading animations: {e}")
            import traceback

            traceback.print_exc()

    def publish_shader_status(self):
        """Publish current shader status to MQTT"""
        if not self.mqtt_client:
            return

        try:
            # Build animations list with metadata
            animations_list = []
            for shader_name in self.available_shaders:
                metadata = self.shader_metadata.get(shader_name, {})
                animation_info = {
                    "id": shader_name,
                    "name": metadata.get("name", shader_name.replace("_", " ").title()),
                    "emoji": metadata.get("emoji", ""),
                    "type": metadata.get("type", "base"),
                    "uniforms": [],
                }

                # Add uniform metadata if available
                if "uniforms" in metadata:
                    for uniform_name, uniform_config in metadata["uniforms"].items():
                        # Check if this is a per-display uniform (has left/right keys)
                        if "left" in uniform_config and "right" in uniform_config:
                            # Use left side config as the template (web UI will apply to both)
                            config = uniform_config["left"]
                            uniform_info = {
                                "name": uniform_name,
                                "type": config.get("type", "float"),
                                "target": "per-display",  # Mark as per-display
                                "value": {
                                    "left": config.get("value"),
                                    "right": uniform_config["right"].get("value"),
                                },
                            }
                        else:
                            # Simple uniform (applies to both displays)
                            uniform_info = {
                                "name": uniform_name,
                                "type": uniform_config.get("type", "float"),
                                "target": "both",
                                "value": uniform_config.get("value"),
                            }
                            config = uniform_config

                        # Add range info if available
                        if "min" in config:
                            uniform_info["min"] = config["min"]
                        if "max" in config:
                            uniform_info["max"] = config["max"]
                        if "step" in config:
                            uniform_info["step"] = config["step"]

                        animation_info["uniforms"].append(uniform_info)

                animations_list.append(animation_info)

            status = {
                "available": self.available_shaders,
                "animations": animations_list,  # Include full metadata
                "current": {
                    "left": self.shaders["left"]["current_name"],
                    "right": self.shaders["right"]["current_name"],
                },
                "transition": {
                    "left": {
                        "active": self.shaders["left"]["transition_start"] is not None,
                        "target": self.shaders["left"]["target_name"],
                        "queued": self.shaders["left"]["queued"] is not None,
                    },
                    "right": {
                        "active": self.shaders["right"]["transition_start"] is not None,
                        "target": self.shaders["right"]["target_name"],
                        "queued": self.shaders["right"]["queued"] is not None,
                    },
                },
            }

            self.mqtt_client.publish(
                "protogen/fins/renderer/status/shader", json.dumps(status), retain=True
            )

        except Exception as e:
            print(f"[Renderer] Error publishing shader status: {e}")

    def publish_uniform_status(self):
        """Publish current uniform status to MQTT"""
        if not self.mqtt_client:
            return

        try:
            # Only publish uniforms that belong to the current (or transitioning target) shader
            all_uniforms = {}

            # Get shader names - prefer target if transitioning, otherwise current
            left_shader_name = self.shaders["left"].get("target_name") or self.shaders[
                "left"
            ].get("current_name")
            right_shader_name = self.shaders["right"].get(
                "target_name"
            ) or self.shaders["right"].get("current_name")

            # If no shader is loaded yet, publish empty uniforms
            if not left_shader_name:
                self.mqtt_client.publish(
                    "protogen/fins/renderer/status/uniform", json.dumps({}), retain=True
                )
                return

            # Use the left shader's metadata (or right if left doesn't exist)
            shader_name = left_shader_name or right_shader_name
            if shader_name not in self.shader_metadata:
                # No metadata, publish empty
                self.mqtt_client.publish(
                    "protogen/fins/renderer/status/uniform", json.dumps({}), retain=True
                )
                return

            shader_config = self.shader_metadata[shader_name]
            uniforms_config = shader_config.get("uniforms", {})

            # Only include uniforms that are defined in the current shader's config
            for uniform_name, uniform_config in uniforms_config.items():
                # Check if this is per-display or global
                if "left" in uniform_config or "right" in uniform_config:
                    # Per-display uniform
                    left_config = uniform_config.get("left", {})
                    right_config = uniform_config.get("right", {})

                    all_uniforms[uniform_name] = {
                        "type": left_config.get("type", "float"),
                        "per_display": True,
                        "left": self.shaders["left"]["uniforms"].get(
                            uniform_name, left_config.get("value", 0.0)
                        ),
                        "right": self.shaders["right"]["uniforms"].get(
                            uniform_name, right_config.get("value", 0.0)
                        ),
                    }

                    # Add metadata if available
                    if "min" in left_config:
                        all_uniforms[uniform_name]["min"] = left_config["min"]
                    if "max" in left_config:
                        all_uniforms[uniform_name]["max"] = left_config["max"]
                    if "step" in left_config:
                        all_uniforms[uniform_name]["step"] = left_config["step"]
                else:
                    # Global uniform (both displays)
                    value = self.shaders["left"]["uniforms"].get(
                        uniform_name, uniform_config.get("value")
                    )
                    if isinstance(value, tuple):
                        value = list(value)

                    all_uniforms[uniform_name] = {
                        "value": value,
                        "type": uniform_config.get(
                            "type", self._infer_uniform_type(value)
                        ),
                    }

                    # Add metadata if available
                    if "min" in uniform_config:
                        all_uniforms[uniform_name]["min"] = uniform_config["min"]
                    if "max" in uniform_config:
                        all_uniforms[uniform_name]["max"] = uniform_config["max"]
                    if "step" in uniform_config:
                        all_uniforms[uniform_name]["step"] = uniform_config["step"]

            self.mqtt_client.publish(
                "protogen/fins/renderer/status/uniform",
                json.dumps(all_uniforms),
                retain=True,
            )

        except Exception as e:
            print(f"[Renderer] Error publishing uniform status: {e}")
            import traceback

            traceback.print_exc()

    def _infer_uniform_type(self, value):
        """Infer uniform type from value"""
        if isinstance(value, (int, np.integer)):
            return "int"
        elif isinstance(value, (float, np.floating)):
            return "float"
        elif isinstance(value, (tuple, list)):
            length = len(value)
            if length == 2:
                return "vec2"
            elif length == 3:
                return "vec3"
            elif length == 4:
                return "vec4"
        return "unknown"

    def init_gl(self):
        """Initialize OpenGL context and resources"""
        os.environ["DISPLAY"] = ":0"
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{self.left_x},{self.display_y}"
        pygame.init()

        # Create single wide window for both displays
        self.screen = pygame.display.set_mode(
            (self.total_width, self.total_height),
            pygame.OPENGL | pygame.DOUBLEBUF | pygame.NOFRAME,
        )
        pygame.display.set_caption("Protosuit Renderer")

        # Create OpenGL context
        self.ctx = moderngl.create_context(require=310)
        self.ctx.viewport = (0, 0, self.total_width, self.total_height)

        # Create framebuffers for each display
        for display in ["left", "right"]:
            render_width = int(
                self.display_width * self.shaders[display]["render_scale"]
            )
            render_height = int(
                self.display_height * self.shaders[display]["render_scale"]
            )
            self.fbos[display] = create_framebuffers(
                self.ctx, render_width, render_height
            )

        # Create blend shader
        self.blend_program, self.blend_vao = create_blend_shader(self.ctx)

        # Create audio FFT texture (512x2, single-channel float32)
        # Row 0 = FFT magnitudes, Row 1 = waveform data
        self.audio_texture = self.ctx.texture((512, 2), 1, dtype="f4")
        self.audio_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        print("[Renderer] OpenGL initialized")
        print(f"[Renderer] Window size: {self.total_width}x{self.total_height}")

    def _recreate_fbos(self, display: str):
        """Recreate framebuffers for a display at current render scale"""
        try:
            # Release old framebuffers
            for fbo in self.fbos[display]:
                if fbo:
                    fbo.release()

            render_width = int(
                self.display_width * self.shaders[display]["render_scale"]
            )
            render_height = int(
                self.display_height * self.shaders[display]["render_scale"]
            )

            print(
                f"[Renderer] Recreating FBOs for {display} at {render_width}x{render_height} (scale: {self.shaders[display]['render_scale']})"
            )

            # Create new framebuffers
            self.fbos[display] = create_framebuffers(
                self.ctx, render_width, render_height
            )

            print(f"[Renderer] FBOs created successfully for {display}")
        except Exception as e:
            print(f"[Renderer] ERROR creating FBOs for {display}: {e}")
            print(
                f"[Renderer] Context info: valid={self.ctx is not None}, dimensions={render_width}x{render_height}"
            )
            import traceback

            traceback.print_exc()
            # Keep old FBOs if recreation fails
            raise

        # Recompile current shader at new resolution
        if self.shaders[display]["current"]:
            shader_src = self.shaders[display]["current"].get("source")
            if shader_src:
                old_shader = self.shaders[display]["current"]
                self.shaders[display]["current"] = compile_shader(
                    self.ctx, shader_src, render_width, render_height
                )
                if old_shader and self.shaders[display]["current"]:
                    self.shaders[display]["current"]["start_time"] = old_shader[
                        "start_time"
                    ]
                    self.shaders[display]["current"]["frame"] = old_shader["frame"]
                if old_shader:
                    try:
                        old_shader["vao"].release()
                        old_shader["program"].release()
                    except:
                        pass

        if self.shaders[display]["target"]:
            shader_src = self.shaders[display]["target"].get("source")
            if shader_src:
                old_shader = self.shaders[display]["target"]
                self.shaders[display]["target"] = compile_shader(
                    self.ctx, shader_src, render_width, render_height
                )
                if old_shader:
                    try:
                        old_shader["vao"].release()
                        old_shader["program"].release()
                    except:
                        pass

    def _apply_scale_change(self, display: str, new_scale: float):
        """Apply a resolution scale change"""
        if new_scale == self.shaders[display]["render_scale"]:
            return

        self.shaders[display]["scale_changing"] = True

        # Cancel any ongoing transition
        if self.shaders[display]["target"]:
            if self.shaders[display]["current"]:
                try:
                    self.shaders[display]["current"]["vao"].release()
                    self.shaders[display]["current"]["program"].release()
                except:
                    pass
            self.shaders[display]["current"] = self.shaders[display]["target"]
            self.shaders[display]["target"] = None
            self.shaders[display]["transition_start"] = None

        self.shaders[display]["render_scale"] = new_scale
        self._recreate_fbos(display)
        self.shaders[display]["scale_change_frame_count"] = 0

        print(f"[Renderer] Scale changed for {display}: {new_scale}")

    def set_shader(
        self,
        display: str,
        shader_source: str,
        transition_duration: float,
        target_scale: float = None,
        shader_name: str = None,
    ):
        """Set a new shader for a display with transition"""
        state = self.shaders[display]

        # If already transitioning, queue this shader
        if state["transition_start"] is not None and state["target"] is not None:
            print(
                f"[Renderer] Transition in progress for {display}, queueing shader change"
            )
            state["queued"] = (
                shader_source,
                transition_duration,
                target_scale,
                shader_name,
            )
            return

        # If scale is changing, defer this shader load
        if state["scale_changing"]:
            print(
                f"[Renderer] Deferring shader load for {display} until scale change completes"
            )
            state["pending"] = (
                shader_source,
                transition_duration,
                target_scale,
                shader_name,
            )
            return

        # Handle scale change logic
        if target_scale is not None and target_scale != state["render_scale"]:
            if target_scale > state["render_scale"]:
                # Upscaling: defer until after transition
                print(
                    f"[Renderer] {display} upscaling {state['render_scale']} -> {target_scale}: will apply AFTER transition"
                )
                state["pending_scale"] = target_scale
            else:
                # Downscaling: apply immediately
                print(
                    f"[Renderer] {display} downscaling {state['render_scale']} -> {target_scale}: applying BEFORE transition"
                )
                self._apply_scale_change(display, target_scale)

        render_width = int(self.display_width * state["render_scale"])
        render_height = int(self.display_height * state["render_scale"])

        new_shader = compile_shader(
            self.ctx, shader_source, render_width, render_height
        )

        if new_shader is None:
            print(f"[Renderer] Failed to compile shader for {display}")
            return

        # If this shader needs audio and mic isn't available, trigger a retry
        if new_shader.get("uses_audio_texture") and not self.audio_capture.available:
            print("[Renderer] FFT shader loaded but no mic - requesting audio retry")
            self.audio_capture.request_retry()

        if state["current"] is None:
            # First shader, no transition
            state["current"] = new_shader
            state["current_name"] = shader_name
            # If there's a pending scale, apply it now
            if state["pending_scale"] is not None:
                self._apply_scale_change(display, state["pending_scale"])
                state["pending_scale"] = None

            # Publish status for first shader load (check if both displays are set)
            if display == "both" or (
                self.shaders["left"]["current"] and self.shaders["right"]["current"]
            ):
                self.publish_shader_status()
                self.publish_uniform_status()
        else:
            # Start transition
            state["target"] = new_shader
            state["target_name"] = shader_name
            state["transition_start"] = time.time()
            state["transition_duration"] = transition_duration

            print(
                f"[Renderer] Shader set for {display} (transition: {transition_duration}s)"
            )

            # Publish updated shader and uniform status immediately
            # This allows adjusting uniforms for the incoming shader while it transitions
            self.publish_shader_status()
            self.publish_uniform_status()

    def render_shader(self, display: str, shader_obj, target_fbo=None):
        """Render a shader to a framebuffer"""
        if shader_obj is None:
            return

        state = self.shaders[display]
        render_width = int(self.display_width * state["render_scale"])
        render_height = int(self.display_height * state["render_scale"])

        if target_fbo:
            target_fbo.use()
            self.ctx.viewport = (0, 0, render_width, render_height)

        # Update uniforms
        program = shader_obj["program"]
        if "iTime" in program:
            program["iTime"].value = time.time() - shader_obj["start_time"]
        if "frame" in program:
            program["frame"].value = shader_obj["frame"]
        if "iResolution" in program:
            program["iResolution"].value = (float(render_width), float(render_height))

        # Update custom uniforms
        for uniform_name, uniform_value in state["uniforms"].items():
            if uniform_name in program:
                try:
                    program[uniform_name].value = uniform_value
                except Exception as e:
                    print(f"[Renderer] Could not set uniform '{uniform_name}': {e}")

        # Bind audio texture for shaders that use it
        if shader_obj.get("uses_audio_texture") and self.audio_texture:
            if "iChannel0" in program:
                self.audio_texture.use(location=2)
                program["iChannel0"].value = 2

        # Render
        self.ctx.clear(0.0, 0.0, 0.0)
        shader_obj["vao"].render(moderngl.TRIANGLE_STRIP)
        shader_obj["frame"] += 1

    def render_display(self, display: str, viewport_x: int):
        """Render a single display (left or right)"""
        state = self.shaders[display]

        # Handle scale change completion
        if state["scale_changing"]:
            state["scale_change_frame_count"] += 1
            if state["scale_change_frame_count"] >= 5:
                state["scale_changing"] = False
                print(f"[Renderer] Scale change complete for {display}")
                # Load pending shader if any
                if state["pending"]:
                    if len(state["pending"]) == 4:
                        shader_source, duration, target_scale, shader_name = state[
                            "pending"
                        ]
                    elif len(state["pending"]) == 3:
                        shader_source, duration, target_scale = state["pending"]
                        shader_name = None
                    else:
                        shader_source, duration = state["pending"]
                        target_scale = None
                        shader_name = None
                    state["pending"] = None
                    self.set_shader(
                        display, shader_source, duration, target_scale, shader_name
                    )

        # Render
        if state["transition_start"] is not None and state["target"] is not None:
            # Transitioning
            elapsed = time.time() - state["transition_start"]
            alpha = min(1.0, elapsed / state["transition_duration"])

            # Render both shaders to FBOs
            self.render_shader(display, state["current"], self.fbos[display][0])
            self.render_shader(display, state["target"], self.fbos[display][1])

            # Blend to screen
            self.ctx.screen.use()
            self.ctx.viewport = (viewport_x, 0, self.display_width, self.display_height)
            self.blend_program["tex1"].value = 0
            self.blend_program["tex2"].value = 1
            self.blend_program["alpha"].value = alpha
            self.blend_program["resolution"].value = (
                float(self.display_width),
                float(self.display_height),
            )
            self.blend_program["blurEnabled"].value = 1.0 if self.blur_enabled else 0.0
            self.blend_program["blurStrengthMax"].value = self.blur_strength

            self.fbos[display][0].color_attachments[0].use(location=0)
            self.fbos[display][1].color_attachments[0].use(location=1)

            self.blend_vao.render(moderngl.TRIANGLE_STRIP)

            if alpha >= 1.0:
                # Transition complete
                if state["current"]:
                    state["current"]["vao"].release()
                    state["current"]["program"].release()
                state["current"] = state["target"]
                state["current_name"] = state["target_name"]
                state["target"] = None
                state["target_name"] = None
                state["transition_start"] = None

                # Apply pending scale change
                if state["pending_scale"] is not None:
                    print(
                        f"[Renderer] Applying pending scale for {display}: {state['pending_scale']}"
                    )
                    self._apply_scale_change(display, state["pending_scale"])
                    state["pending_scale"] = None

                # Publish updated status after transition completes
                self.publish_shader_status()
                self.publish_uniform_status()

                # Start queued transition if one exists
                if state["queued"] is not None:
                    if len(state["queued"]) == 4:
                        queued_shader, queued_duration, queued_scale, queued_name = (
                            state["queued"]
                        )
                    else:
                        queued_shader, queued_duration, queued_scale = state["queued"]
                        queued_name = None
                    state["queued"] = None
                    print(f"[Renderer] Starting queued transition for {display}")
                    self.set_shader(
                        display,
                        queued_shader,
                        queued_duration,
                        queued_scale,
                        queued_name,
                    )

                # Publish updated shader status
                self.publish_shader_status()
        else:
            # No transition - render current shader
            if state["current"]:
                self.render_shader(display, state["current"], self.fbos[display][0])

                # Blit to screen
                self.ctx.screen.use()
                self.ctx.viewport = (
                    viewport_x,
                    0,
                    self.display_width,
                    self.display_height,
                )

                self.fbos[display][0].color_attachments[0].use(location=0)
                self.blend_program["tex1"].value = 0
                self.blend_program["tex2"].value = 0
                self.blend_program["alpha"].value = 0.0
                self.blend_program["resolution"].value = (
                    float(self.display_width),
                    float(self.display_height),
                )
                self.blend_program["blurEnabled"].value = 0.0
                self.blend_program["blurStrengthMax"].value = 0.0
                self.blend_vao.render(moderngl.TRIANGLE_STRIP)

    def run(self):
        """Main render loop"""
        self.init_gl()
        self.init_mqtt()

        # Start audio capture (non-blocking, graceful if no mic)
        if not self.audio_capture.start():
            print(
                "[Renderer] No microphone found - audio-reactive shaders will show silence"
            )

        clock = pygame.time.Clock()

        print("[Renderer] Starting main loop")

        # Load default animation from config
        try:
            default_anim = self.config_loader.config.get(
                "default_animation", "aperture"
            )
            if default_anim in self.available_shaders:
                print(f"[Renderer] Loading default animation: {default_anim}")
                # Queue the default shader load
                shader_cmd = json.dumps(
                    {
                        "display": "both",
                        "name": default_anim,
                        "transition_duration": 0.0,
                    }
                )
                self.handle_shader_command(shader_cmd)
            else:
                print(
                    f"[Renderer] Default animation '{default_anim}' not found in config"
                )
        except Exception as e:
            print(f"[Renderer] Error loading default animation: {e}")

        while self.running:
            try:
                # Handle pygame events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        print("[Renderer] Received pygame QUIT event")
                        self.running = False

                # Process queued commands (from MQTT thread) in main thread
                while not self.command_queue.empty():
                    try:
                        cmd = self.command_queue.get_nowait()
                        if cmd[0] == "shader":
                            _, display, shader_source, duration, scale, shader_name = (
                                cmd
                            )
                            if display in ["left", "right"]:
                                self.set_shader(
                                    display, shader_source, duration, scale, shader_name
                                )
                            elif display == "both":
                                self.set_shader(
                                    "left", shader_source, duration, scale, shader_name
                                )
                                self.set_shader(
                                    "right", shader_source, duration, scale, shader_name
                                )
                    except Exception as cmd_error:
                        print(f"[Renderer] Error processing command: {cmd_error}")

                # Update audio texture with latest FFT data
                if self.audio_texture and self.audio_capture.available:
                    self.audio_texture.write(self.audio_capture.get_texture_data())

                # Performance optimization: skip rendering when executable or video is running
                if not self.exec_running and not self.video_running:
                    # Render both displays
                    self.render_display("left", 0)
                    self.render_display("right", self.display_width)

                    # Swap buffers
                    pygame.display.flip()
                else:
                    # When executable or video is running, just clear the screen to black
                    # This saves significant GPU/CPU resources
                    self.ctx.clear(0.0, 0.0, 0.0, 1.0)  # Clear to black
                    pygame.display.flip()

                clock.tick(60)

                # Track FPS
                self.fps_counter += 1

                # Publish FPS data periodically
                if time.time() - self.last_fps_publish >= self.fps_publish_interval:
                    self.publish_fps_data()
            except Exception as e:
                print(f"[Renderer] Error in main loop: {e}")
                import traceback

                traceback.print_exc()
                # Don't exit on errors, just log and continue
                time.sleep(0.1)

        print("[Renderer] Shutting down")

        # Cleanup
        self.audio_capture.stop()

        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

        pygame.quit()


if __name__ == "__main__":
    print("=" * 60)
    print("Protosuit Renderer")
    print("=" * 60)

    renderer = Renderer()
    renderer.run()

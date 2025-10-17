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
from renderer.shader_compiler import compile_shader


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
                "target": None,
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
                "target": None,
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

        # MQTT
        self.mqtt_client = None
        self.mqtt_broker = mqtt_config.broker
        self.mqtt_port = mqtt_config.port

        # Command queue for thread-safe OpenGL operations
        from queue import Queue

        self.command_queue = Queue()

        print("Renderer initialized")
        print(
            f"Display config: {self.display_width}x{self.display_height} @ ({self.left_x}, {self.right_x})"
        )

    def init_mqtt(self):
        """Initialize MQTT client for control and status"""
        try:
            self.mqtt_client = create_mqtt_client(self.config_loader)
            self.mqtt_client.on_message = self.on_mqtt_message

            # Subscribe to control topics
            self.mqtt_client.subscribe("protogen/renderer/shader")
            self.mqtt_client.subscribe("protogen/renderer/uniform")
            self.mqtt_client.subscribe("protogen/renderer/command")

            self.mqtt_client.loop_start()

            # Publish initial status
            self.publish_status("ready")

            # Request current state from engine (in case we started after engine)
            self.mqtt_client.publish("protogen/renderer/request_state", "shader")

            print("[Renderer] MQTT client initialized")
            print("[Renderer] Subscribed to:")
            print("  - protogen/renderer/shader")
            print("  - protogen/renderer/uniform")
            print("  - protogen/renderer/command")
            print("[Renderer] Requested current state from engine")

        except Exception as e:
            print(f"[Renderer] Failed to initialize MQTT client: {e}")
            self.mqtt_client = None

    def on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8")

            if topic == "protogen/renderer/shader":
                self.handle_shader_command(payload)
            elif topic == "protogen/renderer/uniform":
                self.handle_uniform_command(payload)
            elif topic == "protogen/renderer/command":
                self.handle_control_command(payload)

        except Exception as e:
            print(f"[Renderer] Error handling MQTT message: {e}")
            import traceback

            traceback.print_exc()

    def handle_shader_command(self, payload: str):
        """Handle shader change command (queues for main thread)

        Format: display:duration:scale:shader_source
        """
        try:
            parts = payload.split(":", 3)
            if len(parts) < 4:
                print(f"[Renderer] Invalid shader command format")
                return

            display = parts[0]  # 'left', 'right', or 'both'
            duration = float(parts[1])
            scale = float(parts[2])
            shader_source = parts[3]

            # Queue command for main thread (OpenGL operations must be on main thread)
            self.command_queue.put(("shader", display, shader_source, duration, scale))

        except Exception as e:
            print(f"[Renderer] Error handling shader command: {e}")
            import traceback

            traceback.print_exc()

    def handle_uniform_command(self, payload: str):
        """Handle uniform update command

        Format: display:name:type:value
        """
        try:
            parts = payload.split(":", 3)
            if len(parts) < 4:
                print(f"[Renderer] Invalid uniform command format: {payload}")
                return

            display = parts[0]  # 'left', 'right', or 'both'
            uniform_name = parts[1]
            uniform_type = parts[2]
            value_str = parts[3]

            # Parse value based on type
            if uniform_type == "float":
                value = float(value_str)
            elif uniform_type == "int":
                value = int(value_str)
            elif uniform_type in ["vec2", "vec3", "vec4"]:
                # Values are space-separated from display_manager
                value = tuple(float(x.strip()) for x in value_str.split())
            else:
                print(f"[Renderer] Unknown uniform type: {uniform_type}")
                return

            if display in ["left", "right"]:
                self.shaders[display]["uniforms"][uniform_name] = value
            elif display == "both":
                self.shaders["left"]["uniforms"][uniform_name] = value
                self.shaders["right"]["uniforms"][uniform_name] = value

            print(f"[Renderer] Set uniform '{uniform_name}' = {value} on {display}")

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
            print("[Renderer] Configuration reloaded")
        except Exception as e:
            print(f"[Renderer] Error reloading config: {e}")

    def publish_status(self, status: str, details: str = None):
        """Publish renderer status to MQTT"""
        if not self.mqtt_client:
            return

        try:
            status_data = {"status": status, "timestamp": time.time()}
            if details:
                status_data["details"] = details

            self.mqtt_client.publish(
                "protogen/renderer/status", json.dumps(status_data), retain=True
            )
        except Exception as e:
            print(f"[Renderer] Error publishing status: {e}")

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
                "protogen/renderer/fps", json.dumps(fps_data), retain=True
            )

            # Reset counters
            self.fps_counter = 0
            self.fps_start_time = current_time
            self.last_fps_publish = current_time

        except Exception as e:
            print(f"[Renderer] Error publishing FPS data: {e}")

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

            fbo1 = self.ctx.framebuffer(
                color_attachments=[self.ctx.texture((render_width, render_height), 4)]
            )
            fbo2 = self.ctx.framebuffer(
                color_attachments=[self.ctx.texture((render_width, render_height), 4)]
            )
            self.fbos[display] = [fbo1, fbo2]

        # Create blend shader
        self._init_blend_shader()

        print("[Renderer] OpenGL initialized")
        print(f"[Renderer] Window size: {self.total_width}x{self.total_height}")

    def _init_blend_shader(self):
        """Initialize shader for blending two framebuffers"""
        vertex_shader = """
        #version 300 es
        precision highp float;
        in vec2 in_position;
        out vec2 uv;

        void main() {
            gl_Position = vec4(in_position, 0.0, 1.0);
            uv = (in_position + 1.0) * 0.5;
        }
        """

        fragment_shader = """
        #version 300 es
        precision highp float;
        uniform sampler2D tex1;
        uniform sampler2D tex2;
        uniform float alpha;
        uniform vec2 resolution;
        uniform float blurEnabled;
        uniform float blurStrengthMax;
        in vec2 uv;
        out vec4 fragColor;

        // Gaussian blur function
        vec4 blur(sampler2D tex, vec2 uv, float strength) {
            if (strength <= 0.0) {
                return texture(tex, uv);
            }

            vec2 texelSize = 1.0 / resolution;
            vec4 result = vec4(0.0);
            float total = 0.0;

            // 9-tap gaussian blur kernel
            float kernel[9];
            kernel[0] = 1.0; kernel[1] = 2.0; kernel[2] = 1.0;
            kernel[3] = 2.0; kernel[4] = 4.0; kernel[5] = 2.0;
            kernel[6] = 1.0; kernel[7] = 2.0; kernel[8] = 1.0;

            int index = 0;
            for (int y = -1; y <= 1; y++) {
                for (int x = -1; x <= 1; x++) {
                    vec2 offset = vec2(float(x), float(y)) * texelSize * strength;
                    result += texture(tex, uv + offset) * kernel[index];
                    total += kernel[index];
                    index++;
                }
            }

            return result / total;
        }

        void main() {
            // Smoothstep easing
            float t = alpha * alpha * (3.0 - 2.0 * alpha);

            // Blur strength peaks at middle of transition (alpha = 0.5)
            float blurStrength = blurEnabled * 4.0 * alpha * (1.0 - alpha) * blurStrengthMax;

            // Apply blur to both textures
            vec4 col1 = blur(tex1, uv, blurStrength);
            vec4 col2 = blur(tex2, uv, blurStrength);

            fragColor = mix(col1, col2, t);
        }
        """

        self.blend_program = self.ctx.program(
            vertex_shader=vertex_shader, fragment_shader=fragment_shader
        )

        # Create fullscreen quad
        vertices = np.array(
            [
                -1.0,
                -1.0,
                1.0,
                -1.0,
                -1.0,
                1.0,
                1.0,
                1.0,
            ],
            dtype="f4",
        )

        vbo = self.ctx.buffer(vertices.tobytes())
        self.blend_vao = self.ctx.simple_vertex_array(
            self.blend_program, vbo, "in_position"
        )

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

            # Create new textures
            tex1 = self.ctx.texture((render_width, render_height), 4)
            tex2 = self.ctx.texture((render_width, render_height), 4)

            # Create framebuffers
            fbo1 = self.ctx.framebuffer(color_attachments=[tex1])
            fbo2 = self.ctx.framebuffer(color_attachments=[tex2])
            self.fbos[display] = [fbo1, fbo2]

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
    ):
        """Set a new shader for a display with transition"""
        state = self.shaders[display]

        # If already transitioning, queue this shader
        if state["transition_start"] is not None and state["target"] is not None:
            print(
                f"[Renderer] Transition in progress for {display}, queueing shader change"
            )
            state["queued"] = (shader_source, transition_duration, target_scale)
            return

        # If scale is changing, defer this shader load
        if state["scale_changing"]:
            print(
                f"[Renderer] Deferring shader load for {display} until scale change completes"
            )
            state["pending"] = (shader_source, transition_duration, target_scale)
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

        if state["current"] is None:
            # First shader, no transition
            state["current"] = new_shader
            # If there's a pending scale, apply it now
            if state["pending_scale"] is not None:
                self._apply_scale_change(display, state["pending_scale"])
                state["pending_scale"] = None
        else:
            # Start transition
            state["target"] = new_shader
            state["transition_start"] = time.time()
            state["transition_duration"] = transition_duration

        print(
            f"[Renderer] Shader set for {display} (transition: {transition_duration}s)"
        )

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
                    if len(state["pending"]) == 3:
                        shader_source, duration, target_scale = state["pending"]
                    else:
                        shader_source, duration = state["pending"]
                        target_scale = None
                    state["pending"] = None
                    self.set_shader(display, shader_source, duration, target_scale)

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
                state["target"] = None
                state["transition_start"] = None

                # Apply pending scale change
                if state["pending_scale"] is not None:
                    print(
                        f"[Renderer] Applying pending scale for {display}: {state['pending_scale']}"
                    )
                    self._apply_scale_change(display, state["pending_scale"])
                    state["pending_scale"] = None

                # Start queued transition if one exists
                if state["queued"] is not None:
                    queued_shader, queued_duration, queued_scale = state["queued"]
                    state["queued"] = None
                    print(f"[Renderer] Starting queued transition for {display}")
                    self.set_shader(
                        display, queued_shader, queued_duration, queued_scale
                    )
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

        clock = pygame.time.Clock()

        print("[Renderer] Starting main loop")
        self.publish_status("running")

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
                            _, display, shader_source, duration, scale = cmd
                            if display in ["left", "right"]:
                                self.set_shader(display, shader_source, duration, scale)
                            elif display == "both":
                                self.set_shader("left", shader_source, duration, scale)
                                self.set_shader("right", shader_source, duration, scale)
                    except Exception as cmd_error:
                        print(f"[Renderer] Error processing command: {cmd_error}")

                # Render both displays
                self.render_display("left", 0)
                self.render_display("right", self.display_width)

                # Swap buffers
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
        self.publish_status("stopped")

        # Cleanup
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

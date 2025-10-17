"""
MQTT Handler - Handles MQTT communication and command routing
"""

import paho.mqtt.client as mqtt
import signal
import json
import time
from engine.display_manager import DisplayManager
from utils.mqtt_client import create_mqtt_client_with_callbacks


class MQTTHandler:
    """
    Handles MQTT communication for the protosuit engine
    Routes commands to the display manager
    """

    def __init__(self, display_manager: DisplayManager):
        """
        Initialize MQTT handler

        Args:
            display_manager: DisplayManager instance to control
        """
        self.display_manager = display_manager
        self.mqtt_client = None

    def handle_message(self, client, userdata, msg):
        """
        Handle incoming MQTT messages

        Args:
            client: MQTT client instance
            userdata: User data
            msg: MQTT message
        """
        topic = msg.topic
        payload = msg.payload.decode()

        # Base animation control
        if topic == "protogen/fins/base":
            self.display_manager.set_base_animation(
                payload, mqtt_client=self.mqtt_client
            )

        # Legacy shader command (backward compatibility)
        elif topic == "protogen/fins/shader":
            # Treat as base animation
            self.display_manager.set_base_animation(
                payload, mqtt_client=self.mqtt_client
            )

        # Media playback
        elif topic == "protogen/fins/media":
            # Handle media playback
            if payload == "stop" or payload == "quit":
                # Stop any running media
                self.display_manager.stop_overlay()
            else:
                # Play media file (uses configuration default)
                self.display_manager.play_media(payload)

        # Media playback with blank background
        elif topic == "protogen/fins/media/blank":
            # Handle media playback with blank background
            if payload == "stop" or payload == "quit":
                # Stop any running media
                self.display_manager.stop_overlay()
            else:
                # Play media file with blank background
                self.display_manager.play_media(payload, fade_to_blank=True)

        # Sync with face expression (legacy)
        elif topic == "protogen/fins/sync":
            self.display_manager.set_base_animation(
                payload, mqtt_client=self.mqtt_client
            )

        # Game launching
        elif topic == "protogen/fins/game":
            if payload == "stop" or payload == "quit":
                # Stop any running game
                self.display_manager.stop_overlay()
            else:
                self.display_manager.launch_program(payload)

        # Uniform control (real-time shader parameters)
        elif topic == "protogen/fins/uniform":
            self._handle_uniform_command(payload)

        # Uniform state query (for synchronizing web clients)
        elif topic == "protogen/fins/uniform/query":
            self._handle_uniform_query()

        # Renderer state request (for synchronizing renderer on startup)
        elif topic == "protogen/renderer/request_state":
            self._handle_renderer_state_request()

    def _handle_uniform_command(self, payload: str):
        """
        Handle uniform control command

        Args:
            payload: Uniform command in format "name:type:value" or "display:name:type:value"
        """
        try:
            parts = payload.split(":", 3)
            if len(parts) == 3:
                # Both displays
                uniform_name, uniform_type, value_str = parts
                display_idx = -1
            elif len(parts) == 4:
                # Specific display
                display_idx = int(parts[0])
                uniform_name = parts[1]
                uniform_type = parts[2]
                value_str = parts[3]
            else:
                print(f"Invalid uniform format: {payload}")
                return

            # Parse value
            if uniform_type == "float":
                value = float(value_str)
            elif uniform_type == "int":
                value = int(value_str)
            elif uniform_type in ["vec2", "vec3", "vec4"]:
                value = tuple(float(x.strip()) for x in value_str.split(","))
            else:
                print(f"Unknown uniform type: {uniform_type}")
                return

            # Set the uniform via display manager
            self.display_manager.set_uniform(
                uniform_name, uniform_type, value, display_idx, self.mqtt_client
            )
            print(f"Set uniform '{uniform_name}' to {value}")

            # Broadcast the change to all clients for synchronization
            change_payload = json.dumps(
                {
                    "uniform": uniform_name,
                    "type": uniform_type,
                    "value": list(value) if isinstance(value, tuple) else value,
                }
            )
            self.mqtt_client.publish(
                "protogen/fins/uniform/changed", change_payload, retain=False
            )
        except Exception as e:
            print(f"Error setting uniform: {e}")

    def _handle_uniform_query(self):
        """
        Handle request for current uniform state
        Publishes all current uniform values to 'protogen/fins/uniform/state' as JSON
        """
        try:
            # Get current uniform state from display manager
            uniform_state = self.display_manager.get_uniform_state()

            # Convert to old gl_renderer format: {uniform_name: value}
            # Web interface expects just the values, not the metadata
            serializable_state = {}
            for name, data in uniform_state.items():
                value = data["value"]
                # Convert tuples to lists for JSON serialization
                serializable_state[name] = (
                    list(value) if isinstance(value, tuple) else value
                )

            # Convert to JSON and publish
            state_json = json.dumps(serializable_state)
            self.mqtt_client.publish("protogen/fins/uniform/state", state_json)
            print(f"Published uniform state: {len(uniform_state)} values")
        except Exception as e:
            print(f"Error querying uniform state: {e}")

    def _handle_renderer_state_request(self):
        """
        Handle renderer state request - resend current shader and uniforms
        Called when renderer starts and needs to sync with engine state
        """
        try:
            print("[MQTT] Renderer requested current state, resending...")

            # Resend current base animation/shader
            if self.display_manager.current_base:
                print(
                    f"[MQTT] Resending current shader: {self.display_manager.current_base}"
                )
                self.display_manager.set_base_animation(
                    self.display_manager.current_base,
                    store_previous=False,
                    mqtt_client=self.mqtt_client,
                )

            # Resend all current uniforms
            uniform_state = self.display_manager.get_uniform_state()
            for uniform_name, uniform_data in uniform_state.items():
                # Resend each uniform to the renderer
                self.display_manager.set_uniform(
                    uniform_name,
                    uniform_data["type"],
                    uniform_data["value"],
                    uniform_data.get("display", "both"),
                    self.mqtt_client,
                )

            print("[MQTT] State resync complete")

        except Exception as e:
            print(f"[MQTT] Error handling renderer state request: {e}")
            import traceback

            traceback.print_exc()

    def start(self):
        """Start MQTT client and main loop"""
        # Setup signal handlers for clean exit
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Clean up any lingering processes from previous runs
        self.display_manager.cleanup_processes()

        # Setup MQTT
        self.mqtt_client = create_mqtt_client_with_callbacks(
            self.display_manager.config_loader, on_message=self.handle_message
        )
        self.mqtt_client.subscribe("protogen/fins/#")
        self.mqtt_client.subscribe("protogen/renderer/#")

        # Start with default base animation
        print("Starting engine with default animation...")
        default_animation = self.display_manager.config_loader.get_default_animation()
        print(f"Loading default animation: {default_animation}")
        self.display_manager.set_base_animation(
            default_animation, mqtt_client=self.mqtt_client
        )

        # Publish startup status (wait a moment for MQTT connection to stabilize)
        # Use retain=True so new clients get the current state immediately
        print("[MQTT] About to sleep and publish...")
        time.sleep(0.1)
        print(f"[MQTT] Publishing current_animation: {default_animation}")
        self.mqtt_client.publish(
            "protogen/fins/current_animation", default_animation, retain=True
        )
        print("[MQTT] Published successfully")

        # Run forever
        try:
            print("[MQTT] Starting MQTT loop_forever...")
            self.mqtt_client.loop_forever()
            print("[MQTT] loop_forever() exited unexpectedly!")
        except KeyboardInterrupt:
            print("[MQTT] Keyboard interrupt received")
            self._cleanup_and_exit()
        except Exception as e:
            print(f"[MQTT] Exception in loop_forever: {e}")
            import traceback

            traceback.print_exc()
            self._cleanup_and_exit()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\nReceived signal {signum}, cleaning up...")
        self._cleanup_and_exit()

    def _cleanup_and_exit(self):
        """Clean up all processes and exit"""
        print("Cleaning up...")
        self.display_manager.cleanup()
        print("Cleanup complete, exiting.")
        exit(0)

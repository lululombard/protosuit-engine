"""
ESPBridge - Serial bridge between MQTT and ESP32

Forwards MQTT messages to ESP32 via serial and publishes ESP32 sensor data to MQTT.

Serial Protocol:
    Pi -> ESP32:  >topic\tpayload\n  (forward MQTT message)
    ESP32 -> Pi:  <topic\tpayload\n  (ESP32 wants to publish)

MQTT Topics:
    Subscribes to:
        - protogen/# (all messages, forwards to ESP32)

    Publishes (from ESP32):
        - protogen/visor/esp/status/sensors - {temp, hum, rpm, fan}
        - protogen/visor/esp/status/alive - ESP32 connection status
        - protogen/visor/teensy/raw - Raw Teensy messages
"""

import paho.mqtt.client as mqtt
import serial
import signal
import json
import threading
import time
import sys
import os
from typing import Optional
from queue import Queue, Empty

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from utils.mqtt_client import create_mqtt_client


class ESPBridge:
    """
    ESP32 Serial Bridge Service

    Bridges MQTT messages to ESP32 via serial port and publishes
    ESP32 sensor data back to MQTT.
    """

    # Protocol constants
    MSG_FROM_PI = ">"
    MSG_TO_PI = "<"
    MSG_SEPARATOR = "\t"
    MSG_CRC_DELIM = "*"

    # CRC-8/SMBUS lookup table (polynomial 0x07)
    _CRC8_TABLE = (
        0x00,0x07,0x0E,0x09,0x1C,0x1B,0x12,0x15,0x38,0x3F,0x36,0x31,0x24,0x23,0x2A,0x2D,
        0x70,0x77,0x7E,0x79,0x6C,0x6B,0x62,0x65,0x48,0x4F,0x46,0x41,0x54,0x53,0x5A,0x5D,
        0xE0,0xE7,0xEE,0xE9,0xFC,0xFB,0xF2,0xF5,0xD8,0xDF,0xD6,0xD1,0xC4,0xC3,0xCA,0xCD,
        0x90,0x97,0x9E,0x99,0x8C,0x8B,0x82,0x85,0xA8,0xAF,0xA6,0xA1,0xB4,0xB3,0xBA,0xBD,
        0xC7,0xC0,0xC9,0xCE,0xDB,0xDC,0xD5,0xD2,0xFF,0xF8,0xF1,0xF6,0xE3,0xE4,0xED,0xEA,
        0xB7,0xB0,0xB9,0xBE,0xAB,0xAC,0xA5,0xA2,0x8F,0x88,0x81,0x86,0x93,0x94,0x9D,0x9A,
        0x27,0x20,0x29,0x2E,0x3B,0x3C,0x35,0x32,0x1F,0x18,0x11,0x16,0x03,0x04,0x0D,0x0A,
        0x57,0x50,0x59,0x5E,0x4B,0x4C,0x45,0x42,0x6F,0x68,0x61,0x66,0x73,0x74,0x7D,0x7A,
        0x89,0x8E,0x87,0x80,0x95,0x92,0x9B,0x9C,0xB1,0xB6,0xBF,0xB8,0xAD,0xAA,0xA3,0xA4,
        0xF9,0xFE,0xF7,0xF0,0xE5,0xE2,0xEB,0xEC,0xC1,0xC6,0xCF,0xC8,0xDD,0xDA,0xD3,0xD4,
        0x69,0x6E,0x67,0x60,0x75,0x72,0x7B,0x7C,0x51,0x56,0x5F,0x58,0x4D,0x4A,0x43,0x44,
        0x19,0x1E,0x17,0x10,0x05,0x02,0x0B,0x0C,0x21,0x26,0x2F,0x28,0x3D,0x3A,0x33,0x34,
        0x4E,0x49,0x40,0x47,0x52,0x55,0x5C,0x5B,0x76,0x71,0x78,0x7F,0x6A,0x6D,0x64,0x63,
        0x3E,0x39,0x30,0x37,0x22,0x25,0x2C,0x2B,0x06,0x01,0x08,0x0F,0x1A,0x1D,0x14,0x13,
        0xAE,0xA9,0xA0,0xA7,0xB2,0xB5,0xBC,0xBB,0x96,0x91,0x98,0x9F,0x8A,0x8D,0x84,0x83,
        0xDE,0xD9,0xD0,0xD7,0xC2,0xC5,0xCC,0xCB,0xE6,0xE1,0xE8,0xEF,0xFA,0xFD,0xF4,0xF3,
    )

    # Topics ESP32 actually handles - only forward these
    ESP32_TOPICS = [
        "protogen/visor/esp/set/fan",
        "protogen/visor/esp/set/fanmode",
        "protogen/visor/esp/config/fancurve",
        "protogen/fins/renderer/status/shader",
        "protogen/fins/bluetoothbridge/status/devices",
        "protogen/global/notifications",
        "protogen/visor/teensy/menu/set",
        "protogen/visor/teensy/menu/get",
        "protogen/visor/teensy/menu/save",
        "protogen/visor/esp/restart",
    ]

    def __init__(self, serial_port: str = "/dev/ttyUSB0", baud_rate: int = 921600):
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.serial: Optional[serial.Serial] = None
        self.mqtt_client: Optional[mqtt.Client] = None
        self.running = False

        # Message queues
        self.mqtt_to_serial_queue: Queue = Queue()

        # State tracking
        self.esp_connected = False
        self.last_esp_message = 0
        self.retained_forwarded = False  # Only forward retained once
        self.last_shader_payload = None  # Dedupe rapid shader updates

        # Retained messages to forward on connect
        self.retained_messages: dict = {}

        # Load configuration
        self.config_loader = ConfigLoader()

        # Threads
        self.serial_read_thread: Optional[threading.Thread] = None
        self.serial_write_thread: Optional[threading.Thread] = None

        print(f"[ESPBridge] Initialized for {serial_port} @ {baud_rate}")

    @staticmethod
    def _crc8(data: bytes) -> int:
        crc = 0x00
        for b in data:
            crc = ESPBridge._CRC8_TABLE[crc ^ b]
        return crc

    def start(self):
        """Start the ESP bridge service"""
        self.running = True

        # Initialize serial connection
        if not self._init_serial():
            print("[ESPBridge] Failed to initialize serial, will retry...")

        # Initialize MQTT
        self._init_mqtt()

        # Start threads
        self.serial_read_thread = threading.Thread(target=self._serial_read_loop, daemon=True)
        self.serial_write_thread = threading.Thread(target=self._serial_write_loop, daemon=True)
        self.serial_read_thread.start()
        self.serial_write_thread.start()

        print("[ESPBridge] Service started")

        # Main loop - handle reconnections
        while self.running:
            try:
                # Check serial connection
                if self.serial is None or not self.serial.is_open:
                    self._init_serial()

                # Check ESP32 timeout (no messages for 10 seconds)
                if self.esp_connected and time.time() - self.last_esp_message > 10:
                    self.esp_connected = False
                    self._publish_esp_status(False)

                time.sleep(1)

            except Exception as e:
                print(f"[ESPBridge] Error in main loop: {e}")
                time.sleep(1)

    def stop(self):
        """Stop the ESP bridge service"""
        print("[ESPBridge] Stopping...")
        self.running = False

        if self.serial and self.serial.is_open:
            self.serial.close()

        if self.mqtt_client:
            self._publish_esp_status(False)
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

        print("[ESPBridge] Stopped")

    def _init_serial(self) -> bool:
        """Initialize serial connection to ESP32, with fallback to other ttyUSB devices."""
        if self.serial and self.serial.is_open:
            self.serial.close()

        # Try configured port first, then fall back to other ttyUSB devices
        import glob
        fallbacks = sorted(glob.glob("/dev/ttyUSB*"))
        candidates = [self.serial_port] + [p for p in fallbacks if p != self.serial_port]

        for port in candidates:
            try:
                self.serial = serial.Serial(
                    port=port,
                    baudrate=self.baud_rate,
                    timeout=0.1,
                    write_timeout=None,
                )
                if port != self.serial_port:
                    print(f"[ESPBridge] {self.serial_port} unavailable, fell back to {port}")
                print(f"[ESPBridge] Serial connected to {port}")
                return True
            except serial.SerialException:
                continue

        print(f"[ESPBridge] No serial port available (tried {candidates})")
        self.serial = None
        return False

    def _init_mqtt(self):
        """Initialize MQTT client"""
        try:
            mqtt_config = self.config_loader.get_mqtt_config()

            self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_message = self._on_mqtt_message
            self.mqtt_client.on_disconnect = self._on_mqtt_disconnect

            self.mqtt_client.connect(
                mqtt_config.broker, mqtt_config.port, mqtt_config.keepalive
            )
            self.mqtt_client.loop_start()

            print("[ESPBridge] MQTT client initialized")

        except Exception as e:
            print(f"[ESPBridge] MQTT error: {e}")

    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties):
        """Handle MQTT connection"""
        print(f"[ESPBridge] MQTT connected: {reason_code}")

        # Subscribe to all protogen messages
        client.subscribe("protogen/#")
        print("[ESPBridge] Subscribed to protogen/#")

    def _on_mqtt_disconnect(self, client, userdata, flags, reason_code, properties):
        """Handle MQTT disconnection"""
        print(f"[ESPBridge] MQTT disconnected: {reason_code}")

    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT message"""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8", errors="replace")

            # Don't forward messages that originated from ESP32
            if topic.startswith("protogen/visor/esp/status/") or topic == "protogen/visor/teensy/raw":
                return

            # Only forward topics ESP32 actually handles
            if not any(topic.startswith(t) for t in self.ESP32_TOPICS):
                return

            # Strip large arrays from shader status (ESP32 has 512 byte buffer)
            if topic == "protogen/fins/renderer/status/shader":
                try:
                    data = json.loads(payload)
                    # Only keep current and transition, strip animations and available
                    filtered = {
                        "current": data.get("current"),
                        "transition": data.get("transition"),
                    }
                    payload = json.dumps(filtered, separators=(",", ":"))
                    # Dedupe rapid shader updates - skip if same as last sent
                    if payload == self.last_shader_payload:
                        print(f"[ESPBridge] Shader SKIPPED (dupe): {filtered['current']}")
                        return
                    self.last_shader_payload = payload
                    print(f"[ESPBridge] Shader SEND: retain={msg.retain} current={filtered['current']}")
                except json.JSONDecodeError:
                    pass

            # Store retained messages after filtering - will forward when ESP32 connects
            if msg.retain:
                self.retained_messages[topic] = payload
                return

            # Only queue non-retained messages if ESP32 is already connected
            if self.esp_connected:
                self.mqtt_to_serial_queue.put((topic, payload))

        except Exception as e:
            print(f"[ESPBridge] Error processing MQTT message: {e}")

    def _forward_retained_messages(self):
        """Forward all stored retained messages to ESP32"""
        if self.retained_forwarded:
            return
        self.retained_forwarded = True
        print(f"[ESPBridge] Forwarding {len(self.retained_messages)} retained messages...")
        for topic, payload in self.retained_messages.items():
            self.mqtt_to_serial_queue.put((topic, payload))

    def _serial_write_loop(self):
        """Thread for writing to serial"""
        while self.running:
            try:
                # Get message from queue with timeout
                topic, payload = self.mqtt_to_serial_queue.get(timeout=0.5)

                if self.serial and self.serial.is_open:
                    # Format: >topic\tpayload*XX\n
                    body = f"{topic}{self.MSG_SEPARATOR}{payload}"
                    crc = self._crc8(body.encode("utf-8"))
                    message = f"{self.MSG_FROM_PI}{body}{self.MSG_CRC_DELIM}{crc:02X}\n"
                    self.serial.write(message.encode("utf-8"))
                    self.serial.flush()  # Wait for write to complete
                    # Delay to let ESP32 process before next message
                    time.sleep(0.05)

            except Empty:
                continue
            except serial.SerialException as e:
                print(f"[ESPBridge] Serial write error: {e}")
                self.serial = None
                time.sleep(1)
            except Exception as e:
                print(f"[ESPBridge] Write error: {e}")

    def _serial_read_loop(self):
        """Thread for reading from serial"""
        buffer = ""

        while self.running:
            try:
                if self.serial is None or not self.serial.is_open:
                    time.sleep(1)
                    continue

                # Read available data
                if self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting)
                    buffer += data.decode("utf-8", errors="replace")

                    # Process complete lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if line.startswith(self.MSG_TO_PI):
                            body = line[1:]
                            # Require CRC
                            crc_pos = body.rfind(self.MSG_CRC_DELIM)
                            if crc_pos <= 0 or len(body) - crc_pos != 3:
                                print(f"[ESPBridge] CRC MISSING, dropping")
                                continue
                            crc_hex = body[crc_pos + 1:]
                            data = body[:crc_pos]
                            try:
                                expected = int(crc_hex, 16)
                            except ValueError:
                                print(f"[ESPBridge] CRC INVALID '{crc_hex}', dropping")
                                continue
                            actual = self._crc8(data.encode("utf-8"))
                            if expected != actual:
                                print(f"[ESPBridge] CRC FAIL: expected {expected:02X} got {actual:02X}, dropping")
                                continue
                            self._process_esp_message(data)
                        elif line:
                            print(f"[ESP32] {line}")

                time.sleep(0.01)

            except serial.SerialException as e:
                print(f"[ESPBridge] Serial read error: {e}")
                self.serial = None
                buffer = ""
                time.sleep(1)
            except Exception as e:
                print(f"[ESPBridge] Read error: {e}")

    def _process_esp_message(self, message: str):
        """Process message from ESP32"""
        try:
            # Update connection state
            self.last_esp_message = time.time()
            if not self.esp_connected:
                self.esp_connected = True
                self._publish_esp_status(True)
                # Forward retained messages now that ESP32 is confirmed alive
                if not self.retained_forwarded:
                    threading.Timer(0.5, self._forward_retained_messages).start()
                # Request Teensy menu sync after ESP32 settles
                threading.Timer(2.0, self._request_teensy_sync).start()

            # Parse: topic\tpayload
            if self.MSG_SEPARATOR in message:
                topic, payload = message.split(self.MSG_SEPARATOR, 1)

                # Publish to MQTT
                if self.mqtt_client:
                    retain = (
                        topic.endswith("/alive") or
                        topic.endswith("/sensors") or
                        topic.endswith("/fancurve") or
                        topic.startswith("protogen/visor/teensy/menu/status/") or
                        topic == "protogen/visor/teensy/menu/schema"
                    )
                    self.mqtt_client.publish(topic, payload, retain=retain)

        except Exception as e:
            print(f"[ESPBridge] Error processing ESP message: {e}")

    def _request_teensy_sync(self):
        """Request Teensy menu state + schema from ESP32"""
        if self.esp_connected:
            self.mqtt_to_serial_queue.put(("protogen/visor/teensy/menu/get", ""))

    def _publish_esp_status(self, connected: bool):
        """Publish ESP32 connection status"""
        if self.mqtt_client:
            status = "true" if connected else "false"
            self.mqtt_client.publish(
                "protogen/visor/esp/status/alive", status, retain=True
            )
            print(f"[ESPBridge] ESP32 {'connected' if connected else 'disconnected'}")


def main():
    """Main entry point"""
    import argparse

    # Load config for defaults
    config_loader = ConfigLoader()
    esp32_config = config_loader.get_esp32_config()

    parser = argparse.ArgumentParser(description="ESP32 Serial Bridge")
    parser.add_argument(
        "--port",
        default=esp32_config.serial_port,
        help=f"Serial port (default: {esp32_config.serial_port})",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=esp32_config.baud_rate,
        help=f"Baud rate (default: {esp32_config.baud_rate})",
    )
    args = parser.parse_args()

    bridge = ESPBridge(serial_port=args.port, baud_rate=args.baud)

    # Handle signals
    def signal_handler(sig, frame):
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    bridge.start()


if __name__ == "__main__":
    main()

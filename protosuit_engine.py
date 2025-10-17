#!/usr/bin/env python3
"""
Protosuit Engine - Main Entry Point
Dual-display LED fin controller with base/overlay animation system
"""
from engine.display_manager import DisplayManager
from engine.mqtt_handler import MQTTHandler


if __name__ == "__main__":
    # Initialize display manager
    manager = DisplayManager()

    # Initialize MQTT handler
    mqtt = MQTTHandler(manager)

    # Start main loop
    mqtt.start()

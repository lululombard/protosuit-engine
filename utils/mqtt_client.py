"""
MQTT client factory for protosuit engine
Provides standardized MQTT client creation and configuration
"""

import paho.mqtt.client as mqtt
from config.loader import ConfigLoader


def create_mqtt_client(config_loader: ConfigLoader) -> mqtt.Client:
    """
    Create and configure MQTT client with standard settings

    Args:
        config_loader: ConfigLoader instance to get MQTT configuration

    Returns:
        Configured MQTT client instance
    """
    mqtt_config = config_loader.get_mqtt_config()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(mqtt_config.broker, mqtt_config.port, mqtt_config.keepalive)
    return client


def create_mqtt_client_with_callbacks(
    config_loader: ConfigLoader, on_connect=None, on_message=None, on_disconnect=None
) -> mqtt.Client:
    """
    Create MQTT client with custom callbacks

    Args:
        config_loader: ConfigLoader instance to get MQTT configuration
        on_connect: Callback for connection events
        on_message: Callback for message events
        on_disconnect: Callback for disconnection events

    Returns:
        Configured MQTT client instance with callbacks
    """
    mqtt_config = config_loader.get_mqtt_config()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    if on_connect:
        client.on_connect = on_connect
    if on_message:
        client.on_message = on_message
    if on_disconnect:
        client.on_disconnect = on_disconnect

    client.connect(mqtt_config.broker, mqtt_config.port, mqtt_config.keepalive)
    return client

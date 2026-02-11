"""
Shared notification publisher for Protosuit Engine services.
Publishes structured notifications to protogen/visor/notifications.
"""

import json
import time


def publish_notification(mqtt_client, ntype: str, event: str, service: str, message: str):
    """Publish a notification event to the visor notification topic.

    Args:
        mqtt_client: Connected paho MQTT client instance
        ntype: Notification category (e.g. "cast", "bluetooth", "audio", "controller")
        event: Event name (e.g. "connected", "disconnected", "enabled", "error")
        service: Service identifier (e.g. "airplay", "spotify", "speaker", "gamepad")
        message: Human-readable notification message
    """
    payload = {
        "type": ntype,
        "event": event,
        "service": service,
        "message": message,
        "timestamp": time.time(),
    }
    mqtt_client.publish(
        "protogen/visor/notifications",
        json.dumps(payload),
    )

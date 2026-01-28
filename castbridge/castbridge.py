"""
Cast Bridge - AirPlay and Spotify Connect Management Service
Manages shairport-sync (AirPlay) and raspotify (Spotify Connect) via MQTT
"""

import os
import subprocess
import json
import time
import threading
import signal
import yaml
from dataclasses import dataclass, asdict
from typing import Dict
import paho.mqtt.client as mqtt


@dataclass
class AirPlayStatus:
    enabled: bool = False
    device_name: str = "Protosuit"
    password: str = ""
    running: bool = False


@dataclass
class SpotifyStatus:
    enabled: bool = False
    device_name: str = "Protosuit"
    username: str = ""
    password: str = ""
    running: bool = False


class CastBridge:
    def __init__(self, config, mqtt_client):
        self.config = config
        self.mqtt = mqtt_client
        self.running = False

        # State
        self.airplay_status = AirPlayStatus()
        self.spotify_status = SpotifyStatus()

        # Load config from file
        self._load_config()

    def _load_config(self):
        """Load configuration from config file"""
        cast_config = self.config.get('cast', {})

        airplay = cast_config.get('airplay', {})
        self.airplay_status.device_name = airplay.get('device_name', 'Protosuit')
        self.airplay_status.password = airplay.get('password', '')

        spotify = cast_config.get('spotify', {})
        self.spotify_status.device_name = spotify.get('device_name', 'Protosuit')
        self.spotify_status.username = spotify.get('username', '')
        self.spotify_status.password = spotify.get('password', '')

    def start(self):
        """Start the cast bridge"""
        print("[CastBridge] Starting...")
        self.running = True

        # Subscribe to MQTT topics
        self._subscribe_mqtt()

        # Start polling loop
        threading.Thread(target=self._poll_loop, daemon=True).start()

        print("[CastBridge] Started successfully")

    def stop(self):
        """Stop the cast bridge"""
        print("[CastBridge] Stopping...")
        self.running = False

    # ======== Polling Loop ========

    def _poll_loop(self):
        """Poll service status every 10 seconds"""
        # Publish initial status on startup
        self._publish_airplay_status()
        self._publish_spotify_status()

        while self.running:
            try:
                self._update_airplay_status()
                self._update_spotify_status()
            except Exception as e:
                print(f"[CastBridge] Error in poll loop: {e}")
            time.sleep(10)

    # ======== AirPlay (shairport-sync) Management ========

    def _configure_shairport(self):
        """Write shairport-sync configuration file"""
        print(f"[CastBridge] Configuring shairport-sync: name={self.airplay_status.device_name}")

        config = f'''// Shairport-sync configuration - managed by CastBridge
general = {{
    name = "{self.airplay_status.device_name}";
    output_backend = "pa";
    mdns_backend = "avahi";
}};
'''
        if self.airplay_status.password:
            config += f'''
sessioncontrol = {{
    session_timeout = 120;
}};
'''

        # Write config to temp file
        config_path = "/tmp/shairport-sync.conf"
        try:
            with open(config_path, 'w') as f:
                f.write(config)
            # Make config readable by shairport-sync user
            os.chmod(config_path, 0o644)
            # Set DAEMON_ARGS to use our config file (requires sudo)
            subprocess.run(
                ["sudo", "tee", "/etc/default/shairport-sync"],
                input=f'DAEMON_ARGS="-c {config_path}"\n',
                capture_output=True, text=True
            )
            print("[CastBridge] shairport-sync config written")
            return True
        except Exception as e:
            print(f"[CastBridge] Failed to write shairport-sync config: {e}")
            return False

    def _enable_airplay(self, enable: bool) -> bool:
        """Enable or disable AirPlay (shairport-sync)"""
        print(f"[CastBridge] {'Enabling' if enable else 'Disabling'} AirPlay...")

        if enable:
            # Configure first
            if not self._configure_shairport():
                return False

            # Unmask and start the service
            subprocess.run(
                ["sudo", "systemctl", "unmask", "shairport-sync"],
                capture_output=True
            )
            result = subprocess.run(
                ["sudo", "systemctl", "start", "shairport-sync"],
                capture_output=True, text=True
            )

            if result.returncode != 0:
                print(f"[CastBridge] Failed to start shairport-sync: {result.stderr}")
                return False

            print("[CastBridge] AirPlay enabled successfully")
            self.airplay_status.enabled = True
        else:
            # Stop the service
            subprocess.run(
                ["sudo", "systemctl", "stop", "shairport-sync"],
                capture_output=True
            )

            print("[CastBridge] AirPlay disabled successfully")
            self.airplay_status.enabled = False

        self._publish_airplay_status()
        return True

    def _update_airplay_status(self):
        """Check if shairport-sync is running"""
        result = subprocess.run(
            ["systemctl", "is-active", "shairport-sync"],
            capture_output=True, text=True
        )

        is_running = result.stdout.strip() == "active"

        if is_running != self.airplay_status.running:
            self.airplay_status.running = is_running
            self._publish_airplay_status()

    # ======== Spotify (raspotify) Management ========

    def _configure_raspotify(self):
        """Write raspotify configuration file"""
        print(f"[CastBridge] Configuring raspotify: name={self.spotify_status.device_name}")

        config_lines = [
            f'LIBRESPOT_NAME="{self.spotify_status.device_name}"',
            'LIBRESPOT_BACKEND="pulseaudio"',
            'LIBRESPOT_BITRATE="160"',
            'LIBRESPOT_DISABLE_AUDIO_CACHE="true"',
        ]

        # Add credentials if provided
        if self.spotify_status.username and self.spotify_status.password:
            config_lines.append(f'LIBRESPOT_USERNAME="{self.spotify_status.username}"')
            config_lines.append(f'LIBRESPOT_PASSWORD="{self.spotify_status.password}"')

        config = '\n'.join(config_lines) + '\n'

        # Write config to raspotify's config location (requires sudo)
        try:
            subprocess.run(
                ["sudo", "mkdir", "-p", "/etc/raspotify"],
                capture_output=True
            )
            subprocess.run(
                ["sudo", "tee", "/etc/raspotify/conf"],
                input=config,
                capture_output=True, text=True
            )
            print("[CastBridge] raspotify config written")
            return True
        except Exception as e:
            print(f"[CastBridge] Failed to write raspotify config: {e}")
            return False

    def _enable_spotify(self, enable: bool) -> bool:
        """Enable or disable Spotify Connect (raspotify)"""
        print(f"[CastBridge] {'Enabling' if enable else 'Disabling'} Spotify...")

        if enable:
            # Configure first
            if not self._configure_raspotify():
                return False

            # Unmask and start the service
            subprocess.run(
                ["sudo", "systemctl", "unmask", "raspotify"],
                capture_output=True
            )
            result = subprocess.run(
                ["sudo", "systemctl", "start", "raspotify"],
                capture_output=True, text=True
            )

            if result.returncode != 0:
                print(f"[CastBridge] Failed to start raspotify: {result.stderr}")
                return False

            print("[CastBridge] Spotify enabled successfully")
            self.spotify_status.enabled = True
        else:
            # Stop the service
            subprocess.run(
                ["sudo", "systemctl", "stop", "raspotify"],
                capture_output=True
            )

            print("[CastBridge] Spotify disabled successfully")
            self.spotify_status.enabled = False

        self._publish_spotify_status()
        return True

    def _update_spotify_status(self):
        """Check if raspotify is running"""
        result = subprocess.run(
            ["systemctl", "is-active", "raspotify"],
            capture_output=True, text=True
        )

        is_running = result.stdout.strip() == "active"

        if is_running != self.spotify_status.running:
            self.spotify_status.running = is_running
            self._publish_spotify_status()

    # ======== MQTT Interface ========

    def _subscribe_mqtt(self):
        """Subscribe to command topics"""
        topics = [
            "protogen/fins/castbridge/airplay/enable",
            "protogen/fins/castbridge/airplay/config",
            "protogen/fins/castbridge/spotify/enable",
            "protogen/fins/castbridge/spotify/config",
        ]

        for topic in topics:
            self.mqtt.subscribe(topic)
            print(f"[CastBridge] Subscribed to {topic}")

        # Set up message callbacks
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/enable",
            lambda client, userdata, msg: threading.Thread(
                target=self._enable_airplay, args=(json.loads(msg.payload)['enable'],), daemon=True
            ).start()
        )

        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/config",
            lambda client, userdata, msg: self._handle_airplay_config(json.loads(msg.payload))
        )

        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/spotify/enable",
            lambda client, userdata, msg: threading.Thread(
                target=self._enable_spotify, args=(json.loads(msg.payload)['enable'],), daemon=True
            ).start()
        )

        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/spotify/config",
            lambda client, userdata, msg: self._handle_spotify_config(json.loads(msg.payload))
        )

    def _handle_airplay_config(self, data: Dict):
        """Handle AirPlay configuration update"""
        print(f"[CastBridge] Updating AirPlay config: {data}")

        self.airplay_status.device_name = data.get('device_name', self.airplay_status.device_name)
        self.airplay_status.password = data.get('password', self.airplay_status.password)

        # If service is running, restart with new config
        if self.airplay_status.running:
            print("[CastBridge] Restarting AirPlay with new config...")
            self._enable_airplay(False)
            time.sleep(1)
            self._enable_airplay(True)
        else:
            self._publish_airplay_status()

    def _handle_spotify_config(self, data: Dict):
        """Handle Spotify configuration update"""
        print(f"[CastBridge] Updating Spotify config: {data}")

        self.spotify_status.device_name = data.get('device_name', self.spotify_status.device_name)
        self.spotify_status.username = data.get('username', self.spotify_status.username)
        self.spotify_status.password = data.get('password', self.spotify_status.password)

        # If service is running, restart with new config
        if self.spotify_status.running:
            print("[CastBridge] Restarting Spotify with new config...")
            self._enable_spotify(False)
            time.sleep(1)
            self._enable_spotify(True)
        else:
            self._publish_spotify_status()

    # ======== MQTT Publishers ========

    def _publish_airplay_status(self):
        """Publish AirPlay status"""
        self.mqtt.publish(
            "protogen/fins/castbridge/status/airplay",
            json.dumps(asdict(self.airplay_status)),
            retain=True
        )

    def _publish_spotify_status(self):
        """Publish Spotify status"""
        self.mqtt.publish(
            "protogen/fins/castbridge/status/spotify",
            json.dumps(asdict(self.spotify_status)),
            retain=True
        )

    def cleanup(self):
        """Cleanup on shutdown"""
        print("[CastBridge] Stopping...")
        self.running = False
        self.mqtt.loop_stop()
        self.mqtt.disconnect()
        print("[CastBridge] Stopped")

    def run(self):
        """Main run loop"""
        print("[CastBridge] Starting cast bridge...")

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start the bridge
        self.start()

        print("[CastBridge] Cast bridge is running. Press Ctrl+C to exit.")

        # Keep running
        try:
            while self.running:
                signal.pause()
        except KeyboardInterrupt:
            print("\n[CastBridge] Keyboard interrupt received")

        self.cleanup()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n[CastBridge] Received signal {signum}")
        self.running = False


def main():
    """Main entry point"""
    # Load config
    with open('/home/proto/protosuit-engine/config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Create MQTT client
    mqtt_client = mqtt.Client(
        client_id="protosuit-castbridge",
        clean_session=True
    )

    # Connect to MQTT broker
    mqtt_config = config['mqtt']
    mqtt_client.connect(
        mqtt_config['broker'],
        mqtt_config['port'],
        mqtt_config['keepalive']
    )

    # Start MQTT loop
    mqtt_client.loop_start()

    # Create and run bridge
    bridge = CastBridge(config, mqtt_client)
    bridge.run()


if __name__ == "__main__":
    main()

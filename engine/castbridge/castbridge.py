"""
Cast Bridge - AirPlay and Spotify Connect Management Service
Manages shairport-sync (AirPlay) and spotifyd (Spotify Connect) via systemd/D-Bus and MQTT
"""

import os
import sys
import json
import time
import threading
import signal
import re
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from utils.mqtt_client import create_mqtt_client
from utils.logger import setup_logger, get_logger
from utils.service_controller import ServiceController
from utils.notifications import publish_notification

try:
    from castbridge.lyrics import LyricsService
except ImportError:
    from lyrics import LyricsService

logger = get_logger("castbridge")

SHAIRPORT_CONFIG_PATH = "/etc/shairport-sync.conf"
SPOTIFYD_CONFIG_PATH = "/etc/spotifyd.conf"


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

        # Service controllers (D-Bus, no MQTT dependency)
        self._airplay_svc = ServiceController("shairport-sync")
        self._spotify_svc = ServiceController("spotifyd")

        # State
        self.airplay_status = AirPlayStatus()
        self.spotify_status = SpotifyStatus()

        # Spotify playback tracking
        self._spotify_playback = {
            "playing": False,
            "title": "",
            "artist": "",
            "album": "",
            "cover_url": "",
            "track_id": "",
            "duration_ms": 0,
            "position_ms": 0,
        }
        self._spotify_metadata_cache = {}  # track_id -> metadata dict
        self._spotify_position_ref = 0  # position_ms at last event
        self._spotify_position_time = 0  # time.monotonic() at last event
        self._spotify_ticker = None

        # AirPlay playback tracking
        self._airplay_playback = {
            "playing": False,
            "title": "",
            "artist": "",
            "album": "",
            "genre": "",
            "track_id": "",
            "duration_ms": 0,
            "position_ms": 0,
            "start_frame": 0,
            "prgr_start": 0,
            "prgr_end": 0,
        }
        self._airplay_last_phbt_frame = 0  # For frame-delta tracking without prgr

        # AirPlay <-> AudioBridge volume sync
        self._airplay_session_active = False
        self._volume_source = None          # "airplay" | "audiobridge" | None
        self._volume_source_time = 0        # time.monotonic() of last source change
        self._volume_cooldown = 1.0         # seconds to suppress echo feedback
        self._last_airplay_volume = None    # float, -30.0..0.0
        self._last_system_volume = None     # int, 0..100
        self._airplay_dbus_proxy = None     # pydbus proxy for shairport-sync RemoteControl

        # Spotify <-> AudioBridge volume sync
        self._spotify_session_active = False
        self._spotify_volume_source = None      # "spotify" | "audiobridge" | None
        self._spotify_volume_source_time = 0
        self._last_spotify_volume = None        # float, 0.0-1.0 MPRIS scale
        self._spotify_mpris_proxy = None        # pydbus proxy for MPRIS Player
        self._spotify_state_change_time = 0     # suppress volumeset around play/pause

        # Lyrics service
        self._lyrics = LyricsService()

        # Load defaults from config.yaml, then override with actual service configs
        self._load_config()

    def _handle_config_reload(self):
        """Reload configuration from file."""
        logger.info("Reloading configuration...")
        self.config = ConfigLoader().config
        self._load_config()
        logger.info("Configuration reloaded")

    def _load_config(self):
        """Load configuration: defaults from config.yaml, then parse actual service configs"""
        cast_config = self.config.get('cast', {})

        # Defaults from config.yaml
        airplay = cast_config.get('airplay', {})
        self.airplay_status.device_name = airplay.get('device_name', 'Protosuit')
        self.airplay_status.password = airplay.get('password', '')

        spotify = cast_config.get('spotify', {})
        self.spotify_status.device_name = spotify.get('device_name', 'Protosuit')
        self.spotify_status.username = spotify.get('username', '')
        self.spotify_status.password = spotify.get('password', '')

        # Override with actual service config files (source of truth after first configure)
        self._parse_shairport_config()
        self._parse_spotifyd_config()

    def _parse_shairport_config(self):
        """Parse /etc/shairport-sync.conf to recover device_name and password"""
        content = self._airplay_svc.read_config(SHAIRPORT_CONFIG_PATH)
        if content is None:
            return

        # Extract name from: name = "DeviceName";
        match = re.search(r'name\s*=\s*"([^"]*)"', content)
        if match:
            self.airplay_status.device_name = match.group(1)

        # Password is implied by presence of sessioncontrol block
        self.airplay_status.password = ""
        if "sessioncontrol" in content:
            # We store password in config.yaml, sessioncontrol just indicates it's set
            pass

    def _parse_spotifyd_config(self):
        """Parse /etc/spotifyd.conf (TOML) to recover device_name, username, password"""
        content = self._spotify_svc.read_config(SPOTIFYD_CONFIG_PATH)
        if content is None:
            return

        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"')
            if key == "device_name":
                self.spotify_status.device_name = value
            elif key == "username":
                self.spotify_status.username = value
            elif key == "password":
                self.spotify_status.password = value

    # ======== Startup ========

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT (re)connection — re-subscribe to all topics"""
        logger.info(f"MQTT connected (reason={reason_code}), subscribing to topics")
        self._subscribe_mqtt()
        if self.running:
            self._sync_service_state()

    def start(self):
        """Start the cast bridge"""
        logger.info("Starting...")
        self.running = True

        # Set on_connect handler for (re)connection resilience
        self.mqtt.on_connect = self._on_connect

        # Systemd is the source of truth for service state
        self._sync_service_state()

        # Subscribe to MQTT topics (also re-done in on_connect for reconnects)
        self._subscribe_mqtt()

        # Start polling loop
        threading.Thread(target=self._poll_loop, daemon=True).start()

        # Start log streaming for enabled services
        if self.airplay_status.enabled:
            self._start_log_stream("airplay")
        if self.spotify_status.enabled:
            self._start_log_stream("spotify")

        # Start lyrics service
        lyrics_config = self.config.get('cast', {}).get('lyrics', {})
        if lyrics_config.get('enabled', True):
            self._lyrics.start(self.mqtt, self.config)

        logger.info("Started successfully")

    def _sync_service_state(self):
        """Read systemd state at startup — systemd is the source of truth"""
        airplay_health = self._airplay_svc.get_health()
        self.airplay_status.enabled = airplay_health.is_enabled
        self.airplay_status.running = airplay_health.is_active
        logger.info(
            f"AirPlay: enabled={airplay_health.is_enabled}, "
            f"active={airplay_health.is_active}, "
            f"state={airplay_health.active_state}/{airplay_health.sub_state}"
        )

        spotify_health = self._spotify_svc.get_health()
        self.spotify_status.enabled = spotify_health.is_enabled
        self.spotify_status.running = spotify_health.is_active
        logger.info(
            f"Spotify: enabled={spotify_health.is_enabled}, "
            f"active={spotify_health.is_active}, "
            f"state={spotify_health.active_state}/{spotify_health.sub_state}"
        )

        # Publish initial status
        self._publish_airplay_status()
        self._publish_spotify_status()
        self._publish_service_health("airplay", airplay_health)
        self._publish_service_health("spotify", spotify_health)

    def stop(self):
        """Stop the cast bridge"""
        logger.info("Stopping...")
        self.running = False
        self._stop_log_stream("airplay")
        self._stop_log_stream("spotify")
        self._lyrics.stop()

    # ======== Polling Loop ========

    def _poll_loop(self):
        """Poll service status every 10 seconds"""
        while self.running:
            try:
                self._update_airplay_status()
                self._update_spotify_status()
            except Exception as e:
                logger.error(f"Error in poll loop: {e}")
            time.sleep(10)

    # ======== AirPlay Volume Sync ========

    @staticmethod
    def _airplay_to_system_volume(airplay_vol: float) -> int:
        """Convert AirPlay volume (-30.0..0.0) to system volume (0..100)."""
        clamped = max(-30.0, min(0.0, airplay_vol))
        return round(((clamped + 30.0) / 30.0) * 100.0)

    @staticmethod
    def _system_to_airplay_volume(system_vol: int) -> float:
        """Convert system volume (0..100) to AirPlay volume (-30.0..0.0)."""
        clamped = max(0, min(100, system_vol))
        return (clamped / 100.0) * 30.0 - 30.0

    def _get_airplay_remote_control(self):
        """Get or create D-Bus proxy for shairport-sync RemoteControl."""
        if self._airplay_dbus_proxy is not None:
            return self._airplay_dbus_proxy
        try:
            bus = self._airplay_svc._bus
            self._airplay_dbus_proxy = bus.get(
                "org.gnome.ShairportSync",
                "/org/gnome/ShairportSync"
            )
            return self._airplay_dbus_proxy
        except Exception as e:
            logger.debug(f"Cannot get shairport-sync D-Bus proxy: {e}")
            self._airplay_dbus_proxy = None
            return None

    def _on_airplay_session_start(self):
        """Push current system volume to iPhone when AirPlay session starts."""
        if self._last_system_volume is not None:
            airplay_vol = self._system_to_airplay_volume(self._last_system_volume)
            logger.info(f"AirPlay session start: syncing system volume {self._last_system_volume}% -> AirPlay {airplay_vol:.1f}")
            self._last_airplay_volume = airplay_vol
            self._volume_source = "audiobridge"
            self._volume_source_time = time.monotonic()
            # Delay to let shairport-sync establish DACP connection to the sender
            threading.Thread(
                target=self._initial_volume_sync,
                args=(airplay_vol,),
                daemon=True
            ).start()
        else:
            logger.debug("AirPlay session start: no system volume cached yet, skipping initial sync")

    def _initial_volume_sync(self, airplay_vol: float):
        """Wait for DACP connection, then push volume to iPhone."""
        time.sleep(2)
        if self._airplay_session_active:
            self._set_airplay_volume_dbus(airplay_vol)

    def _handle_airplay_volume(self, client, userdata, msg):
        """Handle volume updates from shairport-sync MQTT."""
        if not self._airplay_session_active:
            return
        try:
            payload = msg.payload.decode("utf-8", errors="replace").strip()
            if not payload:
                return
            # Format: "airplay_vol,vol,lowest_vol" or just a float
            parts = payload.split(",")
            airplay_vol = float(parts[0])

            now = time.monotonic()
            if (self._volume_source == "audiobridge"
                    and (now - self._volume_source_time) < self._volume_cooldown):
                self._last_airplay_volume = airplay_vol
                return

            system_vol = self._airplay_to_system_volume(airplay_vol)
            if (self._last_system_volume is not None
                    and abs(system_vol - self._last_system_volume) <= 1):
                self._last_airplay_volume = airplay_vol
                return

            logger.info(f"AirPlay volume: {airplay_vol:.1f} -> system {system_vol}%")
            self._last_airplay_volume = airplay_vol
            self._last_system_volume = system_vol
            self._volume_source = "airplay"
            self._volume_source_time = now
            self.mqtt.publish(
                "protogen/fins/audiobridge/volume/set",
                json.dumps({"volume": system_vol})
            )
        except (ValueError, IndexError) as e:
            logger.warning(f"Could not parse AirPlay volume: {msg.payload} ({e})")

    def _handle_audiobridge_volume(self, client, userdata, msg):
        """Handle volume status from audiobridge — forward to AirPlay/Spotify if session active."""
        try:
            data = json.loads(msg.payload)
            system_vol = data.get("volume")
            if system_vol is None:
                return
            self._last_system_volume = system_vol
        except (json.JSONDecodeError, KeyError):
            return

        # Forward to AirPlay if active
        if self._airplay_session_active:
            now = time.monotonic()
            if (self._volume_source == "airplay"
                    and (now - self._volume_source_time) < self._volume_cooldown):
                return

            airplay_vol = self._system_to_airplay_volume(system_vol)
            if (self._last_airplay_volume is not None
                    and abs(airplay_vol - self._last_airplay_volume) < 0.5):
                return

            logger.info(f"System volume: {system_vol}% -> AirPlay {airplay_vol:.1f}")
            self._last_airplay_volume = airplay_vol
            self._volume_source = "audiobridge"
            self._volume_source_time = now
            threading.Thread(
                target=self._set_airplay_volume_dbus,
                args=(airplay_vol,),
                daemon=True
            ).start()

        # Forward to Spotify if actively playing (not when paused — system
        # volume changes during pause are likely unrelated to Spotify and
        # pushing them would overwrite the remote's volume unexpectedly)
        elif self._spotify_session_active and self._spotify_playback["playing"]:
            now = time.monotonic()
            if (self._spotify_volume_source == "spotify"
                    and (now - self._spotify_volume_source_time) < self._volume_cooldown):
                return

            mpris_vol = self._system_to_spotify_volume(system_vol)
            if (self._last_spotify_volume is not None
                    and abs(mpris_vol - self._last_spotify_volume) < 0.01):
                return

            logger.info(f"System volume: {system_vol}% -> Spotify MPRIS {mpris_vol:.2f}")
            self._last_spotify_volume = mpris_vol
            self._spotify_volume_source = "audiobridge"
            self._spotify_volume_source_time = now
            threading.Thread(
                target=self._set_spotify_volume_mpris,
                args=(mpris_vol,),
                daemon=True
            ).start()

    def _set_airplay_volume_dbus(self, airplay_vol: float):
        """Call SetAirplayVolume on shairport-sync via D-Bus."""
        try:
            proxy = self._get_airplay_remote_control()
            if proxy is None:
                return
            proxy.SetAirplayVolume(airplay_vol)
        except Exception as e:
            logger.warning(f"SetAirplayVolume failed: {e}")
            self._airplay_dbus_proxy = None

    # ======== Spotify Volume Sync ========

    @staticmethod
    def _spotify_to_system_volume(mpris_vol: float) -> int:
        """Convert MPRIS volume (0.0..1.0) to system volume (0..100)."""
        return round(max(0.0, min(1.0, mpris_vol)) * 100.0)

    @staticmethod
    def _system_to_spotify_volume(system_vol: int) -> float:
        """Convert system volume (0..100) to MPRIS volume (0.0..1.0)."""
        return max(0, min(100, system_vol)) / 100.0

    def _get_spotify_mpris(self):
        """Get or create D-Bus proxy for spotifyd MPRIS Player.

        spotifyd registers with an instance-suffixed bus name like
        org.mpris.MediaPlayer2.spotifyd.instance12345, so we need to
        discover the actual name on the bus.
        """
        if self._spotify_mpris_proxy is not None:
            return self._spotify_mpris_proxy
        try:
            bus = self._spotify_svc._bus
            # List all bus names and find the spotifyd MPRIS instance
            dbus_proxy = bus.get("org.freedesktop.DBus", "/org/freedesktop/DBus")
            names = dbus_proxy.ListNames()
            spotifyd_name = None
            for name in names:
                if name.startswith("org.mpris.MediaPlayer2.spotifyd"):
                    spotifyd_name = name
                    break
            if spotifyd_name is None:
                logger.debug("No spotifyd MPRIS bus name found")
                return None
            self._spotify_mpris_proxy = bus.get(
                spotifyd_name,
                "/org/mpris/MediaPlayer2"
            )
            logger.info(f"Connected to spotifyd MPRIS: {spotifyd_name}")
            return self._spotify_mpris_proxy
        except Exception as e:
            logger.debug(f"Cannot get spotifyd MPRIS proxy: {e}")
            self._spotify_mpris_proxy = None
            return None

    def _on_spotify_session_start(self):
        """Push current system volume to Spotify when session starts."""
        if self._last_system_volume is not None:
            mpris_vol = self._system_to_spotify_volume(self._last_system_volume)
            logger.info(f"Spotify session start: syncing system volume {self._last_system_volume}% -> MPRIS {mpris_vol:.2f}")
            self._last_spotify_volume = mpris_vol
            self._spotify_volume_source = "audiobridge"
            self._spotify_volume_source_time = time.monotonic()
            threading.Thread(
                target=self._initial_spotify_volume_sync,
                args=(mpris_vol,),
                daemon=True
            ).start()
        else:
            logger.debug("Spotify session start: no system volume cached yet, skipping initial sync")

    def _initial_spotify_volume_sync(self, mpris_vol: float):
        """Wait for MPRIS connection, then push volume to Spotify."""
        time.sleep(2)
        if self._spotify_session_active:
            self._set_spotify_volume_mpris(mpris_vol)

    def _handle_spotify_volume_event(self, data: dict):
        """Handle volumeset event from spotifyd."""
        if not self._spotify_session_active:
            return

        raw_volume = data.get("volume", 0)
        system_vol = round(raw_volume / 655.35)
        system_vol = max(0, min(100, system_vol))

        now = time.monotonic()

        # Ignore volumeset events that arrive right after play/pause/start —
        # spotifyd echoes its internal librespot volume on state transitions,
        # which can be stale/max when volume_controller = "none"
        if (now - self._spotify_state_change_time) < 2.0:
            logger.debug(f"Ignoring volumeset {raw_volume} — too close to state change")
            return

        if (self._spotify_volume_source == "audiobridge"
                and (now - self._spotify_volume_source_time) < self._volume_cooldown):
            return

        if (self._last_system_volume is not None
                and abs(system_vol - self._last_system_volume) <= 1):
            return

        logger.info(f"Spotify volume: {raw_volume}/65535 -> system {system_vol}%")
        self._last_system_volume = system_vol
        self._spotify_volume_source = "spotify"
        self._spotify_volume_source_time = now
        self.mqtt.publish(
            "protogen/fins/audiobridge/volume/set",
            json.dumps({"volume": system_vol})
        )

    def _set_spotify_volume_mpris(self, mpris_vol: float):
        """Set Spotify volume via MPRIS D-Bus property."""
        try:
            proxy = self._get_spotify_mpris()
            if proxy is None:
                return
            proxy.Volume = mpris_vol
        except Exception as e:
            logger.warning(f"Set Spotify MPRIS volume failed: {e}")
            self._spotify_mpris_proxy = None

    # ======== AirPlay (shairport-sync) Management ========

    def _configure_shairport(self):
        """Write shairport-sync configuration to /etc/shairport-sync.conf"""
        logger.info(f"Configuring shairport-sync: name={self.airplay_status.device_name}")

        mqtt_config = self.config.get('mqtt', {})
        mqtt_host = mqtt_config.get('broker', 'localhost')
        mqtt_port = mqtt_config.get('port', 1883)

        config = f'''// Shairport-sync configuration - managed by CastBridge
general = {{
    name = "{self.airplay_status.device_name}";
    output_backend = "pa";
    mdns_backend = "avahi";
    ignore_volume_control = "yes";
}};

metadata = {{
    progress_interval = 1.0;
}};

mqtt = {{
    enabled = "yes";
    hostname = "{mqtt_host}";
    port = {mqtt_port};
    topic = "protogen/fins/castbridge/airplay/playback";
    publish_parsed = "yes";
    publish_raw = "yes";
    publish_cover = "yes";
}};
'''
        if self.airplay_status.password:
            config += f'''
sessioncontrol = {{
    session_timeout = 120;
}};
'''

        if not self._airplay_svc.write_config(SHAIRPORT_CONFIG_PATH, config):
            logger.error("Failed to write shairport-sync config")
            return False

        logger.info("shairport-sync config written")
        return True

    def _enable_airplay(self, enable: bool) -> bool:
        """Enable or disable AirPlay (shairport-sync)"""
        logger.info(f"{'Enabling' if enable else 'Disabling'} AirPlay...")

        if enable:
            if not self._configure_shairport():
                self._publish_notification("airplay", "error", "Failed to configure AirPlay")
                return False

            if not self._airplay_svc.enable():
                logger.error("Failed to enable shairport-sync")
                self._publish_notification("airplay", "error", "Failed to enable AirPlay")
                return False

            logger.info("AirPlay enabled successfully")
            self.airplay_status.enabled = True
            self.airplay_status.running = True
            self._start_log_stream("airplay")
            self._publish_notification("airplay", "enabled", "AirPlay enabled")
        else:
            self._stop_log_stream("airplay")

            if not self._airplay_svc.disable():
                logger.error("Failed to disable shairport-sync")
                return False

            logger.info("AirPlay disabled successfully")
            self.airplay_status.enabled = False
            self.airplay_status.running = False
            self._airplay_session_active = False
            self._airplay_dbus_proxy = None
            self._volume_source = None
            self._last_airplay_volume = None
            self._publish_notification("airplay", "disabled", "AirPlay disabled")

        self._publish_airplay_status()
        return True

    def _update_airplay_status(self):
        """Check shairport-sync status via D-Bus"""
        health = self._airplay_svc.get_health()
        changed = False

        if health.is_active != self.airplay_status.running:
            self.airplay_status.running = health.is_active
            changed = True
            if not health.is_active and self.airplay_status.enabled:
                self._publish_notification(
                    "airplay", "stopped",
                    f"AirPlay stopped unexpectedly ({health.active_state}/{health.sub_state})"
                )

        if health.is_enabled != self.airplay_status.enabled:
            self.airplay_status.enabled = health.is_enabled
            changed = True

        if changed:
            self._publish_airplay_status()

        self._publish_service_health("airplay", health)

    # ======== Spotify (spotifyd) Management ========

    def _configure_spotifyd(self):
        """Write spotifyd configuration to /etc/spotifyd.conf (TOML)"""
        logger.info(f"Configuring spotifyd: name={self.spotify_status.device_name}")

        event_script = os.path.join(os.path.dirname(__file__), "spotify_event.sh")

        config_lines = [
            "[global]",
            'backend = "pulseaudio"',
            f'device_name = "{self.spotify_status.device_name}"',
            "bitrate = 160",
            "no_audio_cache = true",
            'volume_controller = "none"',
            "initial_volume = 30",
            "volume_normalisation = false",
            "use_mpris = true",
            'dbus_type = "system"',
            f'onevent = "{event_script}"',
        ]

        if self.spotify_status.username and self.spotify_status.password:
            config_lines.append(f'username = "{self.spotify_status.username}"')
            config_lines.append(f'password = "{self.spotify_status.password}"')

        config = '\n'.join(config_lines) + '\n'

        if not self._spotify_svc.write_config(SPOTIFYD_CONFIG_PATH, config):
            logger.error("Failed to write spotifyd config")
            return False

        logger.info("spotifyd config written")
        return True

    def _enable_spotify(self, enable: bool) -> bool:
        """Enable or disable Spotify Connect (spotifyd)"""
        logger.info(f"{'Enabling' if enable else 'Disabling'} Spotify...")

        if enable:
            self._reset_spotify_playback()

            if not self._configure_spotifyd():
                self._publish_notification("spotify", "error", "Failed to configure Spotify")
                return False

            if not self._spotify_svc.enable():
                logger.error("Failed to enable spotifyd")
                self._publish_notification("spotify", "error", "Failed to enable Spotify")
                return False

            logger.info("Spotify enabled successfully")
            self.spotify_status.enabled = True
            self.spotify_status.running = True
            self._start_log_stream("spotify")
            self._publish_notification("spotify", "enabled", "Spotify Connect enabled")
        else:
            self._stop_spotify_ticker()
            self._reset_spotify_playback()
            self._publish_spotify_playback()
            self._stop_log_stream("spotify")

            if not self._spotify_svc.disable():
                logger.error("Failed to disable spotifyd")
                return False

            logger.info("Spotify disabled successfully")
            self.spotify_status.enabled = False
            self.spotify_status.running = False
            self._spotify_session_active = False
            self._spotify_mpris_proxy = None
            self._spotify_volume_source = None
            self._last_spotify_volume = None
            self._publish_notification("spotify", "disabled", "Spotify Connect disabled")

        self._publish_spotify_status()
        return True

    def _update_spotify_status(self):
        """Check spotifyd status via D-Bus"""
        health = self._spotify_svc.get_health()
        changed = False

        if health.is_active != self.spotify_status.running:
            self.spotify_status.running = health.is_active
            changed = True
            if not health.is_active and self.spotify_status.enabled:
                self._publish_notification(
                    "spotify", "stopped",
                    f"Spotify stopped unexpectedly ({health.active_state}/{health.sub_state})"
                )

        if health.is_enabled != self.spotify_status.enabled:
            self.spotify_status.enabled = health.is_enabled
            changed = True

        if changed:
            self._publish_spotify_status()

        self._publish_service_health("spotify", health)

    def _reset_spotify_playback(self):
        """Reset all Spotify playback state"""
        self._spotify_playback["playing"] = False
        self._spotify_playback["title"] = ""
        self._spotify_playback["artist"] = ""
        self._spotify_playback["album"] = ""
        self._spotify_playback["cover_url"] = ""
        self._spotify_playback["track_id"] = ""
        self._spotify_playback["duration_ms"] = 0
        self._spotify_playback["position_ms"] = 0
        self._spotify_position_ref = 0
        self._spotify_position_time = 0

    # ======== Spotify Playback Tracking ========

    def _fetch_spotify_metadata(self, track_id: str) -> Optional[dict]:
        """Fetch track metadata from Spotify embed page, with caching"""
        if track_id in self._spotify_metadata_cache:
            return self._spotify_metadata_cache[track_id]

        url = f"https://open.spotify.com/embed/track/{track_id}"
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            # Extract __NEXT_DATA__ JSON
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                html,
            )
            if not match:
                logger.warning(f"No __NEXT_DATA__ found for track {track_id}")
                return None

            data = json.loads(match.group(1))
            entity = data["props"]["pageProps"]["state"]["data"]["entity"]

            artists = ", ".join(a["name"] for a in entity.get("artists", []))
            images = entity.get("visualIdentity", {}).get("image", [])
            # Pick largest cover art
            cover_url = ""
            if images:
                cover_url = max(images, key=lambda i: i.get("maxWidth", 0))["url"]

            metadata = {
                "title": entity.get("title", entity.get("name", "")),
                "artist": artists,
                "cover_url": cover_url,
                "duration_ms": entity.get("duration", 0),
            }

            self._spotify_metadata_cache[track_id] = metadata
            logger.info(f"Spotify metadata: {metadata['artist']} - {metadata['title']}")
            return metadata

        except (URLError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to fetch Spotify metadata for {track_id}: {e}")
            return None

    def _handle_spotify_event(self, client, userdata, msg):
        """Handle raw Spotify events from spotifyd onevent script"""
        try:
            data = json.loads(msg.payload)
        except json.JSONDecodeError:
            return

        event = data.get("event", "")
        track_uri = data.get("track_id", "")

        # Extract bare track ID from spotify:track:XXXXX URI
        track_id = track_uri.split(":")[-1] if ":" in track_uri else track_uri

        # spotifyd event: "change" — track changed, provides full metadata
        if event == "change":
            self._spotify_playback["track_id"] = track_id
            self._spotify_playback["duration_ms"] = data.get("duration_ms", 0)
            name = data.get("name", "")
            artists = data.get("artists", "")
            album = data.get("album", "")
            covers = data.get("covers", "")
            if name:
                self._spotify_playback["title"] = name
            if artists:
                self._spotify_playback["artist"] = artists
            if album:
                self._spotify_playback["album"] = album
            if covers:
                # covers is newline-separated list of URLs, pick the first (largest)
                self._spotify_playback["cover_url"] = covers.split()[0].strip()
            elif track_id:
                threading.Thread(
                    target=self._fetch_and_update_spotify_metadata,
                    args=(track_id,),
                    daemon=True,
                ).start()
            logger.info(f"Spotify track: {artists} - {name}")
            return  # Don't publish yet, start/play event follows

        # spotifyd events: "start" (new track), "play" (resume)
        elif event in ("start", "play"):
            self._spotify_state_change_time = time.monotonic()
            was_active = self._spotify_session_active
            self._spotify_session_active = True
            self._spotify_playback["playing"] = True
            self._spotify_position_ref = data.get("position_ms", 0)
            self._spotify_position_time = time.monotonic()
            if track_id and track_id != self._spotify_playback["track_id"]:
                self._spotify_playback["track_id"] = track_id
                threading.Thread(
                    target=self._fetch_and_update_spotify_metadata,
                    args=(track_id,),
                    daemon=True,
                ).start()
            if not was_active:
                logger.info("Spotify session started, enabling volume sync")
                self._on_spotify_session_start()
            self._start_spotify_ticker()
            return  # Ticker will publish

        # spotifyd event: "pause"
        elif event == "pause":
            self._spotify_state_change_time = time.monotonic()
            self._spotify_playback["playing"] = False
            self._spotify_playback["position_ms"] = data.get("position_ms", 0)
            self._stop_spotify_ticker()

        # spotifyd event: "stop" — session disconnected
        elif event == "stop":
            self._reset_spotify_playback()
            self._stop_spotify_ticker()
            self._spotify_session_active = False
            self._spotify_mpris_proxy = None
            self._spotify_volume_source = None
            self._last_spotify_volume = None

        # spotifyd event: "volumeset" — volume changed from Spotify app
        elif event == "volumeset":
            self._handle_spotify_volume_event(data)
            return

        # spotifyd events: "load", "preloading", "endoftrack", "sessionconnected"
        elif event in ("load", "preloading", "endoftrack", "sessionconnected",
                        "unavailable"):
            return

        self._publish_spotify_playback()

    def _start_spotify_ticker(self):
        """Start a 0.5s ticker that publishes interpolated position while playing"""
        if self._spotify_ticker is not None:
            return  # Already running
        self._spotify_ticker = threading.Thread(
            target=self._spotify_tick_loop, daemon=True
        )
        self._spotify_ticker.start()

    def _stop_spotify_ticker(self):
        """Stop the position ticker"""
        self._spotify_ticker = None  # Thread checks this to exit

    def _spotify_tick_loop(self):
        """Publish position every 0.5s while playing"""
        while self._spotify_ticker is not None and self._spotify_playback["playing"]:
            elapsed = time.monotonic() - self._spotify_position_time
            pos = self._spotify_position_ref + int(elapsed * 1000)
            dur = self._spotify_playback["duration_ms"]
            if dur > 0:
                pos = min(pos, dur)
            self._spotify_playback["position_ms"] = pos
            self._publish_spotify_playback()
            time.sleep(0.5)
        self._spotify_ticker = None

    def _fetch_and_update_spotify_metadata(self, track_id: str):
        """Fetch metadata and update playback state (runs in background thread)"""
        metadata = self._fetch_spotify_metadata(track_id)
        if metadata:
            self._spotify_playback["title"] = metadata["title"]
            self._spotify_playback["artist"] = metadata["artist"]
            self._spotify_playback["cover_url"] = metadata["cover_url"]
            if metadata["duration_ms"]:
                self._spotify_playback["duration_ms"] = metadata["duration_ms"]
        self._publish_spotify_playback()

    def _publish_spotify_playback(self):
        """Publish consolidated Spotify playback state"""
        payload = {
            "playing": self._spotify_playback["playing"],
            "title": self._spotify_playback["title"],
            "artist": self._spotify_playback["artist"],
            "cover_url": self._spotify_playback["cover_url"],
            "track_id": self._spotify_playback["track_id"],
            "duration_ms": self._spotify_playback["duration_ms"],
            "position_ms": self._spotify_playback["position_ms"],
        }
        self.mqtt.publish(
            "protogen/fins/castbridge/status/spotify/playback",
            json.dumps(payload),
            retain=True,
        )

    # ======== MQTT Interface ========

    def _subscribe_mqtt(self):
        """Subscribe to command topics"""
        topics = [
            "protogen/fins/castbridge/airplay/enable",
            "protogen/fins/castbridge/airplay/config",
            "protogen/fins/castbridge/spotify/enable",
            "protogen/fins/castbridge/spotify/config",
        ]

        # AirPlay playback topics from shairport-sync
        playback_topics = [
            "protogen/fins/castbridge/airplay/playback/title",
            "protogen/fins/castbridge/airplay/playback/artist",
            "protogen/fins/castbridge/airplay/playback/album",
            "protogen/fins/castbridge/airplay/playback/genre",
            "protogen/fins/castbridge/airplay/playback/track_id",
            "protogen/fins/castbridge/airplay/playback/play_start",
            "protogen/fins/castbridge/airplay/playback/play_end",
            "protogen/fins/castbridge/airplay/playback/play_resume",
            "protogen/fins/castbridge/airplay/playback/play_flush",
            "protogen/fins/castbridge/airplay/playback/core/astm",
            "protogen/fins/castbridge/airplay/playback/ssnc/phbt",
            "protogen/fins/castbridge/airplay/playback/ssnc/prgr",
            "protogen/fins/castbridge/airplay/playback/cover",
        ]

        for topic in topics + playback_topics:
            self.mqtt.subscribe(topic)
            logger.debug(f"Subscribed to {topic}")

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

        # Spotify playback events from spotifyd onevent script
        self.mqtt.subscribe("protogen/fins/castbridge/spotify/event")
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/spotify/event",
            self._handle_spotify_event,
        )

        # AirPlay playback callbacks
        for field in ["title", "artist", "album", "genre", "track_id"]:
            self.mqtt.message_callback_add(
                f"protogen/fins/castbridge/airplay/playback/{field}",
                self._handle_airplay_metadata
            )
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/playback/play_start",
            lambda c, u, m: self._handle_airplay_play_state(True)
        )
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/playback/play_end",
            lambda c, u, m: self._handle_airplay_play_state(False)
        )
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/playback/play_resume",
            lambda c, u, m: self._handle_airplay_play_state(True)
        )
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/playback/play_flush",
            lambda c, u, m: self._handle_airplay_flush()
        )
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/playback/core/astm",
            self._handle_airplay_duration
        )
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/playback/ssnc/phbt",
            self._handle_airplay_phbt
        )
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/playback/ssnc/prgr",
            self._handle_airplay_prgr
        )
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/playback/cover",
            self._handle_airplay_cover
        )

        # Volume sync: shairport-sync volume + audiobridge status
        self.mqtt.subscribe("protogen/fins/castbridge/airplay/playback/volume")
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/airplay/playback/volume",
            self._handle_airplay_volume
        )
        self.mqtt.subscribe("protogen/fins/audiobridge/status/volume")
        self.mqtt.message_callback_add(
            "protogen/fins/audiobridge/status/volume",
            self._handle_audiobridge_volume
        )

        # Config reload
        self.mqtt.subscribe("protogen/fins/config/reload")
        self.mqtt.message_callback_add(
            "protogen/fins/config/reload",
            lambda client, userdata, msg: self._handle_config_reload()
        )
        self.mqtt.subscribe("protogen/fins/castbridge/config/reload")
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/config/reload",
            lambda client, userdata, msg: self._handle_config_reload()
        )

        logger.info("Subscribed to all MQTT topics")

    # ======== AirPlay Playback Tracking ========

    def _handle_airplay_metadata(self, client, userdata, msg):
        """Handle metadata updates from shairport-sync"""
        field = msg.topic.split("/")[-1]
        value = msg.payload.decode("utf-8", errors="replace")
        if value == "--":
            value = ""
        if self._airplay_playback.get(field) != value:
            self._airplay_playback[field] = value
            if field == "track_id":
                self._airplay_playback["prgr_start"] = 0
                self._airplay_playback["prgr_end"] = 0
                self._airplay_playback["position_ms"] = 0
                self._airplay_playback["duration_ms"] = 0
            self._publish_airplay_playback()

    def _handle_airplay_play_state(self, playing: bool):
        """Handle play_start/play_end/play_resume events (NOT flush)"""
        was_active = self._airplay_session_active
        self._airplay_playback["playing"] = playing

        if playing:
            self._airplay_session_active = True
            if not was_active:
                logger.info("AirPlay session started, enabling volume sync")
                self._on_airplay_session_start()
        else:
            # play_end: session disconnected
            self._airplay_session_active = False
            self._airplay_dbus_proxy = None
            self._volume_source = None
            self._last_airplay_volume = None
            self._airplay_playback["title"] = ""
            self._airplay_playback["artist"] = ""
            self._airplay_playback["album"] = ""
            self._airplay_playback["genre"] = ""
            self._airplay_playback["track_id"] = ""
            self._airplay_playback["duration_ms"] = 0
            self._airplay_playback["position_ms"] = 0
            self._airplay_playback["start_frame"] = 0
            self._airplay_playback["prgr_start"] = 0
            self._airplay_playback["prgr_end"] = 0
            # Clear retained cover art
            self.mqtt.publish(
                "protogen/fins/castbridge/status/airplay/playback/cover",
                b"",
                retain=True
            )

        self._publish_airplay_playback()

    def _handle_airplay_flush(self):
        """Handle play_flush — buffer flushed (seek/skip), NOT disconnect."""
        self._airplay_playback["start_frame"] = 0
        self._airplay_playback["prgr_start"] = 0
        self._airplay_playback["prgr_end"] = 0
        self._publish_airplay_playback()

    def _handle_airplay_duration(self, client, userdata, msg):
        """Handle core/astm (song time in milliseconds)"""
        try:
            raw = msg.payload
            # astm is a 4-byte big-endian unsigned int (milliseconds)
            if len(raw) == 4:
                duration_ms = int.from_bytes(raw, byteorder="big")
                self._airplay_playback["duration_ms"] = duration_ms
                self._publish_airplay_playback()
        except Exception as e:
            logger.error(f"Error parsing astm: {e}")

    def _handle_airplay_prgr(self, client, userdata, msg):
        """Handle ssnc/prgr (start/current/end RTP timestamps) - fires on track start and seek"""
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
            parts = payload.split("/")
            if len(parts) == 3:
                prgr_start = int(parts[0])
                prgr_current = int(parts[1])
                prgr_end = int(parts[2])
                self._airplay_playback["prgr_start"] = prgr_start
                self._airplay_playback["prgr_end"] = prgr_end
                # Compute position and duration from RTP frames
                self._airplay_playback["position_ms"] = int((prgr_current - prgr_start) / 44100 * 1000)
                self._airplay_playback["duration_ms"] = int((prgr_end - prgr_start) / 44100 * 1000)
                # Set start_frame for phbt-based tracking going forward
                self._airplay_playback["start_frame"] = prgr_current
                self._airplay_last_phbt_frame = 0  # Reset delta tracking, using absolute now
                self._publish_airplay_playback()
        except Exception as e:
            logger.error(f"Error parsing prgr: {e}")

    def _handle_airplay_phbt(self, client, userdata, msg):
        """Handle ssnc/phbt (frame position / monotonic time) - fires every second"""
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
            parts = payload.split("/")
            if len(parts) != 2:
                return
            frame = int(parts[0])

            # phbt only fires during active playback — detect playback after restart
            if not self._airplay_playback["playing"]:
                self._airplay_playback["playing"] = True
                self._airplay_last_phbt_frame = frame
                self._publish_airplay_playback()
                return

            prgr_start = self._airplay_playback.get("prgr_start", 0)
            if prgr_start:
                # Normal path: absolute position from prgr reference
                self._airplay_playback["position_ms"] = int((frame - prgr_start) / 44100 * 1000)
            elif self._airplay_last_phbt_frame:
                # No prgr reference (e.g. after restart) — use frame delta
                delta_ms = int((frame - self._airplay_last_phbt_frame) / 44100 * 1000)
                if 0 < delta_ms < 5000:  # Sanity: ignore jumps > 5s
                    self._airplay_playback["position_ms"] += delta_ms

            self._airplay_last_phbt_frame = frame
            self._publish_airplay_playback()
        except Exception as e:
            logger.error(f"Error parsing phbt: {e}")

    def _handle_airplay_cover(self, client, userdata, msg):
        """Re-publish cover art with retain flag so it persists across page loads"""
        self.mqtt.publish(
            "protogen/fins/castbridge/status/airplay/playback/cover",
            msg.payload,
            retain=True
        )

    def _publish_airplay_playback(self):
        """Publish consolidated AirPlay playback state"""
        payload = {
            "playing": self._airplay_playback["playing"],
            "title": self._airplay_playback["title"],
            "artist": self._airplay_playback["artist"],
            "album": self._airplay_playback["album"],
            "genre": self._airplay_playback["genre"],
            "track_id": self._airplay_playback["track_id"],
            "duration_ms": self._airplay_playback["duration_ms"],
            "position_ms": self._airplay_playback["position_ms"],
        }
        self.mqtt.publish(
            "protogen/fins/castbridge/status/airplay/playback",
            json.dumps(payload),
            retain=True
        )

    # ======== Config Update Handlers ========

    def _handle_airplay_config(self, data: Dict):
        """Handle AirPlay configuration update"""
        logger.info(f"Updating AirPlay config: {data}")

        self.airplay_status.device_name = data.get('device_name', self.airplay_status.device_name)
        self.airplay_status.password = data.get('password', self.airplay_status.password)

        if self.airplay_status.running:
            logger.info("Restarting AirPlay with new config...")
            self._configure_shairport()
            self._airplay_svc.restart()
            self._airplay_dbus_proxy = None
            self._publish_notification("airplay", "restarted", "AirPlay restarted with new config")

        self._publish_airplay_status()

    def _handle_spotify_config(self, data: Dict):
        """Handle Spotify configuration update"""
        logger.info(f"Updating Spotify config: {data}")

        self.spotify_status.device_name = data.get('device_name', self.spotify_status.device_name)
        self.spotify_status.username = data.get('username', self.spotify_status.username)
        self.spotify_status.password = data.get('password', self.spotify_status.password)

        if self.spotify_status.running:
            logger.info("Restarting Spotify with new config...")
            self._configure_spotifyd()
            self._spotify_svc.restart()
            self._spotify_mpris_proxy = None
            self._publish_notification("spotify", "restarted", "Spotify restarted with new config")

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

    def _publish_service_health(self, service: str, health):
        """Publish service health data for monitoring"""
        self.mqtt.publish(
            f"protogen/fins/castbridge/status/{service}/health",
            json.dumps(health.to_dict()),
            retain=True,
        )

    def _publish_notification(self, service: str, event: str, message: str):
        """Publish a notification event to the global notification topic"""
        publish_notification(self.mqtt, "cast", event, service, message)
        logger.info(f"Notification: [{service}] {event} - {message}")

    # ======== Log Streaming ========

    def _start_log_stream(self, service: str):
        """Start streaming journal logs for a service to MQTT"""
        svc = self._airplay_svc if service == "airplay" else self._spotify_svc
        topic = f"protogen/fins/castbridge/status/{service}/logs"

        def on_log_entry(entry):
            log_msg = {
                "message": entry.get("MESSAGE", ""),
                "priority": int(entry.get("PRIORITY", 6)),
                "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                "pid": entry.get("_PID", ""),
            }
            self.mqtt.publish(topic, json.dumps(log_msg))

        svc.start_log_stream(on_log_entry)

    def _stop_log_stream(self, service: str):
        """Stop journal log streaming for a service"""
        svc = self._airplay_svc if service == "airplay" else self._spotify_svc
        svc.stop_log_stream()

    # ======== Lifecycle ========

    def cleanup(self):
        """Cleanup on shutdown"""
        logger.info("Cleaning up...")
        self.running = False
        self._stop_log_stream("airplay")
        self._stop_log_stream("spotify")
        self._lyrics.stop()
        self.mqtt.loop_stop()
        self.mqtt.disconnect()
        logger.info("Stopped")

    def run(self):
        """Main run loop"""
        logger.info("Starting cast bridge...")

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.start()

        logger.info("Cast bridge is running. Press Ctrl+C to exit.")

        try:
            while self.running:
                signal.pause()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")

        self.cleanup()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}")
        self.running = False


def main():
    """Main entry point"""
    setup_logger("castbridge")

    config_loader = ConfigLoader()
    config = config_loader.config

    mqtt_client = create_mqtt_client(config_loader)
    mqtt_client.loop_start()

    bridge = CastBridge(config, mqtt_client)
    bridge.run()


if __name__ == "__main__":
    main()

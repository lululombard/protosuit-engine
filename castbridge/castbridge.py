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
import re
import yaml
from dataclasses import dataclass, asdict
from typing import Dict, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
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

        mqtt_config = self.config.get('mqtt', {})
        mqtt_host = mqtt_config.get('broker', 'localhost')
        mqtt_port = mqtt_config.get('port', 1883)

        config = f'''// Shairport-sync configuration - managed by CastBridge
general = {{
    name = "{self.airplay_status.device_name}";
    output_backend = "pa";
    mdns_backend = "avahi";
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

        event_script = os.path.join(os.path.dirname(__file__), "spotify_event.sh")

        config_lines = [
            f'LIBRESPOT_NAME="{self.spotify_status.device_name}"',
            'LIBRESPOT_BACKEND="pulseaudio"',
            'LIBRESPOT_BITRATE="160"',
            'LIBRESPOT_DISABLE_AUDIO_CACHE="true"',
            f'LIBRESPOT_ONEVENT="{event_script}"',
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
            # Clear playback state before starting
            self._reset_spotify_playback()

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
            # Stop ticker and clear playback state
            self._stop_spotify_ticker()
            self._reset_spotify_playback()
            self._publish_spotify_playback()

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
                print(f"[CastBridge] No __NEXT_DATA__ found for track {track_id}")
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
            print(f"[CastBridge] Spotify metadata: {metadata['artist']} - {metadata['title']}")
            return metadata

        except (URLError, json.JSONDecodeError, KeyError) as e:
            print(f"[CastBridge] Failed to fetch Spotify metadata for {track_id}: {e}")
            return None

    def _handle_spotify_event(self, client, userdata, msg):
        """Handle raw Spotify events from librespot onevent script"""
        try:
            data = json.loads(msg.payload)
        except json.JSONDecodeError:
            return

        event = data.get("event", "")
        track_uri = data.get("track_id", "")

        # Extract bare track ID from spotify:track:XXXXX URI
        track_id = track_uri.split(":")[-1] if ":" in track_uri else track_uri

        if event == "track_changed":
            # track_changed provides full metadata from librespot
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
                # Fallback to embed scraping if no covers provided
                threading.Thread(
                    target=self._fetch_and_update_spotify_metadata,
                    args=(track_id,),
                    daemon=True,
                ).start()
            print(f"[CastBridge] Spotify track: {artists} - {name}")
            return  # Don't publish yet, playing event follows

        elif event in ("playing", "started"):
            self._spotify_playback["playing"] = True
            self._spotify_position_ref = data.get("position_ms", 0)
            self._spotify_position_time = time.monotonic()
            # If track_id changed without a track_changed event (e.g. on startup),
            # fetch metadata via embed scraper
            if track_id and track_id != self._spotify_playback["track_id"]:
                self._spotify_playback["track_id"] = track_id
                threading.Thread(
                    target=self._fetch_and_update_spotify_metadata,
                    args=(track_id,),
                    daemon=True,
                ).start()
            self._start_spotify_ticker()
            return  # Ticker will publish

        elif event in ("seeked", "position_correction"):
            self._spotify_position_ref = data.get("position_ms", 0)
            self._spotify_position_time = time.monotonic()
            # Ticker keeps running, next tick picks up the new ref

        elif event == "paused":
            self._spotify_playback["playing"] = False
            self._spotify_playback["position_ms"] = data.get("position_ms", 0)
            self._stop_spotify_ticker()

        elif event in ("stopped", "unavailable", "end_of_track"):
            self._spotify_playback["playing"] = False
            self._stop_spotify_ticker()

        elif event in ("volume_changed", "loading", "preloading",
                        "preload_next", "session_connected",
                        "session_disconnected", "session_client_changed",
                        "shuffle_changed", "repeat_changed",
                        "auto_play_changed", "filter_explicit_content_changed",
                        "sink", "play_request_id_changed", "added_to_queue"):
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

        # Spotify playback events from librespot onevent script
        self.mqtt.subscribe("protogen/fins/castbridge/spotify/event")
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/spotify/event",
            self._handle_spotify_event,
        )
        print("[CastBridge] Subscribed to protogen/fins/castbridge/spotify/event")

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
            lambda c, u, m: self._handle_airplay_play_state(False)
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
        """Handle play_start/play_end/play_resume/play_flush events"""
        self._airplay_playback["playing"] = playing
        if not playing:
            # Reset references so next phbt after resume waits for fresh prgr
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
            print(f"[CastBridge] Error parsing astm: {e}")

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
                self._publish_airplay_playback()
        except Exception as e:
            print(f"[CastBridge] Error parsing prgr: {e}")

    def _handle_airplay_phbt(self, client, userdata, msg):
        """Handle ssnc/phbt (frame position / monotonic time) - fires every second"""
        if not self._airplay_playback["playing"]:
            return
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
            parts = payload.split("/")
            if len(parts) == 2:
                frame = int(parts[0])
                prgr_start = self._airplay_playback.get("prgr_start", 0)
                if not prgr_start:
                    # No prgr reference yet (e.g. just resumed) — skip until prgr arrives
                    return
                self._airplay_playback["position_ms"] = int((frame - prgr_start) / 44100 * 1000)
                self._publish_airplay_playback()
        except Exception as e:
            print(f"[CastBridge] Error parsing phbt: {e}")

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

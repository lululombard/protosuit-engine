"""
Lyrics Service - Real-time synced lyrics via MQTT
Subscribes to playback state from CastBridge, fetches lyrics from lrclib.net,
and publishes current/next line + full lyrics to MQTT topics.
"""

import json
import re
import time
import bisect
import threading
from urllib.request import urlopen, Request
from urllib.parse import quote
from urllib.error import URLError, HTTPError


class LyricsService:
    def __init__(self):
        self.mqtt = None
        self._priority = ["spotify", "airplay"]
        self._tick_interval = 0.25

        # Per-service playback state (updated from MQTT)
        self._spotify = {"playing": False, "title": "", "artist": "", "position_ms": 0, "duration_ms": 0}
        self._airplay = {"playing": False, "title": "", "artist": "", "position_ms": 0, "duration_ms": 0}
        self._spotify_update_time = 0.0  # time.monotonic() of last position update
        self._airplay_update_time = 0.0

        # Per-service lyrics and the track key they correspond to
        self._spotify_lyrics = None
        self._airplay_lyrics = None
        self._spotify_track_key = ("", "")  # (artist_lower, title_lower)
        self._airplay_track_key = ("", "")

        # Fetch guards: track key currently being fetched per service
        self._spotify_fetching = ("", "")
        self._airplay_fetching = ("", "")

        # LRU cache: [(key, lyrics_data | None), ...] — max 3 entries
        self._cache = []
        self._cache_max = 3

        # Placeholder titles to ignore
        self._skip_titles = {"chargement", "chargement…", "loading", "loading…", "loading..."}

        # Ticker state
        self._ticker = None
        self._last_line_idx = -1
        self._last_active_key = ("", "", "")  # (service, artist, title)
        self._last_had_lyrics = False  # Track whether we had lyrics last tick

    def start(self, mqtt_client, config):
        """Start the lyrics service"""
        self.mqtt = mqtt_client

        lyrics_config = config.get("cast", {}).get("lyrics", {})
        self._priority = lyrics_config.get("priority", ["spotify", "airplay"])
        self._tick_interval = lyrics_config.get("tick_interval", 0.25)

        # Subscribe to playback topics
        self.mqtt.subscribe("protogen/fins/castbridge/status/spotify/playback")
        self.mqtt.subscribe("protogen/fins/castbridge/status/airplay/playback")

        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/status/spotify/playback",
            lambda c, u, m: self._on_playback("spotify", m),
        )
        self.mqtt.message_callback_add(
            "protogen/fins/castbridge/status/airplay/playback",
            lambda c, u, m: self._on_playback("airplay", m),
        )

        # Start ticker
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
        self._ticker.start()

        print("[Lyrics] Started")

    def stop(self):
        """Stop the lyrics service"""
        self._ticker = None
        self._publish_clear()
        print("[Lyrics] Stopped")

    # ======== MQTT Handlers ========

    def _on_playback(self, service, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        state = self._spotify if service == "spotify" else self._airplay
        state["playing"] = data.get("playing", False)
        state["title"] = data.get("title", "")
        state["artist"] = data.get("artist", "")
        state["position_ms"] = data.get("position_ms", 0)
        state["duration_ms"] = data.get("duration_ms", 0)
        if service == "spotify":
            self._spotify_update_time = time.monotonic()
        else:
            self._airplay_update_time = time.monotonic()

        # Check if track changed — skip placeholder titles
        new_key = (state["artist"].lower().strip(), state["title"].lower().strip())
        if not new_key[0] or not new_key[1]:
            return
        if new_key[1] in self._skip_titles or new_key[0] in self._skip_titles:
            return

        if service == "spotify":
            current_key = self._spotify_track_key
            fetching = self._spotify_fetching
        else:
            current_key = self._airplay_track_key
            fetching = self._airplay_fetching

        # Only fetch if this is a new track AND we're not already fetching it
        if new_key != current_key and new_key != fetching:
            # Clear old lyrics immediately and publish loading state
            if service == "spotify":
                self._spotify_lyrics = None
                self._spotify_fetching = new_key
            else:
                self._airplay_lyrics = None
                self._airplay_fetching = new_key
            self._last_line_idx = -99
            self._last_had_lyrics = False
            self._publish_loading(service)
            threading.Thread(
                target=self._fetch_and_assign,
                args=(service, state["artist"], state["title"], new_key),
                daemon=True,
            ).start()

    def _fetch_and_assign(self, service, artist, title, track_key):
        cache_key = (artist.lower().strip(), title.lower().strip())
        lyrics = None
        for attempt in range(3):
            lyrics = self._fetch_lyrics(artist, title)
            if lyrics is not None:
                break
            # If it's cached as not-found (404), don't retry
            _, cached = self._cache_get(cache_key)
            if cached:
                break
            if attempt < 2:
                print(f"[Lyrics] Retry {attempt + 1}/2 for {artist} - {title}")
                time.sleep(2)

        if service == "spotify":
            self._spotify_lyrics = lyrics
            self._spotify_track_key = track_key
            self._spotify_fetching = ("", "")
        else:
            self._airplay_lyrics = lyrics
            self._airplay_track_key = track_key
            self._airplay_fetching = ("", "")
        # Reset ticker state to force re-evaluation
        self._last_line_idx = -99
        self._last_had_lyrics = False
        self._publish_full_lyrics()

    # ======== Lyrics Fetching ========

    def _cache_get(self, key):
        for i, (k, v) in enumerate(self._cache):
            if k == key:
                # Move to end (most recent)
                self._cache.append(self._cache.pop(i))
                return v, True
        return None, False

    def _cache_put(self, key, value):
        # Remove existing entry if present
        self._cache = [(k, v) for k, v in self._cache if k != key]
        self._cache.append((key, value))
        # Evict oldest if over limit
        while len(self._cache) > self._cache_max:
            self._cache.pop(0)

    def _fetch_lyrics(self, artist, title):
        if not artist or not title:
            return None

        cache_key = (artist.lower().strip(), title.lower().strip())
        cached, found = self._cache_get(cache_key)
        if found:
            return cached

        url = f"https://lrclib.net/api/get?artist_name={quote(artist)}&track_name={quote(title)}"
        try:
            req = Request(url, headers={"User-Agent": "CastBridge/1.0"})
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                synced = self._parse_lrc(data.get("syncedLyrics", ""))
                lyrics_data = {
                    "track_name": data.get("trackName", title),
                    "artist_name": data.get("artistName", artist),
                    "synced": synced,
                    "timestamps": [ts for ts, _ in synced],
                    "plain": data.get("plainLyrics", ""),
                    "instrumental": data.get("instrumental", False),
                    "duration": data.get("duration", 0.0),
                }
                self._cache_put(cache_key, lyrics_data)
                print(f"[Lyrics] Fetched: {artist} - {title} ({len(synced)} synced lines)")
                return lyrics_data
        except HTTPError as e:
            if e.code == 404:
                # Track not found — cache so we don't retry
                self._cache_put(cache_key, None)
                print(f"[Lyrics] Not found: {artist} - {title}")
            else:
                # Server error — don't cache, allow retry
                print(f"[Lyrics] HTTP {e.code} for {artist} - {title}")
            return None
        except Exception as e:
            # Network error — don't cache, allow retry
            print(f"[Lyrics] Fetch error for {artist} - {title}: {e}")
            return None

    # ======== LRC Parsing ========

    _LRC_RE = re.compile(r"\[(\d+):(\d+)\.(\d+)\]\s*(.*)")

    def _parse_lrc(self, lrc_text):
        if not lrc_text:
            return []
        lines = []
        for raw in lrc_text.strip().split("\n"):
            m = self._LRC_RE.match(raw.strip())
            if m:
                minutes, seconds, frac_str, text = m.group(1), m.group(2), m.group(3), m.group(4)
                frac = int(frac_str) * 10 if len(frac_str) == 2 else int(frac_str[:3])
                ts_ms = (int(minutes) * 60 + int(seconds)) * 1000 + frac
                lines.append((ts_ms, text.strip()))
        lines.sort(key=lambda x: x[0])
        return lines

    # ======== Priority & Position ========

    def _get_active_service(self):
        playing = []
        if self._spotify["playing"]:
            playing.append("spotify")
        if self._airplay["playing"]:
            playing.append("airplay")
        if not playing:
            return None
        for svc in self._priority:
            if svc in playing:
                return svc
        return playing[0]

    def _get_lyrics(self, service):
        return self._spotify_lyrics if service == "spotify" else self._airplay_lyrics

    def _get_position(self, service):
        state = self._spotify if service == "spotify" else self._airplay
        pos = state["position_ms"]
        if state["playing"]:
            update_time = self._spotify_update_time if service == "spotify" else self._airplay_update_time
            if update_time > 0:
                elapsed_ms = (time.monotonic() - update_time) * 1000
                pos = int(pos + elapsed_ms)
                duration = state["duration_ms"]
                if duration > 0:
                    pos = min(pos, duration)
        return pos

    def _find_current_line(self, timestamps, position_ms):
        if not timestamps:
            return -1
        return bisect.bisect_right(timestamps, position_ms) - 1

    # ======== Ticker ========

    def _tick_loop(self):
        ticker_ref = self._ticker
        while ticker_ref is self._ticker:
            try:
                service = self._get_active_service()
                if service is None:
                    if self._last_line_idx != -2:
                        self._publish_clear()
                    time.sleep(self._tick_interval)
                    continue

                lyrics = self._get_lyrics(service)
                position_ms = self._get_position(service)

                # Check if active source changed
                state = self._spotify if service == "spotify" else self._airplay
                new_key = (service, state["artist"], state["title"])
                if new_key != self._last_active_key:
                    self._last_active_key = new_key
                    self._last_line_idx = -99
                    self._last_had_lyrics = False

                has_lyrics = lyrics is not None and bool(lyrics.get("synced"))

                # If lyrics just became available (fetch completed), reset line index
                if has_lyrics and not self._last_had_lyrics:
                    self._last_had_lyrics = True
                    self._last_line_idx = -99

                if not has_lyrics:
                    self._last_had_lyrics = False
                    if self._last_line_idx != -3:
                        self._publish_lyrics_status(service, position_ms, lyrics)
                        self._last_line_idx = -3
                    time.sleep(self._tick_interval)
                    continue

                idx = self._find_current_line(lyrics["timestamps"], position_ms)

                if idx != self._last_line_idx:
                    self._last_line_idx = idx
                    synced = lyrics["synced"]

                    current_text = synced[idx][1] if idx >= 0 else ""
                    current_ts = synced[idx][0] if idx >= 0 else 0
                    next_text = synced[idx + 1][1] if idx + 1 < len(synced) else ""
                    next_ts = synced[idx + 1][0] if idx + 1 < len(synced) else 0

                    self._publish_lyrics_line(
                        service, current_text, next_text,
                        current_ts, next_ts, idx, len(synced), position_ms,
                    )

            except Exception as e:
                print(f"[Lyrics] Tick error: {e}")

            time.sleep(self._tick_interval)

    # ======== MQTT Publishing ========

    def _publish_lyrics_line(self, service, current_line, next_line,
                             current_ts, next_ts, line_index, total_lines, position_ms):
        payload = {
            "source": service,
            "playing": True,
            "current_line": current_line,
            "next_line": next_line,
            "current_line_ts": current_ts,
            "next_line_ts": next_ts,
            "line_index": line_index,
            "total_lines": total_lines,
            "position_ms": position_ms,
        }
        self.mqtt.publish(
            "protogen/fins/castbridge/status/lyrics",
            json.dumps(payload),
            retain=True,
        )

    def _publish_full_lyrics(self):
        service = self._get_active_service()
        lyrics = self._get_lyrics(service) if service else None

        if lyrics and lyrics.get("synced"):
            payload = {
                "source": service,
                "track_name": lyrics["track_name"],
                "artist_name": lyrics["artist_name"],
                "instrumental": lyrics.get("instrumental", False),
                "synced_lines": [{"ts": ts, "text": text} for ts, text in lyrics["synced"]],
                "plain": lyrics.get("plain", ""),
            }
        else:
            payload = {
                "source": service or "",
                "track_name": "",
                "artist_name": "",
                "instrumental": lyrics.get("instrumental", False) if lyrics else False,
                "synced_lines": [],
                "plain": lyrics.get("plain", "") if lyrics else "",
            }

        self.mqtt.publish(
            "protogen/fins/castbridge/status/lyrics/full",
            json.dumps(payload),
            retain=True,
        )

    def _is_fetching(self, service):
        fetching = self._spotify_fetching if service == "spotify" else self._airplay_fetching
        return fetching != ("", "")

    def _publish_lyrics_status(self, service, position_ms, lyrics):
        payload = {
            "source": service,
            "playing": True,
            "loading": self._is_fetching(service),
            "current_line": "",
            "next_line": "",
            "current_line_ts": 0,
            "next_line_ts": 0,
            "line_index": -1,
            "total_lines": 0,
            "position_ms": position_ms,
            "instrumental": lyrics.get("instrumental", False) if lyrics else False,
        }
        self.mqtt.publish(
            "protogen/fins/castbridge/status/lyrics",
            json.dumps(payload),
            retain=True,
        )

    def _publish_loading(self, service):
        """Publish loading state — clears old lyrics and signals fetch in progress"""
        loading = {
            "source": service,
            "playing": True,
            "loading": True,
            "current_line": "",
            "next_line": "",
            "current_line_ts": 0,
            "next_line_ts": 0,
            "line_index": -1,
            "total_lines": 0,
            "position_ms": 0,
        }
        self.mqtt.publish("protogen/fins/castbridge/status/lyrics", json.dumps(loading), retain=True)
        loading_full = {
            "source": service,
            "loading": True,
            "track_name": "",
            "artist_name": "",
            "instrumental": False,
            "synced_lines": [],
            "plain": "",
        }
        self.mqtt.publish("protogen/fins/castbridge/status/lyrics/full", json.dumps(loading_full), retain=True)

    def _publish_clear(self):
        self._last_line_idx = -2
        self._last_active_key = ("", "", "")
        self._last_had_lyrics = False
        empty = {
            "source": "",
            "playing": False,
            "current_line": "",
            "next_line": "",
            "current_line_ts": 0,
            "next_line_ts": 0,
            "line_index": -1,
            "total_lines": 0,
            "position_ms": 0,
        }
        self.mqtt.publish("protogen/fins/castbridge/status/lyrics", json.dumps(empty), retain=True)
        empty_full = {
            "source": "",
            "track_name": "",
            "artist_name": "",
            "instrumental": False,
            "synced_lines": [],
            "plain": "",
        }
        self.mqtt.publish("protogen/fins/castbridge/status/lyrics/full", json.dumps(empty_full), retain=True)

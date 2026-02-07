#!/usr/bin/env python3
"""
Now Playing - Dual display album art + lyrics viewer
Subscribes to CastBridge MQTT topics for playback info and synced lyrics.
"""

import pygame
import json
import io
import os
import threading
from urllib.request import urlopen, Request
import paho.mqtt.client as mqtt


# Colors
COLOR_BG = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (160, 160, 160)
COLOR_DIM = (80, 80, 80)
COLOR_ACCENT = (100, 200, 255)
COLOR_BAR_BG = (40, 40, 40)
COLOR_BAR_FILL = (100, 200, 255)

ART_SIZE = 300
PROGRESS_WIDTH = 500
PROGRESS_HEIGHT = 6


class NowPlayingApp:
    def __init__(self, width=1440, height=720):
        pygame.init()

        self.width = width
        self.height = height
        self.half_width = width // 2

        os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
        self.screen = pygame.display.set_mode((width, height), pygame.NOFRAME)
        pygame.display.set_caption("Now Playing")

        self.clock = pygame.time.Clock()

        # Fonts
        self.font_title = pygame.font.Font(None, 52)
        self.font_artist = pygame.font.Font(None, 38)
        self.font_time = pygame.font.Font(None, 30)
        self.font_lyric = pygame.font.Font(None, 40)
        self.font_lyric_current = pygame.font.Font(None, 48)
        self.font_idle = pygame.font.Font(None, 60)

        # Playback state
        self._spotify = {"playing": False, "title": "", "artist": "", "cover_url": "", "position_ms": 0, "duration_ms": 0}
        self._airplay = {"playing": False, "title": "", "artist": "", "album": "", "position_ms": 0, "duration_ms": 0}

        # Lyrics state
        self._lyrics = {"source": "", "playing": False, "loading": False, "current_line": "", "next_line": "", "line_index": -1, "total_lines": 0}
        self._lyrics_full = []  # [{ts, text}, ...]

        # Cover art surfaces
        self._airplay_cover = None  # pygame.Surface
        self._spotify_cover = None  # pygame.Surface
        self._spotify_cover_url = ""  # currently loaded URL

        # MQTT
        self._mqtt = None
        self._connect_mqtt()

    def _connect_mqtt(self):
        self._mqtt = mqtt.Client(
            client_id="protosuit-nowplaying-" + os.urandom(4).hex(),
            clean_session=True,
        )

        def on_connect(client, userdata, flags, rc, *args):
            client.subscribe("protogen/fins/castbridge/status/spotify/playback")
            client.subscribe("protogen/fins/castbridge/status/airplay/playback")
            client.subscribe("protogen/fins/castbridge/status/airplay/playback/cover")
            client.subscribe("protogen/fins/castbridge/status/lyrics")
            client.subscribe("protogen/fins/castbridge/status/lyrics/full")
            print("[NowPlaying] MQTT connected, subscribed")

        def on_message(client, userdata, msg):
            topic = msg.topic
            try:
                if topic == "protogen/fins/castbridge/status/airplay/playback/cover":
                    self._handle_airplay_cover(msg.payload)
                elif topic == "protogen/fins/castbridge/status/spotify/playback":
                    data = json.loads(msg.payload)
                    self._spotify.update({k: data.get(k, v) for k, v in self._spotify.items()})
                    # Fetch cover art if URL changed
                    url = data.get("cover_url", "")
                    if url and url != self._spotify_cover_url:
                        self._spotify_cover_url = url
                        threading.Thread(target=self._fetch_spotify_cover, args=(url,), daemon=True).start()
                elif topic == "protogen/fins/castbridge/status/airplay/playback":
                    data = json.loads(msg.payload)
                    self._airplay.update({k: data.get(k, v) for k, v in self._airplay.items()})
                elif topic == "protogen/fins/castbridge/status/lyrics":
                    data = json.loads(msg.payload)
                    self._lyrics.update({k: data.get(k, v) for k, v in self._lyrics.items()})
                    self._lyrics["loading"] = data.get("loading", False)
                elif topic == "protogen/fins/castbridge/status/lyrics/full":
                    data = json.loads(msg.payload)
                    self._lyrics_full = data.get("synced_lines", [])
            except Exception as e:
                print(f"[NowPlaying] MQTT parse error: {e}")

        self._mqtt.on_connect = on_connect
        self._mqtt.on_message = on_message
        self._mqtt.connect("localhost", 1883, 60)
        self._mqtt.loop_start()

    def _handle_airplay_cover(self, data):
        if not data or len(data) == 0:
            self._airplay_cover = None
            return
        try:
            img = pygame.image.load(io.BytesIO(data))
            self._airplay_cover = pygame.transform.smoothscale(img, (ART_SIZE, ART_SIZE))
        except Exception as e:
            print(f"[NowPlaying] Failed to load AirPlay cover: {e}")
            self._airplay_cover = None

    def _fetch_spotify_cover(self, url):
        try:
            req = Request(url, headers={"User-Agent": "CastBridge/1.0"})
            with urlopen(req, timeout=5) as resp:
                data = resp.read()
            img = pygame.image.load(io.BytesIO(data))
            self._spotify_cover = pygame.transform.smoothscale(img, (ART_SIZE, ART_SIZE))
        except Exception as e:
            print(f"[NowPlaying] Failed to load Spotify cover: {e}")

    def _get_active(self):
        """Return (state_dict, cover_surface) for the active service, or None"""
        # Follow the lyrics source if available, else pick whichever is playing
        source = self._lyrics.get("source", "")
        if source == "spotify" and self._spotify["playing"]:
            return self._spotify, self._spotify_cover
        if source == "airplay" and self._airplay["playing"]:
            return self._airplay, self._airplay_cover
        # Fallback
        if self._spotify["playing"]:
            return self._spotify, self._spotify_cover
        if self._airplay["playing"]:
            return self._airplay, self._airplay_cover
        return None, None

    def _format_time(self, ms):
        total_sec = max(0, int(ms / 1000))
        m = total_sec // 60
        s = total_sec % 60
        return f"{m}:{s:02d}"

    def _draw_display(self, cx, cy):
        """Draw now-playing UI centered at (cx, cy) within a 720x720 area"""
        state, cover = self._get_active()

        if state is None:
            # Nothing playing — show idle text
            idle = self.font_idle.render("No music playing", True, COLOR_DIM)
            self.screen.blit(idle, idle.get_rect(center=(cx, cy)))
            return

        y = 40  # top padding

        # Album art
        if cover:
            art_rect = cover.get_rect(center=(cx, y + ART_SIZE // 2))
            self.screen.blit(cover, art_rect)
            y += ART_SIZE + 20
        else:
            # Placeholder box
            placeholder = pygame.Rect(cx - ART_SIZE // 2, y, ART_SIZE, ART_SIZE)
            pygame.draw.rect(self.screen, COLOR_BAR_BG, placeholder)
            y += ART_SIZE + 20

        # Title
        title = state.get("title", "")
        if title:
            title_surf = self.font_title.render(title, True, COLOR_WHITE)
            # Clip to display width
            if title_surf.get_width() > self.half_width - 40:
                title_surf = pygame.transform.smoothscale(
                    title_surf,
                    (self.half_width - 40, title_surf.get_height())
                )
            self.screen.blit(title_surf, title_surf.get_rect(center=(cx, y + 15)))
            y += 40

        # Artist
        artist = state.get("artist", "")
        if artist:
            artist_surf = self.font_artist.render(artist, True, COLOR_GRAY)
            if artist_surf.get_width() > self.half_width - 40:
                artist_surf = pygame.transform.smoothscale(
                    artist_surf,
                    (self.half_width - 40, artist_surf.get_height())
                )
            self.screen.blit(artist_surf, artist_surf.get_rect(center=(cx, y + 12)))
            y += 35

        # Progress bar
        y += 15
        duration = state.get("duration_ms", 0)
        position = state.get("position_ms", 0)
        bar_x = cx - PROGRESS_WIDTH // 2
        bar_y = y

        # Background
        pygame.draw.rect(self.screen, COLOR_BAR_BG,
                         (bar_x, bar_y, PROGRESS_WIDTH, PROGRESS_HEIGHT),
                         border_radius=3)
        # Fill
        if duration > 0:
            fill_w = int((position / duration) * PROGRESS_WIDTH)
            fill_w = min(fill_w, PROGRESS_WIDTH)
            if fill_w > 0:
                pygame.draw.rect(self.screen, COLOR_BAR_FILL,
                                 (bar_x, bar_y, fill_w, PROGRESS_HEIGHT),
                                 border_radius=3)

        # Times
        y += PROGRESS_HEIGHT + 6
        time_current = self.font_time.render(self._format_time(position), True, COLOR_GRAY)
        time_total = self.font_time.render(self._format_time(duration), True, COLOR_GRAY)
        self.screen.blit(time_current, (bar_x, y))
        self.screen.blit(time_total, (bar_x + PROGRESS_WIDTH - time_total.get_width(), y))
        y += 35

        # Lyrics
        y += 10

        # Show loading indicator while fetching lyrics
        if self._lyrics.get("loading"):
            loading_surf = self.font_lyric.render("Loading lyrics...", True, COLOR_DIM)
            self.screen.blit(loading_surf, loading_surf.get_rect(center=(cx, y + 45)))
            return

        line_idx = self._lyrics.get("line_index", -1)
        current_line = self._lyrics.get("current_line", "")
        next_line = self._lyrics.get("next_line", "")

        # Previous line (from full lyrics if available)
        prev_line = ""
        if self._lyrics_full and line_idx > 0:
            prev_line = self._lyrics_full[line_idx - 1].get("text", "")
        elif self._lyrics_full and line_idx == 0:
            prev_line = ""

        # Draw previous line (dimmed)
        if prev_line:
            prev_surf = self.font_lyric.render(prev_line, True, COLOR_DIM)
            if prev_surf.get_width() > self.half_width - 40:
                prev_surf = pygame.transform.smoothscale(
                    prev_surf, (self.half_width - 40, prev_surf.get_height()))
            self.screen.blit(prev_surf, prev_surf.get_rect(center=(cx, y)))
        y += 40

        # Draw current line (bright, larger)
        if current_line:
            curr_surf = self.font_lyric_current.render(current_line, True, COLOR_ACCENT)
            if curr_surf.get_width() > self.half_width - 30:
                curr_surf = pygame.transform.smoothscale(
                    curr_surf, (self.half_width - 30, curr_surf.get_height()))
            self.screen.blit(curr_surf, curr_surf.get_rect(center=(cx, y)))
        y += 50

        # Draw next line (dimmed)
        if next_line:
            next_surf = self.font_lyric.render(next_line, True, COLOR_DIM)
            if next_surf.get_width() > self.half_width - 40:
                next_surf = pygame.transform.smoothscale(
                    next_surf, (self.half_width - 40, next_surf.get_height()))
            self.screen.blit(next_surf, next_surf.get_rect(center=(cx, y)))

    def draw(self):
        self.screen.fill(COLOR_BG)

        left_cx = self.half_width // 2
        right_cx = self.half_width + self.half_width // 2
        cy = self.height // 2

        self._draw_display(left_cx, cy)
        self._draw_display(right_cx, cy)

        pygame.display.flip()

    def run(self):
        print("[NowPlaying] Running...")
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False

            self.draw()
            self.clock.tick(30)

        print("[NowPlaying] Exiting")
        self._mqtt.loop_stop()
        self._mqtt.disconnect()
        pygame.quit()


def main():
    width = int(os.environ.get('PROTOSUIT_DISPLAY_WIDTH', 720)) * 2
    height = int(os.environ.get('PROTOSUIT_DISPLAY_HEIGHT', 720))

    print(f"[NowPlaying] Starting with display size: {width}x{height}")

    app = NowPlayingApp(width, height)
    app.run()


if __name__ == "__main__":
    main()

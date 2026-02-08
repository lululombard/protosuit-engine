#!/usr/bin/env python3
"""
Now Playing - Dual display album art + lyrics viewer
Subscribes to CastBridge MQTT topics for playback info and synced lyrics.
"""

import pygame
import pygame.gfxdraw
import json
import io
import os
import math
import time
import threading
from urllib.request import urlopen, Request
import paho.mqtt.client as mqtt


# Colors
COLOR_BG = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (160, 160, 160)
COLOR_DIM = (80, 80, 80)
COLOR_ACCENT = (255, 255, 255)
COLOR_BAR_BG = (40, 40, 40)
COLOR_BAR_FILL = (255, 255, 255)

ART_SIZE = 250

# Arc layout for circular displays
PROGRESS_ARC_SPAN = math.radians(270)  # arc around the display
PROGRESS_ARC_WIDTH = 16
PROGRESS_ARC_RESOLUTION = 16

DEBUG = os.environ.get("DEBUG", "0") == "1"


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

        # HQ fonts for arc text (2x for supersampled anti-aliasing)
        self.font_title_hq = pygame.font.Font(None, 104)
        self.font_artist_hq = pygame.font.Font(None, 76)

        # Playback state
        self._spotify = {"playing": False, "title": "", "artist": "", "cover_url": "", "position_ms": 0, "duration_ms": 0}
        self._airplay = {"playing": False, "title": "", "artist": "", "album": "", "position_ms": 0, "duration_ms": 0}
        self._spotify_pos_time = 0.0
        self._airplay_pos_time = 0.0

        # Lyrics state
        self._lyrics = {"source": "", "playing": False, "loading": False, "current_line": "", "next_line": "", "line_index": -1, "total_lines": 0}
        self._lyrics_full = []  # [{ts, text}, ...]

        # Cover art surfaces
        self._airplay_cover = None  # pygame.Surface
        self._spotify_cover = None  # pygame.Surface
        self._spotify_cover_url = ""  # currently loaded URL

        # Blurred background surfaces (generated from cover art)
        self._airplay_bg = None
        self._spotify_bg = None

        # Cached progress arc surfaces
        self._arc_bg_cache = None
        self._arc_fill_full = None
        self._arc_fill_cache = None
        self._arc_fill_pixel = -1
        self._arc_masked = None
        self._arc_erase = None
        self._arc_bbox = 0

        # Cached arc text renders (keyed by text content)
        self._arc_text_cache = {}

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
                    self._spotify_pos_time = time.monotonic()
                    # Fetch cover art if URL changed
                    url = data.get("cover_url", "")
                    if url and url != self._spotify_cover_url:
                        self._spotify_cover_url = url
                        threading.Thread(target=self._fetch_spotify_cover, args=(url,), daemon=True).start()
                elif topic == "protogen/fins/castbridge/status/airplay/playback":
                    data = json.loads(msg.payload)
                    self._airplay.update({k: data.get(k, v) for k, v in self._airplay.items()})
                    self._airplay_pos_time = time.monotonic()
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

    def _make_bg(self, cover):
        """Create a blurred, darkened background from cover art (Apple Music style)"""
        if cover is None:
            return None
        # Scale down to tiny size for extreme blur, then back up
        tiny = pygame.transform.smoothscale(cover, (6, 6))
        bg = pygame.transform.smoothscale(tiny, (self.half_width, self.height))
        # Darken so text remains readable
        dark = pygame.Surface((self.half_width, self.height))
        dark.fill((0, 0, 0))
        dark.set_alpha(140)
        bg.blit(dark, (0, 0))
        return bg

    def _draw_arc_text(self, text, font, color, cx, cy, radius, max_angle=math.radians(120),
                       hq_font=None):
        """Draw text along a circular arc centered at the top of the circle.
        Convention: 0 = top (12 o'clock), angle increases clockwise.
        Caches the rendered result — rotozoom only runs when text changes."""
        if not text:
            return

        scale = 2 if hq_font else 1
        render_font = hq_font if hq_font else font
        cache_key = (text, id(render_font), color, radius, max_angle)

        if cache_key not in self._arc_text_cache:
            # Render each character (at HQ resolution if available)
            char_surfs = []
            total_width = 0
            for ch in text:
                surf = render_font.render(ch, True, color)
                char_surfs.append(surf)
                total_width += surf.get_width()

            if total_width == 0:
                return

            display_width = total_width / scale
            span = display_width / radius

            # Compress characters horizontally if too wide (like lyrics)
            if span > max_angle:
                target_width = max_angle * radius * scale
                ratio = target_width / total_width
                compressed = []
                for surf in char_surfs:
                    new_w = max(int(surf.get_width() * ratio), 1)
                    compressed.append(pygame.transform.smoothscale(
                        surf, (new_w, surf.get_height())))
                char_surfs = compressed
                total_width = sum(s.get_width() for s in char_surfs)
                display_width = total_width / scale
                span = display_width / radius

            # Render all chars onto a temp SRCALPHA surface, then crop
            margin = 60
            cache_size = int((radius + margin) * 2)
            tmp = pygame.Surface((cache_size, cache_size), pygame.SRCALPHA)
            cache_c = cache_size // 2

            angle = -span / 2
            for surf in char_surfs:
                char_span = (surf.get_width() / scale) / radius
                char_center = angle + char_span / 2

                x = cache_c + radius * math.sin(char_center)
                y = cache_c - radius * math.cos(char_center)

                rotated = pygame.transform.rotozoom(surf, -math.degrees(char_center),
                                                    1.0 / scale)
                rect = rotated.get_rect(center=(int(x), int(y)))
                tmp.blit(rotated, rect)

                angle += char_span

            # Crop to tight bounding box, convert to colorkey for fast blitting
            bounds = tmp.get_bounding_rect()
            cropped = tmp.subsurface(bounds).copy()
            ck_surf = pygame.Surface((bounds.width, bounds.height))
            ck_surf.fill((0, 0, 0))
            ck_surf.set_colorkey((0, 0, 0))
            ck_surf.blit(cropped, (0, 0))
            self._arc_text_cache[cache_key] = (ck_surf, bounds.x - cache_c, bounds.y - cache_c)

        cached, ox, oy = self._arc_text_cache[cache_key]
        self.screen.blit(cached, (cx + ox, cy + oy))

    def _draw_arc_raw(self, surface, cx, cy, radius, start_deg, end_deg, color, width):
        """Draw arc as filled polygon with rounded end caps (smooth edges for supersampling)."""
        outer_r = radius + width // 2
        inner_r = radius - width // 2
        num_pts = max(int(abs(end_deg - start_deg) * 2), 20)

        # Build polygon: outer edge forward, then inner edge backward
        pts = []
        for i in range(num_pts + 1):
            angle = math.radians(start_deg + (end_deg - start_deg) * i / num_pts)
            pts.append((int(cx + outer_r * math.cos(angle)),
                        int(cy + outer_r * math.sin(angle))))
        for i in range(num_pts, -1, -1):
            angle = math.radians(start_deg + (end_deg - start_deg) * i / num_pts)
            pts.append((int(cx + inner_r * math.cos(angle)),
                        int(cy + inner_r * math.sin(angle))))
        pygame.draw.polygon(surface, color, pts)

        # Rounded end caps
        cap_r = width // 2
        for deg in (start_deg, end_deg):
            a = math.radians(deg)
            pygame.draw.circle(surface, color, (int(cx + radius * math.cos(a)),
                                                int(cy + radius * math.sin(a))), cap_r)

    def _draw_arc_progress(self, cx, cy, radius, position_ms, duration_ms):
        """Draw progress bar arc with true alpha AA.
        Both arcs pre-rendered at 8x supersample as SRCALPHA (preserves AA).
        Masking via BLEND_RGBA_SUB to zero alpha in unfilled region.
        Fill direction: left to right."""
        pad = PROGRESS_ARC_WIDTH // 2 + 2
        bbox = int((radius + pad) * 2)

        span_deg = math.degrees(PROGRESS_ARC_SPAN)
        start_deg = 90 - span_deg / 2   # right side of arc
        end_deg = 90 + span_deg / 2     # left side of arc

        half = bbox // 2

        # One-time: pre-render both arcs with 8x supersampled anti-aliasing
        if self._arc_bg_cache is None:
            SCALE = 8
            ss_size = bbox * SCALE
            ss = pygame.Surface((ss_size, ss_size), pygame.SRCALPHA)

            # Background arc (gray) — keep as SRCALPHA for true AA
            self._draw_arc_raw(ss, ss_size // 2, ss_size // 2, radius * SCALE,
                               start_deg, end_deg, COLOR_BAR_BG, PROGRESS_ARC_WIDTH * SCALE)
            self._arc_bg_cache = pygame.transform.smoothscale(ss, (bbox, bbox))

            # Full fill arc (white) — keep as SRCALPHA for true AA
            ss.fill((0, 0, 0, 0))
            self._draw_arc_raw(ss, ss_size // 2, ss_size // 2, radius * SCALE,
                               start_deg, end_deg, COLOR_BAR_FILL, PROGRESS_ARC_WIDTH * SCALE)
            self._arc_fill_full = pygame.transform.smoothscale(ss, (bbox, bbox))

            # Pre-allocate work surfaces (SRCALPHA)
            self._arc_masked = pygame.Surface((bbox, bbox), pygame.SRCALPHA)
            self._arc_erase = pygame.Surface((bbox, bbox), pygame.SRCALPHA)
            self._arc_fill_cache = None
            self._arc_bbox = bbox

        blit_pos = (cx - half, cy - half)
        self.screen.blit(self._arc_bg_cache, blit_pos)

        if duration_ms > 0 and position_ms > 0:
            progress = min(position_ms / duration_ms, 1.0)
            step = int(progress * span_deg * PROGRESS_ARC_RESOLUTION)

            if step != self._arc_fill_pixel:
                # Copy full fill arc (with true alpha edges)
                self._arc_masked.fill((0, 0, 0, 0))
                self._arc_masked.blit(self._arc_fill_full, (0, 0))

                # Left-to-right: filled from end_deg back by progress amount
                # Erase unfilled region by subtracting alpha via pie-wedge
                fill_boundary = end_deg - step / PROGRESS_ARC_RESOLUTION
                if fill_boundary > start_deg + 0.5:
                    r_mask = radius + pad + 10
                    cap_margin = 5
                    pts = [(half, half)]
                    for d in range(int(start_deg) - cap_margin, int(fill_boundary) + 1):
                        a = math.radians(d)
                        pts.append((int(half + r_mask * math.cos(a)),
                                    int(half + r_mask * math.sin(a))))
                    a = math.radians(fill_boundary)
                    pts.append((int(half + r_mask * math.cos(a)),
                                int(half + r_mask * math.sin(a))))
                    pts.append((half, half))
                    # Draw opaque polygon, then subtract its alpha from the fill
                    self._arc_erase.fill((0, 0, 0, 0))
                    pygame.draw.polygon(self._arc_erase, (0, 0, 0, 255), pts)
                    self._arc_masked.blit(self._arc_erase, (0, 0),
                                          special_flags=pygame.BLEND_RGBA_SUB)

                self._arc_fill_cache = self._arc_masked
                self._arc_fill_pixel = step

            if self._arc_fill_cache is not None:
                self.screen.blit(self._arc_fill_cache, blit_pos)

        # Time labels (drawn directly, text is already AA)
        label_r = radius - 35
        lx = int(cx + label_r * math.cos(math.radians(end_deg)))
        ly = int(cy + label_r * math.sin(math.radians(end_deg)))
        time_cur = self.font_time.render(self._format_time(position_ms), True, COLOR_GRAY)
        self.screen.blit(time_cur, time_cur.get_rect(center=(lx, ly)))

        rx = int(cx + label_r * math.cos(math.radians(start_deg)))
        ry = int(cy + label_r * math.sin(math.radians(start_deg)))
        time_tot = self.font_time.render('-' + self._format_time(duration_ms - position_ms), True, COLOR_GRAY)
        self.screen.blit(time_tot, time_tot.get_rect(center=(rx, ry)))

    def _handle_airplay_cover(self, data):
        if not data or len(data) == 0:
            self._airplay_cover = None
            self._airplay_bg = None
            return
        try:
            img = pygame.image.load(io.BytesIO(data))
            self._airplay_cover = pygame.transform.smoothscale(img, (ART_SIZE, ART_SIZE))
            self._airplay_bg = self._make_bg(self._airplay_cover)
        except Exception as e:
            print(f"[NowPlaying] Failed to load AirPlay cover: {e}")
            self._airplay_cover = None
            self._airplay_bg = None

    def _fetch_spotify_cover(self, url):
        try:
            req = Request(url, headers={"User-Agent": "CastBridge/1.0"})
            with urlopen(req, timeout=5) as resp:
                data = resp.read()
            img = pygame.image.load(io.BytesIO(data))
            self._spotify_cover = pygame.transform.smoothscale(img, (ART_SIZE, ART_SIZE))
            self._spotify_bg = self._make_bg(self._spotify_cover)
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

    def _get_position(self, state):
        """Return interpolated position_ms based on elapsed time since last MQTT update."""
        pos = state.get("position_ms", 0)
        if state.get("playing"):
            t = self._spotify_pos_time if state is self._spotify else self._airplay_pos_time
            if t > 0:
                pos += (time.monotonic() - t) * 1000
            duration = state.get("duration_ms", 0)
            if duration > 0:
                pos = min(pos, duration)
        return pos

    def _format_time(self, ms):
        total_sec = max(0, int(ms / 1000))
        m = total_sec // 60
        s = total_sec % 60
        return f"{m}:{s:02d}"

    def _draw_display(self, cx, cy):
        """Draw now-playing UI centered at (cx, cy) for a circular display"""
        state, cover = self._get_active()

        if state is None:
            idle = self.font_idle.render("No music playing", True, COLOR_DIM)
            self.screen.blit(idle, idle.get_rect(center=(cx, cy)))
            return

        half_h = self.height // 2
        title_r = half_h - 55   # ~305 for 720
        artist_r = half_h - 95  # ~265 for 720
        progress_r = half_h - PROGRESS_ARC_WIDTH / 2

        # === Title arc (top) ===
        title = state.get("title", "")
        if title:
            self._draw_arc_text(title, self.font_title, COLOR_WHITE, cx, cy, title_r,
                                max_angle=math.radians(80), hq_font=self.font_title_hq)

        # === Artist arc (below title, smaller radius) ===
        artist = state.get("artist", "")
        if artist:
            self._draw_arc_text(artist, self.font_artist, COLOR_GRAY, cx, cy, artist_r,
                                max_angle=math.radians(80), hq_font=self.font_artist_hq)

        # === Album art (centered, slightly above circle center) ===
        art_y = cy - 80
        if cover:
            self.screen.blit(cover, cover.get_rect(center=(cx, art_y)))
        else:
            placeholder = pygame.Rect(cx - ART_SIZE // 2, art_y - ART_SIZE // 2,
                                      ART_SIZE, ART_SIZE)
            pygame.draw.rect(self.screen, COLOR_BAR_BG, placeholder)

        # === Lyrics (below art) ===
        lyrics_y = art_y + ART_SIZE // 2 + 30
        max_lyric_w = self.half_width - 80

        if self._lyrics.get("loading"):
            loading_surf = self.font_lyric.render("Loading lyrics...", True, COLOR_DIM)
            self.screen.blit(loading_surf, loading_surf.get_rect(center=(cx, lyrics_y + 40)))
        else:
            line_idx = self._lyrics.get("line_index", -1)
            current_line = self._lyrics.get("current_line", "")
            next_line = self._lyrics.get("next_line", "")

            prev_line = ""
            if self._lyrics_full and line_idx > 0:
                prev_line = self._lyrics_full[line_idx - 1].get("text", "")

            if prev_line:
                prev_surf = self.font_lyric.render(prev_line, True, COLOR_DIM)
                if prev_surf.get_width() > max_lyric_w:
                    prev_surf = pygame.transform.smoothscale(
                        prev_surf, (max_lyric_w, prev_surf.get_height()))
                self.screen.blit(prev_surf, prev_surf.get_rect(center=(cx, lyrics_y)))
            lyrics_y += 40

            if current_line:
                curr_surf = self.font_lyric_current.render(current_line, True, COLOR_ACCENT)
                if curr_surf.get_width() > max_lyric_w:
                    curr_surf = pygame.transform.smoothscale(
                        curr_surf, (max_lyric_w, curr_surf.get_height()))
                self.screen.blit(curr_surf, curr_surf.get_rect(center=(cx, lyrics_y)))
            lyrics_y += 50

            if next_line:
                next_surf = self.font_lyric.render(next_line, True, COLOR_DIM)
                if next_surf.get_width() > max_lyric_w:
                    next_surf = pygame.transform.smoothscale(
                        next_surf, (max_lyric_w, next_surf.get_height()))
                self.screen.blit(next_surf, next_surf.get_rect(center=(cx, lyrics_y)))

        # === Progress arc (bottom) ===
        duration = state.get("duration_ms", 0)
        position = self._get_position(state)
        self._draw_arc_progress(cx, cy, progress_r, position, duration)

    def draw(self):
        self.screen.fill(COLOR_BG)

        # Draw blurred album art background
        state, cover = self._get_active()
        bg = None
        if state is self._spotify:
            bg = self._spotify_bg
        elif state is self._airplay:
            bg = self._airplay_bg
        if bg:
            self.screen.blit(bg, (0, 0))

        left_cx = self.half_width // 2
        cy = self.height // 2

        # Render left display only, then duplicate to right
        self._draw_display(left_cx, cy)

        if DEBUG:
            fps = self.clock.get_fps()
            fps_surf = self.font_time.render(f"{fps:.1f} FPS", True, COLOR_DIM)
            self.screen.blit(fps_surf, fps_surf.get_rect(center=(left_cx, 30)))

        # Copy left half to right half (identical content, fast pixel copy)
        self.screen.blit(self.screen, (self.half_width, 0), (0, 0, self.half_width, self.height))

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
            self.clock.tick(60)

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

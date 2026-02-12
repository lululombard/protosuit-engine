#!/usr/bin/env python3
"""
Ring Ding - Circle timing game with dual display
Simple rewrite with correct coordinate handling
"""

import pygame
import numpy as np
import math
import sys
import os
from enum import Enum

# Game constants
NUM_LEVELS = 20
INITIAL_TARGET_ARC = 90  # degrees
FINAL_TARGET_ARC = 20    # degrees
ROTATION_SPEED = 2.0     # degrees per frame
CIRCLE_RADIUS = 280      # pixels
TRACK_WIDTH = 40         # pixels
MARKER_SIZE = 50         # pixels
HIT_MARGIN = 6           # degrees

# Colors (RGB)
COLOR_BG = (0, 0, 0)
COLOR_TRACK = (40, 40, 40)
COLOR_TARGET = (255, 50, 50)
COLOR_MARKER = (50, 255, 50)
COLOR_WIN = (50, 255, 50)
COLOR_LOSE = (255, 50, 50)
COLOR_TEXT = (200, 200, 200)

# Audio constants
SAMPLE_RATE = 22050


class GameState(Enum):
    IDLE = 0
    PLAYING = 1
    WIN = 2
    LOSE = 3


class SoundSynth:
    """Synthesize simple sound effects"""

    def __init__(self, sample_rate=SAMPLE_RATE):
        self.sample_rate = sample_rate
        pygame.mixer.init(frequency=sample_rate, size=-16, channels=1, buffer=1024)

    def generate_tone(self, frequency, duration, volume=1):
        num_samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, num_samples)
        wave = np.sin(2 * np.pi * frequency * t)
        envelope = np.ones(num_samples)
        fade_samples = int(0.01 * self.sample_rate)
        envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        wave = wave * envelope * volume
        wave = (wave * 32767).astype(np.int16)
        stereo_wave = np.column_stack((wave, wave))
        return pygame.sndarray.make_sound(stereo_wave)

    def generate_chord(self, frequencies, duration, volume=1):
        num_samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, num_samples)
        wave = np.zeros(num_samples)
        for freq in frequencies:
            wave += np.sin(2 * np.pi * freq * t)
        wave = wave / len(frequencies)
        envelope = np.ones(num_samples)
        fade_samples = int(0.01 * self.sample_rate)
        envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        wave = wave * envelope * volume
        wave = (wave * 32767).astype(np.int16)
        stereo_wave = np.column_stack((wave, wave))
        return pygame.sndarray.make_sound(stereo_wave)

    def ding(self):
        return self.generate_chord([523, 659, 784], 0.3, volume=1)

    def win_fanfare(self):
        return self.generate_chord([523, 659, 784, 1047], 0.6, volume=1)

    def lose_sound(self):
        # Classic Mac crash sound - 3 descending chords using generate_chord
        duration = 0.82  # 820ms total (200ms + 10ms + 200ms + 10ms + 400ms)
        num_samples = int(duration * self.sample_rate)
        wave = np.zeros(num_samples)

        # First chord: Minor 2nd cluster (C-C#-D) - 200ms - very dissonant crash sound
        chord1 = self.generate_chord([523.25, 554.37, 587.33], 0.2, volume=1.0)
        chord1_array = pygame.sndarray.array(chord1)
        # Convert from int16 to float, normalize, then back to int16
        chord1_float = chord1_array[:, 0].astype(np.float32) / 32767.0
        wave[:len(chord1_float)] = chord1_float

        # Gap 1: 10ms silence
        gap1_start = len(chord1_float)
        gap1_samples = int(0.01 * self.sample_rate)

        # Second chord: A minor (A-C-E) - 200ms
        chord2 = self.generate_chord([440.00, 523.25, 659.25], 0.2, volume=1.0)
        chord2_array = pygame.sndarray.array(chord2)
        chord2_float = chord2_array[:, 0].astype(np.float32) / 32767.0
        chord2_start = gap1_start + gap1_samples
        wave[chord2_start:chord2_start + len(chord2_float)] = chord2_float

        # Gap 2: 10ms silence
        gap2_start = chord2_start + len(chord2_float)
        gap2_samples = int(0.01 * self.sample_rate)

        # Third chord: F major (F-A-C) - 400ms
        chord3 = self.generate_chord([349.23, 440.00, 523.25], 0.4, volume=1.0)
        chord3_array = pygame.sndarray.array(chord3)
        chord3_float = chord3_array[:, 0].astype(np.float32) / 32767.0
        chord3_start = gap2_start + gap2_samples
        wave[chord3_start:chord3_start + len(chord3_float)] = chord3_float

        # Convert back to pygame sound
        wave = (wave * 32767).astype(np.int16)
        stereo_wave = np.column_stack((wave, wave))
        return pygame.sndarray.make_sound(stereo_wave)


class RingDingGame:
    def __init__(self, width=1440, height=720):
        pygame.init()

        self.width = width
        self.height = height
        self.half_width = width // 2

        # Set window position to top-left before creating window
        os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'

        self.screen = pygame.display.set_mode((width, height), pygame.NOFRAME)
        pygame.display.set_caption("Ring Ding")

        self.clock = pygame.time.Clock()
        self.fps = 60

        self.synth = SoundSynth()
        self.sounds = {
            'ding': self.synth.ding(),
            'win': self.synth.win_fanfare(),
            'lose': self.synth.lose_sound()
        }

        self.font_large = pygame.font.Font(None, 72)
        self.font_medium = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 36)

        self.state = GameState.IDLE
        self.current_level = 0
        self.score = 0
        self.marker_angle = 0.0  # 0-360, internal angle
        self.target_start_angle = 0.0
        self.target_arc_size = 0.0
        self.rotation_speed = ROTATION_SPEED
        self.state_timer = 0
        self.was_in_target = False  # Track if marker was in target zone last frame
        self.validated_this_pass = False  # Track if player validated during this target pass
        self.pass_count = 0  # Track number of passes through target
        self.feedback_text = None  # Current feedback text to show
        self.feedback_color = None  # Color of feedback
        self.feedback_alpha = 0  # Alpha for fade effect

    def start_game(self):
        self.state = GameState.PLAYING
        self.current_level = 1
        self.score = 0
        self.marker_angle = 0.0
        self.was_in_target = False
        self.validated_this_pass = False
        self.pass_count = 0
        self.feedback_text = None
        self.feedback_alpha = 0
        self.set_new_objective()
        print(f"[RingDing] Starting game - Level {self.current_level}")

    def set_new_objective(self):
        progress = (self.current_level - 1) / (NUM_LEVELS - 1)
        self.rotation_speed = ROTATION_SPEED + (self.current_level * 0.3)
        self.target_arc_size = INITIAL_TARGET_ARC - (INITIAL_TARGET_ARC - FINAL_TARGET_ARC) * progress
        max_angle = 360 - self.target_arc_size
        self.target_start_angle = np.random.uniform(0, max_angle)
        self.was_in_target = False
        self.validated_this_pass = False
        self.pass_count = 0
        print(f"[RingDing] Level {self.current_level}: Target={self.target_start_angle:.1f}° size={self.target_arc_size:.1f}°")

    def check_hit(self, verbose=False):
        """Simple angle range check"""
        marker = self.marker_angle % 360
        target_start = (self.target_start_angle - HIT_MARGIN) % 360
        target_end = (self.target_start_angle + self.target_arc_size + HIT_MARGIN) % 360

        if target_start <= target_end:
            in_zone = target_start <= marker <= target_end
        else:
            in_zone = marker >= target_start or marker <= target_end

        if verbose:
            print(f"[RingDing] Hit: M={marker:.0f}° T={target_start:.0f}°-{target_end:.0f}° = {in_zone}")
        return in_zone

    def handle_hit(self):
        if self.state != GameState.PLAYING:
            if self.state == GameState.IDLE:
                self.start_game()
            elif self.state in [GameState.WIN, GameState.LOSE]:
                self.start_game()
            return

        if self.check_hit(verbose=True):
            self.validated_this_pass = True
            self.score += 10
            if self.current_level >= NUM_LEVELS:
                self.state = GameState.WIN
                self.state_timer = 0
                self.sounds['win'].play()
                print("[RingDing] GAME WON!")
            else:
                self.sounds['ding'].play()
                self.current_level += 1
                self.feedback_text = "+10"
                self.feedback_color = COLOR_WIN
                self.feedback_alpha = 255
                self.set_new_objective()
                print(f"[RingDing] Level {self.current_level}")
        else:
            self.state = GameState.LOSE
            self.state_timer = 0
            self.sounds['lose'].play()
            print("[RingDing] GAME LOST!")

    def update(self):
        if self.state == GameState.PLAYING:
            self.marker_angle += self.rotation_speed
            self.marker_angle %= 360

            # Check if marker is currently in target zone
            in_target = self.check_hit()

            # Detect when marker exits target zone
            if self.was_in_target and not in_target:
                self.pass_count += 1
                # Skip first pass, don't penalize
                if self.pass_count > 1 and not self.validated_this_pass:
                    if self.score > 0:
                        self.score -= 1
                        self.feedback_text = "-1 missed loop"
                        self.feedback_color = COLOR_LOSE
                        self.feedback_alpha = 255
                        print(f"[RingDing] Missed target! Score: {self.score}")
                self.validated_this_pass = False  # Reset for next pass

            self.was_in_target = in_target

            # Fade out feedback text
            if self.feedback_alpha > 0:
                self.feedback_alpha = max(0, self.feedback_alpha - 5)
        elif self.state in [GameState.WIN, GameState.LOSE]:
            self.state_timer += 1

    def draw_arc_segment(self, surface, center_x, center_y, radius, start_angle_deg, end_angle_deg, color, width):
        """Draw arc using overlapping circles for smooth appearance"""
        arc_length = abs(end_angle_deg - start_angle_deg)
        num_points = max(int(arc_length * 3), 10)  # 3 points per degree for smooth arcs

        for i in range(num_points + 1):
            t = i / num_points
            angle = start_angle_deg + t * (end_angle_deg - start_angle_deg)

            x = center_x + radius * math.cos(math.radians(angle))
            y = center_y + radius * math.sin(math.radians(angle))

            # Draw a circle at this point for smooth coverage
            pygame.draw.circle(surface, color, (int(x), int(y)), width // 2)

    def draw_circle_display(self, surface, center_x, center_y, mirror=False):
        """Draw game on one display. mirror=True flips to counter-clockwise"""
        # Draw track
        pygame.draw.circle(surface, COLOR_TRACK, (center_x, center_y), CIRCLE_RADIUS, TRACK_WIDTH)

        if self.state == GameState.PLAYING:
            # Calculate visual angles (mirror inverts direction)
            if mirror:
                # Right display: flip and add 180° offset
                visual_target_start = -(self.target_start_angle + 180)
                visual_target_end = -(self.target_start_angle + self.target_arc_size + 180)
                visual_marker = -(self.marker_angle + 180)
            else:
                # Left display: use raw angles (appears clockwise due to Y-down)
                visual_target_start = self.target_start_angle
                visual_target_end = self.target_start_angle + self.target_arc_size
                visual_marker = self.marker_angle

            # Draw target arc
            self.draw_arc_segment(surface, center_x, center_y, CIRCLE_RADIUS,
                                visual_target_start, visual_target_end, COLOR_TARGET, TRACK_WIDTH + 10)

            # Draw marker
            marker_x = center_x + CIRCLE_RADIUS * math.cos(math.radians(visual_marker))
            marker_y = center_y + CIRCLE_RADIUS * math.sin(math.radians(visual_marker))
            pygame.draw.circle(surface, COLOR_MARKER, (int(marker_x), int(marker_y)), MARKER_SIZE // 2)

            # Level text
            level_text = self.font_medium.render(f"Level {self.current_level}", True, COLOR_TEXT)
            score_text = self.font_medium.render(f"Score {self.score}", True, COLOR_TEXT)
            text_rect = level_text.get_rect(center=(center_x, center_y - 25))
            surface.blit(level_text, text_rect)
            score_rect = score_text.get_rect(center=(center_x, center_y + 25))
            surface.blit(score_text, score_rect)

            # Feedback text with fade
            if self.feedback_text and self.feedback_alpha > 0:
                feedback_surface = self.font_small.render(self.feedback_text, True, self.feedback_color)
                feedback_surface.set_alpha(self.feedback_alpha)
                feedback_rect = feedback_surface.get_rect(center=(center_x, center_y + 65))
                surface.blit(feedback_surface, feedback_rect)

    def draw(self):
        self.screen.fill(COLOR_BG)

        if self.state == GameState.IDLE:
            title = self.font_large.render("RING DING", True, COLOR_TEXT)
            rule_text_1 = self.font_small.render("20 levels - Press A when green hits red zone", True, COLOR_TEXT)
            rule_text_2 = self.font_small.render("Press outside zone = Game Over | Let it loop = -1 pt", True, COLOR_TEXT)
            start_text = self.font_medium.render("Press A to start", True, COLOR_TEXT)
            credit_text_1 = self.font_small.render("Original ESP32 LED game by", True, COLOR_TEXT)
            credit_text_2 = self.font_small.render("Miggy and Dharsi", True, COLOR_TEXT)
            credit_text_3 = self.font_small.render("Score system by Azavech", True, COLOR_TEXT)
            credit_text_4 = self.font_small.render("Ported to Pygame by lululombard", True, COLOR_TEXT)

            for x_offset in [self.half_width // 2, self.half_width + self.half_width // 2]:
                title_rect = title.get_rect(center=(x_offset, self.height // 2 - 180))
                self.screen.blit(title, title_rect)
                rule_rect_1 = rule_text_1.get_rect(center=(x_offset, self.height // 2 - 100))
                self.screen.blit(rule_text_1, rule_rect_1)
                rule_rect_2 = rule_text_2.get_rect(center=(x_offset, self.height // 2 - 65))
                self.screen.blit(rule_text_2, rule_rect_2)
                start_rect = start_text.get_rect(center=(x_offset, self.height // 2 + 20))
                self.screen.blit(start_text, start_rect)
                credit_rect_1 = credit_text_1.get_rect(center=(x_offset, self.height // 2 + 160))
                self.screen.blit(credit_text_1, credit_rect_1)
                credit_rect_2 = credit_text_2.get_rect(center=(x_offset, self.height // 2 + 195))
                self.screen.blit(credit_text_2, credit_rect_2)
                credit_rect_3 = credit_text_3.get_rect(center=(x_offset, self.height // 2 + 230))
                self.screen.blit(credit_text_3, credit_rect_3)
                credit_rect_4 = credit_text_4.get_rect(center=(x_offset, self.height // 2 + 265))
                self.screen.blit(credit_text_4, credit_rect_4)

        elif self.state == GameState.PLAYING:
            self.draw_circle_display(self.screen, self.half_width // 2, self.height // 2, mirror=False)
            self.draw_circle_display(self.screen, self.half_width + self.half_width // 2, self.height // 2, mirror=True)

        elif self.state == GameState.WIN:
            self.screen.fill(COLOR_WIN)
            win_text = self.font_large.render("YOU WIN!", True, COLOR_BG)
            max_score = NUM_LEVELS * 10
            score_text = self.font_medium.render(f"Score: {self.score} / {max_score}", True, COLOR_BG)
            restart_text = self.font_small.render("Press A to play again", True, COLOR_BG)
            menu_text = self.font_small.render("Press B for menu", True, COLOR_BG)

            for x_offset in [self.half_width // 2, self.half_width + self.half_width // 2]:
                win_rect = win_text.get_rect(center=(x_offset, self.height // 2 - 70))
                self.screen.blit(win_text, win_rect)
                score_rect = score_text.get_rect(center=(x_offset, self.height // 2))
                self.screen.blit(score_text, score_rect)
                restart_rect = restart_text.get_rect(center=(x_offset, self.height // 2 + 70))
                self.screen.blit(restart_text, restart_rect)
                menu_rect = menu_text.get_rect(center=(x_offset, self.height // 2 + 110))
                self.screen.blit(menu_text, menu_rect)

        elif self.state == GameState.LOSE:
            self.screen.fill(COLOR_LOSE)
            lose_text = self.font_large.render("GAME OVER", True, COLOR_BG)
            restart_text = self.font_small.render("Press A to try again", True, COLOR_BG)
            menu_text = self.font_small.render("Press B for menu", True, COLOR_BG)

            for x_offset in [self.half_width // 2, self.half_width + self.half_width // 2]:
                lose_rect = lose_text.get_rect(center=(x_offset, self.height // 2 - 50))
                self.screen.blit(lose_text, lose_rect)
                restart_rect = restart_text.get_rect(center=(x_offset, self.height // 2 + 50))
                self.screen.blit(restart_text, restart_rect)
                menu_rect = menu_text.get_rect(center=(x_offset, self.height // 2 + 90))
                self.screen.blit(menu_text, menu_rect)

        pygame.display.flip()

    def run(self):
        running = True

        if os.environ.get('RING_DING_AUTO_START', '0') == '1':
            print("[RingDing] Auto-starting game...")
            self.start_game()
        else:
            print("[RingDing] Game started. Press A to begin!")

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_a:
                        self.handle_hit()
                    elif event.key == pygame.K_b:
                        if self.state in [GameState.PLAYING, GameState.WIN, GameState.LOSE]:
                            print("[RingDing] Returning to main menu...")
                            self.state = GameState.IDLE
                    elif event.key == pygame.K_ESCAPE:
                        running = False

            self.update()
            self.draw()
            self.clock.tick(self.fps)

        print("[RingDing] Game ended")
        pygame.quit()


def main():
    width = int(os.environ.get('PROTOSUIT_DISPLAY_WIDTH', 720)) * 2
    height = int(os.environ.get('PROTOSUIT_DISPLAY_HEIGHT', 720))

    print(f"[RingDing] Starting with display size: {width}x{height}")

    game = RingDingGame(width, height)
    game.run()


if __name__ == "__main__":
    main()

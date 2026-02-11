"""
Audio capture and FFT processing for shader visualization.
Captures from a USB microphone and produces a 512x2 float32 texture:
  Row 0: FFT frequency magnitudes (0.0-1.0)
  Row 1: Waveform samples (0.0-1.0, centered at 0.5)
"""

import threading
import numpy as np
import time


class AudioCapture:
    """
    Captures audio from a USB microphone and computes FFT data.

    Thread-safe: the render thread reads get_texture_data() while
    the capture thread writes internally.
    """

    FFT_SIZE = 1024  # Input samples per FFT window
    TEXTURE_WIDTH = 512  # Output bins (FFT_SIZE // 2)
    SAMPLE_RATE = 44100
    PROCESS_HZ = 60  # Match render frame rate
    RETRY_INTERVAL = 10.0  # Seconds between device retry attempts

    def __init__(self):
        self._lock = threading.Lock()
        self._fft_data = np.zeros(self.TEXTURE_WIDTH, dtype=np.float32)
        self._waveform_data = np.full(self.TEXTURE_WIDTH, 0.5, dtype=np.float32)
        self._running = False
        self._thread = None
        self._available = False
        self._stream = None

        # Ring buffer for audio samples from callback
        self._buffer_lock = threading.Lock()
        self._ring_buffer = np.zeros(self.FFT_SIZE, dtype=np.float32)
        self._buffer_pos = 0

        # Smoothing for FFT magnitudes
        self._smoothed_fft = np.zeros(self.TEXTURE_WIDTH, dtype=np.float32)
        self._smooth_factor = 0.3  # 0=instant, 1=frozen

        # Noise floor estimation: slow-moving average of FFT magnitudes
        # Subtracted from each frame so steady-state noise (fans, hum) is removed
        self._noise_floor = None  # Initialized on first frame
        self._noise_adapt_rate = 0.01  # How fast noise floor adapts (slow = stable)

        # Windowing function (Hann window reduces spectral leakage)
        self._window = np.hanning(self.FFT_SIZE).astype(np.float32)

        # Log frequency mapping: remap 512 linear FFT bins to log scale
        # Maps output texels to logarithmically-spaced source bins
        # so bass is compressed and mids/treble get more space
        min_freq = 20.0  # Hz
        max_freq = self.SAMPLE_RATE / 2.0  # Nyquist
        hz_per_bin = self.SAMPLE_RATE / self.FFT_SIZE
        log_freqs = np.logspace(
            np.log10(min_freq), np.log10(max_freq), self.TEXTURE_WIDTH
        )
        self._log_bin_indices = np.clip(
            (log_freqs / hz_per_bin).astype(int), 0, self.TEXTURE_WIDTH - 1
        )

    def start(self) -> bool:
        """Start audio capture. Returns True if mic was found."""
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

        # Wait briefly to see if device was found
        time.sleep(0.5)
        return self._available

    def stop(self):
        """Stop audio capture and release device."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._close_stream()

    @property
    def available(self) -> bool:
        """Whether audio capture is active and producing data."""
        return self._available

    def get_texture_data(self) -> bytes:
        """
        Returns 512x2 float32 data for ModernGL texture.write().
        Layout: 512 floats (FFT row) followed by 512 floats (waveform row).
        Total: 4096 bytes.
        """
        with self._lock:
            data = np.concatenate([self._fft_data, self._waveform_data])
        return data.tobytes()

    def _audio_callback(self, indata, frames, time_info, status):
        """PortAudio callback - copy samples to ring buffer."""
        samples = indata[:, 0].astype(np.float32)  # Mono, first channel
        n = len(samples)

        with self._buffer_lock:
            # Write into ring buffer
            end = self._buffer_pos + n
            if end <= self.FFT_SIZE:
                self._ring_buffer[self._buffer_pos : end] = samples
            else:
                # Wrap around
                first = self.FFT_SIZE - self._buffer_pos
                self._ring_buffer[self._buffer_pos :] = samples[:first]
                self._ring_buffer[: n - first] = samples[first:]
            self._buffer_pos = end % self.FFT_SIZE

    def _find_usb_mic(self):
        """Find a USB microphone device index."""
        import sounddevice as sd

        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                name = dev["name"].lower()
                if "usb" in name or "mic" in name:
                    print(f"[AudioCapture] Found USB mic: {dev['name']} (index {i})")
                    return i

        # Fallback: default input device
        try:
            default = sd.query_devices(kind="input")
            if default and default["max_input_channels"] > 0:
                idx = default["index"]
                print(
                    f"[AudioCapture] Using default input: {default['name']} (index {idx})"
                )
                return idx
        except Exception:
            pass

        return None

    def _open_stream(self, device_idx):
        """Open an audio input stream on the given device."""
        import sounddevice as sd

        self._stream = sd.InputStream(
            device=device_idx,
            channels=1,
            samplerate=self.SAMPLE_RATE,
            blocksize=1024,
            dtype=np.float32,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._available = True
        print("[AudioCapture] Stream started")

    def _close_stream(self):
        """Close the audio stream if open."""
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._available = False

    def _capture_loop(self):
        """Main processing loop - runs FFT at ~60Hz."""
        try:
            import sounddevice  # noqa: F401 - verify import works
        except ImportError:
            print(
                "[AudioCapture] sounddevice not installed - audio capture disabled"
            )
            return

        last_retry = 0

        while self._running:
            # Try to open device if not available
            if not self._available:
                now = time.time()
                if now - last_retry >= self.RETRY_INTERVAL:
                    last_retry = now
                    device_idx = self._find_usb_mic()
                    if device_idx is not None:
                        try:
                            self._open_stream(device_idx)
                        except Exception as e:
                            print(f"[AudioCapture] Failed to open device: {e}")
                            self._close_stream()
                    else:
                        print("[AudioCapture] No microphone found, retrying...")

                time.sleep(0.1)
                continue

            try:
                # Read current buffer snapshot
                with self._buffer_lock:
                    # Get samples in order (oldest to newest)
                    samples = np.roll(
                        self._ring_buffer, -self._buffer_pos
                    ).copy()

                # Apply window function and compute FFT
                windowed = samples * self._window
                fft_result = np.fft.rfft(windowed)
                magnitudes = np.abs(fft_result[: self.TEXTURE_WIDTH]).astype(
                    np.float32
                )

                # Remap linear FFT bins to logarithmic frequency scale
                magnitudes = magnitudes[self._log_bin_indices]

                # Noise floor subtraction: remove steady-state noise (fans, hum)
                # The noise floor adapts slowly, so transient sounds stand out
                if self._noise_floor is None:
                    self._noise_floor = magnitudes.copy()
                else:
                    self._noise_floor = (
                        self._noise_floor * (1.0 - self._noise_adapt_rate)
                        + magnitudes * self._noise_adapt_rate
                    )
                magnitudes = np.maximum(magnitudes - self._noise_floor, 0.0)

                # Logarithmic (dB) scale: convert to decibels, then map to 0-1
                # This matches how we perceive loudness and makes quieter
                # frequencies visible alongside loud ones
                DB_RANGE = 60.0  # Dynamic range in dB (60dB = 1000:1 ratio)
                peak = magnitudes.max()
                if peak > 1e-10:
                    # Convert to dB relative to peak: 0 dB = peak, -60 dB = floor
                    magnitudes = np.maximum(magnitudes, peak * 1e-6)  # Avoid log(0)
                    db = 20.0 * np.log10(magnitudes / peak)
                    # Map [-DB_RANGE, 0] to [0, 1]
                    magnitudes = np.clip((db + DB_RANGE) / DB_RANGE, 0.0, 1.0).astype(
                        np.float32
                    )
                else:
                    magnitudes[:] = 0.0

                # Exponential smoothing
                self._smoothed_fft = (
                    self._smoothed_fft * self._smooth_factor
                    + magnitudes * (1.0 - self._smooth_factor)
                )

                # Waveform: last 512 samples, scale from [-1,1] to [0,1]
                waveform = (samples[-self.TEXTURE_WIDTH :] + 1.0) * 0.5
                np.clip(waveform, 0.0, 1.0, out=waveform)

                # Write to shared output
                with self._lock:
                    self._fft_data[:] = self._smoothed_fft
                    self._waveform_data[:] = waveform

                # Sleep to match ~60Hz processing rate
                time.sleep(1.0 / self.PROCESS_HZ)

            except Exception as e:
                print(f"[AudioCapture] Error in capture loop: {e}")
                self._close_stream()
                time.sleep(1.0)

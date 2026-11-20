"""Bounded, CPU-only POS pulse extraction; pulse evidence is not a PAD verdict.

Original implementation of Wang et al., Algorithmic Principles of Remote PPG
(2017), DOI: 10.1109/TBME.2016.2609282. No third-party model/code is bundled.
"""
from collections import deque
from dataclasses import dataclass
from enum import Enum
import math

import numpy as np


class RppgStatus(str, Enum):
    COLLECTING = "collecting"
    SIGNAL_DETECTED = "signal_detected"
    INCONCLUSIVE = "inconclusive"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class RppgEvidence:
    status: RppgStatus
    reason: str
    instruction: str
    sample_count: int = 0
    duration_seconds: float = 0.0
    effective_fps: float = 0.0
    bpm: float | None = None
    quality: float = 0.0
    algorithm_id: str = "pos-v1"


@dataclass(frozen=True)
class RppgWaveform:
    """Local-only relative pulse units; no biometric identity/key is implied."""

    timestamps: tuple
    samples: tuple
    algorithm_id: str = "pos-v1"


def pos_waveform(rgb, fps):
    """Project an N x 3 mean-RGB trace using overlapping 1.6-second windows."""
    values = np.asarray(rgb, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
        raise ValueError("Expected finite N x 3 RGB means")
    length = max(2, math.ceil(1.6 * fps))
    pulse = np.zeros(len(values))
    weights = np.zeros(len(values))
    for start in range(len(values) - length + 1):
        clip = values[start:start + length]
        mean = clip.mean(axis=0)
        if np.any(mean <= 1e-9):
            continue
        normalized = clip / mean - 1.0
        first = normalized[:, 1] - normalized[:, 2]
        second = normalized[:, 1] + normalized[:, 2] - 2 * normalized[:, 0]
        spread = second.std()
        if spread <= 1e-12:
            continue
        projected = first + first.std() / spread * second
        pulse[start:start + length] += projected - projected.mean()
        weights[start:start + length] += 1
    np.divide(pulse, weights, out=pulse, where=weights > 0)
    return pulse


class PosRppgAnalyzer:
    """Keep only timestamps and three RGB means per region, never video frames.

    Quality is spectral concentration, not a calibrated liveness probability.
    Defaults are research settings and must be calibrated on the target camera.
    """

    def __init__(self, *, window_seconds=10.0, min_seconds=8.0,
                 expected_fps=30.0, min_fps=20.0, max_gap=0.15,
                 update_interval=1.0, min_quality=0.45,
                 agreement_bpm=8.0, roi_max_age=0.75):
        numbers = (window_seconds, min_seconds, expected_fps, min_fps, max_gap,
                   update_interval, min_quality, agreement_bpm, roi_max_age)
        if not all(math.isfinite(value) and value > 0 for value in numbers):
            raise ValueError("rPPG settings must be finite and positive")
        if min_seconds < 3 or window_seconds < min_seconds:
            raise ValueError("rPPG window must contain at least 3 seconds")
        if min_fps > expected_fps or min_quality > 1:
            raise ValueError("Invalid rPPG rate or quality setting")
        self.window_seconds, self.min_seconds = window_seconds, min_seconds
        self.min_fps, self.max_gap = min_fps, max_gap
        self.update_interval, self.min_quality = update_interval, min_quality
        self.agreement_bpm, self.roi_max_age = agreement_bpm, roi_max_age
        self._samples = deque(maxlen=math.ceil(window_seconds * expected_fps) + 2)
        self._box = None
        self._frame_number = None
        self._last_analysis = None
        self._waveform = None
        self.evidence = RppgEvidence(
            RppgStatus.COLLECTING, "waiting_for_depth", "Complete the depth movement first",
        )

    def clear(self):
        """Release transient color traces and waveform on stop or cancellation."""
        self._samples.clear()
        self._waveform = None
        self._box = None
        self._frame_number = None
        self._last_analysis = None

    def _reset(self, reason, instruction, status=RppgStatus.COLLECTING):
        self.clear()
        self.evidence = RppgEvidence(status, reason, instruction)
        return self.evidence

    def update(self, frame, observation, *, challenge_complete=False):
        """Use a recent depth face box on each RGB frame after the challenge."""
        sensor_time = getattr(frame, 'sensor_timestamp', None)
        stamp = float(frame.captured_at if sensor_time is None else sensor_time)
        if not math.isfinite(stamp):
            return self._reset("invalid_time", "Restart the camera check", RppgStatus.UNAVAILABLE)
        if observation is None or not observation.candidate or observation.face_box is None:
            return self._reset("no_valid_face", "Center one face in the camera")
        age = frame.captured_at - observation.captured_at
        if not math.isfinite(age) or not 0 <= age <= self.roi_max_age:
            return self._reset("stale_face", "Wait for a fresh face region", RppgStatus.UNAVAILABLE)
        if not challenge_complete:
            return self._reset("waiting_for_depth", "Complete the depth movement first")
        box = observation.face_box
        if self._box is not None:
            x, y, w, h = self._box
            bx, by, bw, bh = box
            motion = max(abs(bx - x) / w, abs(by - y) / h,
                         abs(bw - w) / w, abs(bh - h) / h)
            if motion > 0.12:
                self._reset("face_moved", "Hold still; restarting pulse collection")
        # Anchor to the first box, so slow accumulated movement is detected too.
        if self._box is None:
            self._box = box
        if self._samples:
            previous = self._samples[-1][0]
            if stamp <= previous or frame.frame_number <= self._frame_number:
                return self._reset("non_monotonic_frame", "Restarting pulse collection")
            if stamp - previous > self.max_gap:
                self._reset("frame_gap", "Hold still; camera timing interrupted")
                self._box = box
        rgb = self._region_means(frame.color_rgb, box)
        if rgb is None:
            return self._reset("poor_exposure", "Use steady, even lighting on your face")
        self._frame_number = frame.frame_number
        self._samples.append((stamp, rgb))
        while self._samples and stamp - self._samples[0][0] > self.window_seconds:
            self._samples.popleft()
        duration = stamp - self._samples[0][0]
        fps = (len(self._samples) - 1) / duration if duration > 0 else 0.0
        if duration + 1e-6 < self.min_seconds:
            self.evidence = RppgEvidence(
                RppgStatus.COLLECTING, "warming_up", "Hold still while pulse evidence is collected",
                len(self._samples), duration, fps,
            )
        elif self._last_analysis is None or stamp - self._last_analysis >= self.update_interval:
            self._last_analysis = stamp
            self.evidence = self._analyze(duration, fps)
        return self.evidence

    @staticmethod
    def _region_means(image, box):
        image = np.asarray(image)
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise ValueError("rPPG requires uint8 RGB frames")
        x, y, width, height = box
        if width < 40 or height < 40 or x < 0 or y < 0:
            return None
        if x + width > image.shape[1] or y + height > image.shape[0]:
            return None
        regions = ((.30, .12, .70, .28), (.15, .50, .40, .72), (.60, .50, .85, .72))
        means = []
        for left, top, right, bottom in regions:
            patch = image[y + int(top * height):y + int(bottom * height),
                          x + int(left * width):x + int(right * width)]
            pixels = patch.reshape(-1, 3)
            # Avoid an ethnicity-specific skin-color threshold. Reject clipped pixels.
            usable = pixels[(pixels.min(axis=1) > 5) & (pixels.max(axis=1) < 250)]
            if len(usable) < max(16, len(pixels) * .6):
                return None
            means.append(usable.mean(axis=0))
        return np.asarray(means)

    def _analyze(self, duration, fps):
        count = len(self._samples)
        def result(status, reason, instruction, bpm=None, quality=0.0):
            return RppgEvidence(status, reason, instruction, count, duration, fps, bpm, quality)
        self._waveform = None
        if fps < self.min_fps:
            return result(RppgStatus.UNAVAILABLE, "low_frame_rate", "Camera is too slow for pulse analysis")
        stamps = np.array([item[0] for item in self._samples])
        rgb = np.stack([item[1] for item in self._samples])
        # Interpolate minor arrival jitter only; larger gaps reset before this point.
        uniform = np.linspace(stamps[0], stamps[-1], count)
        traces, rates, qualities = [], [], []
        for region in range(3):
            colors = np.column_stack([
                np.interp(uniform, stamps, rgb[:, region, channel]) for channel in range(3)
            ])
            wave = pos_waveform(colors, fps)
            axis = np.linspace(-1, 1, count)
            wave = wave - np.polyval(np.polyfit(axis, wave, 1), axis)
            spread = wave.std()
            if spread < 1e-8:
                traces.append(wave)
                rates.append(0.0)
                qualities.append(0.0)
                continue
            wave /= spread
            spectrum = np.fft.rfft(wave * np.hanning(count))
            frequencies = np.fft.rfftfreq(count, 1 / fps)
            power = np.abs(spectrum) ** 2
            band = (frequencies >= .7) & (frequencies <= 3.0)  # 42–180 BPM, configurable later
            peak = np.flatnonzero(band)[np.argmax(power[band])]
            neighborhood = np.abs(frequencies - frequencies[peak]) <= 1.1 / duration
            # Denominator includes out-of-band changes: this is not an SNR/probability.
            quality = float(power[band & neighborhood].sum() / max(power[1:].sum(), 1e-12))
            rates.append(float(frequencies[peak] * 60))
            qualities.append(quality)
            # Export relative, band-limited samples separately from the windowed FFT.
            filtered = np.fft.rfft(wave)
            filtered[~band] = 0
            traces.append(np.fft.irfft(filtered, n=count))
        best = max(range(3), key=lambda index: qualities[index])
        agreeing = [index for index in range(3)
                    if qualities[index] >= self.min_quality
                    and abs(rates[index] - rates[best]) <= self.agreement_bpm]
        if len(agreeing) < 2:
            return result(RppgStatus.INCONCLUSIVE, "weak_or_inconsistent_pulse",
                          "Pulse evidence is weak; hold still in even lighting")
        bpm = float(np.mean([rates[index] for index in agreeing]))
        quality = float(np.mean([qualities[index] for index in agreeing]))
        self._waveform = RppgWaveform(
            tuple(float(value) for value in uniform),
            tuple(tuple(float(value) for value in traces[index]) for index in range(3)),
        )
        return result(RppgStatus.SIGNAL_DETECTED, "consistent_pulse",
                      "Pulse signal detected; this is supporting evidence only", bpm, quality)

    def waveform(self):
        """Internal future-processing hook. Never serialized to browser status."""
        return self._waveform

    def abort(self):
        return self._reset("capture_interrupted", "Capture interrupted; start another check",
                           RppgStatus.UNAVAILABLE)

    def finish(self):
        if self.evidence.status == RppgStatus.COLLECTING:
            self.evidence = RppgEvidence(
                RppgStatus.INCONCLUSIVE, "insufficient_capture",
                "Not enough steady pulse data; start another check",
                self.evidence.sample_count, self.evidence.duration_seconds,
                self.evidence.effective_fps,
            )
        return self.evidence

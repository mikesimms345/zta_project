"""Signal recovery and invalidation tests using known synthetic inputs, no camera."""
from dataclasses import asdict
import math
from types import SimpleNamespace
import unittest

import numpy as np

from zta.liveness.domain import DepthLivenessObservation
from zta.liveness.rppg import PosRppgAnalyzer, RppgStatus


BOX = (5, 5, 70, 70)


def sample(index, *, fps=30, bpm=90, common=False):
    stamp = index / fps
    beat = math.sin(2 * math.pi * bpm / 60 * stamp)
    color = np.array([120, 95, 70]) + np.array([.3, 2.8, .2]) * beat
    if common:
        color = np.repeat(110 + 10 * beat, 3)
    image = np.empty((80, 80, 3), dtype=np.uint8)
    image[:] = np.rint(color).astype(np.uint8)
    frame = SimpleNamespace(color_rgb=image, color_bgr=image[:, :, ::-1],
                            captured_at=stamp, sensor_timestamp=stamp,
                            frame_number=index)
    observation = DepthLivenessObservation(True, "depth_candidate", BOX, 1., .6,
                                           .02, stamp, "synthetic-depth")
    return frame, observation


def feed(analyzer, *, fps=30, bpm=90, common=False, seconds=10):
    result = None
    for index in range(round(fps * seconds)):
        frame, observation = sample(index, fps=fps, bpm=bpm, common=common)
        result = analyzer.update(frame, observation, challenge_complete=True)
    return result


class PulseTests(unittest.TestCase):
    def test_recovers_known_rates_and_keeps_waveform_out_of_summary(self):
        for bpm in (60, 90, 120):
            with self.subTest(bpm=bpm):
                analyzer = PosRppgAnalyzer()
                result = feed(analyzer, bpm=bpm)
                self.assertEqual(result.status, RppgStatus.SIGNAL_DETECTED)
                self.assertAlmostEqual(result.bpm, bpm, delta=7.5)
                wave = analyzer.waveform()
                self.assertIsNotNone(wave)
                self.assertEqual(len(wave.samples), 3)
                self.assertEqual(len(wave.timestamps), len(wave.samples[0]))
                self.assertNotIn("samples", asdict(result))
                self.assertNotIn("timestamps", asdict(result))

    def test_static_and_common_brightness_do_not_become_pulse_evidence(self):
        for kwargs in ({"bpm": 0}, {"common": True}):
            with self.subTest(kwargs=kwargs):
                analyzer = PosRppgAnalyzer()
                result = feed(analyzer, **kwargs)
                self.assertEqual(result.status, RppgStatus.INCONCLUSIVE)
                self.assertIsNone(result.bpm)
                self.assertIsNone(analyzer.waveform())

    def test_noise_is_not_a_consistent_signal(self):
        analyzer = PosRppgAnalyzer()
        rng = np.random.default_rng(17)
        for index in range(300):
            frame, observation = sample(index)
            frame.color_rgb[:] = rng.integers(60, 150, frame.color_rgb.shape, dtype=np.uint8)
            result = analyzer.update(frame, observation, challenge_complete=True)
        self.assertEqual(result.status, RppgStatus.INCONCLUSIVE)

    def test_short_capture_is_inconclusive_and_slow_capture_unavailable(self):
        analyzer = PosRppgAnalyzer()
        feed(analyzer, seconds=3)
        self.assertEqual(analyzer.finish().reason, "insufficient_capture")
        result = feed(PosRppgAnalyzer(), fps=10)
        self.assertEqual(result.status, RppgStatus.UNAVAILABLE)
        self.assertEqual(result.reason, "low_frame_rate")

    def test_loss_motion_gap_and_duplicate_invalidate_old_waveform(self):
        for condition in ("lost", "moved", "gap", "duplicate", "stale", "challenge"):
            with self.subTest(condition=condition):
                analyzer = PosRppgAnalyzer()
                feed(analyzer)
                frame, observation = sample(300)
                complete = True
                if condition == "lost":
                    observation = None
                elif condition == "moved":
                    observation = DepthLivenessObservation(
                        True, "depth_candidate", (25, 5, 50, 70), 1., .6, .02,
                        frame.captured_at, "synthetic-depth")
                elif condition == "gap":
                    frame, observation = sample(330)
                elif condition == "duplicate":
                    frame, observation = sample(299)
                elif condition == "stale":
                    frame.captured_at += 1
                elif condition == "challenge":
                    complete = False
                result = analyzer.update(frame, observation, challenge_complete=complete)
                self.assertIsNone(result.bpm)
                self.assertIsNone(analyzer.waveform())
                self.assertLessEqual(result.sample_count, 1)

    def test_sensor_timing_survives_arrival_jitter(self):
        analyzer = PosRppgAnalyzer()
        for index in range(300):
            frame, observation = sample(index)
            # Device sampling remains uniform despite host-delivery jitter.
            frame.captured_at += .02 * (index % 2)
            result = analyzer.update(frame, observation, challenge_complete=True)
        self.assertEqual(result.status, RppgStatus.SIGNAL_DETECTED)
        self.assertAlmostEqual(result.effective_fps, 30, places=6)

    def test_clipping_and_nonfinite_timestamps_invalidate(self):
        analyzer = PosRppgAnalyzer()
        frame, observation = sample(0)
        frame.color_rgb[:] = 255
        self.assertEqual(analyzer.update(frame, observation, challenge_complete=True).reason,
                         "poor_exposure")
        frame.sensor_timestamp = float('nan')
        self.assertEqual(analyzer.update(frame, observation, challenge_complete=True).status,
                         RppgStatus.UNAVAILABLE)

    def test_storage_is_bounded_and_cleared(self):
        analyzer = PosRppgAnalyzer()
        feed(analyzer, seconds=20)
        self.assertLessEqual(len(analyzer._samples), 302)
        self.assertLessEqual(analyzer.evidence.duration_seconds, 10)
        analyzer.abort()
        self.assertEqual(len(analyzer._samples), 0)
        self.assertIsNone(analyzer.waveform())
        self.assertIsNone(analyzer.evidence.bpm)

    def test_invalid_settings(self):
        for kwargs in ({"min_seconds": 2}, {"max_gap": float('nan')},
                       {"min_quality": 2}, {"min_fps": 40}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PosRppgAnalyzer(**kwargs)


if __name__ == '__main__':
    unittest.main()

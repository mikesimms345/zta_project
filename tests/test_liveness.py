import unittest

import numpy as np

from zta.liveness import (
    DepthLivenessAnalyzer,
    DepthLivenessObservation,
    DepthLivenessPolicy,
)
from zta.media import CameraIntrinsics, RGBDFrame


def _frame(depth):
    color = np.zeros((100, 100, 3), dtype=np.uint8)
    return RGBDFrame(
        color_bgr=color,
        color_rgb=color[:, :, ::-1],
        aligned_depth=depth.astype(np.uint16),
        depth_scale=0.001,
        intrinsics=CameraIntrinsics(100, 100, 1, 1, 50, 50, "none", ()),
        frame_number=1,
        captured_at=1.0,
    )


def _observation(depth, *, candidate=True, reason="depth_candidate"):
    return DepthLivenessObservation(
        candidate=candidate,
        reason=reason,
        face_box=(20, 20, 60, 60),
        valid_depth_ratio=1.0,
        median_depth_m=depth,
        relief_m=0.025 if candidate else 0.001,
        captured_at=1.0,
        analyzer_id="test-depth",
    )


class DepthLivenessTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = DepthLivenessAnalyzer(
            face_detector=lambda _image: [(20, 20, 60, 60)],
        )

    def test_planar_depth_is_not_a_live_candidate(self):
        result = self.analyzer.analyze(
            _frame(np.full((100, 100), 700, dtype=np.uint16)),
        )

        self.assertFalse(result.candidate)
        self.assertEqual("planar_surface", result.reason)
        self.assertLess(result.relief_m, 0.012)

    def test_curved_depth_is_a_live_candidate(self):
        rows, columns = np.indices((100, 100))
        radius = ((columns - 50) ** 2 + (rows - 50) ** 2) / (30 ** 2)
        curved = 650 + np.clip(radius, 0, 1) * 55

        result = self.analyzer.analyze(_frame(curved))

        self.assertTrue(result.candidate)
        self.assertEqual("depth_candidate", result.reason)
        self.assertGreaterEqual(result.relief_m, 0.012)

    def test_move_closer_and_return_completes_challenge(self):
        policy = DepthLivenessPolicy(required_live_observations=3)

        first = policy.evaluate(_observation(0.70))
        closer = policy.evaluate(_observation(0.63))
        returned = policy.evaluate(_observation(0.69))

        self.assertEqual("collecting", first.status)
        self.assertIn("closer", first.instruction)
        self.assertEqual("collecting", closer.status)
        self.assertIn("back", closer.instruction)
        self.assertEqual("live", returned.status)
        self.assertTrue(returned.challenge_complete)

    def test_repeated_planar_observations_flag_possible_spoof(self):
        policy = DepthLivenessPolicy(spoof_streak=2)

        policy.evaluate(_observation(0.70, candidate=False, reason="planar_surface"))
        result = policy.evaluate(
            _observation(0.70, candidate=False, reason="planar_surface"),
        )

        self.assertEqual("spoof_suspected", result.status)


if __name__ == "__main__":
    unittest.main()

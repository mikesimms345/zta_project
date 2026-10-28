import unittest
from threading import Event

import numpy as np

from zta.camera import RGBDCameraPipeline, TERMINAL_PHASES
from zta.domain import Evidence, Status
from zta.liveness import DepthLivenessObservation, DepthLivenessPolicy
from zta.media import CameraIntrinsics, RGBDFrame


class _Source:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.frame_number = 0

    def start(self):
        self.started = True

    def read(self):
        self.frame_number += 1
        color = np.zeros((8, 8, 3), dtype=np.uint8)
        return RGBDFrame(
            color_bgr=color,
            color_rgb=color[:, :, ::-1],
            aligned_depth=np.full((8, 8), 700, dtype=np.uint16),
            depth_scale=0.001,
            intrinsics=CameraIntrinsics(8, 8, 1, 1, 4, 4, "none", ()),
            frame_number=self.frame_number,
            captured_at=float(self.frame_number),
        )

    def stop(self):
        self.stopped = True


class _Analyzer:
    def __init__(self):
        self.calls = 0

    def analyze(self, frame):
        self.calls += 1
        depth = (0.70, 0.63, 0.69)[min(self.calls - 1, 2)]
        return DepthLivenessObservation(
            candidate=True,
            reason="depth_candidate",
            face_box=(1, 1, 6, 6),
            valid_depth_ratio=1.0,
            median_depth_m=depth,
            relief_m=0.025,
            captured_at=frame.captured_at,
            analyzer_id="test-depth",
        )


class _Renderer:
    def __init__(self):
        self.frames = 0
        self.closed = False

    def show(self, _name, _frame, _media, _liveness):
        self.frames += 1
        return False

    def close(self, _name):
        self.closed = True


class RGBDCameraPipelineTests(unittest.TestCase):
    def test_inference_and_liveness_continue_after_first_full_window(self):
        calls = []
        fourth_inference = Event()

        def submit(key, owner, frame):
            calls.append((key, owner, frame))
            status = Status.COLLECTING if len(calls) == 1 else Status.BELOW_THRESHOLD
            if len(calls) >= 4:
                fourth_inference.set()
            return Evidence(status, min(len(calls), 2), 0, 0.0, 2, "test-model")

        source = _Source()
        renderer = _Renderer()
        pipeline = RGBDCameraPipeline(
            submit,
            sample_interval=0,
            source_factory=lambda: source,
            liveness_analyzer=_Analyzer(),
            liveness_policy_factory=lambda: DepthLivenessPolicy(
                required_live_observations=3,
            ),
            preview_renderer=renderer,
        )
        pipeline.start("capture-key", "owner")

        self.assertTrue(fourth_inference.wait(2), "fourth inference never ran")
        state = pipeline.snapshot("capture-key", "owner")
        self.assertEqual("running", state["phase"])
        self.assertEqual(2, state["sample_count"])
        self.assertGreaterEqual(len(calls), 4)
        self.assertEqual("live", state["liveness"]["status"])
        self.assertTrue(state["liveness"]["challenge_complete"])

        pipeline.stop("capture-key", "owner")
        state = pipeline.snapshot("capture-key", "owner")
        self.assertEqual("stopped", state["phase"])
        self.assertIn(state["phase"], TERMINAL_PHASES)
        self.assertTrue(source.started)
        self.assertTrue(source.stopped)
        self.assertTrue(renderer.closed)
        self.assertGreater(renderer.frames, 0)


if __name__ == "__main__":
    unittest.main()

"""Bounded worker/lifecycle integration with an injected RGB-D source."""
from importlib import import_module
from threading import Event, get_ident
import time
import unittest

from zta.liveness.depth import DepthLivenessAnalyzer
from zta.liveness.domain import LivenessEvidence, LivenessStatus
from tests.test_rppg import sample


frames = import_module('zta.frame-handler')
media_domain = import_module('zta.deepfake-detection.domain')


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


class Source:
    def __init__(self, clock):
        self.clock = clock
        self.count = 0
        self.stopped = False
        self.ready = Event()
        self.threads = set()

    def start(self):
        self.threads.add(get_ident())

    def read(self):
        time.sleep(.002)  # Yield to consumers while advancing simulated camera time.
        self.count += 1
        self.clock.value = self.count / 30
        frame, _ = sample(self.count)
        self.threads.add(get_ident())
        self.ready.set()
        return frame

    def stop(self):
        self.threads.add(get_ident())
        self.stopped = True


class Depth:
    def analyze(self, frame):
        return sample(frame.frame_number)[1]


class CompletedChallenge:
    def evaluate(self, observation):
        return LivenessEvidence(LivenessStatus.LIVE, "Complete", "depth_candidate",
                                5, 5, True, 1., .6, .02, observation.face_box, "test-depth")


class CaptureTests(unittest.TestCase):
    def build(self, submit=None, **kwargs):
        clock = Clock()
        source = Source(clock)
        analyzer = []
        from zta.liveness.rppg import PosRppgAnalyzer
        def pulse_factory():
            item = PosRppgAnalyzer()
            analyzer.append(item)
            return item
        pipeline = frames.RGBDCameraPipeline(
            submit or (lambda *args: None), source_factory=lambda: source, preview=False,
            clock=clock, liveness_analyzer=Depth(),
            liveness_policy_factory=CompletedChallenge, rppg_factory=pulse_factory, **kwargs)
        self.addCleanup(self.cleanup, pipeline)
        return pipeline, source, analyzer

    @staticmethod
    def cleanup(pipeline):
        for key, run in pipeline._runs.items():
            try:
                pipeline.stop(key, run.owner)
            except frames.CameraBusy:
                pass

    def finish(self, pipeline):
        pipeline._runs['capture'].thread.join(10)
        self.assertFalse(pipeline._runs['capture'].thread.is_alive())
        return pipeline.snapshot('capture', 'owner')

    def test_slow_cnn_does_not_throttle_pulse_capture_and_deadline_releases_camera(self):
        calls = []
        def slow(*args):
            calls.append(1)
            time.sleep(.08)
        pipeline, source, analyzers = self.build(slow)
        pipeline.start('capture', 'owner')
        state = self.finish(pipeline)
        self.assertEqual(state['phase'], 'completed')
        self.assertEqual(state['rppg']['status'], 'signal_detected')
        self.assertAlmostEqual(state['rppg']['bpm'], 90, delta=8)
        self.assertGreaterEqual(source.count, 449)
        self.assertLess(len(calls), 75)
        self.assertEqual(len(source.threads), 1)  # SDK lifecycle stays on one owner.
        self.assertTrue(source.stopped)
        self.assertIsNone(analyzers[0].waveform())
        self.assertFalse(any(worker.is_alive() for worker in pipeline._runs['capture'].workers))

    def test_cancel_and_owner_isolation(self):
        pipeline, source, _ = self.build()
        pipeline.start('capture', 'owner')
        self.assertTrue(source.ready.wait(2))
        with self.assertRaises(frames.CameraBusy):
            pipeline.start('second', 'owner')
        with self.assertRaises(frames.CameraRunNotFound):
            pipeline.snapshot('capture', 'other')
        with self.assertRaises(frames.CameraRunNotFound):
            pipeline.stop('capture', 'other')
        pipeline.stop('capture', 'owner')
        state = pipeline.snapshot('capture', 'owner')
        self.assertEqual(state['phase'], 'stopped')
        self.assertEqual(state['rppg']['status'], 'unavailable')
        self.assertTrue(source.stopped)

    def test_worker_failure_never_completes_successfully(self):
        def failing(*args):
            raise media_domain.ModelUnavailable('test failure')
        pipeline, source, _ = self.build(failing)
        with self.assertLogs('zta.frame-handler', level='ERROR'):
            pipeline.start('capture', 'owner')
            state = self.finish(pipeline)
        self.assertEqual(state['phase'], 'failed')
        self.assertEqual(state['rppg']['status'], 'unavailable')
        self.assertTrue(source.stopped)

    def test_multiple_faces_produce_no_region(self):
        import numpy as np
        frame, _ = sample(0)
        frame.aligned_depth = np.full((80, 80), 600, dtype=np.uint16)
        frame.depth_scale = .001
        analyzer = DepthLivenessAnalyzer(face_detector=lambda _: [(0, 0, 40, 40), (40, 0, 40, 40)])
        observation = analyzer.analyze(frame)
        self.assertEqual(observation.reason, 'multiple_faces')
        self.assertIsNone(observation.face_box)

    def test_camera_failure_invalidates_pulse_and_releases_source(self):
        pipeline, source, _ = self.build()
        def fail_read():
            raise RuntimeError('camera disconnected')
        source.read = fail_read
        with self.assertLogs('zta.frame-handler', level='ERROR'):
            pipeline.start('capture', 'owner')
            state = self.finish(pipeline)
        self.assertEqual(state['phase'], 'failed')
        self.assertEqual(state['rppg']['status'], 'unavailable')
        self.assertTrue(source.stopped)

    def test_hung_consumer_keeps_slot_busy_until_it_exits(self):
        release, entered = Event(), Event()
        def hang(*args):
            entered.set()
            release.wait(6)
        pipeline, source, _ = self.build(hang, capture_seconds=.5)
        try:
            pipeline.start('capture', 'owner')
            self.assertTrue(entered.wait(1))
            state = self.finish(pipeline)
            self.assertEqual(state['phase'], 'failed')
            self.assertTrue(source.stopped)
            with self.assertRaises(frames.CameraBusy):
                pipeline.start('new', 'owner')
        finally:
            release.set()
            for worker in pipeline._runs['capture'].workers:
                worker.join(2)

    def test_short_deadline_is_inconclusive_and_runs_are_isolated(self):
        pipeline, source, _ = self.build(capture_seconds=.5)
        pipeline.start('capture', 'owner')
        state = self.finish(pipeline)
        self.assertEqual(state['phase'], 'completed')
        self.assertEqual(state['rppg']['status'], 'inconclusive')
        source.count = 0
        source.clock.value = 0
        pipeline.start('new', 'owner')
        pipeline._runs['new'].thread.join(3)
        self.assertEqual(pipeline.snapshot('new', 'owner')['rppg']['status'], 'inconclusive')
        with self.assertRaises(frames.CameraRunNotFound):
            pipeline.snapshot('capture', 'owner')

    def test_sdk_frame_keeps_sensor_and_host_time_separate(self):
        from types import SimpleNamespace
        import numpy as np
        from zta.realsense import RealSenseFrameSource
        color = np.full((2, 3, 3), [10, 20, 30], dtype=np.uint8)
        depth = np.full((2, 3), 600, dtype=np.uint16)
        values = SimpleNamespace(width=3, height=2, fx=1, fy=1, ppx=1, ppy=1,
                                 model='none', coeffs=[0] * 5)
        color_frame = SimpleNamespace(
            get_data=lambda: color, get_timestamp=lambda: 1234.5, get_frame_number=lambda: 7,
            profile=SimpleNamespace(as_video_stream_profile=lambda: SimpleNamespace(intrinsics=values)))
        aligned = SimpleNamespace(get_depth_frame=lambda: SimpleNamespace(get_data=lambda: depth),
                                  get_color_frame=lambda: color_frame)
        source = RealSenseFrameSource(clock=lambda: 10.)
        source._pipeline = SimpleNamespace(wait_for_frames=lambda timeout: aligned)
        source._align = SimpleNamespace(process=lambda frame: frame)
        source._depth_scale = .001
        frame = source.read()
        self.assertEqual(frame.captured_at, 10.)
        self.assertAlmostEqual(frame.sensor_timestamp, 1.2345)
        self.assertEqual(frame.frame_number, 7)
        self.assertEqual(frame.color_rgb[0, 0].tolist(), [30, 20, 10])
        color[:] = 0
        self.assertEqual(frame.color_bgr[0, 0].tolist(), [10, 20, 30])


if __name__ == '__main__':
    unittest.main()

import unittest

import numpy as np

from zta.adapters.realsense import RealSenseFrameSource


class _Intrinsics:
    width = 4
    height = 3
    fx = 100.0
    fy = 101.0
    ppx = 2.0
    ppy = 1.5
    model = "brown"
    coeffs = [0, 0, 0, 0, 0]


class _VideoProfile:
    intrinsics = _Intrinsics()

    def as_video_stream_profile(self):
        return self


class _ColorFrame:
    profile = _VideoProfile()

    def get_data(self):
        data = np.zeros((3, 4, 3), dtype=np.uint8)
        data[:, :, 0] = 10
        data[:, :, 2] = 30
        return data

    def get_frame_number(self):
        return 42


class _DepthFrame:
    def get_data(self):
        return np.full((3, 4), 700, dtype=np.uint16)


class _Frames:
    def get_color_frame(self):
        return _ColorFrame()

    def get_depth_frame(self):
        return _DepthFrame()


class _DepthSensor:
    def get_depth_scale(self):
        return 0.001


class _Device:
    def first_depth_sensor(self):
        return _DepthSensor()

    def get_info(self, key):
        return {"name": "Intel RealSense D435", "serial": "1234"}[key]


class _PipelineProfile:
    def get_device(self):
        return _Device()


class _Config:
    def __init__(self):
        self.serial = None
        self.streams = []

    def enable_device(self, serial):
        self.serial = serial

    def enable_stream(self, *values):
        self.streams.append(values)


class _Pipeline:
    def __init__(self):
        self.config = None
        self.stopped = False
        self.timeout = None

    def start(self, config):
        self.config = config
        return _PipelineProfile()

    def wait_for_frames(self, timeout):
        self.timeout = timeout
        return _Frames()

    def stop(self):
        self.stopped = True


class _Align:
    def process(self, frames):
        return frames


class _RS:
    class stream:
        depth = "depth"
        color = "color"

    class format:
        z16 = "z16"
        bgr8 = "bgr8"

    class camera_info:
        name = "name"
        serial_number = "serial"

    def __init__(self):
        self.pipeline_instance = _Pipeline()
        self.config_instance = _Config()

    def pipeline(self):
        return self.pipeline_instance

    def config(self):
        return self.config_instance

    def align(self, stream):
        if stream != self.stream.color:
            raise AssertionError("depth must align to color")
        return _Align()


class RealSenseFrameSourceTests(unittest.TestCase):
    def test_returns_sdk_free_aligned_rgbd_frame_and_releases_pipeline(self):
        rs = _RS()
        source = RealSenseFrameSource(
            serial="1234", width=4, height=3, clock=lambda: 12.5, rs_module=rs,
        )

        source.start()
        frame = source.read()
        source.stop()

        self.assertEqual("1234", rs.config_instance.serial)
        self.assertEqual(2, len(rs.config_instance.streams))
        self.assertEqual((3, 4, 3), frame.color_bgr.shape)
        self.assertEqual((3, 4), frame.aligned_depth.shape)
        self.assertEqual(30, frame.color_rgb[0, 0, 0])
        self.assertEqual(10, frame.color_rgb[0, 0, 2])
        self.assertEqual(0.001, frame.depth_scale)
        self.assertEqual(42, frame.frame_number)
        self.assertEqual(12.5, frame.captured_at)
        self.assertEqual("Intel RealSense D435", source.device_name)
        self.assertTrue(rs.pipeline_instance.stopped)


if __name__ == "__main__":
    unittest.main()

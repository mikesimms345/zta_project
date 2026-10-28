"""Intel RealSense RGB-D source; SDK objects do not cross this boundary."""
from time import monotonic

from ..media import CameraIntrinsics, RGBDFrame


class RealSenseFrameSource:
    def __init__(self, *, serial=None, width=640, height=480, fps=30,
                 timeout_ms=1000, clock=monotonic, rs_module=None):
        self.serial = serial or None
        self.width = width
        self.height = height
        self.fps = fps
        self.timeout_ms = timeout_ms
        self.clock = clock
        self._rs_module = rs_module
        self._pipeline = None
        self._align = None
        self._depth_scale = None
        self.device_name = ""
        self.device_serial = ""

    def _rs(self):
        if self._rs_module is None:
            import pyrealsense2 as rs
            self._rs_module = rs
        return self._rs_module

    def start(self):
        if self._pipeline is not None:
            raise RuntimeError("RealSense source is already running")
        rs = self._rs()
        pipeline = rs.pipeline()
        config = rs.config()
        if self.serial:
            config.enable_device(self.serial)
        config.enable_stream(
            rs.stream.depth, self.width, self.height, rs.format.z16, self.fps,
        )
        config.enable_stream(
            rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps,
        )
        try:
            profile = pipeline.start(config)
            device = profile.get_device()
            depth_sensor = device.first_depth_sensor()
            depth_scale = float(depth_sensor.get_depth_scale())
            if depth_scale <= 0:
                raise RuntimeError("RealSense returned an invalid depth scale")
            self.device_name = str(device.get_info(rs.camera_info.name))
            self.device_serial = str(device.get_info(rs.camera_info.serial_number))
            self._align = rs.align(rs.stream.color)
            self._depth_scale = depth_scale
            self._pipeline = pipeline
        except Exception:
            try:
                pipeline.stop()
            except Exception:
                pass
            raise

    def read(self):
        import numpy as np

        if self._pipeline is None:
            raise RuntimeError("RealSense source is not running")
        frames = self._pipeline.wait_for_frames(self.timeout_ms)
        aligned = self._align.process(frames)
        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()
        if not depth_frame or not color_frame:
            raise RuntimeError("RealSense did not return synchronized color and depth")

        color_bgr = np.asanyarray(color_frame.get_data()).copy()
        aligned_depth = np.asanyarray(depth_frame.get_data()).copy()
        if color_bgr.ndim != 3 or color_bgr.shape[2] != 3:
            raise RuntimeError("RealSense returned an invalid color frame")
        if aligned_depth.ndim != 2 or aligned_depth.shape != color_bgr.shape[:2]:
            raise RuntimeError("Aligned RealSense depth does not match color dimensions")

        video_profile = color_frame.profile.as_video_stream_profile()
        values = video_profile.intrinsics
        intrinsics = CameraIntrinsics(
            width=int(values.width),
            height=int(values.height),
            fx=float(values.fx),
            fy=float(values.fy),
            ppx=float(values.ppx),
            ppy=float(values.ppy),
            distortion_model=str(values.model),
            coefficients=tuple(float(value) for value in values.coeffs),
        )
        return RGBDFrame(
            color_bgr=color_bgr,
            color_rgb=color_bgr[:, :, ::-1].copy(),
            aligned_depth=aligned_depth,
            depth_scale=self._depth_scale,
            intrinsics=intrinsics,
            frame_number=int(color_frame.get_frame_number()),
            captured_at=self.clock(),
        )

    def stop(self):
        pipeline = self._pipeline
        self._pipeline = None
        self._align = None
        self._depth_scale = None
        if pipeline is not None:
            pipeline.stop()

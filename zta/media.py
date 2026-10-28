"""Framework-independent contracts for synchronized local RGB-D capture."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CameraIntrinsics:
    width: int
    height: int
    fx: float
    fy: float
    ppx: float
    ppy: float
    distortion_model: str
    coefficients: tuple


@dataclass(frozen=True)
class RGBDFrame:
    color_bgr: object
    color_rgb: object
    aligned_depth: object
    depth_scale: float
    intrinsics: CameraIntrinsics
    frame_number: int
    captured_at: float


class RGBDFrameSource(Protocol):
    def start(self):
        """Acquire the RGB-D device."""

    def read(self) -> RGBDFrame:
        """Return one synchronized color/depth frameset."""

    def stop(self):
        """Release the device."""

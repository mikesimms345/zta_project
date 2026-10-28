"""Validation for in-memory RGB frames supplied by the Python camera pipeline."""
import numpy as np

from ..domain import InvalidFrame


def validate_rgb_frame(frame):
    """Return a contiguous uint8 HWC RGB array within the prototype size bound."""
    pixels = np.asarray(frame)
    if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3:
        raise InvalidFrame("Expected an 8-bit RGB frame")
    height, width = pixels.shape[:2]
    if width < 1 or height < 1 or width * height > 1920 * 1080:
        raise InvalidFrame("Expected a frame at most 1920x1080 pixels")
    return np.ascontiguousarray(pixels)

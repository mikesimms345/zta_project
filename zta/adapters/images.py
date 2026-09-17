"""Shared bounded JPEG decoding for video model adapters."""
from io import BytesIO
import warnings
from PIL import Image, UnidentifiedImageError
from ..domain import InvalidFrame


def decode_frame(encoded_image):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(encoded_image)) as source:
                if source.format != "JPEG" or source.width * source.height > 1920 * 1080:
                    raise InvalidFrame("Expected JPEG at most 1920x1080 pixels")
                image = source.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise InvalidFrame("Invalid JPEG frame") from exc
    return image

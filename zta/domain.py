"""Framework-free evidence contracts; these are not authentication decisions."""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Label(str, Enum):
    REAL = "real"
    FAKE = "fake"


class Status(str, Enum):
    COLLECTING = "collecting"
    FLAGGED = "flagged"
    BELOW_THRESHOLD = "below_threshold"


@dataclass(frozen=True)
class Prediction:
    label: Label
    model_id: str


@dataclass(frozen=True)
class Evidence:
    status: Status
    sample_count: int
    fake_count: int
    fake_ratio: float
    window_size: int
    model_id: str


class FrameClassifier(Protocol):
    def classify(self, encoded_image: bytes) -> Prediction:
        """Return media evidence or raise; never fabricate a successful result."""


class InvalidFrame(ValueError):
    pass


class ModelUnavailable(RuntimeError):
    pass

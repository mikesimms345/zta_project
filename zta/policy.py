"""Pure rolling-window aggregation, independent of transport and access policy."""
from collections import deque
from dataclasses import dataclass
import math

from .domain import Evidence, Prediction, Label, Status


@dataclass(frozen=True)
class EvidencePolicy:
    window_size: int = 75
    fake_threshold: float = 0.70

    def __post_init__(self):
        if type(self.window_size) is not int or self.window_size < 1:
            raise ValueError("window_size must be a positive integer")
        if not math.isfinite(self.fake_threshold) or not 0 < self.fake_threshold <= 1:
            raise ValueError("fake_threshold must be in (0, 1]")

    def new_window(self):
        return deque(maxlen=self.window_size)

    def evaluate(self, window, prediction: Prediction) -> Evidence:
        fake_count = sum(label == Label.FAKE for label in window)
        count = len(window)
        ratio = fake_count / count if count else 0.0
        status = Status.COLLECTING
        if count == self.window_size:
            status = Status.FLAGGED if ratio >= self.fake_threshold else Status.BELOW_THRESHOLD
        return Evidence(status, count, fake_count, ratio, self.window_size, prediction.model_id)

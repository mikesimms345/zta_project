"""Contracts for depth liveness observations and temporal evidence."""
from dataclasses import dataclass
from enum import Enum


class LivenessStatus(str, Enum):
    COLLECTING = "collecting"
    LIVE = "live"
    SPOOF_SUSPECTED = "spoof_suspected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class DepthLivenessObservation:
    candidate: bool
    reason: str
    face_box: tuple | None
    valid_depth_ratio: float
    median_depth_m: float | None
    relief_m: float | None
    captured_at: float
    analyzer_id: str


@dataclass(frozen=True)
class LivenessEvidence:
    status: LivenessStatus
    instruction: str
    reason: str
    observation_count: int
    live_observation_count: int
    challenge_complete: bool
    valid_depth_ratio: float
    median_depth_m: float | None
    relief_m: float | None
    face_box: tuple | None
    analyzer_id: str

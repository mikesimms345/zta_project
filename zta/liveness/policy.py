"""Temporal liveness policy with a simple depth-motion challenge."""
from .domain import LivenessEvidence, LivenessStatus


class DepthLivenessPolicy:
    def __init__(self, *, required_live_observations=5, closer_delta_m=0.05,
                 return_delta_m=0.04, spoof_streak=5, unavailable_streak=25):
        if required_live_observations < 1 or spoof_streak < 1 or unavailable_streak < 1:
            raise ValueError("liveness streak lengths must be positive")
        if closer_delta_m <= 0 or return_delta_m <= 0:
            raise ValueError("liveness challenge deltas must be positive")
        self.required_live_observations = required_live_observations
        self.closer_delta_m = closer_delta_m
        self.return_delta_m = return_delta_m
        self.spoof_streak = spoof_streak
        self.unavailable_streak = unavailable_streak
        self._observation_count = 0
        self._live_count = 0
        self._planar_streak = 0
        self._unavailable_streak = 0
        self._baseline_depth = None
        self._close_depth = None
        self._challenge_complete = False
        self._spoof_suspected = False

    def evaluate(self, observation):
        self._observation_count += 1
        if observation.candidate:
            self._live_count += 1
            self._planar_streak = 0
            self._unavailable_streak = 0
            self._advance_challenge(observation.median_depth_m)
        else:
            if observation.reason == "planar_surface":
                self._planar_streak += 1
                self._unavailable_streak = 0
                if self._planar_streak >= self.spoof_streak:
                    self._spoof_suspected = True
            else:
                self._planar_streak = 0
                self._unavailable_streak += 1

        status = LivenessStatus.COLLECTING
        if self._spoof_suspected:
            status = LivenessStatus.SPOOF_SUSPECTED
        elif self._unavailable_streak >= self.unavailable_streak:
            status = LivenessStatus.UNAVAILABLE
        elif (self._challenge_complete
              and self._live_count >= self.required_live_observations):
            status = LivenessStatus.LIVE

        return LivenessEvidence(
            status=status,
            instruction=self._instruction(status, observation.reason),
            reason=observation.reason,
            observation_count=self._observation_count,
            live_observation_count=self._live_count,
            challenge_complete=self._challenge_complete,
            valid_depth_ratio=observation.valid_depth_ratio,
            median_depth_m=observation.median_depth_m,
            relief_m=observation.relief_m,
            face_box=observation.face_box,
            analyzer_id=observation.analyzer_id,
        )

    def _advance_challenge(self, depth):
        if depth is None or self._challenge_complete:
            return
        if self._baseline_depth is None:
            self._baseline_depth = depth
            return
        if self._close_depth is None:
            if depth <= self._baseline_depth - self.closer_delta_m:
                self._close_depth = depth
            return
        if depth >= self._close_depth + self.return_delta_m:
            self._challenge_complete = True

    def _instruction(self, status, reason):
        if status == LivenessStatus.LIVE:
            return "Depth liveness challenge complete"
        if status == LivenessStatus.SPOOF_SUSPECTED:
            return "Depth surface appears too flat"
        if reason == "no_face":
            return "Center your face in the RGB view"
        if reason == "face_too_small":
            return "Move closer to the camera"
        if reason == "insufficient_depth":
            return "Hold still so the depth camera can resolve your face"
        if reason == "out_of_range":
            return "Stay between 0.3 m and 1.5 m from the camera"
        if self._baseline_depth is None:
            return "Hold still to begin the depth challenge"
        if self._close_depth is None:
            return "Move about 5 cm closer to the camera"
        return "Move back to your starting position"

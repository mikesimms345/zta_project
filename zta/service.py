"""Application orchestration with expiring per-capture state."""
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from uuid import uuid4

from .domain import FrameClassifier, Label, ModelUnavailable
from .policy import EvidencePolicy


class SessionNotFound(LookupError):
    pass


class CapacityExceeded(RuntimeError):
    pass


@dataclass
class CaptureSession:
    owner: str
    expires_at: float
    window: object
    model_id: str = ""


class VerificationService:
    def __init__(self, classifier: FrameClassifier, policy=None, *, clock=monotonic,
                 ttl=300, max_sessions=32):
        if ttl <= 0 or max_sessions < 1:
            raise ValueError("ttl and max_sessions must be positive")
        self.classifier = classifier
        self.policy = policy or EvidencePolicy()
        self.clock, self.ttl, self.max_sessions = clock, ttl, max_sessions
        self._sessions = {}
        self._lock = RLock()

    def _prune(self):
        now = self.clock()
        for key in list(self._sessions):
            if self._sessions[key].expires_at <= now:
                del self._sessions[key]

    def start(self, owner):
        if not owner:
            raise ValueError("owner is required")
        with self._lock:
            self._prune()
            if len(self._sessions) >= self.max_sessions:
                raise CapacityExceeded("Capture capacity reached")
            key = uuid4().hex
            self._sessions[key] = CaptureSession(owner, self.clock() + self.ttl,
                                                  self.policy.new_window())
            return key

    def _get(self, key, owner):
        self._prune()
        capture = self._sessions.get(key)
        if capture is None or capture.owner != owner:
            raise SessionNotFound("Capture not found or expired")
        return capture

    def submit(self, key, owner, encoded_image):
        # Deliberately serialized for the single-process local harness. A production
        # deployment should inject a durable store and a bounded inference worker.
        with self._lock:
            capture = self._get(key, owner)
            prediction = self.classifier.classify(encoded_image)
            capture = self._get(key, owner)  # inference may outlive the capture TTL
            if not isinstance(prediction.label, Label) or not prediction.model_id:
                raise ModelUnavailable("Invalid classifier result")
            if capture.model_id and capture.model_id != prediction.model_id:
                capture.window.clear()  # do not mix evidence across model upgrades
            capture.model_id = prediction.model_id
            capture.window.append(prediction.label)
            return self.policy.evaluate(capture.window, prediction)

    def stop(self, key, owner):
        with self._lock:
            self._get(key, owner)
            del self._sessions[key]

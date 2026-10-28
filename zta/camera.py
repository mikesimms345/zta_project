"""Python-owned RGB-D capture, inference coordination, and result delivery."""
from dataclasses import asdict, dataclass
import logging
from threading import Condition, Event, RLock, Thread
from time import monotonic

from .adapters.realsense import RealSenseFrameSource
from .domain import ModelUnavailable
from .liveness import DepthLivenessAnalyzer, DepthLivenessPolicy
from .preview import SideBySidePreviewRenderer


LOG = logging.getLogger(__name__)
TERMINAL_PHASES = frozenset({"failed", "stopped"})


class CameraBusy(RuntimeError):
    pass


class CameraRunNotFound(LookupError):
    pass


@dataclass
class _CameraRun:
    owner: str
    stop_event: Event
    phase: str = "starting"
    evidence: object = None
    liveness: object = None
    error: str = ""
    version: int = 0
    thread: object = None


class RGBDCameraPipeline:
    """Coordinate one RGB-D source, independent evidence paths, and preview."""

    def __init__(self, submit_prediction, *, device_serial=None, sample_interval=0.2,
                 preview=True, clock=monotonic, source_factory=None,
                 liveness_analyzer=None, liveness_policy_factory=None,
                 preview_renderer=None):
        if sample_interval < 0:
            raise ValueError("sample_interval must be non-negative")
        self._submit_prediction = submit_prediction
        self.device_serial = device_serial or None
        self.sample_interval = sample_interval
        self.preview = preview
        self.clock = clock
        self._source_factory = source_factory or (
            lambda: RealSenseFrameSource(serial=self.device_serial)
        )
        self._liveness_analyzer = liveness_analyzer or DepthLivenessAnalyzer()
        self._liveness_policy_factory = (
            liveness_policy_factory or DepthLivenessPolicy
        )
        self._preview_renderer = preview_renderer or SideBySidePreviewRenderer()
        self._runs = {}
        self._lock = RLock()
        self._changed = Condition(self._lock)

    def _get(self, key, owner):
        run = self._runs.get(key)
        if run is None or run.owner != owner:
            raise CameraRunNotFound("Camera check not found")
        return run

    def _update(self, run, *, phase=None, evidence=None, liveness=None, error=None):
        with self._changed:
            if phase is not None:
                run.phase = phase
            if evidence is not None:
                run.evidence = evidence
            if liveness is not None:
                run.liveness = liveness
            if error is not None:
                run.error = error
            run.version += 1
            self._changed.notify_all()

    def start(self, key, owner):
        with self._changed:
            self._runs = {
                run_key: run for run_key, run in self._runs.items()
                if run.thread and run.thread.is_alive()
            }
            if any(run.thread and run.thread.is_alive() for run in self._runs.values()):
                raise CameraBusy("The local camera is already in use")
            run = _CameraRun(owner=owner, stop_event=Event())
            thread = Thread(target=self._run, args=(key, run),
                            name=f"zta-camera-{key[:8]}", daemon=True)
            run.thread = thread
            self._runs[key] = run
            thread.start()

    def stop(self, key, owner, *, wait=3.0):
        with self._changed:
            run = self._get(key, owner)
            run.stop_event.set()
            thread = run.thread
            self._changed.notify_all()
        if thread and thread.is_alive():
            thread.join(wait)
        if thread and thread.is_alive():
            raise CameraBusy("Camera worker did not stop in time")
        with self._changed:
            if run.phase not in TERMINAL_PHASES:
                self._update(run, phase="stopped")

    def snapshot(self, key, owner):
        with self._lock:
            run = self._get(key, owner)
            return self._snapshot(run)

    def wait_for_update(self, key, owner, version, *, timeout=15.0):
        with self._changed:
            run = self._get(key, owner)
            if run.version == version and run.phase not in TERMINAL_PHASES:
                self._changed.wait_for(
                    lambda: run.version != version or run.phase in TERMINAL_PHASES,
                    timeout=timeout,
                )
            return run.version, self._snapshot(run)

    @staticmethod
    def _snapshot(run):
        result = {"phase": run.phase, "error": run.error}
        if run.evidence is not None:
            result.update(asdict(run.evidence))
        if run.liveness is not None:
            result["liveness"] = asdict(run.liveness)
        return result

    def _run(self, key, run):
        source = None
        terminal_phase = "stopped"
        terminal_error = ""
        window_name = f"ZTA RGB-D check {key[:8]} (Q or Esc to stop)"
        try:
            source = self._source_factory()
            source.start()
            liveness_policy = self._liveness_policy_factory()
            self._update(run, phase="running")
            next_sample = self.clock()

            while not run.stop_event.is_set():
                frame = source.read()

                now = self.clock()
                if now >= next_sample:
                    observation = self._liveness_analyzer.analyze(frame)
                    liveness = liveness_policy.evaluate(observation)
                    evidence = self._submit_prediction(
                        key, run.owner, frame.color_rgb,
                    )
                    self._update(run, evidence=evidence, liveness=liveness)
                    next_sample = self.clock() + self.sample_interval
                if self.preview:
                    if self._preview_renderer.show(
                        window_name, frame, run.evidence, run.liveness,
                    ):
                        run.stop_event.set()

        except ModelUnavailable:
            LOG.exception("Video model unavailable")
            terminal_phase = "failed"
            terminal_error = "Video model unavailable; no result recorded"
        except Exception:
            LOG.exception("RGB-D camera pipeline failed")
            terminal_phase = "failed"
            terminal_error = "Local RGB-D camera check failed; see server log"
        finally:
            if source is not None:
                try:
                    source.stop()
                except Exception:
                    LOG.exception("Could not cleanly stop the RGB-D source")
            if self.preview:
                try:
                    self._preview_renderer.close(window_name)
                except Exception:
                    LOG.debug("OpenCV preview window was already closed", exc_info=True)
            self._update(run, phase=terminal_phase, error=terminal_error)

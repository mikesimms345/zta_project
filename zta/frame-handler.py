"""RGB-D frame contracts, inference coordination, and result delivery."""
from dataclasses import asdict, dataclass
from importlib import import_module
import logging
import math
from queue import Empty, Full, Queue
from threading import Condition, Event, RLock, Thread
from time import monotonic
from typing import Protocol

from .liveness import DepthLivenessAnalyzer, DepthLivenessPolicy
from .liveness.rppg import PosRppgAnalyzer
from .preview import SideBySidePreviewRenderer


ModelUnavailable = import_module('.deepfake-detection.domain', __package__).ModelUnavailable
LOG = logging.getLogger(__name__)
TERMINAL_PHASES = frozenset({"failed", "stopped", "completed"})


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
    sensor_timestamp: float | None = None


class RGBDFrameSource(Protocol):
    def start(self):
        """Acquire the RGB-D device."""

    def read(self) -> RGBDFrame:
        """Return one synchronized color/depth frameset."""

    def stop(self):
        """Release the device."""


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
    observation: object = None
    rppg: object = None
    error: str = ""
    version: int = 0
    thread: object = None
    workers: tuple = ()
    worker_error: bool = False


class RGBDCameraPipeline:
    """Coordinate one RGB-D source, independent evidence paths, and preview."""

    def __init__(self, submit_prediction, *, device_serial=None, sample_interval=0.2,
                 preview=True, clock=monotonic, source_factory=None,
                 liveness_analyzer=None, liveness_policy_factory=None,
                 preview_renderer=None, rppg_factory=None, capture_seconds=15.0,
                 preview_interval=0.1):
        if not math.isfinite(sample_interval) or sample_interval < 0:
            raise ValueError("sample_interval must be non-negative")
        if not math.isfinite(capture_seconds) or capture_seconds <= 0:
            raise ValueError("capture_seconds must be finite and positive")
        if not math.isfinite(preview_interval) or preview_interval <= 0:
            raise ValueError("preview_interval must be finite and positive")
        self._submit_prediction = submit_prediction
        self.device_serial = device_serial or None
        self.sample_interval = sample_interval
        self.preview = preview
        self.clock = clock
        self.capture_seconds = capture_seconds
        self.preview_interval = preview_interval
        self._rppg_factory = rppg_factory or PosRppgAnalyzer
        self._source_factory = source_factory or self._create_realsense_source
        self._liveness_analyzer = liveness_analyzer or DepthLivenessAnalyzer()
        self._liveness_policy_factory = (
            liveness_policy_factory or DepthLivenessPolicy
        )
        self._preview_renderer = preview_renderer or SideBySidePreviewRenderer()
        self._runs = {}
        self._lock = RLock()
        self._changed = Condition(self._lock)

    def _create_realsense_source(self):
        # The adapter imports our frame types; defer its import to avoid a cycle.
        from .realsense import RealSenseFrameSource

        return RealSenseFrameSource(serial=self.device_serial)

    def _get(self, key, owner):
        run = self._runs.get(key)
        if run is None or run.owner != owner:
            raise CameraRunNotFound("Camera check not found")
        return run

    def _update(self, run, *, phase=None, evidence=None, liveness=None, error=None,
                observation=None, rppg=None):
        with self._changed:
            # In-flight inference cannot publish after stop/deadline/failure.
            if phase is None and run.stop_event.is_set():
                return
            if phase is not None:
                run.phase = phase
            if evidence is not None:
                run.evidence = evidence
            if liveness is not None:
                run.liveness = liveness
            if observation is not None:
                run.observation = observation
            if rppg is not None:
                run.rppg = rppg
            if error is not None:
                run.error = error
            run.version += 1
            self._changed.notify_all()

    def start(self, key, owner):
        with self._changed:
            self._runs = {
                run_key: run for run_key, run in self._runs.items()
                if self._active(run)
            }
            if any(self._active(run) for run in self._runs.values()):
                raise CameraBusy("The local camera is already in use")
            run = _CameraRun(owner=owner, stop_event=Event())
            thread = Thread(target=self._run, args=(key, run),
                            name=f"zta-camera-{key[:8]}", daemon=True)
            run.thread = thread
            self._runs[key] = run
            thread.start()

    @staticmethod
    def _active(run):
        return any(thread is not None and thread.is_alive()
                   for thread in (run.thread, *run.workers))

    def stop(self, key, owner, *, wait=3.0):
        with self._changed:
            run = self._get(key, owner)
            run.stop_event.set()
            thread = run.thread
            self._changed.notify_all()
        if thread and thread.is_alive():
            thread.join(wait)
        if self._active(run):
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
        if run.rppg is not None:
            result["rppg"] = asdict(run.rppg)
        return result

    @staticmethod
    def _offer_latest(queue, frame):
        # One pending frame per slow consumer, plus its currently processing frame.
        try:
            queue.put_nowait(frame)
        except Full:
            try:
                queue.get_nowait()
            except Empty:
                pass
            queue.put_nowait(frame)

    def _consume(self, run, queue, analyze):
        next_sample = float('-inf')
        try:
            while not run.stop_event.is_set():
                try:
                    frame = queue.get(timeout=0.1)
                except Empty:
                    continue
                if frame.captured_at < next_sample or run.stop_event.is_set():
                    continue
                analyze(frame)
                next_sample = frame.captured_at + self.sample_interval
        except Exception:
            LOG.exception("Camera analysis worker failed")
            with self._lock:
                # Do not retain exceptions/tracebacks that could keep raw frames alive.
                run.worker_error = True
            run.stop_event.set()

    def _run(self, key, run):
        source = None
        rppg = None
        queues = (Queue(maxsize=1), Queue(maxsize=1))
        terminal_phase = "stopped"
        terminal_error = ""
        window_name = f"ZTA RGB-D check {key[:8]} (Q or Esc to stop)"
        try:
            source = self._source_factory()
            source.start()
            liveness_policy = self._liveness_policy_factory()
            rppg = self._rppg_factory()

            def depth(frame):
                observation = self._liveness_analyzer.analyze(frame)
                self._update(run, observation=observation,
                             liveness=liveness_policy.evaluate(observation))

            def media(frame):
                self._update(run, evidence=self._submit_prediction(key, run.owner, frame.color_rgb))

            run.workers = tuple(
                Thread(target=self._consume, args=(run, queue, analyze),
                       name=f"zta-{name}-{key[:8]}", daemon=True)
                for name, queue, analyze in zip(("depth", "cnn"), queues, (depth, media))
            )
            for worker in run.workers:
                worker.start()
            self._update(run, phase="running", rppg=rppg.evidence)
            deadline = self.clock() + self.capture_seconds
            next_preview = next_status = self.clock()

            while not run.stop_event.is_set():
                if self.clock() >= deadline:
                    terminal_phase = "completed"
                    break
                frame = source.read()
                now = self.clock()
                if now >= deadline:
                    terminal_phase = "completed"
                    break
                for queue in queues:
                    self._offer_latest(queue, frame)
                with self._lock:
                    observation, liveness = run.observation, run.liveness
                pulse = rppg.update(
                    frame, observation,
                    challenge_complete=(liveness is not None
                                        and liveness.status.value == "live"
                                        and liveness.challenge_complete),
                )
                if now >= next_status:
                    self._update(run, rppg=pulse)
                    next_status = now + 0.2
                if self.preview and now >= next_preview:
                    if self._preview_renderer.show(
                        window_name, frame, run.evidence, run.liveness, pulse,
                    ):
                        run.stop_event.set()
                    next_preview = now + self.preview_interval

        except ModelUnavailable:
            LOG.exception("Video model unavailable")
            terminal_phase = "failed"
            terminal_error = "Video model unavailable; no result recorded"
        except Exception:
            LOG.exception("RGB-D camera pipeline failed")
            terminal_phase = "failed"
            terminal_error = "Local RGB-D camera check failed; see server log"
        finally:
            run.stop_event.set()
            if source is not None:
                try:
                    source.stop()
                except Exception:
                    LOG.exception("Could not cleanly stop the RGB-D source")
                    terminal_phase = "failed"
                    terminal_error = "Could not release the camera; restart the application"
            # Bounded waiting; a hung consumer keeps the camera slot busy until it exits.
            join_deadline = monotonic() + 2.0
            for worker in run.workers:
                if worker.ident is not None:
                    worker.join(max(0.0, join_deadline - monotonic()))
            for queue in queues:
                try:
                    queue.get_nowait()
                except Empty:
                    pass
            if run.worker_error or any(worker.is_alive() for worker in run.workers):
                terminal_phase = "failed"
                terminal_error = "Camera analysis failed or did not stop; no successful check recorded"
            if rppg is not None:
                with self._lock:
                    run.rppg = rppg.finish() if terminal_phase == "completed" else rppg.abort()
                rppg.clear()
            if self.preview:
                try:
                    self._preview_renderer.close(window_name)
                except Exception:
                    LOG.debug("OpenCV preview window was already closed", exc_info=True)
            self._update(run, phase=terminal_phase, error=terminal_error)

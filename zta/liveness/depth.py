"""Prototype facial-depth analyzer for planar presentation-attack detection."""
import math

from .domain import DepthLivenessObservation


class DepthLivenessAnalyzer:
    """Measure face depth coverage and non-planar relief in an aligned frame."""

    ANALYZER_ID = "depth-plane-residual-v1"

    def __init__(self, *, min_valid_ratio=0.60, min_depth_m=0.30,
                 max_depth_m=1.50, min_relief_m=0.012, face_detector=None,
                 max_fit_points=5000, cv2_module=None):
        if not 0 < min_valid_ratio <= 1:
            raise ValueError("min_valid_ratio must be in (0, 1]")
        if min_depth_m <= 0 or max_depth_m <= min_depth_m:
            raise ValueError("invalid liveness depth range")
        if min_relief_m <= 0 or max_fit_points < 100:
            raise ValueError("invalid liveness geometry configuration")
        self.min_valid_ratio = min_valid_ratio
        self.min_depth_m = min_depth_m
        self.max_depth_m = max_depth_m
        self.min_relief_m = min_relief_m
        self.max_fit_points = max_fit_points
        self._face_detector = face_detector
        self._cv2_module = cv2_module
        self._cascade = None

    def _cv2(self):
        if self._cv2_module is None:
            import cv2
            self._cv2_module = cv2
        return self._cv2_module

    def _detect_faces(self, color_bgr):
        cv2 = self._cv2()
        if self._face_detector is not None:
            return self._face_detector(color_bgr)
        if self._cascade is None:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(path)
            if cascade.empty():
                raise RuntimeError("Could not load OpenCV frontal-face detector")
            self._cascade = cascade
        gray = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2GRAY)
        return self._cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80),
        )

    def analyze(self, frame):
        import numpy as np

        color = np.asarray(frame.color_bgr)
        depth = np.asarray(frame.aligned_depth)
        if color.ndim != 3 or color.shape[2] != 3:
            raise ValueError("Expected a BGR color frame")
        if depth.ndim != 2 or depth.shape != color.shape[:2]:
            raise ValueError("Expected depth aligned to the color frame")
        if not math.isfinite(frame.depth_scale) or frame.depth_scale <= 0:
            raise ValueError("Invalid depth scale")

        faces = list(self._detect_faces(color))
        if not faces:
            return self._observation(frame, False, "no_face")
        x, y, width, height = max(faces, key=lambda box: int(box[2]) * int(box[3]))
        x, y, width, height = (int(x), int(y), int(width), int(height))
        x = max(0, x)
        y = max(0, y)
        width = min(width, depth.shape[1] - x)
        height = min(height, depth.shape[0] - y)
        face_box = (x, y, width, height)
        if width < 20 or height < 20:
            return self._observation(frame, False, "face_too_small", face_box)

        face_depth = depth[y:y + height, x:x + width].astype(np.float32)
        row, column = np.ogrid[:height, :width]
        center_x = (width - 1) / 2
        center_y = (height - 1) * 0.52
        ellipse = (
            ((column - center_x) / max(width * 0.43, 1)) ** 2
            + ((row - center_y) / max(height * 0.50, 1)) ** 2
        ) <= 1
        valid = ellipse & (face_depth > 0)
        ellipse_count = int(np.count_nonzero(ellipse))
        valid_count = int(np.count_nonzero(valid))
        valid_ratio = valid_count / ellipse_count if ellipse_count else 0.0
        if valid_ratio < self.min_valid_ratio:
            return self._observation(
                frame, False, "insufficient_depth", face_box, valid_ratio,
            )

        depth_m = face_depth * frame.depth_scale
        values = depth_m[valid]
        median_depth = float(np.median(values))
        if median_depth < self.min_depth_m or median_depth > self.max_depth_m:
            return self._observation(
                frame, False, "out_of_range", face_box, valid_ratio,
                median_depth,
            )

        rows, columns = np.nonzero(valid)
        sample_step = max(1, math.ceil(valid_count / self.max_fit_points))
        rows = rows[::sample_step]
        columns = columns[::sample_step]
        samples = depth_m[rows, columns]
        normalized_x = (columns - center_x) / max(width, 1)
        normalized_y = (rows - center_y) / max(height, 1)
        design = np.column_stack((normalized_x, normalized_y, np.ones_like(normalized_x)))
        plane, *_ = np.linalg.lstsq(design, samples, rcond=None)
        residual = samples - design @ plane
        relief = float(np.percentile(residual, 95) - np.percentile(residual, 5))
        candidate = relief >= self.min_relief_m
        reason = "depth_candidate" if candidate else "planar_surface"
        return self._observation(
            frame, candidate, reason, face_box, valid_ratio, median_depth, relief,
        )

    def _observation(self, frame, candidate, reason, face_box=None,
                     valid_depth_ratio=0.0, median_depth_m=None, relief_m=None):
        return DepthLivenessObservation(
            candidate=candidate,
            reason=reason,
            face_box=face_box,
            valid_depth_ratio=float(valid_depth_ratio),
            median_depth_m=median_depth_m,
            relief_m=relief_m,
            captured_at=float(frame.captured_at),
            analyzer_id=self.ANALYZER_ID,
        )

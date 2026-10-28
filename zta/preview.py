"""OpenCV renderer for one side-by-side RGB and aligned-depth window."""


class SideBySidePreviewRenderer:
    def __init__(self, *, enabled=True, min_depth_m=0.30, max_depth_m=1.50,
                 cv2_module=None):
        self.enabled = enabled
        self.min_depth_m = min_depth_m
        self.max_depth_m = max_depth_m
        self._cv2_module = cv2_module

    def _cv2(self):
        if self._cv2_module is None:
            import cv2
            self._cv2_module = cv2
        return self._cv2_module

    def compose(self, frame, media_evidence=None, liveness=None):
        import numpy as np

        cv2 = self._cv2()
        color = frame.color_bgr.copy()
        depth_m = frame.aligned_depth.astype(np.float32) * frame.depth_scale
        valid = (depth_m >= self.min_depth_m) & (depth_m <= self.max_depth_m)
        normalized = np.zeros(depth_m.shape, dtype=np.uint8)
        normalized[valid] = np.clip(
            (self.max_depth_m - depth_m[valid])
            / (self.max_depth_m - self.min_depth_m) * 255,
            0,
            255,
        ).astype(np.uint8)
        depth_view = cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)
        depth_view[~valid] = 0
        if depth_view.shape[:2] != color.shape[:2]:
            depth_view = cv2.resize(
                depth_view, (color.shape[1], color.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )

        if liveness is not None and liveness.face_box is not None:
            x, y, width, height = liveness.face_box
            box_color = (0, 255, 0) if liveness.status.value == "live" else (0, 215, 255)
            cv2.rectangle(color, (x, y), (x + width, y + height), box_color, 2)
            cv2.rectangle(depth_view, (x, y), (x + width, y + height), box_color, 2)

        media_text = "Media: starting"
        if media_evidence is not None:
            media_text = (
                f"Media: {media_evidence.status.value} "
                f"{media_evidence.sample_count}/{media_evidence.window_size}"
            )
        self._text(cv2, color, "RGB / LiteRT", 26)
        self._text(cv2, color, media_text, 52)
        self._text(cv2, depth_view, "Aligned depth / liveness", 26)
        if liveness is not None:
            self._text(cv2, depth_view, f"Liveness: {liveness.status.value}", 52)
            self._text(cv2, depth_view, liveness.instruction, 78, scale=0.48)
            if liveness.median_depth_m is not None:
                metrics = f"Distance {liveness.median_depth_m:.2f} m"
                if liveness.relief_m is not None:
                    metrics += f"  relief {liveness.relief_m * 1000:.1f} mm"
                self._text(cv2, depth_view, metrics, 104, scale=0.48)
        return np.hstack((color, depth_view))

    @staticmethod
    def _text(cv2, image, value, y, *, scale=0.60):
        cv2.putText(
            image, value, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
            scale, (0, 0, 0), 4, cv2.LINE_AA,
        )
        cv2.putText(
            image, value, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
            scale, (255, 255, 255), 1, cv2.LINE_AA,
        )

    def show(self, window_name, frame, media_evidence=None, liveness=None):
        if not self.enabled:
            return False
        cv2 = self._cv2()
        cv2.imshow(window_name, self.compose(frame, media_evidence, liveness))
        return (cv2.waitKey(1) & 0xFF) in (27, ord("q"))

    def close(self, window_name):
        if not self.enabled:
            return
        cv2 = self._cv2()
        cv2.destroyWindow(window_name)
        cv2.waitKey(1)

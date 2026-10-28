"""Video classifier backed by Google's LiteRT Python runtime."""
from hashlib import sha256
from pathlib import Path
from threading import Lock

from ..domain import Label, ModelUnavailable, Prediction
from .images import validate_rgb_frame


class LiteRTFrameClassifier:
    def __init__(self, model_path, *, interpreter_factory=None):
        self.model_path = Path(model_path)
        self._interpreter_factory = interpreter_factory
        self._interpreter = None
        self._lock = Lock()
        self._model_id = ""

    def _load(self):
        if self._interpreter is not None:
            return
        try:
            factory = self._interpreter_factory
            if factory is None:
                from ai_edge_litert.interpreter import Interpreter
                factory = Interpreter
            interpreter = factory(model_path=str(self.model_path))
            interpreter.allocate_tensors()
            self._model_id = "sha256:" + sha256(self.model_path.read_bytes()).hexdigest()
            self._interpreter = interpreter
        except Exception as exc:
            raise ModelUnavailable("Could not initialize video model") from exc

    def classify(self, rgb_frame):
        import cv2
        import numpy as np

        image = validate_rgb_frame(rgb_frame)

        with self._lock:
            self._load()
            try:
                interpreter = self._interpreter
                inp = interpreter.get_input_details()[0]
                out = interpreter.get_output_details()[0]
                shape = tuple(inp['shape'])
                if len(shape) != 4 or shape[0] != 1:
                    raise ValueError("Expected a single-image tensor")
                chw = shape[1] == 3
                if not chw and shape[3] != 3:
                    raise ValueError("Expected RGB input")
                h, w = shape[2:4] if chw else shape[1:3]
                pixels = cv2.resize(image, (int(w), int(h)), interpolation=cv2.INTER_AREA)
                # Preserve the original model's input mapping. Its training
                # preprocessing must be validated separately on labeled samples.
                if inp['dtype'] == np.uint8:
                    tensor = pixels
                elif inp['dtype'] == np.int8:
                    tensor = (pixels.astype(np.int16) - 128).astype(np.int8)
                elif inp['dtype'] == np.float32:
                    tensor = pixels.astype(np.float32) / 255.0
                else:
                    raise ValueError("Unsupported input dtype")
                if chw:
                    tensor = tensor.transpose(2, 0, 1)
                interpreter.set_tensor(inp['index'], tensor[np.newaxis])
                interpreter.invoke()
                scores = interpreter.get_tensor(out['index']).copy().reshape(-1)
                if np.issubdtype(scores.dtype, np.integer):
                    scale, zero = out['quantization']
                    if scale <= 0:
                        raise ValueError("Missing output quantization")
                    scores = (scores.astype(np.float32) - zero) * scale
                if scores.size not in (1, 2) or not np.isfinite(scores).all():
                    raise ValueError("Unsupported model output")
                label = int(scores[0] >= 0.5) if scores.size == 1 else int(np.argmax(scores))
                return Prediction(Label.FAKE if label else Label.REAL, self._model_id)
            except Exception as exc:
                raise ModelUnavailable("Video inference failed") from exc

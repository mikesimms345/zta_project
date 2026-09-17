"""Video-only instance-based adapter derived from the capstone TFLite path."""
from hashlib import sha256
from pathlib import Path
from threading import Lock

from ..domain import Label, ModelUnavailable, Prediction
from .images import decode_frame


class TFLiteFrameClassifier:
    def __init__(self, model_path):
        self.model_path = Path(model_path)
        self._interpreter = None
        self._lock = Lock()
        self._model_id = ""

    def _load(self):
        if self._interpreter is not None:
            return
        try:
            try:
                from tflite_runtime.interpreter import Interpreter
            except ImportError:
                import tensorflow as tf
                Interpreter = tf.lite.Interpreter
            interpreter = Interpreter(model_path=str(self.model_path))
            interpreter.allocate_tensors()
            self._model_id = "sha256:" + sha256(self.model_path.read_bytes()).hexdigest()
            self._interpreter = interpreter
        except Exception as exc:
            raise ModelUnavailable("Could not initialize video model") from exc

    def classify(self, encoded_image):
        import numpy as np

        image = decode_frame(encoded_image)

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
                pixels = np.asarray(image.resize((int(w), int(h))))
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

import tempfile
import unittest
from pathlib import Path

import numpy as np

from zta.adapters.litert import LiteRTFrameClassifier
from zta.domain import Label


class _Interpreter:
    def __init__(self, *, model_path):
        self.model_path = model_path
        self.allocated = False
        self.invocations = 0
        self.input_tensor = None

    def allocate_tensors(self):
        self.allocated = True

    def get_input_details(self):
        return [{
            "shape": np.array([1, 2, 2, 3]),
            "dtype": np.uint8,
            "index": 4,
        }]

    def get_output_details(self):
        return [{
            "dtype": np.uint8,
            "index": 7,
            "quantization": (0.005, 0),
        }]

    def set_tensor(self, index, value):
        if index != 4:
            raise AssertionError("unexpected input tensor")
        self.input_tensor = value.copy()

    def invoke(self):
        self.invocations += 1

    def get_tensor(self, index):
        if index != 7:
            raise AssertionError("unexpected output tensor")
        return np.array([[0, 200]], dtype=np.uint8)


class LiteRTFrameClassifierTests(unittest.TestCase):
    def test_litert_interpreter_is_loaded_once_and_runs_quantized_model(self):
        created = []

        def factory(**kwargs):
            interpreter = _Interpreter(**kwargs)
            created.append(interpreter)
            return interpreter

        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "model.tflite"
            model_path.write_bytes(b"test model")
            classifier = LiteRTFrameClassifier(
                model_path, interpreter_factory=factory,
            )
            frame = np.zeros((4, 4, 3), dtype=np.uint8)

            first = classifier.classify(frame)
            second = classifier.classify(frame)

        self.assertEqual(Label.FAKE, first.label)
        self.assertEqual(first.model_id, second.model_id)
        self.assertTrue(first.model_id.startswith("sha256:"))
        self.assertEqual(1, len(created))
        self.assertTrue(created[0].allocated)
        self.assertEqual(2, created[0].invocations)
        self.assertEqual((1, 2, 2, 3), created[0].input_tensor.shape)
        self.assertEqual(np.uint8, created[0].input_tensor.dtype)


if __name__ == "__main__":
    unittest.main()

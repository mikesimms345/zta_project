from io import BytesIO
import unittest
from PIL import Image
from zta.adapters.tflite import TFLiteFrameClassifier
from zta.domain import InvalidFrame, ModelUnavailable


class AdapterTests(unittest.TestCase):
    def test_invalid_image_rejected_before_model_load(self):
        detector = TFLiteFrameClassifier('/nonexistent/model.tflite')
        with self.assertRaises(InvalidFrame):
            detector.classify(b'not an image')
        self.assertIsNone(detector._interpreter)

    def test_wrong_format_rejected(self):
        data = BytesIO()
        Image.new('RGB', (16, 16)).save(data, format='PNG')
        with self.assertRaises(InvalidFrame):
            TFLiteFrameClassifier('/nonexistent/model.tflite').classify(data.getvalue())

    def test_missing_model_is_not_real(self):
        data = BytesIO()
        Image.new('RGB', (16, 16)).save(data, format='JPEG')
        with self.assertRaises(ModelUnavailable):
            TFLiteFrameClassifier('/nonexistent/model.tflite').classify(data.getvalue())

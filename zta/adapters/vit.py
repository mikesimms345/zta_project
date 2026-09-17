"""Local MobileViT adapter; independent of CUDA and the conferencing application."""
from hashlib import sha256
from pathlib import Path
from threading import Lock

from ..domain import Label, ModelUnavailable, Prediction
from .images import decode_frame


class ViTFrameClassifier:
    def __init__(self, model_path):
        self.model_path = Path(model_path)
        self._model = None
        self._processor = None
        self._model_id = ''
        self._lock = Lock()

    def _load(self):
        if self._model is not None:
            return
        try:
            from transformers import MobileViTForImageClassification, MobileViTImageProcessor
            processor = MobileViTImageProcessor.from_pretrained(
                str(self.model_path), local_files_only=True)
            model = MobileViTForImageClassification.from_pretrained(
                str(self.model_path), local_files_only=True, use_safetensors=True)
            model.eval()  # CPU supports this prototype on both Mac and non-CUDA hosts.
            digest = sha256()
            for name in ('config.json', 'preprocessor_config.json', 'model.safetensors'):
                digest.update(name.encode())
                digest.update((self.model_path / name).read_bytes())
            self._model_id = 'mobilevit:sha256:' + digest.hexdigest()
            self._processor, self._model = processor, model
        except Exception as exc:
            raise ModelUnavailable('Could not initialize ViT model') from exc

    def classify(self, encoded_image):
        image = decode_frame(encoded_image)
        with self._lock:
            self._load()
            try:
                import torch
                inputs = self._processor(images=image, return_tensors='pt')
                with torch.inference_mode():
                    logits = self._model(**inputs).logits
                if tuple(logits.shape) != (1, 2) or not torch.isfinite(logits).all():
                    raise ValueError('Unexpected ViT output')
                index = logits.argmax(dim=-1).item()
                label = Label(self._model.config.id2label[index].lower())
                return Prediction(label, self._model_id)
            except Exception as exc:
                raise ModelUnavailable('ViT inference failed') from exc

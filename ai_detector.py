import os
import threading
import numpy as np
from collections import deque
from PIL import Image

basedir = os.path.abspath(os.path.dirname(__file__))

USE_GPU = False
vit_model = None
vit_processor = None
tflite_interpreter = None
_tflite_lock = threading.Lock()  # TFLite interpreter is not thread-safe

audio_tflite_interpreter = None
_audio_tflite_lock = threading.Lock()

WINDOW_SIZE = 75
AUDIO_WINDOW_SIZE = 10  # audio chunks (~1 s each → ~10 s rolling window)
FAKE_THRESHOLD = 0.70


def init_model():
    """Detect GPU and load the appropriate model at startup."""
    global USE_GPU, vit_model, vit_processor, tflite_interpreter

    try:
        import torch
        if torch.cuda.is_available():
            USE_GPU = True
    except ImportError:
        USE_GPU = False

    if USE_GPU:
        _load_vit()
    else:
        _load_tflite()

    _load_audio_tflite()

    print(f"[AI Detector] Initialized — GPU={'yes' if USE_GPU else 'no'}, "
          f"video backend={'MobileViT (safetensors)' if USE_GPU else 'TFLite'}, "
          f"audio backend=TFLite")


def _load_vit():
    global vit_model, vit_processor
    from transformers import MobileViTForImageClassification, MobileViTImageProcessor
    import torch

    model_path = os.path.join(basedir, "models", "MobileViT")
    vit_processor = MobileViTImageProcessor.from_pretrained(model_path)
    vit_model = MobileViTForImageClassification.from_pretrained(model_path)
    vit_model.to("cuda")
    vit_model.eval()


def _load_tflite():
    global tflite_interpreter
    try:
        import tflite_runtime.Interpreter as tflite
        tflite_interpreter = tflite.Interpreter(
            model_path=os.path.join(basedir, "models", "lighter_quant_model.tflite")
        )
    except ImportError:
        import tensorflow as tf
        tflite_interpreter = tf.lite.Interpreter(
            model_path=os.path.join(basedir, "models", "lighter_quant_model.tflite")
        )
    tflite_interpreter.allocate_tensors()


def _load_audio_tflite():
    global audio_tflite_interpreter
    try:
        import tflite_runtime.Interpreter as tflite
        audio_tflite_interpreter = tflite.Interpreter(
            model_path=os.path.join(basedir, "models", "deepfake_voice_detector_v2.tflite")
        )
    except ImportError:
        import tensorflow as tf
        audio_tflite_interpreter = tf.lite.Interpreter(
            model_path=os.path.join(basedir, "models", "deepfake_voice_detector_v2.tflite")
        )
    audio_tflite_interpreter.allocate_tensors()


def classify_frame(image: Image.Image) -> int:
    """Classify a single PIL Image. Returns 0 (REAL) or 1 (FAKE)."""
    if USE_GPU:
        return _classify_vit(image)
    else:
        return _classify_tflite(image)


def classify_audio(pcm_samples: np.ndarray, sample_rate: int) -> int:
    """Classify a PCM float32 audio chunk via mel spectrogram. Returns 0 (REAL) or 1 (FAKE)."""
    import librosa

    mel_spec = librosa.feature.melspectrogram(y=pcm_samples, sr=sample_rate, n_mels=128)
    mel_db = librosa.power_to_db(mel_spec, ref=np.max)  # shape: (128, time_frames)

    input_details = audio_tflite_interpreter.get_input_details()
    output_details = audio_tflite_interpreter.get_output_details()
    input_shape = input_details[0]['shape']
    input_dtype = input_details[0]['dtype']

    print(f"[AI Audio] pcm samples={len(pcm_samples)}, sr={sample_rate}")
    print(f"[AI Audio] mel_db shape={mel_db.shape} min={mel_db.min():.2f} max={mel_db.max():.2f}")
    print(f"[AI Audio] model expects shape={input_shape} dtype={input_dtype}")

    # Determine spatial H×W from model shape — handle [1,H,W,1], [1,1,H,W], [1,H,W]
    if len(input_shape) == 4:
        if input_shape[3] == 1:      # channels-last: [1, H, W, 1]
            h, w = input_shape[1], input_shape[2]
        elif input_shape[1] == 1:    # channels-first: [1, 1, H, W]
            h, w = input_shape[2], input_shape[3]
        else:
            h, w = input_shape[1], input_shape[2]
    else:
        h, w = mel_db.shape

    # Normalize spectrogram to [0, 1] and resize to model's spatial dims
    spec_min, spec_max = mel_db.min(), mel_db.max()
    normalized = (mel_db - spec_min) / (spec_max - spec_min + 1e-8)  # float64 [0,1], shape (n_mels, time)
    spec_resized = np.array(
        Image.fromarray((normalized * 255).astype(np.uint8), mode='L').resize((w, h), Image.BILINEAR),
        dtype=np.float32
    ) / 255.0  # float32 [0,1], shape (h, w)

    # Build the channel dimension.
    # For 3-channel inputs, apply the viridis colormap — this matches how audio deepfake
    # detectors are typically trained (mel spectrograms saved as colormap PNG images).
    # Stacking identical grayscale channels is a different distribution entirely.
    import matplotlib.cm as cm
    if len(input_shape) == 4:
        if input_shape[1] == 1:          # channels-first [1, 1, H, W]
            spec_array = spec_resized[np.newaxis, np.newaxis, :, :]
        elif input_shape[1] == 3:        # channels-first [1, 3, H, W]
            rgb = cm.get_cmap('viridis')(spec_resized)[:, :, :3].astype(np.float32)
            spec_array = rgb.transpose(2, 0, 1)[np.newaxis]
        elif input_shape[3] == 1:        # channels-last [1, H, W, 1]
            spec_array = spec_resized[np.newaxis, :, :, np.newaxis]
        else:                            # channels-last [1, H, W, C] — use colormap for C=3
            c = input_shape[3]
            rgb = cm.get_cmap('viridis')(spec_resized)[:, :, :c].astype(np.float32)
            spec_array = rgb[np.newaxis]
    else:
        spec_array = spec_resized[np.newaxis, :, :]

    # Match the dtype the model expects
    if input_dtype == np.uint8:
        spec_array = (spec_array * 255).astype(np.uint8)
    elif input_dtype == np.int8:
        spec_array = (spec_array * 255 - 128).astype(np.int8)
    else:
        spec_array = spec_array.astype(np.float32)

    print(f"[AI Audio] tensor shape={spec_array.shape} min={spec_array.min():.4f} max={spec_array.max():.4f} dtype={spec_array.dtype}")

    with _audio_tflite_lock:
        audio_tflite_interpreter.set_tensor(input_details[0]['index'], spec_array)
        audio_tflite_interpreter.invoke()
        output = audio_tflite_interpreter.get_tensor(output_details[0]['index']).copy()

    scores = output[0]
    if len(scores) == 1:
        predicted = 1 if scores[0] >= 0.5 else 0
        print(f"[AI] Audio raw output: {scores[0]:.4f} → {'FAKE' if predicted else 'REAL'}")
    else:
        predicted = int(np.argmax(scores))
        print(f"[AI] Audio raw output: {scores} → {'FAKE' if predicted else 'REAL'}")
    return predicted


def _classify_vit(image: Image.Image) -> int:
    import torch

    inputs = vit_processor(images=image, return_tensors="pt")
    inputs = {k: v.to("cuda") for k, v in inputs.items()}
    with torch.no_grad():
        outputs = vit_model(**inputs)
    predicted = outputs.logits.argmax(dim=-1).item()
    return predicted


def _classify_tflite(image: Image.Image) -> int:
    input_details = tflite_interpreter.get_input_details()
    output_details = tflite_interpreter.get_output_details()

    input_shape = input_details[0]['shape']  # e.g. [1, 256, 256, 3] or [1, 3, 256, 256]
    input_dtype = input_details[0]['dtype']

    # Determine spatial dimensions — handle both HWC and CHW layouts
    if input_shape[1] == 3:  # channels-first: [1, 3, H, W]
        h, w = input_shape[2], input_shape[3]
        channels_first = True
    else:                    # channels-last: [1, H, W, 3]
        h, w = input_shape[1], input_shape[2]
        channels_first = False

    img = image.resize((w, h))
    img_array = np.array(img)  # uint8 HWC

    if channels_first:
        img_array = np.transpose(img_array, (2, 0, 1))  # HWC -> CHW

    # Match the dtype the model actually expects
    if input_dtype == np.uint8:
        img_array = img_array.astype(np.uint8)
    elif input_dtype == np.int8:
        # Quantized int8: scale [0,255] -> [-128, 127]
        img_array = (img_array.astype(np.int16) - 128).astype(np.int8)
    else:
        img_array = img_array.astype(np.float32) / 255.0

    img_array = np.expand_dims(img_array, axis=0)

    with _tflite_lock:
        tflite_interpreter.set_tensor(input_details[0]['index'], img_array)
        tflite_interpreter.invoke()
        # .copy() is required — get_tensor() returns a view into interpreter memory
        # that becomes invalid after the next invoke() call
        output = tflite_interpreter.get_tensor(output_details[0]['index']).copy()

    scores = output[0]
    if len(scores) == 1:
        # Single sigmoid output: value is P(FAKE), threshold at 0.5
        predicted = 1 if scores[0] >= 0.5 else 0
        print(f"[AI] TFLite raw output: {scores[0]:.4f} → {'FAKE' if predicted else 'REAL'}  dtype={input_dtype.__name__}")
    else:
        # Multi-class softmax: argmax over [P(REAL), P(FAKE)]
        predicted = int(np.argmax(scores))
        print(f"[AI] TFLite raw output: {scores}  → {'FAKE' if predicted else 'REAL'}  dtype={input_dtype.__name__}")
    return predicted


class RoomDetector:
    """Tracks per-sender classification results for video and audio with rolling windows.

    Disconnect logic is OR-based: if either the video window OR the audio window
    for a given sender crosses FAKE_THRESHOLD, should_disconnect is True.
    """

    _WINDOW_SIZES = {'video': WINDOW_SIZE, 'audio': AUDIO_WINDOW_SIZE}

    def __init__(self):
        # (room, sid, modality) -> deque of ints (0 or 1)
        self._windows = {}

    def add_result(self, room: str, sid: str, label: int, modality: str = 'video') -> dict:
        """Add a classification result for a specific sender and modality.

        Returns dict with:
          - fake_count / total / fake_ratio: stats for this modality's window
          - modality: which modality this result is for
          - should_disconnect: True if either video OR audio window is full and >= FAKE_THRESHOLD
        """
        window_size = self._WINDOW_SIZES.get(modality, WINDOW_SIZE)
        key = (room, sid, modality)
        if key not in self._windows:
            self._windows[key] = deque(maxlen=window_size)

        self._windows[key].append(label)
        window = self._windows[key]

        fake_count = sum(window)
        total = len(window)
        fake_ratio = fake_count / total if total > 0 else 0.0

        this_over_threshold = total >= window_size and fake_ratio >= FAKE_THRESHOLD

        # Check the other modality for OR logic
        other_modality = 'audio' if modality == 'video' else 'video'
        other_key = (room, sid, other_modality)
        other_over_threshold = False
        if other_key in self._windows:
            other_window = self._windows[other_key]
            other_size = self._WINDOW_SIZES.get(other_modality, WINDOW_SIZE)
            other_total = len(other_window)
            if other_total > 0:
                other_ratio = sum(other_window) / other_total
                other_over_threshold = other_total >= other_size and other_ratio >= FAKE_THRESHOLD

        return {
            "fake_count": fake_count,
            "total": total,
            "fake_ratio": round(fake_ratio, 3),
            "modality": modality,
            "should_disconnect": this_over_threshold or other_over_threshold,
        }

    def clear_room(self, room: str):
        keys = [k for k in self._windows if k[0] == room]
        for k in keys:
            del self._windows[k]

    def clear_sender(self, room: str, sid: str):
        keys = [k for k in self._windows if k[0] == room and k[1] == sid]
        for k in keys:
            del self._windows[k]

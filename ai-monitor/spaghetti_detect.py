"""
KlipperOS-AI — Spaghetti Detection Module
==========================================
TFLite modeli ile 3D baski hatasi tespiti.
Spaghetti (basarisiz baski), layer shift, baski tamamlanma tespiti.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("klipperos-ai.detect")

# Varsayilan model dizini
DEFAULT_MODEL_DIR = Path(__file__).parent / "models"
DEFAULT_MODEL_NAME = "spaghetti_detect.tflite"

# Sinif etiketleri
CLASS_LABELS = {
    0: "normal",      # Normal baski
    1: "spaghetti",   # Spaghetti / basarisiz baski
    2: "stringing",   # Stringing / iplenmis
    3: "completed",   # Baski tamamlandi / bos tabla
}

# Tehlike esikleri
THRESHOLDS = {
    "spaghetti": 0.70,   # %70 guven -> duraklat
    "stringing": 0.80,   # %80 guven -> uyar
    "completed": 0.85,   # %85 guven -> tamamlandi bildir
}


class SpaghettiDetector:
    """TFLite tabanli baski hatasi tespit sinifi."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        thresholds: Optional[dict] = None,
    ):
        self.model_path = model_path or str(DEFAULT_MODEL_DIR / DEFAULT_MODEL_NAME)
        self.thresholds = thresholds or THRESHOLDS
        self._interpreter = None
        self._input_details = None
        self._output_details = None
        self._loaded = False

    def load_model(self) -> bool:
        """TFLite modelini yukle."""
        if not os.path.exists(self.model_path):
            logger.warning("Model dosyasi bulunamadi: %s", self.model_path)
            logger.info("Model indirmek icin: kos_update download-models")
            return False

        try:
            import tflite_runtime.interpreter as tflite
            self._interpreter = tflite.Interpreter(model_path=self.model_path)
        except ImportError:
            try:
                import tensorflow as tf
                self._interpreter = tf.lite.Interpreter(model_path=self.model_path)
            except ImportError:
                logger.error("TFLite runtime bulunamadi. Kurun: pip install tflite-runtime")
                return False

        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()
        self._loaded = True

        input_shape = self._input_details[0]["shape"]
        logger.info("Model yuklendi: %s (input: %s)", self.model_path, input_shape)
        return True

    def detect(self, frame: np.ndarray) -> dict:
        """Frame uzerinde baski hatasi tespiti yap.

        Args:
            frame: numpy array (H, W, 3), [0, 1] araliginda normalize edilmis

        Returns:
            {
                "class": "normal|spaghetti|stringing|completed",
                "confidence": float (0-1),
                "action": "none|pause|notify|complete",
                "scores": {class_name: score, ...}
            }
        """
        if not self._loaded:
            return self._no_model_result()

        try:
            # Input boyutunu ayarla
            input_shape = self._input_details[0]["shape"]
            expected_h, expected_w = input_shape[1], input_shape[2]

            if frame.shape[0] != expected_h or frame.shape[1] != expected_w:
                from PIL import Image
                img = Image.fromarray((frame * 255).astype(np.uint8))
                img = img.resize((expected_w, expected_h), Image.BILINEAR)
                frame = np.array(img, dtype=np.float32) / 255.0

            # Batch dimension ekle
            input_data = np.expand_dims(frame, axis=0).astype(np.float32)

            # Inference
            self._interpreter.set_tensor(self._input_details[0]["index"], input_data)
            self._interpreter.invoke()

            output_data = self._interpreter.get_tensor(self._output_details[0]["index"])
            scores = output_data[0]

            # Sonuclari isle
            return self._process_scores(scores)

        except Exception as e:
            logger.error("Tespit hatasi: %s", e)
            return self._error_result(str(e))

    def _process_scores(self, scores: np.ndarray) -> dict:
        """Model ciktisini isle ve aksiyon belirle."""
        # Softmax (eger model zaten softmax uygulamadiysa)
        if np.max(scores) > 1.0 or np.min(scores) < 0.0:
            exp_scores = np.exp(scores - np.max(scores))
            scores = exp_scores / exp_scores.sum()

        class_scores = {}
        for idx, label in CLASS_LABELS.items():
            if idx < len(scores):
                class_scores[label] = float(scores[idx])

        predicted_class_idx = int(np.argmax(scores))
        predicted_class = CLASS_LABELS.get(predicted_class_idx, "unknown")
        confidence = float(scores[predicted_class_idx])

        # Aksiyon belirle
        action = "none"
        if predicted_class == "spaghetti" and confidence >= self.thresholds.get("spaghetti", 0.7):
            action = "pause"
        elif predicted_class == "stringing" and confidence >= self.thresholds.get("stringing", 0.8):
            action = "notify"
        elif predicted_class == "completed" and confidence >= self.thresholds.get("completed", 0.85):
            action = "complete"

        return {
            "class": predicted_class,
            "confidence": confidence,
            "action": action,
            "scores": class_scores,
        }

    def _no_model_result(self) -> dict:
        """Model yuklu degilken dondurulecek sonuc."""
        return {
            "class": "unknown",
            "confidence": 0.0,
            "action": "none",
            "scores": {},
            "error": "Model yuklenmemis",
        }

    def _error_result(self, error_msg: str) -> dict:
        """Hata durumunda dondurulecek sonuc."""
        return {
            "class": "error",
            "confidence": 0.0,
            "action": "none",
            "scores": {},
            "error": error_msg,
        }

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def input_shape(self) -> Optional[tuple]:
        if self._input_details:
            return tuple(self._input_details[0]["shape"])
        return None

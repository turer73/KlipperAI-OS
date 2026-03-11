"""
KlipperOS-AI — Spaghetti Detection Module (v3 — ONNX Runtime)
==============================================================
ONNX Runtime ile 3D baski hatasi tespiti.
5 sinif: normal, spaghetti, no_extrusion, stringing, completed.

v3 degisiklik:
    - TFLite → ONNX Runtime gecisi
    - Tek backend: onnxruntime (tflite/ai-edge-litert/tensorflow fallback yok)
    - .tflite yerine .onnx model dosyasi
    - Geriye uyumlu API: SpaghettiDetector.detect() degismedi

Model donusumu:
    python -m tf2onnx.convert --tflite spaghetti_detect.tflite --output spaghetti_detect.onnx
"""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("klipperos-ai.detect")

# Varsayilan model dizini
DEFAULT_MODEL_DIR = Path(__file__).parent / "models"

# v3: Oncelik ONNX, fallback olarak TFLite de denenir
DEFAULT_MODEL_NAME_ONNX = "spaghetti_detect.onnx"
DEFAULT_MODEL_NAME_TFLITE = "spaghetti_detect.tflite"  # geriye uyumluluk

# Sinif etiketleri
CLASS_LABELS = {
    0: "normal",        # Normal baski
    1: "spaghetti",     # Spaghetti / basarisiz baski
    2: "no_extrusion",  # Akis yok / ekstruzyon durmus
    3: "stringing",     # Stringing / iplenmis
    4: "completed",     # Baski tamamlandi / bos tabla
}

# Tehlike esikleri
THRESHOLDS = {
    "spaghetti": 0.65,     # %65 guven -> duraklat (v4 dusuruldu)
    "no_extrusion": 0.60,  # %60 guven -> duraklat (v4 dusuruldu)
    "stringing": 0.75,     # %75 guven -> uyar (v4 dusuruldu)
    "completed": 0.85,     # %85 guven -> tamamlandi bildir
}

# Anomali tespiti: normal sinif guveni bu esik altindaysa -> anomali
NORMAL_LOW_THRESHOLD = 0.40


# ---------------------------------------------------------------------------
# Backend Protocol
# ---------------------------------------------------------------------------

class _InferenceBackend:
    """Inference backend arayuzu (duck typing)."""
    def load(self, model_path: str) -> bool: ...
    def infer(self, input_data: np.ndarray) -> np.ndarray: ...
    def input_shape(self) -> tuple: ...
    @property
    def name(self) -> str: ...


class ONNXBackend:
    """ONNX Runtime inference backend."""

    def __init__(self):
        self._session = None
        self._input_name: str = ""
        self._input_shape: tuple = ()

    @property
    def name(self) -> str:
        return "onnxruntime"

    def load(self, model_path: str) -> bool:
        try:
            import onnxruntime as ort
            # SBC icin optimize: sadece CPU, thread sayisi kisitli
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 2
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self._session = ort.InferenceSession(
                model_path, sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            inp = self._session.get_inputs()[0]
            self._input_name = inp.name
            self._input_shape = tuple(inp.shape)
            logger.info("ONNX model yuklendi: %s (input: %s, name: %s)",
                        model_path, self._input_shape, self._input_name)
            return True
        except ImportError:
            logger.warning("onnxruntime kurulu degil: pip install onnxruntime")
            return False
        except Exception as exc:
            logger.error("ONNX model yukleme hatasi: %s", exc)
            return False

    def infer(self, input_data: np.ndarray) -> np.ndarray:
        result = self._session.run(None, {self._input_name: input_data})
        return result[0]

    def input_shape(self) -> tuple:
        return self._input_shape


class TFLiteBackend:
    """TFLite fallback backend (geriye uyumluluk)."""

    def __init__(self):
        self._interpreter = None
        self._input_details = None
        self._output_details = None

    @property
    def name(self) -> str:
        return "tflite"

    def load(self, model_path: str) -> bool:
        try:
            try:
                import tflite_runtime.interpreter as tflite
                self._interpreter = tflite.Interpreter(model_path=model_path)
            except ImportError:
                try:
                    from ai_edge_litert.interpreter import Interpreter
                    self._interpreter = Interpreter(model_path=model_path)
                except ImportError:
                    import tensorflow as tf
                    self._interpreter = tf.lite.Interpreter(model_path=model_path)

            self._interpreter.allocate_tensors()
            self._input_details = self._interpreter.get_input_details()
            self._output_details = self._interpreter.get_output_details()
            logger.info("TFLite model yuklendi: %s", model_path)
            return True
        except ImportError:
            logger.warning("TFLite runtime bulunamadi")
            return False
        except Exception as exc:
            logger.error("TFLite model yukleme hatasi: %s", exc)
            return False

    def infer(self, input_data: np.ndarray) -> np.ndarray:
        self._interpreter.set_tensor(
            self._input_details[0]["index"], input_data
        )
        self._interpreter.invoke()
        return self._interpreter.get_tensor(
            self._output_details[0]["index"]
        )

    def input_shape(self) -> tuple:
        if self._input_details:
            return tuple(self._input_details[0]["shape"])
        return ()


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class SpaghettiDetector:
    """Baski hatasi tespit sinifi — ONNX Runtime (v3) + TFLite fallback.

    API v2 ile tamamen geriye uyumlu: detect(), is_loaded, input_shape
    ayni sekilde calisir.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        thresholds: Optional[dict] = None,
    ):
        self.model_path = model_path  # None ise otomatik tespit
        self.thresholds = thresholds or THRESHOLDS
        self._backend: Optional[_InferenceBackend] = None
        self._loaded = False

    def load_model(self) -> bool:
        """Model yukle — once ONNX, sonra TFLite dene.

        Model yolu verilmemisse models/ dizininde once .onnx sonra
        .tflite dosyasini arar.
        """
        if self.model_path:
            # Acik yol verildi
            return self._try_load(self.model_path)

        # Otomatik tespit: once ONNX
        onnx_path = DEFAULT_MODEL_DIR / DEFAULT_MODEL_NAME_ONNX
        if onnx_path.exists():
            if self._try_load(str(onnx_path)):
                return True

        # Fallback: TFLite
        tflite_path = DEFAULT_MODEL_DIR / DEFAULT_MODEL_NAME_TFLITE
        if tflite_path.exists():
            if self._try_load(str(tflite_path)):
                return True

        logger.warning("Model dosyasi bulunamadi: %s veya %s",
                        onnx_path, tflite_path)
        logger.info("Model indirmek icin: kos_update download-models")
        return False

    def _try_load(self, path: str) -> bool:
        """Verilen model dosyasini uygun backend ile yukle."""
        if not os.path.exists(path):
            return False

        if path.endswith(".onnx"):
            backend = ONNXBackend()
            if backend.load(path):
                self._backend = backend
                self._loaded = True
                self.model_path = path
                return True

        if path.endswith(".tflite"):
            backend = TFLiteBackend()
            if backend.load(path):
                self._backend = backend
                self._loaded = True
                self.model_path = path
                return True

        logger.warning("Desteklenmeyen model formati: %s", path)
        return False

    def detect(self, frame: np.ndarray) -> dict:
        """Frame uzerinde baski hatasi tespiti yap.

        Args:
            frame: numpy array (H, W, 3), [0, 1] araliginda normalize edilmis

        Returns:
            {
                "class": "normal|spaghetti|no_extrusion|stringing|completed",
                "confidence": float (0-1),
                "action": "none|pause|notify|complete",
                "scores": {class_name: score, ...},
                "backend": "onnxruntime|tflite"
            }
        """
        if not self._loaded or self._backend is None:
            return self._no_model_result()

        try:
            # Input boyutunu ayarla
            shape = self._backend.input_shape()
            if len(shape) >= 3:
                expected_h, expected_w = shape[1], shape[2]

                if frame.shape[0] != expected_h or frame.shape[1] != expected_w:
                    from PIL import Image
                    img = Image.fromarray((frame * 255).astype(np.uint8))
                    img = img.resize((expected_w, expected_h), Image.BILINEAR)
                    frame = np.array(img, dtype=np.float32) / 255.0

            # Batch dimension ekle
            input_data = np.expand_dims(frame, axis=0).astype(np.float32)

            # Inference
            output_data = self._backend.infer(input_data)
            scores = output_data[0] if output_data.ndim > 1 else output_data

            # Sonuclari isle
            result = self._process_scores(scores)
            result["backend"] = self._backend.name
            return result

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
        elif predicted_class == "no_extrusion" and confidence >= self.thresholds.get("no_extrusion", 0.75):
            action = "pause"
        elif predicted_class == "stringing" and confidence >= self.thresholds.get("stringing", 0.8):
            action = "notify"
        elif predicted_class == "completed" and confidence >= self.thresholds.get("completed", 0.85):
            action = "complete"


        # v4: Anomali tespiti - normal skoru cok dusukse
        # Hicbir sinif kendi esigini gecmese bile, bilinmeyen anomali olarak isle
        if action == "none" and class_scores.get("normal", 1.0) < NORMAL_LOW_THRESHOLD:
            anomaly_classes = {k: v for k, v in class_scores.items() if k != "normal"}
            if anomaly_classes:
                top_anomaly = max(anomaly_classes, key=anomaly_classes.get)
                top_score = anomaly_classes[top_anomaly]
                if top_score > 0.30:
                    action = "pause"
                    predicted_class = top_anomaly
                    confidence = top_score
                    logger.warning(
                        "ANOMALI tespit: normal=%.1f%% < %d%%, en yuksek: %s=%.1f%%",
                        class_scores.get("normal", 0) * 100,
                        int(NORMAL_LOW_THRESHOLD * 100),
                        top_anomaly,
                        top_score * 100,
                    )

        return {
            "class": predicted_class,
            "confidence": confidence,
            "action": action,
            "scores": class_scores,
        }

    def _no_model_result(self) -> dict:
        return {
            "class": "unknown",
            "confidence": 0.0,
            "action": "none",
            "scores": {},
            "error": "Model yuklenmemis",
        }

    def _error_result(self, error_msg: str) -> dict:
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
    def backend_name(self) -> str:
        """Aktif backend adi."""
        if self._backend:
            return self._backend.name
        return "none"

    @property
    def input_shape(self) -> Optional[tuple]:
        if self._backend:
            return self._backend.input_shape()
        return None

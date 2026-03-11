"""Tests for SpaghettiDetector v3 (ONNX Runtime + TFLite fallback)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from spaghetti_detect import (
    SpaghettiDetector, CLASS_LABELS, THRESHOLDS,
    ONNXBackend, TFLiteBackend,
)


class TestClassLabels:
    """Sinif etiketleri testleri."""

    def test_label_count(self):
        assert len(CLASS_LABELS) == 5

    def test_expected_labels(self):
        expected = {"normal", "spaghetti", "no_extrusion", "stringing", "completed"}
        assert set(CLASS_LABELS.values()) == expected


class TestThresholds:
    """Esik degerleri testleri."""

    def test_thresholds_exist(self):
        assert "spaghetti" in THRESHOLDS
        assert "no_extrusion" in THRESHOLDS

    def test_thresholds_in_range(self):
        for key, val in THRESHOLDS.items():
            assert 0.0 < val <= 1.0, f"{key} esigi aralik disinda: {val}"


class TestSpaghettiDetector:
    """SpaghettiDetector unit testleri."""

    def test_init_defaults(self):
        det = SpaghettiDetector()
        assert det.is_loaded is False
        assert det.backend_name == "none"
        assert det.input_shape is None

    def test_detect_without_model(self):
        det = SpaghettiDetector()
        frame = np.zeros((224, 224, 3), dtype=np.float32)
        result = det.detect(frame)
        assert result["class"] == "unknown"
        assert result["action"] == "none"
        assert "error" in result

    def test_load_nonexistent_model(self):
        det = SpaghettiDetector(model_path="/tmp/nonexistent-model.onnx")
        assert det.load_model() is False

    def test_process_scores_normal(self):
        det = SpaghettiDetector()
        # Normal sinif en yuksek
        scores = np.array([0.85, 0.05, 0.03, 0.05, 0.02])
        result = det._process_scores(scores)
        assert result["class"] == "normal"
        assert result["action"] == "none"
        assert result["confidence"] == pytest.approx(0.85, abs=0.01)

    def test_process_scores_spaghetti_pause(self):
        det = SpaghettiDetector()
        scores = np.array([0.1, 0.75, 0.05, 0.05, 0.05])
        result = det._process_scores(scores)
        assert result["class"] == "spaghetti"
        assert result["action"] == "pause"

    def test_process_scores_spaghetti_below_threshold(self):
        det = SpaghettiDetector()
        scores = np.array([0.35, 0.60, 0.02, 0.02, 0.01])
        result = det._process_scores(scores)
        assert result["class"] == "spaghetti"
        assert result["action"] == "none"  # 0.60 < 0.70 threshold

    def test_process_scores_no_extrusion(self):
        det = SpaghettiDetector()
        scores = np.array([0.05, 0.05, 0.80, 0.05, 0.05])
        result = det._process_scores(scores)
        assert result["class"] == "no_extrusion"
        assert result["action"] == "pause"

    def test_process_scores_stringing_notify(self):
        det = SpaghettiDetector()
        scores = np.array([0.05, 0.05, 0.05, 0.82, 0.03])
        result = det._process_scores(scores)
        assert result["class"] == "stringing"
        assert result["action"] == "notify"

    def test_process_scores_completed(self):
        det = SpaghettiDetector()
        scores = np.array([0.02, 0.03, 0.02, 0.03, 0.90])
        result = det._process_scores(scores)
        assert result["class"] == "completed"
        assert result["action"] == "complete"

    def test_process_scores_softmax_applied(self):
        """Softmax uygulanmamis logit'ler icin otomatik softmax."""
        det = SpaghettiDetector()
        # Logit (normalize edilmemis) degerler
        logits = np.array([5.0, 1.0, 0.5, 0.3, 0.1])
        result = det._process_scores(logits)
        # Softmax sonrasi sinif 0 (normal) en yuksek olmali
        assert result["class"] == "normal"
        assert 0 < result["confidence"] <= 1.0

    def test_process_scores_dict_has_all_classes(self):
        det = SpaghettiDetector()
        scores = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
        result = det._process_scores(scores)
        assert set(result["scores"].keys()) == set(CLASS_LABELS.values())

    def test_custom_thresholds(self):
        custom = {"spaghetti": 0.5}
        det = SpaghettiDetector(thresholds=custom)
        scores = np.array([0.1, 0.55, 0.1, 0.15, 0.1])
        result = det._process_scores(scores)
        assert result["action"] == "pause"  # 0.55 >= 0.5


class TestONNXBackend:
    """ONNXBackend unit testleri."""

    def test_name(self):
        b = ONNXBackend()
        assert b.name == "onnxruntime"

    def test_load_nonexistent(self):
        b = ONNXBackend()
        assert b.load("/tmp/nonexistent.onnx") is False


class TestTFLiteBackend:
    """TFLiteBackend unit testleri."""

    def test_name(self):
        b = TFLiteBackend()
        assert b.name == "tflite"

    def test_empty_input_shape(self):
        b = TFLiteBackend()
        assert b.input_shape() == ()

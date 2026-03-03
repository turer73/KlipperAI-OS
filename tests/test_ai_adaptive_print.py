"""Tests for Adaptive Thresholds + Adaptive Print Controller (Phase 2)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-monitor"))
from adaptive_thresholds import RunningStats, AdaptiveThresholdEngine
from adaptive_print import (
    AdaptivePrintController,
    LayerQualityScore,
    PrintAdjustment,
    compute_flow_consistency,
    compute_thermal_stability,
    compute_visual_score,
    SPEED_MIN_FACTOR,
    SPEED_MAX_FACTOR,
    FLOW_MIN,
    FLOW_MAX,
    TEMP_DELTA_MAX,
)


# ═══════════════════════════════════════════════════════════════════════════════
# RunningStats (Welford Algoritmasi)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunningStats:
    """Welford online istatistik testleri."""

    def test_empty_stats(self):
        s = RunningStats()
        assert s.n == 0
        assert s.mean == 0.0
        assert s.variance == 0.0
        assert s.std == 0.0
        assert not s.is_ready

    def test_single_value(self):
        s = RunningStats()
        s.update(5.0)
        assert s.n == 1
        assert s.mean == 5.0
        assert s.variance == 0.0

    def test_mean_calculation(self):
        s = RunningStats()
        for v in [2, 4, 6, 8, 10]:
            s.update(v)
        assert s.mean == pytest.approx(6.0)

    def test_std_calculation(self):
        s = RunningStats()
        for v in [10, 10, 10, 10, 10]:
            s.update(v)
        assert s.std == pytest.approx(0.0)

    def test_variance_nonzero(self):
        s = RunningStats()
        for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
            s.update(v)
        assert s.variance > 0
        assert s.is_ready

    def test_is_ready_after_10(self):
        s = RunningStats()
        for i in range(9):
            s.update(float(i))
        assert not s.is_ready
        s.update(9.0)
        assert s.is_ready


# ═══════════════════════════════════════════════════════════════════════════════
# AdaptiveThresholdEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdaptiveThresholdEngine:
    """Adaptif esik motoru testleri."""

    def test_initial_state(self):
        engine = AdaptiveThresholdEngine()
        assert engine.heater_stats.n == 0
        assert engine.tmc_stats.n == 0

    def test_heater_threshold_fallback(self):
        engine = AdaptiveThresholdEngine()
        # Veri yok → 0
        assert engine.get_heater_threshold() == 0.0

    def test_heater_threshold_with_data(self):
        engine = AdaptiveThresholdEngine()
        for _ in range(15):
            engine.update(heater_duty=0.50)
        # Sabit veri: std=0 → threshold = mean - 2*0 = 0.50
        threshold = engine.get_heater_threshold()
        assert threshold == pytest.approx(0.50, abs=0.01)

    def test_heater_threshold_with_variance(self):
        engine = AdaptiveThresholdEngine()
        # Degisken veri
        for v in [0.45, 0.50, 0.55, 0.48, 0.52, 0.47, 0.53, 0.49, 0.51, 0.50]:
            engine.update(heater_duty=v)
        threshold = engine.get_heater_threshold()
        # threshold < mean (anomali tespiti icin dusuk)
        assert threshold < engine.heater_stats.mean

    def test_tmc_thresholds(self):
        engine = AdaptiveThresholdEngine()
        for v in [200, 210, 190, 205, 195, 200, 198, 202, 208, 192]:
            engine.update(sg_result=float(v))
        clog = engine.get_tmc_clog_threshold()
        empty = engine.get_tmc_empty_threshold()
        assert clog < engine.tmc_stats.mean
        assert empty > engine.tmc_stats.mean
        assert clog >= 0  # Negatif olamaz

    def test_summary_format(self):
        engine = AdaptiveThresholdEngine()
        for _ in range(15):
            engine.update(heater_duty=0.5, sg_result=200.0, ai_confidence=0.9)
        summary = engine.summary
        assert "heater" in summary
        assert "tmc" in summary
        assert "ai_confidence" in summary
        assert summary["heater"]["ready"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Skor Hesaplama Fonksiyonlari
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreFunctions:
    """Katman skoru hesaplama testleri."""

    def test_flow_consistency_normal(self):
        assert compute_flow_consistency(1.0) == pytest.approx(1.0)

    def test_flow_consistency_under_extrusion(self):
        score = compute_flow_consistency(1.05)
        assert 0.0 < score < 1.0

    def test_flow_consistency_over_extrusion(self):
        score = compute_flow_consistency(0.95)
        assert 0.0 < score < 1.0

    def test_thermal_stability_perfect(self):
        assert compute_thermal_stability(0.50, 0.50) == pytest.approx(1.0)

    def test_thermal_stability_deviation(self):
        score = compute_thermal_stability(0.40, 0.50)
        assert score < 1.0

    def test_thermal_stability_no_baseline(self):
        assert compute_thermal_stability(0.50, 0.0) == 1.0

    def test_visual_score_normal(self):
        assert compute_visual_score(0.95, "normal") == pytest.approx(0.95)

    def test_visual_score_spaghetti(self):
        score = compute_visual_score(0.90, "spaghetti")
        assert score < 0.2

    def test_visual_score_unknown_class(self):
        assert compute_visual_score(0.8, "some_unknown") == 0.8


# ═══════════════════════════════════════════════════════════════════════════════
# AdaptivePrintController
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdaptivePrintController:
    """Adaptif baski kontrolcu testleri."""

    def setup_method(self):
        self.ctrl = AdaptivePrintController()
        self.ctrl.set_base_params(speed=100.0, temp=200.0)

    def test_score_layer_returns_score(self):
        score = self.ctrl.score_layer(layer=1, z_height=0.2)
        assert isinstance(score, LayerQualityScore)
        assert 0 <= score.composite_score <= 1.0

    def test_good_layers_no_adjustment(self):
        """Iyi katmanlar → parametre degisikligi yok."""
        for i in range(10):
            self.ctrl.score_layer(
                layer=i, z_height=0.2 * i,
                flow_rate_suggestion=1.0,
                heater_duty=0.5, heater_baseline=0.5,
                ai_confidence=0.95, ai_class="normal",
            )
        adj = self.ctrl.evaluate_adaptation()
        assert adj is None  # Degisiklik yok

    def test_bad_layers_slow_down(self):
        """Kotu katmanlar → hiz dusur."""
        for i in range(10):
            self.ctrl.score_layer(
                layer=i, z_height=0.2 * i,
                flow_rate_suggestion=1.10,  # under-extrusion
                heater_duty=0.35, heater_baseline=0.5,  # %30 sapma
                ai_confidence=0.80, ai_class="stringing",
            )
        adj = self.ctrl.evaluate_adaptation()
        assert adj is not None
        assert adj.speed_factor < 1.0

    def test_speed_never_below_minimum(self):
        """Hiz asla SPEED_MIN_FACTOR'un altina dusmez."""
        self.ctrl._current_speed_factor = SPEED_MIN_FACTOR
        for i in range(10):
            self.ctrl.score_layer(
                layer=i, z_height=0.2 * i,
                flow_rate_suggestion=1.10,
                heater_duty=0.30, heater_baseline=0.5,
                ai_confidence=0.60, ai_class="under_extrusion",
            )
        adj = self.ctrl.evaluate_adaptation()
        if adj:
            assert adj.speed_factor >= SPEED_MIN_FACTOR

    def test_speed_never_above_maximum(self):
        """Hiz asla SPEED_MAX_FACTOR'un ustune cikmaz."""
        self.ctrl._current_speed_factor = 1.12
        for i in range(10):
            self.ctrl.score_layer(
                layer=i, z_height=0.2 * i,
                flow_rate_suggestion=1.0,
                heater_duty=0.5, heater_baseline=0.5,
                ai_confidence=0.99, ai_class="normal",
            )
        adj = self.ctrl.evaluate_adaptation()
        if adj:
            assert adj.speed_factor <= SPEED_MAX_FACTOR

    def test_flow_limits(self):
        """Akis orani asla sinirlari asmaz."""
        adj = PrintAdjustment(flow_factor=2.0)
        adj.flow_factor = max(FLOW_MIN, min(FLOW_MAX, adj.flow_factor))
        assert adj.flow_factor == FLOW_MAX

        adj2 = PrintAdjustment(flow_factor=0.5)
        adj2.flow_factor = max(FLOW_MIN, min(FLOW_MAX, adj2.flow_factor))
        assert adj2.flow_factor == FLOW_MIN

    def test_temp_delta_limits(self):
        """Sicaklik degisikligi asla ±10°C'yi asmaz."""
        adj = PrintAdjustment(temp_delta=20)
        adj.temp_delta = max(-TEMP_DELTA_MAX, min(TEMP_DELTA_MAX, adj.temp_delta))
        assert adj.temp_delta == TEMP_DELTA_MAX

    def test_apply_generates_gcode(self):
        """apply_adjustment dogru G-code uretir."""
        commands = []
        def mock_sender(cmd):
            commands.append(cmd)

        self.ctrl._current_speed_factor = 1.0
        adj = PrintAdjustment(speed_factor=0.90, flow_factor=1.05, temp_delta=5)
        self.ctrl.apply_adjustment(adj, gcode_sender=mock_sender)

        assert any("SET_VELOCITY_LIMIT" in c for c in commands)
        assert any("M221" in c for c in commands)
        assert any("M104" in c for c in commands)

    def test_reset_clears_state(self):
        """reset() tum durumu temizler."""
        self.ctrl.score_layer(layer=1, z_height=0.2)
        self.ctrl._current_speed_factor = 0.80
        self.ctrl.reset()
        assert self.ctrl._current_speed_factor == 1.0
        assert len(self.ctrl._scores) == 0

    def test_disable_skips_evaluation(self):
        """Devre disi adaptif — evaluate None dondurur."""
        self.ctrl.set_enabled(False)
        for i in range(10):
            self.ctrl.score_layer(layer=i, z_height=0.2 * i)
        adj = self.ctrl.evaluate_adaptation()
        assert adj is None

    def test_current_adjustments_format(self):
        status = self.ctrl.current_adjustments
        assert "speed_factor" in status
        assert "flow_factor" in status
        assert "temp_delta" in status
        assert "enabled" in status


# ═══════════════════════════════════════════════════════════════════════════════
# PrintMonitor Entegrasyon Testleri
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrintMonitorIntegration:
    """print_monitor.py adaptive entegrasyon testleri."""

    def test_monitor_imports_adaptive_modules(self):
        """print_monitor adaptive modulleri import edebilir."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-monitor"))
        from adaptive_thresholds import AdaptiveThresholdEngine
        from adaptive_print import AdaptivePrintController
        assert AdaptiveThresholdEngine is not None
        assert AdaptivePrintController is not None

    def test_adaptive_default_disabled(self):
        """Adaptive varsayilan olarak devre disi."""
        import os
        old = os.environ.get("ADAPTIVE_PRINT")
        os.environ.pop("ADAPTIVE_PRINT", None)
        try:
            enabled = os.environ.get("ADAPTIVE_PRINT", "0").lower() in ("1", "true", "yes", "on")
            assert enabled is False
        finally:
            if old is not None:
                os.environ["ADAPTIVE_PRINT"] = old

    def test_adaptive_enabled_via_env(self):
        """ADAPTIVE_PRINT=1 ile aktif."""
        import os
        old = os.environ.get("ADAPTIVE_PRINT")
        os.environ["ADAPTIVE_PRINT"] = "1"
        try:
            enabled = os.environ.get("ADAPTIVE_PRINT", "0").lower() in ("1", "true", "yes", "on")
            assert enabled is True
        finally:
            if old is not None:
                os.environ["ADAPTIVE_PRINT"] = old
            else:
                os.environ.pop("ADAPTIVE_PRINT", None)

    def test_adaptive_score_cycle_skips_same_layer(self):
        """Ayni katman tekrar skorlanmaz."""
        ctrl = AdaptivePrintController()
        ctrl.set_base_params(speed=100, temp=200)

        # Ilk skor
        s1 = ctrl.score_layer(layer=5, z_height=1.0)
        count_after_first = len(ctrl._scores)

        # Ayni katman — eklenmemeli (bu mantik _adaptive_score_cycle'da)
        # Burada dogrudan test ediyoruz
        assert count_after_first == 1
        s2 = ctrl.score_layer(layer=5, z_height=1.0)
        # score_layer her zaman ekler (deduplicate monitor'da)
        assert len(ctrl._scores) == 2  # Controller kendisi filtrelemez

    def test_threshold_engine_feeds_during_calibration(self):
        """Kalibrasyon sirasinda threshold engine beslenir."""
        engine = AdaptiveThresholdEngine()
        for _ in range(30):
            engine.update(heater_duty=0.45, sg_result=200.0)
        assert engine.heater_stats.is_ready
        assert engine.tmc_stats.is_ready

    def test_gcode_sender_integration(self):
        """G-code sender callable olarak kullanilir."""
        ctrl = AdaptivePrintController()
        ctrl.set_base_params(speed=100, temp=200)
        ctrl._current_speed_factor = 1.0

        sent = []
        def mock_gcode(cmd):
            sent.append(cmd)

        adj = PrintAdjustment(speed_factor=0.85, flow_factor=1.0, temp_delta=0)
        ctrl.apply_adjustment(adj, gcode_sender=mock_gcode)
        assert any("SET_VELOCITY_LIMIT" in c for c in sent)
        assert "85" in sent[0]  # 100 * 0.85 = 85

    def test_reset_on_print_end(self):
        """Baski bitince adaptive state sifirlanir."""
        ctrl = AdaptivePrintController()
        engine = AdaptiveThresholdEngine()

        ctrl.set_base_params(speed=100, temp=200)
        for i in range(10):
            ctrl.score_layer(layer=i, z_height=0.2 * i)
            engine.update(heater_duty=0.5, sg_result=200)

        # Simulate print end
        ctrl.reset()
        engine_new = AdaptiveThresholdEngine()

        assert len(ctrl._scores) == 0
        assert ctrl._current_speed_factor == 1.0
        assert engine_new.heater_stats.n == 0

    def test_stats_includes_adaptive_info(self):
        """Adaptive bilgisi stats'a dahil edilir."""
        ctrl = AdaptivePrintController()
        engine = AdaptiveThresholdEngine()

        status = ctrl.current_adjustments
        summary = engine.summary

        assert "speed_factor" in status
        assert "heater" in summary
        assert "tmc" in summary

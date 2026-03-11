"""Tests for TrendAnalyzer (FlowGuard Layer 5)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
from unittest.mock import patch
from trend_analyzer import (
    TrendAnalyzer, TrendResult, TrendDirection,
    TrendSeverity, _MetricBuffer,
)


class TestLinearRegression:
    """_linear_regression statik metodu testleri."""

    def test_flat_line_zero_slope(self):
        times = [0, 60, 120, 180, 240]
        values = [210.0, 210.0, 210.0, 210.0, 210.0]
        slope, r_sq = TrendAnalyzer._linear_regression(times, values)
        assert abs(slope) < 0.001

    def test_rising_trend(self):
        # 1 C/dakika yukselis
        times = [0, 60, 120, 180, 240]
        values = [200.0, 201.0, 202.0, 203.0, 204.0]
        slope, r_sq = TrendAnalyzer._linear_regression(times, values)
        assert slope == pytest.approx(1.0, abs=0.01)
        assert r_sq == pytest.approx(1.0, abs=0.01)

    def test_falling_trend(self):
        # -0.5 C/dakika dusus
        times = [0, 60, 120, 180, 240]
        values = [210.0, 209.5, 209.0, 208.5, 208.0]
        slope, r_sq = TrendAnalyzer._linear_regression(times, values)
        assert slope == pytest.approx(-0.5, abs=0.01)
        assert r_sq == pytest.approx(1.0, abs=0.01)

    def test_noisy_data_low_r_squared(self):
        times = [0, 60, 120, 180, 240]
        values = [210.0, 208.0, 212.0, 207.0, 211.0]
        slope, r_sq = TrendAnalyzer._linear_regression(times, values)
        assert r_sq < 0.3  # zayif korelasyon

    def test_single_point_returns_zero(self):
        slope, r_sq = TrendAnalyzer._linear_regression([0], [210.0])
        assert slope == 0.0
        assert r_sq == 0.0

    def test_empty_returns_zero(self):
        slope, r_sq = TrendAnalyzer._linear_regression([], [])
        assert slope == 0.0


class TestTrendAnalyzer:
    """TrendAnalyzer entegrasyon testleri."""

    def _make_analyzer(self, **kwargs):
        defaults = {"window_minutes": 30, "sample_interval": 0, "min_samples": 5}
        defaults.update(kwargs)
        return TrendAnalyzer(**defaults)

    def _feed_linear(self, analyzer, metric, start_val, slope_per_sample, count):
        """Lineer veri seti besle (monotonic time mock ile)."""
        base_time = 1000.0
        for i in range(count):
            with patch('trend_analyzer.monotonic', return_value=base_time + i * 10):
                analyzer.add_sample(metric, start_val + slope_per_sample * i)

    def test_insufficient_data_returns_normal(self):
        analyzer = self._make_analyzer(min_samples=10)
        with patch('trend_analyzer.monotonic', return_value=1000.0):
            analyzer.add_sample("extruder_temp", 210.0)
        result = analyzer.analyze_metric("extruder_temp")
        assert result.severity == TrendSeverity.NORMAL
        assert "Yetersiz" in result.message

    def test_stable_temperature_is_normal(self):
        analyzer = self._make_analyzer()
        base = 1000.0
        for i in range(20):
            with patch('trend_analyzer.monotonic', return_value=base + i * 10):
                analyzer.add_sample("extruder_temp", 210.0 + (i % 2) * 0.1)
        result = analyzer.analyze_metric("extruder_temp")
        assert result.severity == TrendSeverity.NORMAL
        assert result.direction == TrendDirection.STABLE

    def test_fast_falling_temp_is_anomaly(self):
        analyzer = self._make_analyzer()
        base = 1000.0
        # -1 C/dakika dusus (6 sample = 1dk'da 1C dusus)
        for i in range(20):
            temp = 210.0 - (i * 10 / 60.0) * 1.0  # 1 C/dk dusus
            with patch('trend_analyzer.monotonic', return_value=base + i * 10):
                analyzer.add_sample("extruder_temp", temp)
        result = analyzer.analyze_metric("extruder_temp")
        assert result.severity == TrendSeverity.ANOMALY
        assert result.direction == TrendDirection.FALLING

    def test_slow_falling_temp_is_watch(self):
        analyzer = self._make_analyzer()
        base = 1000.0
        # -0.4 C/dakika dusus (watch esigi: -0.3)
        for i in range(20):
            temp = 210.0 - (i * 10 / 60.0) * 0.4
            with patch('trend_analyzer.monotonic', return_value=base + i * 10):
                analyzer.add_sample("extruder_temp", temp)
        result = analyzer.analyze_metric("extruder_temp")
        assert result.severity == TrendSeverity.WATCH

    def test_mcu_rising_temp_anomaly(self):
        analyzer = self._make_analyzer()
        base = 1000.0
        # +1.5 C/dakika MCU isinma (anomaly esigi: 1.0)
        for i in range(20):
            temp = 45.0 + (i * 10 / 60.0) * 1.5
            with patch('trend_analyzer.monotonic', return_value=base + i * 10):
                analyzer.add_sample("mcu_temp", temp)
        result = analyzer.analyze_metric("mcu_temp")
        assert result.severity == TrendSeverity.ANOMALY
        assert result.direction == TrendDirection.RISING

    def test_has_anomaly_returns_true(self):
        analyzer = self._make_analyzer()
        base = 1000.0
        for i in range(20):
            temp = 210.0 - (i * 10 / 60.0) * 1.0
            with patch('trend_analyzer.monotonic', return_value=base + i * 10):
                analyzer.add_sample("extruder_temp", temp)
        assert analyzer.has_anomaly() is True

    def test_has_anomaly_returns_false_when_stable(self):
        analyzer = self._make_analyzer()
        base = 1000.0
        for i in range(20):
            with patch('trend_analyzer.monotonic', return_value=base + i * 10):
                analyzer.add_sample("extruder_temp", 210.0)
        assert analyzer.has_anomaly() is False

    def test_check_trends_returns_all_metrics(self):
        analyzer = self._make_analyzer()
        base = 1000.0
        for i in range(20):
            with patch('trend_analyzer.monotonic', return_value=base + i * 10):
                analyzer.add_sample("extruder_temp", 210.0)
                analyzer.add_sample("bed_temp", 60.0)
        results = analyzer.check_trends()
        assert "extruder_temp" in results
        assert "bed_temp" in results

    def test_reset_clears_all(self):
        analyzer = self._make_analyzer()
        with patch('trend_analyzer.monotonic', return_value=1000.0):
            analyzer.add_sample("extruder_temp", 210.0)
        analyzer.reset()
        assert len(analyzer._buffers) == 0

    def test_rate_limiting_skips_fast_samples(self):
        analyzer = TrendAnalyzer(sample_interval=10, min_samples=5)
        # Ayni zamanda 5 sample — rate limiting dolayisiyla sadece 1 alinmali
        with patch('trend_analyzer.monotonic', return_value=1000.0):
            for _ in range(5):
                analyzer.add_sample("extruder_temp", 210.0)
        buf = analyzer._buffers.get("extruder_temp")
        assert buf is not None
        assert len(buf.times) == 1


class TestFlowGuardV2Integration:
    """FlowGuard v2 + TrendAnalyzer entegrasyon testi."""

    def test_trend_signal_in_evaluate(self):
        from flow_guard import FlowGuard, FlowSignal, FlowVerdict
        guard = FlowGuard()
        # 4 sinyal verilince trend otomatik eklenir (OK olarak)
        verdict = guard.evaluate([
            FlowSignal.OK, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.OK

    def test_5_signals_accepted(self):
        from flow_guard import FlowGuard, FlowSignal, FlowVerdict
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.OK, FlowSignal.OK, FlowSignal.OK,
            FlowSignal.OK, FlowSignal.ANOMALY
        ])
        # 1/5 anomaly → NOTICE
        assert verdict == FlowVerdict.NOTICE

    def test_trend_summary_property(self):
        from flow_guard import FlowGuard
        guard = FlowGuard()
        summary = guard.trend_summary
        assert isinstance(summary, dict)

    def test_feed_trend_data(self):
        from flow_guard import FlowGuard
        guard = FlowGuard()
        guard.feed_trend(extruder_temp=210, bed_temp=60, heater_duty=0.4)
        # Veri eklendikten sonra trend buffer'inda olmali
        assert "extruder_temp" in guard.trend._buffers

    def test_reset_clears_trend(self):
        from flow_guard import FlowGuard
        guard = FlowGuard()
        guard.feed_trend(extruder_temp=210)
        guard.reset()
        assert len(guard.trend._buffers) == 0

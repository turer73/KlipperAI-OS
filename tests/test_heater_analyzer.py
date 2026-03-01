"""Tests for HeaterDutyAnalyzer."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
from heater_analyzer import HeaterDutyAnalyzer, FlowState


class TestHeaterDutyAnalyzer:
    def test_baseline_calibration(self):
        analyzer = HeaterDutyAnalyzer(window_size=10, calibration_count=10)
        for _ in range(10):
            analyzer.add_sample(0.70)
        analyzer.calibrate()
        assert abs(analyzer.baseline - 0.70) < 0.01

    def test_normal_flow_detected(self):
        analyzer = HeaterDutyAnalyzer(window_size=10, calibration_count=10)
        analyzer.baseline = 0.70
        for _ in range(10):
            analyzer.add_sample(0.68)
        state = analyzer.check_flow()
        assert state == FlowState.OK

    def test_clog_detected_duty_drop(self):
        analyzer = HeaterDutyAnalyzer(window_size=10, calibration_count=10)
        analyzer.baseline = 0.70
        # Duty drops >15% (clog — less heat absorption)
        for _ in range(10):
            analyzer.add_sample(0.50)
        state = analyzer.check_flow()
        assert state == FlowState.ANOMALY

    def test_insufficient_samples_returns_ok(self):
        analyzer = HeaterDutyAnalyzer(window_size=10, calibration_count=10)
        analyzer.baseline = 0.70
        analyzer.add_sample(0.30)
        state = analyzer.check_flow()
        assert state == FlowState.OK  # Not enough data

    def test_reset_clears_state(self):
        analyzer = HeaterDutyAnalyzer(window_size=10, calibration_count=10)
        analyzer.baseline = 0.70
        for _ in range(10):
            analyzer.add_sample(0.50)
        analyzer.reset()
        assert analyzer.baseline is None
        assert len(analyzer._window) == 0

    def test_confidence_is_fixed(self):
        analyzer = HeaterDutyAnalyzer()
        assert analyzer.confidence == 0.70

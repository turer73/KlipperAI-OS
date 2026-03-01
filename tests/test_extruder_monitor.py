"""Tests for ExtruderLoadMonitor."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
from extruder_monitor import ExtruderLoadMonitor
from heater_analyzer import FlowState


class TestExtruderLoadMonitor:
    def test_normal_sg_result(self):
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(90)
        state = monitor.check_flow()
        assert state == FlowState.OK

    def test_clog_high_load(self):
        """Very low SG_RESULT = high motor load = clog."""
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(20)
        state = monitor.check_flow()
        assert state == FlowState.ANOMALY

    def test_no_filament_low_load(self):
        """Very high SG_RESULT = no motor load = filament gone."""
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(200)
        state = monitor.check_flow()
        assert state == FlowState.ANOMALY

    def test_suggest_flow_rate_normal(self):
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(85)
        suggestion = monitor.suggest_flow_rate()
        assert suggestion == 1.0

    def test_suggest_flow_rate_under_extrusion(self):
        """Low load (high SG) = under-extrusion, suggest increase."""
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(120)
        suggestion = monitor.suggest_flow_rate()
        assert suggestion == 1.05

    def test_suggest_flow_rate_over_extrusion(self):
        """High load (low SG) = over-extrusion, suggest decrease."""
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(60)
        suggestion = monitor.suggest_flow_rate()
        assert suggestion == 0.95

    def test_insufficient_samples_returns_ok(self):
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        monitor.add_sample(20)
        state = monitor.check_flow()
        assert state == FlowState.OK

    def test_no_baseline_returns_ok(self):
        monitor = ExtruderLoadMonitor(window_size=10)
        for _ in range(10):
            monitor.add_sample(50)
        state = monitor.check_flow()
        assert state == FlowState.OK

    def test_confidence_is_fixed(self):
        monitor = ExtruderLoadMonitor()
        assert monitor.confidence == 0.85

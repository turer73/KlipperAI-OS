"""Tests for FlowGuard Voting Engine."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
from flow_guard import FlowGuard, FlowVerdict, FlowSignal


class TestFlowGuardVoting:
    def test_all_ok_returns_ok(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.OK, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.OK

    def test_one_anomaly_returns_notice(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.NOTICE

    def test_two_anomaly_returns_warning(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.ANOMALY, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.WARNING

    def test_three_anomaly_returns_critical(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.ANOMALY, FlowSignal.ANOMALY, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.CRITICAL

    def test_four_anomaly_returns_critical(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.ANOMALY,
            FlowSignal.ANOMALY, FlowSignal.ANOMALY
        ])
        assert verdict == FlowVerdict.CRITICAL

    def test_warning_escalation_after_3_cycles(self):
        guard = FlowGuard()
        signals_2of4 = [
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.ANOMALY, FlowSignal.OK
        ]
        # First 2 cycles: WARNING
        for _ in range(2):
            v = guard.evaluate(signals_2of4)
            assert v == FlowVerdict.WARNING
        # 3rd cycle: escalates to CRITICAL
        v = guard.evaluate(signals_2of4)
        assert v == FlowVerdict.CRITICAL

    def test_warning_resets_on_ok(self):
        guard = FlowGuard()
        guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.ANOMALY, FlowSignal.OK
        ])
        # Then all OK — resets warning counter
        guard.evaluate([
            FlowSignal.OK, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK
        ])
        # Back to WARNING, not escalated
        v = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.ANOMALY, FlowSignal.OK
        ])
        assert v == FlowVerdict.WARNING

    def test_unavailable_signals_treated_as_ok(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.UNAVAILABLE, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.OK

    def test_last_flow_ok_layer_tracked(self):
        guard = FlowGuard()
        guard.update_layer(50, 10.0)
        guard.evaluate([FlowSignal.OK, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK])
        guard.update_layer(60, 12.0)
        guard.evaluate([FlowSignal.ANOMALY, FlowSignal.ANOMALY,
                        FlowSignal.ANOMALY, FlowSignal.OK])
        assert guard.last_ok_layer == 50
        assert guard.last_ok_z == 10.0

    def test_reset_clears_all(self):
        guard = FlowGuard()
        guard.update_layer(50, 10.0)
        guard.evaluate([FlowSignal.ANOMALY, FlowSignal.OK,
                        FlowSignal.ANOMALY, FlowSignal.OK])
        guard.reset()
        assert guard.warning_count == 0
        assert guard.last_ok_layer == 0
        assert guard.last_ok_z == 0.0

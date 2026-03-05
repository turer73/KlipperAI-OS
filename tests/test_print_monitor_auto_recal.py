# tests/test_print_monitor_auto_recal.py
"""Tests for PrintMonitor auto-recalibration feature."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

from bed_level_analyzer import DriftReport, TrendResult, DriftDetector


# ---------------------------------------------------------------------------
# Helper: build a minimal PrintMonitor with all heavy deps mocked out
# ---------------------------------------------------------------------------

def _make_monitor(auto_recalibrate: bool = False):
    """Create a PrintMonitor with mocked dependencies."""
    env = {
        "AUTO_RECALIBRATE": "1" if auto_recalibrate else "0",
        "BED_LEVEL_CHECK": "1",
        "FLOWGUARD_ENABLED": "0",
        "ADAPTIVE_PRINT": "0",
        "PREDICTIVE_MAINT": "0",
        "AUTORECOVERY_ENABLED": "0",
    }
    with patch.dict(os.environ, env, clear=False), \
         patch("print_monitor.FrameCapture"), \
         patch("print_monitor.SpaghettiDetector"), \
         patch("print_monitor.FlowGuard"), \
         patch("print_monitor.HeaterDutyAnalyzer"), \
         patch("print_monitor.ExtruderLoadMonitor"), \
         patch("print_monitor.AdaptiveThresholdEngine"), \
         patch("print_monitor.AdaptivePrintController"), \
         patch("print_monitor.PredictiveMaintenanceEngine"), \
         patch("print_monitor.AutonomousRecoveryEngine"), \
         patch("print_monitor.DriftDetector") as MockDD, \
         patch("print_monitor.MoonrakerClient") as MockMR:

        from print_monitor import PrintMonitor
        monitor = PrintMonitor()
        # Replace with controllable mocks
        monitor.moonraker = MagicMock()
        monitor.drift_detector = MagicMock()
    return monitor


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPrePrintAutoRecalibrate:
    """Pre-print auto recalibration tests."""

    def test_pre_print_recalibrate_when_enabled(self):
        """drift=recalibrate + AUTO_RECALIBRATE=True -> sends KOS_BED_LEVEL_CALIBRATE gcode."""
        monitor = _make_monitor(auto_recalibrate=True)
        monitor._last_auto_recal_date = ""  # no recal today

        # Moonraker returns mesh data with a profile
        monitor.moonraker.get_bed_mesh.return_value = {
            "profile_name": "default",
            "mesh_matrix": [[0.15, 0.12], [0.11, 0.14]],
        }
        # DriftDetector says recalibrate
        monitor.drift_detector.check_drift.return_value = DriftReport(
            max_point_drift=0.15,
            mean_drift=0.13,
            recommendation="recalibrate",
        )

        monitor._bed_level_pre_print_check()

        # Should send gcode
        monitor.moonraker.send_gcode.assert_called_once_with("KOS_BED_LEVEL_CALIBRATE")
        # Should send notification about auto calibration
        monitor.moonraker.send_notification.assert_called_once()
        assert "Otomatik kalibrasyon" in monitor.moonraker.send_notification.call_args[0][0]
        # Date should be updated
        assert monitor._last_auto_recal_date == time.strftime("%Y-%m-%d")

    def test_pre_print_no_recalibrate_when_disabled(self):
        """drift=recalibrate + AUTO_RECALIBRATE=False -> only notification, no gcode."""
        monitor = _make_monitor(auto_recalibrate=False)
        monitor._last_auto_recal_date = ""

        monitor.moonraker.get_bed_mesh.return_value = {
            "profile_name": "default",
            "mesh_matrix": [[0.15, 0.12], [0.11, 0.14]],
        }
        monitor.drift_detector.check_drift.return_value = DriftReport(
            max_point_drift=0.15,
            mean_drift=0.13,
            recommendation="recalibrate",
        )

        monitor._bed_level_pre_print_check()

        # Should NOT send gcode
        monitor.moonraker.send_gcode.assert_not_called()
        # Should send notification recommending manual recalibration
        monitor.moonraker.send_notification.assert_called_once()
        assert "onerilir" in monitor.moonraker.send_notification.call_args[0][0]


class TestPostPrintAutoRecalibrate:
    """Post-print auto recalibration tests."""

    def test_post_print_auto_recalibrate_on_worsening(self):
        """worsening trend + idle + auto=True -> sends gcode."""
        monitor = _make_monitor(auto_recalibrate=True)
        monitor._last_auto_recal_date = ""

        monitor.moonraker.get_bed_mesh.return_value = {
            "profile_name": "default",
            "mesh_matrix": [[0.08, 0.0], [0.0, 0.0]],
        }
        monitor.moonraker.is_printing.return_value = False  # idle

        monitor.drift_detector.get_drift_trend.return_value = TrendResult(
            trend_direction="worsening",
            avg_drift_per_day=0.01,
            snapshots_analyzed=3,
            days_analyzed=5.0,
            forecast_days_to_recalibrate=5.0,
        )

        monitor._bed_level_post_print()

        # Should send notification + gcode because worsening + idle + auto enabled
        monitor.moonraker.send_notification.assert_called()
        monitor.moonraker.send_gcode.assert_called_once_with("KOS_BED_LEVEL_CALIBRATE")
        assert monitor._last_auto_recal_date == time.strftime("%Y-%m-%d")

    def test_daily_limit_prevents_second_recalibration(self):
        """same day -> no gcode sent (daily limit)."""
        monitor = _make_monitor(auto_recalibrate=True)
        # Already recalibrated today
        monitor._last_auto_recal_date = time.strftime("%Y-%m-%d")

        monitor.moonraker.get_bed_mesh.return_value = {
            "profile_name": "default",
            "mesh_matrix": [[0.08, 0.0], [0.0, 0.0]],
        }
        monitor.moonraker.is_printing.return_value = False

        monitor.drift_detector.get_drift_trend.return_value = TrendResult(
            trend_direction="worsening",
            avg_drift_per_day=0.01,
            snapshots_analyzed=3,
            days_analyzed=5.0,
            forecast_days_to_recalibrate=5.0,
        )

        monitor._bed_level_post_print()

        # Should NOT send gcode — already done today
        monitor.moonraker.send_gcode.assert_not_called()

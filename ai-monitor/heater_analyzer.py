"""
KlipperOS-AI — Heater Duty Cycle Analyzer (FlowGuard Layer 2)
=============================================================
Analyzes extruder heater PWM duty cycle to detect filament flow anomalies.
When filament stops flowing, the hotend absorbs less heat, causing duty
cycle to drop ~15% from baseline.
"""

from collections import deque
from enum import Enum
from typing import Optional


class FlowState(Enum):
    """Flow detection state."""
    OK = "OK"
    ANOMALY = "ANOMALY"
    CALIBRATING = "CALIBRATING"


class HeaterDutyAnalyzer:
    """Analyzes heater duty cycle for flow anomaly detection."""

    def __init__(self, window_size: int = 30, threshold_pct: float = 0.15,
                 calibration_count: int = 30):
        self.window_size = window_size
        self.threshold_pct = threshold_pct
        self.calibration_count = calibration_count
        self._window: deque = deque(maxlen=window_size)
        self._calibration_samples: list = []
        self.baseline: Optional[float] = None

    def add_sample(self, duty_cycle: float) -> None:
        """Add a duty cycle sample (0.0 to 1.0)."""
        self._window.append(duty_cycle)
        if self.baseline is None:
            self._calibration_samples.append(duty_cycle)

    def calibrate(self) -> None:
        """Compute baseline from collected calibration samples."""
        if self._calibration_samples:
            self.baseline = sum(self._calibration_samples) / len(self._calibration_samples)

    def check_flow(self) -> FlowState:
        """Check flow state based on duty cycle analysis."""
        if self.baseline is None:
            return FlowState.OK
        if len(self._window) < self.window_size:
            return FlowState.OK

        mean = sum(self._window) / len(self._window)
        if mean < self.baseline * (1 - self.threshold_pct):
            return FlowState.ANOMALY
        return FlowState.OK

    @property
    def confidence(self) -> float:
        """Fixed confidence for heater duty method."""
        return 0.70

    def reset(self) -> None:
        """Clear all state."""
        self._window.clear()
        self._calibration_samples.clear()
        self.baseline = None

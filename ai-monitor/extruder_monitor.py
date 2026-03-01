"""
KlipperOS-AI — Extruder Load Monitor (FlowGuard Layer 3)
========================================================
Monitors TMC2209 StallGuard SG_RESULT to detect flow anomalies.
Low SG = high motor load (clog), high SG = no load (no filament).
Also provides flow rate suggestions based on load deviation from baseline.
"""

from collections import deque
from typing import Optional

from heater_analyzer import FlowState


class ExtruderLoadMonitor:
    """Monitors TMC extruder motor load for flow detection."""

    def __init__(self, window_size: int = 100,
                 clog_threshold: float = 0.30,
                 empty_threshold: float = 2.0):
        self.window_size = window_size
        self.clog_threshold = clog_threshold
        self.empty_threshold = empty_threshold
        self._window: deque = deque(maxlen=window_size)
        self.baseline: Optional[float] = None

    def set_baseline(self, baseline: float) -> None:
        """Set the baseline SG_RESULT value from calibration."""
        self.baseline = baseline

    def add_sample(self, sg_result: int) -> None:
        """Add an SG_RESULT sample."""
        self._window.append(float(sg_result))

    def check_flow(self) -> FlowState:
        """Check flow state based on SG_RESULT analysis."""
        if self.baseline is None:
            return FlowState.OK
        if len(self._window) < self.window_size:
            return FlowState.OK

        mean = sum(self._window) / len(self._window)

        # Very low SG = high motor load = potential clog
        if mean < self.baseline * self.clog_threshold:
            return FlowState.ANOMALY

        # Very high SG = no motor load = filament gone
        if mean > self.baseline * self.empty_threshold:
            return FlowState.ANOMALY

        return FlowState.OK

    def suggest_flow_rate(self) -> float:
        """Suggest flow rate multiplier based on load deviation.

        Returns:
            1.0 for normal, 1.05 for under-extrusion, 0.95 for over-extrusion.
        """
        if self.baseline is None or len(self._window) == 0:
            return 1.0

        mean = sum(self._window) / len(self._window)
        ratio = mean / self.baseline

        if ratio > 1.2:  # Low load = under-extrusion
            return 1.05
        if ratio < 0.8:  # High load = over-extrusion
            return 0.95
        return 1.0

    @property
    def confidence(self) -> float:
        """Fixed confidence for TMC SG_RESULT method."""
        return 0.85

    def reset(self) -> None:
        """Clear all state."""
        self._window.clear()
        self.baseline = None

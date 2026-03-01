"""
KlipperOS-AI — FlowGuard Voting Engine
=======================================
Central voting engine for 4-layer flow detection.
Receives signals from sensor, heater, TMC, and AI camera layers,
produces a verdict using configurable voting thresholds.

Voting logic:
    0/4 anomalies → OK
    1/4 anomalies → NOTICE (log only)
    2/4 anomalies → WARNING (escalates after 3 consecutive cycles)
    3-4/4 anomalies → CRITICAL (instant pause)
"""

from enum import Enum
from typing import List


class FlowSignal(Enum):
    """Signal from a detection layer."""
    OK = "OK"
    ANOMALY = "ANOMALY"
    UNAVAILABLE = "UNAVAILABLE"


class FlowVerdict(Enum):
    """Verdict from the voting engine."""
    OK = "OK"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class FlowGuard:
    """4-layer flow detection voting engine."""

    def __init__(self, warning_threshold: int = 3):
        self.warning_threshold = warning_threshold
        self.warning_count: int = 0
        self.last_ok_layer: int = 0
        self.last_ok_z: float = 0.0
        self.current_layer: int = 0
        self.current_z: float = 0.0

    def update_layer(self, layer: int, z_height: float) -> None:
        """Update current layer and Z height."""
        self.current_layer = layer
        self.current_z = z_height

    def evaluate(self, signals: List[FlowSignal]) -> FlowVerdict:
        """Evaluate signals from all 4 detection layers.

        Args:
            signals: List of 4 FlowSignal values
                [sensor, heater, tmc, ai_camera]

        Returns:
            FlowVerdict based on voting logic.
        """
        # Count anomalies (UNAVAILABLE treated as OK)
        anomaly_count = sum(
            1 for s in signals if s == FlowSignal.ANOMALY
        )

        if anomaly_count == 0:
            # All OK — reset warning counter, track last OK layer
            self.warning_count = 0
            self.last_ok_layer = self.current_layer
            self.last_ok_z = self.current_z
            return FlowVerdict.OK

        elif anomaly_count == 1:
            # Single anomaly — notice only, don't escalate
            self.warning_count = 0
            return FlowVerdict.NOTICE

        elif anomaly_count == 2:
            # Two anomalies — warning, with escalation tracking
            self.warning_count += 1
            if self.warning_count >= self.warning_threshold:
                self.warning_count = 0
                return FlowVerdict.CRITICAL
            return FlowVerdict.WARNING

        else:
            # 3-4 anomalies — critical, instant action
            self.warning_count = 0
            return FlowVerdict.CRITICAL

    def reset(self) -> None:
        """Reset all state."""
        self.warning_count = 0
        self.last_ok_layer = 0
        self.last_ok_z = 0.0
        self.current_layer = 0
        self.current_z = 0.0

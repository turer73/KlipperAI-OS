"""
KlipperOS-AI — FlowGuard Voting Engine v2
==========================================
Central voting engine for 5-layer flow detection.
Layers:
    1. Filament sensor       — fiziksel filament algilama
    2. Heater duty cycle     — isitici PWM analizi
    3. TMC StallGuard        — motor yuk algilama
    4. AI camera             — gorsel hata tespiti
    5. Trend analyzer (v2)   — zaman serisi regresyon

Voting logic (5 katman):
    0/5 anomalies → OK
    1/5 anomalies → NOTICE (log only)
    2/5 anomalies → WARNING (escalates after 3 consecutive cycles)
    3-5/5 anomalies → CRITICAL (instant pause)
"""

from enum import Enum
from typing import List, Optional

try:
    from .trend_analyzer import TrendAnalyzer, TrendSeverity
except ImportError:
    from trend_analyzer import TrendAnalyzer, TrendSeverity


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
    """5-layer flow detection voting engine (v2).

    v2 yenilikleri:
    - 5. katman: TrendAnalyzer — zaman serisi regresyon ile yavas trend tespiti
    - feed_trend(): sicaklik/duty/sg verilerini trend analyzer'a besle
    - evaluate() artik 5 sinyal kabul eder (geriye uyumlu: 4 de olur)
    """

    def __init__(self, warning_threshold: int = 3,
                 trend_window_minutes: int = 30):
        self.warning_threshold = warning_threshold
        self.warning_count: int = 0
        self.last_ok_layer: int = 0
        self.last_ok_z: float = 0.0
        self.current_layer: int = 0
        self.current_z: float = 0.0

        # v2: Trend analyzer (5. katman)
        self.trend: TrendAnalyzer = TrendAnalyzer(
            window_minutes=trend_window_minutes,
            sample_interval=10,
            min_samples=18,  # ~3 dakika veri sonrasi aktif
        )

    def update_layer(self, layer: int, z_height: float) -> None:
        """Update current layer and Z height."""
        self.current_layer = layer
        self.current_z = z_height

    def feed_trend(self, extruder_temp: float = 0, bed_temp: float = 0,
                   heater_duty: float = 0, tmc_sg: int = 0,
                   mcu_temp: float = 0) -> None:
        """Trend analyzer'a veri besle. Her cycle'da cagirilmali.

        Args:
            extruder_temp: Extruder sicakligi (C)
            bed_temp: Yatak sicakligi (C)
            heater_duty: Extruder isitici duty cycle (0-1)
            tmc_sg: TMC StallGuard degeri
            mcu_temp: MCU sicakligi (C, opsiyonel)
        """
        if extruder_temp > 0:
            self.trend.add_sample("extruder_temp", extruder_temp)
        if bed_temp > 0:
            self.trend.add_sample("bed_temp", bed_temp)
        if heater_duty > 0:
            self.trend.add_sample("heater_duty", heater_duty)
        if tmc_sg > 0:
            self.trend.add_sample("tmc_sg", float(tmc_sg))
        if mcu_temp > 0:
            self.trend.add_sample("mcu_temp", mcu_temp)

    def get_trend_signal(self) -> FlowSignal:
        """Trend analyzer'dan FlowSignal uret."""
        if self.trend.has_anomaly():
            return FlowSignal.ANOMALY
        return FlowSignal.OK

    def evaluate(self, signals: List[FlowSignal]) -> FlowVerdict:
        """Evaluate signals from all detection layers.

        Args:
            signals: List of FlowSignal values.
                4 eleman: [sensor, heater, tmc, ai_camera] (v1 uyumlu)
                5 eleman: [sensor, heater, tmc, ai_camera, trend] (v2)
                4 eleman verilirse trend otomatik eklenir.

        Returns:
            FlowVerdict based on voting logic.
        """
        # v1 uyumluluk: 4 sinyal gelirse trend'i otomatik ekle
        if len(signals) < 5:
            signals = list(signals) + [self.get_trend_signal()]

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
            # 3+ anomalies — critical, instant action
            self.warning_count = 0
            return FlowVerdict.CRITICAL

    @property
    def trend_summary(self) -> dict:
        """Trend analizi ozeti — API/loglama icin."""
        trends = self.trend.check_trends()
        return {
            metric: {
                "direction": r.direction.value,
                "severity": r.severity.value,
                "slope": r.slope,
                "r_squared": r.r_squared,
                "samples": r.sample_count,
                "message": r.message,
            }
            for metric, r in trends.items()
        }

    def reset(self) -> None:
        """Reset all state."""
        self.warning_count = 0
        self.last_ok_layer = 0
        self.last_ok_z = 0.0
        self.current_layer = 0
        self.current_z = 0.0
        self.trend.reset()

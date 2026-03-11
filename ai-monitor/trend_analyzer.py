"""
KlipperOS-AI — Time Series Trend Analyzer (FlowGuard Layer 5)
=============================================================
Son N dakikadaki veri noktalarinda lineer regresyon ile trend tespiti.
Yavas gelisen sorunlari yakalar: nozul tikanma, isitici yaslama,
motor asiri isinma gibi durumlar.

Kullanim:
    analyzer = TrendAnalyzer(window_minutes=30, sample_interval=10)
    analyzer.add_sample("extruder_temp", 210.3)
    analyzer.add_sample("heater_duty", 0.42)
    result = analyzer.check_trends()
    # => {"extruder_temp": TrendResult(...), "heater_duty": TrendResult(...)}
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Optional


class TrendDirection(Enum):
    """Trend yonu."""
    STABLE = "stable"
    RISING = "rising"
    FALLING = "falling"


class TrendSeverity(Enum):
    """Trend siddeti."""
    NORMAL = "normal"
    WATCH = "watch"       # izleniyor, henuz aksiyon yok
    ANOMALY = "anomaly"   # FlowGuard'a sinyal gonder


@dataclass
class TrendResult:
    """Tek bir metrik icin trend analizi sonucu."""
    metric: str
    direction: TrendDirection = TrendDirection.STABLE
    severity: TrendSeverity = TrendSeverity.NORMAL
    slope: float = 0.0            # birim/dakika degisim hizi
    r_squared: float = 0.0       # regresyon uyumu (0-1)
    sample_count: int = 0
    message: str = ""


@dataclass
class _MetricBuffer:
    """Tek metrik icin zaman serisi buffer'i."""
    times: deque = field(default_factory=lambda: deque(maxlen=200))
    values: deque = field(default_factory=lambda: deque(maxlen=200))


class TrendAnalyzer:
    """Zaman serisi trend analizi — sliding window + lineer regresyon.

    Args:
        window_minutes: Analiz penceresi (dakika). Default 30.
        sample_interval: Ornekleme araligi (saniye). Default 10.
        min_samples: Trend tespiti icin minimum ornekleme. Default 18 (~3dk).
    """

    # Metrik bazli esik degerleri: (watch_slope, anomaly_slope)
    # slope birimi: birim/dakika
    THRESHOLDS: dict[str, tuple[float, float]] = {
        # Sicaklik dusmesi (C/dk) — pozitif = yukselis, negatif = dusus
        "extruder_temp":  (-0.3, -0.8),    # -0.3C/dk watch, -0.8C/dk anomaly
        "bed_temp":       (-0.2, -0.5),
        # Heater duty dususu (oran/dk)
        "heater_duty":    (-0.005, -0.015),
        # TMC StallGuard dususu (birim/dk)
        "tmc_sg":         (-2.0, -5.0),
        # Sicaklik yukselisi (asiri isinma)
        "mcu_temp":       (0.5, 1.0),       # MCU asiri isinma
    }

    def __init__(self, window_minutes: int = 30, sample_interval: int = 10,
                 min_samples: int = 18):
        self.window_seconds = window_minutes * 60
        self.sample_interval = sample_interval
        self.min_samples = min_samples
        self._buffers: dict[str, _MetricBuffer] = {}
        self._last_sample_time: dict[str, float] = {}

    def add_sample(self, metric: str, value: float) -> None:
        """Yeni veri noktasi ekle.

        Ayni metrik icin sample_interval'dan hizli gelen veriler atlanir.
        """
        now = monotonic()

        # Rate limiting
        last = self._last_sample_time.get(metric, 0)
        if now - last < self.sample_interval * 0.8:
            return

        if metric not in self._buffers:
            self._buffers[metric] = _MetricBuffer()

        buf = self._buffers[metric]
        buf.times.append(now)
        buf.values.append(value)
        self._last_sample_time[metric] = now

        # Eski verileri kirp (window disinda kalanlar)
        self._prune(metric)

    def _prune(self, metric: str) -> None:
        """Window disindaki eski verileri at."""
        buf = self._buffers[metric]
        cutoff = monotonic() - self.window_seconds
        while buf.times and buf.times[0] < cutoff:
            buf.times.popleft()
            buf.values.popleft()

    @staticmethod
    def _linear_regression(times: list[float], values: list[float]) -> tuple[float, float]:
        """Basit lineer regresyon — numpy gerektirmez.

        Returns:
            (slope, r_squared) — slope birimi: birim/dakika
        """
        n = len(times)
        if n < 2:
            return 0.0, 0.0

        # Zamanlari dakikaya cevir (ilk noktadan itibaren)
        t0 = times[0]
        t = [(ti - t0) / 60.0 for ti in times]

        # Ortalamalar
        t_mean = sum(t) / n
        v_mean = sum(values) / n

        # Regresyon katsayilari
        num = sum((ti - t_mean) * (vi - v_mean) for ti, vi in zip(t, values))
        den = sum((ti - t_mean) ** 2 for ti in t)

        if den < 1e-10:
            return 0.0, 0.0

        slope = num / den  # birim/dakika

        # R-squared
        ss_res = sum((vi - (v_mean + slope * (ti - t_mean))) ** 2
                      for ti, vi in zip(t, values))
        ss_tot = sum((vi - v_mean) ** 2 for vi in values)

        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-10 else 0.0
        r_squared = max(0.0, min(1.0, r_squared))  # clamp [0,1]

        return slope, r_squared

    def analyze_metric(self, metric: str) -> TrendResult:
        """Tek bir metrik icin trend analizi yap."""
        buf = self._buffers.get(metric)
        if buf is None or len(buf.times) < self.min_samples:
            return TrendResult(
                metric=metric,
                sample_count=len(buf.times) if buf else 0,
                message="Yetersiz veri"
            )

        times = list(buf.times)
        values = list(buf.values)
        slope, r_sq = self._linear_regression(times, values)

        # Trend yonu — 0.01/dk altindaki slope gurultu sayilir
        if abs(slope) < 0.01:
            direction = TrendDirection.STABLE
        elif slope > 0:
            direction = TrendDirection.RISING
        else:
            direction = TrendDirection.FALLING

        # Esik kontrol — r_squared < 0.3 ise trend guvenilir degil
        severity = TrendSeverity.NORMAL
        message = ""

        thresholds = self.THRESHOLDS.get(metric)
        if thresholds and r_sq >= 0.3:
            watch_thr, anomaly_thr = thresholds

            # Negatif esikler: dusus algilama
            if watch_thr < 0:
                if slope <= anomaly_thr:
                    severity = TrendSeverity.ANOMALY
                    message = f"{metric} hizla dusuyor: {slope:.3f}/dk (R²={r_sq:.2f})"
                elif slope <= watch_thr:
                    severity = TrendSeverity.WATCH
                    message = f"{metric} dusuyor: {slope:.3f}/dk"
            # Pozitif esikler: yukselis algilama (asiri isinma vb.)
            else:
                if slope >= anomaly_thr:
                    severity = TrendSeverity.ANOMALY
                    message = f"{metric} hizla yukseliyor: {slope:.3f}/dk (R²={r_sq:.2f})"
                elif slope >= watch_thr:
                    severity = TrendSeverity.WATCH
                    message = f"{metric} yukseliyor: {slope:.3f}/dk"

        return TrendResult(
            metric=metric,
            direction=direction,
            severity=severity,
            slope=round(slope, 4),
            r_squared=round(r_sq, 3),
            sample_count=len(values),
            message=message,
        )

    def check_trends(self) -> dict[str, TrendResult]:
        """Tum metriklerin trendini analiz et."""
        results = {}
        for metric in list(self._buffers.keys()):
            self._prune(metric)
            results[metric] = self.analyze_metric(metric)
        return results

    def has_anomaly(self) -> bool:
        """Herhangi bir metrikte ANOMALY var mi? FlowGuard entegrasyonu icin."""
        for metric in self._buffers:
            result = self.analyze_metric(metric)
            if result.severity == TrendSeverity.ANOMALY:
                return True
        return False

    def get_worst_trend(self) -> Optional[TrendResult]:
        """En kotu trendi dondur — bildirim icin."""
        worst: Optional[TrendResult] = None
        for metric in self._buffers:
            result = self.analyze_metric(metric)
            if worst is None or result.severity.value > worst.severity.value:
                worst = result
        return worst

    def reset(self) -> None:
        """Tum verileri temizle."""
        self._buffers.clear()
        self._last_sample_time.clear()

"""
KlipperOS-AI — Adaptive Threshold Engine
==========================================
Sabit esik degerleri yerine oturum basina ogrenen dinamik esikler.
Welford online algoritmasi ile mean/variance hesaplar — O(1) bellek.

HeaterDutyAnalyzer ve ExtruderLoadMonitor'deki sabit threshold_pct
degerleri yerine, gercek varyansa dayali esikler saglar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class RunningStats:
    """Welford online algoritmasi — mean/variance, depolama olmadan.

    Her yeni deger geldiginde O(1) islemle guncellenir.
    Sonuc: mean, variance, std
    """

    def __init__(self):
        self.n: int = 0
        self.mean: float = 0.0
        self._m2: float = 0.0

    def update(self, value: float) -> None:
        """Yeni deger ekle."""
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        delta2 = value - self.mean
        self._m2 += delta * delta2

    @property
    def variance(self) -> float:
        """Ornek varyans (n-1)."""
        if self.n < 2:
            return 0.0
        return self._m2 / (self.n - 1)

    @property
    def std(self) -> float:
        """Standart sapma."""
        return math.sqrt(self.variance)

    @property
    def is_ready(self) -> bool:
        """Yeterli ornek var mi? (en az 10)"""
        return self.n >= 10


@dataclass
class AdaptiveThresholdEngine:
    """Oturum basina ogrenilen dinamik esikler.

    Heater duty ve TMC SG_RESULT icin ayri istatistikler tutar.
    Sabit 15% yerine mean - 2*std kullanir — daha duyarli.
    """

    heater_stats: RunningStats = field(default_factory=RunningStats)
    tmc_stats: RunningStats = field(default_factory=RunningStats)
    ai_confidence_stats: RunningStats = field(default_factory=RunningStats)

    # Fallback sabit esikler (istatistik hazir olmadan)
    _heater_fallback_pct: float = 0.15
    _tmc_clog_fallback: float = 0.30
    _tmc_empty_fallback: float = 2.0

    def update(self, heater_duty: float = -1.0,
               sg_result: float = -1.0,
               ai_confidence: float = -1.0) -> None:
        """Yeni orneklerle istatistikleri guncelle."""
        if heater_duty >= 0:
            self.heater_stats.update(heater_duty)
        if sg_result >= 0:
            self.tmc_stats.update(sg_result)
        if ai_confidence >= 0:
            self.ai_confidence_stats.update(ai_confidence)

    def get_heater_threshold(self) -> float:
        """Heater duty anomali esigi: mean - 2*std.

        Returns:
            Heater duty cycle degeri altinda anomali sayilir.
        """
        if not self.heater_stats.is_ready:
            # Fallback: baseline yoksa sabit %15 dusus
            return self.heater_stats.mean * (1 - self._heater_fallback_pct) \
                if self.heater_stats.n > 0 else 0.0
        return self.heater_stats.mean - 2 * self.heater_stats.std

    def get_tmc_clog_threshold(self) -> float:
        """TMC SG_RESULT tikama esigi: cok dusuk SG = yuksek motor yuku.

        Returns:
            SG_RESULT bu degerin altindaysa tikama olasi.
        """
        if not self.tmc_stats.is_ready:
            return self.tmc_stats.mean * self._tmc_clog_fallback \
                if self.tmc_stats.n > 0 else 0.0
        # mean - 3*std (tikama nadir — 3 sigma)
        threshold = self.tmc_stats.mean - 3 * self.tmc_stats.std
        return max(threshold, 0.0)

    def get_tmc_empty_threshold(self) -> float:
        """TMC SG_RESULT bos filament esigi: cok yuksek SG = motor yuku yok.

        Returns:
            SG_RESULT bu degerin ustundeyse filament bitmis olabilir.
        """
        if not self.tmc_stats.is_ready:
            return self.tmc_stats.mean * self._tmc_empty_fallback \
                if self.tmc_stats.n > 0 else float("inf")
        # mean + 3*std
        return self.tmc_stats.mean + 3 * self.tmc_stats.std

    def get_ai_confidence_threshold(self) -> float:
        """AI guven esigi: mean - 1.5*std.

        Returns:
            AI confidence bu degerin altindaysa dusuk guvenli sonuc.
        """
        if not self.ai_confidence_stats.is_ready:
            return 0.7  # Sabit fallback
        return max(self.ai_confidence_stats.mean - 1.5 * self.ai_confidence_stats.std, 0.3)

    @property
    def summary(self) -> dict:
        """Mevcut esik ozeti."""
        return {
            "heater": {
                "samples": self.heater_stats.n,
                "mean": round(self.heater_stats.mean, 4),
                "std": round(self.heater_stats.std, 4),
                "threshold": round(self.get_heater_threshold(), 4),
                "ready": self.heater_stats.is_ready,
            },
            "tmc": {
                "samples": self.tmc_stats.n,
                "mean": round(self.tmc_stats.mean, 2),
                "std": round(self.tmc_stats.std, 2),
                "clog_threshold": round(self.get_tmc_clog_threshold(), 2),
                "empty_threshold": round(self.get_tmc_empty_threshold(), 2),
                "ready": self.tmc_stats.is_ready,
            },
            "ai_confidence": {
                "samples": self.ai_confidence_stats.n,
                "mean": round(self.ai_confidence_stats.mean, 3),
                "threshold": round(self.get_ai_confidence_threshold(), 3),
                "ready": self.ai_confidence_stats.is_ready,
            },
        }

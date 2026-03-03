"""
KlipperOS-AI — Adaptive Print Controller
==========================================
Gercek zamanli baski parametresi ayarlama motoru.
Her 5 katmanda skorlari degerlendirip hiz, akis ve sicaklik ayarlar.

Guvenlik sinirlari:
    SPEED_MIN_FACTOR = 0.70  (asla %70'in altina)
    SPEED_MAX_FACTOR = 1.15  (asla %115'in ustune)
    FLOW_MIN = 0.90          (asla %90'in altina)
    FLOW_MAX = 1.10          (asla %110'un ustune)
    TEMP_DELTA_MAX = 10      (asla +/-10°C'den fazla)

G-code komutlari:
    SET_VELOCITY_LIMIT VELOCITY=X  — hiz
    M221 S{percent}                — akis orani
    M104 S{temp}                   — sicaklik
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("klipperos-ai.adaptive-print")


# ─── Guvenlik Sinirlari ──────────────────────────────────────────────────────

SPEED_MIN_FACTOR = 0.70   # Asla orijinal hizin %70'inin altina
SPEED_MAX_FACTOR = 1.15   # Asla orijinal hizin %115'inin ustune
FLOW_MIN = 0.90           # Asla akis oraninin %90'inin altina
FLOW_MAX = 1.10           # Asla akis oraninin %110'unun ustune
TEMP_DELTA_MAX = 10       # Asla ±10°C'den fazla sicaklik degisikligi

EVAL_INTERVAL_LAYERS = 5  # Her 5 katmanda bir degerlendir
HISTORY_SIZE = 50          # Son 50 katman skoru tut


# ─── Veri Yapilari ────────────────────────────────────────────────────────────

@dataclass
class LayerQualityScore:
    """Tek bir katmanin kalite skoru."""
    layer: int = 0
    z_height: float = 0.0
    flow_consistency: float = 1.0  # extruder_monitor'den (0-1)
    thermal_stability: float = 1.0  # heater_analyzer'den (0-1)
    visual_score: float = 1.0       # spaghetti_detect'ten (0-1)
    composite_score: float = 1.0    # agirlikli ortalama
    timestamp: float = field(default_factory=time.time)


@dataclass
class PrintAdjustment:
    """Uygulanan parametre ayarlamasi."""
    speed_factor: float = 1.0   # 1.0 = degisiklik yok
    flow_factor: float = 1.0    # 1.0 = degisiklik yok
    temp_delta: float = 0.0     # 0 = degisiklik yok
    reason: str = ""


# ─── Skor Hesaplama ──────────────────────────────────────────────────────────

def compute_flow_consistency(flow_rate_suggestion: float) -> float:
    """ExtruderLoadMonitor.suggest_flow_rate() sonucunu skora cevir.

    suggest_flow_rate: 1.0=normal, 1.05=under-extrusion, 0.95=over-extrusion
    Skor: 1.0=mukemmel, 0.0=cok kotu
    """
    deviation = abs(flow_rate_suggestion - 1.0)
    return max(0.0, 1.0 - deviation * 10)  # 0.05 sapma -> 0.5 skor


def compute_thermal_stability(heater_duty: float, baseline: float) -> float:
    """Heater duty cycle sapmasi skora cevir.

    baseline'a yakin → 1.0, %20 sapma → 0.0
    """
    if baseline <= 0:
        return 1.0
    ratio = heater_duty / baseline
    deviation = abs(ratio - 1.0)
    return max(0.0, 1.0 - deviation * 5)  # %20 sapma = 0


def compute_visual_score(ai_confidence: float, ai_class: str) -> float:
    """AI tespit sonucunu skora cevir.

    normal + yuksek guven → 1.0
    spaghetti + yuksek guven → 0.0
    """
    if ai_class == "normal":
        return min(1.0, ai_confidence)
    elif ai_class in ("spaghetti", "stringing", "under_extrusion"):
        return max(0.0, 1.0 - ai_confidence)
    return 0.8  # Bilinmeyen sinif — hafif uyari


# ─── Ana Kontrolcu ───────────────────────────────────────────────────────────

class AdaptivePrintController:
    """Gercek zamanli baski parametresi ayarlama motoru."""

    # Agirliklar: flow > thermal > visual
    WEIGHT_FLOW = 0.40
    WEIGHT_THERMAL = 0.30
    WEIGHT_VISUAL = 0.30

    def __init__(self):
        self._scores: deque[LayerQualityScore] = deque(maxlen=HISTORY_SIZE)
        self._current_speed_factor = 1.0
        self._current_flow_factor = 1.0
        self._current_temp_delta = 0.0
        self._base_speed: Optional[float] = None  # Orijinal yazici hizi
        self._base_temp: Optional[float] = None    # Orijinal sicaklik
        self._adjustments: list[PrintAdjustment] = []
        self._enabled = True

    def set_base_params(self, speed: float, temp: float) -> None:
        """Baski baslangic parametrelerini kaydet."""
        self._base_speed = speed
        self._base_temp = temp
        logger.info("Adaptive base: speed=%.0f mm/s, temp=%.0f°C", speed, temp)

    # --- Katman Skorlama ---

    def score_layer(
        self,
        layer: int,
        z_height: float,
        flow_rate_suggestion: float = 1.0,
        heater_duty: float = 0.0,
        heater_baseline: float = 0.0,
        ai_confidence: float = 1.0,
        ai_class: str = "normal",
    ) -> LayerQualityScore:
        """Katman kalite skoru hesapla."""
        flow_score = compute_flow_consistency(flow_rate_suggestion)
        thermal_score = compute_thermal_stability(heater_duty, heater_baseline)
        visual_score = compute_visual_score(ai_confidence, ai_class)

        composite = (
            self.WEIGHT_FLOW * flow_score
            + self.WEIGHT_THERMAL * thermal_score
            + self.WEIGHT_VISUAL * visual_score
        )

        score = LayerQualityScore(
            layer=layer,
            z_height=z_height,
            flow_consistency=round(flow_score, 3),
            thermal_stability=round(thermal_score, 3),
            visual_score=round(visual_score, 3),
            composite_score=round(composite, 3),
        )
        self._scores.append(score)
        return score

    # --- Degerlendir & Ayarla ---

    def evaluate_adaptation(self) -> Optional[PrintAdjustment]:
        """Son N katman skorlarini analiz et, parametre ayarlamasi dondur.

        Returns:
            PrintAdjustment veya None (ayarlama gerekli degilse).
        """
        if not self._enabled or len(self._scores) < EVAL_INTERVAL_LAYERS:
            return None

        # Son EVAL_INTERVAL_LAYERS katman
        recent = list(self._scores)[-EVAL_INTERVAL_LAYERS:]
        avg_composite = sum(s.composite_score for s in recent) / len(recent)
        avg_flow = sum(s.flow_consistency for s in recent) / len(recent)
        avg_thermal = sum(s.thermal_stability for s in recent) / len(recent)

        adj = PrintAdjustment()
        reasons = []

        # Dusuk kalite → hiz dusur
        if avg_composite < 0.6:
            adj.speed_factor = max(SPEED_MIN_FACTOR, self._current_speed_factor - 0.05)
            reasons.append(f"dusuk kalite ({avg_composite:.2f})")

        # Yuksek kalite → hiz artir (tedbirli)
        elif avg_composite > 0.9 and self._current_speed_factor < 1.0:
            adj.speed_factor = min(SPEED_MAX_FACTOR, self._current_speed_factor + 0.02)
            reasons.append(f"yuksek kalite ({avg_composite:.2f})")
        else:
            adj.speed_factor = self._current_speed_factor

        # Akis tutarsizligi → akis ayarla
        if avg_flow < 0.5:
            adj.flow_factor = min(FLOW_MAX, self._current_flow_factor + 0.02)
            reasons.append(f"dusuk akis ({avg_flow:.2f})")
        elif avg_flow > 0.95:
            # Mukemmel akis — orijinale dogru don
            if self._current_flow_factor != 1.0:
                adj.flow_factor = 1.0 + (self._current_flow_factor - 1.0) * 0.5
                adj.flow_factor = max(FLOW_MIN, min(FLOW_MAX, adj.flow_factor))
        else:
            adj.flow_factor = self._current_flow_factor

        # Termal dengesizlik → sicaklik ayarla
        if avg_thermal < 0.5:
            adj.temp_delta = min(TEMP_DELTA_MAX, self._current_temp_delta + 2)
            reasons.append(f"termal sapma ({avg_thermal:.2f})")
        else:
            adj.temp_delta = self._current_temp_delta

        # Guvenlik sinirlari
        adj.speed_factor = max(SPEED_MIN_FACTOR, min(SPEED_MAX_FACTOR, adj.speed_factor))
        adj.flow_factor = max(FLOW_MIN, min(FLOW_MAX, adj.flow_factor))
        adj.temp_delta = max(-TEMP_DELTA_MAX, min(TEMP_DELTA_MAX, adj.temp_delta))

        # Degisiklik var mi?
        speed_changed = abs(adj.speed_factor - self._current_speed_factor) > 0.005
        flow_changed = abs(adj.flow_factor - self._current_flow_factor) > 0.005
        temp_changed = abs(adj.temp_delta - self._current_temp_delta) > 0.5

        if not (speed_changed or flow_changed or temp_changed):
            return None

        adj.reason = "; ".join(reasons) if reasons else "fine-tuning"
        return adj

    def apply_adjustment(self, adj: PrintAdjustment, gcode_sender=None) -> bool:
        """G-code ile parametreleri uygula.

        Args:
            adj: Uygulanacak ayarlama.
            gcode_sender: Callable — gcode_sender("G-CODE") cagirir.
                         Genellikle MoonrakerClient uzerinden.

        Returns:
            True basarili ise.
        """
        commands = []

        if abs(adj.speed_factor - self._current_speed_factor) > 0.005:
            if self._base_speed:
                new_speed = int(self._base_speed * adj.speed_factor)
                commands.append(f"SET_VELOCITY_LIMIT VELOCITY={new_speed}")
            self._current_speed_factor = adj.speed_factor

        if abs(adj.flow_factor - self._current_flow_factor) > 0.005:
            flow_pct = int(adj.flow_factor * 100)
            commands.append(f"M221 S{flow_pct}")
            self._current_flow_factor = adj.flow_factor

        if abs(adj.temp_delta - self._current_temp_delta) > 0.5:
            if self._base_temp:
                new_temp = int(self._base_temp + adj.temp_delta)
                commands.append(f"M104 S{new_temp}")
            self._current_temp_delta = adj.temp_delta

        if commands and gcode_sender:
            for cmd in commands:
                try:
                    gcode_sender(cmd)
                    logger.info("Adaptive G-code: %s", cmd)
                except Exception as e:
                    logger.error("G-code hatasi: %s — %s", cmd, e)
                    return False

        self._adjustments.append(adj)
        if len(self._adjustments) > 100:
            self._adjustments = self._adjustments[-100:]

        logger.info(
            "Adaptive: speed=%.2f, flow=%.2f, temp_delta=%.1f — %s",
            adj.speed_factor, adj.flow_factor, adj.temp_delta, adj.reason,
        )
        return True

    # --- Durum ---

    @property
    def current_adjustments(self) -> dict:
        """Mevcut ayarlama durumu."""
        return {
            "speed_factor": self._current_speed_factor,
            "flow_factor": self._current_flow_factor,
            "temp_delta": self._current_temp_delta,
            "base_speed": self._base_speed,
            "base_temp": self._base_temp,
            "enabled": self._enabled,
            "score_count": len(self._scores),
            "adjustment_count": len(self._adjustments),
        }

    @property
    def recent_scores(self) -> list[dict]:
        """Son katman skorlari."""
        return [
            {
                "layer": s.layer,
                "z": s.z_height,
                "flow": s.flow_consistency,
                "thermal": s.thermal_stability,
                "visual": s.visual_score,
                "composite": s.composite_score,
            }
            for s in list(self._scores)[-20:]
        ]

    def reset(self) -> None:
        """Tum durumu sifirla (yeni baski icin)."""
        self._scores.clear()
        self._current_speed_factor = 1.0
        self._current_flow_factor = 1.0
        self._current_temp_delta = 0.0
        self._base_speed = None
        self._base_temp = None
        self._adjustments.clear()

    def set_enabled(self, enabled: bool) -> None:
        """Adaptif modu ac/kapat."""
        self._enabled = enabled
        logger.info("Adaptive print: %s", "aktif" if enabled else "devre disi")

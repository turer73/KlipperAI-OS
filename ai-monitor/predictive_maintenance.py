"""
KlipperOS-AI — Predictive Maintenance Engine
=============================================
Uzun vadeli trend analizi ile bakim ihtiyaclarini onceden tahmin eder.

Izlenen bilesenler:
    - Nozul: duty cycle trendi (tikanma/asınma)
    - Isitici: ayni sicaklik icin artan duty (eleman yaslanmasi)
    - Kayis: TMC SG_RESULT trendi (kayis gevsemesi/rulman asınmasi)

Depolama: /var/lib/klipperos-ai/maintenance.json
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("klipperos-ai.maintenance")


# ─── Sabitler ────────────────────────────────────────────────────────────────

STATE_PATH = Path("/var/lib/klipperos-ai/maintenance.json")
MAX_TREND_POINTS = 500      # Trend basina max veri noktasi
CHECK_INTERVAL_SEC = 60     # Bakim kontrolu araligi (1 dk)
HOURS_TO_SECONDS = 3600


# ─── Trend Analizi ───────────────────────────────────────────────────────────

class TrendAnalyzer:
    """Basit lineer regresyon ile zaman serisi trend analizi.

    Incremental hesaplama — her add_point() O(1).
    slope() negatif = azaliyor, pozitif = artiyor.
    """

    def __init__(self, max_points: int = MAX_TREND_POINTS):
        self._max_points = max_points
        self._points: list[tuple[float, float]] = []
        # Incremental lineer regresyon icin
        self._n = 0
        self._sum_x = 0.0
        self._sum_y = 0.0
        self._sum_xy = 0.0
        self._sum_x2 = 0.0

    def add_point(self, timestamp: float, value: float) -> None:
        """Yeni veri noktasi ekle."""
        self._points.append((timestamp, value))
        self._n += 1
        self._sum_x += timestamp
        self._sum_y += value
        self._sum_xy += timestamp * value
        self._sum_x2 += timestamp * timestamp

        # Max boyut kontrolu — en eski noktayi cikar
        if len(self._points) > self._max_points:
            old_t, old_v = self._points.pop(0)
            self._n -= 1
            self._sum_x -= old_t
            self._sum_y -= old_v
            self._sum_xy -= old_t * old_v
            self._sum_x2 -= old_t * old_t

    @property
    def count(self) -> int:
        return self._n

    def slope(self) -> float:
        """Lineer regresyon egimi (birim/saniye).

        Returns:
            Egim degeri. 0.0 eger yeterli veri yoksa.
        """
        if self._n < 2:
            return 0.0
        denom = self._n * self._sum_x2 - self._sum_x ** 2
        if abs(denom) < 1e-12:
            return 0.0
        return (self._n * self._sum_xy - self._sum_x * self._sum_y) / denom

    def slope_per_hour(self) -> float:
        """Saatlik egim (birim/saat)."""
        return self.slope() * HOURS_TO_SECONDS

    def predict(self, seconds_ahead: float) -> float:
        """Gelecek tahmini.

        Args:
            seconds_ahead: Kac saniye sonrasini tahmin et.

        Returns:
            Tahmini deger.
        """
        if self._n < 2:
            return self._sum_y / self._n if self._n > 0 else 0.0

        # y = mx + b
        m = self.slope()
        mean_x = self._sum_x / self._n
        mean_y = self._sum_y / self._n
        b = mean_y - m * mean_x

        last_t = self._points[-1][0] if self._points else time.time()
        return m * (last_t + seconds_ahead) + b

    def is_degrading(self, threshold_per_hour: float) -> bool:
        """Trend bozuluyor mu?

        Args:
            threshold_per_hour: Saatlik degisim esigi (pozitif = artan sorun).

        Returns:
            True eger trend esigi asiyorsa.
        """
        if self._n < 10:
            return False
        return abs(self.slope_per_hour()) > threshold_per_hour

    def current_mean(self) -> float:
        """Mevcut ortalama."""
        if self._n == 0:
            return 0.0
        return self._sum_y / self._n

    def to_dict(self) -> dict:
        """Serializasyon."""
        # Son 100 noktayi kaydet (disk tasarrufu)
        return {
            "points": self._points[-100:],
            "n": self._n,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TrendAnalyzer:
        """Deserialization."""
        ta = cls()
        for t, v in data.get("points", []):
            ta.add_point(t, v)
        return ta


# ─── Bakim Uyarisi ───────────────────────────────────────────────────────────

class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MaintenanceAlert:
    """Bakim uyarisi."""
    component: str          # "belt_x", "nozzle", "heater"
    severity: str           # "info", "warning", "critical"
    message: str
    probability: float      # 0-1
    recommended_action: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Bilesen Izleyicileri ────────────────────────────────────────────────────

class ThermalDriftTracker:
    """Uzun vadeli isitici davranisi — eleman yaslanmasi tespiti.

    Ayni hedef sicaklik icin artan duty cycle = isitici bozuluyor.
    Dusuk duty -> normal. Artan duty -> isitici direnci artiyor.
    """

    def __init__(self):
        self.duty_trend = TrendAnalyzer()
        self._last_target_temp: float = 0.0

    def update(self, duty: float, target_temp: float) -> None:
        """Yeni heater duty ornegi."""
        # Sadece sabit sicaklik icin kaydet (rampa haric)
        if target_temp > 0 and abs(target_temp - self._last_target_temp) < 2.0:
            self.duty_trend.add_point(time.time(), duty)
        self._last_target_temp = target_temp

    def check(self) -> Optional[MaintenanceAlert]:
        """Isitici yaslanma kontrolu."""
        if self.duty_trend.count < 30:
            return None

        slope_h = self.duty_trend.slope_per_hour()

        # Duty cycle saatte %1+ artiyorsa uyari
        if slope_h > 0.01:
            severity = AlertSeverity.WARNING if slope_h < 0.03 else AlertSeverity.CRITICAL
            prob = min(1.0, slope_h / 0.05)
            return MaintenanceAlert(
                component="heater",
                severity=severity,
                message=f"Isitici duty cycle artis trendi: {slope_h:.4f}/saat. "
                        f"Isitici elemani yaslanmis olabilir.",
                probability=round(prob, 2),
                recommended_action="PID kalibrasyonu calistirin. "
                                   "Devam ederse isitici katrij degistirin.",
            )
        return None

    def to_dict(self) -> dict:
        return {"duty_trend": self.duty_trend.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> ThermalDriftTracker:
        t = cls()
        if "duty_trend" in data:
            t.duty_trend = TrendAnalyzer.from_dict(data["duty_trend"])
        return t


class MotorLoadTracker:
    """TMC SG_RESULT trendleri — kayis/rulman asınması tespiti.

    Sabit hizda artan motor yuku (dusuk SG) = kayis gevsemis veya
    rulman asınmis. Azalan SG trendi sorun isareti.
    """

    def __init__(self, name: str = "extruder"):
        self.name = name
        self.sg_trend = TrendAnalyzer()

    def update(self, sg_result: float) -> None:
        """Yeni SG_RESULT ornegi."""
        if sg_result >= 0:
            self.sg_trend.add_point(time.time(), sg_result)

    def check(self) -> Optional[MaintenanceAlert]:
        """Motor yuku trend kontrolu."""
        if self.sg_trend.count < 30:
            return None

        slope_h = self.sg_trend.slope_per_hour()

        # SG azaliyor (motor yuku artiyor) = sorun
        if slope_h < -5.0:  # Saatte 5+ SG dususu
            severity = AlertSeverity.WARNING if slope_h > -15.0 else AlertSeverity.CRITICAL
            prob = min(1.0, abs(slope_h) / 20.0)
            return MaintenanceAlert(
                component=f"motor_{self.name}",
                severity=severity,
                message=f"{self.name} motor yuku artiyor (SG trend: {slope_h:.1f}/saat). "
                        f"Kayis/rulman asınmasi olabilir.",
                probability=round(prob, 2),
                recommended_action="Kayis gerilimini kontrol edin. "
                                   "Ekstruder mekanizmasini temizleyin.",
            )

        # SG artiyor (motor yuku azaliyor) = filament tutamiyaor
        if slope_h > 10.0:
            return MaintenanceAlert(
                component=f"motor_{self.name}",
                severity=AlertSeverity.WARNING,
                message=f"{self.name} motor yuku azaliyor (SG trend: +{slope_h:.1f}/saat). "
                        f"Ekstruder kavrama gucu dusmus olabilir.",
                probability=round(min(1.0, slope_h / 20.0), 2),
                recommended_action="Ekstruder disliyi kontrol edin. "
                                   "Filament yolunu temizleyin.",
            )

        return None

    def to_dict(self) -> dict:
        return {"name": self.name, "sg_trend": self.sg_trend.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> MotorLoadTracker:
        t = cls(name=data.get("name", "extruder"))
        if "sg_trend" in data:
            t.sg_trend = TrendAnalyzer.from_dict(data["sg_trend"])
        return t


class NozzleWearTracker:
    """Nozul asınma/tıkanma tespiti.

    Duty + SG birlikte degerlendirilir:
    - Dusuk duty + dusuk SG = tikali nozul
    - Normal duty + yuksek variasyon = nozul asınmis
    """

    def __init__(self):
        self.duty_variance_trend = TrendAnalyzer()
        self._duty_window: list[float] = []
        self._window_size = 20

    def update(self, duty: float) -> None:
        """Duty cycle varyans takibi."""
        self._duty_window.append(duty)
        if len(self._duty_window) > self._window_size:
            self._duty_window.pop(0)

        if len(self._duty_window) >= self._window_size:
            mean = sum(self._duty_window) / len(self._duty_window)
            variance = sum((x - mean) ** 2 for x in self._duty_window) / len(self._duty_window)
            self.duty_variance_trend.add_point(time.time(), variance)

    def check(self) -> Optional[MaintenanceAlert]:
        """Nozul durum kontrolu."""
        if self.duty_variance_trend.count < 10:
            return None

        slope_h = self.duty_variance_trend.slope_per_hour()
        current_var = self.duty_variance_trend.current_mean()

        # Varyans artiyor = nozul asınmis (kararsiz akis)
        if slope_h > 0.001 and current_var > 0.005:
            severity = AlertSeverity.WARNING if current_var < 0.01 else AlertSeverity.CRITICAL
            prob = min(1.0, current_var / 0.02)
            return MaintenanceAlert(
                component="nozzle",
                severity=severity,
                message=f"Nozul akis kararsizligi artiyor (varyans: {current_var:.4f}, "
                        f"trend: +{slope_h:.5f}/saat). Nozul asınmis olabilir.",
                probability=round(prob, 2),
                recommended_action="Nozul temizleyin veya degistirin. "
                                   "Soguk cekme (cold pull) deneyin.",
            )
        return None

    def to_dict(self) -> dict:
        return {"variance_trend": self.duty_variance_trend.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> NozzleWearTracker:
        t = cls()
        if "variance_trend" in data:
            t.duty_variance_trend = TrendAnalyzer.from_dict(data["variance_trend"])
        return t


# ─── Ana Motor ───────────────────────────────────────────────────────────────

class PredictiveMaintenanceEngine:
    """Ongorucu bakim motoru.

    3 bilesen izleyicisini orkestre eder:
    - ThermalDriftTracker  (isitici yaslanmasi)
    - MotorLoadTracker     (kayis/rulman asınmasi)
    - NozzleWearTracker    (nozul asınma/tikanma)

    check_maintenance() tum bilesenlerden uyari toplar.
    """

    def __init__(self, state_path: Path = STATE_PATH):
        self._state_path = state_path
        self.thermal_tracker = ThermalDriftTracker()
        self.motor_tracker = MotorLoadTracker()
        self.nozzle_tracker = NozzleWearTracker()

        self._alerts: list[MaintenanceAlert] = []
        self._last_check_time = 0.0
        self._total_print_hours = 0.0
        self._session_start = time.time()

        # Onceki durumu yukle
        self.load_state()

    def update(self, heater_duty: float = -1.0,
               sg_result: float = -1.0,
               target_temp: float = 0.0) -> None:
        """Yeni sensor verileriyle izleyicileri guncelle.

        Args:
            heater_duty: Heater PWM orani (0-1), -1=mevcut degil.
            sg_result: TMC SG_RESULT, -1=mevcut degil.
            target_temp: Hedef sicaklik (°C).
        """
        if heater_duty >= 0:
            self.thermal_tracker.update(heater_duty, target_temp)
            self.nozzle_tracker.update(heater_duty)

        if sg_result >= 0:
            self.motor_tracker.update(sg_result)

    def check_maintenance(self) -> list[MaintenanceAlert]:
        """Tum bilesenlerden bakim uyarisi topla.

        Returns:
            Aktif uyari listesi.
        """
        now = time.time()
        if now - self._last_check_time < CHECK_INTERVAL_SEC:
            return self._alerts  # Cache'li sonuc

        self._last_check_time = now
        alerts = []

        # Her izleyiciyi kontrol et
        for tracker in [self.thermal_tracker, self.motor_tracker, self.nozzle_tracker]:
            alert = tracker.check()
            if alert:
                alerts.append(alert)

        self._alerts = alerts

        # Durum kaydet (her kontrolde degil, her 10 dk'da)
        if int(now) % 600 < CHECK_INTERVAL_SEC:
            self.save_state()

        return alerts

    def save_state(self) -> bool:
        """Durumu diske kaydet."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "version": 1,
                "saved_at": time.time(),
                "print_hours": self._total_print_hours,
                "thermal": self.thermal_tracker.to_dict(),
                "motor": self.motor_tracker.to_dict(),
                "nozzle": self.nozzle_tracker.to_dict(),
            }
            self._state_path.write_text(json.dumps(state, indent=2))
            return True
        except Exception as e:
            logger.error("Bakim durumu kaydedilemedi: %s", e)
            return False

    def load_state(self) -> bool:
        """Durumu diskten yukle."""
        if not self._state_path.exists():
            return False
        try:
            data = json.loads(self._state_path.read_text())
            if data.get("version") != 1:
                return False

            self._total_print_hours = data.get("print_hours", 0.0)

            if "thermal" in data:
                self.thermal_tracker = ThermalDriftTracker.from_dict(data["thermal"])
            if "motor" in data:
                self.motor_tracker = MotorLoadTracker.from_dict(data["motor"])
            if "nozzle" in data:
                self.nozzle_tracker = NozzleWearTracker.from_dict(data["nozzle"])

            logger.info("Bakim durumu yuklendi (%.1f saat)", self._total_print_hours)
            return True
        except Exception as e:
            logger.error("Bakim durumu yuklenemedi: %s", e)
            return False

    def add_print_hours(self, hours: float) -> None:
        """Baski saati ekle."""
        self._total_print_hours += hours

    @property
    def status(self) -> dict:
        """Mevcut bakim durumu."""
        return {
            "print_hours": round(self._total_print_hours, 1),
            "alerts": [a.to_dict() for a in self._alerts],
            "trackers": {
                "heater": {
                    "samples": self.thermal_tracker.duty_trend.count,
                    "slope_per_hour": round(self.thermal_tracker.duty_trend.slope_per_hour(), 6),
                },
                "motor": {
                    "samples": self.motor_tracker.sg_trend.count,
                    "slope_per_hour": round(self.motor_tracker.sg_trend.slope_per_hour(), 2),
                },
                "nozzle": {
                    "samples": self.nozzle_tracker.duty_variance_trend.count,
                    "mean_variance": round(self.nozzle_tracker.duty_variance_trend.current_mean(), 6),
                },
            },
        }

    def reset(self) -> None:
        """Tum izleyicileri sifirla."""
        self.thermal_tracker = ThermalDriftTracker()
        self.motor_tracker = MotorLoadTracker()
        self.nozzle_tracker = NozzleWearTracker()
        self._alerts = []
        self._last_check_time = 0.0

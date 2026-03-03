"""
KlipperOS-AI — AI Resource Manager
====================================
CPU governor, bellek yonetimi, termal koruma.
2 saniyede bir sistem metriklerini toplar, degerlendirip aksiyon alir.

Governor durum makinesi:
    idle     → schedutil (guc tasarrufu)
    printing → performance (maks kararlilik)
    paused   → ondemand (dengeli)
    >82°C    → powersave (termal koruma, hepsini override)

Ortam degiskenleri:
    MOONRAKER_URL       — default http://127.0.0.1:7125
    RESOURCE_INTERVAL   — kontrol araligi saniye (default: 2)
    THERMAL_WARNING     — uyari sicakligi (default: 75)
    THERMAL_CRITICAL    — kritik sicaklik (default: 82)
    MEMORY_WARNING_PCT  — bellek uyari esigi (default: 80)
    MEMORY_CRITICAL_PCT — bellek kritik esigi (default: 90)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/kos-resource-manager.log", mode="a"),
    ],
)
logger = logging.getLogger("klipperos-ai.resource-mgr")

# --- Yapilandirma ---
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")
RESOURCE_INTERVAL = int(os.environ.get("RESOURCE_INTERVAL", "2"))


# ─── Veri Yapilari ────────────────────────────────────────────────────────────

@dataclass
class ResourcePolicy:
    """Esik degerleri — API uzerinden degistirilebilir."""
    memory_warning_pct: float = float(os.environ.get("MEMORY_WARNING_PCT", "80"))
    memory_critical_pct: float = float(os.environ.get("MEMORY_CRITICAL_PCT", "90"))
    cpu_temp_warning: float = float(os.environ.get("THERMAL_WARNING", "75"))
    cpu_temp_critical: float = float(os.environ.get("THERMAL_CRITICAL", "82"))


@dataclass
class SystemMetrics:
    """Tek bir olcum noktasi."""
    timestamp: float = 0.0
    cpu_percent: float = 0.0
    cpu_per_core: list[float] = field(default_factory=list)
    memory_percent: float = 0.0
    memory_available_mb: int = 0
    cpu_temperature: float = 0.0
    disk_io_percent: float = 0.0
    load_avg_1m: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class ResourceAction(Enum):
    """Kaynak yoneticisi aksiyonlari."""
    SET_GOVERNOR = "set_governor"
    THROTTLE_CAMERA = "throttle_camera"
    MEMORY_RELIEF = "memory_relief"
    NOTIFY = "notify"


class PrinterState(Enum):
    IDLE = "idle"
    PRINTING = "printing"
    PAUSED = "paused"
    UNKNOWN = "unknown"


# Governor haritasi: durum → governor
GOVERNOR_MAP = {
    PrinterState.IDLE: "schedutil",
    PrinterState.PRINTING: "performance",
    PrinterState.PAUSED: "ondemand",
}


# ─── Governor Kontrolu ───────────────────────────────────────────────────────

def get_available_governors() -> list[str]:
    """Mevcut CPU governor'lari."""
    try:
        path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors")
        if path.exists():
            return path.read_text().strip().split()
    except Exception:
        pass
    return []


def get_current_governor() -> str:
    """Aktif CPU governor."""
    try:
        path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
        if path.exists():
            return path.read_text().strip()
    except Exception:
        pass
    return "unknown"


def set_governor(governor: str) -> bool:
    """Tum CPU'larda governor ayarla."""
    try:
        cpufreq = Path("/sys/devices/system/cpu")
        for cpu_dir in sorted(cpufreq.glob("cpu[0-9]*")):
            gov_file = cpu_dir / "cpufreq" / "scaling_governor"
            if gov_file.exists():
                gov_file.write_text(governor)
        logger.info("CPU governor → %s", governor)
        return True
    except PermissionError:
        # cpufreq-set fallback
        try:
            subprocess.run(
                ["cpufreq-set", "-g", governor, "-r"],
                capture_output=True, timeout=5,
            )
            return True
        except Exception:
            pass
    except Exception as e:
        logger.error("Governor ayarlanamadi: %s", e)
    return False


# ─── CPU Sicaklik Okuma ──────────────────────────────────────────────────────

def read_cpu_temperature() -> float:
    """CPU sicakligini oku (derece C). Bulunamazsa -1."""
    # thermal_zone0 (genellikle CPU)
    try:
        path = Path("/sys/class/thermal/thermal_zone0/temp")
        if path.exists():
            raw = int(path.read_text().strip())
            return raw / 1000.0 if raw > 1000 else float(raw)
    except Exception:
        pass

    # RPi vcgencmd fallback
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            # temp=45.0'C
            temp_str = result.stdout.strip().replace("temp=", "").replace("'C", "")
            return float(temp_str)
    except Exception:
        pass

    return -1.0


# ─── Ana Sinif ───────────────────────────────────────────────────────────────

class AIResourceManager:
    """AI tabanli sistem kaynak yoneticisi."""

    HISTORY_SIZE = 60  # Son 60 veri noktasi (2sn aralık = 2 dakika)

    def __init__(self, policy: Optional[ResourcePolicy] = None):
        self.policy = policy or ResourcePolicy()
        self._running = False
        self._current_governor = "unknown"
        self._thermal_override = False
        self._last_camera_fps = 15
        self._action_log: list[dict] = []
        self._metrics_history: deque[SystemMetrics] = deque(maxlen=self.HISTORY_SIZE)
        self._printer_state = PrinterState.UNKNOWN

    # --- Metrik Toplama ---

    def collect_metrics(self) -> SystemMetrics:
        """Sistem metriklerini topla."""
        m = SystemMetrics(timestamp=time.time())

        if psutil is not None:
            m.cpu_percent = psutil.cpu_percent(interval=0)
            m.cpu_per_core = psutil.cpu_percent(percpu=True)
            mem = psutil.virtual_memory()
            m.memory_percent = mem.percent
            m.memory_available_mb = int(mem.available / 1024 / 1024)
            try:
                m.load_avg_1m = os.getloadavg()[0]
            except (OSError, AttributeError):
                m.load_avg_1m = 0.0

        m.cpu_temperature = read_cpu_temperature()
        self._metrics_history.append(m)
        return m

    # --- Yazici Durumu ---

    def _get_printer_state(self) -> PrinterState:
        """Moonraker'dan yazici durumunu al."""
        if requests is None:
            return PrinterState.UNKNOWN
        try:
            resp = requests.get(
                f"{MOONRAKER_URL}/printer/objects/query",
                params={"print_stats": "state"},
                timeout=3,
            )
            resp.raise_for_status()
            state_str = (
                resp.json()
                .get("result", {})
                .get("status", {})
                .get("print_stats", {})
                .get("state", "standby")
            )
            mapping = {
                "printing": PrinterState.PRINTING,
                "paused": PrinterState.PAUSED,
                "standby": PrinterState.IDLE,
                "complete": PrinterState.IDLE,
                "cancelled": PrinterState.IDLE,
                "error": PrinterState.IDLE,
            }
            return mapping.get(state_str, PrinterState.UNKNOWN)
        except Exception:
            return PrinterState.UNKNOWN

    # --- Degerlendirme ---

    def evaluate(self, m: SystemMetrics) -> list[tuple[ResourceAction, dict]]:
        """Metrikleri degerlendir, aksiyon listesi dondur."""
        actions: list[tuple[ResourceAction, dict]] = []
        self._printer_state = self._get_printer_state()

        # 1. Termal kontrol (en yuksek oncelik)
        if m.cpu_temperature > 0:
            if m.cpu_temperature >= self.policy.cpu_temp_critical:
                if not self._thermal_override:
                    actions.append((ResourceAction.SET_GOVERNOR, {"governor": "powersave"}))
                    actions.append((ResourceAction.THROTTLE_CAMERA, {"fps": 1}))
                    actions.append((ResourceAction.NOTIFY, {
                        "message": f"TERMAL KRITIK: CPU {m.cpu_temperature:.0f}°C! "
                                   f"Powersave mod aktif, kamera 1fps."
                    }))
                    self._thermal_override = True
            elif m.cpu_temperature >= self.policy.cpu_temp_warning:
                if not self._thermal_override:
                    actions.append((ResourceAction.NOTIFY, {
                        "message": f"Termal uyari: CPU {m.cpu_temperature:.0f}°C"
                    }))
            else:
                # Sicaklik normal — override kaldir
                if self._thermal_override:
                    self._thermal_override = False
                    actions.append((ResourceAction.THROTTLE_CAMERA, {"fps": 15}))
                    actions.append((ResourceAction.NOTIFY, {
                        "message": f"Termal normal: CPU {m.cpu_temperature:.0f}°C — "
                                   f"performans modu geri yuklendi"
                    }))

        # 2. Governor ayarla (termal override yoksa)
        if not self._thermal_override:
            target_gov = GOVERNOR_MAP.get(self._printer_state, "schedutil")
            if target_gov != self._current_governor:
                actions.append((ResourceAction.SET_GOVERNOR, {"governor": target_gov}))

        # 3. Bellek kontrolu
        if m.memory_percent >= self.policy.memory_critical_pct:
            actions.append((ResourceAction.MEMORY_RELIEF, {}))
            actions.append((ResourceAction.THROTTLE_CAMERA, {"fps": 1}))
            actions.append((ResourceAction.NOTIFY, {
                "message": f"BELLEK KRITIK: %{m.memory_percent:.0f} kullanımda! "
                           f"Cache temizlendi, kamera 1fps."
            }))
        elif m.memory_percent >= self.policy.memory_warning_pct:
            actions.append((ResourceAction.NOTIFY, {
                "message": f"Bellek uyari: %{m.memory_percent:.0f} kullanımda"
            }))

        return actions

    # --- Aksiyon Uygulama ---

    def apply_actions(self, actions: list[tuple[ResourceAction, dict]]):
        """Aksiyonlari uygula."""
        for action, params in actions:
            try:
                if action == ResourceAction.SET_GOVERNOR:
                    gov = params["governor"]
                    if set_governor(gov):
                        self._current_governor = gov

                elif action == ResourceAction.THROTTLE_CAMERA:
                    fps = params["fps"]
                    self._set_camera_fps(fps)
                    self._last_camera_fps = fps

                elif action == ResourceAction.MEMORY_RELIEF:
                    self._emergency_memory_relief()

                elif action == ResourceAction.NOTIFY:
                    self._send_notification(params["message"])

                self._action_log.append({
                    "time": time.time(),
                    "action": action.value,
                    "params": params,
                })
            except Exception as e:
                logger.error("Aksiyon hatasi (%s): %s", action.value, e)

        # Son 100 aksiyonu tut
        if len(self._action_log) > 100:
            self._action_log = self._action_log[-100:]

    def _set_camera_fps(self, fps: int):
        """Crowsnest kamera FPS ayarla (crowsnest.conf uzerinden)."""
        conf_path = Path("/home/klipper/printer_data/config/crowsnest.conf")
        if not conf_path.exists():
            return
        try:
            content = conf_path.read_text()
            import re
            new_content = re.sub(
                r"^max_fps:\s*\d+",
                f"max_fps: {fps}",
                content,
                flags=re.MULTILINE,
            )
            if new_content != content:
                conf_path.write_text(new_content)
                # Crowsnest restart
                subprocess.run(
                    ["systemctl", "restart", "crowsnest"],
                    capture_output=True, timeout=10,
                )
                logger.info("Kamera FPS → %d", fps)
        except Exception as e:
            logger.warning("Kamera FPS ayarlanamadi: %s", e)

    def _emergency_memory_relief(self):
        """Acil bellek kurtarma: cache drop + earlyoom tetikle."""
        try:
            # Sync + drop caches
            subprocess.run(["sync"], timeout=5)
            Path("/proc/sys/vm/drop_caches").write_text("3")
            logger.warning("Acil bellek kurtarma: cache drop yapildi")
        except Exception as e:
            logger.error("Cache drop hatasi: %s", e)

    def _send_notification(self, message: str):
        """Moonraker bildirim gonder."""
        if requests is None:
            return
        try:
            requests.post(
                f"{MOONRAKER_URL}/server/notifications/create",
                json={"title": "KlipperOS-AI Resource Manager", "message": message},
                timeout=3,
            )
        except Exception:
            pass
        logger.info("Bildirim: %s", message)

    # --- Durum Raporu ---

    @property
    def status(self) -> dict:
        """Mevcut durum ozeti."""
        latest = self._metrics_history[-1] if self._metrics_history else SystemMetrics()
        return {
            "governor": self._current_governor,
            "printer_state": self._printer_state.value,
            "thermal_override": self._thermal_override,
            "camera_fps": self._last_camera_fps,
            "metrics": latest.to_dict(),
            "policy": {
                "memory_warning_pct": self.policy.memory_warning_pct,
                "memory_critical_pct": self.policy.memory_critical_pct,
                "cpu_temp_warning": self.policy.cpu_temp_warning,
                "cpu_temp_critical": self.policy.cpu_temp_critical,
            },
        }

    @property
    def history(self) -> list[dict]:
        """Son 60 metrik noktasi."""
        return [m.to_dict() for m in self._metrics_history]

    @property
    def recent_actions(self) -> list[dict]:
        """Son aksiyonlar."""
        return self._action_log[-20:]

    # --- Ana Dongu ---

    def run(self):
        """Daemon ana dongusu."""
        logger.info("=" * 50)
        logger.info("KlipperOS-AI Resource Manager baslatiliyor")
        logger.info("  Moonraker: %s", MOONRAKER_URL)
        logger.info("  Aralik:    %d saniye", RESOURCE_INTERVAL)
        logger.info("  Policy:    mem_warn=%.0f%%, mem_crit=%.0f%%, "
                     "temp_warn=%.0f°C, temp_crit=%.0f°C",
                     self.policy.memory_warning_pct,
                     self.policy.memory_critical_pct,
                     self.policy.cpu_temp_warning,
                     self.policy.cpu_temp_critical)
        logger.info("=" * 50)

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self._current_governor = get_current_governor()
        logger.info("Baslangic governor: %s", self._current_governor)

        self._running = True
        while self._running:
            try:
                metrics = self.collect_metrics()
                actions = self.evaluate(metrics)
                if actions:
                    self.apply_actions(actions)
            except Exception as e:
                logger.error("Kontrol dongusu hatasi: %s", e)

            time.sleep(RESOURCE_INTERVAL)

    def _signal_handler(self, signum, frame):
        logger.info("Sinyal alindi (%s). Resource Manager durduruluyor...", signum)
        self._running = False


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main():
    manager = AIResourceManager()
    manager.run()


if __name__ == "__main__":
    main()

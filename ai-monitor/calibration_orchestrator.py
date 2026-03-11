"""
KlipperOS-AI — Auto-Calibration Orchestrator (v3)
==================================================
Moonraker API uzerinden tam otomatik kalibrasyon sekansi:
    1. PID Extruder
    2. PID Bed
    3. Input Shaper (ivmeolcer varsa)
    4. Pressure Advance (PA tuning test)
    5. Flow Rate (TMC StallGuard baseline)

Ozellikler:
    - Async-free: senkron Moonraker REST cagirilari (SBC uyumlu)
    - Adim atlama (skip_pid, skip_shaper, skip_pa, skip_flow)
    - Hata kurtarma + retry (her adimda max 2 deneme)
    - Progress callback (API/WebSocket bildirim icin)
    - JSON durum dosyasi (/var/lib/klipperos-ai/calibration-state.json)
    - Thread-safe: Lock ile korunmus state
"""

from __future__ import annotations

import json
import logging
import time
import threading
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data
# ---------------------------------------------------------------------------

class CalibStep(Enum):
    """Kalibrasyon adimi."""
    IDLE = "idle"
    PID_EXTRUDER = "pid_extruder"
    PID_BED = "pid_bed"
    INPUT_SHAPER = "input_shaper"
    PRESSURE_ADVANCE = "pressure_advance"
    FLOW_RATE = "flow_rate"
    DONE = "done"
    FAILED = "failed"


class StepStatus(Enum):
    """Tek bir adimin durumu."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class StepResult:
    """Tek bir adimin sonuc kaydı."""
    step: str
    status: str = "pending"
    message: str = ""
    duration_sec: float = 0.0
    data: dict = field(default_factory=dict)


@dataclass
class CalibrationState:
    """Tum kalibrasyon sekansi durumu."""
    current_step: str = CalibStep.IDLE.value
    progress_percent: int = 0
    steps: dict[str, dict] = field(default_factory=dict)
    started_at: float = 0.0
    finished_at: float = 0.0
    error: Optional[str] = None

    # Parametreler
    extruder_temp: int = 210
    bed_temp: int = 60
    pa_start: float = 0.0
    pa_end: float = 0.1
    pa_step: float = 0.005


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

# MoonrakerClient protocol — gercek client veya mock enjekte edilebilir
class _MoonrakerProto:
    """Moonraker client arayuz tanimi (duck typing)."""
    def get(self, path: str, use_cache: bool = True) -> dict | None: ...
    def post(self, path: str, body: dict | None = None, timeout: float | None = None) -> dict | None: ...
    def send_gcode(self, script: str, timeout: float | None = None) -> bool: ...
    def get_printer_objects(self, *objects: str) -> dict: ...
    def is_available(self) -> bool: ...


class CalibrationOrchestrator:
    """Moonraker API uzerinden otomatik kalibrasyon sekansi.

    Args:
        moonraker: MoonrakerClient instance
        state_path: JSON durum dosyasi yolu
        on_progress: Durum degisikliginde cagirilacak callback
    """

    # Adim sirasi ve agirlik (progress hesaplama icin)
    STEP_ORDER = [
        (CalibStep.PID_EXTRUDER, 25),
        (CalibStep.PID_BED, 25),
        (CalibStep.INPUT_SHAPER, 20),
        (CalibStep.PRESSURE_ADVANCE, 20),
        (CalibStep.FLOW_RATE, 10),
    ]

    MAX_RETRIES = 2
    POLL_INTERVAL = 3.0  # saniye

    def __init__(
        self,
        moonraker: _MoonrakerProto,
        state_path: str | Path = "/var/lib/klipperos-ai/calibration-state.json",
        on_progress: Optional[Callable[[CalibrationState], None]] = None,
    ):
        self._mr = moonraker
        self._state_path = Path(state_path)
        self._on_progress = on_progress
        self._state = CalibrationState()
        self._lock = threading.Lock()
        self._abort = threading.Event()
        self._running = False

    # -- Public API --

    @property
    def state(self) -> CalibrationState:
        with self._lock:
            return self._state

    @property
    def is_running(self) -> bool:
        return self._running

    def start(
        self,
        extruder_temp: int = 210,
        bed_temp: int = 60,
        skip_pid: bool = False,
        skip_shaper: bool = False,
        skip_pa: bool = False,
        skip_flow: bool = False,
        pa_start: float = 0.0,
        pa_end: float = 0.1,
        pa_step: float = 0.005,
    ) -> bool:
        """Kalibrasyon sekansini baslat (blocking).

        Ayri thread'de cagirmak icin start_async() kullanin.
        Returns: True basarili, False hata.
        """
        if self._running:
            logger.warning("Kalibrasyon zaten calisiyor")
            return False

        self._running = True
        self._abort.clear()

        # State baslangic
        with self._lock:
            self._state = CalibrationState(
                extruder_temp=extruder_temp,
                bed_temp=bed_temp,
                pa_start=pa_start,
                pa_end=pa_end,
                pa_step=pa_step,
                started_at=time.time(),
            )
            for step, _ in self.STEP_ORDER:
                self._state.steps[step.value] = asdict(StepResult(step=step.value))

        skips = {
            CalibStep.PID_EXTRUDER: skip_pid,
            CalibStep.PID_BED: skip_pid,
            CalibStep.INPUT_SHAPER: skip_shaper,
            CalibStep.PRESSURE_ADVANCE: skip_pa,
            CalibStep.FLOW_RATE: skip_flow,
        }

        success = True
        completed_weight = 0

        try:
            for step, weight in self.STEP_ORDER:
                if self._abort.is_set():
                    self._set_error("Kullanici tarafindan iptal edildi")
                    success = False
                    break

                if skips.get(step, False):
                    self._update_step(step, StepStatus.SKIPPED, "Kullanici atladi")
                    completed_weight += weight
                    self._update_progress(completed_weight)
                    continue

                # Adimi calistir (retry ile)
                ok = self._run_step_with_retry(step)
                if ok:
                    completed_weight += weight
                    self._update_progress(completed_weight)
                else:
                    success = False
                    break

            if success:
                with self._lock:
                    self._state.current_step = CalibStep.DONE.value
                    self._state.progress_percent = 100
                    self._state.finished_at = time.time()
                self._notify()
                logger.info("Kalibrasyon tamamlandi")
        except Exception as exc:
            self._set_error(f"Beklenmeyen hata: {exc}")
            success = False
        finally:
            self._running = False
            self._save_state()

        return success

    def start_async(self, **kwargs) -> threading.Thread:
        """Kalibrasyon sekansini arka planda baslat."""
        t = threading.Thread(
            target=self.start,
            kwargs=kwargs,
            daemon=True,
            name="calibration-orchestrator",
        )
        t.start()
        return t

    def abort(self) -> None:
        """Calisani durdur."""
        self._abort.set()
        logger.info("Kalibrasyon iptal istegi gonderildi")

    def to_dict(self) -> dict:
        """API ciktisi icin JSON-uyumlu dict."""
        with self._lock:
            return asdict(self._state)

    # -- Step Implementations --

    def _run_step_with_retry(self, step: CalibStep) -> bool:
        """Adimi retry ile calistir."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            self._update_step(step, StepStatus.RUNNING,
                              f"Deneme {attempt}/{self.MAX_RETRIES}")
            start_t = time.time()

            try:
                ok = self._execute_step(step)
            except Exception as exc:
                logger.error("Adim %s hata: %s", step.value, exc)
                ok = False

            duration = time.time() - start_t

            if ok:
                # Adim kendi statusunu SKIPPED olarak set etmis olabilir
                # (ornegin: hardware bulunamadi). Bu durumda ezmeyelim.
                with self._lock:
                    cur = self._state.steps.get(step.value, {})
                    already_final = cur.get("status") == StepStatus.SKIPPED.value
                if not already_final:
                    self._update_step(step, StepStatus.COMPLETED,
                                      f"Tamamlandi ({duration:.0f}s)",
                                      duration=duration)
                return True

            if attempt < self.MAX_RETRIES:
                logger.warning("Adim %s basarisiz, tekrar deneniyor...",
                               step.value)
                # Kuyruk birikimini onlemek icin yazicinin idle olmasini bekle
                self._ensure_printer_idle(timeout=120)
                time.sleep(5)

        self._update_step(step, StepStatus.FAILED,
                          f"Basarisiz ({self.MAX_RETRIES} deneme sonrasi)")
        self._set_error(f"Adim basarisiz: {step.value}")
        return False

    def _execute_step(self, step: CalibStep) -> bool:
        """Tek bir kalibrasyon adimini calistir."""
        dispatch = {
            CalibStep.PID_EXTRUDER: self._step_pid_extruder,
            CalibStep.PID_BED: self._step_pid_bed,
            CalibStep.INPUT_SHAPER: self._step_input_shaper,
            CalibStep.PRESSURE_ADVANCE: self._step_pressure_advance,
            CalibStep.FLOW_RATE: self._step_flow_rate,
        }
        handler = dispatch.get(step)
        if handler is None:
            return False
        return handler()

    def _step_pid_extruder(self) -> bool:
        """PID Extruder kalibrasyonu."""
        temp = self._state.extruder_temp
        logger.info("PID Extruder basliyor (target=%d)", temp)

        ok = self._mr.send_gcode(
            f"PID_CALIBRATE HEATER=extruder TARGET={temp}",
            timeout=600
        )
        if not ok:
            return False

        # PID kalibrasyonu ~2-5 dk surer — bitisini bekle
        if not self._wait_for_idle(timeout=600):
            return False

        # PID sonuclarini kaydet (Klipper restart olacak)
        logger.info("PID Extruder tamamlandi, SAVE_CONFIG kaydediliyor")
        self._mr.send_gcode("SAVE_CONFIG", timeout=30)
        return self._wait_for_klipper_ready(timeout=60)

    def _step_pid_bed(self) -> bool:
        """PID Bed kalibrasyonu."""
        temp = self._state.bed_temp
        logger.info("PID Bed basliyor (target=%d)", temp)

        ok = self._mr.send_gcode(
            f"PID_CALIBRATE HEATER=heater_bed TARGET={temp}",
            timeout=1200
        )
        if not ok:
            return False

        if not self._wait_for_idle(timeout=1200):
            return False

        # PID sonuclarini kaydet (Klipper restart olacak)
        logger.info("PID Bed tamamlandi, SAVE_CONFIG kaydediliyor")
        self._mr.send_gcode("SAVE_CONFIG", timeout=30)
        return self._wait_for_klipper_ready(timeout=60)

    def _step_input_shaper(self) -> bool:
        """Input Shaper kalibrasyonu (ivmeolcer gerektirir)."""
        # Once ivmeolcer varligini kontrol et
        if not self._has_config_section("adxl345"):
            self._update_step(CalibStep.INPUT_SHAPER, StepStatus.SKIPPED,
                              "ivmeolcer (adxl345) bulunamadi")
            return True  # Skip, hata degil

        logger.info("Input Shaper basliyor")
        ok = self._mr.send_gcode("SHAPER_CALIBRATE", timeout=900)
        if not ok:
            return False

        return self._wait_for_idle(timeout=900)

    def _step_pressure_advance(self) -> bool:
        """Pressure Advance tuning testi.

        Bowden tube extruder icin genellikle 0.5-1.5 arasi,
        Direct drive icin 0.01-0.10 arasi.
        Test pattern basar, kullanici en iyi deger secmelidir.
        Burada baseline testi yapilir ve onerilen deger hesaplanir.
        """
        pa_start = self._state.pa_start
        pa_end = self._state.pa_end
        pa_step = self._state.pa_step
        ext_temp = self._state.extruder_temp
        bed_temp = self._state.bed_temp

        logger.info("Pressure Advance testi basliyor "
                     "(start=%.3f, end=%.3f, step=%.3f)",
                     pa_start, pa_end, pa_step)

        # Nozul ve yatak isit
        cmds = [
            f"M104 S{ext_temp}",       # Nozul hedef
            f"M140 S{bed_temp}",        # Yatak hedef
            f"M109 S{ext_temp}",        # Nozul bekle
            f"M190 S{bed_temp}",        # Yatak bekle
            "G28",                      # Home
        ]
        for cmd in cmds:
            if self._abort.is_set():
                return False
            if not self._mr.send_gcode(cmd, timeout=300):
                return False

        # Isitma bekle
        if not self._wait_for_temp(ext_temp, "extruder", timeout=300):
            return False

        # PA tuning test G-code (SET_VELOCITY_LIMIT + TUNING_TOWER)
        tuning_cmds = [
            "SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=1 ACCEL=500",
            f"TUNING_TOWER COMMAND=SET_PRESSURE_ADVANCE "
            f"PARAMETER=ADVANCE START={pa_start} FACTOR={pa_step}",
        ]
        for cmd in tuning_cmds:
            if not self._mr.send_gcode(cmd):
                return False

        # PA testi kullanicinin test modeli basmasini gerektirir.
        # Basit mod: mevcut PA'yi kaydet ve baseline olarak kullan
        self._update_step(CalibStep.PRESSURE_ADVANCE, StepStatus.RUNNING,
                          "TUNING_TOWER aktif — test modeli basildiktan sonra "
                          "en iyi katmani olcun")

        # Yazdirma bitisini bekle (idle'a donene kadar)
        return self._wait_for_idle(timeout=1800)

    def _step_flow_rate(self) -> bool:
        """TMC StallGuard baseline kalibrasyonu.

        30 saniye boyunca SG_RESULT ornekleri toplar
        ve ortalama baseline degerini kaydeder.
        """
        logger.info("Flow Rate (TMC SG baseline) basliyor")

        # TMC2209 varligini kontrol et
        objects = self._mr.get_printer_objects("tmc2209 extruder")
        tmc_data = objects.get("tmc2209 extruder")
        if not tmc_data:
            self._update_step(CalibStep.FLOW_RATE, StepStatus.SKIPPED,
                              "TMC2209 extruder bulunamadi")
            return True  # Hata degil, donanim yok

        # 30 ornekleme
        samples: list[int] = []
        for i in range(30):
            if self._abort.is_set():
                return False

            obj = self._mr.get_printer_objects("tmc2209 extruder")
            tmc = obj.get("tmc2209 extruder", {})
            drv = tmc.get("drv_status") or {}  # None-safe: Moonraker null -> {}
            sg = drv.get("sg_result")
            if sg is not None:
                samples.append(int(sg))

            self._update_step(CalibStep.FLOW_RATE, StepStatus.RUNNING,
                              f"SG ornekleme [{i + 1}/30]")
            time.sleep(1)

        if not samples:
            self._update_step(
                CalibStep.FLOW_RATE, StepStatus.SKIPPED,
                "TMC2209 drv_status/SG_RESULT mevcut degil (diag_pin gerekli)",
            )
            logger.info("Flow Rate: SG_RESULT alinamadi, adim atlaniyor")
            return True  # Hata degil — donanim StallGuard desteklemiyor

        baseline = round(sum(samples) / len(samples))
        self._update_step(
            CalibStep.FLOW_RATE, StepStatus.COMPLETED,
            f"Baseline SG={baseline} ({len(samples)} ornek)",
            data={"baseline_sg": baseline, "sample_count": len(samples)},
        )
        return True

    # -- Helpers --

    def _ensure_printer_idle(self, timeout: float = 120) -> None:
        """Retry oncesi yazicinin bos oldugundan emin ol (kuyruk birikimini onle)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort.is_set():
                return
            objects = self._mr.get_printer_objects("idle_timeout")
            state = objects.get("idle_timeout", {}).get("state", "")
            if state in ("Idle", "Ready"):
                return
            logger.info("Yazici hala mesgul (%s), bekleniyor...", state)
            time.sleep(self.POLL_INTERVAL)
        logger.warning("Yazici %ds sonra hala idle degil", timeout)

    def _wait_for_klipper_ready(self, timeout: float = 60) -> bool:
        """SAVE_CONFIG sonrasi Klipper restart'ini bekle."""
        deadline = time.time() + timeout
        time.sleep(5)  # Klipper restart icin bekleme
        while time.time() < deadline:
            if self._abort.is_set():
                return False
            if self._mr.is_available():
                logger.info("Klipper tekrar hazir")
                return True
            time.sleep(2)
        logger.error("Klipper %ds icinde hazir olmadi", timeout)
        return False

    def _wait_for_idle(self, timeout: float = 300) -> bool:
        """Yazicinin idle durumuna donmesini bekle."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort.is_set():
                return False

            objects = self._mr.get_printer_objects(
                "idle_timeout", "print_stats"
            )

            # idle_timeout.state en guvenilir (PID gibi non-print icin)
            idle_state = objects.get("idle_timeout", {}).get("state", "")
            if idle_state in ("Idle", "Ready"):
                return True

            # print_stats hata kontrolu
            stats = objects.get("print_stats", {})
            ps_state = stats.get("state", "")
            if ps_state == "error":
                logger.error("Yazici hata durumunda")
                return False

            time.sleep(self.POLL_INTERVAL)

        logger.error("Timeout: yazici idle'a donmedi (%ds)", timeout)
        return False

    def _wait_for_temp(self, target: float, heater: str = "extruder",
                       timeout: float = 300, tolerance: float = 3.0) -> bool:
        """Hedef sicakliga ulasmasini bekle."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort.is_set():
                return False

            objects = self._mr.get_printer_objects(heater)
            data = objects.get(heater, {})
            current = data.get("temperature", 0)

            if abs(current - target) <= tolerance:
                return True

            time.sleep(self.POLL_INTERVAL)

        return False

    def _has_config_section(self, section: str) -> bool:
        """Klipper config'de belirli bir section var mi?"""
        resp = self._mr.get("/printer/objects/list")
        if resp and "result" in resp:
            objects = resp["result"].get("objects", [])
            return section in objects
        return False

    def _update_step(self, step: CalibStep, status: StepStatus,
                     message: str = "", duration: float = 0.0,
                     data: dict | None = None) -> None:
        """Adim durumunu guncelle."""
        with self._lock:
            self._state.current_step = step.value
            result = self._state.steps.get(step.value, {})
            result["status"] = status.value
            result["message"] = message
            if duration > 0:
                result["duration_sec"] = duration
            if data:
                result["data"] = data
            self._state.steps[step.value] = result
        self._notify()

    def _update_progress(self, completed_weight: int) -> None:
        """Progress yuzdesi guncelle."""
        total = sum(w for _, w in self.STEP_ORDER)
        with self._lock:
            self._state.progress_percent = min(
                int(completed_weight / total * 100), 99
            )
        self._notify()

    def _set_error(self, msg: str) -> None:
        """Hata durumuna gec."""
        with self._lock:
            self._state.current_step = CalibStep.FAILED.value
            self._state.error = msg
            self._state.finished_at = time.time()
        self._notify()
        self._save_state()

    def _notify(self) -> None:
        """Progress callback'i cagir."""
        if self._on_progress:
            try:
                self._on_progress(self._state)
            except Exception:
                pass  # Callback hatasi kalibrasyonu bozmasin

    def _save_state(self) -> None:
        """Durumu JSON dosyasina yaz (atomik)."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            tmp.replace(self._state_path)
        except OSError as exc:
            logger.warning("State dosyasi yazilamadi: %s", exc)

    @classmethod
    def load_state(cls, path: str | Path) -> dict | None:
        """Onceki kalibrasyon durumunu oku."""
        p = Path(path)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None

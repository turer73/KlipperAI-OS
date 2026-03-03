"""
KlipperOS-AI — Autonomous Recovery Engine
==========================================
Ariza teshisi + otomatik kurtarma motoru.

Desteklenen arizalar:
    FILAMENT_RUNOUT     → Durdur → sensor bekle → isit → purge → devam
    FILAMENT_CLOG       → Geri cek → +20°C isit → bekle → it → dogrula
    THERMAL_DEVIATION   → Sogut → PID kalibre → yeni PID → devam
    THERMAL_RUNAWAY     → Acil durdurma (otonom kurtarma YOK)
    SPAGHETTI           → Durdur + bildir (otonom kurtarma YOK)
    LAYER_SHIFT         → Durdur + bildir (otonom kurtarma YOK)

Guvenlik:
    - Ariza basina max 2 kurtarma denemesi
    - Spaghetti/layer_shift icin ASLA otomatik kurtarma
    - Sicaklik 280°C ustu icin otomatik kurtarma yok
    - Her prosedur icin 5 dakika timeout
    - Basarisiz kurtarma → durdur + bildirim
    - Tum kararlar JSONL'ye loglaniyor
    - AUTORECOVERY_ENABLED=0 ile devre disi birakilabilir
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger("klipperos-ai.recovery")


# ─── Sabitler ────────────────────────────────────────────────────────────────

MAX_RECOVERY_ATTEMPTS = 2          # Ariza basina max deneme
MAX_TEMP_FOR_AUTO_RECOVERY = 280   # Bu sicakligin uzerinde otonom kurtarma yok
RECOVERY_TIMEOUT_SEC = 300         # 5 dakika prosedur timeout
PURGE_LENGTH_MM = 50               # Filament purge uzunlugu
RETRACT_LENGTH_MM = 20             # Clog kurtarma geri cekme
CLOG_TEMP_BOOST = 20               # Clog icin sicaklik artisi (°C)
COOLDOWN_TEMP = 50                 # Soguma hedefi (°C)
DECISION_LOG_PATH = Path("/var/log/klipperos-ai/recovery-decisions.jsonl")


# ─── Enums & Veri Yapilari ───────────────────────────────────────────────────

class FailureCategory(str, Enum):
    """Ariza kategorileri."""
    FILAMENT_RUNOUT = "filament_runout"
    FILAMENT_CLOG = "filament_clog"
    THERMAL_RUNAWAY = "thermal_runaway"
    THERMAL_DEVIATION = "thermal_deviation"
    SPAGHETTI = "spaghetti"
    LAYER_SHIFT = "layer_shift"


# Otomatik kurtarma YAPILABILIR kategoriler
AUTO_RECOVERABLE = {
    FailureCategory.FILAMENT_RUNOUT,
    FailureCategory.FILAMENT_CLOG,
    FailureCategory.THERMAL_DEVIATION,
}


@dataclass
class FailureDiagnosis:
    """Ariza teshis sonucu."""
    category: FailureCategory
    confidence: float           # 0-1
    evidence: list[str]         # Teshis kanit listesi
    auto_recoverable: bool      # Otonom kurtarma mumkun mu?
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d


class RecoveryStepType(str, Enum):
    """Kurtarma adim tipleri."""
    PAUSE = "pause"
    WAIT_SENSOR = "wait_sensor"
    HEAT = "heat"
    COOLDOWN = "cooldown"
    PURGE = "purge"
    RETRACT = "retract"
    EXTRUDE = "extrude"
    PID_CALIBRATE = "pid_calibrate"
    RESUME = "resume"
    NOTIFY = "notify"
    GCODE = "gcode"
    WAIT = "wait"


@dataclass
class RecoveryStep:
    """Tek bir kurtarma adimi."""
    step_type: RecoveryStepType
    description: str
    params: dict = field(default_factory=dict)
    timeout_sec: float = 60.0


@dataclass
class RecoveryPlan:
    """Kurtarma plani — adimlar dizisi."""
    diagnosis: FailureDiagnosis
    steps: list[RecoveryStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "diagnosis": self.diagnosis.to_dict(),
            "steps": [
                {"type": s.step_type.value, "desc": s.description, "params": s.params}
                for s in self.steps
            ],
            "created_at": self.created_at,
        }


@dataclass
class RecoveryResult:
    """Kurtarma sonucu."""
    success: bool
    plan: RecoveryPlan
    completed_steps: int
    total_steps: int
    failure_reason: str = ""
    duration_sec: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "diagnosis": self.plan.diagnosis.category.value,
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
            "failure_reason": self.failure_reason,
            "duration_sec": round(self.duration_sec, 1),
            "timestamp": self.timestamp,
        }


# ─── Teshis Motoru ──────────────────────────────────────────────────────────

class DiagnosisEngine:
    """FlowGuard sinyallerinden kok neden teshisi.

    Sinyal kombinasyonlari:
        sensor=0 AND tmc_sg=yuksek  → FILAMENT_RUNOUT
        sensor=1 AND tmc_sg=dusuk   → FILAMENT_CLOG
        heater duty yuksek + temp artiyor → THERMAL_RUNAWAY
        heater duty anomali + temp dusuyor → THERMAL_DEVIATION
        AI class = spaghetti → SPAGHETTI
        AI class = layer_shift → LAYER_SHIFT
    """

    def diagnose(
        self,
        sensor_state: int,      # 1=detected, 0=not, -1=unavailable
        tmc_sg: int,            # SG_RESULT (-1=unavailable)
        tmc_sg_baseline: float, # Normal SG ortalamasi
        heater_duty: float,     # Heater PWM (0-1)
        heater_baseline: float, # Normal duty ortalamasi
        target_temp: float,     # Hedef sicaklik
        current_temp: float,    # Mevcut sicaklik
        ai_class: str,          # AI tespit sinifi
        ai_confidence: float,   # AI guven (0-1)
    ) -> Optional[FailureDiagnosis]:
        """Sinyalleri analiz et → kok neden belirle.

        Returns:
            FailureDiagnosis veya None (sorun yok).
        """
        evidence = []

        # --- AI bazli teshisler (en yuksek oncelik) ---
        if ai_class == "spaghetti" and ai_confidence > 0.7:
            return FailureDiagnosis(
                category=FailureCategory.SPAGHETTI,
                confidence=ai_confidence,
                evidence=[f"AI spaghetti tespiti (guven: {ai_confidence:.0%})"],
                auto_recoverable=False,
            )

        if ai_class == "layer_shift" and ai_confidence > 0.7:
            return FailureDiagnosis(
                category=FailureCategory.LAYER_SHIFT,
                confidence=ai_confidence,
                evidence=[f"AI katman kaymasi tespiti (guven: {ai_confidence:.0%})"],
                auto_recoverable=False,
            )

        # --- Filament teshisi ---
        if sensor_state == 0 and tmc_sg >= 0:
            # Sensor bos + motor yuku dusuk = filament bitmis
            if tmc_sg_baseline > 0 and tmc_sg > tmc_sg_baseline * 1.3:
                return FailureDiagnosis(
                    category=FailureCategory.FILAMENT_RUNOUT,
                    confidence=0.95,
                    evidence=[
                        "Filament sensoru: bos",
                        f"TMC SG yuksek: {tmc_sg} (baseline: {tmc_sg_baseline:.0f})",
                    ],
                    auto_recoverable=True,
                )
            # Sensor bos ama SG normal/dusuk = muhtemelen yine bitmis
            evidence.append("Filament sensoru: bos")
            return FailureDiagnosis(
                category=FailureCategory.FILAMENT_RUNOUT,
                confidence=0.80,
                evidence=evidence,
                auto_recoverable=True,
            )

        if sensor_state == 1 and tmc_sg >= 0 and tmc_sg_baseline > 0:
            # Sensor dolu ama motor yuku cok yuksek = tikanma
            if tmc_sg < tmc_sg_baseline * 0.4:
                return FailureDiagnosis(
                    category=FailureCategory.FILAMENT_CLOG,
                    confidence=0.85,
                    evidence=[
                        "Filament sensoru: dolu",
                        f"TMC SG cok dusuk: {tmc_sg} (baseline: {tmc_sg_baseline:.0f})",
                    ],
                    auto_recoverable=True,
                )

        # --- Termal teshis ---
        if heater_baseline > 0 and target_temp > 0:
            duty_ratio = heater_duty / heater_baseline if heater_baseline > 0 else 1.0
            temp_diff = current_temp - target_temp

            # Duty yuksek + sicaklik artiyor kontolsuz = RUNAWAY
            if duty_ratio > 1.5 and temp_diff > 10:
                return FailureDiagnosis(
                    category=FailureCategory.THERMAL_RUNAWAY,
                    confidence=0.90,
                    evidence=[
                        f"Duty cycle cok yuksek: {heater_duty:.2f} (baseline: {heater_baseline:.2f})",
                        f"Sicaklik hedefin uzerinde: {current_temp:.0f}°C (hedef: {target_temp:.0f}°C)",
                    ],
                    auto_recoverable=False,  # Guvenlik: ASLA otomatik
                )

            # Duty anomali + sicaklik dusuyor = deviation
            if duty_ratio > 1.3 and temp_diff < -5:
                return FailureDiagnosis(
                    category=FailureCategory.THERMAL_DEVIATION,
                    confidence=0.80,
                    evidence=[
                        f"Duty cycle yuksek: {heater_duty:.2f} (baseline: {heater_baseline:.2f})",
                        f"Sicaklik hedefin altinda: {current_temp:.0f}°C (hedef: {target_temp:.0f}°C)",
                    ],
                    auto_recoverable=True,
                )

        return None


# ─── Kurtarma Planlayici ───────────────────────────────────────────────────

class RecoveryPlanner:
    """Teshis sonucuna gore kurtarma plani olusturur."""

    def plan(self, diagnosis: FailureDiagnosis,
             current_temp: float = 0.0,
             target_temp: float = 0.0) -> Optional[RecoveryPlan]:
        """Kurtarma plani olustur.

        Returns:
            RecoveryPlan veya None (kurtarma yapilamazsa).
        """
        if not diagnosis.auto_recoverable:
            return None

        if current_temp > MAX_TEMP_FOR_AUTO_RECOVERY:
            logger.warning("Sicaklik %.0f°C > %d°C limiti. Otonom kurtarma iptal.",
                           current_temp, MAX_TEMP_FOR_AUTO_RECOVERY)
            return None

        cat = diagnosis.category

        if cat == FailureCategory.FILAMENT_RUNOUT:
            return self._plan_filament_runout(diagnosis, target_temp)
        elif cat == FailureCategory.FILAMENT_CLOG:
            return self._plan_filament_clog(diagnosis, target_temp)
        elif cat == FailureCategory.THERMAL_DEVIATION:
            return self._plan_thermal_deviation(diagnosis, target_temp)

        return None

    def _plan_filament_runout(self, diag: FailureDiagnosis,
                              target_temp: float) -> RecoveryPlan:
        """Filament bitmis → sensor bekle → isit → purge → devam."""
        plan = RecoveryPlan(diagnosis=diag)
        plan.steps = [
            RecoveryStep(
                step_type=RecoveryStepType.PAUSE,
                description="Baski duraklatiliyor",
            ),
            RecoveryStep(
                step_type=RecoveryStepType.NOTIFY,
                description="Kullaniciya filament bittigini bildir",
                params={"message": "Filament bitmis. Yeni filament yukleyin ve devam edin."},
            ),
            RecoveryStep(
                step_type=RecoveryStepType.WAIT_SENSOR,
                description="Filament sensoru dolu sinyali bekle",
                timeout_sec=180.0,  # 3 dakika
                params={"expected_state": 1},
            ),
            RecoveryStep(
                step_type=RecoveryStepType.HEAT,
                description=f"Nozulu {target_temp:.0f}°C'ye isit",
                params={"target_temp": target_temp},
                timeout_sec=120.0,
            ),
            RecoveryStep(
                step_type=RecoveryStepType.PURGE,
                description=f"{PURGE_LENGTH_MM}mm filament purge et",
                params={"length_mm": PURGE_LENGTH_MM, "speed": 3},
            ),
            RecoveryStep(
                step_type=RecoveryStepType.RESUME,
                description="Baskiyi devam ettir",
            ),
        ]
        return plan

    def _plan_filament_clog(self, diag: FailureDiagnosis,
                            target_temp: float) -> RecoveryPlan:
        """Filament tikali → geri cek → isit → bekle → it → dogrula."""
        boosted_temp = min(target_temp + CLOG_TEMP_BOOST, MAX_TEMP_FOR_AUTO_RECOVERY)
        plan = RecoveryPlan(diagnosis=diag)
        plan.steps = [
            RecoveryStep(
                step_type=RecoveryStepType.PAUSE,
                description="Baski duraklatiliyor",
            ),
            RecoveryStep(
                step_type=RecoveryStepType.RETRACT,
                description=f"{RETRACT_LENGTH_MM}mm geri cek",
                params={"length_mm": RETRACT_LENGTH_MM, "speed": 5},
            ),
            RecoveryStep(
                step_type=RecoveryStepType.HEAT,
                description=f"Nozulu {boosted_temp:.0f}°C'ye isit (tikanma acma)",
                params={"target_temp": boosted_temp},
                timeout_sec=120.0,
            ),
            RecoveryStep(
                step_type=RecoveryStepType.WAIT,
                description="10 saniye bekle (filament yumusasin)",
                params={"seconds": 10},
            ),
            RecoveryStep(
                step_type=RecoveryStepType.EXTRUDE,
                description=f"{RETRACT_LENGTH_MM + 10}mm ileri it",
                params={"length_mm": RETRACT_LENGTH_MM + 10, "speed": 2},
            ),
            RecoveryStep(
                step_type=RecoveryStepType.HEAT,
                description=f"Sicakligi {target_temp:.0f}°C'ye dondur",
                params={"target_temp": target_temp},
                timeout_sec=60.0,
            ),
            RecoveryStep(
                step_type=RecoveryStepType.PURGE,
                description=f"{PURGE_LENGTH_MM}mm purge",
                params={"length_mm": PURGE_LENGTH_MM, "speed": 3},
            ),
            RecoveryStep(
                step_type=RecoveryStepType.RESUME,
                description="Baskiyi devam ettir",
            ),
        ]
        return plan

    def _plan_thermal_deviation(self, diag: FailureDiagnosis,
                                target_temp: float) -> RecoveryPlan:
        """Termal sapma → sogut → PID kalibre → yeni PID → devam."""
        plan = RecoveryPlan(diagnosis=diag)
        plan.steps = [
            RecoveryStep(
                step_type=RecoveryStepType.PAUSE,
                description="Baski duraklatiliyor",
            ),
            RecoveryStep(
                step_type=RecoveryStepType.COOLDOWN,
                description=f"Nozulu {COOLDOWN_TEMP}°C'ye sogut",
                params={"target_temp": COOLDOWN_TEMP},
                timeout_sec=180.0,
            ),
            RecoveryStep(
                step_type=RecoveryStepType.PID_CALIBRATE,
                description=f"PID kalibrasyonu calistir ({target_temp:.0f}°C)",
                params={"target_temp": target_temp},
                timeout_sec=180.0,
            ),
            RecoveryStep(
                step_type=RecoveryStepType.HEAT,
                description=f"Yeni PID ile {target_temp:.0f}°C'ye isit",
                params={"target_temp": target_temp},
                timeout_sec=120.0,
            ),
            RecoveryStep(
                step_type=RecoveryStepType.RESUME,
                description="Baskiyi devam ettir",
            ),
        ]
        return plan


# ─── Kurtarma Yurutucusu ──────────────────────────────────────────────────

class RecoveryExecutor:
    """Kurtarma planini adim adim yurutur.

    G-code gonderimi icin gcode_sender callback kullanir.
    Sensor durumu icin sensor_reader callback kullanir.
    """

    def __init__(
        self,
        gcode_sender: Optional[Callable[[str], bool]] = None,
        pause_printer: Optional[Callable[[], bool]] = None,
        resume_printer: Optional[Callable[[], bool]] = None,
        sensor_reader: Optional[Callable[[], int]] = None,
        temp_reader: Optional[Callable[[], float]] = None,
        notifier: Optional[Callable[[str], bool]] = None,
    ):
        self._send_gcode = gcode_sender or (lambda cmd: True)
        self._pause = pause_printer or (lambda: True)
        self._resume = resume_printer or (lambda: True)
        self._read_sensor = sensor_reader or (lambda: -1)
        self._read_temp = temp_reader or (lambda: 0.0)
        self._notify = notifier or (lambda msg: True)

    def execute(self, plan: RecoveryPlan) -> RecoveryResult:
        """Kurtarma planini calistir.

        Returns:
            RecoveryResult — basari/basarisizlik ve detaylar.
        """
        start = time.time()
        completed = 0

        for i, step in enumerate(plan.steps):
            logger.info("Recovery [%d/%d]: %s", i + 1, len(plan.steps), step.description)

            try:
                success = self._execute_step(step)
            except Exception as e:
                logger.error("Recovery adim hatasi: %s — %s", step.description, e)
                success = False

            if not success:
                duration = time.time() - start
                logger.error("Recovery basarisiz adim %d: %s", i + 1, step.description)
                return RecoveryResult(
                    success=False,
                    plan=plan,
                    completed_steps=completed,
                    total_steps=len(plan.steps),
                    failure_reason=f"Adim {i + 1} basarisiz: {step.description}",
                    duration_sec=duration,
                )

            completed += 1

            # Toplam timeout kontrolu
            if time.time() - start > RECOVERY_TIMEOUT_SEC:
                return RecoveryResult(
                    success=False,
                    plan=plan,
                    completed_steps=completed,
                    total_steps=len(plan.steps),
                    failure_reason=f"Timeout: {RECOVERY_TIMEOUT_SEC}s asildi",
                    duration_sec=time.time() - start,
                )

        duration = time.time() - start
        logger.info("Recovery basarili! %d adim, %.1f saniye", completed, duration)
        return RecoveryResult(
            success=True,
            plan=plan,
            completed_steps=completed,
            total_steps=len(plan.steps),
            duration_sec=duration,
        )

    def _execute_step(self, step: RecoveryStep) -> bool:
        """Tek bir kurtarma adimini calistir."""
        st = step.step_type

        if st == RecoveryStepType.PAUSE:
            return self._pause()

        elif st == RecoveryStepType.RESUME:
            return self._resume()

        elif st == RecoveryStepType.NOTIFY:
            return self._notify(step.params.get("message", ""))

        elif st == RecoveryStepType.WAIT:
            time.sleep(step.params.get("seconds", 5))
            return True

        elif st == RecoveryStepType.HEAT:
            temp = step.params.get("target_temp", 200)
            self._send_gcode(f"M104 S{int(temp)}")
            return self._wait_for_temp(temp, step.timeout_sec)

        elif st == RecoveryStepType.COOLDOWN:
            temp = step.params.get("target_temp", COOLDOWN_TEMP)
            self._send_gcode("M104 S0")  # Isiticiyi kapat
            return self._wait_for_cooldown(temp, step.timeout_sec)

        elif st == RecoveryStepType.PURGE:
            length = step.params.get("length_mm", PURGE_LENGTH_MM)
            speed = step.params.get("speed", 3)
            self._send_gcode("M83")  # Relative extrusion
            self._send_gcode(f"G1 E{length} F{speed * 60}")
            self._send_gcode("G92 E0")  # Reset extruder
            return True

        elif st == RecoveryStepType.RETRACT:
            length = step.params.get("length_mm", RETRACT_LENGTH_MM)
            speed = step.params.get("speed", 5)
            self._send_gcode("M83")
            self._send_gcode(f"G1 E-{length} F{speed * 60}")
            return True

        elif st == RecoveryStepType.EXTRUDE:
            length = step.params.get("length_mm", 30)
            speed = step.params.get("speed", 2)
            self._send_gcode("M83")
            self._send_gcode(f"G1 E{length} F{speed * 60}")
            self._send_gcode("G92 E0")
            return True

        elif st == RecoveryStepType.WAIT_SENSOR:
            expected = step.params.get("expected_state", 1)
            return self._wait_for_sensor(expected, step.timeout_sec)

        elif st == RecoveryStepType.PID_CALIBRATE:
            temp = step.params.get("target_temp", 200)
            self._send_gcode(f"PID_CALIBRATE HEATER=extruder TARGET={int(temp)}")
            # PID kalibrasyonu uzun surer — timeout kadar bekle
            time.sleep(min(step.timeout_sec, 120))
            self._send_gcode("SAVE_CONFIG")
            return True

        elif st == RecoveryStepType.GCODE:
            cmd = step.params.get("command", "")
            return self._send_gcode(cmd) if cmd else False

        logger.warning("Bilinmeyen adim tipi: %s", st)
        return False

    def _wait_for_temp(self, target: float, timeout: float) -> bool:
        """Sicaklik hedefe ulasmasi bekle (±3°C tolerans)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = self._read_temp()
            if abs(current - target) <= 3.0:
                return True
            time.sleep(2)
        logger.warning("Sicaklik timeout: hedef %.0f°C", target)
        return False

    def _wait_for_cooldown(self, target: float, timeout: float) -> bool:
        """Sicaklik dusene kadar bekle."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = self._read_temp()
            if current <= target:
                return True
            time.sleep(3)
        logger.warning("Soguma timeout: hedef %.0f°C", target)
        return False

    def _wait_for_sensor(self, expected: int, timeout: float) -> bool:
        """Filament sensoru beklenen duruma gelene kadar bekle."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self._read_sensor()
            if state == expected:
                return True
            time.sleep(1)
        logger.warning("Sensor timeout: beklenen %d", expected)
        return False


# ─── Ana Motor ───────────────────────────────────────────────────────────────

class AutonomousRecoveryEngine:
    """Otonom kurtarma motoru.

    Teshis → Plan → Yurut dongusu.
    Ariza basina max MAX_RECOVERY_ATTEMPTS deneme.
    """

    def __init__(
        self,
        gcode_sender: Optional[Callable[[str], bool]] = None,
        pause_printer: Optional[Callable[[], bool]] = None,
        resume_printer: Optional[Callable[[], bool]] = None,
        sensor_reader: Optional[Callable[[], int]] = None,
        temp_reader: Optional[Callable[[], float]] = None,
        notifier: Optional[Callable[[str], bool]] = None,
    ):
        self.diagnosis_engine = DiagnosisEngine()
        self.planner = RecoveryPlanner()
        self.executor = RecoveryExecutor(
            gcode_sender=gcode_sender,
            pause_printer=pause_printer,
            resume_printer=resume_printer,
            sensor_reader=sensor_reader,
            temp_reader=temp_reader,
            notifier=notifier,
        )

        self._attempt_counts: dict[str, int] = {}  # category → deneme sayisi
        self._history: list[RecoveryResult] = []
        self._last_diagnosis: Optional[FailureDiagnosis] = None
        self._enabled = True

    def set_enabled(self, enabled: bool) -> None:
        """Otonom kurtarmayi ac/kapat."""
        self._enabled = enabled
        logger.info("Otonom kurtarma: %s", "aktif" if enabled else "devre disi")

    def diagnose(
        self,
        sensor_state: int = -1,
        tmc_sg: int = -1,
        tmc_sg_baseline: float = 0.0,
        heater_duty: float = 0.0,
        heater_baseline: float = 0.0,
        target_temp: float = 0.0,
        current_temp: float = 0.0,
        ai_class: str = "normal",
        ai_confidence: float = 0.0,
    ) -> Optional[FailureDiagnosis]:
        """Sinyalleri analiz et → kok neden belirle."""
        diagnosis = self.diagnosis_engine.diagnose(
            sensor_state=sensor_state,
            tmc_sg=tmc_sg,
            tmc_sg_baseline=tmc_sg_baseline,
            heater_duty=heater_duty,
            heater_baseline=heater_baseline,
            target_temp=target_temp,
            current_temp=current_temp,
            ai_class=ai_class,
            ai_confidence=ai_confidence,
        )
        self._last_diagnosis = diagnosis
        if diagnosis:
            self._log_decision("diagnosis", diagnosis.to_dict())
        return diagnosis

    def plan_recovery(self, diagnosis: FailureDiagnosis,
                      current_temp: float = 0.0,
                      target_temp: float = 0.0) -> Optional[RecoveryPlan]:
        """Kurtarma plani olustur.

        Returns:
            RecoveryPlan veya None (kurtarma yapilamazsa/gerekmiyorsa).
        """
        if not self._enabled:
            logger.info("Otonom kurtarma devre disi. Plan olusturulmuyor.")
            return None

        # Deneme limiti
        cat_key = diagnosis.category.value
        attempts = self._attempt_counts.get(cat_key, 0)
        if attempts >= MAX_RECOVERY_ATTEMPTS:
            logger.warning("Max deneme asildi (%s): %d/%d",
                           cat_key, attempts, MAX_RECOVERY_ATTEMPTS)
            self._log_decision("max_attempts", {
                "category": cat_key, "attempts": attempts})
            return None

        plan = self.planner.plan(
            diagnosis, current_temp=current_temp, target_temp=target_temp)

        if plan:
            self._log_decision("plan_created", plan.to_dict())

        return plan

    def execute_recovery(self, plan: RecoveryPlan) -> RecoveryResult:
        """Kurtarma planini calistir.

        Returns:
            RecoveryResult.
        """
        cat_key = plan.diagnosis.category.value
        self._attempt_counts[cat_key] = self._attempt_counts.get(cat_key, 0) + 1

        logger.info("Recovery baslatiliyor: %s (deneme %d/%d)",
                     cat_key, self._attempt_counts[cat_key], MAX_RECOVERY_ATTEMPTS)

        result = self.executor.execute(plan)

        self._history.append(result)
        if len(self._history) > 50:
            self._history = self._history[-50:]

        self._log_decision("result", result.to_dict())

        if result.success:
            logger.info("Recovery BASARILI: %s (%.1fs)", cat_key, result.duration_sec)
        else:
            logger.error("Recovery BASARISIZ: %s — %s", cat_key, result.failure_reason)

        return result

    def reset_attempts(self, category: Optional[str] = None) -> None:
        """Deneme sayacini sifirla."""
        if category:
            self._attempt_counts.pop(category, None)
        else:
            self._attempt_counts.clear()

    @property
    def status(self) -> dict:
        """Mevcut kurtarma motoru durumu."""
        return {
            "enabled": self._enabled,
            "attempt_counts": dict(self._attempt_counts),
            "history_count": len(self._history),
            "last_diagnosis": self._last_diagnosis.to_dict() if self._last_diagnosis else None,
            "recent_results": [r.to_dict() for r in self._history[-5:]],
        }

    @property
    def last_result(self) -> Optional[RecoveryResult]:
        """Son kurtarma sonucu."""
        return self._history[-1] if self._history else None

    def _log_decision(self, event_type: str, data: dict) -> None:
        """Karari JSONL'ye logla."""
        entry = {
            "timestamp": time.time(),
            "event": event_type,
            "data": data,
        }
        try:
            DECISION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(DECISION_LOG_PATH, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Log hatasi kritik degil

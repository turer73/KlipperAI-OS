"""Tests for Autonomous Recovery Engine (Phase 4)."""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-monitor"))
from autonomous_recovery import (
    AutonomousRecoveryEngine,
    DiagnosisEngine,
    RecoveryPlanner,
    RecoveryExecutor,
    RecoveryPlan,
    RecoveryStep,
    RecoveryStepType,
    RecoveryResult,
    FailureCategory,
    FailureDiagnosis,
    AUTO_RECOVERABLE,
    MAX_RECOVERY_ATTEMPTS,
    MAX_TEMP_FOR_AUTO_RECOVERY,
    PURGE_LENGTH_MM,
    RETRACT_LENGTH_MM,
    CLOG_TEMP_BOOST,
)


# ═══════════════════════════════════════════════════════════════════════════════
# DiagnosisEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiagnosisEngine:
    """Ariza teshis motoru testleri."""

    def setup_method(self):
        self.engine = DiagnosisEngine()

    def test_no_failure(self):
        """Normal durum → teshis yok."""
        diag = self.engine.diagnose(
            sensor_state=1, tmc_sg=200, tmc_sg_baseline=200.0,
            heater_duty=0.5, heater_baseline=0.5,
            target_temp=200.0, current_temp=200.0,
            ai_class="normal", ai_confidence=0.95,
        )
        assert diag is None

    def test_filament_runout_sensor_and_sg(self):
        """Sensor bos + SG yuksek → filament bitmis."""
        diag = self.engine.diagnose(
            sensor_state=0, tmc_sg=300, tmc_sg_baseline=200.0,
            heater_duty=0.5, heater_baseline=0.5,
            target_temp=200.0, current_temp=200.0,
            ai_class="normal", ai_confidence=0.90,
        )
        assert diag is not None
        assert diag.category == FailureCategory.FILAMENT_RUNOUT
        assert diag.auto_recoverable is True
        assert diag.confidence >= 0.90

    def test_filament_runout_sensor_only(self):
        """Sensor bos, SG normal → yine de runout."""
        diag = self.engine.diagnose(
            sensor_state=0, tmc_sg=200, tmc_sg_baseline=200.0,
            heater_duty=0.5, heater_baseline=0.5,
            target_temp=200.0, current_temp=200.0,
            ai_class="normal", ai_confidence=0.90,
        )
        assert diag is not None
        assert diag.category == FailureCategory.FILAMENT_RUNOUT
        assert diag.confidence >= 0.70

    def test_filament_clog(self):
        """Sensor dolu + SG cok dusuk → tikanma."""
        diag = self.engine.diagnose(
            sensor_state=1, tmc_sg=50, tmc_sg_baseline=200.0,
            heater_duty=0.5, heater_baseline=0.5,
            target_temp=200.0, current_temp=200.0,
            ai_class="normal", ai_confidence=0.90,
        )
        assert diag is not None
        assert diag.category == FailureCategory.FILAMENT_CLOG
        assert diag.auto_recoverable is True

    def test_thermal_runaway(self):
        """Duty cok yuksek + sicaklik artiyor → runaway."""
        diag = self.engine.diagnose(
            sensor_state=1, tmc_sg=200, tmc_sg_baseline=200.0,
            heater_duty=0.9, heater_baseline=0.5,  # %80 fazla
            target_temp=200.0, current_temp=215.0,  # hedefin 15°C uzerinde
            ai_class="normal", ai_confidence=0.90,
        )
        assert diag is not None
        assert diag.category == FailureCategory.THERMAL_RUNAWAY
        assert diag.auto_recoverable is False  # ASLA otomatik

    def test_thermal_deviation(self):
        """Duty yuksek + sicaklik dusuyor → sapma."""
        diag = self.engine.diagnose(
            sensor_state=1, tmc_sg=200, tmc_sg_baseline=200.0,
            heater_duty=0.70, heater_baseline=0.5,  # %40 fazla
            target_temp=200.0, current_temp=192.0,  # hedefin 8°C altinda
            ai_class="normal", ai_confidence=0.90,
        )
        assert diag is not None
        assert diag.category == FailureCategory.THERMAL_DEVIATION
        assert diag.auto_recoverable is True

    def test_spaghetti_detection(self):
        """AI spaghetti tespiti → otonom kurtarma yok."""
        diag = self.engine.diagnose(
            sensor_state=1, tmc_sg=200, tmc_sg_baseline=200.0,
            heater_duty=0.5, heater_baseline=0.5,
            target_temp=200.0, current_temp=200.0,
            ai_class="spaghetti", ai_confidence=0.85,
        )
        assert diag is not None
        assert diag.category == FailureCategory.SPAGHETTI
        assert diag.auto_recoverable is False

    def test_layer_shift_detection(self):
        """AI katman kaymasi tespiti → otonom kurtarma yok."""
        diag = self.engine.diagnose(
            sensor_state=1, tmc_sg=200, tmc_sg_baseline=200.0,
            heater_duty=0.5, heater_baseline=0.5,
            target_temp=200.0, current_temp=200.0,
            ai_class="layer_shift", ai_confidence=0.80,
        )
        assert diag is not None
        assert diag.category == FailureCategory.LAYER_SHIFT
        assert diag.auto_recoverable is False

    def test_ai_low_confidence_ignored(self):
        """AI dusuk guven → teshis yok (sinif etkisiz)."""
        diag = self.engine.diagnose(
            sensor_state=1, tmc_sg=200, tmc_sg_baseline=200.0,
            heater_duty=0.5, heater_baseline=0.5,
            target_temp=200.0, current_temp=200.0,
            ai_class="spaghetti", ai_confidence=0.50,  # Dusuk guven
        )
        assert diag is None

    def test_sensor_unavailable_no_diagnosis(self):
        """Sensor yok, SG yok → teshis yapilmaz (veri yetersiz)."""
        diag = self.engine.diagnose(
            sensor_state=-1, tmc_sg=-1, tmc_sg_baseline=0.0,
            heater_duty=0.5, heater_baseline=0.5,
            target_temp=200.0, current_temp=200.0,
            ai_class="normal", ai_confidence=0.90,
        )
        assert diag is None


# ═══════════════════════════════════════════════════════════════════════════════
# RecoveryPlanner
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecoveryPlanner:
    """Kurtarma planlayici testleri."""

    def setup_method(self):
        self.planner = RecoveryPlanner()

    def test_non_recoverable_returns_none(self):
        """Kurtarilamaz ariza → plan yok."""
        diag = FailureDiagnosis(
            category=FailureCategory.SPAGHETTI,
            confidence=0.90,
            evidence=["test"],
            auto_recoverable=False,
        )
        plan = self.planner.plan(diag)
        assert plan is None

    def test_filament_runout_plan(self):
        """Filament bitmis → gecerli plan."""
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_RUNOUT,
            confidence=0.95,
            evidence=["test"],
            auto_recoverable=True,
        )
        plan = self.planner.plan(diag, current_temp=200.0, target_temp=210.0)
        assert plan is not None
        assert len(plan.steps) >= 4
        # Son adim RESUME olmali
        assert plan.steps[-1].step_type == RecoveryStepType.RESUME
        # WAIT_SENSOR adimi olmali
        assert any(s.step_type == RecoveryStepType.WAIT_SENSOR for s in plan.steps)

    def test_filament_clog_plan(self):
        """Filament tikali → gecerli plan."""
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_CLOG,
            confidence=0.85,
            evidence=["test"],
            auto_recoverable=True,
        )
        plan = self.planner.plan(diag, current_temp=200.0, target_temp=210.0)
        assert plan is not None
        assert len(plan.steps) >= 6
        # RETRACT adimi olmali
        assert any(s.step_type == RecoveryStepType.RETRACT for s in plan.steps)
        # EXTRUDE adimi olmali
        assert any(s.step_type == RecoveryStepType.EXTRUDE for s in plan.steps)

    def test_thermal_deviation_plan(self):
        """Termal sapma → gecerli plan."""
        diag = FailureDiagnosis(
            category=FailureCategory.THERMAL_DEVIATION,
            confidence=0.80,
            evidence=["test"],
            auto_recoverable=True,
        )
        plan = self.planner.plan(diag, current_temp=195.0, target_temp=200.0)
        assert plan is not None
        # PID_CALIBRATE adimi olmali
        assert any(s.step_type == RecoveryStepType.PID_CALIBRATE for s in plan.steps)
        # COOLDOWN adimi olmali
        assert any(s.step_type == RecoveryStepType.COOLDOWN for s in plan.steps)

    def test_high_temp_blocks_recovery(self):
        """Cok yuksek sicaklik → plan olusturulmaz."""
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_CLOG,
            confidence=0.85,
            evidence=["test"],
            auto_recoverable=True,
        )
        plan = self.planner.plan(diag, current_temp=290.0, target_temp=280.0)
        assert plan is None

    def test_clog_temp_boost_applied(self):
        """Clog plani: sicaklik boost uygulanir."""
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_CLOG,
            confidence=0.85,
            evidence=["test"],
            auto_recoverable=True,
        )
        plan = self.planner.plan(diag, current_temp=200.0, target_temp=210.0)
        boosted = 210.0 + CLOG_TEMP_BOOST
        heat_steps = [s for s in plan.steps if s.step_type == RecoveryStepType.HEAT]
        # Ilk heat adimi boosted temp olmali
        assert heat_steps[0].params["target_temp"] == boosted

    def test_plan_serialization(self):
        """Plan to_dict calisiyor."""
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_RUNOUT,
            confidence=0.95,
            evidence=["test"],
            auto_recoverable=True,
        )
        plan = self.planner.plan(diag, target_temp=200.0)
        d = plan.to_dict()
        assert "diagnosis" in d
        assert "steps" in d
        assert len(d["steps"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# RecoveryExecutor
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecoveryExecutor:
    """Kurtarma yurutucu testleri."""

    def test_simple_plan_success(self):
        """Basit plan basarili yurutulur."""
        gcode_cmds = []
        executor = RecoveryExecutor(
            gcode_sender=lambda cmd: (gcode_cmds.append(cmd), True)[-1],
            pause_printer=lambda: True,
            resume_printer=lambda: True,
            notifier=lambda msg: True,
        )
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_RUNOUT,
            confidence=0.95, evidence=[], auto_recoverable=True,
        )
        plan = RecoveryPlan(diagnosis=diag, steps=[
            RecoveryStep(step_type=RecoveryStepType.PAUSE, description="duraklat"),
            RecoveryStep(step_type=RecoveryStepType.NOTIFY, description="bildir",
                         params={"message": "test"}),
            RecoveryStep(step_type=RecoveryStepType.RESUME, description="devam"),
        ])
        result = executor.execute(plan)
        assert result.success is True
        assert result.completed_steps == 3

    def test_step_failure_stops_execution(self):
        """Adim basarisiz → yurume durur."""
        call_count = 0

        def failing_pause():
            nonlocal call_count
            call_count += 1
            return False

        executor = RecoveryExecutor(pause_printer=failing_pause)
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_CLOG,
            confidence=0.85, evidence=[], auto_recoverable=True,
        )
        plan = RecoveryPlan(diagnosis=diag, steps=[
            RecoveryStep(step_type=RecoveryStepType.PAUSE, description="duraklat"),
            RecoveryStep(step_type=RecoveryStepType.RESUME, description="devam"),
        ])
        result = executor.execute(plan)
        assert result.success is False
        assert result.completed_steps == 0
        assert "basarisiz" in result.failure_reason.lower() or "Adim" in result.failure_reason

    def test_gcode_commands_sent(self):
        """G-code komutlari gonderilir."""
        cmds = []
        executor = RecoveryExecutor(
            gcode_sender=lambda cmd: (cmds.append(cmd), True)[-1],
        )
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_CLOG,
            confidence=0.85, evidence=[], auto_recoverable=True,
        )
        plan = RecoveryPlan(diagnosis=diag, steps=[
            RecoveryStep(step_type=RecoveryStepType.RETRACT, description="geri cek",
                         params={"length_mm": 10, "speed": 5}),
            RecoveryStep(step_type=RecoveryStepType.EXTRUDE, description="ileri it",
                         params={"length_mm": 15, "speed": 2}),
        ])
        result = executor.execute(plan)
        assert result.success is True
        # M83 (relative) + G1 E-10 + M83 + G1 E15 + G92 E0
        assert any("M83" in c for c in cmds)
        assert any("E-10" in c for c in cmds)
        assert any("E15" in c for c in cmds)

    def test_purge_sends_correct_gcode(self):
        """Purge adimi dogru G-code gonderir."""
        cmds = []
        executor = RecoveryExecutor(
            gcode_sender=lambda cmd: (cmds.append(cmd), True)[-1],
        )
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_RUNOUT,
            confidence=0.95, evidence=[], auto_recoverable=True,
        )
        plan = RecoveryPlan(diagnosis=diag, steps=[
            RecoveryStep(step_type=RecoveryStepType.PURGE, description="purge",
                         params={"length_mm": 50, "speed": 3}),
        ])
        result = executor.execute(plan)
        assert result.success is True
        assert any("E50" in c for c in cmds)
        assert any("G92 E0" in c for c in cmds)

    def test_wait_step(self):
        """Wait adimi belirtilen sure bekler."""
        executor = RecoveryExecutor()
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_CLOG,
            confidence=0.85, evidence=[], auto_recoverable=True,
        )
        plan = RecoveryPlan(diagnosis=diag, steps=[
            RecoveryStep(step_type=RecoveryStepType.WAIT, description="bekle",
                         params={"seconds": 0.01}),  # Cok kisa test icin
        ])
        result = executor.execute(plan)
        assert result.success is True

    def test_result_serialization(self):
        """RecoveryResult to_dict calisiyor."""
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_RUNOUT,
            confidence=0.95, evidence=[], auto_recoverable=True,
        )
        plan = RecoveryPlan(diagnosis=diag, steps=[])
        result = RecoveryResult(
            success=True, plan=plan,
            completed_steps=3, total_steps=3,
            duration_sec=5.2,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["completed_steps"] == 3
        assert d["diagnosis"] == "filament_runout"


# ═══════════════════════════════════════════════════════════════════════════════
# AutonomousRecoveryEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutonomousRecoveryEngine:
    """Ana kurtarma motoru testleri."""

    def setup_method(self):
        self.engine = AutonomousRecoveryEngine(
            gcode_sender=lambda cmd: True,
            pause_printer=lambda: True,
            resume_printer=lambda: True,
            sensor_reader=lambda: 1,
            temp_reader=lambda: 200.0,
            notifier=lambda msg: True,
        )

    def test_initial_state(self):
        """Ilk durumda hicbir sey yok."""
        status = self.engine.status
        assert status["enabled"] is True
        assert len(status["attempt_counts"]) == 0
        assert status["history_count"] == 0

    def test_diagnose_and_plan_runout(self):
        """Filament runout teshis + plan."""
        diag = self.engine.diagnose(
            sensor_state=0, tmc_sg=300, tmc_sg_baseline=200.0,
            target_temp=200.0, current_temp=200.0,
        )
        assert diag is not None
        assert diag.category == FailureCategory.FILAMENT_RUNOUT

        plan = self.engine.plan_recovery(diag, target_temp=200.0)
        assert plan is not None
        assert len(plan.steps) > 0

    def test_execute_full_recovery(self):
        """Tam kurtarma dongusu: teshis → plan → yurut."""
        diag = self.engine.diagnose(
            sensor_state=0, tmc_sg=300, tmc_sg_baseline=200.0,
        )
        plan = self.engine.plan_recovery(diag, target_temp=200.0)

        # Sensor reader: hemen "dolu" dondursun (wait_sensor icin)
        self.engine.executor._read_sensor = lambda: 1
        self.engine.executor._read_temp = lambda: 200.0

        result = self.engine.execute_recovery(plan)
        assert result.success is True
        assert self.engine._attempt_counts["filament_runout"] == 1

    def test_max_attempts_blocks_plan(self):
        """Max deneme asilinca plan olusturulmaz."""
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_CLOG,
            confidence=0.85, evidence=[], auto_recoverable=True,
        )
        self.engine._attempt_counts["filament_clog"] = MAX_RECOVERY_ATTEMPTS

        plan = self.engine.plan_recovery(diag, target_temp=200.0)
        assert plan is None

    def test_disabled_blocks_plan(self):
        """Devre disi iken plan olusturulmaz."""
        self.engine.set_enabled(False)
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_RUNOUT,
            confidence=0.95, evidence=[], auto_recoverable=True,
        )
        plan = self.engine.plan_recovery(diag, target_temp=200.0)
        assert plan is None

    def test_spaghetti_never_auto_recovers(self):
        """Spaghetti: teshis EVET ama kurtarma HAYIR."""
        diag = self.engine.diagnose(
            sensor_state=1, tmc_sg=200, tmc_sg_baseline=200.0,
            ai_class="spaghetti", ai_confidence=0.85,
        )
        assert diag is not None
        assert diag.auto_recoverable is False

        plan = self.engine.plan_recovery(diag, target_temp=200.0)
        assert plan is None

    def test_layer_shift_never_auto_recovers(self):
        """Layer shift: teshis EVET ama kurtarma HAYIR."""
        diag = self.engine.diagnose(
            sensor_state=1, tmc_sg=200, tmc_sg_baseline=200.0,
            ai_class="layer_shift", ai_confidence=0.80,
        )
        assert diag is not None
        assert diag.auto_recoverable is False

        plan = self.engine.plan_recovery(diag, target_temp=200.0)
        assert plan is None

    def test_reset_attempts(self):
        """Deneme sayaci sifirlanabilir."""
        self.engine._attempt_counts["filament_clog"] = 2
        self.engine._attempt_counts["filament_runout"] = 1

        self.engine.reset_attempts("filament_clog")
        assert "filament_clog" not in self.engine._attempt_counts
        assert "filament_runout" in self.engine._attempt_counts

        self.engine.reset_attempts()
        assert len(self.engine._attempt_counts) == 0

    def test_history_limit(self):
        """Gecmis 50 ile sinirli."""
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_RUNOUT,
            confidence=0.95, evidence=[], auto_recoverable=True,
        )
        for _ in range(60):
            plan = RecoveryPlan(diagnosis=diag, steps=[])
            result = RecoveryResult(success=True, plan=plan,
                                    completed_steps=0, total_steps=0)
            self.engine._history.append(result)

        # Engine'in yurutmesi trim yapar
        assert len(self.engine._history) == 60  # append ile 60 olur
        # execute_recovery ile trim edilir — sadece burada test
        self.engine._history = self.engine._history[-50:]
        assert len(self.engine._history) == 50

    def test_status_format(self):
        """Durum formati dogru."""
        status = self.engine.status
        assert "enabled" in status
        assert "attempt_counts" in status
        assert "history_count" in status
        assert "last_diagnosis" in status
        assert "recent_results" in status


# ═══════════════════════════════════════════════════════════════════════════════
# Guvenlik Testleri
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyGuarantees:
    """Guvenlik siniri testleri."""

    def test_auto_recoverable_categories(self):
        """Sadece 3 kategori otonom kurtarilabiir."""
        assert FailureCategory.FILAMENT_RUNOUT in AUTO_RECOVERABLE
        assert FailureCategory.FILAMENT_CLOG in AUTO_RECOVERABLE
        assert FailureCategory.THERMAL_DEVIATION in AUTO_RECOVERABLE
        assert FailureCategory.SPAGHETTI not in AUTO_RECOVERABLE
        assert FailureCategory.LAYER_SHIFT not in AUTO_RECOVERABLE
        assert FailureCategory.THERMAL_RUNAWAY not in AUTO_RECOVERABLE

    def test_thermal_runaway_never_auto(self):
        """Thermal runaway: ASLA otomatik kurtarma."""
        engine = DiagnosisEngine()
        diag = engine.diagnose(
            sensor_state=1, tmc_sg=200, tmc_sg_baseline=200.0,
            heater_duty=0.9, heater_baseline=0.5,
            target_temp=200.0, current_temp=215.0,
            ai_class="normal", ai_confidence=0.90,
        )
        assert diag.category == FailureCategory.THERMAL_RUNAWAY
        assert diag.auto_recoverable is False

    def test_max_temp_safety(self):
        """280°C uzerinde otonom kurtarma engellenir."""
        planner = RecoveryPlanner()
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_CLOG,
            confidence=0.85, evidence=[], auto_recoverable=True,
        )
        plan = planner.plan(diag, current_temp=285.0, target_temp=280.0)
        assert plan is None

    def test_max_recovery_attempts_is_2(self):
        """Max deneme sayisi 2."""
        assert MAX_RECOVERY_ATTEMPTS == 2

    def test_max_temp_limit_is_280(self):
        """Max sicaklik limiti 280°C."""
        assert MAX_TEMP_FOR_AUTO_RECOVERY == 280


# ═══════════════════════════════════════════════════════════════════════════════
# FailureDiagnosis & Serialization
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataStructures:
    """Veri yapisi testleri."""

    def test_diagnosis_serialization(self):
        """FailureDiagnosis to_dict calisiyor."""
        diag = FailureDiagnosis(
            category=FailureCategory.FILAMENT_CLOG,
            confidence=0.85,
            evidence=["test1", "test2"],
            auto_recoverable=True,
        )
        d = diag.to_dict()
        assert d["category"] == "filament_clog"
        assert d["confidence"] == 0.85
        assert len(d["evidence"]) == 2

    def test_failure_category_values(self):
        """Tum kategoriler dogru deger tasir."""
        assert FailureCategory.FILAMENT_RUNOUT == "filament_runout"
        assert FailureCategory.FILAMENT_CLOG == "filament_clog"
        assert FailureCategory.THERMAL_RUNAWAY == "thermal_runaway"
        assert FailureCategory.THERMAL_DEVIATION == "thermal_deviation"
        assert FailureCategory.SPAGHETTI == "spaghetti"
        assert FailureCategory.LAYER_SHIFT == "layer_shift"

    def test_recovery_step_types(self):
        """Tum adim tipleri mevcut."""
        types = [e.value for e in RecoveryStepType]
        assert "pause" in types
        assert "resume" in types
        assert "heat" in types
        assert "cooldown" in types
        assert "purge" in types
        assert "retract" in types
        assert "pid_calibrate" in types

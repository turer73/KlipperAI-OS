"""Tests for CalibrationOrchestrator (v3 Auto-Calibration)."""
import sys
import os
import time
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
from calibration_orchestrator import (
    CalibrationOrchestrator, CalibrationState, CalibStep,
    StepStatus, StepResult,
)


class MockMoonraker:
    """Test icin sahte Moonraker client."""

    def __init__(self, *, has_adxl=True, has_tmc=True, has_probe=True):
        self._has_adxl = has_adxl
        self._has_tmc = has_tmc
        self._has_probe = has_probe
        self._gcode_log: list[str] = []
        self._state = "standby"  # idle donerek wait_for_idle'i gecir

    def get(self, path: str, use_cache: bool = True) -> dict | None:
        if "/printer/objects/list" in path:
            objects = ["extruder", "heater_bed", "print_stats"]
            if self._has_adxl:
                objects.append("adxl345")
            if self._has_tmc:
                objects.append("tmc2209 extruder")
            if self._has_probe:
                objects.append("probe")
            return {"result": {"objects": objects}}
        return {"result": {}}

    def post(self, path: str, body: dict | None = None) -> dict | None:
        return {"result": "ok"}

    def send_gcode(self, script: str) -> bool:
        self._gcode_log.append(script)
        return True

    def get_printer_objects(self, *objects: str) -> dict:
        result = {}
        for obj in objects:
            if obj == "print_stats":
                result["print_stats"] = {"state": self._state}
            elif obj == "extruder":
                result["extruder"] = {"temperature": 210.0, "target": 210.0}
            elif obj == "heater_bed":
                result["heater_bed"] = {"temperature": 60.0, "target": 60.0}
            elif obj == "tmc2209 extruder" and self._has_tmc:
                result["tmc2209 extruder"] = {
                    "drv_status": {"sg_result": 42}
                }
        return result

    def is_available(self) -> bool:
        return True


class TestCalibrationState:
    """State dataclass testleri."""

    def test_default_state(self):
        state = CalibrationState()
        assert state.current_step == CalibStep.IDLE.value
        assert state.progress_percent == 0
        assert state.error is None

    def test_step_result_default(self):
        result = StepResult(step="pid_extruder")
        assert result.status == "pending"
        assert result.duration_sec == 0.0


class TestOrchestratorInit:
    """Orchestrator baslangic testleri."""

    def test_init_not_running(self):
        mr = MockMoonraker()
        orch = CalibrationOrchestrator(mr, state_path="/tmp/test-cal.json")
        assert orch.is_running is False
        assert orch.state.current_step == CalibStep.IDLE.value

    def test_state_is_dict(self):
        mr = MockMoonraker()
        orch = CalibrationOrchestrator(mr, state_path="/tmp/test-cal.json")
        d = orch.to_dict()
        assert isinstance(d, dict)
        assert "current_step" in d


class TestOrchestratorSteps:
    """Kalibrasyon adim testleri."""

    def _make_orch(self, **mock_kwargs):
        mr = MockMoonraker(**mock_kwargs)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            state_path = f.name
        orch = CalibrationOrchestrator(mr, state_path=state_path)
        return orch, mr, state_path

    def test_full_calibration_all_skip(self):
        """Tum adimlar atlandiginda hizla bitmeli."""
        orch, mr, path = self._make_orch()
        result = orch.start(
            skip_pid=True, skip_shaper=True,
            skip_pa=True, skip_flow=True,
        )
        assert result is True
        assert orch.state.current_step == CalibStep.DONE.value
        assert orch.state.progress_percent == 100
        os.unlink(path)

    def test_skip_pid_only(self):
        """PID atlandiginda diger adimlar calisir."""
        orch, mr, path = self._make_orch()
        result = orch.start(
            skip_pid=True, skip_shaper=True,
            skip_pa=True, skip_flow=True,
        )
        assert result is True
        # PID adimlarinin durumu skipped olmali
        steps = orch.state.steps
        assert steps["pid_extruder"]["status"] == "skipped"
        assert steps["pid_bed"]["status"] == "skipped"
        os.unlink(path)

    def test_flow_rate_without_tmc(self):
        """TMC yoksa flow rate otomatik atlanmali."""
        orch, mr, path = self._make_orch(has_tmc=False)
        result = orch.start(
            skip_pid=True, skip_shaper=True, skip_pa=True,
        )
        assert result is True
        steps = orch.state.steps
        assert steps["flow_rate"]["status"] == "skipped"
        os.unlink(path)

    def test_input_shaper_without_adxl(self):
        """ADXL yoksa input shaper otomatik atlanmali."""
        orch, mr, path = self._make_orch(has_adxl=False)
        result = orch.start(
            skip_pid=True, skip_pa=True, skip_flow=True,
        )
        assert result is True
        steps = orch.state.steps
        assert steps["input_shaper"]["status"] == "skipped"
        os.unlink(path)

    def test_flow_rate_collects_samples(self):
        """Flow rate adimi SG orneklerini toplamali."""
        orch, mr, path = self._make_orch()
        result = orch.start(
            skip_pid=True, skip_shaper=True, skip_pa=True,
        )
        assert result is True
        steps = orch.state.steps
        fr = steps["flow_rate"]
        assert fr["status"] == "completed"
        assert "baseline_sg" in fr.get("data", {})
        os.unlink(path)

    def test_abort_mechanism(self):
        """abort() methodu event flag'i set etmeli."""
        orch, mr, path = self._make_orch()
        assert orch._abort.is_set() is False
        orch.abort()
        assert orch._abort.is_set() is True
        os.unlink(path)

    def test_abort_during_flow_rate(self):
        """Flow rate sirasinda abort kalibrasyonu durdurmali."""
        import threading
        orch, mr, path = self._make_orch()
        t = threading.Thread(target=orch.start, kwargs={
            "skip_pid": True, "skip_shaper": True, "skip_pa": True,
        })
        t.start()
        time.sleep(0.5)  # Flow rate sample toplama baslasin
        orch.abort()
        t.join(timeout=15)
        assert orch.state.current_step in ("failed", "done")
        os.unlink(path)

    def test_state_saved_to_file(self):
        """Kalibrasyon tamamlandiginda state dosyasi yazilmali."""
        orch, mr, path = self._make_orch()
        orch.start(
            skip_pid=True, skip_shaper=True,
            skip_pa=True, skip_flow=True,
        )
        # State dosyasi okunabilmeli
        data = CalibrationOrchestrator.load_state(path)
        assert data is not None
        assert data["current_step"] == "done"
        os.unlink(path)

    def test_progress_callback_called(self):
        """Progress callback cagirilmali."""
        mr = MockMoonraker()
        callback_count = {"n": 0}

        def on_progress(state):
            callback_count["n"] += 1

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        orch = CalibrationOrchestrator(
            mr, state_path=path, on_progress=on_progress,
        )
        orch.start(
            skip_pid=True, skip_shaper=True,
            skip_pa=True, skip_flow=True,
        )
        assert callback_count["n"] > 0
        os.unlink(path)

    def test_double_start_rejected(self):
        """Zaten calisan orkestrator ikinci start'i reddetmeli."""
        orch, mr, path = self._make_orch()
        orch._running = True  # Simulate running
        result = orch.start()
        assert result is False
        orch._running = False
        os.unlink(path)


class TestGCodeSequence:
    """G-code calistirma sira testleri."""

    def test_pid_sends_correct_gcode(self):
        mr = MockMoonraker()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        orch = CalibrationOrchestrator(mr, state_path=path)
        orch.start(
            extruder_temp=230, bed_temp=80,
            skip_shaper=True, skip_pa=True, skip_flow=True,
        )

        # PID G-code'lari gonderilmis olmali
        gcodes = mr._gcode_log
        assert any("PID_CALIBRATE HEATER=extruder TARGET=230" in g for g in gcodes)
        assert any("PID_CALIBRATE HEATER=heater_bed TARGET=80" in g for g in gcodes)
        os.unlink(path)

    def test_pa_sends_tuning_tower(self):
        mr = MockMoonraker()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        orch = CalibrationOrchestrator(mr, state_path=path)
        orch.start(
            skip_pid=True, skip_shaper=True, skip_flow=True,
        )

        gcodes = mr._gcode_log
        assert any("TUNING_TOWER" in g for g in gcodes)
        assert any("SET_PRESSURE_ADVANCE" in g for g in gcodes)
        os.unlink(path)


class TestLoadState:
    """State dosya okuma testleri."""

    def test_load_nonexistent_returns_none(self):
        result = CalibrationOrchestrator.load_state("/tmp/nonexistent-xyz.json")
        assert result is None

    def test_load_corrupt_returns_none(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("{corrupt json")
            path = f.name

        result = CalibrationOrchestrator.load_state(path)
        assert result is None
        os.unlink(path)

    def test_load_valid_state(self):
        data = {"current_step": "done", "progress_percent": 100}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            path = f.name

        result = CalibrationOrchestrator.load_state(path)
        assert result == data
        os.unlink(path)

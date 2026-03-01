# KlipperOS-AI v2.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Power Loss Recovery, 4-layer FlowGuard flow detection, Smart Rewind coordinate rollback, TMC calibration, jschuh/klipper-macros integration, and 8 component improvements to KlipperOS-AI.

**Architecture:** Hybrid approach — Klipper macros for PLR state saving (direct disk write, no Moonraker dependency), standalone Python daemon extension for FlowGuard (extends existing `print_monitor.py`), CLI tools for rewind/calibration (follows existing `kos_*.py` pattern with argparse). jschuh/klipper-macros provides base macro infrastructure, extended via `rename_existing` hooks.

**Tech Stack:** Python 3.9+, Klipper G-code macros, Moonraker REST API, TFLite, requests, numpy, argparse. No new dependencies beyond existing project.

**Design doc:** `docs/plans/2026-03-01-klipperos-ai-v2-design.md`

---

### Task 1: MCU Board Database (JSON)

**Files:**
- Create: `data/boards.json`

**Step 1: Create the board database**

```json
{
  "version": "1.0.0",
  "boards": [
    {
      "name": "Creality V4.2.2",
      "vid": "1a86",
      "pid": "7523",
      "mcu": "STM32F103",
      "chip": "stm32f103xe",
      "bootloader": "28KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": ["Ender 3", "Ender 3 Pro", "CR-10"]
    },
    {
      "name": "Creality V4.2.7",
      "vid": "1a86",
      "pid": "7523",
      "mcu": "STM32F103",
      "chip": "stm32f103xe",
      "bootloader": "28KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": ["Ender 3 V2", "Ender 3 S1"]
    },
    {
      "name": "BTT SKR Mini E3 V3",
      "vid": "1d50",
      "pid": "614e",
      "mcu": "STM32G0B1",
      "chip": "stm32g0b1xx",
      "bootloader": "8KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": []
    },
    {
      "name": "BTT SKR 3",
      "vid": "1d50",
      "pid": "614e",
      "mcu": "STM32H743",
      "chip": "stm32h743xx",
      "bootloader": "128KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": []
    },
    {
      "name": "BTT Octopus V1.1",
      "vid": "1d50",
      "pid": "614e",
      "mcu": "STM32F446",
      "chip": "stm32f446xx",
      "bootloader": "32KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": ["Voron 2.4", "Voron Trident"]
    },
    {
      "name": "BTT Manta M4P",
      "vid": "1d50",
      "pid": "614e",
      "mcu": "STM32G0B1",
      "chip": "stm32g0b1xx",
      "bootloader": "8KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": []
    },
    {
      "name": "BTT Manta M5P",
      "vid": "1d50",
      "pid": "614e",
      "mcu": "STM32G0B1",
      "chip": "stm32g0b1xx",
      "bootloader": "8KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": []
    },
    {
      "name": "BTT Manta M8P",
      "vid": "1d50",
      "pid": "614e",
      "mcu": "STM32G0B1",
      "chip": "stm32g0b1xx",
      "bootloader": "8KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": []
    },
    {
      "name": "RP2040 (SKR Pico)",
      "vid": "2e8a",
      "pid": "0003",
      "mcu": "RP2040",
      "chip": "rp2040",
      "bootloader": "none",
      "comm": "usb",
      "baud": 250000,
      "printer_models": ["Voron V0"]
    },
    {
      "name": "Arduino Mega 2560",
      "vid": "2341",
      "pid": "0042",
      "mcu": "ATmega2560",
      "chip": "atmega2560",
      "bootloader": "none",
      "comm": "serial",
      "baud": 250000,
      "printer_models": ["RAMPS 1.4"]
    },
    {
      "name": "MKS Robin Nano V3",
      "vid": "0483",
      "pid": "5740",
      "mcu": "STM32F407",
      "chip": "stm32f407xx",
      "bootloader": "32KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": []
    },
    {
      "name": "Fysetc Spider V2",
      "vid": "1d50",
      "pid": "614e",
      "mcu": "STM32F446",
      "chip": "stm32f446xx",
      "bootloader": "64KiB",
      "comm": "serial",
      "baud": 250000,
      "printer_models": ["Voron 2.4"]
    },
    {
      "name": "BTT EBB36/42 CAN",
      "vid": "1d50",
      "pid": "606f",
      "mcu": "STM32G0B1",
      "chip": "stm32g0b1xx",
      "bootloader": "8KiB",
      "comm": "canbus",
      "baud": 1000000,
      "printer_models": []
    }
  ]
}
```

**Step 2: Commit**

```bash
git add data/boards.json
git commit -m "feat: add MCU board database JSON with 13 board definitions"
```

---

### Task 2: Klipper PLR Macros

**Files:**
- Create: `config/klipper/kos_plr.cfg`

**Context:** These are Klipper G-code macros. They use `[save_variables]` to persist state to disk. `BEFORE_LAYER_CHANGE` is the hook point from jschuh/klipper-macros `layers.cfg`. The `rename_existing` pattern preserves the original macro while adding PLR behavior.

**Step 1: Write kos_plr.cfg**

The file must contain:
- `[save_variables]` section pointing to `~/printer_data/config/variables.cfg`
- `BEFORE_LAYER_CHANGE` macro override with `rename_existing: _KM_BEFORE_LAYER_CHANGE` — calls original then saves PLR state
- `_KOS_SAVE_PLR_STATE` macro — writes all PLR variables using `SAVE_VARIABLE` commands: `plr_active`, `plr_file_position` (from `printer.virtual_sdcard.file_position`), `plr_z_height`, `plr_layer`, `plr_extruder_temp` (from `printer.extruder.target`), `plr_bed_temp` (from `printer.heater_bed.target`), `plr_fan_speed` (from `printer.fan.speed`), `plr_timestamp`
- `_KOS_CHECK_PLR` delayed_gcode (initial_duration: 5) — reads `printer.save_variables.variables.plr_active`, if True shows M117 message "PLR: Kayitli baski var! kos-plr resume ile devam edin"
- `KOS_PLR_RESUME` macro — the resume sequence: M104/M140 for temps, M109/M190 to wait, `SET_KINEMATIC_POSITION Z={z_height}`, G1 Z+5 raise, G28 X Y, fan/flow/speed restore, G92 E0, purge 30mm, retract 2mm, G92 E0, then `RESPOND MSG="PLR resume hazir. RESUME komutu ile devam edin."`
- `KOS_PLR_CLEAR` macro — sets `plr_active` to False
- `PRINT_END` override with `rename_existing: _KM_PRINT_END` — calls `KOS_PLR_CLEAR` then `_KM_PRINT_END`

**Step 2: Commit**

```bash
git add config/klipper/kos_plr.cfg
git commit -m "feat: add PLR Klipper macros with layer-change state saving"
```

---

### Task 3: Klipper FlowGuard Macros

**Files:**
- Create: `config/klipper/kos_flowguard.cfg`

**Step 1: Write kos_flowguard.cfg**

Contents:
- `[filament_motion_sensor btt_sfs]` — `detection_length: 10`, `extruder: extruder`, `switch_pin: ^PG12` (comment: user must edit pin), `pause_on_runout: False` (FlowGuard manages), `event_delay: 3.0`, `runout_gcode: _KOS_FLOWGUARD_SENSOR_TRIGGER`, `insert_gcode: _KOS_FLOWGUARD_SENSOR_INSERT`
- `_KOS_FLOWGUARD_SENSOR_TRIGGER` macro — `{action_respond_info("FlowGuard L1: Filament hareketi tespit edilemedi!")}`
- `_KOS_FLOWGUARD_SENSOR_INSERT` macro — respond info "FlowGuard L1: Filament hareketi algilandi"
- `KOS_FLOWGUARD_STATUS` macro — report current sensor state using `printer["filament_motion_sensor btt_sfs"]`
- Comment block at top explaining: user must edit `switch_pin`, set `pause_on_runout: False` because FlowGuard daemon manages pausing

Note: The sensor section should be commented out by default with instructions, since not all users have the hardware.

**Step 2: Commit**

```bash
git add config/klipper/kos_flowguard.cfg
git commit -m "feat: add FlowGuard Klipper macros with filament sensor template"
```

---

### Task 4: Klipper Rewind Macros

**Files:**
- Create: `config/klipper/kos_rewind.cfg`

**Step 1: Write kos_rewind.cfg**

Contents:
- `[force_move]` section — `enable_force_move: True` (required for SET_KINEMATIC_POSITION)
- `KOS_REWIND_PARK` macro — uses jschuh park system: moves Z up by `params.Z_HOP|default(10)|float` mm at F600, then responds "Nozzle park edildi"
- `KOS_REWIND_HOME` macro — `G28 X Y` only (never Z), responds "X/Y home tamamlandi (Z homing YAPILMADI — baski korumasi)"
- `KOS_REWIND_PREPARE` macro — accepts EXTRUDER_TEMP, BED_TEMP, FAN_SPEED, PURGE_LENGTH params: heats, waits, sets fan, purges, retracts, responds "Rewind hazirligi tamamlandi"

**Step 2: Commit**

```bash
git add config/klipper/kos_rewind.cfg
git commit -m "feat: add Rewind Klipper macros with safe park and home"
```

---

### Task 5: HeaterDutyAnalyzer Module

**Files:**
- Create: `ai-monitor/heater_analyzer.py`
- Create: `tests/test_heater_analyzer.py`

**Step 1: Write the failing test**

```python
# tests/test_heater_analyzer.py
import pytest
from collections import deque

# We test the analysis logic, not Moonraker API calls
from ai_monitor_test_helpers import make_heater_analyzer

class TestHeaterDutyAnalyzer:
    def test_baseline_calibration(self):
        analyzer = make_heater_analyzer(window_size=10)
        # Feed 10 samples to establish baseline
        for _ in range(10):
            analyzer.add_sample(0.70)
        assert abs(analyzer.baseline - 0.70) < 0.01

    def test_normal_flow_detected(self):
        analyzer = make_heater_analyzer(window_size=10, baseline=0.70)
        # Normal duty cycle near baseline
        for _ in range(10):
            analyzer.add_sample(0.68)
        state = analyzer.check_flow()
        assert state.name == "OK"

    def test_clog_detected_duty_drop(self):
        analyzer = make_heater_analyzer(window_size=10, baseline=0.70)
        # Duty drops >15% (clog — less heat absorption)
        for _ in range(10):
            analyzer.add_sample(0.50)
        state = analyzer.check_flow()
        assert state.name == "ANOMALY"

    def test_insufficient_samples_returns_ok(self):
        analyzer = make_heater_analyzer(window_size=10)
        analyzer.add_sample(0.30)
        state = analyzer.check_flow()
        assert state.name == "OK"  # Not enough data
```

**Step 2: Create test helper**

```python
# tests/ai_monitor_test_helpers.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))
```

**Step 3: Write HeaterDutyAnalyzer implementation**

`ai-monitor/heater_analyzer.py`:
- `FlowState` enum: `OK`, `ANOMALY`, `CALIBRATING`
- `HeaterDutyAnalyzer` class:
  - `__init__(self, window_size=30, threshold_pct=0.15)` — creates `deque(maxlen=window_size)`, `baseline=None`, `calibration_samples=[]`, `calibration_count=30`
  - `add_sample(self, duty_cycle: float)` — appends to window, if calibrating adds to calibration_samples
  - `calibrate(self)` — compute mean of calibration_samples, set as baseline
  - `check_flow(self) -> FlowState` — if no baseline or window not full, return OK. Compute mean of window. If `mean < baseline * (1 - threshold_pct)`, return ANOMALY. Else OK.
  - `confidence` property — returns 0.70 (fixed for heater method)
  - `reset(self)` — clear window, baseline, calibration

**Step 4: Run tests**

```bash
cd C:\linux_ai\KlipperOS-AI
python -m pytest tests/test_heater_analyzer.py -v
```

Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add ai-monitor/heater_analyzer.py tests/test_heater_analyzer.py tests/ai_monitor_test_helpers.py
git commit -m "feat: add HeaterDutyAnalyzer with baseline calibration and clog detection"
```

---

### Task 6: ExtruderLoadMonitor Module

**Files:**
- Create: `ai-monitor/extruder_monitor.py`
- Create: `tests/test_extruder_monitor.py`

**Step 1: Write the failing test**

```python
# tests/test_extruder_monitor.py
import pytest

class TestExtruderLoadMonitor:
    def test_normal_sg_result(self):
        from extruder_monitor import ExtruderLoadMonitor
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(90)
        state = monitor.check_flow()
        assert state.name == "OK"

    def test_clog_high_load(self):
        from extruder_monitor import ExtruderLoadMonitor
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(20)  # Very high load
        state = monitor.check_flow()
        assert state.name == "ANOMALY"

    def test_no_filament_low_load(self):
        from extruder_monitor import ExtruderLoadMonitor
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(200)  # No load — filament gone
        state = monitor.check_flow()
        assert state.name == "ANOMALY"

    def test_suggest_flow_rate_normal(self):
        from extruder_monitor import ExtruderLoadMonitor
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(85)
        suggestion = monitor.suggest_flow_rate()
        assert suggestion == 1.0

    def test_suggest_flow_rate_under_extrusion(self):
        from extruder_monitor import ExtruderLoadMonitor
        monitor = ExtruderLoadMonitor(window_size=10)
        monitor.set_baseline(85.0)
        for _ in range(10):
            monitor.add_sample(120)  # Low load = under-extrusion
        suggestion = monitor.suggest_flow_rate()
        assert suggestion == 1.05
```

**Step 2: Write ExtruderLoadMonitor**

`ai-monitor/extruder_monitor.py`:
- Import `FlowState` from `heater_analyzer` (share the enum)
- `ExtruderLoadMonitor` class:
  - `__init__(self, window_size=100, clog_threshold=0.30, empty_threshold=2.0)` — deque, baseline=None
  - `set_baseline(self, baseline: float)` — set baseline SG_RESULT
  - `add_sample(self, sg_result: int)` — append
  - `check_flow(self) -> FlowState` — if no baseline or insufficient samples, OK. Mean of window. If `mean < baseline * clog_threshold` (high load), ANOMALY. If `mean > baseline * empty_threshold` (no load), ANOMALY. Else OK.
  - `suggest_flow_rate(self) -> float` — ratio = mean/baseline. If ratio > 1.2 return 1.05 (increase flow). If ratio < 0.8 return 0.95 (decrease flow). Else 1.0.
  - `confidence` property — returns 0.85

**Step 3: Run tests**

```bash
python -m pytest tests/test_extruder_monitor.py -v
```

**Step 4: Commit**

```bash
git add ai-monitor/extruder_monitor.py tests/test_extruder_monitor.py
git commit -m "feat: add ExtruderLoadMonitor with TMC StallGuard flow detection"
```

---

### Task 7: FlowGuard Voting Engine

**Files:**
- Create: `ai-monitor/flow_guard.py`
- Create: `tests/test_flow_guard.py`

**Step 1: Write the failing test**

```python
# tests/test_flow_guard.py
import pytest
from flow_guard import FlowGuard, FlowVerdict, FlowSignal

class TestFlowGuardVoting:
    def test_all_ok_returns_ok(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.OK, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.OK

    def test_one_anomaly_returns_notice(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.NOTICE

    def test_two_anomaly_returns_warning(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.ANOMALY, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.WARNING

    def test_three_anomaly_returns_critical(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.ANOMALY, FlowSignal.ANOMALY, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.CRITICAL

    def test_four_anomaly_returns_critical(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.ANOMALY,
            FlowSignal.ANOMALY, FlowSignal.ANOMALY
        ])
        assert verdict == FlowVerdict.CRITICAL

    def test_warning_escalation_after_3_cycles(self):
        guard = FlowGuard()
        signals_2of4 = [
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.ANOMALY, FlowSignal.OK
        ]
        # First 2 cycles: WARNING
        for _ in range(2):
            v = guard.evaluate(signals_2of4)
            assert v == FlowVerdict.WARNING
        # 3rd cycle: escalates to CRITICAL
        v = guard.evaluate(signals_2of4)
        assert v == FlowVerdict.CRITICAL

    def test_warning_resets_on_ok(self):
        guard = FlowGuard()
        guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.ANOMALY, FlowSignal.OK
        ])
        # Then all OK — resets warning counter
        guard.evaluate([
            FlowSignal.OK, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK
        ])
        # Back to WARNING, not escalated
        v = guard.evaluate([
            FlowSignal.ANOMALY, FlowSignal.OK, FlowSignal.ANOMALY, FlowSignal.OK
        ])
        assert v == FlowVerdict.WARNING

    def test_unavailable_signals_treated_as_ok(self):
        guard = FlowGuard()
        verdict = guard.evaluate([
            FlowSignal.UNAVAILABLE, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK
        ])
        assert verdict == FlowVerdict.OK

    def test_last_flow_ok_layer_tracked(self):
        guard = FlowGuard()
        guard.update_layer(50, 10.0)
        guard.evaluate([FlowSignal.OK, FlowSignal.OK, FlowSignal.OK, FlowSignal.OK])
        guard.update_layer(60, 12.0)
        guard.evaluate([FlowSignal.ANOMALY, FlowSignal.ANOMALY,
                        FlowSignal.ANOMALY, FlowSignal.OK])
        assert guard.last_ok_layer == 50
        assert guard.last_ok_z == 10.0
```

**Step 2: Write FlowGuard**

`ai-monitor/flow_guard.py`:
- `FlowSignal` enum: `OK`, `ANOMALY`, `UNAVAILABLE`
- `FlowVerdict` enum: `OK`, `NOTICE`, `WARNING`, `CRITICAL`
- `FlowGuard` class:
  - `__init__(self)` — `warning_count=0`, `warning_threshold=3`, `last_ok_layer=0`, `last_ok_z=0.0`, `current_layer=0`, `current_z=0.0`
  - `update_layer(self, layer: int, z_height: float)` — update current
  - `evaluate(self, signals: list[FlowSignal]) -> FlowVerdict` — count anomalies (skip UNAVAILABLE), apply voting logic, track warning escalation, update last_ok on all-OK
  - `reset(self)` — reset warning counter and state

**Step 3: Run tests**

```bash
python -m pytest tests/test_flow_guard.py -v
```

**Step 4: Commit**

```bash
git add ai-monitor/flow_guard.py tests/test_flow_guard.py
git commit -m "feat: add FlowGuard voting engine with 4-signal evaluation and escalation"
```

---

### Task 8: Update spaghetti_detect.py to 5 Classes

**Files:**
- Modify: `ai-monitor/spaghetti_detect.py`

**Step 1: Update CLASS_LABELS and THRESHOLDS**

In `spaghetti_detect.py`, change:

```python
CLASS_LABELS = {
    0: "normal",
    1: "spaghetti",
    2: "no_extrusion",   # NEW
    3: "stringing",
    4: "completed",
}

THRESHOLDS = {
    "spaghetti": 0.70,
    "no_extrusion": 0.75,  # NEW
    "stringing": 0.80,
    "completed": 0.85,
}
```

**Step 2: Update `_process_scores`**

Add `no_extrusion` action mapping:

```python
elif predicted_class == "no_extrusion" and confidence >= self.thresholds.get("no_extrusion", 0.75):
    action = "pause"
```

**Step 3: Commit**

```bash
git add ai-monitor/spaghetti_detect.py
git commit -m "feat: extend spaghetti detector to 5 classes with no_extrusion detection"
```

---

### Task 9: Integrate FlowGuard into print_monitor.py

**Files:**
- Modify: `ai-monitor/print_monitor.py`

**Step 1: Add imports and FlowGuard initialization**

At the top, add imports for `FlowGuard`, `FlowSignal`, `FlowVerdict`, `HeaterDutyAnalyzer`, `ExtruderLoadMonitor`.

In `PrintMonitor.__init__`, add:
- `self.flow_guard = FlowGuard()`
- `self.heater_analyzer = HeaterDutyAnalyzer()`
- `self.extruder_monitor = ExtruderLoadMonitor()`
- `self._flowguard_enabled = True`

**Step 2: Add Moonraker query methods**

Add to `MoonrakerClient`:
- `get_heater_duty(self) -> float | None` — query `/printer/objects/query?extruder=power,temperature,target`, return `power` field
- `get_tmc_sg_result(self) -> int | None` — query `/printer/objects/query?tmc2209+extruder`, return `drv_status.sg_result` (return None if TMC not configured)
- `get_filament_sensor(self) -> bool | None` — query `/printer/objects/query?filament_motion_sensor+btt_sfs`, return `filament_detected` (None if not configured)
- `get_print_layer_info(self) -> dict` — query `print_stats` for `info.current_layer` and `info.total_layer`, plus virtual_sdcard for file_position

**Step 3: Add FlowGuard check cycle**

In `_check_cycle`, after the existing AI detection block, add FlowGuard logic:
1. Read all 4 signals (sensor, heater, TMC, AI) — each wrapped in try/except returning `FlowSignal.UNAVAILABLE` on failure
2. Call `self.flow_guard.evaluate(signals)`
3. If CRITICAL: call `pause_print()` and `send_notification()` with FlowGuard details
4. If WARNING: log warning
5. If NOTICE: log info
6. Update layer info: `self.flow_guard.update_layer(layer, z_height)`

**Step 4: Add FlowGuard calibration in start**

After Moonraker wait, add a calibration phase:
- Log "FlowGuard kalibrasyon bekleniyor..."
- First 30 check cycles: feed heater duty and TMC samples as calibration data
- After 30 cycles: call `heater_analyzer.calibrate()` and `extruder_monitor.set_baseline(mean)`
- Log baseline values

**Step 5: Commit**

```bash
git add ai-monitor/print_monitor.py
git commit -m "feat: integrate FlowGuard 4-layer detection into print monitor daemon"
```

---

### Task 10: PLR CLI Tool

**Files:**
- Create: `tools/kos_plr.py`

**Step 1: Write kos_plr.py**

Follow the exact pattern of `tools/kos_mcu.py` (argparse + subcommands).

Structure:
- `VARIABLES_FILE = Path.home() / "printer_data" / "config" / "variables.cfg"`
- `MOONRAKER_URL` from env or default
- `read_plr_state() -> dict | None` — parse variables.cfg, extract all `plr_*` variables
- `cmd_status(args)` — read PLR state, display formatted table (file, layer, Z, temps, timestamp)
- `cmd_resume(args)` — read state, confirm with user, POST to Moonraker `/printer/gcode/script` with `KOS_PLR_RESUME` command
- `cmd_clear(args)` — POST `KOS_PLR_CLEAR` to Moonraker
- `cmd_test(args)` — POST `_KOS_SAVE_PLR_STATE HEIGHT=10.0 LAYER=50` then read back and verify
- `main()` — argparse with `status`, `resume`, `clear`, `test` subcommands

**Step 2: Commit**

```bash
git add tools/kos_plr.py
git commit -m "feat: add kos-plr CLI tool for power loss recovery management"
```

---

### Task 11: Smart Rewind CLI Tool

**Files:**
- Create: `tools/kos_rewind.py`
- Create: `tests/test_gcode_parser.py`

**Step 1: Write G-code layer parser test**

```python
# tests/test_gcode_parser.py
from kos_rewind import find_layer_position

SAMPLE_GCODE = """; generated by PrusaSlicer
M104 S210
G28
;BEFORE_LAYER_CHANGE
;10.0
G1 Z10.000 F600
;LAYER:50
G1 X100 Y100 F3000
G1 E1.5 F300
;BEFORE_LAYER_CHANGE
;10.2
G1 Z10.200 F600
;LAYER:51
G1 X110 Y110 F3000
"""

def test_find_layer_by_comment():
    pos, z = find_layer_position(SAMPLE_GCODE, target_layer=50)
    assert pos is not None
    assert z == 10.0

def test_find_layer_not_found():
    pos, z = find_layer_position(SAMPLE_GCODE, target_layer=999)
    assert pos is None

def test_find_cura_style():
    gcode = ";LAYER:25\nG1 Z5.0\n;LAYER:26\nG1 Z5.2\n"
    pos, z = find_layer_position(gcode, target_layer=25)
    assert pos is not None
```

**Step 2: Write kos_rewind.py**

Structure:
- `find_layer_position(gcode_text: str, target_layer: int) -> tuple[int | None, float | None]` — scan for `;LAYER:N`, `;BEFORE_LAYER_CHANGE` followed by `;Z`, or Cura/OrcaSlicer patterns. Return byte offset and Z height.
- `apply_z_offset(gcode_lines: list[str], z_offset: float) -> list[str]` — find `G1 Z{value}` patterns, add z_offset to each Z value
- `generate_preamble(state: dict, purge_length: float) -> str` — generate resume G-code (M104/M140/M109/M190, G92, purge, retract, fan, speed)
- `capture_preview(moonraker_url: str, output_path: str) -> bool` — GET camera snapshot, save to file
- `cmd_status(args)` — show current print state + FlowGuard last_ok_layer info from Moonraker
- `cmd_preview(args)` — capture camera image, display path
- `cmd_goto(args)` — the main rewind logic:
  1. Read current gcode file path from Moonraker print_stats
  2. Read PLR state for temps/fan
  3. Parse gcode file to find target layer position
  4. If `--dry-run`, print what would happen and exit
  5. Generate preamble
  6. Create rewind file: `{name}_rewind_L{layer}.gcode` = preamble + gcode from layer position with Z offset applied
  7. Upload rewind file via Moonraker `/server/files/upload`
  8. Send `KOS_REWIND_PARK` then `KOS_REWIND_HOME` then `KOS_REWIND_PREPARE` macros
  9. Start print: `/printer/print/start?filename={rewind_file}`
- `cmd_auto(args)` — read FlowGuard last_ok_layer, call goto with that layer
- `main()` — argparse: `status`, `preview`, `goto` (with `--layer`, `--z-offset`, `--purge`, `--dry-run`), `auto` (with `--z-offset`)

**Step 3: Run tests**

```bash
python -m pytest tests/test_gcode_parser.py -v
```

**Step 4: Commit**

```bash
git add tools/kos_rewind.py tests/test_gcode_parser.py
git commit -m "feat: add kos-rewind CLI tool with G-code layer parsing and Z offset rewind"
```

---

### Task 12: TMC Calibration CLI Tool

**Files:**
- Create: `tools/kos_calibrate.py`

**Step 1: Write kos_calibrate.py**

Structure:
- `CALIBRATION_FILE = Path.home() / "printer_data" / "config" / "kos_calibration.json"`
- `cmd_flow_status(args)` — read calibration JSON, display baseline per filament/temp, suggest flow rate
- `cmd_flow_reset(args)` — delete calibration file
- `cmd_flow_test(args)` — interactive:
  1. Ask filament type (PLA/PETG/ABS/TPU)
  2. Ask nozzle temperature
  3. Start collecting TMC SG_RESULT samples via Moonraker (30s baseline)
  4. Store baseline in calibration JSON keyed by `{filament}_{temp}`
  5. Print baseline result
- `main()` — argparse: `flow-status`, `flow-test`, `flow-reset`

**Step 2: Commit**

```bash
git add tools/kos_calibrate.py
git commit -m "feat: add kos-calibrate CLI tool for TMC flow calibration"
```

---

### Task 13: Update Existing Config Templates

**Files:**
- Modify: `config/klipper/generic.cfg` — add `[exclude_object]`, `[firmware_retraction]`, `[respond]`, `[virtual_sdcard]`, `[display_status]`, `[pause_resume]`, `[save_variables]`, `[force_move]`, include lines for kos_plr/flowguard/rewind, PID calibration macro `KOS_PID_CALIBRATE`
- Modify: `config/klipper/ender3.cfg` — same additions
- Modify: `config/klipper/ender3v2.cfg` — same additions
- Modify: `config/klipper/voron.cfg` — same additions (already has some of these)
- Modify: `config/moonraker/moonraker.conf` — add `[history]`, `[job_queue]`, `temperature_store_size: 2400`, `gcode_store_size: 2000`, `[update_manager klipper-macros]` section
- Modify: `config/crowsnest/crowsnest.conf` — add camera-streamer mode option (commented), HD/FHD resolution profiles (commented)
- Modify: `config/klipperscreen/KlipperScreen.conf` — add `[menu __main custom]` for FlowGuard status and PLR resume

**Step 1: Update all config files**

For each printer config, add these sections at the end (before macros):
```ini
# --- KlipperOS-AI Entegrasyon ---
[include klipper-macros/*.cfg]
[include kos_plr.cfg]
#[include kos_flowguard.cfg]   ; Filament sensoru varsa aktiflestiriniz
[include kos_rewind.cfg]

[exclude_object]

[firmware_retraction]
retract_length: 0.8
retract_speed: 40
unretract_extra_length: 0
unretract_speed: 40

[respond]

[gcode_macro KOS_PID_CALIBRATE]
description: Extruder ve bed PID otomatik kalibrasyon
gcode:
    {% set EXTRUDER_TEMP = params.EXTRUDER_TEMP|default(210)|float %}
    {% set BED_TEMP = params.BED_TEMP|default(60)|float %}
    {action_respond_info("PID kalibrasyonu basliyor...")}
    PID_CALIBRATE HEATER=extruder TARGET={EXTRUDER_TEMP}
    PID_CALIBRATE HEATER=heater_bed TARGET={BED_TEMP}
    SAVE_CONFIG
```

For moonraker.conf, add after existing content:
```ini
[history]

[job_queue]
load_on_startup: False
automatic_transition: False

[update_manager klipper-macros]
type: git_repo
origin: https://github.com/jschuh/klipper-macros.git
path: ~/printer_data/config/klipper-macros
primary_branch: main
is_system_service: False
```

Update `[server]` section to include:
```ini
temperature_store_size: 2400
gcode_store_size: 2000
```

**Step 2: Commit**

```bash
git add config/
git commit -m "feat: update all config templates with v2 features (exclude_object, PLR, FlowGuard, PID macro)"
```

---

### Task 14: Update MCU Manager with Board DB and CANbus

**Files:**
- Modify: `tools/kos_mcu.py`

**Step 1: Update BOARD_CONFIGS to load from JSON**

Replace hardcoded `BOARD_CONFIGS` dict with:
```python
BOARDS_JSON = Path(__file__).parent.parent / "data" / "boards.json"

def load_board_db() -> list[dict]:
    if BOARDS_JSON.exists():
        with open(BOARDS_JSON) as f:
            data = json.load(f)
            return data.get("boards", [])
    return []

def get_board_configs() -> dict:
    boards = load_board_db()
    configs = {}
    for b in boards:
        key = b["name"].lower().replace(" ", "-").replace(".", "")
        configs[key] = {
            "description": f"{b['name']} ({b['mcu']})",
            "mcu": b["chip"],
            "bootloader": b["bootloader"],
            "comm": b["comm"],
        }
    return configs
```

**Step 2: Add CANbus scan to cmd_scan**

After serial port scanning, add:
```python
# CANbus tarama
can_result = run(["ip", "-details", "link", "show", "type", "can"])
if can_result.returncode == 0 and can_result.stdout.strip():
    print("\nCANbus arayuzleri:")
    print(can_result.stdout)
```

**Step 3: Commit**

```bash
git add tools/kos_mcu.py
git commit -m "feat: update MCU manager with JSON board database and CANbus scanning"
```

---

### Task 15: Update Install Scripts

**Files:**
- Modify: `scripts/install-light.sh`
- Modify: `scripts/install-standard.sh`

**Step 1: Add jschuh/klipper-macros to install-light.sh**

Add `install_klipper_macros()` function after `install_mainsail`:
```bash
install_klipper_macros() {
    log "jschuh/klipper-macros kuruluyor..."
    sudo -u "$KLIPPER_USER" git clone \
        https://github.com/jschuh/klipper-macros.git \
        "$PRINTER_DATA/config/klipper-macros"

    # KlipperOS-AI macro genisletmelerini kopyala
    cp "$KOS_DIR/config/klipper/kos_plr.cfg" "$PRINTER_DATA/config/"
    cp "$KOS_DIR/config/klipper/kos_flowguard.cfg" "$PRINTER_DATA/config/"
    cp "$KOS_DIR/config/klipper/kos_rewind.cfg" "$PRINTER_DATA/config/"

    log "klipper-macros kuruldu."
}
```

Add call in `main()` after `setup_printer_data` and before `configure_nginx`.

**Step 2: Update install-standard.sh FlowGuard service**

Update the `klipperos-ai-monitor.service` ExecStart environment to include FlowGuard-related env vars:
```ini
Environment=FLOWGUARD_ENABLED=1
```

**Step 3: Commit**

```bash
git add scripts/install-light.sh scripts/install-standard.sh
git commit -m "feat: update install scripts with jschuh macros and FlowGuard service config"
```

---

### Task 16: Update pyproject.toml and README

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`

**Step 1: Update pyproject.toml**

Add new CLI entry points:
```toml
[project.scripts]
kos-profile = "tools.kos_profile:main"
kos-update = "tools.kos_update:main"
kos-backup = "tools.kos_backup:main"
kos-mcu = "tools.kos_mcu:main"
kos-plr = "tools.kos_plr:main"
kos-rewind = "tools.kos_rewind:main"
kos-calibrate = "tools.kos_calibrate:main"
```

Update version to `2.0.0`.

**Step 2: Update README.md**

Add sections for:
- PLR (Power Loss Recovery) with usage examples
- FlowGuard 4-layer flow detection explanation
- Smart Rewind with kos-rewind usage examples
- TMC Calibration with kos-calibrate usage
- jschuh/klipper-macros integration note
- Updated feature comparison table with new features per profile

**Step 3: Commit**

```bash
git add pyproject.toml README.md
git commit -m "feat: update package config and docs for v2.0 features"
```

---

### Task 17: Final Integration Test

**Step 1: Run all tests**

```bash
cd C:\linux_ai\KlipperOS-AI
python -m pytest tests/ -v --tb=short
```

Expected: All tests pass.

**Step 2: Verify all files exist**

Check new files: `data/boards.json`, `config/klipper/kos_plr.cfg`, `config/klipper/kos_flowguard.cfg`, `config/klipper/kos_rewind.cfg`, `ai-monitor/flow_guard.py`, `ai-monitor/heater_analyzer.py`, `ai-monitor/extruder_monitor.py`, `tools/kos_plr.py`, `tools/kos_rewind.py`, `tools/kos_calibrate.py`.

**Step 3: Verify CLI tools parse**

```bash
python tools/kos_plr.py --help
python tools/kos_rewind.py --help
python tools/kos_calibrate.py --help
```

**Step 4: Final commit if needed**

```bash
git add -A
git commit -m "chore: KlipperOS-AI v2.0.0 integration verification"
```

# G-Code Macro Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Klipper makro ekosistemini 3 alanda gelistirmek: otomatik kalibrasyon sekansi, AI-tetikli bed mesh ve akilli PRINT_START/PRINT_END.

**Architecture:** Moduler CFG dosyalari (kos_auto_calibrate.cfg, kos_smart_print.cfg) + print_monitor.py degisiklikleri. State machine pattern ile firmware restart'lar arasi kalibrasyon devami. AI monitor, Moonraker API uzerinden otonom kalibrasyon tetikler.

**Tech Stack:** Klipper Jinja2 macros, save_variables, delayed_gcode, Python (pytest)

---

## Task 1: KOS_AUTO_CALIBRATE — State Machine Makrosu

**Files:**
- Create: `config/klipper/kos_auto_calibrate.cfg`
- Modify: `config/klipper/generic.cfg:153` (include satiri ekle)

**Step 1: Create kos_auto_calibrate.cfg with full macro**

```cfg
# =============================================================================
# KlipperOS-AI — Auto Calibration Sequencer
# =============================================================================
# Yeni yazici kurulumunda PID, Input Shaper ve Bed Mesh kalibrasyonunu
# tek komutla sirasiyla calistirir. Her SAVE_CONFIG sonrasi firmware
# restart olur; delayed_gcode ile kaldigi yerden devam eder.
#
# Gereksinimler:
#   - [save_variables] (kos_plr.cfg'de tanimli)
#   - [respond]        (generic.cfg'de tanimli)
#
# Kullanim:
#   KOS_AUTO_CALIBRATE                          ; Tam sekans
#   KOS_AUTO_CALIBRATE SKIP_PID=1               ; PID atla
#   KOS_AUTO_CALIBRATE SKIP_SHAPER=1            ; Input Shaper atla
#   KOS_AUTO_CALIBRATE EXTRUDER_TEMP=230 BED_TEMP=80  ; PETG icin
# =============================================================================

# --- Ana Kalibrasyon Baslat ---
[gcode_macro KOS_AUTO_CALIBRATE]
description: Otomatik kalibrasyon sekansi — PID + Input Shaper + Bed Mesh
gcode:
    {% set EXTRUDER_TEMP = params.EXTRUDER_TEMP|default(210)|float %}
    {% set BED_TEMP = params.BED_TEMP|default(60)|float %}
    {% set SKIP_PID = params.SKIP_PID|default(0)|int %}
    {% set SKIP_SHAPER = params.SKIP_SHAPER|default(0)|int %}

    # Parametreleri kaydet (restart sonrasi kullanilacak)
    SAVE_VARIABLE VARIABLE=kos_cal_extruder_temp VALUE={EXTRUDER_TEMP}
    SAVE_VARIABLE VARIABLE=kos_cal_bed_temp VALUE={BED_TEMP}
    SAVE_VARIABLE VARIABLE=kos_cal_skip_shaper VALUE={SKIP_SHAPER}

    {action_respond_info("KOS: Otomatik kalibrasyon sekansi basliyor...")}

    {% if SKIP_PID == 0 %}
        # Adim 1: PID Extruder
        SAVE_VARIABLE VARIABLE=kos_cal_step VALUE=1
        {action_respond_info("KOS [1/4]: PID extruder kalibrasyonu (%d°C)..." % EXTRUDER_TEMP)}
        PID_CALIBRATE HEATER=extruder TARGET={EXTRUDER_TEMP}
        SAVE_CONFIG  ; restart tetikler -> delayed_gcode devam eder
    {% else %}
        {action_respond_info("KOS: PID atlandi (SKIP_PID=1)")}
        # Shaper veya mesh'e atla
        {% if SKIP_SHAPER == 0 and printer.configfile.config["adxl345"] is defined %}
            SAVE_VARIABLE VARIABLE=kos_cal_step VALUE=3
            {action_respond_info("KOS [3/4]: Input Shaper kalibrasyonu...")}
            SHAPER_CALIBRATE
            SAVE_CONFIG
        {% else %}
            SAVE_VARIABLE VARIABLE=kos_cal_step VALUE=4
            _KOS_CAL_BED_MESH
        {% endif %}
    {% endif %}

# --- Restart Sonrasi Devam ---
[delayed_gcode _KOS_CAL_RESUME]
initial_duration: 8
gcode:
    {% set step = printer.save_variables.variables.kos_cal_step|default(0)|int %}
    {% if step == 0 %}
        # Kalibrasyon sekansi aktif degil — baska bir sey yapma
    {% elif step == 1 %}
        # PID extruder tamamlandi -> PID bed
        {% set bed_temp = printer.save_variables.variables.kos_cal_bed_temp|default(60)|float %}
        SAVE_VARIABLE VARIABLE=kos_cal_step VALUE=2
        {action_respond_info("KOS [2/4]: PID bed kalibrasyonu (%d°C)..." % bed_temp)}
        PID_CALIBRATE HEATER=heater_bed TARGET={bed_temp}
        SAVE_CONFIG
    {% elif step == 2 %}
        # PID bed tamamlandi -> Input Shaper veya Bed Mesh
        {% set skip_shaper = printer.save_variables.variables.kos_cal_skip_shaper|default(0)|int %}
        {% if skip_shaper == 0 and printer.configfile.config["adxl345"] is defined %}
            SAVE_VARIABLE VARIABLE=kos_cal_step VALUE=3
            {action_respond_info("KOS [3/4]: Input Shaper kalibrasyonu...")}
            SHAPER_CALIBRATE
            SAVE_CONFIG
        {% else %}
            {% if skip_shaper == 1 %}
                {action_respond_info("KOS: Input Shaper atlandi (SKIP_SHAPER=1)")}
            {% else %}
                {action_respond_info("KOS: Akselerometre yok — Input Shaper atlandi")}
            {% endif %}
            SAVE_VARIABLE VARIABLE=kos_cal_step VALUE=4
            _KOS_CAL_BED_MESH
        {% endif %}
    {% elif step == 3 %}
        # Input Shaper tamamlandi -> Bed Mesh
        SAVE_VARIABLE VARIABLE=kos_cal_step VALUE=4
        _KOS_CAL_BED_MESH
    {% elif step == 4 %}
        # Bed Mesh tamamlandi -> Sekans bitti
        SAVE_VARIABLE VARIABLE=kos_cal_step VALUE=0
        {action_respond_info("KOS: *** KALIBRASYON TAMAMLANDI! ***")}
        {action_respond_info("KOS: PID, Input Shaper ve Bed Mesh kalibrasyonlari basariyla uygulanmistir.")}
    {% endif %}

# --- Bed Mesh Alt Makro ---
[gcode_macro _KOS_CAL_BED_MESH]
description: Kalibrasyon sekansi icin bed mesh adimi (dahili kullanim)
gcode:
    {% set bed_temp = printer.save_variables.variables.kos_cal_bed_temp|default(60)|float %}
    {action_respond_info("KOS [4/4]: Bed mesh kalibrasyonu...")}
    # Yatak isitma
    {% if bed_temp > 0 %}
        M190 S{bed_temp}
        G4 P60000  ; 1 dk termal stabilizasyon
    {% endif %}
    G28
    {% if printer.configfile.config["probe"] is defined or printer.configfile.config["bltouch"] is defined %}
        BED_MESH_CALIBRATE PROFILE=default
        SAVE_CONFIG
    {% else %}
        {action_respond_info("KOS: Probe yok — bed mesh atlandi. Manuel BED_SCREWS_ADJUST kullanin.")}
        # Probesiz durumda sekansi bitir
        SAVE_VARIABLE VARIABLE=kos_cal_step VALUE=0
        {action_respond_info("KOS: *** KALIBRASYON TAMAMLANDI! ***")}
    {% endif %}

# --- Kalibrasyon Durumu ---
[gcode_macro KOS_CAL_STATUS]
description: Otomatik kalibrasyon sekansi durumunu goster
gcode:
    {% set step = printer.save_variables.variables.kos_cal_step|default(0)|int %}
    {% if step == 0 %}
        {action_respond_info("KOS Kalibrasyon: Aktif degil")}
    {% elif step == 1 %}
        {action_respond_info("KOS Kalibrasyon: Adim 1/4 — PID Extruder tamamlandi, PID Bed bekliyor")}
    {% elif step == 2 %}
        {action_respond_info("KOS Kalibrasyon: Adim 2/4 — PID tamamlandi, Input Shaper bekliyor")}
    {% elif step == 3 %}
        {action_respond_info("KOS Kalibrasyon: Adim 3/4 — Shaper tamamlandi, Bed Mesh bekliyor")}
    {% elif step == 4 %}
        {action_respond_info("KOS Kalibrasyon: Adim 4/4 — Bed Mesh tamamlandi, sonuclama bekliyor")}
    {% endif %}
```

**Step 2: Add include to generic.cfg**

In `config/klipper/generic.cfg`, after line 153 (`[include kos_bed_level.cfg]`), add:

```cfg
[include kos_auto_calibrate.cfg]
```

**Step 3: Verify Klipper config syntax**

Run: `python -c "
# Basit Jinja2 syntax dogrulama
from pathlib import Path
cfg = Path('config/klipper/kos_auto_calibrate.cfg').read_text()
# Jinja2 blok eslesme kontrolu
opens = cfg.count('{%')
closes = cfg.count('%}')
assert opens == closes, f'Jinja2 blok eslesmiyor: {opens} acik, {closes} kapali'
print(f'OK: {opens} Jinja2 blok, hepsi eslesik')
# Makro isimleri
import re
macros = re.findall(r'\[gcode_macro (\w+)\]', cfg)
delayed = re.findall(r'\[delayed_gcode (\w+)\]', cfg)
print(f'Makrolar: {macros}')
print(f'Delayed: {delayed}')
"
`
Expected: OK with 3 macros (KOS_AUTO_CALIBRATE, _KOS_CAL_BED_MESH, KOS_CAL_STATUS) and 1 delayed_gcode (_KOS_CAL_RESUME)

**Step 4: Commit**

```bash
git add config/klipper/kos_auto_calibrate.cfg config/klipper/generic.cfg
git commit -m "feat(config): add KOS_AUTO_CALIBRATE state machine sequencer

PID extruder + PID bed + Input Shaper + Bed Mesh in one command.
State machine via save_variables survives firmware restarts.
delayed_gcode resumes sequence after each SAVE_CONFIG."
```

---

## Task 2: Akilli PRINT_START / PRINT_END Makrolari

**Files:**
- Create: `config/klipper/kos_smart_print.cfg`
- Modify: `config/klipper/generic.cfg:154` (include satiri ekle)

**Step 1: Create kos_smart_print.cfg**

```cfg
# =============================================================================
# KlipperOS-AI — Smart Print Start/End
# =============================================================================
# Slicer'dan tek satirla cagrilir, tum baski hazirligini otomatik yapar:
# yatak isitma, homing, mesh profil yukleme, purge line.
#
# Slicer Start G-code:
#   PRINT_START EXTRUDER_TEMP={material_print_temperature_layer_0} BED_TEMP={material_bed_temperature_layer_0} FILAMENT={material_type}
#
# Slicer End G-code:
#   PRINT_END
#
# NOT: Bu dosya kos_plr.cfg'deki PRINT_END'i override ETMEZ.
# kos_plr.cfg'nin PRINT_END rename_existing kullanir. Bu dosyadaki
# PRINT_START yeni bir makrodur (cakisma yok).
# =============================================================================

[gcode_macro PRINT_START]
description: Akilli baski hazirligi — isitma, homing, mesh, purge
gcode:
    {% set EXTRUDER_TEMP = params.EXTRUDER_TEMP|default(210)|float %}
    {% set BED_TEMP = params.BED_TEMP|default(60)|float %}
    {% set FILAMENT = params.FILAMENT|default("pla")|string|lower %}
    {% set SURFACE = params.SURFACE|default("pei")|string|lower %}
    {% set SOAK_TIME = params.SOAK_TIME|default(60000)|int %}
    {% set PURGE_LENGTH = params.PURGE_LENGTH|default(60)|float %}
    {% set ADAPTIVE_MESH = params.ADAPTIVE_MESH|default(0)|int %}

    {action_respond_info("KOS PRINT_START: Hazirlaniyor...")}
    {action_respond_info("  Extruder: %d°C | Bed: %d°C | Filament: %s | Yuzey: %s" % (EXTRUDER_TEMP, BED_TEMP, FILAMENT, SURFACE))}

    # --- 1. Yatak isitma ---
    {action_respond_info("KOS [1/6]: Yatak isitiliyor (%d°C)..." % BED_TEMP)}
    M140 S{BED_TEMP}        ; Yatak isitmaya basla (beklemeden)
    M104 S150               ; Extruder on-isitma (ooze olmadan)

    # --- 2. Home ---
    {action_respond_info("KOS [2/6]: Homing...")}
    G28

    # --- 3. Yatak sicakligina ulasilmasini bekle + termal soak ---
    M190 S{BED_TEMP}
    {% if SOAK_TIME > 0 %}
        {action_respond_info("KOS: Termal stabilizasyon (%d sn)..." % (SOAK_TIME / 1000))}
        G4 P{SOAK_TIME}
    {% endif %}

    # --- 4. Mesh profil yukle veya adaptif mesh ---
    {% if ADAPTIVE_MESH == 1 %}
        {action_respond_info("KOS [3/6]: Adaptif mesh kalibrasyonu...")}
        {% if printer.configfile.config["probe"] is defined or printer.configfile.config["bltouch"] is defined %}
            BED_MESH_CALIBRATE ADAPTIVE=1
        {% else %}
            {action_respond_info("KOS: Probe yok — adaptif mesh atiandi")}
        {% endif %}
    {% else %}
        # Filament+yuzey combo ile profil dene
        {% set mesh_name = SURFACE ~ "_" ~ FILAMENT %}
        {% set mesh_profiles = printer.bed_mesh.profiles|default({}) %}
        {% if mesh_name in mesh_profiles %}
            {action_respond_info("KOS [3/6]: Mesh profil yukleniyor: %s" % mesh_name)}
            BED_MESH_PROFILE LOAD={mesh_name}
        {% elif "default" in mesh_profiles %}
            {action_respond_info("KOS [3/6]: '%s' profili yok, default yukleniyor" % mesh_name)}
            BED_MESH_PROFILE LOAD=default
        {% elif mesh_profiles|length > 0 %}
            {% set first = mesh_profiles.keys()|list|first %}
            {action_respond_info("KOS [3/6]: Default yok, '%s' yukleniyor" % first)}
            BED_MESH_PROFILE LOAD={first}
        {% else %}
            {action_respond_info("KOS UYARI: Hic mesh profili yok! KOS_BED_LEVEL_CALIBRATE onerisi.")}
        {% endif %}
    {% endif %}

    # --- 5. Mesh yas kontrolu ---
    {action_respond_info("KOS [4/6]: Mesh yas kontrolu...")}
    KOS_BED_LEVEL_CHECK

    # --- 6. Extruder hedef sicakliga isit ---
    {action_respond_info("KOS [5/6]: Extruder isitiliyor (%d°C)..." % EXTRUDER_TEMP)}
    M109 S{EXTRUDER_TEMP}

    # --- 7. Purge line ---
    {action_respond_info("KOS [6/6]: Purge line...")}
    G90
    G92 E0
    G1 X5 Y5 F3000                          ; Baslangic noktasi
    G1 Z0.3 F600                             ; Ilk katman yuksekligi
    G1 X{5 + PURGE_LENGTH} Y5 E{PURGE_LENGTH * 0.15} F1500   ; Purge hatti
    G1 Z1.0 F600                             ; Z hop
    G92 E0                                   ; Extruder sifirla

    {action_respond_info("KOS: *** BASKI HAZIR ***")}

# --- PRINT_END override ---
# kos_plr.cfg zaten PRINT_END'i override eder (rename_existing: _KM_PRINT_END).
# Biz onu tekrar override ederek hem PLR temizligi hem de akilli bitis sagliyoruz.
[gcode_macro _KOS_SMART_PRINT_END]
description: Akilli baski bitisi — retract, park, sogutma
gcode:
    {action_respond_info("KOS PRINT_END: Baski tamamlaniyor...")}

    # --- 1. Retract ---
    G91
    G1 E-2 F1800            ; Retract
    G1 Z10 F600             ; Z hop

    # --- 2. Park pozisyonu ---
    G90
    {% set max_y = printer.toolhead.axis_maximum.y|default(220)|float %}
    G1 X0 Y{max_y - 5} F6000     ; Yatak one, parca sunumu

    # --- 3. Sogutma ---
    TURN_OFF_HEATERS
    M107                    ; Fan kapat

    # --- 4. PLR temizle ---
    KOS_PLR_CLEAR

    # --- 5. Stepperlar ---
    M84                     ; Stepperlari devre disi birak

    {action_respond_info("KOS: *** BASKI TAMAMLANDI ***")}
```

**Step 2: Wire PRINT_END through kos_plr.cfg pattern**

The existing `kos_plr.cfg` line 124-128 has:
```cfg
[gcode_macro PRINT_END]
rename_existing: _KM_PRINT_END
gcode:
    KOS_PLR_CLEAR
    _KM_PRINT_END
```

We need to update this to call our smart end instead. Modify `config/klipper/kos_plr.cfg:124-128`:

```cfg
[gcode_macro PRINT_END]
rename_existing: _KM_PRINT_END
gcode:
    _KOS_SMART_PRINT_END
    _KM_PRINT_END
```

This way: PRINT_END -> _KOS_SMART_PRINT_END (retract, park, heaters, PLR clear, steppers) -> _KM_PRINT_END (jschuh cleanup)

**Step 3: Add include to generic.cfg**

In `config/klipper/generic.cfg`, after the kos_auto_calibrate include, add:

```cfg
[include kos_smart_print.cfg]
```

**Step 4: Remove duplicate KOS_PID_CALIBRATE from generic.cfg**

`generic.cfg:165-173` has `KOS_PID_CALIBRATE` which is now superseded by `KOS_AUTO_CALIBRATE`. Remove it to avoid confusion. The PID-only use case is covered by `KOS_AUTO_CALIBRATE SKIP_SHAPER=1`.

Lines to remove from `generic.cfg`:
```
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

**Step 5: Verify syntax**

Run same Jinja2 block check as Task 1 on `kos_smart_print.cfg`.

**Step 6: Commit**

```bash
git add config/klipper/kos_smart_print.cfg config/klipper/kos_plr.cfg config/klipper/generic.cfg
git commit -m "feat(config): add smart PRINT_START/PRINT_END macros

PRINT_START: bed heat + home + mesh profile load + extruder heat + purge.
Accepts slicer params: EXTRUDER_TEMP, BED_TEMP, FILAMENT, SURFACE.
PRINT_END: retract + park + cool + PLR clear + steppers off.
Removes standalone KOS_PID_CALIBRATE (superseded by KOS_AUTO_CALIBRATE)."
```

---

## Task 3: AI-Tetikli Otomatik Bed Mesh — Test

**Files:**
- Modify: `ai-monitor/print_monitor.py:287-334` (init), `795-850` (pre/post print)
- Test: `tests/test_print_monitor_auto_recal.py` (create)

**Step 1: Write failing tests**

Create `tests/test_print_monitor_auto_recal.py`:

```python
"""AI-tetikli otomatik bed mesh recalibration testleri."""
import time
from unittest.mock import MagicMock, patch
import pytest


class FakeMoonraker:
    """Moonraker API mock."""

    def __init__(self):
        self.sent_gcodes = []
        self.notifications = []
        self._is_printing = False
        self._bed_mesh = {"profile_name": "default", "mesh_matrix": [[0.1, 0.2], [0.3, 0.4]]}

    def send_gcode(self, cmd):
        self.sent_gcodes.append(cmd)
        return True

    def send_notification(self, msg):
        self.notifications.append(msg)

    def is_printing(self):
        return self._is_printing

    def get_bed_mesh(self):
        return self._bed_mesh

    def pause_print(self):
        return True

    def resume_print(self):
        return True


class FakeDriftDetector:
    """DriftDetector mock."""

    def __init__(self):
        self._drift_report = MagicMock()
        self._drift_report.recommendation = "ok"
        self._drift_report.max_point_drift = 0.02
        self._trend = MagicMock()
        self._trend.trend_direction = "stable"
        self._trend.avg_drift_per_day = 0.001

    def check_drift(self, profile, matrix):
        return self._drift_report

    def get_drift_trend(self, profile):
        return self._trend

    def add_snapshot(self, profile, matrix):
        pass


class TestAutoRecalibrate:
    """AUTO_RECALIBRATE davranisi."""

    def test_pre_print_recalibrate_when_enabled(self):
        """Drift recalibrate + AUTO_RECALIBRATE=1 -> G-code gonderir."""
        from print_monitor import PrintMonitor

        with patch.dict("os.environ", {"AUTO_RECALIBRATE": "1"}):
            mon = PrintMonitor.__new__(PrintMonitor)
            mon.moonraker = FakeMoonraker()
            mon.drift_detector = FakeDriftDetector()
            mon.drift_detector._drift_report.recommendation = "recalibrate"
            mon._auto_recalibrate = True
            mon._last_auto_recal_date = ""

            mon._bed_level_pre_print_check()

            assert any("KOS_BED_LEVEL_CALIBRATE" in g for g in mon.moonraker.sent_gcodes)

    def test_pre_print_no_recalibrate_when_disabled(self):
        """Drift recalibrate + AUTO_RECALIBRATE=0 -> sadece bildirim."""
        from print_monitor import PrintMonitor

        with patch.dict("os.environ", {"AUTO_RECALIBRATE": "0"}):
            mon = PrintMonitor.__new__(PrintMonitor)
            mon.moonraker = FakeMoonraker()
            mon.drift_detector = FakeDriftDetector()
            mon.drift_detector._drift_report.recommendation = "recalibrate"
            mon._auto_recalibrate = False
            mon._last_auto_recal_date = ""

            mon._bed_level_pre_print_check()

            assert not any("KOS_BED_LEVEL_CALIBRATE" in g for g in mon.moonraker.sent_gcodes)
            assert len(mon.moonraker.notifications) > 0

    def test_post_print_auto_recalibrate_on_worsening(self):
        """Post-print worsening trend + idle + AUTO_RECALIBRATE=1 -> tetikle."""
        from print_monitor import PrintMonitor

        mon = PrintMonitor.__new__(PrintMonitor)
        mon.moonraker = FakeMoonraker()
        mon.moonraker._is_printing = False
        mon.drift_detector = FakeDriftDetector()
        mon.drift_detector._trend.trend_direction = "worsening"
        mon.drift_detector._trend.avg_drift_per_day = 0.015
        mon.drift_detector._trend.forecast_days_to_recalibrate = 3.0
        mon._auto_recalibrate = True
        mon._last_auto_recal_date = ""
        mon._bed_level_enabled = True

        mon._bed_level_post_print()

        assert any("KOS_BED_LEVEL_CALIBRATE" in g for g in mon.moonraker.sent_gcodes)

    def test_daily_limit_prevents_second_recalibration(self):
        """Ayni gun icinde 2. otomatik kalibrasyon engellenir."""
        from print_monitor import PrintMonitor

        today = time.strftime("%Y-%m-%d")
        mon = PrintMonitor.__new__(PrintMonitor)
        mon.moonraker = FakeMoonraker()
        mon.drift_detector = FakeDriftDetector()
        mon.drift_detector._drift_report.recommendation = "recalibrate"
        mon._auto_recalibrate = True
        mon._last_auto_recal_date = today  # Bugun zaten yapildi

        mon._bed_level_pre_print_check()

        assert not any("KOS_BED_LEVEL_CALIBRATE" in g for g in mon.moonraker.sent_gcodes)
```

**Step 2: Run tests to verify they fail**

Run: `cd ai-monitor && python -m pytest ../tests/test_print_monitor_auto_recal.py -v`
Expected: FAIL — `_auto_recalibrate` attribute yok, `_last_auto_recal_date` yok

**Step 3: Implement auto-recalibrate in print_monitor.py**

Add to `__init__` (after line 334):

```python
        # Auto Recalibrate (opt-in)
        self._auto_recalibrate = os.environ.get("AUTO_RECALIBRATE", "0").lower() in ("1", "true", "yes", "on")
        self._last_auto_recal_date = ""  # YYYY-MM-DD — gunde max 1 kez
```

Modify `_bed_level_pre_print_check` (line 810, after `if report.recommendation == "recalibrate":`):

Replace the existing recalibrate block with:

```python
            if report.recommendation == "recalibrate":
                if self._auto_recalibrate and self._last_auto_recal_date != time.strftime("%Y-%m-%d"):
                    logger.warning("Bed Level: drift %.3fmm — otomatik kalibrasyon tetikleniyor", report.max_point_drift)
                    self.moonraker.send_notification(
                        f"KOS: Kritik drift ({report.max_point_drift:.2f}mm). "
                        "Otomatik kalibrasyon baslatiliyor..."
                    )
                    self.moonraker.send_gcode("KOS_BED_LEVEL_CALIBRATE")
                    self._last_auto_recal_date = time.strftime("%Y-%m-%d")
                else:
                    self.moonraker.send_notification(
                        f"KOS: Kritik bed level drift ({report.max_point_drift:.2f}mm). "
                        "Yeniden kalibrasyon onerilir."
                    )
                    logger.warning("Bed Level: drift %.3fmm — recalibrate", report.max_point_drift)
```

Modify `_bed_level_post_print` (after trend worsening notification block, line 850):

Add after the existing logger.warning:

```python
                # Otomatik kalibrasyon (idle ise)
                if self._auto_recalibrate and self._last_auto_recal_date != time.strftime("%Y-%m-%d"):
                    if not self.moonraker.is_printing():
                        logger.info("Bed Level: post-print otomatik kalibrasyon tetikleniyor")
                        self.moonraker.send_gcode("KOS_BED_LEVEL_CALIBRATE")
                        self._last_auto_recal_date = time.strftime("%Y-%m-%d")
```

**Step 4: Run tests to verify they pass**

Run: `cd ai-monitor && python -m pytest ../tests/test_print_monitor_auto_recal.py -v`
Expected: 4 passed

**Step 5: Run full test suite for regression**

Run: `python -m pytest tests/ -v --tb=short`
Expected: 485 passed (481 + 4 new)

**Step 6: Commit**

```bash
git add ai-monitor/print_monitor.py tests/test_print_monitor_auto_recal.py
git commit -m "feat(ai): add auto-recalibrate on critical bed level drift

AUTO_RECALIBRATE=1 env var enables autonomous calibration.
Pre-print: triggers KOS_BED_LEVEL_CALIBRATE on critical drift.
Post-print: triggers on worsening trend when printer is idle.
Daily limit: max 1 auto-recalibration per day (spam prevention)."
```

---

## Task 4: Printer-Specific Config Templates Guncelleme

**Files:**
- Modify: `config/klipper/ender3.cfg`
- Modify: `config/klipper/ender3v2.cfg`
- Modify: `config/klipper/voron.cfg`

**Step 1: Add includes to all printer templates**

Each printer config has the same include block as generic.cfg. Add the 2 new includes to each:

After `[include kos_bed_level.cfg]` in each file, add:
```cfg
[include kos_auto_calibrate.cfg]
[include kos_smart_print.cfg]
```

Also remove `KOS_PID_CALIBRATE` from each file (same as Task 2 Step 4 for generic.cfg).

**Step 2: Adjust PRINT_END in kos_plr.cfg for all printers**

Already done in Task 2 Step 2 — kos_plr.cfg is shared.

**Step 3: Commit**

```bash
git add config/klipper/ender3.cfg config/klipper/ender3v2.cfg config/klipper/voron.cfg
git commit -m "feat(config): add auto-calibrate and smart-print includes to all printer templates

Ender 3, Ender 3 V2, and Voron 2.4 templates now include
kos_auto_calibrate.cfg and kos_smart_print.cfg.
Removes standalone KOS_PID_CALIBRATE from each template."
```

---

## Task 5: Full Verification

**Step 1: Jinja2 syntax check all new cfg files**

Run:
```bash
python -c "
from pathlib import Path
import re
for cfg_file in ['config/klipper/kos_auto_calibrate.cfg', 'config/klipper/kos_smart_print.cfg']:
    cfg = Path(cfg_file).read_text()
    opens = cfg.count('{%')
    closes = cfg.count('%}')
    assert opens == closes, f'{cfg_file}: Jinja2 eslesmiyor: {opens}/{closes}'
    macros = re.findall(r'\[gcode_macro (\w+)\]', cfg)
    delayed = re.findall(r'\[delayed_gcode (\w+)\]', cfg)
    print(f'{cfg_file}: OK — {len(macros)} makro, {len(delayed)} delayed')
print('Tum dosyalar gecerli.')
"
```

**Step 2: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: 485+ passed, 0 failures

**Step 3: Verify git log**

Run: `git log --oneline -5`
Expected: 4 new commits (Tasks 1-4)

**Step 4: List all new/modified files**

Run: `git diff --name-only HEAD~4`
Expected files:
- `config/klipper/kos_auto_calibrate.cfg` (new)
- `config/klipper/kos_smart_print.cfg` (new)
- `config/klipper/generic.cfg` (modified)
- `config/klipper/kos_plr.cfg` (modified)
- `config/klipper/ender3.cfg` (modified)
- `config/klipper/ender3v2.cfg` (modified)
- `config/klipper/voron.cfg` (modified)
- `ai-monitor/print_monitor.py` (modified)
- `tests/test_print_monitor_auto_recal.py` (new)

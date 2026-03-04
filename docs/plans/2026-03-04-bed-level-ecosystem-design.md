# KOS Bed Level Ecosystem — Design Document

**Date**: 2026-03-04
**Version**: v3.0
**Status**: Approved
**Approach**: Hybrid (Yaklaşım C) — 3 katman: AI Monitor / Klipper Config / Installer

## Overview

KlipperOS-AI'ya kapsamlı bed leveling ekosistemi eklenmesi. 5 bileşen:

1. AI-destekli mesh analiz + vida ayarı önerisi
2. Akıllı mesh profil yönetimi (filament+yüzey combo)
3. Baskılar arası bed level drift algılama
4. Printer config şablonlarına bed leveling entegrasyonu
5. Installer'a bed leveling wizard adımı

Tüm yazıcı tipleri eşit öncelikli: problu (BLTouch, Inductive, Klicky) ve probsuz (manuel vida ayarı).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AI Monitor Layer                       │
│  ai-monitor/bed_level_analyzer.py                        │
│  ├── MeshAnalyzer (mesh veri analizi, vida önerisi)      │
│  ├── ProfileManager (filament+yüzey profil seçimi)       │
│  └── DriftDetector (drift trend, yeniden kalibrasyon)    │
├─────────────────────────────────────────────────────────┤
│                   Klipper Macro Layer                     │
│  config/klipper/kos_bed_level.cfg                        │
│  ├── KOS_BED_LEVEL_CALIBRATE (ana kalibrasyon)           │
│  ├── KOS_BED_LEVEL_CHECK (baskı öncesi kontrol)          │
│  ├── KOS_MESH_PROFILE_SAVE/LOAD (profil yönetimi)       │
│  ├── KOS_SCREW_ADJUST (vida ayarı wrapper)               │
│  └── KOS_ADAPTIVE_MESH (adaptif mesh)                    │
├─────────────────────────────────────────────────────────┤
│                    Installer Layer                        │
│  packages/installer/steps/bed_level.py                   │
│  ├── Probe tipi seçimi                                   │
│  ├── Offset girişi                                       │
│  ├── Mesh ayarları                                       │
│  └── Config yazımı                                       │
└─────────────────────────────────────────────────────────┘
```

## Component 1: AI Bed Level Analyzer

**File**: `ai-monitor/bed_level_analyzer.py`
**Estimated**: ~350 lines

### Classes

```python
class MeshAnalyzer:
    analyze_mesh() -> MeshReport        # min/max/range/std_dev
    suggest_screw_turns() -> List[ScrewAdjustment]  # vida önerileri
    detect_patterns() -> BedPattern     # bowl/dome/tilt/twist

class ProfileManager:
    auto_select_profile() -> str        # filament+yüzey combo
    save_profile() -> None              # mesh + metadata kaydet
    compare_profiles() -> ProfileDelta  # iki profil arası delta

class DriftDetector:
    check_drift() -> DriftReport        # mevcut vs referans
    get_drift_trend() -> TrendResult    # zaman serisi (TrendAnalyzer)
    should_recalibrate() -> bool        # eşik aşıldı mı?
```

### Data Structures

```python
@dataclass
class MeshReport:
    mesh_min: float
    mesh_max: float
    mesh_range: float
    mesh_mean: float
    std_dev: float
    pattern: str          # "bowl" / "dome" / "tilt_left" / "tilt_right" / "twist" / "flat"
    screw_adjustments: List[ScrewAdjustment]

@dataclass
class ScrewAdjustment:
    name: str             # "Sol Ön"
    x: float
    y: float
    offset_mm: float      # referansa göre fark
    turns: float          # gerekli tur (0.25 = 1/4 tur)
    direction: str        # "CW" / "CCW"
    description: str      # "CW 1/4 tur (0.12mm yüksek)"

@dataclass
class MeshSnapshot:
    timestamp: float
    profile_name: str
    mesh_matrix: List[List[float]]
    bed_temp: float
    ambient_temp: Optional[float]
    mesh_range: float
    mesh_mean: float
    mesh_std_dev: float

@dataclass
class DriftReport:
    current_range: float
    reference_range: float
    max_point_drift: float
    mean_drift: float
    drift_direction: str  # "worsening" / "stable" / "improving"
    recommendation: str   # "ok" / "recalibrate" / "check_screws"
    days_since_calibration: float
```

### Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `drift_threshold_mm` | 0.05 | Uyarı eşiği |
| `recalibrate_threshold_mm` | 0.10 | Yeniden kalibrasyon eşiği |
| `max_mesh_range_mm` | 0.30 | Mesh min-max fark sınırı |
| `screw_pitch_mm` | 0.50 | M3 vida hatve mesafesi |
| `trend_window_days` | 30 | Drift trend penceresi |
| `max_z_adjust_mm` | 0.05 | Otomatik Z offset sınırı |

### Screw Adjustment Algorithm

```
offset_mm = corner_mesh_value - reference_value
turns = offset_mm / screw_pitch_mm
direction = "CW" if offset_mm > 0 else "CCW"
description = f"{direction} {format_turns(turns)} ({abs(offset_mm):.2f}mm {'yüksek' if offset_mm > 0 else 'düşük'})"
```

## Component 2: Klipper Macro File

**File**: `config/klipper/kos_bed_level.cfg`
**Estimated**: ~180 lines

### Macros

| Macro | Parameters | Default |
|-------|-----------|---------|
| `KOS_BED_LEVEL_CALIBRATE` | `PROFILE=`, `TEMP_BED=` | "default", 0 |
| `KOS_MESH_PROFILE_SAVE` | `SURFACE=`, `FILAMENT=`, `NAME=` | "pei", "pla", auto |
| `KOS_MESH_PROFILE_LOAD` | `NAME=`, `SURFACE=`, `FILAMENT=` | auto-detect |
| `KOS_BED_LEVEL_CHECK` | `MAX_AGE=`, `MAX_DRIFT=` | 72 (saat), 0.10 |
| `KOS_SCREW_ADJUST` | — | — |
| `KOS_ADAPTIVE_MESH` | `AREA_START=`, `AREA_END=` | slicer'dan |

### Profile Naming

```
{surface}_{filament} → "pei_pla", "glass_petg", "textured_abs"
```

### save_variables Metadata

```ini
[Variables]
kos_mesh_{profile}_timestamp = 1709510400
kos_mesh_{profile}_range = 0.08
kos_mesh_{profile}_temp_bed = 60
```

### START_PRINT Hook

```
KOS_BED_LEVEL_CHECK → aktif mesh kontrol → yoksa yükle/uyar
KOS_ADAPTIVE_MESH   → (opsiyonel) baskı alanına göre mesh
```

## Component 3: Config Template Updates

### Changes per file

| File | Added Sections | Lines |
|------|---------------|-------|
| `ender3.cfg` | `[bed_screws]`, `[screws_tilt_adjust]`(comment), `[safe_z_home]`(comment), `[include kos_bed_level.cfg]` | +25 |
| `ender3v2.cfg` | Same as ender3 | +25 |
| `generic.cfg` | `[bed_screws]`, `[probe]`(comment), `[safe_z_home]`(comment), `[screws_tilt_adjust]`(comment), `[bed_mesh]`(comment), `[include]` | +40 |
| `voron.cfg` | `[safe_z_home]`, `[include kos_bed_level.cfg]` | +15 |

### config_manager.py Whitelist Additions

```python
"bed_mesh": ["mesh_min", "mesh_max", "probe_count", "algorithm",
             "bicubic_tension", "mesh_pps", "fade_start", "fade_end",
             "adaptive_margin", "zero_reference_position"],
"probe": ["z_offset", "samples", "samples_tolerance", "speed", "lift_speed"],
"safe_z_home": ["home_xy_position"],
```

## Component 4: Installer Bed Level Wizard

**File**: `packages/installer/steps/bed_level.py`
**Estimated**: ~200 lines

### Wizard Flow

1. **Probe Type** → None / BLTouch / Inductive / Klicky-Tap
2. **Probe Offset** → X, Y offset (probe varsa)
3. **Bed Size Confirm** → hardware step'ten algılanan boyut
4. **Screw Positions** → bilinen yazıcı=otomatik, bilinmeyen=soru
5. **Mesh Settings** → 3x3 / 5x5 / 7x7
6. **Summary & Write** → config yazımı + first boot note

Every step has `<Atla>` (Skip) button. Skipped steps write commented config sections.

### Installer Step Order

```python
STEPS = [
    WelcomeStep, HardwareStep, ProfileStep, NetworkStep,
    UserSetupStep, ServicesStep,
    BedLevelStep,      # NEW — between services and install
    InstallStep, CompleteStep,
]
```

## Component 5: AI Monitor Integration

### Hook Points in print_monitor.py

| Event | Method | Action |
|-------|--------|--------|
| `on_print_start()` | `pre_print_check()` | Mesh yaşı + drift kontrol |
| `on_layer_change(1)` | `first_layer_check()` | Z offset sapma analizi |
| `on_print_end()` | `post_print_snapshot()` | Mesh snapshot + drift trend |
| `periodic_check()` | `check_thermal_drift()` | Termal genleşme izleme (opsiyonel) |

### Notifications (Moonraker)

| Condition | Level | Message |
|-----------|-------|---------|
| No mesh | WARNING | "Aktif bed mesh yok. KOS_BED_LEVEL_CALIBRATE çalıştırın." |
| Mesh old (>72h) | INFO | "Bed mesh 3 günden eski. Yeniden kalibrasyon önerilir." |
| Drift > 0.05mm | WARNING | "Bed level drift algılandı. Vida kontrolü önerilir." |
| Drift > 0.10mm | ERROR | "Kritik bed level drift. Baskı kalitesi etkilenebilir." |
| First layer offset | INFO | "İlk katman Z offset önerisi: +0.02mm" |

### Safety Rules

- AI **never** auto-starts mesh calibration (physical movement required)
- AI **only recommends**, no SET_GCODE_OFFSET without user approval
- Z offset fine-tune limit: **max ±0.05mm**
- No mesh changes during active print — monitoring and reporting only

### Storage

```
/var/lib/klipperos-ai/
├── maintenance.json          # existing
├── bed_level_history.json    # NEW — mesh snapshots
└── bed_level_profiles.json   # NEW — profile metadata
```

## File Summary

| # | Component | File | Lines |
|---|-----------|------|-------|
| 1 | AI Analyzer | `ai-monitor/bed_level_analyzer.py` | ~350 |
| 2 | Klipper Macro | `config/klipper/kos_bed_level.cfg` | ~180 |
| 3 | Config Templates | 4 cfg files + config_manager.py | ~105 |
| 4 | Installer Wizard | `packages/installer/steps/bed_level.py` | ~200 |
| 5 | Monitor Integration | `print_monitor.py` changes | ~60 |
| 6 | Tests | `tests/test_bed_level_analyzer.py` | ~250 |
| **Total** | **3 new + 6 modified files** | **~1145 lines** |

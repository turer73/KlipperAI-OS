# KOS Bed Level Ecosystem — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add comprehensive bed leveling ecosystem to KlipperOS-AI with AI mesh analysis, smart profile management, drift detection, config templates, and installer wizard.

**Architecture:** Hybrid 3-layer approach — AI Monitor (`bed_level_analyzer.py`), Klipper Macros (`kos_bed_level.cfg`), Installer Step (`bed_level.py`). Each layer works independently; AI layer adds intelligence on top of the macro layer.

**Tech Stack:** Python 3.9+, Klipper Jinja2 macros, whiptail TUI, Moonraker REST API, pytest

**Design Doc:** `docs/plans/2026-03-04-bed-level-ecosystem-design.md`

---

## Task 1: AI Bed Level Analyzer — Data Structures & MeshAnalyzer

**Files:**
- Create: `ai-monitor/bed_level_analyzer.py`
- Create: `tests/test_bed_level_analyzer.py`

**Step 1: Write failing tests for data structures and MeshAnalyzer**

```python
# tests/test_bed_level_analyzer.py
"""Tests for KOS Bed Level Analyzer."""
import pytest
import math

# Will import from ai-monitor — handle both import styles
try:
    from bed_level_analyzer import (
        MeshReport, ScrewAdjustment, MeshSnapshot, DriftReport,
        MeshAnalyzer, ProfileManager, DriftDetector,
    )
except ImportError:
    from ai_monitor.bed_level_analyzer import (
        MeshReport, ScrewAdjustment, MeshSnapshot, DriftReport,
        MeshAnalyzer, ProfileManager, DriftDetector,
    )


# --- MeshAnalyzer Tests ---

class TestMeshAnalyzer:
    """MeshAnalyzer: mesh verisi analiz eder, vida onerisi cikarir."""

    def test_analyze_flat_mesh(self):
        """Duz yatak: range ~0, pattern=flat."""
        mesh = [[0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0]]
        analyzer = MeshAnalyzer(screw_positions=[
            {"name": "Sol On", "x": 30, "y": 30},
            {"name": "Sag On", "x": 200, "y": 30},
            {"name": "Sag Arka", "x": 200, "y": 200},
            {"name": "Sol Arka", "x": 30, "y": 200},
        ])
        report = analyzer.analyze_mesh(mesh)
        assert report.mesh_range == pytest.approx(0.0, abs=0.001)
        assert report.pattern == "flat"

    def test_analyze_bowl_mesh(self):
        """Cukur yatak: kenarlar yuksek, orta dusuk."""
        mesh = [[0.10, 0.05, 0.10],
                [0.05, -0.10, 0.05],
                [0.10, 0.05, 0.10]]
        analyzer = MeshAnalyzer(screw_positions=[
            {"name": "Sol On", "x": 30, "y": 30},
            {"name": "Sag On", "x": 200, "y": 30},
            {"name": "Sag Arka", "x": 200, "y": 200},
            {"name": "Sol Arka", "x": 30, "y": 200},
        ])
        report = analyzer.analyze_mesh(mesh)
        assert report.mesh_range == pytest.approx(0.20, abs=0.01)
        assert report.pattern == "bowl"

    def test_analyze_tilt_mesh(self):
        """Egik yatak: bir taraf yuksek."""
        mesh = [[0.20, 0.20, 0.20],
                [0.10, 0.10, 0.10],
                [0.00, 0.00, 0.00]]
        analyzer = MeshAnalyzer(screw_positions=[
            {"name": "Sol On", "x": 30, "y": 30},
            {"name": "Sag On", "x": 200, "y": 30},
            {"name": "Sag Arka", "x": 200, "y": 200},
            {"name": "Sol Arka", "x": 30, "y": 200},
        ])
        report = analyzer.analyze_mesh(mesh)
        assert report.mesh_range == pytest.approx(0.20, abs=0.01)
        assert "tilt" in report.pattern

    def test_suggest_screw_turns(self):
        """Vida onerisi: offset / pitch = tur sayisi."""
        mesh = [[0.25, 0.0, 0.0],
                [0.0,  0.0, 0.0],
                [0.0,  0.0, 0.0]]
        analyzer = MeshAnalyzer(
            screw_positions=[
                {"name": "Sol On", "x": 30, "y": 30},
                {"name": "Sag On", "x": 200, "y": 30},
                {"name": "Sag Arka", "x": 200, "y": 200},
                {"name": "Sol Arka", "x": 30, "y": 200},
            ],
            screw_pitch_mm=0.50,
        )
        report = analyzer.analyze_mesh(mesh)
        # Sol On vidasi 0.25mm yuksek -> CW 0.5 tur
        sol_on = [s for s in report.screw_adjustments if s.name == "Sol On"][0]
        assert sol_on.direction == "CW"
        assert sol_on.turns == pytest.approx(0.5, abs=0.05)

    def test_mesh_statistics(self):
        """Mesh istatistikleri: min, max, mean, std_dev."""
        mesh = [[0.1, 0.2],
                [0.3, 0.4]]
        analyzer = MeshAnalyzer(screw_positions=[])
        report = analyzer.analyze_mesh(mesh)
        assert report.mesh_min == pytest.approx(0.1)
        assert report.mesh_max == pytest.approx(0.4)
        assert report.mesh_mean == pytest.approx(0.25)
        assert report.std_dev > 0
```

**Step 2: Run tests to verify they fail**

Run: `cd /c/linux_ai/KlipperOS-AI && python -m pytest tests/test_bed_level_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement data structures and MeshAnalyzer**

```python
# ai-monitor/bed_level_analyzer.py
"""
KlipperOS-AI — Bed Level Analyzer
==================================
AI-destekli bed mesh analizi, vida onerisi, profil yonetimi ve drift algilama.

Moonraker API uzerinden bed_mesh verisini okur, analiz eder,
kullaniciya vida ayari ve yeniden kalibrasyon onerileri sunar.

Depolama: /var/lib/klipperos-ai/bed_level_history.json
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger("klipperos-ai.bed-level")

# --- Constants ---
STATE_PATH = Path("/var/lib/klipperos-ai/bed_level_history.json")
DRIFT_THRESHOLD_MM = 0.05
RECALIBRATE_THRESHOLD_MM = 0.10
MAX_MESH_RANGE_MM = 0.30
DEFAULT_SCREW_PITCH_MM = 0.50  # M3 standard
MAX_Z_ADJUST_MM = 0.05
TREND_WINDOW_DAYS = 30
MAX_SNAPSHOTS = 200
MESH_AGE_WARNING_HOURS = 72


# --- Data Structures ---

@dataclass
class ScrewAdjustment:
    """Tek bir vida icin ayar onerisi."""
    name: str
    x: float
    y: float
    offset_mm: float
    turns: float
    direction: str      # "CW" / "CCW"
    description: str

    @staticmethod
    def format_turns(turns: float) -> str:
        """Tur sayisini okunabilir formata cevir: 1/4, 1/2, 3/4, 1, 1.5 vb."""
        abs_turns = abs(turns)
        if abs_turns < 0.125:
            return "< 1/8 tur"
        if abs_turns < 0.375:
            return "1/4 tur"
        if abs_turns < 0.625:
            return "1/2 tur"
        if abs_turns < 0.875:
            return "3/4 tur"
        if abs_turns < 1.25:
            return "1 tur"
        return f"{abs_turns:.1f} tur"


@dataclass
class MeshReport:
    """Mesh analiz raporu."""
    mesh_min: float = 0.0
    mesh_max: float = 0.0
    mesh_range: float = 0.0
    mesh_mean: float = 0.0
    std_dev: float = 0.0
    pattern: str = "flat"
    screw_adjustments: List[ScrewAdjustment] = field(default_factory=list)


@dataclass
class MeshSnapshot:
    """Mesh durumunun zaman damgali anlık goruntusu."""
    timestamp: float = 0.0
    profile_name: str = ""
    mesh_matrix: List[List[float]] = field(default_factory=list)
    bed_temp: float = 0.0
    ambient_temp: Optional[float] = None
    mesh_range: float = 0.0
    mesh_mean: float = 0.0
    mesh_std_dev: float = 0.0


@dataclass
class DriftReport:
    """Drift analiz raporu."""
    current_range: float = 0.0
    reference_range: float = 0.0
    max_point_drift: float = 0.0
    mean_drift: float = 0.0
    drift_direction: str = "stable"
    recommendation: str = "ok"
    days_since_calibration: float = 0.0


# --- MeshAnalyzer ---

class MeshAnalyzer:
    """Bed mesh verisini analiz eder, vida onerisi cikarir."""

    def __init__(
        self,
        screw_positions: List[Dict],
        screw_pitch_mm: float = DEFAULT_SCREW_PITCH_MM,
        mesh_min_coord: tuple = (0, 0),
        mesh_max_coord: tuple = (235, 235),
    ):
        self.screw_positions = screw_positions
        self.screw_pitch_mm = screw_pitch_mm
        self.mesh_min_coord = mesh_min_coord
        self.mesh_max_coord = mesh_max_coord

    def analyze_mesh(self, mesh: List[List[float]]) -> MeshReport:
        """Mesh matrisini analiz et, rapor dondur."""
        flat = [v for row in mesh for v in row]
        if not flat:
            return MeshReport()

        mesh_min = min(flat)
        mesh_max = max(flat)
        mesh_range = mesh_max - mesh_min
        mesh_mean = sum(flat) / len(flat)
        variance = sum((v - mesh_mean) ** 2 for v in flat) / len(flat)
        std_dev = math.sqrt(variance)

        pattern = self._detect_pattern(mesh, mesh_mean)
        adjustments = self._suggest_screw_turns(mesh, mesh_mean)

        return MeshReport(
            mesh_min=mesh_min,
            mesh_max=mesh_max,
            mesh_range=mesh_range,
            mesh_mean=mesh_mean,
            std_dev=std_dev,
            pattern=pattern,
            screw_adjustments=adjustments,
        )

    def _detect_pattern(self, mesh: List[List[float]], mean: float) -> str:
        """Mesh pattern algilama: flat/bowl/dome/tilt_x/tilt_y/twist."""
        rows = len(mesh)
        cols = len(mesh[0]) if rows else 0
        if rows < 2 or cols < 2:
            return "flat"

        flat = [v for row in mesh for v in row]
        mesh_range = max(flat) - min(flat)
        if mesh_range < 0.03:
            return "flat"

        # Kose degerleri
        corners = [mesh[0][0], mesh[0][-1], mesh[-1][0], mesh[-1][-1]]
        corner_mean = sum(corners) / 4

        # Orta deger(ler)
        mid_r, mid_c = rows // 2, cols // 2
        center = mesh[mid_r][mid_c]

        # Bowl: kenarlar yuksek, orta dusuk
        if center < corner_mean - 0.03:
            return "bowl"

        # Dome: kenarlar dusuk, orta yuksek
        if center > corner_mean + 0.03:
            return "dome"

        # Tilt: bir kenar yuksek, karsi kenar dusuk
        top_mean = sum(mesh[0]) / cols
        bottom_mean = sum(mesh[-1]) / cols
        left_mean = sum(row[0] for row in mesh) / rows
        right_mean = sum(row[-1] for row in mesh) / rows

        y_tilt = abs(top_mean - bottom_mean)
        x_tilt = abs(left_mean - right_mean)

        if y_tilt > 0.05 and y_tilt > x_tilt:
            return "tilt_y"
        if x_tilt > 0.05 and x_tilt > y_tilt:
            return "tilt_x"
        if y_tilt > 0.03 or x_tilt > 0.03:
            return "tilt_xy"

        return "uneven"

    def _suggest_screw_turns(
        self, mesh: List[List[float]], reference: float,
    ) -> List[ScrewAdjustment]:
        """Her vida icin tur ve yon onerisi."""
        if not self.screw_positions or not mesh:
            return []

        rows = len(mesh)
        cols = len(mesh[0]) if rows else 0
        if rows < 2 or cols < 2:
            return []

        adjustments = []
        for screw in self.screw_positions:
            # Vida koordinatini mesh grid indeksine cevir
            x_frac = (screw["x"] - self.mesh_min_coord[0]) / max(
                self.mesh_max_coord[0] - self.mesh_min_coord[0], 1
            )
            y_frac = (screw["y"] - self.mesh_min_coord[1]) / max(
                self.mesh_max_coord[1] - self.mesh_min_coord[1], 1
            )
            col = min(int(x_frac * (cols - 1) + 0.5), cols - 1)
            row = min(int(y_frac * (rows - 1) + 0.5), rows - 1)
            col = max(0, col)
            row = max(0, row)

            offset_mm = mesh[row][col] - reference
            turns = offset_mm / self.screw_pitch_mm
            direction = "CW" if offset_mm > 0 else "CCW"
            desc_word = "yuksek" if offset_mm > 0 else "dusuk"
            description = (
                f"{direction} {ScrewAdjustment.format_turns(turns)} "
                f"({abs(offset_mm):.2f}mm {desc_word})"
            )

            adjustments.append(ScrewAdjustment(
                name=screw["name"],
                x=screw["x"],
                y=screw["y"],
                offset_mm=offset_mm,
                turns=abs(turns),
                direction=direction,
                description=description,
            ))

        return adjustments
```

**Step 4: Run tests to verify they pass**

Run: `cd /c/linux_ai/KlipperOS-AI && python -m pytest tests/test_bed_level_analyzer.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add ai-monitor/bed_level_analyzer.py tests/test_bed_level_analyzer.py
git commit -m "feat(ai): add bed level analyzer with MeshAnalyzer and data structures"
```

---

## Task 2: ProfileManager & DriftDetector

**Files:**
- Modify: `ai-monitor/bed_level_analyzer.py`
- Modify: `tests/test_bed_level_analyzer.py`

**Step 1: Write failing tests for ProfileManager and DriftDetector**

Add to `tests/test_bed_level_analyzer.py`:

```python
class TestProfileManager:
    """ProfileManager: mesh profil yonetimi — filament+yuzey combo."""

    def setup_method(self):
        self.pm = ProfileManager(state_path=Path("/tmp/kos_test_profiles.json"))
        # Temiz baslat
        if self.pm.state_path.exists():
            self.pm.state_path.unlink()

    def test_save_and_load_profile(self):
        """Profil kaydet ve geri yukle."""
        mesh = [[0.1, 0.2], [0.3, 0.4]]
        self.pm.save_profile("pei_pla", mesh, bed_temp=60.0)
        loaded = self.pm.load_profile("pei_pla")
        assert loaded is not None
        assert loaded.profile_name == "pei_pla"
        assert loaded.mesh_matrix == mesh
        assert loaded.bed_temp == 60.0

    def test_auto_select_profile(self):
        """Filament+yuzey combo ile profil sec."""
        mesh = [[0.1, 0.2], [0.3, 0.4]]
        self.pm.save_profile("pei_pla", mesh, bed_temp=60.0)
        self.pm.save_profile("glass_petg", mesh, bed_temp=80.0)
        name = self.pm.auto_select_profile(surface="pei", filament="pla")
        assert name == "pei_pla"

    def test_auto_select_missing_returns_none(self):
        """Olmayan combo None dondurur."""
        name = self.pm.auto_select_profile(surface="steel", filament="tpu")
        assert name is None

    def test_compare_profiles(self):
        """Iki profil arasi delta hesapla."""
        mesh_a = [[0.1, 0.2], [0.3, 0.4]]
        mesh_b = [[0.15, 0.25], [0.35, 0.45]]
        self.pm.save_profile("a", mesh_a, bed_temp=60.0)
        self.pm.save_profile("b", mesh_b, bed_temp=60.0)
        delta = self.pm.compare_profiles("a", "b")
        assert delta is not None
        assert delta["max_diff"] == pytest.approx(0.05, abs=0.01)
        assert delta["mean_diff"] == pytest.approx(0.05, abs=0.01)

    def test_list_profiles(self):
        """Kayitli profilleri listele."""
        mesh = [[0.0]]
        self.pm.save_profile("pei_pla", mesh, bed_temp=60.0)
        self.pm.save_profile("glass_abs", mesh, bed_temp=100.0)
        names = self.pm.list_profiles()
        assert "pei_pla" in names
        assert "glass_abs" in names


class TestDriftDetector:
    """DriftDetector: mesh drift izleme ve yeniden kalibrasyon onerisi."""

    def setup_method(self):
        self.dd = DriftDetector(state_path=Path("/tmp/kos_test_drift.json"))
        if self.dd.state_path.exists():
            self.dd.state_path.unlink()

    def test_no_drift_on_first_snapshot(self):
        """Ilk snapshot — drift yok."""
        mesh = [[0.0, 0.0], [0.0, 0.0]]
        report = self.dd.check_drift("default", mesh)
        assert report.recommendation == "ok"

    def test_drift_detected(self):
        """Ikinci snapshot farkli — drift algilanir."""
        mesh_ref = [[0.0, 0.0], [0.0, 0.0]]
        mesh_new = [[0.08, 0.06], [0.07, 0.09]]
        self.dd.add_snapshot("default", mesh_ref, bed_temp=60.0)
        report = self.dd.check_drift("default", mesh_new)
        assert report.max_point_drift >= 0.06
        assert report.recommendation in ("recalibrate", "check_screws")

    def test_should_recalibrate_threshold(self):
        """Esik asimi kontrolu."""
        mesh_ref = [[0.0, 0.0], [0.0, 0.0]]
        mesh_bad = [[0.15, 0.12], [0.11, 0.14]]
        self.dd.add_snapshot("default", mesh_ref, bed_temp=60.0)
        assert self.dd.should_recalibrate("default", mesh_bad)

    def test_stable_mesh_no_recalibrate(self):
        """Stabil mesh — yeniden kalibrasyon gerekmez."""
        mesh_ref = [[0.05, 0.05], [0.05, 0.05]]
        mesh_same = [[0.05, 0.06], [0.05, 0.05]]
        self.dd.add_snapshot("default", mesh_ref, bed_temp=60.0)
        assert not self.dd.should_recalibrate("default", mesh_same)
```

**Step 2: Run tests to verify they fail**

Run: `cd /c/linux_ai/KlipperOS-AI && python -m pytest tests/test_bed_level_analyzer.py::TestProfileManager -v`
Expected: FAIL with `ImportError` (ProfileManager not yet implemented)

**Step 3: Implement ProfileManager and DriftDetector**

Append to `ai-monitor/bed_level_analyzer.py`:

```python
# --- ProfileManager ---

class ProfileManager:
    """Mesh profil yonetimi — filament+yuzey combo ile kayit/yukleme."""

    def __init__(self, state_path: Path = STATE_PATH):
        self.state_path = state_path
        self._profiles: Dict[str, MeshSnapshot] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Kaydedilmis profilleri yukle."""
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                for name, snap_dict in data.get("profiles", {}).items():
                    self._profiles[name] = MeshSnapshot(**snap_dict)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Profil dosyasi okunamadi: %s", self.state_path)

    def _save_state(self) -> None:
        """Profilleri diske kaydet."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"profiles": {n: asdict(s) for n, s in self._profiles.items()}}
        self.state_path.write_text(json.dumps(data, indent=2))

    def save_profile(
        self,
        name: str,
        mesh: List[List[float]],
        bed_temp: float = 0.0,
        ambient_temp: Optional[float] = None,
    ) -> None:
        """Mesh'i profil olarak kaydet."""
        flat = [v for row in mesh for v in row]
        mesh_mean = sum(flat) / len(flat) if flat else 0.0
        variance = sum((v - mesh_mean) ** 2 for v in flat) / len(flat) if flat else 0.0

        self._profiles[name] = MeshSnapshot(
            timestamp=time.time(),
            profile_name=name,
            mesh_matrix=mesh,
            bed_temp=bed_temp,
            ambient_temp=ambient_temp,
            mesh_range=(max(flat) - min(flat)) if flat else 0.0,
            mesh_mean=mesh_mean,
            mesh_std_dev=math.sqrt(variance),
        )
        self._save_state()
        logger.info("Profil kaydedildi: %s (range=%.3f)", name, self._profiles[name].mesh_range)

    def load_profile(self, name: str) -> Optional[MeshSnapshot]:
        """Profili yukle."""
        return self._profiles.get(name)

    def auto_select_profile(self, surface: str, filament: str) -> Optional[str]:
        """Filament+yuzey combo ile profil sec."""
        key = f"{surface}_{filament}"
        if key in self._profiles:
            return key
        return None

    def compare_profiles(self, name_a: str, name_b: str) -> Optional[Dict]:
        """Iki profil arasi delta hesapla."""
        a = self._profiles.get(name_a)
        b = self._profiles.get(name_b)
        if not a or not b:
            return None

        diffs = []
        for row_a, row_b in zip(a.mesh_matrix, b.mesh_matrix):
            for va, vb in zip(row_a, row_b):
                diffs.append(abs(va - vb))

        if not diffs:
            return None

        return {
            "max_diff": max(diffs),
            "mean_diff": sum(diffs) / len(diffs),
            "profiles": [name_a, name_b],
        }

    def list_profiles(self) -> List[str]:
        """Kayitli profil isimlerini dondur."""
        return list(self._profiles.keys())


# --- DriftDetector ---

class DriftDetector:
    """Mesh drift izleme ve yeniden kalibrasyon onerisi."""

    def __init__(
        self,
        state_path: Path = STATE_PATH,
        drift_threshold: float = DRIFT_THRESHOLD_MM,
        recalibrate_threshold: float = RECALIBRATE_THRESHOLD_MM,
    ):
        self.state_path = state_path
        self.drift_threshold = drift_threshold
        self.recalibrate_threshold = recalibrate_threshold
        self._snapshots: Dict[str, List[MeshSnapshot]] = {}
        self._load_state()

    def _load_state(self) -> None:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                for name, snaps in data.get("drift_snapshots", {}).items():
                    self._snapshots[name] = [MeshSnapshot(**s) for s in snaps]
            except (json.JSONDecodeError, TypeError):
                pass

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "drift_snapshots": {
                n: [asdict(s) for s in snaps[-MAX_SNAPSHOTS:]]
                for n, snaps in self._snapshots.items()
            }
        }
        self.state_path.write_text(json.dumps(data, indent=2))

    def add_snapshot(
        self, profile: str, mesh: List[List[float]], bed_temp: float = 0.0,
    ) -> None:
        """Yeni mesh snapshot ekle."""
        flat = [v for row in mesh for v in row]
        mesh_mean = sum(flat) / len(flat) if flat else 0.0
        variance = sum((v - mesh_mean) ** 2 for v in flat) / len(flat) if flat else 0.0

        snap = MeshSnapshot(
            timestamp=time.time(),
            profile_name=profile,
            mesh_matrix=mesh,
            bed_temp=bed_temp,
            mesh_range=(max(flat) - min(flat)) if flat else 0.0,
            mesh_mean=mesh_mean,
            mesh_std_dev=math.sqrt(variance),
        )
        if profile not in self._snapshots:
            self._snapshots[profile] = []
        self._snapshots[profile].append(snap)
        self._save_state()

    def check_drift(self, profile: str, current_mesh: List[List[float]]) -> DriftReport:
        """Mevcut mesh ile referans arasindaki drift'i kontrol et."""
        snaps = self._snapshots.get(profile, [])
        if not snaps:
            return DriftReport(recommendation="ok")

        ref = snaps[0]
        diffs = []
        for row_cur, row_ref in zip(current_mesh, ref.mesh_matrix):
            for vc, vr in zip(row_cur, row_ref):
                diffs.append(abs(vc - vr))

        if not diffs:
            return DriftReport(recommendation="ok")

        max_drift = max(diffs)
        mean_drift = sum(diffs) / len(diffs)
        cur_flat = [v for row in current_mesh for v in row]
        cur_range = (max(cur_flat) - min(cur_flat)) if cur_flat else 0.0
        days = (time.time() - ref.timestamp) / 86400

        if max_drift >= self.recalibrate_threshold:
            rec = "recalibrate"
            direction = "worsening"
        elif max_drift >= self.drift_threshold:
            rec = "check_screws"
            direction = "worsening"
        else:
            rec = "ok"
            direction = "stable"

        return DriftReport(
            current_range=cur_range,
            reference_range=ref.mesh_range,
            max_point_drift=max_drift,
            mean_drift=mean_drift,
            drift_direction=direction,
            recommendation=rec,
            days_since_calibration=days,
        )

    def should_recalibrate(self, profile: str, current_mesh: List[List[float]]) -> bool:
        """Yeniden kalibrasyon gerekli mi?"""
        report = self.check_drift(profile, current_mesh)
        return report.recommendation == "recalibrate"
```

**Step 4: Run tests to verify they pass**

Run: `cd /c/linux_ai/KlipperOS-AI && python -m pytest tests/test_bed_level_analyzer.py -v`
Expected: All 16 tests PASS

**Step 5: Commit**

```bash
git add ai-monitor/bed_level_analyzer.py tests/test_bed_level_analyzer.py
git commit -m "feat(ai): add ProfileManager and DriftDetector to bed level analyzer"
```

---

## Task 3: Klipper Macro File — kos_bed_level.cfg

**Files:**
- Create: `config/klipper/kos_bed_level.cfg`

**Step 1: Create the macro file**

```ini
# config/klipper/kos_bed_level.cfg
# =============================================================================
# KlipperOS-AI — Bed Level Macros
# =============================================================================
# Akilli bed leveling, mesh profil yonetimi ve baski oncesi kontrol.
# Kullanim: printer.cfg'ye [include kos_bed_level.cfg] ekleyin.
# =============================================================================

[save_variables]
filename: ~/.klipperos_variables.cfg

# --- Ana Kalibrasyon Macro ---
[gcode_macro KOS_BED_LEVEL_CALIBRATE]
description: Akilli bed level kalibrasyon — prob varsa otomatik, yoksa manuel
variable_last_calibration: 0
gcode:
    {% set PROFILE = params.PROFILE|default("default")|string %}
    {% set TEMP_BED = params.TEMP_BED|default(0)|int %}

    {action_respond_info("KOS: Bed level kalibrasyon basliyor...")}

    # Yatak isitma (istenirse)
    {% if TEMP_BED > 0 %}
        {action_respond_info("KOS: Yatak %d°C'ye isitiliyor..." % TEMP_BED)}
        M190 S{TEMP_BED}
        G4 P60000  ; 1 dk termal stabilizasyon
    {% endif %}

    G28  ; Home all

    # Prob varsa otomatik, yoksa manuel
    {% if printer.configfile.config["probe"] is defined or printer.configfile.config["bltouch"] is defined %}
        {action_respond_info("KOS: Otomatik mesh kalibrasyon (probe algilandi)")}
        BED_MESH_CALIBRATE PROFILE={PROFILE}
    {% elif printer.configfile.config["bed_screws"] is defined %}
        {action_respond_info("KOS: Manuel bed screws ayarlama")}
        BED_SCREWS_ADJUST
    {% else %}
        {action_respond_info("KOS HATA: Ne probe ne de bed_screws tanimli!")}
    {% endif %}

    # Zaman damgasi kaydet
    SAVE_VARIABLE VARIABLE=kos_last_calibration VALUE={printer.toolhead.estimated_print_time}

# --- Baski Oncesi Kontrol ---
[gcode_macro KOS_BED_LEVEL_CHECK]
description: Baski oncesi mesh kontrol — eski veya eksik mesh uyarisi
gcode:
    {% set MAX_AGE = params.MAX_AGE|default(72)|int %}  ; saat

    {% set svv = printer.save_variables.variables %}
    {% set last_cal = svv.kos_last_calibration|default(0)|float %}
    {% set mesh_profiles = printer.bed_mesh.profiles|default({}) %}

    # Aktif mesh kontrol
    {% if printer.bed_mesh.profile_name == "" %}
        {% if "default" in mesh_profiles %}
            {action_respond_info("KOS: Varsayilan mesh profili yukleniyor...")}
            BED_MESH_PROFILE LOAD=default
        {% elif mesh_profiles|length > 0 %}
            {% set first_profile = mesh_profiles.keys()|list|first %}
            {action_respond_info("KOS: '%s' mesh profili yukleniyor..." % first_profile)}
            BED_MESH_PROFILE LOAD={first_profile}
        {% else %}
            {action_respond_info("KOS UYARI: Aktif bed mesh yok! KOS_BED_LEVEL_CALIBRATE calistirin.")}
        {% endif %}
    {% else %}
        {action_respond_info("KOS: Bed mesh aktif (%s)" % printer.bed_mesh.profile_name)}
    {% endif %}

# --- Profil Kaydet ---
[gcode_macro KOS_MESH_PROFILE_SAVE]
description: Mesh profilini filament+yuzey combo ile kaydet
gcode:
    {% set SURFACE = params.SURFACE|default("pei")|string|lower %}
    {% set FILAMENT = params.FILAMENT|default("pla")|string|lower %}
    {% set NAME = params.NAME|default(SURFACE ~ "_" ~ FILAMENT)|string %}

    BED_MESH_PROFILE SAVE={NAME}
    SAVE_VARIABLE VARIABLE=kos_mesh_{NAME}_timestamp VALUE={printer.toolhead.estimated_print_time}
    SAVE_VARIABLE VARIABLE=kos_mesh_{NAME}_surface VALUE='"{SURFACE}"'
    SAVE_VARIABLE VARIABLE=kos_mesh_{NAME}_filament VALUE='"{FILAMENT}"'
    {action_respond_info("KOS: Mesh profili kaydedildi: %s (yuzey=%s, filament=%s)" % (NAME, SURFACE, FILAMENT))}

# --- Profil Yukle ---
[gcode_macro KOS_MESH_PROFILE_LOAD]
description: Mesh profilini yukle — isim veya filament+yuzey combo
gcode:
    {% set SURFACE = params.SURFACE|default("")|string|lower %}
    {% set FILAMENT = params.FILAMENT|default("")|string|lower %}
    {% set NAME = params.NAME|default("")|string %}

    {% if NAME != "" %}
        {action_respond_info("KOS: Mesh profili yukleniyor: %s" % NAME)}
        BED_MESH_PROFILE LOAD={NAME}
    {% elif SURFACE != "" and FILAMENT != "" %}
        {% set auto_name = SURFACE ~ "_" ~ FILAMENT %}
        {action_respond_info("KOS: Mesh profili yukleniyor: %s" % auto_name)}
        BED_MESH_PROFILE LOAD={auto_name}
    {% else %}
        {action_respond_info("KOS HATA: NAME veya SURFACE+FILAMENT parametresi gerekli")}
    {% endif %}

# --- Vida Ayari Wrapper ---
[gcode_macro KOS_SCREW_ADJUST]
description: Vida ayari — prob varsa screws_tilt_calculate, yoksa bed_screws_adjust
gcode:
    G28
    {% if printer.configfile.config["screws_tilt_adjust"] is defined %}
        {action_respond_info("KOS: Probe ile vida ayari basliyor...")}
        SCREWS_TILT_CALCULATE
    {% elif printer.configfile.config["bed_screws"] is defined %}
        {action_respond_info("KOS: Manuel vida ayari basliyor...")}
        BED_SCREWS_ADJUST
    {% else %}
        {action_respond_info("KOS HATA: Ne screws_tilt_adjust ne de bed_screws tanimli!")}
    {% endif %}

# --- Adaptif Mesh ---
[gcode_macro KOS_ADAPTIVE_MESH]
description: Baski alanina gore adaptif mesh kalibrasyon
gcode:
    {% set PROFILE = params.PROFILE|default("default")|string %}

    {action_respond_info("KOS: Adaptif mesh kalibrasyon basliyor...")}
    G28
    BED_MESH_CALIBRATE PROFILE={PROFILE} ADAPTIVE=1
    {action_respond_info("KOS: Adaptif mesh tamamlandi.")}
```

**Step 2: Verify file syntax (no automated test — Klipper macros are Jinja2)**

Manually verify: no unclosed braces, consistent indentation, valid Jinja2 syntax.

**Step 3: Commit**

```bash
git add config/klipper/kos_bed_level.cfg
git commit -m "feat(config): add kos_bed_level.cfg Klipper macro file"
```

---

## Task 4: Config Template Updates

**Files:**
- Modify: `config/klipper/ender3.cfg`
- Modify: `config/klipper/ender3v2.cfg`
- Modify: `config/klipper/generic.cfg`
- Modify: `config/klipper/voron.cfg`
- Modify: `ai-monitor/config_manager.py`

**Step 1: Update ender3.cfg — add bed_screws, expand BLTouch section**

In `config/klipper/ender3.cfg`, **before** the `# --- KlipperOS-AI v2 Entegrasyon ---` line, add:

```ini
# --- Manuel Yatak Hizalama (4 vida) ---
[bed_screws]
screw1: 30.5, 37
screw1_name: Sol On
screw2: 30.5, 207
screw2_name: Sol Arka
screw3: 204.5, 207
screw3_name: Sag Arka
screw4: 204.5, 37
screw4_name: Sag On
horizontal_move_z: 5
speed: 50

# --- BLTouch (varsa yorumlari kaldirin) ---
#[bltouch]
#sensor_pin: ^PB1
#control_pin: PB0
#x_offset: -44
#y_offset: -6
#z_offset: 0

#[safe_z_home]
#home_xy_position: 157, 123
#speed: 80
#z_hop: 10
#z_hop_speed: 10

#[screws_tilt_adjust]
#screw1: 74.5, 43
#screw1_name: Sol On
#screw2: 74.5, 213
#screw2_name: Sol Arka
#screw3: 235, 213
#screw3_name: Sag Arka
#screw4: 235, 43
#screw4_name: Sag On
#horizontal_move_z: 10
#speed: 50
#screw_thread: CW-M4

#[bed_mesh]
#speed: 120
#horizontal_move_z: 5
#mesh_min: 10, 10
#mesh_max: 190, 220
#probe_count: 5, 5
#algorithm: bicubic
#fade_start: 1
#fade_end: 10
```

Replace the old commented-out BLTouch/bed_mesh section with this expanded version.

Also update the KOS include section to add `kos_bed_level.cfg`:

```ini
# --- KlipperOS-AI v2 Entegrasyon ---
[include klipper-macros/*.cfg]
[include kos_plr.cfg]
#[include kos_flowguard.cfg]   ; Filament sensoru varsa aktiflestiriniz
[include kos_rewind.cfg]
[include kos_bed_level.cfg]
```

**Step 2: Update generic.cfg — same pattern** (bed_screws active, probe/mesh commented)

**Step 3: Update voron.cfg — add safe_z_home and include**

After `[quad_gantry_level]` section, add:

```ini
[safe_z_home]
home_xy_position: 150, 150
speed: 100
z_hop: 10
z_hop_speed: 10
```

Add to includes: `[include kos_bed_level.cfg]`

**Step 4: Update config_manager.py whitelist**

In `ai-monitor/config_manager.py`, add to `ALLOWED_PARAMS` dict:

```python
    "bed_mesh": [
        "mesh_min", "mesh_max", "probe_count", "algorithm",
        "bicubic_tension", "mesh_pps", "fade_start", "fade_end",
        "adaptive_margin", "zero_reference_position",
    ],
    "probe": [
        "z_offset", "samples", "samples_tolerance",
        "speed", "lift_speed",
    ],
    "safe_z_home": [
        "home_xy_position",
    ],
```

**Step 5: Commit**

```bash
git add config/klipper/ender3.cfg config/klipper/ender3v2.cfg \
        config/klipper/generic.cfg config/klipper/voron.cfg \
        ai-monitor/config_manager.py
git commit -m "feat(config): add bed leveling to all printer templates and config whitelist"
```

---

## Task 5: Installer Bed Level Wizard

**Files:**
- Create: `packages/installer/steps/bed_level.py`
- Modify: `packages/installer/app.py`

**Step 1: Create the bed level wizard step**

```python
# packages/installer/steps/bed_level.py
"""Adim 6.5: Bed level yapilandirma wizard."""
from __future__ import annotations

from ..tui import TUI
from ..utils.logger import get_logger

logger = get_logger()

# Bilinen yazici vida pozisyonlari (printer_model -> screw list)
KNOWN_SCREW_POSITIONS = {
    "ender3": [
        ("30.5, 37", "Sol On"),
        ("30.5, 207", "Sol Arka"),
        ("204.5, 207", "Sag Arka"),
        ("204.5, 37", "Sag On"),
    ],
    "ender3v2": [
        ("30.5, 37", "Sol On"),
        ("30.5, 207", "Sol Arka"),
        ("204.5, 207", "Sag Arka"),
        ("204.5, 37", "Sag On"),
    ],
}

PROBE_TYPES = [
    ("none", "Prob yok (manuel leveling)"),
    ("bltouch", "BLTouch / 3DTouch"),
    ("inductive", "Inductive / Capacitive Probe"),
    ("klicky", "Klicky / Tap (Voron)"),
]

MESH_DENSITIES = [
    ("3", "3x3 — Hizli (~30 sn)"),
    ("5", "5x5 — Dengeli (~1.5 dk) [Onerilen]"),
    ("7", "7x7 — Detayli (~3 dk)"),
]


class BedLevelStep:
    """Bed leveling yapilandirma wizard'i."""

    def __init__(self, tui: TUI, hw_info=None):
        self.tui = tui
        self.hw_info = hw_info
        self.probe_type = "none"
        self.probe_x_offset = 0.0
        self.probe_y_offset = 0.0
        self.mesh_count = 5
        self.bed_x_max = 235
        self.bed_y_max = 235

    def run(self) -> dict:
        """Wizard adimlari. Config verisini dict olarak dondurur."""
        logger.info("Bed level wizard basliyor...")

        # Atla secenegi
        skip = self.tui.yesno(
            "Bed Leveling",
            "Bed leveling yapilandirmak ister misiniz?\n\n"
            "(Atlarsaniz varsayilan ayarlar kullanilir,\n"
            " ilk acilista KOS_BED_LEVEL_CALIBRATE ile baslayin)",
            default_yes=True,
        )
        if not skip:
            logger.info("Bed level wizard atlandi.")
            return {"skipped": True}

        # 1. Probe tipi
        self.probe_type = self.tui.menu(
            "Probe Tipi",
            PROBE_TYPES,
            text="Yazicinizda Z probe var mi?",
        )
        logger.info("Probe tipi: %s", self.probe_type)

        # 2. Probe offset (probe varsa)
        if self.probe_type != "none":
            self._ask_probe_offset()

        # 3. Mesh ayarlari (probe varsa)
        if self.probe_type != "none":
            self._ask_mesh_settings()

        # 4. Ozet
        self._show_summary()

        result = {
            "skipped": False,
            "probe_type": self.probe_type,
            "probe_x_offset": self.probe_x_offset,
            "probe_y_offset": self.probe_y_offset,
            "mesh_count": self.mesh_count,
            "bed_x_max": self.bed_x_max,
            "bed_y_max": self.bed_y_max,
        }
        logger.info("Bed level config: %s", result)
        return result

    def _ask_probe_offset(self):
        """Probe offset bilgisi sor."""
        defaults = {
            "bltouch": (-44, -6),
            "inductive": (-25, 0),
            "klicky": (0, 0),
        }
        dx, dy = defaults.get(self.probe_type, (0, 0))

        use_default = self.tui.yesno(
            "Probe Offset",
            f"Varsayilan offset kullanilsin mi?\n\n"
            f"  X offset: {dx} mm\n"
            f"  Y offset: {dy} mm\n\n"
            f"(Sonra PROBE_CALIBRATE ile kalibre edebilirsiniz)",
            default_yes=True,
        )
        if use_default:
            self.probe_x_offset = dx
            self.probe_y_offset = dy
        else:
            x_str = self.tui.inputbox("X Offset", "Probe X offset (mm):", str(dx))
            y_str = self.tui.inputbox("Y Offset", "Probe Y offset (mm):", str(dy))
            try:
                self.probe_x_offset = float(x_str)
                self.probe_y_offset = float(y_str)
            except ValueError:
                self.probe_x_offset = dx
                self.probe_y_offset = dy

    def _ask_mesh_settings(self):
        """Mesh cozunurluk ayarlari."""
        choice = self.tui.menu(
            "Mesh Cozunurlugu",
            MESH_DENSITIES,
            text="Bed mesh prob noktasi sayisi:",
        )
        self.mesh_count = int(choice)

    def _show_summary(self):
        """Ozet goster."""
        probe_str = dict(PROBE_TYPES).get(self.probe_type, self.probe_type)
        lines = [
            f"  Probe:          {probe_str}",
        ]
        if self.probe_type != "none":
            lines.extend([
                f"  X Offset:       {self.probe_x_offset} mm",
                f"  Y Offset:       {self.probe_y_offset} mm",
                f"  Mesh:           {self.mesh_count}x{self.mesh_count}",
            ])
        lines.append("\nBu ayarlar printer.cfg'ye yazilacak.")

        self.tui.msgbox("Bed Level Ozeti", "\n".join(lines))

    def generate_config(self) -> str:
        """Klipper config blogu olustur."""
        sections = []

        # bed_screws (her zaman — probsuz da kullanilabilir)
        sections.append(
            "# --- Manuel Yatak Hizalama ---\n"
            "[bed_screws]\n"
            "screw1: 30.5, 37\n"
            "screw1_name: Sol On\n"
            "screw2: 30.5, 207\n"
            "screw2_name: Sol Arka\n"
            "screw3: 204.5, 207\n"
            "screw3_name: Sag Arka\n"
            "screw4: 204.5, 37\n"
            "screw4_name: Sag On\n"
        )

        if self.probe_type != "none":
            # probe section
            if self.probe_type == "bltouch":
                sections.append(
                    "\n[bltouch]\n"
                    "sensor_pin: ^PB1\n"
                    "control_pin: PB0\n"
                    f"x_offset: {self.probe_x_offset}\n"
                    f"y_offset: {self.probe_y_offset}\n"
                    "z_offset: 0\n"
                )
            else:
                sections.append(
                    "\n[probe]\n"
                    "pin: ^PC2\n"
                    f"x_offset: {self.probe_x_offset}\n"
                    f"y_offset: {self.probe_y_offset}\n"
                    "z_offset: 0\n"
                    "speed: 5.0\n"
                    "samples: 3\n"
                    "samples_result: median\n"
                )

            # safe_z_home
            cx = self.bed_x_max // 2
            cy = self.bed_y_max // 2
            sections.append(
                f"\n[safe_z_home]\n"
                f"home_xy_position: {cx}, {cy}\n"
                "speed: 80\n"
                "z_hop: 10\n"
            )

            # bed_mesh
            margin = 10
            mesh_min = f"{margin}, {margin}"
            mesh_max = f"{self.bed_x_max - margin}, {self.bed_y_max - margin}"
            algo = "bicubic" if self.mesh_count >= 4 else "lagrange"
            sections.append(
                "\n[bed_mesh]\n"
                "speed: 120\n"
                "horizontal_move_z: 5\n"
                f"mesh_min: {mesh_min}\n"
                f"mesh_max: {mesh_max}\n"
                f"probe_count: {self.mesh_count}, {self.mesh_count}\n"
                f"algorithm: {algo}\n"
                "fade_start: 1\n"
                "fade_end: 10\n"
            )

        sections.append("\n[include kos_bed_level.cfg]\n")
        return "\n".join(sections)
```

**Step 2: Update app.py — add BedLevelStep import and step order**

In `packages/installer/app.py`:
- Add import: `from .steps.bed_level import BedLevelStep`
- Add bed level step between ServicesStep and CompleteStep (after step 7, before step 8)

```python
        # 6.5 Bed level yapilandirma
        bed_config = BedLevelStep(tui=self.tui, hw_info=hw_info).run()
```

Insert this between `InstallStep.run()` and `ServicesStep.run()` — specifically after step 6 (InstallStep) and before step 7 (ServicesStep).

**Step 3: Commit**

```bash
git add packages/installer/steps/bed_level.py packages/installer/app.py
git commit -m "feat(installer): add bed level wizard step to TUI installer"
```

---

## Task 6: AI Monitor Integration — print_monitor.py hooks

**Files:**
- Modify: `ai-monitor/print_monitor.py`

**Step 1: Add Moonraker bed_mesh query method to MoonrakerClient**

In `MoonrakerClient` class, add:

```python
    def get_bed_mesh(self) -> dict:
        """Get current bed mesh data."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"bed_mesh": "profile_name,profiles,mesh_matrix"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("status", {})
            return data.get("bed_mesh", {})
        except Exception:
            return {}
```

**Step 2: Add BedLevelAnalyzer integration to PrintMonitor.__init__**

Add import at top of file (in the try/except block):

```python
    from bed_level_analyzer import MeshAnalyzer, DriftDetector
```

In `PrintMonitor.__init__`, after the autonomous recovery block, add:

```python
        # Bed Level Analyzer (Phase 5)
        self.drift_detector = DriftDetector()
        self._bed_level_enabled = os.environ.get("BED_LEVEL_CHECK", "1").lower() not in ("0", "false", "no", "off")
        self._bed_level_checked = False
```

**Step 3: Add pre_print_check in _check_cycle (when print starts)**

In the `# Yeni baski basladi mi?` block, after the adaptive print setup, add:

```python
            # Bed Level Check
            if self._bed_level_enabled and not self._bed_level_checked:
                self._bed_level_pre_print_check()
                self._bed_level_checked = True
```

**Step 4: Add post_print_snapshot (when print ends)**

In the `# Baski bitti` block, after the maintenance hours logic, add:

```python
                # Bed Level: post-print snapshot
                if self._bed_level_enabled:
                    self._bed_level_post_print()
                    self._bed_level_checked = False
```

**Step 5: Implement the two helper methods**

Add to `PrintMonitor` class:

```python
    def _bed_level_pre_print_check(self):
        """Baski oncesi bed mesh kontrol."""
        mesh_data = self.moonraker.get_bed_mesh()
        profile = mesh_data.get("profile_name", "")
        if not profile:
            self.moonraker.send_notification(
                "KOS UYARI: Aktif bed mesh yok! "
                "KOS_BED_LEVEL_CALIBRATE calistirin."
            )
            logger.warning("Bed Level: aktif mesh yok")
            return

        mesh_matrix = mesh_data.get("mesh_matrix", [])
        if mesh_matrix:
            report = self.drift_detector.check_drift(profile, mesh_matrix)
            if report.recommendation == "recalibrate":
                self.moonraker.send_notification(
                    f"KOS: Kritik bed level drift ({report.max_point_drift:.2f}mm). "
                    "Yeniden kalibrasyon onerilir."
                )
                logger.warning("Bed Level: drift %.3fmm — recalibrate", report.max_point_drift)
            elif report.recommendation == "check_screws":
                self.moonraker.send_notification(
                    f"KOS: Bed level drift algilandi ({report.max_point_drift:.2f}mm). "
                    "Vida kontrolu onerilir."
                )
                logger.info("Bed Level: drift %.3fmm — check screws", report.max_point_drift)
            else:
                logger.info("Bed Level: mesh OK (drift %.3fmm)", report.max_point_drift)

    def _bed_level_post_print(self):
        """Baski sonrasi mesh snapshot al."""
        mesh_data = self.moonraker.get_bed_mesh()
        profile = mesh_data.get("profile_name", "")
        mesh_matrix = mesh_data.get("mesh_matrix", [])
        if profile and mesh_matrix:
            self.drift_detector.add_snapshot(profile, mesh_matrix)
            logger.info("Bed Level: post-print snapshot kaydedildi (%s)", profile)
```

**Step 6: Add startup log line**

In `PrintMonitor.start()`, after the autonomous recovery log block, add:

```python
        # Bed Level Check baslatma
        if self._bed_level_enabled:
            logger.info("Bed Level Check aktif. Baski oncesi mesh kontrol yapilacak.")
        else:
            logger.info("Bed Level Check devre disi. BED_LEVEL_CHECK=1 ile aktiflestirebilirsiniz.")
```

**Step 7: Commit**

```bash
git add ai-monitor/print_monitor.py
git commit -m "feat(ai): integrate bed level analyzer into print monitor daemon"
```

---

## Task 7: Tests for config_manager whitelist and integration

**Files:**
- Modify: `tests/test_config_manager.py`

**Step 1: Add whitelist test for new bed leveling sections**

Add to existing test file:

```python
    def test_bed_mesh_params_allowed(self):
        """bed_mesh parametreleri whitelist'te."""
        cm = ConfigManager("http://localhost:7125")
        assert cm.is_allowed("bed_mesh", "probe_count")
        assert cm.is_allowed("bed_mesh", "mesh_min")
        assert cm.is_allowed("bed_mesh", "algorithm")
        assert not cm.is_allowed("bed_mesh", "speed")  # speed not whitelisted

    def test_probe_params_allowed(self):
        """probe parametreleri whitelist'te."""
        cm = ConfigManager("http://localhost:7125")
        assert cm.is_allowed("probe", "z_offset")
        assert cm.is_allowed("probe", "samples")
        assert not cm.is_allowed("probe", "pin")  # pin is dangerous

    def test_safe_z_home_allowed(self):
        """safe_z_home parametreleri whitelist'te."""
        cm = ConfigManager("http://localhost:7125")
        assert cm.is_allowed("safe_z_home", "home_xy_position")
```

**Step 2: Run all tests**

Run: `cd /c/linux_ai/KlipperOS-AI && python -m pytest tests/test_config_manager.py tests/test_bed_level_analyzer.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_config_manager.py
git commit -m "test: add bed leveling whitelist tests for config_manager"
```

---

## Task 8: Final verification and documentation

**Step 1: Run full test suite**

Run: `cd /c/linux_ai/KlipperOS-AI && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS, no regressions

**Step 2: Verify file structure**

```bash
ls -la ai-monitor/bed_level_analyzer.py
ls -la config/klipper/kos_bed_level.cfg
ls -la packages/installer/steps/bed_level.py
```

**Step 3: Final commit with all remaining changes**

```bash
git status
# If any unstaged changes remain:
git add -A
git commit -m "feat(bed-level): complete KOS bed level ecosystem v3.0

Adds 5 integrated components:
- AI mesh analyzer with screw turn suggestions
- Smart mesh profile management (filament+surface)
- Drift detection with recalibration alerts
- Config templates with bed leveling for all printers
- Installer TUI wizard for bed level setup"
```

---

## Summary

| Task | Component | Files | Estimated Time |
|------|-----------|-------|---------------|
| 1 | MeshAnalyzer + data structures | 2 new | 15 min |
| 2 | ProfileManager + DriftDetector | 2 modified | 15 min |
| 3 | Klipper macro file | 1 new | 10 min |
| 4 | Config template updates | 5 modified | 10 min |
| 5 | Installer wizard | 1 new + 1 modified | 15 min |
| 6 | Monitor integration | 1 modified | 10 min |
| 7 | Whitelist tests | 1 modified | 5 min |
| 8 | Final verification | — | 5 min |
| **Total** | **3 new + 8 modified** | **~1145 lines** | **~85 min** |

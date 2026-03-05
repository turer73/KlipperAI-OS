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
    """Mesh durumunun zaman damgali anlik goruntusu."""
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
        adjustments = self._suggest_screw_turns(mesh, mesh_min)

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

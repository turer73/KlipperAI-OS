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


# --- Placeholder stubs for Task 2 imports ---

class ProfileManager:
    """Placeholder — will be implemented in Task 2."""
    pass


class DriftDetector:
    """Placeholder — will be implemented in Task 2."""
    pass

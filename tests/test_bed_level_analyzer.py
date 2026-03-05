# tests/test_bed_level_analyzer.py
"""Tests for KOS Bed Level Analyzer."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
import math

from bed_level_analyzer import (
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

# tests/test_bed_level_analyzer.py
"""Tests for KOS Bed Level Analyzer."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
import math
from pathlib import Path

from bed_level_analyzer import (
    MeshReport, ScrewAdjustment, MeshSnapshot, DriftReport, TrendResult,
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


class TestProfileManager:
    """ProfileManager: mesh profil yonetimi — filament+yuzey combo."""

    def setup_method(self):
        path = Path("/tmp/kos_test_profiles.json")
        if path.exists():
            path.unlink()
        self.pm = ProfileManager(state_path=path)

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
        path = Path("/tmp/kos_test_drift.json")
        if path.exists():
            path.unlink()
        self.dd = DriftDetector(state_path=path)

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

    def test_check_drift_uses_latest_snapshot(self):
        """check_drift en son snapshot'i referans alir."""
        import time as _time
        mesh_old = [[0.0, 0.0], [0.0, 0.0]]
        mesh_mid = [[0.05, 0.05], [0.05, 0.05]]
        mesh_cur = [[0.06, 0.06], [0.06, 0.06]]
        self.dd.add_snapshot("default", mesh_old, bed_temp=60.0)
        self.dd.add_snapshot("default", mesh_mid, bed_temp=60.0)
        report = self.dd.check_drift("default", mesh_cur)
        # Referans mesh_mid (snaps[-1]) — drift ~0.01mm, "ok" olmali
        assert report.max_point_drift == pytest.approx(0.01, abs=0.005)
        assert report.recommendation == "ok"

    def test_drift_trend_insufficient_data(self):
        """Tek snapshot — varsayilan TrendResult."""
        mesh = [[0.0, 0.0], [0.0, 0.0]]
        self.dd.add_snapshot("default", mesh)
        trend = self.dd.get_drift_trend("default")
        assert trend.snapshots_analyzed <= 1
        assert trend.trend_direction == "stable"

    def test_drift_trend_stable(self):
        """Ayni mesh_range ile stabil trend."""
        import time as _time
        mesh = [[0.05, 0.0], [0.0, 0.0]]  # range=0.05
        # 3 snapshot ekle (farkli timestamp ile)
        for i in range(3):
            self.dd.add_snapshot("default", mesh)
            # Timestamp farkli olsun
            snaps = self.dd._snapshots["default"]
            snaps[-1].timestamp = _time.time() - (2 - i) * 86400
        trend = self.dd.get_drift_trend("default")
        assert trend.trend_direction == "stable"
        assert trend.snapshots_analyzed >= 2

    def test_drift_trend_worsening(self):
        """Artan mesh_range ile kotulesen trend."""
        import time as _time
        base_time = _time.time() - 5 * 86400
        # range giderek artan mesh'ler
        meshes = [
            [[0.02, 0.0], [0.0, 0.0]],   # range=0.02
            [[0.05, 0.0], [0.0, 0.0]],   # range=0.05
            [[0.08, 0.0], [0.0, 0.0]],   # range=0.08
        ]
        for i, m in enumerate(meshes):
            self.dd.add_snapshot("default", m)
            snaps = self.dd._snapshots["default"]
            snaps[-1].timestamp = base_time + i * 86400
        trend = self.dd.get_drift_trend("default")
        assert trend.trend_direction == "worsening"
        assert trend.avg_drift_per_day > 0

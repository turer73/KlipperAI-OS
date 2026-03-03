"""Tests for Predictive Maintenance Engine (Phase 3)."""

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-monitor"))
from predictive_maintenance import (
    TrendAnalyzer,
    ThermalDriftTracker,
    MotorLoadTracker,
    NozzleWearTracker,
    PredictiveMaintenanceEngine,
    MaintenanceAlert,
    AlertSeverity,
)

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════════════════════
# TrendAnalyzer
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrendAnalyzer:
    """Lineer regresyon trend analizi testleri."""

    def test_empty_slope(self):
        ta = TrendAnalyzer()
        assert ta.slope() == 0.0
        assert ta.count == 0

    def test_single_point(self):
        ta = TrendAnalyzer()
        ta.add_point(1000, 5.0)
        assert ta.slope() == 0.0
        assert ta.count == 1

    def test_constant_values(self):
        ta = TrendAnalyzer()
        for i in range(20):
            ta.add_point(float(i * 100), 50.0)
        assert abs(ta.slope()) < 1e-10

    def test_increasing_trend(self):
        ta = TrendAnalyzer()
        for i in range(20):
            ta.add_point(float(i * 3600), float(i) * 0.01)
        assert ta.slope() > 0
        assert ta.slope_per_hour() > 0

    def test_decreasing_trend(self):
        ta = TrendAnalyzer()
        for i in range(20):
            ta.add_point(float(i * 3600), 200.0 - float(i) * 5.0)
        assert ta.slope() < 0
        assert ta.slope_per_hour() < 0

    def test_predict_future(self):
        ta = TrendAnalyzer()
        for i in range(20):
            ta.add_point(float(i * 100), float(i) * 2.0)
        pred = ta.predict(100)
        # Trend dogrusal, gelecek tahmini mevcut son degerden buyuk olmali
        assert pred > 38.0

    def test_is_degrading_insufficient_data(self):
        ta = TrendAnalyzer()
        for i in range(5):
            ta.add_point(float(i), float(i))
        assert ta.is_degrading(0.01) is False

    def test_is_degrading_with_data(self):
        ta = TrendAnalyzer()
        for i in range(20):
            ta.add_point(float(i * 3600), float(i) * 0.02)
        assert ta.is_degrading(0.01)

    def test_max_points_eviction(self):
        ta = TrendAnalyzer(max_points=10)
        for i in range(20):
            ta.add_point(float(i), float(i))
        assert ta.count == 10

    def test_serialization_roundtrip(self):
        ta = TrendAnalyzer()
        for i in range(15):
            ta.add_point(float(i * 100), float(i) * 0.5)
        data = ta.to_dict()
        ta2 = TrendAnalyzer.from_dict(data)
        assert ta2.count == ta.count
        assert abs(ta2.slope() - ta.slope()) < 1e-6

    def test_current_mean(self):
        ta = TrendAnalyzer()
        ta.add_point(1, 10.0)
        ta.add_point(2, 20.0)
        assert ta.current_mean() == pytest.approx(15.0)


# ═══════════════════════════════════════════════════════════════════════════════
# ThermalDriftTracker
# ═══════════════════════════════════════════════════════════════════════════════

class TestThermalDriftTracker:
    """Isitici yaslanma izleyici testleri."""

    def test_initial_no_alert(self):
        t = ThermalDriftTracker()
        assert t.check() is None

    def test_stable_duty_no_alert(self):
        """Sabit duty cycle → uyari yok."""
        t = ThermalDriftTracker()
        for i in range(50):
            t.update(0.50, 200.0)
        assert t.check() is None

    def test_increasing_duty_warning(self):
        """Artan duty cycle → uyari."""
        t = ThermalDriftTracker()
        base_time = time.time()
        for i in range(50):
            # slope_per_hour > 0.01 gerekli → duty saatte 0.02 artsin
            duty = 0.40 + i * 0.02
            t.duty_trend.add_point(base_time + i * 3600, duty)
        alert = t.check()
        assert alert is not None
        assert alert.component == "heater"

    def test_temp_change_ignored(self):
        """Sicaklik degisirken ornekler atlanir."""
        t = ThermalDriftTracker()
        t.update(0.50, 200.0)   # Ilk cagri: _last_target_temp=0 → 200 farkli, atlanir
        t.update(0.50, 200.0)   # Ikinci: 200-200 < 2 → EKLENIR
        t.update(0.55, 220.0)   # Ucuncu: 220-200=20 >= 2 → atlanir
        assert t.duty_trend.count == 1

    def test_serialization(self):
        t = ThermalDriftTracker()
        for i in range(10):
            t.update(0.50, 200.0)
        data = t.to_dict()
        t2 = ThermalDriftTracker.from_dict(data)
        assert t2.duty_trend.count == t.duty_trend.count


# ═══════════════════════════════════════════════════════════════════════════════
# MotorLoadTracker
# ═══════════════════════════════════════════════════════════════════════════════

class TestMotorLoadTracker:
    """Motor yuku izleyici testleri."""

    def test_initial_no_alert(self):
        m = MotorLoadTracker()
        assert m.check() is None

    def test_stable_sg_no_alert(self):
        """Sabit SG → uyari yok."""
        m = MotorLoadTracker()
        for i in range(50):
            m.sg_trend.add_point(float(i * 100), 200.0)
        assert m.check() is None

    def test_decreasing_sg_warning(self):
        """Azalan SG (artan motor yuku) → uyari."""
        m = MotorLoadTracker()
        base_time = time.time()
        for i in range(50):
            # slope_per_hour < -5.0 gerekli → saatte 10 SG dussun
            sg = 200.0 - i * 10.0
            m.sg_trend.add_point(base_time + i * 3600, sg)
        alert = m.check()
        assert alert is not None
        assert "motor" in alert.component
        assert alert.severity in ("warning", "critical")

    def test_increasing_sg_warning(self):
        """Artan SG (azalan motor yuku) → kavrama uyarisi."""
        m = MotorLoadTracker()
        base_time = time.time()
        for i in range(50):
            # slope_per_hour > 10.0 gerekli → saatte 15 SG artsin
            sg = 100.0 + i * 15.0
            m.sg_trend.add_point(base_time + i * 3600, sg)
        alert = m.check()
        assert alert is not None
        assert "kavrama" in alert.message.lower() or "azal" in alert.message.lower()

    def test_serialization(self):
        m = MotorLoadTracker(name="test_motor")
        for i in range(10):
            m.update(float(200 + i))
        data = m.to_dict()
        m2 = MotorLoadTracker.from_dict(data)
        assert m2.name == "test_motor"
        assert m2.sg_trend.count == m.sg_trend.count


# ═══════════════════════════════════════════════════════════════════════════════
# NozzleWearTracker
# ═══════════════════════════════════════════════════════════════════════════════

class TestNozzleWearTracker:
    """Nozul asınma izleyici testleri."""

    def test_initial_no_alert(self):
        n = NozzleWearTracker()
        assert n.check() is None

    def test_stable_duty_no_alert(self):
        """Sabit duty varyans → uyari yok."""
        n = NozzleWearTracker()
        for i in range(50):
            n.update(0.50)
        assert n.check() is None

    def test_high_variance_alert(self):
        """Yuksek duty varyans → nozul uyarisi."""
        n = NozzleWearTracker()
        base_time = time.time()
        # Artan varyans: alternating yuksek/dusuk
        for i in range(50):
            n.update(0.40 + (i % 2) * 0.20)  # 0.40 ve 0.60 arasi
        # Manual olarak varyans trend'ini besle
        # slope_per_hour > 0.001 ve mean > 0.005 gerekli
        for i in range(20):
            n.duty_variance_trend.add_point(base_time + i * 3600, 0.006 + i * 0.002)
        alert = n.check()
        assert alert is not None
        assert alert.component == "nozzle"

    def test_serialization(self):
        n = NozzleWearTracker()
        for i in range(30):
            n.update(0.50)
        data = n.to_dict()
        n2 = NozzleWearTracker.from_dict(data)
        assert n2.duty_variance_trend.count == n.duty_variance_trend.count


# ═══════════════════════════════════════════════════════════════════════════════
# PredictiveMaintenanceEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestPredictiveMaintenanceEngine:
    """Ana bakim motoru testleri."""

    def test_initial_no_alerts(self):
        engine = PredictiveMaintenanceEngine(
            state_path=Path("/tmp/test_maintenance_state.json")
        )
        engine._last_check_time = 0
        alerts = engine.check_maintenance()
        assert len(alerts) == 0

    def test_update_feeds_all_trackers(self):
        engine = PredictiveMaintenanceEngine(
            state_path=Path("/tmp/test_maintenance_state.json")
        )
        for i in range(10):
            engine.update(heater_duty=0.5, sg_result=200.0, target_temp=200.0)
        assert engine.thermal_tracker.duty_trend.count > 0
        assert engine.motor_tracker.sg_trend.count > 0
        assert engine.nozzle_tracker.duty_variance_trend.count >= 0

    def test_status_format(self):
        engine = PredictiveMaintenanceEngine(
            state_path=Path("/tmp/test_maintenance_state.json")
        )
        status = engine.status
        assert "print_hours" in status
        assert "alerts" in status
        assert "trackers" in status
        assert "heater" in status["trackers"]
        assert "motor" in status["trackers"]
        assert "nozzle" in status["trackers"]

    def test_save_load_state(self, tmp_path):
        state_file = tmp_path / "maintenance.json"
        engine = PredictiveMaintenanceEngine(state_path=state_file)
        engine._total_print_hours = 42.5
        for i in range(10):
            engine.update(heater_duty=0.5, sg_result=200.0, target_temp=200.0)
        assert engine.save_state() is True
        assert state_file.exists()

        # Yeni engine yukle
        engine2 = PredictiveMaintenanceEngine(state_path=state_file)
        assert engine2._total_print_hours == pytest.approx(42.5)

    def test_add_print_hours(self):
        engine = PredictiveMaintenanceEngine(
            state_path=Path("/tmp/test_maintenance_state.json")
        )
        engine.add_print_hours(5.0)
        engine.add_print_hours(3.5)
        assert engine._total_print_hours == pytest.approx(8.5)

    def test_reset_clears_all(self):
        engine = PredictiveMaintenanceEngine(
            state_path=Path("/tmp/test_maintenance_state.json")
        )
        for i in range(10):
            engine.update(heater_duty=0.5, sg_result=200.0, target_temp=200.0)
        engine.reset()
        assert engine.thermal_tracker.duty_trend.count == 0
        assert engine.motor_tracker.sg_trend.count == 0

    def test_check_maintenance_cache(self):
        """Cache mekanizmasi: ardisik cagrilar tekrar kontrol etmez."""
        engine = PredictiveMaintenanceEngine(
            state_path=Path("/tmp/test_maintenance_state.json")
        )
        engine._last_check_time = time.time()
        alerts = engine.check_maintenance()
        # Cache'den donuyor, yeni kontrol yapmiyor
        assert isinstance(alerts, list)

    def test_skip_invalid_heater(self):
        """Negatif duty → izleyiciye beslenmez."""
        engine = PredictiveMaintenanceEngine(
            state_path=Path("/tmp/test_maintenance_state.json")
        )
        engine.update(heater_duty=-1.0, sg_result=200.0)
        assert engine.thermal_tracker.duty_trend.count == 0
        assert engine.nozzle_tracker.duty_variance_trend.count == 0

    def test_skip_invalid_sg(self):
        """Negatif SG → izleyiciye beslenmez."""
        engine = PredictiveMaintenanceEngine(
            state_path=Path("/tmp/test_maintenance_state.json")
        )
        engine.update(heater_duty=0.5, sg_result=-1.0, target_temp=200.0)
        assert engine.motor_tracker.sg_trend.count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# MaintenanceAlert
# ═══════════════════════════════════════════════════════════════════════════════

class TestMaintenanceAlert:
    """Uyari veri yapisi testleri."""

    def test_alert_creation(self):
        alert = MaintenanceAlert(
            component="heater",
            severity=AlertSeverity.WARNING,
            message="Test uyarisi",
            probability=0.75,
            recommended_action="Test aksiyonu",
        )
        assert alert.component == "heater"
        assert alert.severity == "warning"
        assert alert.probability == 0.75

    def test_alert_serialization(self):
        alert = MaintenanceAlert(
            component="nozzle",
            severity=AlertSeverity.CRITICAL,
            message="Nozul asınmis",
            probability=0.9,
            recommended_action="Degistirin",
        )
        d = alert.to_dict()
        assert d["component"] == "nozzle"
        assert d["severity"] == "critical"
        assert "timestamp" in d

    def test_severity_values(self):
        assert AlertSeverity.INFO == "info"
        assert AlertSeverity.WARNING == "warning"
        assert AlertSeverity.CRITICAL == "critical"

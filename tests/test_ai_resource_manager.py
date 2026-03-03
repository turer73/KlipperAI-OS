"""Tests for AI Resource Manager (Phase 1)."""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Resource manager import
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-monitor"))
from resource_manager import (
    AIResourceManager,
    ResourcePolicy,
    SystemMetrics,
    ResourceAction,
    PrinterState,
    GOVERNOR_MAP,
)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"


# ─── Yardimci ────────────────────────────────────────────────────────────────

def make_metrics(**kwargs) -> SystemMetrics:
    """Varsayilan degerlerle metrik olustur."""
    defaults = {
        "timestamp": time.time(),
        "cpu_percent": 30.0,
        "cpu_per_core": [25.0, 35.0],
        "memory_percent": 50.0,
        "memory_available_mb": 2048,
        "cpu_temperature": 55.0,
        "disk_io_percent": 10.0,
        "load_avg_1m": 1.0,
    }
    defaults.update(kwargs)
    return SystemMetrics(**defaults)


# ─── Governor Karar Testleri ──────────────────────────────────────────────────

class TestGovernorDecisions:
    """CPU governor durum makinesi testleri."""

    def setup_method(self):
        self.mgr = AIResourceManager()
        self.mgr._current_governor = "schedutil"

    @patch("resource_manager.requests")
    def test_idle_uses_schedutil(self, mock_req):
        """Idle durumda schedutil governor kullanılır."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "standby"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp

        m = make_metrics()
        actions = self.mgr.evaluate(m)
        # Zaten schedutil'deyiz, degisiklik yok
        gov_actions = [a for a in actions if a[0] == ResourceAction.SET_GOVERNOR]
        assert len(gov_actions) == 0

    @patch("resource_manager.requests")
    def test_printing_uses_performance(self, mock_req):
        """Baski sirasinda performance governor kullanilir."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "printing"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp

        m = make_metrics()
        actions = self.mgr.evaluate(m)
        gov_actions = [a for a in actions if a[0] == ResourceAction.SET_GOVERNOR]
        assert len(gov_actions) == 1
        assert gov_actions[0][1]["governor"] == "performance"

    @patch("resource_manager.requests")
    def test_paused_uses_ondemand(self, mock_req):
        """Duraklatilmis durumda ondemand governor kullanilir."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "paused"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp

        m = make_metrics()
        actions = self.mgr.evaluate(m)
        gov_actions = [a for a in actions if a[0] == ResourceAction.SET_GOVERNOR]
        assert len(gov_actions) == 1
        assert gov_actions[0][1]["governor"] == "ondemand"


# ─── Termal Koruma Testleri ───────────────────────────────────────────────────

class TestThermalProtection:
    """CPU termal koruma testleri."""

    def setup_method(self):
        self.mgr = AIResourceManager()
        self.mgr._current_governor = "performance"

    @patch("resource_manager.requests")
    def test_critical_temp_forces_powersave(self, mock_req):
        """82°C uzerinde powersave zorlanir."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "printing"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp
        mock_req.post.return_value = MagicMock()

        m = make_metrics(cpu_temperature=85.0)
        actions = self.mgr.evaluate(m)

        gov_actions = [a for a in actions if a[0] == ResourceAction.SET_GOVERNOR]
        assert len(gov_actions) == 1
        assert gov_actions[0][1]["governor"] == "powersave"
        assert self.mgr._thermal_override is True

    @patch("resource_manager.requests")
    def test_thermal_override_blocks_governor_change(self, mock_req):
        """Termal override aktifken governor degismez."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "printing"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp
        mock_req.post.return_value = MagicMock()

        # Ilk: kritik sicaklik
        m = make_metrics(cpu_temperature=85.0)
        self.mgr.evaluate(m)
        assert self.mgr._thermal_override is True

        # Ikinci: hala sicak — degisiklik yok
        m2 = make_metrics(cpu_temperature=84.0)
        actions = self.mgr.evaluate(m2)
        gov_actions = [a for a in actions if a[0] == ResourceAction.SET_GOVERNOR]
        assert len(gov_actions) == 0

    @patch("resource_manager.requests")
    def test_temp_recovery_restores_normal(self, mock_req):
        """Sicaklik dusunce override kalkar."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "printing"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp
        mock_req.post.return_value = MagicMock()

        # Kritik
        m1 = make_metrics(cpu_temperature=85.0)
        self.mgr.evaluate(m1)
        assert self.mgr._thermal_override is True

        # Soguk
        m2 = make_metrics(cpu_temperature=60.0)
        actions = self.mgr.evaluate(m2)
        assert self.mgr._thermal_override is False

        # Kamera FPS geri yuklenmelı
        cam_actions = [a for a in actions if a[0] == ResourceAction.THROTTLE_CAMERA]
        assert len(cam_actions) >= 1
        assert cam_actions[0][1]["fps"] == 15

    @patch("resource_manager.requests")
    def test_warning_temp_notifies(self, mock_req):
        """75°C uyari bildirim gonderir."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "printing"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp

        m = make_metrics(cpu_temperature=78.0)
        actions = self.mgr.evaluate(m)
        notify_actions = [a for a in actions if a[0] == ResourceAction.NOTIFY]
        assert len(notify_actions) >= 1


# ─── Bellek Yonetimi Testleri ─────────────────────────────────────────────────

class TestMemoryManagement:
    """Bellek esik testleri."""

    def setup_method(self):
        self.mgr = AIResourceManager()
        self.mgr._current_governor = "performance"

    @patch("resource_manager.requests")
    def test_critical_memory_triggers_relief(self, mock_req):
        """90%+ bellek kullanımında acil kurtarma yapilir."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "printing"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp

        m = make_metrics(memory_percent=95.0)
        actions = self.mgr.evaluate(m)
        relief_actions = [a for a in actions if a[0] == ResourceAction.MEMORY_RELIEF]
        assert len(relief_actions) == 1

    @patch("resource_manager.requests")
    def test_warning_memory_notifies(self, mock_req):
        """80%+ bellek uyari bildirim gonderir."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "printing"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp

        m = make_metrics(memory_percent=85.0)
        actions = self.mgr.evaluate(m)
        notify_actions = [a for a in actions if a[0] == ResourceAction.NOTIFY]
        assert len(notify_actions) >= 1

    @patch("resource_manager.requests")
    def test_normal_memory_no_action(self, mock_req):
        """Normal bellek kullanımında aksiyon yok."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {"status": {"print_stats": {"state": "standby"}}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_req.get.return_value = mock_resp

        self.mgr._current_governor = "schedutil"
        m = make_metrics(memory_percent=50.0)
        actions = self.mgr.evaluate(m)
        relief_actions = [a for a in actions if a[0] == ResourceAction.MEMORY_RELIEF]
        assert len(relief_actions) == 0


# ─── Metrik ve Gecmis Testleri ────────────────────────────────────────────────

class TestMetricsHistory:
    """Metrik toplama ve gecmis testleri."""

    def test_history_max_size(self):
        mgr = AIResourceManager()
        for i in range(100):
            m = make_metrics(cpu_percent=float(i))
            mgr._metrics_history.append(m)
        assert len(mgr._metrics_history) == mgr.HISTORY_SIZE

    def test_status_returns_dict(self):
        mgr = AIResourceManager()
        mgr._metrics_history.append(make_metrics())
        status = mgr.status
        assert "governor" in status
        assert "printer_state" in status
        assert "metrics" in status
        assert "policy" in status

    def test_policy_custom_values(self):
        policy = ResourcePolicy(
            memory_warning_pct=70,
            memory_critical_pct=85,
            cpu_temp_warning=65,
            cpu_temp_critical=78,
        )
        mgr = AIResourceManager(policy=policy)
        assert mgr.policy.memory_warning_pct == 70
        assert mgr.policy.cpu_temp_critical == 78


# ─── Service Dosya Testleri ───────────────────────────────────────────────────

class TestResourceManagerService:
    """kos-resource-manager.service testleri."""

    SERVICE = CONFIG / "systemd" / "kos-resource-manager.service"

    def test_exists(self):
        assert self.SERVICE.exists()

    def test_has_memory_limit(self):
        content = self.SERVICE.read_text()
        assert "MemoryMax=64M" in content

    def test_has_cpu_quota(self):
        content = self.SERVICE.read_text()
        assert "CPUQuota=10%" in content

    def test_runs_as_root(self):
        content = self.SERVICE.read_text()
        assert "User=root" in content

    def test_ordering(self):
        content = self.SERVICE.read_text()
        assert "After=" in content
        assert "kos-os-tuning.service" in content


# ─── Governor Map Testleri ────────────────────────────────────────────────────

class TestGovernorMap:
    """Governor haritasi tutarlilik testleri."""

    def test_all_states_mapped(self):
        for state in [PrinterState.IDLE, PrinterState.PRINTING, PrinterState.PAUSED]:
            assert state in GOVERNOR_MAP

    def test_printing_is_performance(self):
        assert GOVERNOR_MAP[PrinterState.PRINTING] == "performance"

    def test_idle_is_schedutil(self):
        assert GOVERNOR_MAP[PrinterState.IDLE] == "schedutil"

    def test_paused_is_ondemand(self):
        assert GOVERNOR_MAP[PrinterState.PAUSED] == "ondemand"

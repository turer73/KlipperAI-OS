"""Tests for KOS System API module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import subprocess
import pytest
from unittest.mock import patch, MagicMock, mock_open

from kos_system_api import KosSystemAPI, KOS_SERVICES


@pytest.fixture
def api():
    return KosSystemAPI()


# ---------------------------------------------------------------------------
# TestSystemInfo
# ---------------------------------------------------------------------------
class TestSystemInfo:
    """Tests for CPU, memory, disk, and uptime methods."""

    def test_get_cpu_info(self, api):
        mock_psutil = MagicMock()
        mock_psutil.cpu_percent.return_value = 23.5
        mock_psutil.cpu_freq.return_value = MagicMock(current=1500.0)
        mock_psutil.cpu_count.return_value = 4
        # temperatures: some systems use 'cpu_thermal', others 'coretemp'
        mock_psutil.sensors_temperatures.return_value = {
            "cpu_thermal": [MagicMock(current=52.3)]
        }

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            info = api.get_cpu_info()

        assert info["usage_percent"] == 23.5
        assert info["temperature"] == 52.3
        assert info["frequency_mhz"] == 1500.0
        assert info["core_count"] == 4

    def test_get_memory_info(self, api):
        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=1073741824,       # 1024 MB
            used=536870912,         # 512 MB
            available=536870912,    # 512 MB
            percent=50.0,
        )
        mock_psutil.swap_memory.return_value = MagicMock(
            total=524288000,        # ~500 MB zram
            used=104857600,         # ~100 MB
        )

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            info = api.get_memory_info()

        assert info["total_mb"] == 1024.0
        assert info["used_mb"] == 512.0
        assert info["available_mb"] == 512.0
        assert info["percent"] == 50.0
        assert info["zram_total_mb"] == pytest.approx(500.0, abs=1)
        assert info["zram_used_mb"] == pytest.approx(100.0, abs=1)

    def test_get_disk_info(self, api):
        mock_psutil = MagicMock()
        mock_psutil.disk_usage.return_value = MagicMock(
            total=32212254720,      # 30 GB
            used=16106127360,       # 15 GB
            free=16106127360,       # 15 GB
            percent=50.0,
        )

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            info = api.get_disk_info()

        assert info["total_gb"] == pytest.approx(30.0, abs=0.1)
        assert info["used_gb"] == pytest.approx(15.0, abs=0.1)
        assert info["free_gb"] == pytest.approx(15.0, abs=0.1)
        assert info["percent"] == 50.0

    def test_get_uptime(self, api):
        # Simulate 2 days, 3 hours, 45 minutes, 12 seconds of uptime
        total_seconds = 2 * 86400 + 3 * 3600 + 45 * 60 + 12
        result = MagicMock()
        result.returncode = 0
        result.stdout = str(total_seconds) + "\n"

        with patch.object(api, '_run', return_value=result):
            uptime = api.get_uptime()

        assert "2g" in uptime
        assert "3s" in uptime
        assert "45dk" in uptime


# ---------------------------------------------------------------------------
# TestNetworkOperations
# ---------------------------------------------------------------------------
class TestNetworkOperations:
    """Tests for WiFi and network methods."""

    def test_get_wifi_networks(self, api):
        nmcli_output = (
            "MyNetwork:85:WPA2\n"
            "GuestWiFi:60:WPA1\n"
            "OpenNet:45:\n"
        )
        result = MagicMock()
        result.returncode = 0
        result.stdout = nmcli_output

        with patch.object(api, '_run', return_value=result):
            networks = api.get_wifi_networks()

        assert len(networks) == 3
        assert networks[0]["ssid"] == "MyNetwork"
        assert networks[0]["signal"] == "85"
        assert networks[0]["security"] == "WPA2"
        assert networks[2]["security"] == ""

    def test_get_current_ip(self, api):
        # Mock hostname
        hostname_result = MagicMock()
        hostname_result.returncode = 0
        hostname_result.stdout = "klipperos\n"

        # Mock ip route
        ip_result = MagicMock()
        ip_result.returncode = 0
        ip_result.stdout = "default via 192.168.1.1 dev wlan0 proto dhcp src 192.168.1.100 metric 600\n"

        with patch.object(api, '_run', side_effect=[hostname_result, ip_result]):
            info = api.get_current_ip()

        assert info["hostname"] == "klipperos"
        assert info["ip"] == "192.168.1.100"
        assert info["interface"] == "wlan0"

    def test_connect_wifi(self, api):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "Device 'wlan0' successfully activated"

        with patch.object(api, '_run', return_value=result):
            success = api.connect_wifi("TestSSID", "password123")

        assert success is True


# ---------------------------------------------------------------------------
# TestServiceOperations
# ---------------------------------------------------------------------------
class TestServiceOperations:
    """Tests for systemctl service management."""

    def test_get_service_status_active(self, api):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "active\n"

        with patch.object(api, '_run', return_value=result):
            status = api.get_service_status("klipper")

        assert status == "active"

    def test_list_kos_services(self, api):
        def side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 0
            service_name = cmd[-1]
            if service_name in ("klipper", "moonraker", "nginx"):
                mock_result.stdout = "active\n"
            else:
                mock_result.stdout = "inactive\n"
            return mock_result

        with patch.object(api, '_run', side_effect=side_effect):
            services = api.list_kos_services()

        assert len(services) == len(KOS_SERVICES)
        klipper_svc = next(s for s in services if s["name"] == "klipper")
        assert klipper_svc["status"] == "active"

    def test_restart_service_allowed(self, api):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""

        with patch.object(api, '_run', return_value=result):
            success = api.restart_service("klipper")

        assert success is True

    def test_restart_service_disallowed(self, api):
        """Attempting to restart a non-whitelisted service returns False."""
        success = api.restart_service("sshd")
        assert success is False


# ---------------------------------------------------------------------------
# TestTailscale
# ---------------------------------------------------------------------------
class TestTailscale:
    """Tests for Tailscale CLI integration."""

    def test_get_tailscale_status_connected(self, api):
        ts_output = (
            "# Tailscale is running\n"
            "100.64.0.1  klipperos  user@  linux  -\n"
        )
        result = MagicMock()
        result.returncode = 0
        result.stdout = ts_output

        with patch.object(api, '_run', return_value=result):
            status = api.get_tailscale_status()

        assert status["connected"] is True
        assert status["ip"] == "100.64.0.1"
        assert status["hostname"] == "klipperos"

    def test_tailscale_up(self, api):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""

        with patch.object(api, '_run', return_value=result):
            success = api.tailscale_up()

        assert success is True


# ---------------------------------------------------------------------------
# TestPowerOperations
# ---------------------------------------------------------------------------
class TestPowerOperations:
    """Tests for shutdown and reboot."""

    def test_shutdown(self, api):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""

        with patch.object(api, '_run', return_value=result):
            success = api.shutdown()

        assert success is True

    def test_reboot(self, api):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""

        with patch.object(api, '_run', return_value=result):
            success = api.reboot()

        assert success is True


# ---------------------------------------------------------------------------
# TestMoonrakerFileAPI
# ---------------------------------------------------------------------------
class TestMoonrakerFileAPI:
    """Tests for Moonraker HTTP API integration."""

    def test_read_config(self, api):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "[printer]\nkinematics = cartesian\n"

        with patch("kos_system_api.requests.get", return_value=mock_response):
            content = api.read_config("printer.cfg")

        assert content is not None
        assert "kinematics" in content

    def test_write_config(self, api):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"item": {"path": "printer.cfg"}}

        with patch("kos_system_api.requests.post", return_value=mock_response):
            success = api.write_config("printer.cfg", "[printer]\nkinematics = corexy\n")

        assert success is True

    def test_read_config_failure(self, api):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch("kos_system_api.requests.get", return_value=mock_response):
            content = api.read_config("nonexistent.cfg")

        assert content is None

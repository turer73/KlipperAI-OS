# tests/test_ks_panels.py
"""Tests for KlipperScreen panels — import and basic structure checks."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import pytest
from unittest.mock import patch, MagicMock


class TestPowerPanel:
    def test_import(self):
        from kos_power import PANEL_TITLE, PANEL_ACTIONS
        assert PANEL_TITLE == "Guc Yonetimi"
        assert "shutdown" in PANEL_ACTIONS
        assert "reboot" in PANEL_ACTIONS
        assert "restart_klipper" in PANEL_ACTIONS

    @patch("kos_system_api.subprocess.run")
    def test_shutdown_action(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from kos_power import execute_action
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = execute_action(api, "shutdown")
        assert result is True

    @patch("kos_system_api.subprocess.run")
    def test_reboot_action(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from kos_power import execute_action
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = execute_action(api, "reboot")
        assert result is True


class TestSysInfoPanel:
    def test_import(self):
        from kos_sysinfo import PANEL_TITLE, get_panel_data
        assert PANEL_TITLE == "Sistem Bilgisi"

    def test_get_panel_data(self):
        from kos_sysinfo import get_panel_data
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        data = get_panel_data(api)
        assert "cpu" in data
        assert "memory" in data
        assert "disk" in data
        assert "uptime" in data

    def test_format_cpu_line(self):
        from kos_sysinfo import format_cpu_line
        line = format_cpu_line({"usage_percent": 45.2, "temperature": 52.3, "frequency_mhz": 1500})
        assert "45%" in line
        assert "1500 MHz" in line
        assert "52.3°C" in line

    def test_format_memory_line(self):
        from kos_sysinfo import format_memory_line
        line = format_memory_line({"used_mb": 512, "total_mb": 2048, "percent": 25, "zram_total_mb": 1024})
        assert "512/2048" in line
        assert "25%" in line
        assert "zram: 1024" in line

    def test_format_disk_line(self):
        from kos_sysinfo import format_disk_line
        line = format_disk_line({"used_gb": 8.5, "total_gb": 32.0, "percent": 27})
        assert "8.5/32.0" in line
        assert "27%" in line

    def test_format_mcu_lines_empty(self):
        from kos_sysinfo import format_mcu_lines
        lines = format_mcu_lines({})
        assert len(lines) == 1
        assert "alinamiyor" in lines[0]

    def test_format_mcu_lines_with_data(self):
        from kos_sysinfo import format_mcu_lines
        mcu = {"mcu": {"temperature": 45.0, "voltage": 3.3}}
        lines = format_mcu_lines(mcu)
        assert len(lines) == 1
        assert "45.0°C" in lines[0]
        assert "3.30V" in lines[0]

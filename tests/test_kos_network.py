# tests/test_kos_network.py
"""Tests for Network panel."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import pytest
from unittest.mock import patch, MagicMock


class TestNetworkPanel:
    def test_import(self):
        from kos_network import PANEL_TITLE, get_panel_data
        assert PANEL_TITLE == "Ag Ayarlari"

    @patch("kos_system_api.subprocess.run")
    def test_get_panel_data(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="192.168.1.100\n")
        from kos_network import get_panel_data
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        data = get_panel_data(api)
        assert "ip_info" in data
        assert "wifi_networks" in data

    def test_format_network_info(self):
        from kos_network import format_network_info
        info = format_network_info({"ip": "192.168.1.100", "interface": "wlan0"})
        assert "192.168.1.100" in info
        assert "wlan0" in info

    def test_format_network_info_no_connection(self):
        from kos_network import format_network_info
        info = format_network_info({})
        assert "Baglanti yok" in info

    def test_format_wifi_list(self):
        from kos_network import format_wifi_list
        networks = [
            {"ssid": "MyWiFi", "signal": 80, "security": "WPA2"},
            {"ssid": "Guest", "signal": 30, "security": "OPEN"},
        ]
        lines = format_wifi_list(networks)
        assert len(lines) == 2
        assert "MyWiFi" in lines[0]
        assert "80%" in lines[0]

    @patch("kos_system_api.subprocess.run")
    def test_connect_to_wifi(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        from kos_network import connect_to_wifi
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = connect_to_wifi(api, "TestSSID", "password123")
        assert result is True

# tests/test_kos_tailscale.py
"""Tests for Tailscale VPN panel."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import pytest
from unittest.mock import patch, MagicMock


class TestTailscalePanel:
    def test_import(self):
        from kos_tailscale import PANEL_TITLE, get_panel_data
        assert PANEL_TITLE == "Tailscale VPN"

    def test_format_status_connected(self):
        from kos_tailscale import _format_status
        status = {"connected": True, "ip": "100.64.0.1", "hostname": "klipper-pi"}
        text = _format_status(status)
        assert "Bagli" in text
        assert "100.64.0.1" in text
        assert "klipper-pi" in text

    def test_format_status_disconnected(self):
        from kos_tailscale import _format_status
        text = _format_status({"connected": False})
        assert "degil" in text

    @patch("kos_system_api.subprocess.run")
    def test_get_panel_data(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"BackendState":"Running","TailscaleIPs":["100.64.0.1"],"Self":{"HostName":"klipper"}}')
        from kos_tailscale import get_panel_data
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        data = get_panel_data(api)
        assert "connected" in data
        assert "status_text" in data

    @patch("kos_system_api.subprocess.run")
    def test_connect(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        from kos_tailscale import connect
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = connect(api)
        assert result is True

    @patch("kos_system_api.subprocess.run")
    def test_disconnect(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        from kos_tailscale import disconnect
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = disconnect(api)
        assert result is True

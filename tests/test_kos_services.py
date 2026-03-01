# tests/test_kos_services.py
"""Tests for Service Management panel."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import pytest
from unittest.mock import patch, MagicMock


class TestServicesPanel:
    def test_import(self):
        from kos_services import PANEL_TITLE, get_panel_data
        assert PANEL_TITLE == "Servis Yonetimi"

    @patch("kos_system_api.subprocess.run")
    def test_get_panel_data(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="active\nrunning\n")
        from kos_services import get_panel_data
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        data = get_panel_data(api)
        assert "services" in data
        assert len(data["services"]) == 6

    def test_format_service_active(self):
        from kos_services import format_service_status
        text = format_service_status({"name": "klipper", "active": True})
        assert "\u25cf" in text
        assert "klipper" in text
        assert "aktif" in text

    def test_format_service_inactive(self):
        from kos_services import format_service_status
        text = format_service_status({"name": "crowsnest", "active": False})
        assert "\u25cb" in text
        assert "durdu" in text

    @patch("kos_system_api.subprocess.run")
    def test_service_restart(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        from kos_services import service_action
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = service_action(api, "klipper", "restart")
        assert result is True

    def test_service_unknown_action(self):
        from kos_services import service_action
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = service_action(api, "klipper", "explode")
        assert result is False

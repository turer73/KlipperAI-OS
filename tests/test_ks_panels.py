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

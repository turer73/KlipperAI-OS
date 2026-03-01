# tests/test_kos_ai_settings.py
"""Tests for AI Settings panel."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import pytest
from unittest.mock import patch, MagicMock
import json


class TestAISettingsPanel:
    def test_import(self):
        from kos_ai_settings import PANEL_TITLE, DEFAULT_SETTINGS
        assert PANEL_TITLE == "AI Ayarlari"
        assert "enabled" in DEFAULT_SETTINGS
        assert "check_interval_seconds" in DEFAULT_SETTINGS

    def test_format_settings_display(self):
        from kos_ai_settings import format_settings_display, DEFAULT_SETTINGS
        text = format_settings_display(DEFAULT_SETTINGS)
        assert "AI Monitor: Acik" in text
        assert "FlowGuard: Acik" in text
        assert "10s" in text

    def test_format_settings_disabled(self):
        from kos_ai_settings import format_settings_display
        settings = {"enabled": False, "flow_guard_enabled": False, "layer_check_enabled": False,
                     "check_interval_seconds": 20, "flow_deviation_threshold": 15, "temp_deviation_threshold": 10}
        text = format_settings_display(settings)
        assert "AI Monitor: Kapali" in text
        assert "FlowGuard: Kapali" in text

    @patch("kos_system_api.requests.get")
    def test_load_settings_default(self, mock_get):
        mock_get.side_effect = Exception("no connection")
        from kos_ai_settings import load_settings
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        settings = load_settings(api)
        assert settings["enabled"] is True
        assert settings["check_interval_seconds"] == 10

    def test_update_setting_unknown_key(self):
        from kos_ai_settings import update_setting
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = update_setting(api, "nonexistent_key", 42)
        assert result is False

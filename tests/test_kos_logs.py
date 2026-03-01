# tests/test_kos_logs.py
"""Tests for Log Viewer panel."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import pytest
from unittest.mock import patch, MagicMock


class TestLogViewerPanel:
    def test_import(self):
        from kos_logs import PANEL_TITLE, LOG_SOURCES
        assert PANEL_TITLE == "Log Goruntule"
        assert "klippy" in LOG_SOURCES
        assert "moonraker" in LOG_SOURCES
        assert "ai-monitor" in LOG_SOURCES

    def test_format_log_header(self):
        from kos_logs import format_log_header
        header = format_log_header("klippy", 50)
        assert "klippy" in header
        assert "50" in header

    def test_get_panel_data(self):
        from kos_logs import get_panel_data
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        data = get_panel_data(api, "klippy")
        assert data["source"] == "klippy"
        assert "sources" in data
        assert "content" in data
        assert "line_count" in data

    def test_get_panel_data_defaults(self):
        from kos_logs import get_panel_data
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        data = get_panel_data(api)
        assert data["source"] == "klippy"  # default source

    def test_log_sources_match_log_paths(self):
        from kos_logs import LOG_SOURCES
        from kos_system_api import LOG_PATHS
        assert set(LOG_SOURCES) == set(LOG_PATHS.keys())

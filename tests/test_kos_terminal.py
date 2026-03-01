# tests/test_kos_terminal.py
"""Tests for Terminal panel (VTE3-independent tests only)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import pytest


class TestTerminalPanel:
    def test_import_constants(self):
        from kos_terminal import PANEL_TITLE, DEFAULT_SHELL, DEFAULT_FONT_SIZE
        assert PANEL_TITLE == "Terminal"
        assert DEFAULT_SHELL == "/bin/bash"
        assert DEFAULT_FONT_SIZE == 11

    def test_get_panel_data(self):
        from kos_terminal import get_panel_data
        data = get_panel_data()
        assert data["title"] == "Terminal"
        assert data["shell"] == "/bin/bash"
        assert "user" in data
        assert data["font_size"] == 11

    def test_font_size_bounds(self):
        from kos_terminal import MIN_FONT_SIZE, MAX_FONT_SIZE
        assert MIN_FONT_SIZE < MAX_FONT_SIZE
        assert MIN_FONT_SIZE >= 6
        assert MAX_FONT_SIZE <= 30

    def test_vte_class_conditional(self):
        """TerminalPanel GTK class should NOT be available on Windows/CI."""
        import importlib
        mod = importlib.import_module("kos_terminal")
        # TerminalPanel may or may not exist depending on VTE3 availability
        # This test just verifies the module doesn't crash on import
        assert hasattr(mod, "PANEL_TITLE")
        assert hasattr(mod, "get_panel_data")

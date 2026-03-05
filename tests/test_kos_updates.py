# tests/test_kos_updates.py
"""Tests for Update Management panel."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock


class TestUpdatesPanel:
    def test_import(self):
        from kos_updates import PANEL_TITLE, UPDATE_REPOS
        assert PANEL_TITLE == "Guncelleme"
        assert "klipper" in UPDATE_REPOS
        assert "KlipperOS-AI" in UPDATE_REPOS

    def test_format_repo_status_uptodate(self):
        from kos_updates import format_repo_status
        text = format_repo_status({"name": "klipper", "has_updates": False, "current_sha": "abc1234"})
        assert "\u2713" in text
        assert "guncel" in text

    def test_format_repo_status_has_updates(self):
        from kos_updates import format_repo_status
        text = format_repo_status({"name": "klipper", "has_updates": True, "behind_count": 3, "current_sha": "abc1234"})
        assert "\u2191" in text
        assert "3" in text

    def test_format_repo_status_error(self):
        from kos_updates import format_repo_status
        text = format_repo_status({"name": "klipper", "error": "git not found"})
        assert "\u26a0" in text
        assert "hata" in text

    @patch("tools.kos_update.git_check_updates")
    def test_check_repo(self, mock_check):
        # git_check_updates returns tuple[bool, str]
        mock_check.return_value = (True, "5 yeni commit")
        from kos_updates import _check_repo
        result = _check_repo("klipper", "/home/klipper/klipper")
        assert result["has_updates"] is True
        assert result["behind_count"] == 5
        assert result["name"] == "klipper"

    @patch("tools.kos_update.git_update")
    def test_update_repo(self, mock_update):
        mock_update.return_value = True
        from kos_updates import update_repo
        result = update_repo("klipper")
        assert result is True

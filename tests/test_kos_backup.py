# tests/test_kos_backup.py
"""Tests for Backup Management panel."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock


class TestBackupPanel:
    def test_import(self):
        from kos_backup_panel import PANEL_TITLE
        assert PANEL_TITLE == "Yedekleme"

    def test_format_backup_entry(self):
        from kos_backup_panel import format_backup_entry
        text = format_backup_entry({"name": "backup_20260301.tar.zst", "size_mb": 15.3, "date": "2026-03-01"})
        assert "backup_20260301" in text
        assert "15.3 MB" in text
        assert "2026-03-01" in text

    @patch("tools.kos_backup.list_backups")
    def test_get_panel_data(self, mock_list):
        mock_list.return_value = [
            {"name": "b1.tar.zst", "path": "/backups/b1.tar.zst", "size_mb": 10, "date": "2026-01-01"},
        ]
        from kos_backup_panel import get_panel_data
        data = get_panel_data()
        assert "backups" in data
        assert len(data["backups"]) == 1

    @patch("tools.kos_backup.create_backup")
    def test_create_new_backup(self, mock_create):
        mock_create.return_value = "/backups/new.tar.zst"
        from kos_backup_panel import create_new_backup
        result = create_new_backup()
        assert result == "/backups/new.tar.zst"

    @patch("tools.kos_backup.restore_backup")
    def test_restore_backup(self, mock_restore):
        mock_restore.return_value = True
        from kos_backup_panel import restore_selected_backup
        result = restore_selected_backup("/backups/b1.tar.zst")
        assert result is True

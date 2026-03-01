# ks-panels/kos_backup_panel.py
"""KlipperOS-AI — Backup Management Panel for KlipperScreen.

List backups, create new, restore selected.
"""

import logging
import sys
import os
from typing import Optional, List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from kos_system_api import KosSystemAPI

logger = logging.getLogger("KOS-Backup")

PANEL_TITLE = "Yedekleme"
BACKUP_DIR = os.path.expanduser("~/printer_data/backups")


def get_panel_data() -> dict:
    """Get backup list for panel display."""
    try:
        from tools.kos_backup import list_backups
        backups = list_backups(BACKUP_DIR)
    except Exception as exc:
        logger.warning("Yedek listesi alinamadi: %s", exc)
        backups = []
    return {
        "title": PANEL_TITLE,
        "backups": backups,
        "backup_dir": BACKUP_DIR,
    }


def create_new_backup() -> Optional[str]:
    """Create a new backup."""
    try:
        from tools.kos_backup import create_backup
        path = create_backup(BACKUP_DIR)
        if path:
            logger.info("Yedek olusturuldu: %s", path)
        return path
    except Exception as exc:
        logger.error("Yedek olusturma hatasi: %s", exc)
        return None


def restore_selected_backup(backup_path: str) -> bool:
    """Restore a selected backup."""
    try:
        from tools.kos_backup import restore_backup
        restore_dir = os.path.expanduser("~/printer_data/config")
        result = restore_backup(backup_path, restore_dir)
        if result:
            logger.info("Yedek geri yuklendi: %s", backup_path)
        return result
    except Exception as exc:
        logger.error("Geri yukleme hatasi: %s", exc)
        return False


def format_backup_entry(backup: dict) -> str:
    """Format backup entry for display."""
    name = backup.get("name", "?")
    size = backup.get("size_mb", 0)
    date = backup.get("date", "?")
    return f"{name}  |  {size:.1f} MB  |  {date}"


# --- GTK Panel ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    class BackupPanel:
        """KlipperScreen backup management panel."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()
            self._backups: List[dict] = []
            self._selected_idx: Optional[int] = None

        def build_ui(self) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(15)
            box.set_margin_start(15)
            box.set_margin_end(15)

            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 10)

            # Create backup button
            create_btn = Gtk.Button(label="Yeni Yedek Olustur")
            create_btn.connect("clicked", self._on_create)
            create_btn.set_size_request(-1, 45)
            box.pack_start(create_btn, False, False, 5)

            # Backup list
            scroll = Gtk.ScrolledWindow()
            scroll.set_min_content_height(200)
            self._listbox = Gtk.ListBox()
            self._listbox.connect("row-selected", self._on_selected)
            scroll.add(self._listbox)
            box.pack_start(scroll, True, True, 5)

            # Restore button
            self._restore_btn = Gtk.Button(label="Secili Yedegi Geri Yukle")
            self._restore_btn.connect("clicked", self._on_restore)
            self._restore_btn.set_sensitive(False)
            box.pack_start(self._restore_btn, False, False, 5)

            # Status
            self._status_label = Gtk.Label(label="")
            box.pack_start(self._status_label, False, False, 5)

            # Load initial data
            self._refresh_list()

            return box

        def _refresh_list(self):
            data = get_panel_data()
            self._backups = data["backups"]
            for child in self._listbox.get_children():
                self._listbox.remove(child)
            for backup in self._backups:
                row = Gtk.ListBoxRow()
                label = Gtk.Label(label=format_backup_entry(backup))
                label.set_halign(Gtk.Align.START)
                row.add(label)
                self._listbox.add(row)
            self._listbox.show_all()

        def _on_selected(self, _listbox, row):
            if row:
                self._selected_idx = row.get_index()
                self._restore_btn.set_sensitive(True)
            else:
                self._selected_idx = None
                self._restore_btn.set_sensitive(False)

        def _on_create(self, _btn):
            self._status_label.set_text("Yedek olusturuluyor...")
            path = create_new_backup()
            if path:
                self._status_label.set_text("Yedek olusturuldu")
                self._refresh_list()
            else:
                self._status_label.set_text("Yedek olusturma basarisiz")

        def _on_restore(self, _btn):
            if self._selected_idx is None or self._selected_idx >= len(self._backups):
                return
            backup = self._backups[self._selected_idx]
            path = backup.get("path", "")
            self._status_label.set_text("Geri yukleniyor...")
            success = restore_selected_backup(path)
            if success:
                self._status_label.set_text("Geri yukleme basarili")
            else:
                self._status_label.set_text("Geri yukleme basarisiz")

except ImportError:
    pass

# ks-panels/kos_updates.py
"""KlipperOS-AI — Update Management Panel for KlipperScreen.

Check for updates, update individual components with progress.
"""

import logging
import sys
import os
from typing import Optional, List, Dict

# Add project root to path for tools import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from kos_system_api import KosSystemAPI

logger = logging.getLogger("KOS-Updates")

PANEL_TITLE = "Guncelleme"

# Repos to check
UPDATE_REPOS = {
    "klipper": "~/klipper",
    "moonraker": "~/moonraker",
    "KlipperScreen": "~/KlipperScreen",
    "crowsnest": "~/crowsnest",
    "KlipperOS-AI": "~/KlipperOS-AI",
}


def get_panel_data() -> dict:
    """Get update status for all repos."""
    results = []
    for name, path in UPDATE_REPOS.items():
        expanded = os.path.expanduser(path)
        status = _check_repo(name, expanded)
        results.append(status)
    return {
        "title": PANEL_TITLE,
        "repos": results,
    }


def _check_repo(name: str, path: str) -> dict:
    """Check a single repo for updates."""
    try:
        from tools.kos_update import git_check_updates
        from pathlib import Path
        has_update, message = git_check_updates(Path(path))
        # Parse commit count from message like "5 yeni commit"
        behind_count = 0
        if has_update:
            parts = message.split()
            if parts and parts[0].isdigit():
                behind_count = int(parts[0])
        return {
            "name": name,
            "has_updates": has_update,
            "behind_count": behind_count,
            "current_sha": "",
        }
    except Exception as exc:
        logger.warning("Update check basarisiz %s: %s", name, exc)
        return {
            "name": name,
            "has_updates": False,
            "behind_count": 0,
            "current_sha": "?",
            "error": str(exc),
        }


def update_repo(name: str) -> bool:
    """Update a single repo."""
    path = UPDATE_REPOS.get(name)
    if not path:
        return False
    expanded = os.path.expanduser(path)
    try:
        from tools.kos_update import git_update
        result = git_update(expanded)
        if result:
            logger.info("Guncelleme basarili: %s", name)
        else:
            logger.warning("Guncelleme basarisiz: %s", name)
        return result
    except Exception as exc:
        logger.error("Guncelleme hatasi %s: %s", name, exc)
        return False


def format_repo_status(repo: dict) -> str:
    """Format repo status for display."""
    name = repo.get("name", "?")
    sha = repo.get("current_sha", "?")
    if repo.get("error"):
        return f"\u26a0 {name}: hata ({repo['error'][:30]})"
    if repo.get("has_updates"):
        behind = repo.get("behind_count", 0)
        return f"\u2191 {name}: {behind} guncelleme mevcut ({sha})"
    return f"\u2713 {name}: guncel ({sha})"


# --- GTK Panel ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    class UpdatesPanel:
        """KlipperScreen update management panel."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()
            self._labels: Dict[str, Gtk.Label] = {}
            self._buttons: Dict[str, Gtk.Button] = {}

        def build_ui(self) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(15)
            box.set_margin_start(15)
            box.set_margin_end(15)

            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 10)

            # Check all button
            check_btn = Gtk.Button(label="Tum Guncellemeleri Kontrol Et")
            check_btn.connect("clicked", self._on_check_all)
            check_btn.set_size_request(-1, 45)
            box.pack_start(check_btn, False, False, 5)

            # Repo rows
            for name in UPDATE_REPOS:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
                label = Gtk.Label(label=f"  {name}: kontrol edilmedi")
                label.set_halign(Gtk.Align.START)
                label.set_hexpand(True)
                update_btn = Gtk.Button(label="Guncelle")
                update_btn.connect("clicked", self._on_update, name)
                update_btn.set_sensitive(False)
                update_btn.set_size_request(80, 35)
                row.pack_start(label, True, True, 0)
                row.pack_start(update_btn, False, False, 0)
                self._labels[name] = label
                self._buttons[name] = update_btn
                box.pack_start(row, False, False, 3)

            self._status_label = Gtk.Label(label="")
            box.pack_start(self._status_label, False, False, 10)

            return box

        def _on_check_all(self, _btn):
            self._status_label.set_text("Kontrol ediliyor...")
            data = get_panel_data()
            for repo in data["repos"]:
                name = repo["name"]
                if name in self._labels:
                    self._labels[name].set_text(format_repo_status(repo))
                    self._buttons[name].set_sensitive(repo.get("has_updates", False))
            self._status_label.set_text("Kontrol tamamlandi")

        def _on_update(self, _btn, name: str):
            self._status_label.set_text(f"Guncelleniyor: {name}...")
            success = update_repo(name)
            if success:
                self._labels[name].set_text(f"\u2713 {name}: guncellendi")
                self._buttons[name].set_sensitive(False)
                self._status_label.set_text(f"{name} guncellendi")
            else:
                self._status_label.set_text(f"{name} guncelleme basarisiz")

except ImportError:
    pass

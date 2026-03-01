# ks-panels/kos_mcu_panel.py
"""KlipperOS-AI — MCU Management Panel for KlipperScreen.

Scan MCU boards, show board info, flash firmware.
"""

import logging
import sys
import os
from typing import Optional, List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from kos_system_api import KosSystemAPI

logger = logging.getLogger("KOS-MCU")

PANEL_TITLE = "MCU Yonetimi"


def get_panel_data() -> dict:
    """Get MCU/board info for panel display."""
    ports = scan_ports()
    boards = get_board_list()
    return {
        "title": PANEL_TITLE,
        "ports": ports,
        "boards": boards,
    }


def scan_ports() -> List[dict]:
    """Scan for serial ports (MCU boards)."""
    try:
        from tools.kos_mcu import find_serial_ports
        return find_serial_ports()
    except Exception as exc:
        logger.warning("Port tarama hatasi: %s", exc)
        return []


def get_board_list() -> Dict[str, dict]:
    """Get supported board database."""
    try:
        from tools.kos_mcu import load_board_db
        return load_board_db()
    except Exception as exc:
        logger.warning("Board DB yuklenemedi: %s", exc)
        return {}


def format_port_entry(port: dict) -> str:
    """Format a serial port for display."""
    device = port.get("device", "?")
    desc = port.get("description", "")
    if desc:
        return f"{device} — {desc}"
    return device


def format_board_entry(name: str, info: dict) -> str:
    """Format a board for display."""
    mcu = info.get("mcu", "?")
    return f"{name} ({mcu})"


# --- GTK Panel ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    class MCUPanel:
        """KlipperScreen MCU management panel."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()

        def build_ui(self) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(15)
            box.set_margin_start(15)
            box.set_margin_end(15)

            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 10)

            # Scan button
            scan_btn = Gtk.Button(label="Portlari Tara")
            scan_btn.connect("clicked", self._on_scan)
            scan_btn.set_size_request(-1, 45)
            box.pack_start(scan_btn, False, False, 5)

            # Port list
            port_label = Gtk.Label()
            port_label.set_markup("<b>Bulunan Portlar:</b>")
            port_label.set_halign(Gtk.Align.START)
            box.pack_start(port_label, False, False, 5)

            scroll = Gtk.ScrolledWindow()
            scroll.set_min_content_height(120)
            self._port_listbox = Gtk.ListBox()
            scroll.add(self._port_listbox)
            box.pack_start(scroll, True, True, 5)

            # Board database
            board_label = Gtk.Label()
            board_label.set_markup("<b>Desteklenen Kartlar:</b>")
            board_label.set_halign(Gtk.Align.START)
            box.pack_start(board_label, False, False, 5)

            scroll2 = Gtk.ScrolledWindow()
            scroll2.set_min_content_height(120)
            self._board_listbox = Gtk.ListBox()
            scroll2.add(self._board_listbox)
            box.pack_start(scroll2, True, True, 5)

            # Status
            self._status_label = Gtk.Label(label="")
            box.pack_start(self._status_label, False, False, 5)

            # Load boards
            self._load_boards()

            return box

        def _on_scan(self, _btn):
            self._status_label.set_text("Taraniyor...")
            ports = scan_ports()
            for child in self._port_listbox.get_children():
                self._port_listbox.remove(child)
            for port in ports:
                row = Gtk.ListBoxRow()
                label = Gtk.Label(label=format_port_entry(port))
                label.set_halign(Gtk.Align.START)
                row.add(label)
                self._port_listbox.add(row)
            self._port_listbox.show_all()
            self._status_label.set_text(f"{len(ports)} port bulundu")

        def _load_boards(self):
            boards = get_board_list()
            for name, info in boards.items():
                row = Gtk.ListBoxRow()
                label = Gtk.Label(label=format_board_entry(name, info))
                label.set_halign(Gtk.Align.START)
                row.add(label)
                self._board_listbox.add(row)
            self._board_listbox.show_all()

except ImportError:
    pass

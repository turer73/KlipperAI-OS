# ks-panels/kos_logs.py
"""KlipperOS-AI — Log Viewer Panel for KlipperScreen.

View klippy, moonraker, crowsnest, and AI monitor logs with auto-scroll.
"""

import logging
from typing import Optional, List, Dict

from kos_system_api import KosSystemAPI, LOG_PATHS

logger = logging.getLogger("KOS-Logs")

PANEL_TITLE = "Log Goruntule"

LOG_SOURCES = list(LOG_PATHS.keys())


def get_panel_data(api: KosSystemAPI, source: str = "klippy", lines: int = 50) -> dict:
    """Get log content for panel display."""
    content = api.read_log_tail(source, lines=lines)
    return {
        "title": PANEL_TITLE,
        "source": source,
        "sources": LOG_SOURCES,
        "content": content,
        "line_count": len(content.splitlines()) if content else 0,
    }


def format_log_header(source: str, line_count: int) -> str:
    """Format log viewer header."""
    return f"{source} — {line_count} satir"


# --- GTK Panel ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib, Pango

    class LogViewerPanel:
        """KlipperScreen log viewer panel with source selector and auto-scroll."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()
            self._current_source = "klippy"

        def build_ui(self) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(10)
            box.set_margin_start(10)
            box.set_margin_end(10)

            # Title
            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 5)

            # Source selector row
            source_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            source_label = Gtk.Label(label="Kaynak:")
            self._source_combo = Gtk.ComboBoxText()
            for src in LOG_SOURCES:
                self._source_combo.append_text(src)
            self._source_combo.set_active(0)
            self._source_combo.connect("changed", self._on_source_changed)

            refresh_btn = Gtk.Button(label="Yenile")
            refresh_btn.connect("clicked", self._on_refresh)

            source_box.pack_start(source_label, False, False, 0)
            source_box.pack_start(self._source_combo, True, True, 0)
            source_box.pack_start(refresh_btn, False, False, 0)
            box.pack_start(source_box, False, False, 5)

            # Header
            self._header_label = Gtk.Label(label="")
            self._header_label.set_halign(Gtk.Align.START)
            box.pack_start(self._header_label, False, False, 3)

            # Log text view (scrollable)
            scroll = Gtk.ScrolledWindow()
            scroll.set_min_content_height(300)
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            self._text_view = Gtk.TextView()
            self._text_view.set_editable(False)
            self._text_view.set_cursor_visible(False)
            self._text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            # Monospace font for logs
            font_desc = Pango.FontDescription("monospace 9")
            self._text_view.override_font(font_desc)
            scroll.add(self._text_view)
            box.pack_start(scroll, True, True, 5)

            self._scroll = scroll

            # Load initial content
            self._load_log()

            return box

        def _on_source_changed(self, combo):
            self._current_source = combo.get_active_text()
            self._load_log()

        def _on_refresh(self, _btn):
            self._load_log()

        def _load_log(self):
            data = get_panel_data(self.api, self._current_source)
            buf = self._text_view.get_buffer()
            buf.set_text(data["content"] or "Log dosyasi bos veya okunamiyor")
            self._header_label.set_text(format_log_header(data["source"], data["line_count"]))
            # Auto-scroll to bottom
            GLib.idle_add(self._scroll_to_bottom)

        def _scroll_to_bottom(self):
            adj = self._scroll.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
            return False

except ImportError:
    pass

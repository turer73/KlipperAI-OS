# ks-panels/kos_terminal.py
"""KlipperOS-AI — VTE3 Terminal Panel for KlipperScreen.

Full terminal emulator with keyboard/mouse support.
Lazy-loaded: shell process only spawns when panel is opened.
Runs as 'klipper' user (not root).
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("KOS-Terminal")

PANEL_TITLE = "Terminal"
DEFAULT_SHELL = "/bin/bash"
DEFAULT_FONT_SIZE = 11
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 20


def get_panel_data() -> dict:
    """Get terminal panel metadata."""
    return {
        "title": PANEL_TITLE,
        "shell": DEFAULT_SHELL,
        "user": os.environ.get("USER", "klipper"),
        "font_size": DEFAULT_FONT_SIZE,
    }


# --- GTK + VTE Panel ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Vte", "2.91")
    from gi.repository import Gtk, Vte, GLib, Pango

    class TerminalPanel:
        """KlipperScreen VTE3 terminal panel with font controls."""

        def __init__(self):
            self._terminal: Optional[Vte.Terminal] = None
            self._font_size: int = DEFAULT_FONT_SIZE
            self._child_pid: Optional[int] = None

        def build_ui(self) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            box.set_margin_top(5)
            box.set_margin_start(5)
            box.set_margin_end(5)

            # Toolbar
            toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            toolbar.pack_start(title, False, False, 5)

            # Font size controls
            font_minus = Gtk.Button(label="A-")
            font_minus.connect("clicked", self._on_font_smaller)
            font_plus = Gtk.Button(label="A+")
            font_plus.connect("clicked", self._on_font_larger)
            toolbar.pack_end(font_plus, False, False, 2)
            toolbar.pack_end(font_minus, False, False, 2)

            box.pack_start(toolbar, False, False, 0)

            # VTE Terminal
            self._terminal = Vte.Terminal()
            self._terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
            self._terminal.set_scrollback_lines(1000)
            self._terminal.set_scroll_on_output(True)
            self._terminal.set_scroll_on_keystroke(True)
            self._update_font()

            # Spawn shell (lazy — only when panel is built)
            self._spawn_shell()

            # Scrolled window for terminal
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.add(self._terminal)
            box.pack_start(scroll, True, True, 0)

            return box

        def _spawn_shell(self):
            """Spawn shell process in terminal."""
            try:
                self._terminal.spawn_async(
                    Vte.PtyFlags.DEFAULT,
                    os.environ.get("HOME", "/home/klipper"),
                    [DEFAULT_SHELL],
                    None,
                    GLib.SpawnFlags.DEFAULT,
                    None,
                    None,
                    -1,
                    None,
                    self._on_spawn_complete,
                )
            except Exception as exc:
                logger.error("Shell baslatma hatasi: %s", exc)

        def _on_spawn_complete(self, terminal, pid, error):
            """Handle shell spawn completion."""
            if error:
                logger.error("Shell spawn hatasi: %s", error)
            else:
                self._child_pid = pid
                logger.info("Terminal shell baslatildi (PID: %s)", pid)

        def _update_font(self):
            """Update terminal font size."""
            font_desc = Pango.FontDescription(f"monospace {self._font_size}")
            self._terminal.set_font(font_desc)

        def _on_font_smaller(self, _btn):
            if self._font_size > MIN_FONT_SIZE:
                self._font_size -= 1
                self._update_font()

        def _on_font_larger(self, _btn):
            if self._font_size < MAX_FONT_SIZE:
                self._font_size += 1
                self._update_font()

        def stop(self):
            """Stop terminal — kill shell process, free memory."""
            if self._child_pid is not None:
                try:
                    import signal
                    os.kill(self._child_pid, signal.SIGTERM)
                    logger.info("Terminal shell durduruldu (PID: %s)", self._child_pid)
                except ProcessLookupError:
                    pass  # already dead
                self._child_pid = None

except ImportError:
    # VTE3 not available (Windows, headless)
    pass

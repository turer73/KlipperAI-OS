# ks-panels/kos_power.py
"""KlipperOS-AI — Power Management Panel for KlipperScreen."""

import logging
from typing import Optional

from panels.kos_system_api import KosSystemAPI

logger = logging.getLogger("KOS-Power")

PANEL_TITLE = "Guc Yonetimi"
PANEL_ACTIONS = {
    "shutdown": "Sistemi Kapat",
    "reboot": "Yeniden Baslat",
    "restart_klipper": "Klipper Yeniden Baslat",
    "restart_moonraker": "Moonraker Yeniden Baslat",
    "restart_firmware": "Firmware Restart",
}


def execute_action(api: KosSystemAPI, action: str) -> bool:
    """Execute a power action."""
    if action == "shutdown":
        return api.shutdown()
    elif action == "reboot":
        return api.reboot()
    elif action == "restart_klipper":
        return api.restart_service("klipper")
    elif action == "restart_moonraker":
        return api.restart_service("moonraker")
    elif action == "restart_firmware":
        return api.firmware_restart()
    return False


def get_panel_data(api: KosSystemAPI) -> dict:
    """Get data for the power panel display."""
    return {
        "title": PANEL_TITLE,
        "actions": PANEL_ACTIONS,
        "uptime": api.get_uptime(),
    }


# --- GTK Panel (used by KlipperScreen) ---
# NOTE: GTK imports are conditional — only when running inside KlipperScreen
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    class PowerPanel:
        """KlipperScreen power management panel."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()

        def build_ui(self) -> Gtk.Box:
            """Build the GTK panel UI."""
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.set_margin_top(20)
            box.set_margin_start(20)
            box.set_margin_end(20)

            # Title
            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 10)

            # Uptime
            uptime_label = Gtk.Label(label=f"Calisma Suresi: {self.api.get_uptime()}")
            box.pack_start(uptime_label, False, False, 5)

            # Action buttons
            for action_id, label in PANEL_ACTIONS.items():
                btn = Gtk.Button(label=label)
                btn.connect("clicked", self._on_action, action_id)
                btn.set_size_request(-1, 50)
                box.pack_start(btn, False, False, 5)

            return box

        def _on_action(self, _button, action_id: str) -> None:
            """Handle action button click."""
            result = execute_action(self.api, action_id)
            if result:
                logger.info("Power action basarili: %s", action_id)
            else:
                logger.error("Power action basarisiz: %s", action_id)

except ImportError:
    pass  # GTK not available (headless/test environment)


# --- KlipperScreen Panel Adapter ---
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    """KlipperScreen adapter for PowerPanel."""
    def __init__(self, screen, title):
        super().__init__(screen, title or PANEL_TITLE)
        try:
            self._inner = PowerPanel(api=KosSystemAPI())
            self.content.add(self._inner.build_ui())
        except Exception as exc:
            import logging
            logging.getLogger("KOS").error("Panel init error: %s", exc)
            err = Gtk.Label(label=f"Panel yukleme hatasi: {exc}")
            err.set_line_wrap(True)
            self.content.add(err)


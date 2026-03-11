# ks-panels/kos_services.py
"""KlipperOS-AI — Service Management Panel for KlipperScreen.

Shows all KOS services with status, provides start/stop/restart controls.
"""

import logging
from typing import Optional, List, Dict

from panels.kos_system_api import KosSystemAPI, KOS_SERVICES

logger = logging.getLogger("KOS-Services")

PANEL_TITLE = "Servis Yonetimi"


def get_panel_data(api: KosSystemAPI) -> dict:
    """Get all service statuses for panel display."""
    services = []
    for name in KOS_SERVICES:
        status = api.get_service_status(name)
        # get_service_status returns a str ("active"/"inactive"/"unknown")
        if isinstance(status, dict):
            active = status.get("active", False)
            status_text = status.get("status", "unknown")
        else:
            status_text = status if isinstance(status, str) else "unknown"
            active = status_text == "active"
        services.append({
            "name": name,
            "active": active,
            "status": status_text,
        })
    return {
        "title": PANEL_TITLE,
        "services": services,
    }


def format_service_status(service: dict) -> str:
    """Format a single service for display."""
    name = service.get("name", "?")
    active = service.get("active", False)
    icon = "\u25cf" if active else "\u25cb"
    status_text = "aktif" if active else "durdu"
    return f"{icon} {name}: {status_text}"


def service_action(api: KosSystemAPI, name: str, action: str) -> bool:
    """Execute a service action (start/stop/restart)."""
    if action == "restart":
        result = api.restart_service(name)
    elif action == "stop":
        result = api.stop_service(name)
    elif action == "start":
        result = api.start_service(name)
    else:
        logger.error("Bilinmeyen servis islemi: %s", action)
        return False
    if result:
        logger.info("Servis %s: %s basarili", action, name)
    else:
        logger.warning("Servis %s: %s basarisiz", action, name)
    return result


# --- GTK Panel ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    class ServicesPanel:
        """KlipperScreen service management panel."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()
            self._rows: Dict[str, Dict] = {}

        def build_ui(self) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(15)
            box.set_margin_start(15)
            box.set_margin_end(15)

            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 10)

            # Service rows
            data = get_panel_data(self.api)
            for svc in data["services"]:
                row = self._build_service_row(svc)
                box.pack_start(row, False, False, 3)

            # Refresh button
            refresh_btn = Gtk.Button(label="Yenile")
            refresh_btn.connect("clicked", self._on_refresh)
            box.pack_start(refresh_btn, False, False, 10)

            self._container = box
            return box

        def _build_service_row(self, svc: dict) -> Gtk.Box:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            name = svc["name"]

            status_label = Gtk.Label(label=format_service_status(svc))
            status_label.set_halign(Gtk.Align.START)
            status_label.set_hexpand(True)
            row.pack_start(status_label, True, True, 0)

            for action in ("restart", "stop", "start"):
                btn = Gtk.Button(label=action.capitalize())
                btn.connect("clicked", self._on_action, name, action)
                btn.set_size_request(70, 35)
                row.pack_start(btn, False, False, 2)

            self._rows[name] = {"label": status_label, "box": row}
            return row

        def _on_action(self, _btn, name: str, action: str):
            service_action(self.api, name, action)
            self._refresh_service(name)

        def _refresh_service(self, name: str):
            status = self.api.get_service_status(name)
            # get_service_status returns a str, not dict
            active = (status == "active") if isinstance(status, str) else status.get("active", False)
            svc = {"name": name, "active": active}
            if name in self._rows:
                self._rows[name]["label"].set_text(format_service_status(svc))

        def _on_refresh(self, _btn):
            for name in KOS_SERVICES:
                self._refresh_service(name)

except ImportError:
    pass


# --- KlipperScreen Panel Adapter ---
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    """KlipperScreen adapter for ServicesPanel."""
    def __init__(self, screen, title):
        super().__init__(screen, title or PANEL_TITLE)
        try:
            self._inner = ServicesPanel(api=KosSystemAPI())
            self.content.add(self._inner.build_ui())
        except Exception as exc:
            import logging
            logging.getLogger("KOS").error("Panel init error: %s", exc)
            err = Gtk.Label(label=f"Panel yukleme hatasi: {exc}")
            err.set_line_wrap(True)
            self.content.add(err)


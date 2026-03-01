# ks-panels/kos_tailscale.py
"""KlipperOS-AI — Tailscale VPN Panel for KlipperScreen."""

import logging
from typing import Optional, Dict

from kos_system_api import KosSystemAPI

logger = logging.getLogger("KOS-Tailscale")

PANEL_TITLE = "Tailscale VPN"


def get_panel_data(api: KosSystemAPI) -> dict:
    """Get Tailscale status for panel display."""
    status = api.get_tailscale_status()
    return {
        "title": PANEL_TITLE,
        "connected": status.get("connected", False),
        "ip": status.get("ip", ""),
        "hostname": status.get("hostname", ""),
        "status_text": _format_status(status),
    }


def _format_status(status: dict) -> str:
    """Format Tailscale status for display."""
    if status.get("connected"):
        ip = status.get("ip", "?")
        hostname = status.get("hostname", "?")
        return f"Bagli  |  IP: {ip}  |  Host: {hostname}"
    return "Bagli degil"


def connect(api: KosSystemAPI) -> bool:
    """Connect to Tailscale network."""
    result = api.tailscale_up()
    if result:
        logger.info("Tailscale baglantisi basarili")
    else:
        logger.warning("Tailscale baglantisi basarisiz")
    return result


def disconnect(api: KosSystemAPI) -> bool:
    """Disconnect from Tailscale network."""
    result = api.tailscale_down()
    if result:
        logger.info("Tailscale baglantisi kesildi")
    return result


# --- GTK Panel ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    class TailscalePanel:
        """KlipperScreen Tailscale VPN panel."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()

        def build_ui(self) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.set_margin_top(20)
            box.set_margin_start(20)
            box.set_margin_end(20)

            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 10)

            data = get_panel_data(self.api)
            self._status_label = Gtk.Label(label=data["status_text"])
            box.pack_start(self._status_label, False, False, 10)

            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            connect_btn = Gtk.Button(label="Baglan")
            connect_btn.connect("clicked", self._on_connect)
            connect_btn.set_size_request(-1, 50)
            disconnect_btn = Gtk.Button(label="Kes")
            disconnect_btn.connect("clicked", self._on_disconnect)
            disconnect_btn.set_size_request(-1, 50)
            btn_box.pack_start(connect_btn, True, True, 0)
            btn_box.pack_start(disconnect_btn, True, True, 0)
            box.pack_start(btn_box, False, False, 10)

            refresh_btn = Gtk.Button(label="Durumu Yenile")
            refresh_btn.connect("clicked", self._on_refresh)
            box.pack_start(refresh_btn, False, False, 5)

            return box

        def _on_connect(self, _btn):
            connect(self.api)
            self._refresh_status()

        def _on_disconnect(self, _btn):
            disconnect(self.api)
            self._refresh_status()

        def _on_refresh(self, _btn):
            self._refresh_status()

        def _refresh_status(self):
            data = get_panel_data(self.api)
            self._status_label.set_text(data["status_text"])

except ImportError:
    pass

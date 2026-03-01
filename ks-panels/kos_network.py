# ks-panels/kos_network.py
"""KlipperOS-AI — Network Management Panel for KlipperScreen.

WiFi SSID scanning, connection with password entry, IP display.
Supports physical keyboard, on-screen keyboard, and touchscreen.
"""

import logging
from typing import Optional, List, Dict

from kos_system_api import KosSystemAPI

logger = logging.getLogger("KOS-Network")

PANEL_TITLE = "Ag Ayarlari"


def get_panel_data(api: KosSystemAPI) -> dict:
    """Get network information for panel display."""
    return {
        "title": PANEL_TITLE,
        "ip_info": api.get_current_ip(),
        "wifi_networks": api.get_wifi_networks(),
    }


def connect_to_wifi(api: KosSystemAPI, ssid: str, password: str) -> bool:
    """Attempt WiFi connection."""
    result = api.connect_wifi(ssid, password)
    if result:
        logger.info("WiFi baglanti basarili: %s", ssid)
    else:
        logger.warning("WiFi baglanti basarisiz: %s", ssid)
    return result


def disconnect_wifi(api: KosSystemAPI) -> bool:
    """Disconnect from current WiFi."""
    result = api.disconnect_wifi()
    if result:
        logger.info("WiFi baglanti kesildi")
    return result


def format_network_info(ip_info: dict) -> str:
    """Format current network info for display."""
    ip = ip_info.get("ip", "Baglanti yok")
    iface = ip_info.get("interface", "")
    if iface:
        return f"IP: {ip} ({iface})"
    return f"IP: {ip}"


def format_wifi_list(networks: List[dict]) -> List[str]:
    """Format WiFi networks for display."""
    lines = []
    for net in networks:
        ssid = net.get("ssid", "?")
        signal = net.get("signal", 0)
        security = net.get("security", "")
        lock = "\U0001f512" if security and security != "OPEN" else "  "
        # Signal strength indicator
        if signal >= 70:
            bars = "\u25b0\u25b0\u25b0\u25b0"
        elif signal >= 50:
            bars = "\u25b0\u25b0\u25b0\u25b1"
        elif signal >= 30:
            bars = "\u25b0\u25b0\u25b1\u25b1"
        else:
            bars = "\u25b0\u25b1\u25b1\u25b1"
        lines.append(f"{lock} {ssid}  {bars} {signal}%")
    return lines


# --- GTK Panel (used by KlipperScreen) ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib

    class NetworkPanel:
        """KlipperScreen network management panel."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()
            self._networks: List[dict] = []
            self._selected_ssid: Optional[str] = None

        def build_ui(self) -> Gtk.Box:
            """Build the GTK panel UI."""
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(15)
            box.set_margin_start(15)
            box.set_margin_end(15)

            # Title
            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 10)

            # Current IP
            ip_data = self.api.get_current_ip()
            self._ip_label = Gtk.Label(label=format_network_info(ip_data))
            box.pack_start(self._ip_label, False, False, 5)

            # Scan button
            scan_btn = Gtk.Button(label="WiFi Tara")
            scan_btn.connect("clicked", self._on_scan)
            box.pack_start(scan_btn, False, False, 5)

            # WiFi list (scrollable)
            scroll = Gtk.ScrolledWindow()
            scroll.set_min_content_height(150)
            self._wifi_listbox = Gtk.ListBox()
            self._wifi_listbox.connect("row-selected", self._on_network_selected)
            scroll.add(self._wifi_listbox)
            box.pack_start(scroll, True, True, 5)

            # Password entry
            pw_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            pw_label = Gtk.Label(label="Sifre:")
            self._pw_entry = Gtk.Entry()
            self._pw_entry.set_visibility(False)
            self._pw_entry.set_placeholder_text("WiFi sifresi")
            pw_toggle = Gtk.ToggleButton(label="\U0001f441")
            pw_toggle.connect("toggled", self._on_toggle_pw)
            pw_box.pack_start(pw_label, False, False, 0)
            pw_box.pack_start(self._pw_entry, True, True, 0)
            pw_box.pack_start(pw_toggle, False, False, 0)
            box.pack_start(pw_box, False, False, 5)

            # Connect / Disconnect buttons
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            connect_btn = Gtk.Button(label="Baglan")
            connect_btn.connect("clicked", self._on_connect)
            disconnect_btn = Gtk.Button(label="Kes")
            disconnect_btn.connect("clicked", self._on_disconnect)
            btn_box.pack_start(connect_btn, True, True, 0)
            btn_box.pack_start(disconnect_btn, True, True, 0)
            box.pack_start(btn_box, False, False, 5)

            # Status
            self._status_label = Gtk.Label(label="")
            box.pack_start(self._status_label, False, False, 5)

            return box

        def _on_scan(self, _button) -> None:
            """Scan for WiFi networks."""
            self._status_label.set_text("Taraniyor...")
            self._networks = self.api.get_wifi_networks()
            # Clear old rows
            for child in self._wifi_listbox.get_children():
                self._wifi_listbox.remove(child)
            # Add new rows
            lines = format_wifi_list(self._networks)
            for line in lines:
                row = Gtk.ListBoxRow()
                label = Gtk.Label(label=line)
                label.set_halign(Gtk.Align.START)
                row.add(label)
                self._wifi_listbox.add(row)
            self._wifi_listbox.show_all()
            self._status_label.set_text(f"{len(self._networks)} ag bulundu")

        def _on_network_selected(self, _listbox, row) -> None:
            """Handle network selection."""
            if row is not None:
                idx = row.get_index()
                if 0 <= idx < len(self._networks):
                    self._selected_ssid = self._networks[idx].get("ssid")

        def _on_connect(self, _button) -> None:
            """Connect to selected WiFi."""
            if not self._selected_ssid:
                self._status_label.set_text("Bir ag secin")
                return
            password = self._pw_entry.get_text()
            self._status_label.set_text(f"Baglaniyor: {self._selected_ssid}...")
            success = connect_to_wifi(self.api, self._selected_ssid, password)
            if success:
                self._status_label.set_text(f"Baglandi: {self._selected_ssid}")
                # Update IP
                ip_data = self.api.get_current_ip()
                self._ip_label.set_text(format_network_info(ip_data))
            else:
                self._status_label.set_text("Baglanti basarisiz")

        def _on_disconnect(self, _button) -> None:
            """Disconnect from WiFi."""
            disconnect_wifi(self.api)
            self._status_label.set_text("WiFi baglantisi kesildi")
            ip_data = self.api.get_current_ip()
            self._ip_label.set_text(format_network_info(ip_data))

        def _on_toggle_pw(self, toggle) -> None:
            """Toggle password visibility."""
            self._pw_entry.set_visibility(toggle.get_active())

except ImportError:
    pass  # GTK not available

# ks-panels/kos_ai_settings.py
"""KlipperOS-AI — AI Settings Panel for KlipperScreen.

Toggle AI Monitor on/off, adjust check interval and thresholds.
"""

import logging
import json
from typing import Optional, Dict

from kos_system_api import KosSystemAPI

logger = logging.getLogger("KOS-AISettings")

PANEL_TITLE = "AI Ayarlari"

# Default AI settings
DEFAULT_SETTINGS = {
    "enabled": True,
    "check_interval_seconds": 10,
    "flow_guard_enabled": True,
    "flow_deviation_threshold": 15.0,
    "temp_deviation_threshold": 10.0,
    "layer_check_enabled": True,
}

SETTINGS_PATH = "kos_ai_settings.json"


def get_panel_data(api: KosSystemAPI) -> dict:
    """Get current AI settings."""
    settings = load_settings(api)
    return {
        "title": PANEL_TITLE,
        "settings": settings,
    }


def load_settings(api: KosSystemAPI) -> dict:
    """Load AI settings from Moonraker config store."""
    try:
        raw = api.read_config(SETTINGS_PATH)
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("AI ayarlari okunamadi: %s", exc)
    return DEFAULT_SETTINGS.copy()


def save_settings(api: KosSystemAPI, settings: dict) -> bool:
    """Save AI settings to Moonraker config store."""
    try:
        content = json.dumps(settings, indent=2)
        result = api.write_config(SETTINGS_PATH, content)
        if result:
            logger.info("AI ayarlari kaydedildi")
        return result
    except Exception as exc:
        logger.error("AI ayarlari kaydedilemedi: %s", exc)
        return False


def update_setting(api: KosSystemAPI, key: str, value) -> bool:
    """Update a single AI setting."""
    settings = load_settings(api)
    if key not in DEFAULT_SETTINGS:
        logger.warning("Bilinmeyen AI ayari: %s", key)
        return False
    settings[key] = value
    return save_settings(api, settings)


def format_settings_display(settings: dict) -> str:
    """Format settings for text display."""
    lines = [
        f"AI Monitor: {'Acik' if settings.get('enabled') else 'Kapali'}",
        f"Kontrol Araligi: {settings.get('check_interval_seconds', 10)}s",
        f"FlowGuard: {'Acik' if settings.get('flow_guard_enabled') else 'Kapali'}",
        f"Akis Sapma Esigi: {settings.get('flow_deviation_threshold', 15)}%",
        f"Sicaklik Sapma Esigi: {settings.get('temp_deviation_threshold', 10)}°C",
        f"Katman Kontrol: {'Acik' if settings.get('layer_check_enabled') else 'Kapali'}",
    ]
    return "\n".join(lines)


# --- GTK Panel ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    class AISettingsPanel:
        """KlipperScreen AI settings panel."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()
            self._settings: dict = {}

        def build_ui(self) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(15)
            box.set_margin_start(15)
            box.set_margin_end(15)

            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 10)

            self._settings = load_settings(self.api)

            # AI Monitor toggle
            ai_row = self._build_toggle_row("AI Monitor", "enabled")
            box.pack_start(ai_row, False, False, 3)

            # FlowGuard toggle
            fg_row = self._build_toggle_row("FlowGuard", "flow_guard_enabled")
            box.pack_start(fg_row, False, False, 3)

            # Layer check toggle
            lc_row = self._build_toggle_row("Katman Kontrol", "layer_check_enabled")
            box.pack_start(lc_row, False, False, 3)

            # Check interval slider
            interval_row = self._build_slider_row("Kontrol Araligi (s)", "check_interval_seconds", 5, 30, 1)
            box.pack_start(interval_row, False, False, 3)

            # Flow deviation threshold slider
            flow_row = self._build_slider_row("Akis Sapma Esigi (%)", "flow_deviation_threshold", 5, 50, 1)
            box.pack_start(flow_row, False, False, 3)

            # Temp deviation threshold slider
            temp_row = self._build_slider_row("Sicaklik Sapma (°C)", "temp_deviation_threshold", 3, 30, 1)
            box.pack_start(temp_row, False, False, 3)

            # Save button
            save_btn = Gtk.Button(label="Kaydet")
            save_btn.connect("clicked", self._on_save)
            save_btn.set_size_request(-1, 45)
            box.pack_start(save_btn, False, False, 10)

            # Status
            self._status_label = Gtk.Label(label="")
            box.pack_start(self._status_label, False, False, 5)

            return box

        def _build_toggle_row(self, label_text: str, key: str) -> Gtk.Box:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            label = Gtk.Label(label=label_text)
            label.set_halign(Gtk.Align.START)
            label.set_hexpand(True)
            switch = Gtk.Switch()
            switch.set_active(self._settings.get(key, False))
            switch.connect("notify::active", self._on_toggle, key)
            row.pack_start(label, True, True, 0)
            row.pack_start(switch, False, False, 0)
            return row

        def _build_slider_row(self, label_text: str, key: str, min_val: float, max_val: float, step: float) -> Gtk.Box:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            label = Gtk.Label(label=label_text)
            label.set_halign(Gtk.Align.START)
            adj = Gtk.Adjustment(value=self._settings.get(key, min_val), lower=min_val, upper=max_val, step_increment=step)
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
            scale.set_digits(0 if step >= 1 else 1)
            scale.set_hexpand(True)
            scale.connect("value-changed", self._on_slider, key)
            value_label = Gtk.Label(label=str(int(self._settings.get(key, min_val))))
            row.pack_start(label, False, False, 0)
            row.pack_start(scale, True, True, 0)
            row.pack_start(value_label, False, False, 0)
            return row

        def _on_toggle(self, switch, _pspec, key):
            self._settings[key] = switch.get_active()

        def _on_slider(self, scale, key):
            self._settings[key] = scale.get_value()

        def _on_save(self, _btn):
            success = save_settings(self.api, self._settings)
            if success:
                self._status_label.set_text("Ayarlar kaydedildi")
            else:
                self._status_label.set_text("Kaydetme basarisiz")

except ImportError:
    pass

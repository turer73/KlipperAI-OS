# ks-panels/kos_sysinfo.py
"""KlipperOS-AI — System Information Panel for KlipperScreen.

Displays CPU, RAM, Disk info plus MCU temperatures, voltages, and CAN board status.
Auto-refreshes every 2 seconds when GTK panel is active.
"""

import logging
from typing import Optional, Dict, List

from kos_system_api import KosSystemAPI

logger = logging.getLogger("KOS-SysInfo")

PANEL_TITLE = "Sistem Bilgisi"


def get_panel_data(api: KosSystemAPI) -> dict:
    """Get all system information for panel display."""
    data = {
        "title": PANEL_TITLE,
        "cpu": api.get_cpu_info(),
        "memory": api.get_memory_info(),
        "disk": api.get_disk_info(),
        "uptime": api.get_uptime(),
    }
    # MCU info may fail if Moonraker is not running
    try:
        data["mcu"] = api.get_mcu_info()
    except Exception:
        data["mcu"] = {}
    return data


def format_cpu_line(cpu: dict) -> str:
    """Format CPU info for display."""
    usage = cpu.get("usage_percent", 0)
    temp = cpu.get("temperature")
    freq = cpu.get("frequency_mhz", 0)
    line = f"CPU: {usage:.0f}%  |  {freq:.0f} MHz"
    if temp is not None:
        line += f"  |  {temp:.1f}°C"
    return line


def format_memory_line(mem: dict) -> str:
    """Format memory info for display."""
    used = mem.get("used_mb", 0)
    total = mem.get("total_mb", 0)
    pct = mem.get("percent", 0)
    zram = mem.get("zram_total_mb", 0)
    line = f"RAM: {used:.0f}/{total:.0f} MB ({pct:.0f}%)"
    if zram > 0:
        line += f"  |  zram: {zram:.0f} MB"
    return line


def format_disk_line(disk: dict) -> str:
    """Format disk info for display."""
    used = disk.get("used_gb", 0)
    total = disk.get("total_gb", 0)
    pct = disk.get("percent", 0)
    return f"Disk: {used:.1f}/{total:.1f} GB ({pct:.0f}%)"


def format_mcu_lines(mcu: dict) -> List[str]:
    """Format MCU info as list of display lines."""
    lines = []
    if not mcu:
        lines.append("MCU: Bilgi alinamiyor")
        return lines
    for name, info in mcu.items():
        temp = info.get("temperature")
        voltage = info.get("voltage")
        line = f"MCU ({name}):"
        if temp is not None:
            line += f"  {temp:.1f}°C"
        if voltage is not None:
            line += f"  |  {voltage:.2f}V"
        lines.append(line)
    return lines


# --- GTK Panel (used by KlipperScreen) ---
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib

    class SysInfoPanel:
        """KlipperScreen system information panel with auto-refresh."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()
            self._timer_id: Optional[int] = None
            self._labels: Dict[str, Gtk.Label] = {}

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

            # Create info labels
            for key in ("cpu", "memory", "disk", "uptime", "mcu"):
                label = Gtk.Label()
                label.set_halign(Gtk.Align.START)
                label.set_line_wrap(True)
                self._labels[key] = label
                box.pack_start(label, False, False, 3)

            # Initial data load
            self._refresh()

            # Auto-refresh every 2 seconds
            self._timer_id = GLib.timeout_add_seconds(2, self._refresh)

            return box

        def _refresh(self) -> bool:
            """Refresh all system info labels. Returns True to keep timer running."""
            try:
                data = get_panel_data(self.api)
                self._labels["cpu"].set_text(format_cpu_line(data["cpu"]))
                self._labels["memory"].set_text(format_memory_line(data["memory"]))
                self._labels["disk"].set_text(format_disk_line(data["disk"]))
                self._labels["uptime"].set_text(f"Uptime: {data['uptime']}")
                mcu_lines = format_mcu_lines(data.get("mcu", {}))
                self._labels["mcu"].set_text("\n".join(mcu_lines))
            except Exception as exc:
                logger.warning("SysInfo refresh hatasi: %s", exc)
            return True  # keep timer

        def stop(self) -> None:
            """Stop auto-refresh timer."""
            if self._timer_id is not None:
                GLib.source_remove(self._timer_id)
                self._timer_id = None

except ImportError:
    pass  # GTK not available

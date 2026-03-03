"""Adim 4: Profil secimi."""
from __future__ import annotations

from ..tui import TUI
from ..hw_detect import HardwareInfo
from ..profiles import PROFILES


class ProfileStep:
    def __init__(self, tui: TUI, hw_info: HardwareInfo):
        self.tui = tui
        self.hw_info = hw_info

    def run(self) -> str:
        if self.hw_info.is_force_light:
            self.tui.msgbox("Profil Secimi", f"""
  RAM: {self.hw_info.ram_total_mb} MB (< 1.5 GB)

  Yetersiz RAM nedeniyle sadece LIGHT profil
  kurulabilir.

  LIGHT: Klipper + Moonraker + Mainsail""")
            return "LIGHT"

        default_map = {"LIGHT": "1", "STANDARD": "2", "FULL": "3"}
        default = default_map.get(self.hw_info.recommended_profile, "2")

        items = [
            ("1", f"LIGHT    — {PROFILES['LIGHT'].description}"),
            ("2", f"STANDARD — {PROFILES['STANDARD'].description}"),
            ("3", f"FULL     — {PROFILES['FULL'].description}"),
        ]

        choice = self.tui.menu(
            "Kurulum Profili Secin",
            items,
            text=f"Donanim: {self.hw_info.ram_total_mb}MB RAM, {self.hw_info.cpu_cores} cekirdek\n"
                 f"Onerilen: {self.hw_info.recommended_profile}",
            default=default,
        )

        profile_map = {"1": "LIGHT", "2": "STANDARD", "3": "FULL"}
        return profile_map.get(choice, "STANDARD")

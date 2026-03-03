"""Adim 1: Hosgeldin ekrani."""
from __future__ import annotations

from ..tui import TUI

ASCII_BANNER = r"""
  _  _  _ _                      _    ___
 | |/ /| (_)_ __  _ __   ___ _ _/_\  |_ _|
 | ' / | | | '_ \| '_ \ / _ \ '_/ _ \ | |
 | . \ | | | |_) | |_) |  __/ |/ ___ \| |
 |_|\_\|_|_| .__/| .__/ \___|_/_/   \_\___|
            |_|   |_|     OS v3.0

  AI-Powered 3D Printer Operating System
"""


class WelcomeStep:
    def __init__(self, tui: TUI):
        self.tui = tui

    def run(self) -> bool:
        self.tui.msgbox("KlipperOS-AI'ye Hosgeldiniz!", f"""{ASCII_BANNER}
  Bu sihirbaz sisteminizi yapilandiracak:
  1. Donanim algilama
  2. Ag baglantisi
  3. Kurulum profili secimi
  4. Kullanici ayarlari
  5. Yazilim kurulumu

  Devam etmek icin OK'a basin.""")
        return True

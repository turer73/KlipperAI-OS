"""Adim 8: Tamamlandi ekrani."""
from __future__ import annotations

from ..tui import TUI
from ..utils.runner import run_cmd


class CompleteStep:
    def __init__(self, tui: TUI, profile_name: str):
        self.tui = tui
        self.profile_name = profile_name

    def run(self) -> bool:
        ok, output = run_cmd(["hostname", "-I"])
        ip_addr = output.strip().split()[0] if ok and output.strip() else "bilinmiyor"

        self.tui.msgbox("Kurulum Tamamlandi!", f"""
  KlipperOS-AI basariyla kuruldu!

  Profil:     {self.profile_name}
  IP Adresi:  {ip_addr}
  Web UI:     http://klipperos.local
  SSH:        ssh klipper@{ip_addr}

  Sonraki adimlar:
  1. printer.cfg'yi yaziciya gore duzenleyin
  2. MCU firmware flash: kos_mcu flash
  3. Web arayuzunden yaziciyi test edin

  Sistem simdi yeniden baslatilacak.""")

        return True

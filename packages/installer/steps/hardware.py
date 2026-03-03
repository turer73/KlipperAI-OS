"""Adim 2: Donanim tespiti."""
from __future__ import annotations

from ..tui import TUI
from ..hw_detect import HardwareInfo


class HardwareStep:
    def __init__(self, tui: TUI):
        self.tui = tui

    def run(self) -> HardwareInfo:
        try:
            hw = HardwareInfo.detect()
        except Exception:
            hw = HardwareInfo(
                cpu_model="Unknown", cpu_cores=1, cpu_freq_mhz=0,
                ram_total_mb=2048, disk_total_mb=0,
                has_wifi=False, has_ethernet=True,
                board_type="x86", recommended_profile="STANDARD",
            )

        wifi_str = "Evet" if hw.has_wifi else "Hayir"
        eth_str = "Evet" if hw.has_ethernet else "Hayir"

        self.tui.msgbox("Donanim Algilama Sonuclari", f"""
  CPU:       {hw.cpu_model}
  Cekirdek:  {hw.cpu_cores}
  RAM:       {hw.ram_total_mb} MB
  Disk:      {hw.disk_total_mb} MB
  WiFi:      {wifi_str}
  Ethernet:  {eth_str}

  Onerilen Profil: {hw.recommended_profile}""")

        return hw

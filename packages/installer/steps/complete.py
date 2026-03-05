"""Adim 10: Tamamlandi ekrani + disk temizligi."""
from __future__ import annotations

from ..tui import TUI
from ..utils.runner import run_cmd
from ..utils.target import get_target, set_target
from ..utils.logger import get_logger

logger = get_logger()


class CompleteStep:
    def __init__(self, tui: TUI, profile_name: str):
        self.tui = tui
        self.profile_name = profile_name

    def run(self) -> bool:
        ok, output = run_cmd(["hostname", "-I"])
        ip_addr = output.strip().split()[0] if ok and output.strip() else "bilinmiyor"

        target = get_target()
        install_type = "Disk kurulum" if target else "Live kurulum"

        self.tui.msgbox("Kurulum Tamamlandi!", f"""
  KlipperOS-AI basariyla kuruldu!

  Tip:        {install_type}
  Profil:     {self.profile_name}
  IP Adresi:  {ip_addr}
  Web UI:     http://klipperos.local
  SSH:        ssh klipper@{ip_addr}

  Sonraki adimlar:
  1. printer.cfg'yi yaziciya gore duzenleyin
  2. MCU firmware flash: kos_mcu flash
  3. Web arayuzunden yaziciyi test edin

  Sistem simdi yeniden baslatilacak.""")

        # Disk kurulumda mount noktalarini temizle
        if target:
            self._unmount_all(target)

        return True

    @staticmethod
    def _unmount_all(target: str) -> None:
        """Bind mount ve disk bolumlerini cikar."""
        logger.info("Mount noktalari cikariliyor: %s", target)
        for m in ["/dev/pts", "/dev", "/proc", "/sys", "/run", "/boot/efi"]:
            full = f"{target}{m}"
            run_cmd(["umount", "-l", full])
        run_cmd(["umount", "-l", target])
        set_target(None)
        logger.info("Tum mount noktalari basariyla cikarildi.")

"""Adim 5: Kullanici ayarlari."""
from __future__ import annotations

from ..tui import TUI
from ..utils.runner import run_cmd
from ..utils.logger import get_logger

logger = get_logger()


class UserSetupStep:
    def __init__(self, tui: TUI):
        self.tui = tui

    def run(self) -> bool:
        new_hostname = self.tui.inputbox("Cihaz adi (hostname):", title="Hostname", default="klipperos")
        if new_hostname and new_hostname != "klipperos":
            run_cmd(["hostnamectl", "set-hostname", new_hostname])
            logger.info("Hostname: %s", new_hostname)

        new_pass = self.tui.passwordbox(
            "'klipper' kullanicisi icin yeni sifre\n(bos birakirsaniz varsayilan kalir):",
            title="Kullanici Sifresi",
        )
        if new_pass:
            run_cmd(["chpasswd"], timeout=10)
            logger.info("klipper sifresi degistirildi")

        return True

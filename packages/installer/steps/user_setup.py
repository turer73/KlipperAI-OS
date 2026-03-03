"""Adim 5: Kullanici ayarlari."""
from __future__ import annotations

import subprocess

from ..tui import TUI
from ..utils.runner import run_cmd
from ..utils.logger import get_logger

logger = get_logger()


class UserSetupStep:
    def __init__(self, tui: TUI, dry_run: bool = False):
        self.tui = tui
        self.dry_run = dry_run

    def _set_password(self, password: str) -> bool:
        """klipper kullanicisinin sifresini degistir."""
        if self.dry_run:
            return True
        try:
            proc = subprocess.run(
                ["chpasswd"],
                input=f"klipper:{password}\n",
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error("Sifre degistirme hatasi: %s", e)
            return False

    def _set_hostname(self, hostname: str) -> bool:
        """Hostname degistir."""
        if self.dry_run:
            return True
        try:
            with open("/etc/hostname", "w") as f:
                f.write(hostname + "\n")
            run_cmd(["sed", "-i", f"s/klipperos/{hostname}/g", "/etc/hosts"])
            run_cmd(["hostnamectl", "set-hostname", hostname])
            return True
        except OSError as e:
            logger.error("Hostname degistirme hatasi: %s", e)
            return False

    def run(self) -> bool:
        new_hostname = self.tui.inputbox(
            "Cihaz adi (hostname):",
            title="Hostname",
            default="klipperos",
        )
        if new_hostname and new_hostname != "klipperos":
            self._set_hostname(new_hostname)
            logger.info("Hostname: %s", new_hostname)

        new_pass = self.tui.passwordbox(
            "'klipper' kullanicisi icin yeni sifre\n(bos birakirsaniz varsayilan kalir):",
            title="Kullanici Sifresi",
        )
        if new_pass:
            if self._set_password(new_pass):
                logger.info("klipper sifresi degistirildi")
            else:
                logger.error("klipper sifresi degistirilemedi")

        return True

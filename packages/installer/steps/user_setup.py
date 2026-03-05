"""Adim 5: Kullanici ayarlari."""
from __future__ import annotations

import subprocess

from ..tui import TUI
from ..utils.runner import run_cmd
from ..utils.target import target_path, get_target
from ..utils.logger import get_logger

logger = get_logger()


class UserSetupStep:
    def __init__(self, tui: TUI, dry_run: bool = False):
        self.tui = tui
        self.dry_run = dry_run

    def _set_password(self, password: str) -> bool:
        """klipper kullanicisinin sifresini degistir.

        Disk kurulumda chpasswd chroot icinde calisir (run_cmd otomatik).
        """
        if self.dry_run:
            return True
        # chpasswd stdin'den okur — run_cmd stdin desteklemiyor,
        # dogrudan subprocess kullanalim (chroot destekli)
        target = get_target()
        cmd = ["chpasswd"]
        if target:
            cmd = ["chroot", target, "chpasswd"]
        try:
            proc = subprocess.run(
                cmd,
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
        """Hostname degistir.

        Disk kurulumda /etc/hostname ve /etc/hosts hedef diske yazilir.
        hostnamectl atlanir (chroot icinde systemd yok).
        """
        if self.dry_run:
            return True
        try:
            from pathlib import Path
            hostname_file = target_path("/etc/hostname")
            Path(hostname_file).parent.mkdir(parents=True, exist_ok=True)
            with open(hostname_file, "w") as f:
                f.write(hostname + "\n")
            # sed chroot icinde calisir (run_cmd otomatik)
            run_cmd(["sed", "-i", f"s/klipperos/{hostname}/g", "/etc/hosts"])
            # hostnamectl sadece live modda — chroot'ta systemd yok
            if get_target() is None:
                run_cmd(["hostnamectl", "set-hostname", hostname])
            return True
        except OSError as e:
            logger.error("Hostname degistirme hatasi: %s", e)
            return False

    def run(self) -> bool:
        new_hostname = self.tui.inputbox(
            "Cihaz adi (hostname):\n\n"
            "Ag uzerinde cihazinizin gorunecegi isim.\n"
            "Ornek: klipperos, yazici1, ender3",
            title="Cihaz Adi",
            default="klipperos",
        )
        if new_hostname and new_hostname != "klipperos":
            self._set_hostname(new_hostname)
            logger.info("Hostname: %s", new_hostname)

        new_pass = self.tui.password_input(
            "'klipper' kullanicisi icin yeni sifre:\n\n"
            "SSH ve web erisimi icin kullanilir.\n"
            "(bos birakirsaniz varsayilan kalir)",
            title="Kullanici Sifresi",
        )
        if new_pass:
            if self._set_password(new_pass):
                logger.info("klipper sifresi degistirildi")
            else:
                logger.error("klipper sifresi degistirilemedi")

        return True

"""Adim 6: Paket ve bilesen kurulumu."""
from __future__ import annotations

import time

from ..tui import TUI
from ..profiles import PROFILES
from ..utils.runner import run_cmd
from ..utils.sentinel import Sentinel
from ..utils.target import target_path
from ..utils.logger import get_logger
from ..installers.klipper import KlipperInstaller
from ..installers.moonraker import MoonrakerInstaller
from ..installers.mainsail import MainsailInstaller
from ..installers.klipperscreen import KlipperScreenInstaller
from ..installers.crowsnest import CrowsnestInstaller
from ..installers.ai_monitor import AIMonitorInstaller
from ..installers.multi_printer import MultiPrinterInstaller
from ..installers.timelapse import TimelapseInstaller

logger = get_logger()

COMPONENT_MAP: dict[str, type] = {
    "klipper": KlipperInstaller,
    "moonraker": MoonrakerInstaller,
    "mainsail": MainsailInstaller,
    "klipperscreen": KlipperScreenInstaller,
    "crowsnest": CrowsnestInstaller,
    "ai_monitor": AIMonitorInstaller,
    "multi_printer": MultiPrinterInstaller,
    "timelapse": TimelapseInstaller,
}


class InstallStep:
    def __init__(self, tui: TUI, profile_name: str, sentinel: Sentinel | None = None):
        self.tui = tui
        self.profile_name = profile_name
        self.sentinel = sentinel or Sentinel()
        self.profile = PROFILES[profile_name]

    def run(self) -> bool:
        self.tui.msgbox("Kurulum Basliyor", f"""
  Profil: {self.profile_name}

  Simdi yazilim kuruluyor. Bu islem internet
  hiziniza bagli olarak 10-30 dakika surebilir.

  Ilerleme asagida gorunecek.
  Lutfen bekleyin ve sistemi kapatmayin.""")

        log_path = "/var/log/kos-install-output.log"

        # APT update
        logger.info("APT paket listesi guncelleniyor...")
        self.tui.progress(
            "Kurulum",
            "Paket listesi guncelleniyor...\napt-get update",
            3,
        )
        ok, output = run_cmd(["apt-get", "update", "-qq"], timeout=120)
        self._append_log(log_path, "apt-get update", output)

        # APT install
        packages = self.profile.apt_packages
        self.tui.progress(
            "Kurulum",
            f"APT paketleri indiriliyor...\n"
            f"{len(packages)} paket kurulacak\n\n"
            f"Bu islem birkac dakika surebilir.",
            8,
        )
        ok, output = run_cmd(
            ["apt-get", "install", "-y", "--no-install-recommends"] + packages,
            timeout=600,
        )
        self._append_log(log_path, "apt-get install", output)
        if not ok:
            logger.error("APT paket kurulumu basarisiz")

        # Bilesenleri kur
        total = len(self.profile.components)
        for i, comp_name in enumerate(self.profile.components):
            percent = int(20 + (i / total) * 75)
            self.tui.progress(
                "Kurulum",
                f"Kuruluyor: {comp_name}\n"
                f"({i + 1}/{total} bilesen)\n\n"
                f"Profil: {self.profile_name}",
                percent,
            )

            installer_cls = COMPONENT_MAP.get(comp_name)
            if installer_cls:
                installer = installer_cls(sentinel=self.sentinel)
                installer.install()
            else:
                logger.warning("Installer bulunamadi: %s — atlaniyor.", comp_name)

        self.tui.progress("Kurulum", "Tum bilesenler basariyla kuruldu!", 100)
        time.sleep(2)
        return True

    @staticmethod
    def _append_log(path: str, label: str, output: str) -> None:
        """Komut ciktisini log dosyasina ekle."""
        try:
            real = target_path(path)
            from pathlib import Path
            Path(real).parent.mkdir(parents=True, exist_ok=True)
            with open(real, "a") as f:
                f.write(f"\n=== {label} ===\n{output}\n")
        except OSError:
            pass

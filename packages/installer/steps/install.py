"""Adim 6: Paket ve bilesen kurulumu."""
from __future__ import annotations

from ..tui import TUI
from ..profiles import PROFILES
from ..utils.runner import run_cmd
from ..utils.sentinel import Sentinel
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

  Lutfen bekleyin ve sistemi kapatmayin.""")

        logger.info("APT paketleri kuruluyor...")
        self.tui.gauge("APT paketleri indiriliyor...", 5)
        run_cmd(["apt-get", "update", "-qq"], timeout=120)

        packages = self.profile.apt_packages
        ok, _ = run_cmd(
            ["apt-get", "install", "-y", "--no-install-recommends"] + packages,
            timeout=600,
        )
        if not ok:
            logger.error("APT paket kurulumu basarisiz")

        total = len(self.profile.components)
        for i, comp_name in enumerate(self.profile.components):
            percent = int(20 + (i / total) * 75)
            self.tui.gauge(f"Kuruluyor: {comp_name}...", percent)

            installer_cls = COMPONENT_MAP.get(comp_name)
            if installer_cls:
                installer = installer_cls(sentinel=self.sentinel)
                installer.install()
            else:
                logger.warning("Installer bulunamadi: %s — atlaniyor.", comp_name)

        self.tui.gauge("Kurulum tamamlandi!", 100)
        return True

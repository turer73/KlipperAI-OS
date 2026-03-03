"""Installer ana uygulamasi."""
from __future__ import annotations

import subprocess

from .tui import TUI
from .utils.logger import get_logger
from .utils.sentinel import Sentinel
from .steps.welcome import WelcomeStep
from .steps.hardware import HardwareStep
from .steps.network_step import NetworkStep
from .steps.profile import ProfileStep
from .steps.user_setup import UserSetupStep
from .steps.install import InstallStep
from .steps.services import ServicesStep
from .steps.complete import CompleteStep

logger = get_logger()

SENTINEL_DIR = "/opt/klipperos-ai"
FIRST_BOOT_MARKER = "/opt/klipperos-ai/.first-boot"


class InstallerApp:
    """KlipperOS-AI TUI installer ana uygulamasi."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.tui = TUI(dry_run=dry_run)
        self.sentinel = Sentinel(base_dir=SENTINEL_DIR if not dry_run else "/tmp/kos-test")

    def run(self) -> int:
        """Tum adimlari sirayla calistir. 0=basari, 1=hata."""
        logger.info("=== KlipperOS-AI Installer v3.0 ===")

        # 1. Hosgeldin
        WelcomeStep(tui=self.tui).run()

        # 2. Donanim tespiti
        hw_info = HardwareStep(tui=self.tui).run()

        # 3. Ag baglantisi
        net_ok = NetworkStep(tui=self.tui, hw_info=hw_info).run()
        if not net_ok and not self.dry_run:
            logger.error("Internet baglantisi yok — kurulum iptal.")
            return 1

        # 4. Profil secimi
        profile_name = ProfileStep(tui=self.tui, hw_info=hw_info).run()

        # 5. Kullanici ayarlari
        UserSetupStep(tui=self.tui, dry_run=self.dry_run).run()

        # 6. Kurulum
        InstallStep(
            tui=self.tui,
            profile_name=profile_name,
            sentinel=self.sentinel,
        ).run()

        # 7. Servis yapilandirma
        ServicesStep(tui=self.tui).run()

        # 8. Tamamlandi
        CompleteStep(tui=self.tui, profile_name=profile_name).run()

        logger.info("Installer tamamlandi.")

        # First-boot sentinel'i kaldir ve reboot
        if not self.dry_run:
            self._cleanup_and_reboot()

        return 0

    def _cleanup_and_reboot(self) -> None:
        """First-boot sentinel'i sil, installer service'i devre disi birak, reboot."""
        import os
        try:
            if os.path.exists(FIRST_BOOT_MARKER):
                os.remove(FIRST_BOOT_MARKER)
                logger.info("First-boot marker silindi.")
        except OSError as e:
            logger.warning("First-boot marker silinemedi: %s", e)

        try:
            subprocess.run(
                ["systemctl", "disable", "kos-installer"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

        logger.info("Sistem yeniden baslatiliyor...")
        try:
            subprocess.run(["reboot"], timeout=5)
        except Exception:
            pass

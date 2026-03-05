"""Installer ana uygulamasi."""
from __future__ import annotations

import subprocess

from .tui import TUI
from .utils.logger import get_logger
from .utils.sentinel import Sentinel
from .utils.target import get_target, target_path
from .steps.welcome import WelcomeStep
from .steps.hardware import HardwareStep
from .steps.network_step import NetworkStep
from .steps.profile import ProfileStep
from .steps.disk import DiskStep, MOUNT_POINT
from .steps.user_setup import UserSetupStep
from .steps.install import InstallStep
from .steps.services import ServicesStep
from .steps.bootloader import BootloaderStep
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

        # 0. Klavye duzeni (sifre girisi oncesi zorunlu)
        self._setup_keyboard()

        # 1. Hosgeldin
        WelcomeStep(tui=self.tui).run()

        # 2. Donanim tespiti
        hw_info = HardwareStep(tui=self.tui).run()

        # 3. Ag baglantisi
        net_ok = NetworkStep(tui=self.tui, hw_info=hw_info).run()
        if not net_ok and not self.dry_run:
            logger.warning(
                "Internet baglantisi yok — agsiz devam ediliyor. "
                "Paket kurulumu atlanacak, disk kurulumu yapilabilir."
            )

        # 4. Profil secimi
        profile_name = ProfileStep(tui=self.tui, hw_info=hw_info).run()

        # 5. Disk secimi ve hazirlama
        disk_step = DiskStep(tui=self.tui)
        if not self.dry_run:
            if not disk_step.run():
                logger.error("Disk hazirlama basarisiz — kurulum iptal.")
                return 1
        else:
            logger.info("dry_run: Disk adimi atlandi (live CD modu).")

        # 6. Kullanici ayarlari
        UserSetupStep(tui=self.tui, dry_run=self.dry_run).run()

        # 7. Kurulum
        InstallStep(
            tui=self.tui,
            profile_name=profile_name,
            sentinel=self.sentinel,
        ).run()

        # 8. Servis yapilandirma
        ServicesStep(tui=self.tui).run()

        # 9. Bootloader kurulumu (sadece disk kurulumda)
        if get_target():
            bl_ok = BootloaderStep(
                tui=self.tui,
                disk=disk_step.disk,
                root_part=disk_step.root_part,
                efi_part=disk_step.efi_part,
                uefi=disk_step.uefi,
                mount_point=MOUNT_POINT,
            ).run()
            if not bl_ok:
                logger.error("Bootloader kurulumu basarisiz!")

        # 10. Tamamlandi
        CompleteStep(tui=self.tui, profile_name=profile_name).run()

        logger.info("Installer tamamlandi.")

        # First-boot sentinel'i kaldir ve reboot
        if not self.dry_run:
            self._cleanup_and_reboot()

        return 0

    def _setup_keyboard(self) -> None:
        """Konsol klavye duzenini ayarla (sifre girisi oncesi zorunlu)."""
        choice = self.tui.menu(
            "Klavye Duzeni",
            [("1", "Turkce Q"), ("2", "English US")],
            text="Klavye duzeninizi secin:\n\n"
                 "Turkce Q: i,g,u,s,c,o destegi\n"
                 "English US: standart ABD duzeni",
        )
        keymap = "trq" if choice == "1" else "us"
        if not self.dry_run:
            subprocess.run(
                ["loadkeys", keymap],
                capture_output=True,
                timeout=5,
            )
        logger.info("Klavye duzeni: %s", keymap)

    def _cleanup_and_reboot(self) -> None:
        """First-boot sentinel'i sil, installer service'i devre disi birak, reboot."""
        import os
        from .utils.runner import run_cmd

        # First-boot marker — disk kurulumda target_path ile hedef diskte
        marker = target_path(FIRST_BOOT_MARKER)
        try:
            if os.path.exists(marker):
                os.remove(marker)
                logger.info("First-boot marker silindi: %s", marker)
        except OSError as e:
            logger.warning("First-boot marker silinemedi: %s", e)

        # Installer service'i devre disi birak (chroot-aware run_cmd)
        run_cmd(["systemctl", "disable", "kos-installer"])

        logger.info("Sistem yeniden baslatiliyor...")
        try:
            subprocess.run(["reboot"], timeout=5)
        except Exception:
            pass

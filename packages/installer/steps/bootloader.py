"""Adim 9: Bootloader (GRUB) kurulumu ve fstab uretimi."""
from __future__ import annotations

from pathlib import Path

from ..tui import TUI
from ..utils.runner import run_cmd
from ..utils.target import target_path
from ..utils.logger import get_logger

logger = get_logger()


class BootloaderStep:
    """GRUB bootloader kurulumu — UEFI ve BIOS destekli."""

    def __init__(self, tui: TUI, disk: str, root_part: str,
                 efi_part: str, uefi: bool, mount_point: str):
        self.tui = tui
        self.disk = disk            # /dev/sda
        self.root_part = root_part  # /dev/sda1 veya /dev/sda2
        self.efi_part = efi_part    # /dev/sda1 (sadece UEFI)
        self.uefi = uefi
        self.mount_point = mount_point

    def run(self) -> bool:
        """Bootloader kurulumu: fstab → grub-install → update-grub."""
        logger.info("Bootloader kurulumu basladi (UEFI=%s)", self.uefi)

        # 1. fstab uret
        self.tui.progress("Bootloader", "fstab dosyasi uretiliyor...", 50)
        if not self._generate_fstab():
            self.tui.msgbox("Hata", "fstab dosyasi olusturulamadi!")
            return False

        # 2. GRUB kur
        self.tui.progress(
            "Bootloader",
            "GRUB bootloader kuruluyor...\n\n"
            f"Disk: {self.disk}\n"
            f"Mod: {'UEFI' if self.uefi else 'BIOS'}",
            60,
        )
        if not self._install_grub():
            self.tui.msgbox("Hata", "GRUB kurulumu basarisiz!")
            return False

        # 3. GRUB default ayarlari — dogru root= icin
        self._write_grub_defaults()

        # 4. update-grub (chroot icinde)
        self.tui.progress("Bootloader", "GRUB yapilandirmasi guncelleniyor...", 80)
        ok, out = run_cmd(["update-grub"], timeout=60)
        if not ok:
            logger.warning("update-grub basarisiz: %s", out[:200])
            # Fallback: Manuel grub.cfg uret
            self._write_fallback_grub_cfg()

        # 4. First-boot marker'i kaldir (disk uzerinde)
        self._remove_first_boot_marker()

        self.tui.progress("Bootloader", "Bootloader kurulumu tamamlandi!", 90)
        return True

    def _generate_fstab(self) -> bool:
        """UUID tabanli /etc/fstab dosyasi uret."""
        lines = ["# /etc/fstab — KlipperOS-AI otomatik uretildi\n"]

        # Root bolumu
        root_uuid = self._get_uuid(self.root_part)
        if not root_uuid:
            logger.error("Root UUID alinamadi: %s", self.root_part)
            return False
        lines.append(
            f"UUID={root_uuid}  /  ext4  noatime,errors=remount-ro  0  1\n"
        )

        # EFI bolumu (sadece UEFI)
        if self.uefi and self.efi_part:
            efi_uuid = self._get_uuid(self.efi_part)
            if efi_uuid:
                lines.append(
                    f"UUID={efi_uuid}  /boot/efi  vfat  umask=0077  0  1\n"
                )

        # tmpfs
        lines.append("tmpfs  /tmp  tmpfs  defaults,noatime,mode=1777  0  0\n")

        # Yaz
        fstab_path = target_path("/etc/fstab")
        try:
            Path(fstab_path).parent.mkdir(parents=True, exist_ok=True)
            with open(fstab_path, "w") as f:
                f.writelines(lines)
            logger.info("fstab yazildi: %s", fstab_path)
            return True
        except OSError as e:
            logger.error("fstab yazma hatasi: %s", e)
            return False

    @staticmethod
    def _get_uuid(partition: str) -> str:
        """Bolumun UUID'sini al."""
        ok, out = run_cmd(["blkid", "-s", "UUID", "-o", "value", partition])
        return out.strip() if ok else ""

    def _install_grub(self) -> bool:
        """GRUB'u diske kur (host'ta calisir)."""
        if self.uefi:
            return self._install_grub_uefi()
        return self._install_grub_bios()

    def _install_grub_uefi(self) -> bool:
        """UEFI modunda GRUB kur."""
        ok, out = run_cmd([
            "grub-install",
            "--target=x86_64-efi",
            f"--efi-directory={self.mount_point}/boot/efi",
            f"--boot-directory={self.mount_point}/boot",
            "--removable",
        ], timeout=60)
        if not ok:
            logger.error("GRUB UEFI kurulum hatasi: %s", out[:300])
            return False
        logger.info("GRUB UEFI basariyla kuruldu")
        return True

    def _install_grub_bios(self) -> bool:
        """BIOS/MBR modunda GRUB kur."""
        ok, out = run_cmd([
            "grub-install",
            "--target=i386-pc",
            f"--boot-directory={self.mount_point}/boot",
            self.disk,
        ], timeout=60)
        if not ok:
            logger.error("GRUB BIOS kurulum hatasi: %s", out[:300])
            return False
        logger.info("GRUB BIOS basariyla kuruldu")
        return True

    def _write_grub_defaults(self) -> None:
        """GRUB default config — chroot icinde update-grub dogru root= uretsin."""
        root_uuid = self._get_uuid(self.root_part)
        if not root_uuid:
            return
        defaults = target_path("/etc/default/grub")
        try:
            lines = []
            if Path(defaults).exists():
                lines = Path(defaults).read_text().splitlines(keepends=True)

            # GRUB_CMDLINE_LINUX_DEFAULT'a root= ekle
            content = Path(defaults).read_text() if Path(defaults).exists() else ""
            if "GRUB_DEVICE=" not in content:
                with open(defaults, "a") as f:
                    f.write(f'\nGRUB_DEVICE="UUID={root_uuid}"\n')
            logger.info("GRUB defaults yazildi: root UUID=%s", root_uuid)
        except OSError as e:
            logger.warning("GRUB defaults yazilamadi: %s", e)

    def _write_fallback_grub_cfg(self) -> None:
        """update-grub basarisiz olursa minimal grub.cfg yaz."""
        root_uuid = self._get_uuid(self.root_part)
        if not root_uuid:
            logger.error("Fallback grub.cfg icin UUID alinamadi!")
            return

        grub_cfg = target_path("/boot/grub/grub.cfg")
        cfg_content = f"""\
# KlipperOS-AI — fallback grub.cfg
set default=0
set timeout=5

menuentry "KlipperOS-AI" {{
    search --no-floppy --fs-uuid --set=root {root_uuid}
    linux /boot/vmlinuz root=UUID={root_uuid} ro quiet
    initrd /boot/initrd.img
}}
"""
        try:
            Path(grub_cfg).parent.mkdir(parents=True, exist_ok=True)
            with open(grub_cfg, "w") as f:
                f.write(cfg_content)
            logger.info("Fallback grub.cfg yazildi: %s", grub_cfg)
        except OSError as e:
            logger.error("Fallback grub.cfg yazilamadi: %s", e)

    def _remove_first_boot_marker(self) -> None:
        """First-boot marker'i hedef diskten kaldir."""
        marker = target_path("/opt/klipperos-ai/.first-boot")
        try:
            Path(marker).unlink(missing_ok=True)
            logger.info("First-boot marker silindi: %s", marker)
        except OSError as e:
            logger.warning("First-boot marker silinemedi: %s", e)

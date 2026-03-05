"""Adim 5: Disk secimi, bolumleme, formatlama, mount ve squashfs acma."""
from __future__ import annotations

from pathlib import Path

from ..tui import TUI
from ..utils.runner import run_cmd
from ..utils.target import set_target
from ..utils.logger import get_logger

logger = get_logger()

MOUNT_POINT = "/mnt/target"
SQUASHFS_PATHS = [
    "/run/live/medium/live/filesystem.squashfs",   # Standard live-boot
    "/run/live/rootfs/filesystem.squashfs",         # Some live-boot versions
    "/cdrom/live/filesystem.squashfs",              # Legacy Debian live
    "/lib/live/mount/medium/live/filesystem.squashfs",  # Older live-boot
]


class DiskStep:
    """Hedef diski hazirla: bolumleme → format → mount → squashfs → chroot ortami."""

    def __init__(self, tui: TUI):
        self.tui = tui
        self.uefi = Path("/sys/firmware/efi").exists()
        self.disk = ""        # /dev/sda
        self.root_part = ""   # /dev/sda1 (BIOS) veya /dev/sda2 (UEFI)
        self.efi_part = ""    # /dev/sda1 (sadece UEFI)

    def run(self) -> bool:
        """Disk hazirlama akisi. True=basarili, False=iptal/hata."""
        logger.info("Disk hazirlama basladi (UEFI=%s)", self.uefi)

        self.tui.progress("Disk Hazirlama", "Diskler taraniyor...", 0)

        # 1. Disk listele
        disks = self._list_disks()
        if not disks:
            self.tui.msgbox(
                "Hata",
                "Kurulum icin uygun disk bulunamadi!\n\n"
                "USB disk veya sabit disk takildigindan emin olun.",
            )
            return False

        # 2. Kullanici secimi
        self.disk = self._select_disk(disks)
        if not self.disk:
            return False

        # 3. Onay
        if not self._confirm_wipe():
            return False

        # 4. Bolumleme
        self.tui.progress(
            "Disk Hazirlama",
            f"Disk bolumleniyor: {self.disk}\n"
            f"Mod: {'UEFI (GPT)' if self.uefi else 'BIOS (MBR)'}",
            10,
        )
        if not self._partition():
            self.tui.msgbox("Hata", "Disk bolumleme basarisiz!")
            return False

        # 5. Formatlama
        self.tui.progress(
            "Disk Hazirlama",
            "Bolumler formatlaniyor...",
            20,
        )
        if not self._format():
            self.tui.msgbox("Hata", "Disk formatlama basarisiz!")
            return False

        # 6. Mount
        self.tui.progress(
            "Disk Hazirlama",
            f"Bolumler baglaniyor: {MOUNT_POINT}",
            30,
        )
        if not self._mount():
            self.tui.msgbox("Hata", "Disk mount basarisiz!")
            return False

        # 7. Squashfs ac
        self.tui.progress(
            "Disk Hazirlama",
            "Sistem dosyalari diske kopyalaniyor...\n\n"
            "Bu islem birkac dakika surebilir.\n"
            "Lutfen bekleyin...",
            40,
        )
        if not self._extract_squashfs():
            self.tui.msgbox("Hata", "Sistem dosyalari kopyalanamadi!")
            return False

        # 8. Bind mount
        self.tui.progress(
            "Disk Hazirlama",
            "Chroot ortami hazirlaniyor...",
            85,
        )
        if not self._bind_mounts():
            self.tui.msgbox("Hata", "Chroot bind mount basarisiz!")
            return False
        self._copy_resolv()

        # 9. Target'i ayarla — bundan sonra tum I/O diske gider
        set_target(MOUNT_POINT)
        logger.info("Target set: %s", MOUNT_POINT)

        self.tui.progress(
            "Disk Hazirlama",
            "Disk hazirlama tamamlandi!\n\n"
            f"Hedef: {MOUNT_POINT}",
            90,
        )
        return True

    # ── Disk listeleme ──────────────────────────────────────────────

    def _list_disks(self) -> list[tuple[str, str, str]]:
        """Kurulabilir diskleri listele → [(name, size, model), ...]"""
        ok, output = run_cmd([
            "lsblk", "-d", "-n", "-o", "NAME,SIZE,MODEL", "-e2,7,11",
        ])
        if not ok:
            logger.error("lsblk basarisiz: %s", output)
            return []

        disks = []
        for line in output.strip().splitlines():
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            name = parts[0]
            size = parts[1]
            model = parts[2].strip() if len(parts) > 2 else "Bilinmiyor"
            # Floppy diskleri haric tut (fd0, fd1, ...)
            if name.startswith("fd"):
                logger.debug("Floppy haric tutuldu: %s", name)
                continue
            # Live USB'yi haric tut (boot diskini kurulum yapma)
            dev = f"/dev/{name}"
            if self._is_boot_device(dev):
                continue
            disks.append((name, size, model))

        logger.info("Bulunan diskler: %s", disks)
        return disks

    @staticmethod
    def _is_boot_device(dev: str) -> bool:
        """Boot diski mi kontrol et (live USB'yi haric tut)."""
        ok, output = run_cmd(["findmnt", "-n", "-o", "SOURCE", "/run/live/medium"])
        if ok and output.strip():
            boot_src = output.strip()
            # /dev/sda1 → /dev/sda karsilastirmasi
            if boot_src.startswith(dev):
                return True
        return False

    # ── Disk secimi ─────────────────────────────────────────────────

    def _select_disk(self, disks: list[tuple[str, str, str]]) -> str:
        """TUI menu ile disk sec, /dev/sdX dondur."""
        items = []
        for i, (name, size, model) in enumerate(disks):
            items.append((str(i + 1), f"/dev/{name}  {size}  {model}"))

        choice = self.tui.menu(
            "Kurulum Diski",
            items,
            text="KlipperOS-AI'nin kurulacagi diski secin:\n\n"
                 "DIKKAT: Sectigi diskteki TUM VERILER SILINECEK!",
        )

        try:
            idx = int(choice) - 1
            return f"/dev/{disks[idx][0]}"
        except (ValueError, IndexError):
            return ""

    def _confirm_wipe(self) -> bool:
        """Disk silme oncesi 2. onay."""
        return self.tui.yesno(
            f"UYARI: {self.disk} diskindeki TUM VERILER SILINECEK!\n\n"
            "Bu islem geri alinamaz.\n\n"
            "Devam etmek istiyor musunuz?",
            title="Disk Silme Onayi",
        )

    # ── Bolumleme ───────────────────────────────────────────────────

    def _partition(self) -> bool:
        """Diski bolumle: UEFI=GPT+ESP+root, BIOS=MBR+root."""
        if self.uefi:
            return self._partition_uefi()
        return self._partition_bios()

    def _partition_uefi(self) -> bool:
        """GPT: 512MB ESP (fat32) + geri kalan root (ext4)."""
        cmds = [
            ["parted", "-s", self.disk, "mklabel", "gpt"],
            ["parted", "-s", self.disk, "mkpart", "ESP", "fat32", "1MiB", "513MiB"],
            ["parted", "-s", self.disk, "set", "1", "esp", "on"],
            ["parted", "-s", self.disk, "mkpart", "root", "ext4", "513MiB", "100%"],
        ]
        for cmd in cmds:
            ok, out = run_cmd(cmd, timeout=30)
            if not ok:
                logger.error("Bolumleme hatasi: %s → %s", cmd, out)
                return False

        # Bolum isimlerini belirle
        self.efi_part = self._resolve_partition(1)
        self.root_part = self._resolve_partition(2)
        logger.info("UEFI bolumler: ESP=%s, root=%s", self.efi_part, self.root_part)
        return True

    def _partition_bios(self) -> bool:
        """MBR: tek root bolum (ext4)."""
        cmds = [
            ["parted", "-s", self.disk, "mklabel", "msdos"],
            ["parted", "-s", self.disk, "mkpart", "primary", "ext4", "1MiB", "100%"],
            ["parted", "-s", self.disk, "set", "1", "boot", "on"],
        ]
        for cmd in cmds:
            ok, out = run_cmd(cmd, timeout=30)
            if not ok:
                logger.error("Bolumleme hatasi: %s → %s", cmd, out)
                return False

        self.root_part = self._resolve_partition(1)
        logger.info("BIOS bolumler: root=%s", self.root_part)
        return True

    def _resolve_partition(self, num: int) -> str:
        """Disk adina gore bolum yolunu dondur.

        /dev/sda  → /dev/sda1
        /dev/nvme0n1 → /dev/nvme0n1p1
        /dev/mmcblk0 → /dev/mmcblk0p1
        """
        if self.disk[-1].isdigit():
            return f"{self.disk}p{num}"
        return f"{self.disk}{num}"

    # ── Formatlama ──────────────────────────────────────────────────

    def _format(self) -> bool:
        """Bolumleri formatla."""
        if self.uefi and self.efi_part:
            ok, out = run_cmd(["mkfs.vfat", "-F", "32", self.efi_part], timeout=30)
            if not ok:
                logger.error("ESP formatlama hatasi: %s", out)
                return False

        ok, out = run_cmd(
            ["mkfs.ext4", "-F", "-L", "klipperos", self.root_part],
            timeout=120,
        )
        if not ok:
            logger.error("Root formatlama hatasi: %s", out)
            return False
        return True

    # ── Mount ───────────────────────────────────────────────────────

    def _mount(self) -> bool:
        """Bolumleri mount et."""
        run_cmd(["mkdir", "-p", MOUNT_POINT])
        ok, out = run_cmd(["mount", self.root_part, MOUNT_POINT])
        if not ok:
            logger.error("Root mount hatasi: %s", out)
            return False

        if self.uefi and self.efi_part:
            efi_dir = f"{MOUNT_POINT}/boot/efi"
            run_cmd(["mkdir", "-p", efi_dir])
            ok, out = run_cmd(["mount", self.efi_part, efi_dir])
            if not ok:
                logger.error("ESP mount hatasi: %s", out)
                return False
        return True

    # ── Squashfs ────────────────────────────────────────────────────

    @staticmethod
    def _find_squashfs() -> str:
        """Bilinen yollarda squashfs dosyasini ara, ilk bulunani dondur."""
        for path in SQUASHFS_PATHS:
            if Path(path).exists():
                return path
        # Fallback: find komutu ile ara
        ok, out = run_cmd(
            ["find", "/run/live", "-name", "filesystem.squashfs", "-type", "f"],
            timeout=10,
        )
        if ok and out.strip():
            return out.strip().splitlines()[0]
        return ""

    def _extract_squashfs(self) -> bool:
        """Live squashfs imajini hedefe ac."""
        sqfs = self._find_squashfs()
        if not sqfs:
            logger.error("Squashfs bulunamadi! Aranan yollar: %s", SQUASHFS_PATHS)
            # Debug: list /run/live contents for diagnosis
            ok, ls_out = run_cmd(["find", "/run/live", "-maxdepth", "3", "-ls"], timeout=5)
            if ok:
                logger.error("DEBUG /run/live icerik:\n%s", ls_out[:500])
            self.tui.msgbox(
                "Hata — Squashfs",
                "Squashfs dosyasi bulunamadi!\n\n"
                f"Aranan: {SQUASHFS_PATHS[0]}\n"
                f"Debug: {ls_out[:200] if ok else 'ls basarisiz'}",
            )
            return False

        logger.info("Squashfs bulundu: %s", sqfs)
        ok, out = run_cmd(
            ["unsquashfs", "-f", "-d", MOUNT_POINT, sqfs],
            timeout=600,
        )
        if not ok:
            logger.error("Squashfs acma hatasi: %s", out[:300])
            return False
        logger.info("Squashfs basariyla acildi → %s", MOUNT_POINT)
        return True

    # ── Bind mount + DNS ────────────────────────────────────────────

    def _bind_mounts(self) -> bool:
        """Chroot icin gerekli sanal dosya sistemlerini bagla.

        Returns True if all critical mounts succeed.
        """
        binds = [
            # (mount_args, mount_target_suffix)
            (["mount", "--bind", "/dev"], "/dev"),
            (["mount", "--bind", "/dev/pts"], "/dev/pts"),
            (["mount", "-t", "proc", "proc"], "/proc"),
            (["mount", "-t", "sysfs", "sysfs"], "/sys"),
            (["mount", "--bind", "/run"], "/run"),
        ]
        all_ok = True
        for mount_cmd, target_suffix in binds:
            dest = f"{MOUNT_POINT}{target_suffix}"
            run_cmd(["mkdir", "-p", dest])
            ok, out = run_cmd(mount_cmd + [dest])
            if not ok:
                logger.error("Bind mount basarisiz: %s → %s", mount_cmd, out[:200])
                all_ok = False
        return all_ok

    def _copy_resolv(self) -> None:
        """DNS ayarlarini hedefe kopyala (chroot icin internet erisimi)."""
        run_cmd(["cp", "/etc/resolv.conf", f"{MOUNT_POINT}/etc/resolv.conf"])

    # ── Temizlik (CompleteStep tarafindan cagirilir) ────────────────

    @staticmethod
    def unmount_all() -> None:
        """Tum mount noktalarini temizle (kurulum sonunda cagirilir)."""
        for m in ["/dev/pts", "/dev", "/proc", "/sys", "/run", "/boot/efi"]:
            run_cmd(["umount", "-l", f"{MOUNT_POINT}{m}"])
        run_cmd(["umount", "-l", MOUNT_POINT])
        set_target(None)
        logger.info("Tum mount noktalari cikarildi.")

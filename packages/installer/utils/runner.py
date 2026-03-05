"""Subprocess wrapper — chroot destekli."""
from __future__ import annotations

import subprocess

from .logger import get_logger
from .target import get_target

logger = get_logger()

# Host'ta calismasi gereken komutlar — chroot YAPILMAZ.
# Bunlar dogrudan donanim/disk/mount islemleridir.
_HOST_COMMANDS = frozenset({
    "mount", "umount",
    "parted", "mkfs.ext4", "mkfs.vfat", "mkswap",
    "unsquashfs", "grub-install",
    "lsblk", "blkid", "findmnt",
    "loadkeys",
    "ln", "rm", "cp", "rsync",
})


def run_cmd(
    cmd: list[str],
    timeout: int = 600,
    check: bool = False,
) -> tuple[bool, str]:
    """Komut calistir, (basari, cikti) dondur.

    Target set edilmisse komutlar otomatik chroot icinde calisir.
    _HOST_COMMANDS listesindeki komutlar her zaman host'ta calisir.
    """
    target = get_target()
    if target and cmd[0] not in _HOST_COMMANDS:
        cmd = ["chroot", target] + cmd

    logger.debug("CMD: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        if not success:
            logger.debug("CMD FAIL (rc=%d): %s", result.returncode, output[:200])
        return success, output
    except subprocess.TimeoutExpired:
        logger.error("CMD TIMEOUT: %s", " ".join(cmd))
        return False, "timeout"
    except FileNotFoundError:
        logger.error("CMD NOT FOUND: %s", cmd[0])
        return False, "not found"

"""Mainsail web arayuzu kurucu."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.logger import get_logger
from ..utils.runner import run_cmd

logger = get_logger()

MAINSAIL_DIR = "/home/klipper/mainsail"
MAINSAIL_RELEASE_URL = (
    "https://github.com/mainsail-crew/mainsail/releases/latest/download/mainsail.zip"
)


class MainsailInstaller(BaseInstaller):
    """Mainsail web UI kurucu."""

    name = "mainsail"

    def _install(self) -> bool:
        run_cmd(["mkdir", "-p", MAINSAIL_DIR])

        ok, _ = run_cmd(
            ["wget", "-q", "-O", "/tmp/mainsail.zip", MAINSAIL_RELEASE_URL],
            timeout=120,
        )
        if not ok:
            return False

        ok, _ = run_cmd(["unzip", "-o", "/tmp/mainsail.zip", "-d", MAINSAIL_DIR])
        if not ok:
            return False

        run_cmd(["rm", "-f", "/tmp/mainsail.zip"])
        run_cmd(["chown", "-R", "klipper:klipper", MAINSAIL_DIR])

        return True

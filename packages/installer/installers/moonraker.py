"""Moonraker kurucu."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.logger import get_logger
from ..utils.runner import run_cmd

logger = get_logger()

KLIPPER_USER = "klipper"
KLIPPER_HOME = f"/home/{KLIPPER_USER}"
MOONRAKER_REPO = "https://github.com/Arksine/moonraker.git"
MOONRAKER_DIR = f"{KLIPPER_HOME}/moonraker"
MOONRAKER_VENV = f"{KLIPPER_HOME}/moonraker-env"

MOONRAKER_SERVICE = f"""\
[Unit]
Description=Moonraker API Server
After=network.target klipper.service

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={MOONRAKER_VENV}/bin/python {MOONRAKER_DIR}/moonraker/moonraker.py \
  -d {KLIPPER_HOME}/printer_data
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


class MoonrakerInstaller(BaseInstaller):
    """Moonraker API server kurucu."""

    name = "moonraker"

    def _install(self) -> bool:
        ok, _ = run_cmd(
            ["sudo", "-u", KLIPPER_USER, "git", "clone", MOONRAKER_REPO, MOONRAKER_DIR]
        )
        if not ok:
            return False

        ok, _ = run_cmd(
            ["sudo", "-u", KLIPPER_USER, "python3", "-m", "venv", MOONRAKER_VENV]
        )
        if not ok:
            return False

        ok, _ = run_cmd(
            [
                "sudo",
                "-u",
                KLIPPER_USER,
                f"{MOONRAKER_VENV}/bin/pip",
                "install",
                "--quiet",
                "-r",
                f"{MOONRAKER_DIR}/scripts/moonraker-requirements.txt",
            ],
            timeout=180,
        )
        if not ok:
            return False

        try:
            with self._open_target("/etc/systemd/system/moonraker.service") as f:
                f.write(MOONRAKER_SERVICE)
            run_cmd(["systemctl", "daemon-reload"])
            run_cmd(["systemctl", "enable", "moonraker"])
        except OSError as e:
            logger.error("Moonraker service olusturulamadi: %s", e)
            return False

        return True

"""Klipper kurucu."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.logger import get_logger
from ..utils.runner import run_cmd

logger = get_logger()

KLIPPER_USER = "klipper"
KLIPPER_HOME = f"/home/{KLIPPER_USER}"
KLIPPER_REPO = "https://github.com/Klipper3d/klipper.git"
KLIPPER_VENV = f"{KLIPPER_HOME}/klippy-env"
KLIPPER_DIR = f"{KLIPPER_HOME}/klipper"

KLIPPER_SERVICE = f"""\
[Unit]
Description=Klipper 3D Printer Firmware Host
After=network.target

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={KLIPPER_VENV}/bin/python {KLIPPER_DIR}/klippy/klippy.py \
  {KLIPPER_HOME}/printer_data/config/printer.cfg \
  -l {KLIPPER_HOME}/printer_data/logs/klippy.log \
  -a /tmp/klippy_uds
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


class KlipperInstaller(BaseInstaller):
    """Klipper firmware host kurucu."""

    name = "klipper"

    def _install(self) -> bool:
        ok, _ = run_cmd(
            ["sudo", "-u", KLIPPER_USER, "git", "clone", KLIPPER_REPO, KLIPPER_DIR]
        )
        if not ok:
            return False

        ok, _ = run_cmd(
            ["sudo", "-u", KLIPPER_USER, "python3", "-m", "venv", KLIPPER_VENV]
        )
        if not ok:
            return False

        ok, _ = run_cmd(
            [
                "sudo",
                "-u",
                KLIPPER_USER,
                f"{KLIPPER_VENV}/bin/pip",
                "install",
                "--quiet",
                "cffi",
                "greenlet",
                "pyserial",
                "jinja2",
                "markupsafe",
            ],
            timeout=120,
        )
        if not ok:
            return False

        try:
            with self._open_target("/etc/systemd/system/klipper.service") as f:
                f.write(KLIPPER_SERVICE)
            run_cmd(["systemctl", "daemon-reload"])
            run_cmd(["systemctl", "enable", "klipper"])
        except OSError as e:
            logger.error("Klipper service olusturulamadi: %s", e)
            return False

        return True

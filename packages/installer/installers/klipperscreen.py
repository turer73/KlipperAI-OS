"""KlipperScreen kurucu — dokunmatik ekran arayuzu."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.logger import get_logger
from ..utils.runner import run_cmd

logger = get_logger()

KLIPPER_USER = "klipper"
KLIPPER_HOME = f"/home/{KLIPPER_USER}"
KS_REPO = "https://github.com/KlipperScreen/KlipperScreen.git"
KS_DIR = f"{KLIPPER_HOME}/KlipperScreen"
KS_VENV = f"{KLIPPER_HOME}/KlipperScreen-env"

KS_SERVICE = f"""\
[Unit]
Description=KlipperScreen
After=moonraker.service
Wants=moonraker.service

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={KS_VENV}/bin/python {KS_DIR}/screen.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


class KlipperScreenInstaller(BaseInstaller):
    """KlipperScreen dokunmatik ekran arayuzu kurucu."""

    name = "klipperscreen"

    def _install(self) -> bool:
        ok, _ = run_cmd(
            ["sudo", "-u", KLIPPER_USER, "git", "clone", KS_REPO, KS_DIR],
            timeout=120,
        )
        if not ok:
            return False

        ok, _ = run_cmd(
            ["sudo", "-u", KLIPPER_USER, "python3", "-m", "venv", KS_VENV]
        )
        if not ok:
            return False

        ok, _ = run_cmd(
            [
                "sudo", "-u", KLIPPER_USER,
                f"{KS_VENV}/bin/pip", "install", "--quiet",
                "-r", f"{KS_DIR}/scripts/KlipperScreen-requirements.txt",
            ],
            timeout=180,
        )
        if not ok:
            logger.warning("KlipperScreen pip basarisiz — requirements eksik olabilir")

        try:
            with open("/etc/systemd/system/KlipperScreen.service", "w") as f:
                f.write(KS_SERVICE)
            run_cmd(["systemctl", "daemon-reload"])
            run_cmd(["systemctl", "enable", "KlipperScreen"])
        except OSError as e:
            logger.error("KlipperScreen service olusturulamadi: %s", e)
            return False

        return True

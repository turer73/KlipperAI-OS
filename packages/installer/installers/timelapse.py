"""Timelapse kurucu — baski zaman atlamali kayit."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.logger import get_logger
from ..utils.runner import run_cmd
from ..utils.target import target_path

logger = get_logger()

KLIPPER_USER = "klipper"
KLIPPER_HOME = f"/home/{KLIPPER_USER}"
TL_REPO = "https://github.com/mainsail-crew/moonraker-timelapse.git"
TL_DIR = f"{KLIPPER_HOME}/moonraker-timelapse"

TIMELAPSE_MOONRAKER_SECTION = """\

[timelapse]
output_path: ~/printer_data/timelapse/
frame_path: /tmp/timelapse/
"""


class TimelapseInstaller(BaseInstaller):
    """Moonraker-timelapse kurucu."""

    name = "timelapse"

    def _install(self) -> bool:
        import os

        ok, _ = run_cmd(
            ["sudo", "-u", KLIPPER_USER, "git", "clone", TL_REPO, TL_DIR],
            timeout=120,
        )
        if not ok:
            return False

        # Component symlink — moonraker'a timelapse modulu ekle
        run_cmd([
            "ln", "-sf",
            f"{TL_DIR}/component/timelapse.py",
            f"{KLIPPER_HOME}/moonraker/moonraker/components/timelapse.py",
        ])

        # Klipper macro symlink
        run_cmd([
            "ln", "-sf",
            f"{TL_DIR}/klipper_macro/timelapse.cfg",
            f"{KLIPPER_HOME}/printer_data/config/timelapse.cfg",
        ])

        # printer.cfg'ye include ekle
        pcfg = f"{KLIPPER_HOME}/printer_data/config/printer.cfg"
        try:
            real_pcfg = target_path(pcfg)
            if os.path.exists(real_pcfg):
                with open(real_pcfg, "r") as f:
                    content = f.read()
                if "timelapse.cfg" not in content:
                    with self._open_target(pcfg, "a") as f:
                        f.write("\n[include timelapse.cfg]\n")
        except OSError as e:
            logger.warning("printer.cfg timelapse include eklenemedi: %s", e)

        # moonraker.conf'a timelapse section ekle
        mcfg = f"{KLIPPER_HOME}/printer_data/config/moonraker.conf"
        try:
            real_mcfg = target_path(mcfg)
            if os.path.exists(real_mcfg):
                with open(real_mcfg, "r") as f:
                    content = f.read()
                if "[timelapse]" not in content:
                    with self._open_target(mcfg, "a") as f:
                        f.write(TIMELAPSE_MOONRAKER_SECTION)
        except OSError as e:
            logger.warning("moonraker.conf timelapse section eklenemedi: %s", e)

        # Timelapse output dizini
        run_cmd([
            "sudo", "-u", KLIPPER_USER,
            "mkdir", "-p", f"{KLIPPER_HOME}/printer_data/timelapse",
        ])

        return True

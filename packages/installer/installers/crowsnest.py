"""Crowsnest kurucu — kamera akisi."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.logger import get_logger
from ..utils.runner import run_cmd

logger = get_logger()

KLIPPER_USER = "klipper"
KLIPPER_HOME = f"/home/{KLIPPER_USER}"
CN_REPO = "https://github.com/mainsail-crew/crowsnest.git"
CN_DIR = f"{KLIPPER_HOME}/crowsnest"
CN_CONF = f"{KLIPPER_HOME}/printer_data/config/crowsnest.conf"

CN_CONFIG_TEMPLATE = """\
#### crowsnest.conf — KlipperOS-AI

[crowsnest]
log_path: ~/printer_data/logs/crowsnest.log
log_level: verbose
delete_log: true

[cam 1]
mode: ustreamer
enable_rtsp: false
port: 8080
device: /dev/video0
resolution: 640x480
max_fps: 15
"""

CN_SERVICE = f"""\
[Unit]
Description=Crowsnest Camera Streamer
After=network.target

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={CN_DIR}/crowsnest -c {CN_CONF}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


class CrowsnestInstaller(BaseInstaller):
    """Crowsnest kamera akisi kurucu."""

    name = "crowsnest"

    def _install(self) -> bool:
        ok, _ = run_cmd(
            ["sudo", "-u", KLIPPER_USER, "git", "clone", CN_REPO, CN_DIR],
            timeout=120,
        )
        if not ok:
            return False

        # Crowsnest kendi installer'ini calistir
        run_cmd(
            ["sudo", "-u", KLIPPER_USER, "bash", f"{CN_DIR}/tools/install.sh"],
            timeout=180,
        )

        # Config dosyasi
        try:
            import os
            if not os.path.exists(CN_CONF):
                with open(CN_CONF, "w") as f:
                    f.write(CN_CONFIG_TEMPLATE)
                run_cmd(["chown", f"{KLIPPER_USER}:{KLIPPER_USER}", CN_CONF])
        except OSError as e:
            logger.warning("Crowsnest config olusturulamadi: %s", e)

        # Systemd service (crowsnest kendi kurmadiysa)
        try:
            import os
            if not os.path.exists("/etc/systemd/system/crowsnest.service"):
                with open("/etc/systemd/system/crowsnest.service", "w") as f:
                    f.write(CN_SERVICE)
            run_cmd(["systemctl", "daemon-reload"])
            run_cmd(["systemctl", "enable", "crowsnest"])
        except OSError as e:
            logger.error("Crowsnest service olusturulamadi: %s", e)
            return False

        return True

"""AI Monitor kurucu — yapay zeka baski izleyici."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.logger import get_logger
from ..utils.runner import run_cmd

logger = get_logger()

KLIPPER_USER = "klipper"
AI_DIR = "/opt/klipperos-ai/ai-monitor"
AI_VENV = "/opt/klipperos-ai/ai-venv"
SCRIPT_DIR = "/opt/klipperos-ai"

AI_MONITOR_SERVICE = f"""\
[Unit]
Description=KlipperOS-AI Print Monitor
After=network.target moonraker.service crowsnest.service

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={AI_VENV}/bin/python {AI_DIR}/print_monitor.py
Restart=always
RestartSec=30
Environment=MOONRAKER_URL=http://127.0.0.1:7125
Environment=CAMERA_URL=http://127.0.0.1:8080/?action=snapshot
Environment=CHECK_INTERVAL=10
Environment=FLOWGUARD_ENABLED=1
Environment=ADAPTIVE_PRINT=0
Environment=PREDICTIVE_MAINT=1
Environment=AUTORECOVERY_ENABLED=0

[Install]
WantedBy=multi-user.target
"""

RESOURCE_MANAGER_SERVICE = f"""\
[Unit]
Description=KlipperOS-AI Resource Manager
After=network.target klipperos-ai-monitor.service
Requires=klipperos-ai-monitor.service

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={AI_VENV}/bin/python {AI_DIR}/resource_manager.py
Restart=always
RestartSec=30
MemoryMax=64M
CPUQuota=10%
Environment=MOONRAKER_URL=http://127.0.0.1:7125

[Install]
WantedBy=multi-user.target
"""

AI_PIP_PACKAGES = [
    "tflite-runtime",
    "numpy",
    "pillow",
    "opencv-python-headless",
    "requests",
    "psutil",
]


class AIMonitorInstaller(BaseInstaller):
    """KlipperOS-AI Print Monitor kurucu."""

    name = "ai_monitor"

    def _install(self) -> bool:
        # Dizinleri olustur
        run_cmd(["mkdir", "-p", f"{AI_DIR}/models"])

        # ai-monitor dosyalarini kopyala (kaynak koddan hedefe)
        import os
        src_ai = os.path.join(SCRIPT_DIR, "..", "ai-monitor")
        # ISO icerisinde dosyalar /opt/klipperos-ai altinda zaten olabilir
        # yoksa kaynak dizinden kopyala
        if os.path.isdir(src_ai) and not os.path.exists(f"{AI_DIR}/print_monitor.py"):
            run_cmd(["cp", "-r", f"{src_ai}/.", AI_DIR])

        # Python venv
        if not os.path.isdir(AI_VENV):
            ok, _ = run_cmd(["python3", "-m", "venv", AI_VENV])
            if not ok:
                return False

        # Pip install
        ok, _ = run_cmd(
            [f"{AI_VENV}/bin/pip", "install", "--quiet"] + AI_PIP_PACKAGES,
            timeout=300,
        )
        if not ok:
            logger.warning("AI Monitor pip basarisiz — bazi paketler eksik olabilir")

        # Systemd services
        try:
            with open("/etc/systemd/system/klipperos-ai-monitor.service", "w") as f:
                f.write(AI_MONITOR_SERVICE)
            with open("/etc/systemd/system/kos-resource-manager.service", "w") as f:
                f.write(RESOURCE_MANAGER_SERVICE)
            run_cmd(["systemctl", "daemon-reload"])
            run_cmd(["systemctl", "enable", "klipperos-ai-monitor"])
            run_cmd(["systemctl", "enable", "kos-resource-manager"])
        except OSError as e:
            logger.error("AI Monitor service olusturulamadi: %s", e)
            return False

        return True

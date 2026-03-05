"""Multi-printer kurucu — birden fazla yazici destegi."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.logger import get_logger
from ..utils.runner import run_cmd
from ..utils.target import target_path

logger = get_logger()

KLIPPER_USER = "klipper"
KLIPPER_HOME = f"/home/{KLIPPER_USER}"
MAX_EXTRA_PRINTERS = 2  # printer_2, printer_3


def _klipper_service(idx: int, data_dir: str) -> str:
    return f"""\
[Unit]
Description=Klipper 3D Printer {idx}
After=network.target

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={KLIPPER_HOME}/klippy-env/bin/python {KLIPPER_HOME}/klipper/klippy/klippy.py \
  {data_dir}/config/printer.cfg \
  -l {data_dir}/logs/klippy.log \
  -a /tmp/klippy_uds_{idx}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


def _moonraker_service(idx: int, data_dir: str) -> str:
    return f"""\
[Unit]
Description=Moonraker API Server - Printer {idx}
After=network.target klipper-{idx}.service

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={KLIPPER_HOME}/moonraker-env/bin/python {KLIPPER_HOME}/moonraker/moonraker/moonraker.py \
  -d {data_dir}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


def _moonraker_config(idx: int) -> str:
    port = 7125 + idx - 1
    return f"""\
[server]
host: 0.0.0.0
port: {port}
klippy_uds_address: /tmp/klippy_uds_{idx}

[authorization]
trusted_clients:
    10.0.0.0/8
    127.0.0.0/8
    169.254.0.0/16
    172.16.0.0/12
    192.168.0.0/16
cors_domains:
    *.lan
    *.local
    *://localhost
    *://localhost:*

[octoprint_compat]
[history]
[file_manager]
enable_root_delete: True
"""


class MultiPrinterInstaller(BaseInstaller):
    """Birden fazla yazici destegi kurucu."""

    name = "multi_printer"

    def _install(self) -> bool:
        import os

        for idx in range(2, 2 + MAX_EXTRA_PRINTERS):
            data_dir = f"{KLIPPER_HOME}/printer_{idx}_data"
            subdirs = ["config", "logs", "gcodes", "database"]

            # Veri dizinlerini olustur
            for sub in subdirs:
                run_cmd(["sudo", "-u", KLIPPER_USER, "mkdir", "-p", f"{data_dir}/{sub}"])

            # Klipper instance service
            try:
                with self._open_target(f"/etc/systemd/system/klipper-{idx}.service") as f:
                    f.write(_klipper_service(idx, data_dir))
            except OSError as e:
                logger.error("klipper-%d service olusturulamadi: %s", idx, e)
                return False

            # Moonraker instance service
            try:
                with self._open_target(f"/etc/systemd/system/moonraker-{idx}.service") as f:
                    f.write(_moonraker_service(idx, data_dir))
            except OSError as e:
                logger.error("moonraker-%d service olusturulamadi: %s", idx, e)
                return False

            # Moonraker config
            moon_conf = f"{data_dir}/config/moonraker.conf"
            if not os.path.exists(target_path(moon_conf)):
                try:
                    with self._open_target(moon_conf) as f:
                        f.write(_moonraker_config(idx))
                    run_cmd(["chown", f"{KLIPPER_USER}:{KLIPPER_USER}", moon_conf])
                except OSError as e:
                    logger.warning("moonraker-%d config olusturulamadi: %s", idx, e)

            # Varsayilan printer.cfg
            pcfg = f"{data_dir}/config/printer.cfg"
            if not os.path.exists(target_path(pcfg)):
                try:
                    with self._open_target(pcfg) as f:
                        f.write(f"# Printer {idx} — yapilandirilmamis\n")
                    run_cmd(["chown", f"{KLIPPER_USER}:{KLIPPER_USER}", pcfg])
                except OSError as e:
                    logger.warning("printer-%d cfg olusturulamadi: %s", idx, e)

            # Enable services (baslatma yapma — kullanici talep edince baslatir)
            run_cmd(["systemctl", "daemon-reload"])
            run_cmd(["systemctl", "enable", f"klipper-{idx}"])
            run_cmd(["systemctl", "enable", f"moonraker-{idx}"])

        logger.info("Multi-printer destegi kuruldu (printer 2-%d)", 1 + MAX_EXTRA_PRINTERS)
        return True

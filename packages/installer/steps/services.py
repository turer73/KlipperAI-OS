"""Adim 7: Servis yapilandirma."""
from __future__ import annotations

import os
from pathlib import Path

from ..tui import TUI
from ..utils.runner import run_cmd
from ..utils.target import target_path, get_target
from ..utils.logger import get_logger

logger = get_logger()

NGINX_SITE = """\
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    root /home/klipper/mainsail;
    index index.html;
    server_name _;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /websocket {
        proxy_pass http://127.0.0.1:7125/websocket;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location ~ ^/(printer|api|access|machine|server)/ {
        proxy_pass http://127.0.0.1:7125;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
"""


class ServicesStep:
    def __init__(self, tui: TUI):
        self.tui = tui

    def run(self) -> bool:
        logger.info("Servisler yapilandiriliyor...")
        self.tui.progress(
            "Yapilandirma",
            "Nginx web sunucusu yapilandiriliyor...",
            92,
        )

        try:
            # Nginx config dosyasini hedef diske yaz
            nginx_path = target_path("/etc/nginx/sites-available/mainsail")
            Path(nginx_path).parent.mkdir(parents=True, exist_ok=True)
            with open(nginx_path, "w") as f:
                f.write(NGINX_SITE)

            # Symlink — target_path ile hedef diskte olustur
            # (ln _HOST_COMMANDS'ta → chroot bypass'lanir, dogrudan yazmaliyiz)
            enabled_dir = target_path("/etc/nginx/sites-enabled")
            Path(enabled_dir).mkdir(parents=True, exist_ok=True)

            symlink = os.path.join(enabled_dir, "mainsail")
            if os.path.islink(symlink) or os.path.exists(symlink):
                os.remove(symlink)
            os.symlink("/etc/nginx/sites-available/mainsail", symlink)

            # Default site'i kaldir (hedef diskte)
            default = os.path.join(enabled_dir, "default")
            if os.path.islink(default) or os.path.exists(default):
                os.remove(default)

            # systemctl enable — chroot icinde symlink olusturur (dogru)
            run_cmd(["systemctl", "enable", "nginx"])
            # NOT: systemctl restart/start chroot'ta systemd olmadigi icin
            # basarisiz olur — sadece enable yeterli
        except OSError as e:
            logger.error("Nginx yapilandirilamadi: %s", e)

        self.tui.progress(
            "Yapilandirma",
            "Yazici dizinleri olusturuluyor...",
            95,
        )
        dirs = [
            "/home/klipper/printer_data/config",
            "/home/klipper/printer_data/logs",
            "/home/klipper/printer_data/gcodes",
            "/home/klipper/printer_data/database",
        ]
        for d in dirs:
            # mkdir _HOST_COMMANDS'ta degil → chroot icinde calisir (dogru)
            run_cmd(["mkdir", "-p", d])
        run_cmd(["chown", "-R", "klipper:klipper", "/home/klipper/printer_data"])

        self.tui.progress(
            "Yapilandirma",
            "Servisler yapilandiriliyor...\nKlipper, Moonraker",
            98,
        )
        # Servisleri enable et — chroot icinde symlink olusturur
        for svc in ["klipper", "moonraker"]:
            run_cmd(["systemctl", "enable", svc])
        # NOT: systemctl start chroot'ta systemd olmadigi icin atlanir.
        # Servisler ilk boot'ta otomatik baslar.

        return True

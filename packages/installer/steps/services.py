"""Adim 7: Servis yapilandirma."""
from __future__ import annotations

from ..tui import TUI
from ..utils.runner import run_cmd
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

        try:
            with open("/etc/nginx/sites-available/mainsail", "w") as f:
                f.write(NGINX_SITE)
            run_cmd(["ln", "-sf", "/etc/nginx/sites-available/mainsail",
                     "/etc/nginx/sites-enabled/mainsail"])
            run_cmd(["rm", "-f", "/etc/nginx/sites-enabled/default"])
            run_cmd(["systemctl", "enable", "nginx"])
            run_cmd(["systemctl", "restart", "nginx"])
        except OSError as e:
            logger.error("Nginx yapilandirilamadi: %s", e)

        dirs = [
            "/home/klipper/printer_data/config",
            "/home/klipper/printer_data/logs",
            "/home/klipper/printer_data/gcodes",
            "/home/klipper/printer_data/database",
        ]
        for d in dirs:
            run_cmd(["mkdir", "-p", d])
        run_cmd(["chown", "-R", "klipper:klipper", "/home/klipper/printer_data"])

        for svc in ["klipper", "moonraker"]:
            run_cmd(["systemctl", "start", svc])

        return True

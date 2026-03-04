"""Installer loglama."""
from __future__ import annotations

import logging
from pathlib import Path

LOG_FILE = "/var/log/kos-installer.log"


def get_logger(name: str = "kos-installer") -> logging.Logger:
    """Installer logger'i dondur.

    ONEMLI: Console handler YOK — tum ciktilar sadece dosyaya.
    StreamHandler whiptail TUI'yi bozar (TTY'ye yazdigi icin terminal
    kontrolunu kaybettirir ve whiptail menuleri goruntulenemez).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        # Sadece dosya handler — TTY'ye HICBIR sey yazma
        try:
            Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(LOG_FILE)
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
            logger.addHandler(fh)
        except OSError:
            pass  # /var/log yazilabilir degilse sessizce atla

        # Console handler YOK — whiptail TUI aktifken TTY'ye yazma!
        # Hata ayiklama: tail -f /var/log/kos-installer.log

    return logger

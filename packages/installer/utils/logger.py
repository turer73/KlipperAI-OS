"""Installer loglama."""
from __future__ import annotations

import logging
from pathlib import Path

LOG_FILE = "/var/log/kos-installer.log"


def get_logger(name: str = "kos-installer") -> logging.Logger:
    """Installer logger'i dondur."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        # Dosya handler
        try:
            Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(LOG_FILE)
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
            logger.addHandler(fh)
        except OSError:
            pass  # /var/log yazilabilir degilse sessizce atla

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ch)

    return logger

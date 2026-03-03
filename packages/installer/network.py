"""Ag baglanti yonetimi — nmcli wrapper."""
from __future__ import annotations

from .utils.runner import run_cmd
from .utils.logger import get_logger

logger = get_logger()


class NetworkManager:
    """WiFi ve internet baglanti yonetimi."""

    def check_internet(self) -> bool:
        """Internet baglantisi var mi?"""
        ok, _ = run_cmd(["ping", "-c", "1", "-W", "3", "1.1.1.1"])
        return ok

    def scan_wifi(self) -> list[tuple[str, int]]:
        """WiFi aglarini tara. [(ssid, sinyal_gucu), ...] dondur."""
        ok, output = run_cmd([
            "nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list",
        ])
        if not ok:
            return []

        networks: list[tuple[str, int]] = []
        for line in output.strip().split("\n"):
            if ":" not in line:
                continue
            parts = line.rsplit(":", 1)
            ssid = parts[0].strip()
            if not ssid:
                continue
            try:
                signal = int(parts[1].strip())
            except ValueError:
                signal = 0
            networks.append((ssid, signal))

        # Sinyal gucune gore sirala (yuksekten dusuge)
        networks.sort(key=lambda x: x[1], reverse=True)
        return networks

    def connect_wifi(self, ssid: str, password: str) -> bool:
        """WiFi agina baglan."""
        logger.info("WiFi baglaniyor: %s", ssid)
        ok, output = run_cmd([
            "nmcli", "dev", "wifi", "connect", ssid, "password", password,
        ])
        if ok:
            logger.info("WiFi baglandi: %s", ssid)
        else:
            logger.error("WiFi basarisiz: %s — %s", ssid, output[:100])
        return ok

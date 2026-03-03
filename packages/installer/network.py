"""Ag baglanti yonetimi — nmcli wrapper."""
from __future__ import annotations

import time

from .utils.runner import run_cmd
from .utils.logger import get_logger

logger = get_logger()


class NetworkManager:
    """WiFi ve internet baglanti yonetimi."""

    def check_internet(self) -> bool:
        """Internet baglantisi var mi? (ping yerine socket — iputils gerektirmez)."""
        import socket
        for host in ("1.1.1.1", "8.8.8.8"):
            try:
                sock = socket.create_connection((host, 53), timeout=3)
                sock.close()
                return True
            except OSError:
                continue
        return False

    def ensure_wifi_up(self) -> bool:
        """WiFi arayuzunun aktif oldugunu garanti et."""
        # nmcli radio wifi durumunu kontrol et
        ok, output = run_cmd(["nmcli", "radio", "wifi"])
        if ok and "enabled" in output.lower():
            return True

        # Kapali ise ac
        logger.info("WiFi radio aciliyor...")
        ok, _ = run_cmd(["nmcli", "radio", "wifi", "on"])
        if ok:
            time.sleep(2)  # Arayuzun aktif olmasini bekle
        return ok

    def scan_wifi(self) -> list[tuple[str, int]]:
        """WiFi aglarini tara. [(ssid, sinyal_gucu), ...] dondur."""
        # Once WiFi arayuzunun aktif oldugunu garanti et
        self.ensure_wifi_up()

        # Taze tarama zorla
        run_cmd(["nmcli", "dev", "wifi", "rescan"], timeout=10)
        time.sleep(2)

        ok, output = run_cmd([
            "nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list",
        ])
        if not ok:
            return []

        seen: set[str] = set()
        networks: list[tuple[str, int]] = []
        for line in output.strip().split("\n"):
            if ":" not in line:
                continue
            parts = line.rsplit(":", 1)
            ssid = parts[0].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
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

        # Onceki baglanti varsa kaldir
        run_cmd(["nmcli", "con", "delete", ssid], timeout=5)

        ok, output = run_cmd([
            "nmcli", "dev", "wifi", "connect", ssid, "password", password,
        ], timeout=30)
        if ok:
            logger.info("WiFi baglandi: %s", ssid)
            # Baglantiyi dogrulamak icin kisa bekle
            time.sleep(2)
        else:
            logger.error("WiFi basarisiz: %s — %s", ssid, output[:200])
        return ok

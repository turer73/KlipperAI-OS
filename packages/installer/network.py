"""Ag baglanti yonetimi — nmcli wrapper."""
from __future__ import annotations

import time
from pathlib import Path

from .utils.runner import run_cmd
from .utils.logger import get_logger

logger = get_logger()


class NetworkManager:
    """WiFi ve internet baglanti yonetimi."""

    # ------------------------------------------------------------------
    # Diagnostik yardimcilar
    # ------------------------------------------------------------------

    def _is_nm_running(self) -> bool:
        """NetworkManager servisi calisiyor mu?"""
        ok, _ = run_cmd(
            ["systemctl", "is-active", "--quiet", "NetworkManager"],
            timeout=5,
        )
        return ok

    def _start_nm(self) -> bool:
        """NetworkManager servisini baslat."""
        logger.info("NetworkManager baslatiliyor...")
        ok, _ = run_cmd(
            ["systemctl", "start", "NetworkManager"],
            timeout=15,
        )
        if ok:
            time.sleep(3)  # D-Bus baglantisi icin bekle
        return ok

    def _ensure_nm(self) -> bool:
        """NM calisiyor mu? Degilse baslat."""
        if self._is_nm_running():
            return True
        logger.warning("NetworkManager calismiyor, baslatiliyor...")
        if not self._start_nm():
            logger.error("NetworkManager baslatilamadi!")
            return False
        return self._is_nm_running()

    def _get_wifi_iface(self) -> str | None:
        """WiFi arayuz adini don, yoksa None."""
        net_dir = Path("/sys/class/net")
        if not net_dir.exists():
            return None
        for iface in net_dir.iterdir():
            if iface.name == "lo":
                continue
            if (iface / "wireless").is_dir():
                return iface.name
        return None

    # ------------------------------------------------------------------
    # Ana API
    # ------------------------------------------------------------------

    def check_internet(self) -> bool:
        """Internet baglantisi var mi? (socket — iputils gerektirmez)."""
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
        """WiFi radyosunun acik oldugunu garanti et."""
        # rfkill ile soft-block kaldir (bazi laptoplarda varsayilan bloklu)
        import shutil
        if shutil.which("rfkill"):
            run_cmd(["rfkill", "unblock", "wifi"], timeout=5)

        ok, output = run_cmd(["nmcli", "radio", "wifi"], timeout=10)
        if ok and "enabled" in output.lower():
            return True

        logger.info("WiFi radio aciliyor...")
        ok, _ = run_cmd(["nmcli", "radio", "wifi", "on"], timeout=10)
        if ok:
            time.sleep(2)
        return ok

    def scan_wifi(self) -> list[tuple[str, int]]:
        """WiFi aglarini tara. [(ssid, sinyal_gucu), ...] dondur."""
        # 1. NetworkManager calisiyor mu?
        if not self._ensure_nm():
            logger.error("NetworkManager yok — WiFi taranamaz")
            return []

        # 2. WiFi arayuzu var mi?
        wifi_iface = self._get_wifi_iface()
        if not wifi_iface:
            logger.error("WiFi arayuzu bulunamadi (/sys/class/net/*/wireless)")
            return []
        logger.info("WiFi arayuzu: %s", wifi_iface)

        # 3. WiFi radyosu ac + rfkill kaldir
        self.ensure_wifi_up()

        # 4. Taze tarama zorla
        run_cmd(["nmcli", "dev", "wifi", "rescan"], timeout=10)
        time.sleep(3)

        # 5. Ag listesi al (bos donerse bir kez daha dene)
        networks = self._parse_wifi_list()
        if not networks:
            logger.info("Ilk tarama bos — 3sn sonra tekrar deneniyor...")
            time.sleep(3)
            networks = self._parse_wifi_list()

        logger.info("WiFi tarama: %d ag bulundu", len(networks))
        return networks

    def _parse_wifi_list(self) -> list[tuple[str, int]]:
        """nmcli wifi list ciktisini parse et."""
        ok, output = run_cmd([
            "nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list",
        ], timeout=15)
        if not ok or not output.strip():
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
            time.sleep(2)
        else:
            logger.error("WiFi basarisiz: %s — %s", ssid, output[:200])
        return ok

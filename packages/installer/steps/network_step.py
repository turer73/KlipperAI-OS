"""Adim 3: Ag baglantisi."""
from __future__ import annotations

from ..tui import TUI
from ..network import NetworkManager as NetMgr
from ..hw_detect import HardwareInfo


class NetworkStep:
    def __init__(self, tui: TUI, hw_info: HardwareInfo):
        self.tui = tui
        self.hw_info = hw_info
        self.net = NetMgr()

    def run(self) -> bool:
        if self.net.check_internet():
            self.tui.msgbox("Ag Baglantisi", "Internet baglantisi mevcut. Devam ediliyor.")
            return True

        if not self.hw_info.has_wifi:
            self.tui.msgbox("Ag Baglantisi",
                            "WiFi algilanamadi. Ethernet kablo baglayin.\n"
                            "Kurulum icin internet gerekli.")
            return False

        networks = self.net.scan_wifi()
        if not networks:
            self.tui.msgbox("WiFi", "WiFi agi bulunamadi. Ethernet kablo baglayin.")
            return False

        items = [(str(i + 1), f"{ssid} ({signal}%)") for i, (ssid, signal) in enumerate(networks)]
        choice = self.tui.menu("WiFi Agi Secin", items, text="Baglanilacak agi secin:")

        try:
            idx = int(choice) - 1
            selected_ssid = networks[idx][0]
        except (ValueError, IndexError):
            return False

        password = self.tui.passwordbox(f"{selected_ssid} icin sifre:", title="WiFi Sifresi")

        if self.net.connect_wifi(selected_ssid, password):
            self.tui.msgbox("WiFi", f"Baglanti basarili: {selected_ssid}")
            return True
        else:
            self.tui.msgbox("WiFi Hatasi", "Baglanti basarisiz. Sifre yanlis olabilir.")
            return False

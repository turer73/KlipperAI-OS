"""Adim 3: Ag baglantisi — WiFi tarama, secim, parola, baglanti."""
from __future__ import annotations

from ..tui import TUI
from ..network import NetworkManager as NetMgr
from ..hw_detect import HardwareInfo


MAX_WIFI_RETRIES = 3


class NetworkStep:
    def __init__(self, tui: TUI, hw_info: HardwareInfo):
        self.tui = tui
        self.hw_info = hw_info
        self.net = NetMgr()

    def run(self) -> bool:
        """Ag baglantisi adimi. True=internet var, False=yok."""
        # WiFi varsa her zaman WiFi menusu goster
        if self.hw_info.has_wifi:
            return self._wifi_flow()

        # WiFi yoksa sadece Ethernet kontrol
        if self.net.check_internet():
            self.tui.msgbox(
                "Ag Baglantisi",
                "Ethernet ile internet baglantisi mevcut.\n\n"
                "Devam ediliyor...",
            )
            return True

        self.tui.msgbox(
            "Ag Baglantisi",
            "Internet baglantisi bulunamadi!\n\n"
            "WiFi algilanamadi.\n"
            "Lutfen Ethernet kablo baglayip\n"
            "kurulumu yeniden baslatin.",
        )
        return False

    def _wifi_flow(self) -> bool:
        """WiFi ag secimi ve baglanti akisi."""
        # Ethernet ile internet zaten varsa kullaniciya sor
        if self.net.check_internet():
            use_wifi = self.tui.yesno(
                "Internet baglantisi mevcut (Ethernet).\n\n"
                "WiFi agi de yapilandirmak ister misiniz?",
                title="Ag Baglantisi",
            )
            if not use_wifi:
                return True

        for attempt in range(1, MAX_WIFI_RETRIES + 1):
            # WiFi aglarini tara
            networks = self._scan_networks()
            if not networks:
                retry = self.tui.yesno(
                    "WiFi agi bulunamadi.\n\n"
                    "Tekrar taramak ister misiniz?",
                    title="WiFi Tarama",
                )
                if retry:
                    continue
                # Ethernet ile internet var mi son kontrol
                if self.net.check_internet():
                    return True
                return False

            # Ag secimi
            selected_ssid = self._select_network(networks)
            if selected_ssid is None:
                # Kullanici iptal etti — Ethernet varsa devam
                if self.net.check_internet():
                    return True
                return False

            # Parola girisi
            password = self.tui.passwordbox(
                f"\"{selected_ssid}\" agi icin WiFi sifresini girin:",
                title="WiFi Sifresi",
            )

            # Baglantiyi dene
            if self.net.connect_wifi(selected_ssid, password):
                # Internet erisilebilir mi?
                if self.net.check_internet():
                    self.tui.msgbox(
                        "WiFi Baglantisi",
                        f"Basariyla baglandi: {selected_ssid}\n\n"
                        "Internet baglantisi dogrulandi.",
                    )
                    return True
                else:
                    self.tui.msgbox(
                        "WiFi Baglantisi",
                        f"WiFi baglandi: {selected_ssid}\n"
                        "Ancak internet erisimi yok.\n\n"
                        "Ag ayarlarini kontrol edin.",
                    )
                    # Tekrar denesin mi?
                    if attempt < MAX_WIFI_RETRIES:
                        retry = self.tui.yesno(
                            "Farkli bir ag denemek ister misiniz?",
                            title="Tekrar Dene",
                        )
                        if not retry:
                            return False
                    continue
            else:
                # Baglanti basarisiz
                if attempt < MAX_WIFI_RETRIES:
                    retry = self.tui.yesno(
                        f"\"{selected_ssid}\" agina baglanilamadi.\n"
                        "Sifre yanlis olabilir.\n\n"
                        "Tekrar denemek ister misiniz?",
                        title="Baglanti Basarisiz",
                    )
                    if not retry:
                        if self.net.check_internet():
                            return True
                        return False
                else:
                    self.tui.msgbox(
                        "Baglanti Basarisiz",
                        "WiFi baglantisi kurulamadi.\n\n"
                        "Ethernet kablo baglayin veya\n"
                        "kurulumu yeniden baslatin.",
                    )
                    return False

        return self.net.check_internet()

    def _scan_networks(self) -> list[tuple[str, int]]:
        """WiFi aglarini tara, kullaniciya beklemesini soy."""
        self.tui.msgbox(
            "WiFi Tarama",
            "WiFi aglari taraniyor...\n\n"
            "Lutfen bekleyin.",
        )
        return self.net.scan_wifi()

    def _select_network(self, networks: list[tuple[str, int]]) -> str | None:
        """WiFi ag listesini goster, kullanicinin secmesini bekle."""
        items: list[tuple[str, str]] = []
        for i, (ssid, signal) in enumerate(networks):
            # Sinyal gosterge cubugu
            bars = self._signal_bars(signal)
            items.append((str(i + 1), f"{ssid}  {bars} {signal}%"))

        choice = self.tui.menu(
            "WiFi Agi Secin",
            items,
            text="Baglanmak istediginiz WiFi agini secin:",
        )

        try:
            idx = int(choice) - 1
            return networks[idx][0]
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _signal_bars(signal: int) -> str:
        """Sinyal gucunu gorsel cubuk olarak goster."""
        if signal >= 80:
            return "||||"
        if signal >= 60:
            return "|||."
        if signal >= 40:
            return "||.."
        if signal >= 20:
            return "|..."
        return "...."

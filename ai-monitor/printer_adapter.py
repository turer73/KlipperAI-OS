"""
KlipperOS-AI — Printer Control Abstraction Layer
=================================================
Klipper (Moonraker REST) ve Bambu (MQTT) yazıcıları
tek bir interface altında birleştirir.

MultiPrinterMonitor bu adapter'ları kullanarak
yazıcı tipinden bağımsız kontrol sağlar.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("klipperos-ai.adapter")


# ---------------------------------------------------------------------------
# Unified Status
# ---------------------------------------------------------------------------


@dataclass
class UnifiedPrinterStatus:
    """Yazıcı tipinden bağımsız durum bilgisi."""

    printer_type: str = ""  # "klipper" veya "bambu"
    printer_name: str = ""
    is_printing: bool = False
    state: str = "idle"  # idle, printing, paused, error, complete
    progress_percent: float = 0.0
    nozzle_temp: float = 0.0
    nozzle_target: float = 0.0
    bed_temp: float = 0.0
    bed_target: float = 0.0
    current_layer: int = 0
    total_layers: int = 0
    filename: str = ""
    remaining_minutes: int = 0
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Abstract Printer Adapter
# ---------------------------------------------------------------------------


class PrinterAdapter(ABC):
    """Yazıcı kontrol soyut arayüzü.

    Hem Klipper (Moonraker REST) hem Bambu (MQTT) yazıcılar
    bu interface'i implemente eder.
    """

    @property
    @abstractmethod
    def printer_type(self) -> str:
        """Yazıcı tipi: 'klipper' veya 'bambu'."""
        ...

    @property
    @abstractmethod
    def printer_name(self) -> str:
        """Yazıcı görüntü adı."""
        ...

    @abstractmethod
    def is_printing(self) -> bool:
        """Yazıcı aktif baskı yapıyor mu?"""
        ...

    @abstractmethod
    def pause_print(self) -> bool:
        """Baskıyı duraklat. Başarılıysa True."""
        ...

    @abstractmethod
    def resume_print(self) -> bool:
        """Baskıya devam et. Başarılıysa True."""
        ...

    @abstractmethod
    def get_status(self) -> UnifiedPrinterStatus:
        """Güncel yazıcı durumunu al."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Yazıcıya erişilebilir mi?"""
        ...


# ---------------------------------------------------------------------------
# Klipper Adapter (Moonraker REST API)
# ---------------------------------------------------------------------------


class KlipperAdapter(PrinterAdapter):
    """Klipper/Moonraker yazıcı kontrolü — print_monitor.py MoonrakerClient sarmalayıcı."""

    def __init__(self, moonraker_url: str = "http://127.0.0.1:7125", name: str = "klipper-1"):
        self._url = moonraker_url.rstrip("/")
        self._name = name

        import requests
        self._session = requests.Session()
        self._session.timeout = 5

    @property
    def printer_type(self) -> str:
        return "klipper"

    @property
    def printer_name(self) -> str:
        return self._name

    def is_printing(self) -> bool:
        status = self._query_objects("print_stats")
        return status.get("print_stats", {}).get("state") == "printing"

    def pause_print(self) -> bool:
        try:
            resp = self._session.post(f"{self._url}/printer/print/pause")
            resp.raise_for_status()
            logger.warning("Klipper baskı duraklatıldı: %s", self._name)
            return True
        except Exception as exc:
            logger.error("Klipper pause hatası: %s", exc)
            return False

    def resume_print(self) -> bool:
        try:
            resp = self._session.post(f"{self._url}/printer/print/resume")
            resp.raise_for_status()
            logger.info("Klipper baskıya devam: %s", self._name)
            return True
        except Exception as exc:
            logger.error("Klipper resume hatası: %s", exc)
            return False

    def get_status(self) -> UnifiedPrinterStatus:
        objs = self._query_objects(
            "print_stats", "extruder", "heater_bed", "virtual_sdcard"
        )
        ps = objs.get("print_stats", {})
        ext = objs.get("extruder", {})
        bed = objs.get("heater_bed", {})
        vsd = objs.get("virtual_sdcard", {})

        state_map = {
            "standby": "idle",
            "printing": "printing",
            "paused": "paused",
            "complete": "complete",
            "error": "error",
        }

        return UnifiedPrinterStatus(
            printer_type="klipper",
            printer_name=self._name,
            is_printing=ps.get("state") == "printing",
            state=state_map.get(ps.get("state", "standby"), "idle"),
            progress_percent=round(vsd.get("progress", 0.0) * 100, 1),
            nozzle_temp=ext.get("temperature", 0.0),
            nozzle_target=ext.get("target", 0.0),
            bed_temp=bed.get("temperature", 0.0),
            bed_target=bed.get("target", 0.0),
            filename=ps.get("filename", ""),
        )

    def is_available(self) -> bool:
        try:
            resp = self._session.get(f"{self._url}/server/info", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def _query_objects(self, *objects: str) -> dict:
        """Moonraker printer objects query."""
        try:
            params = {obj: "" for obj in objects}
            resp = self._session.get(
                f"{self._url}/printer/objects/query",
                params=params,
            )
            resp.raise_for_status()
            return resp.json().get("result", {}).get("status", {})
        except Exception as exc:
            logger.debug("Klipper query hatası: %s", exc)
            return {}


# ---------------------------------------------------------------------------
# Bambu Adapter (MQTT)
# ---------------------------------------------------------------------------


class BambuAdapter(PrinterAdapter):
    """Bambu Lab yazıcı kontrolü — BambuMQTTClient sarmalayıcı."""

    # Bambu gcode_state → unified state mapping
    STATE_MAP = {
        "IDLE": "idle",
        "RUNNING": "printing",
        "PAUSE": "paused",
        "FINISH": "complete",
        "FAILED": "error",
        "PREPARE": "printing",
        "SLICING": "printing",
    }

    # Reconnect cooldown: basarisiz baglanti denemesinden sonra minimum bekleme
    RECONNECT_COOLDOWN = 60  # saniye

    def __init__(
        self,
        hostname: str,
        access_code: str,
        serial: str,
        name: str = "bambu-1",
    ):
        self._hostname = hostname
        self._access_code = access_code
        self._serial = serial
        self._name = name
        self._mqtt = None  # Lazy init
        self._last_connect_attempt: float = 0
        self._connect_failures: int = 0

    def _ensure_mqtt(self):
        """MQTT client'ı gerektiğinde oluştur ve bağlan.

        FD sızıntısını önlemek için:
        - Eski client'ı düzgün disconnect et
        - Başarısız denemeler arasında cooldown uygula
        - Cooldown süresini her başarısızlıkta artır (max 5dk)
        """
        if self._mqtt is not None and self._mqtt.is_connected:
            return

        # Cooldown kontrolü — çok sık bağlantı denemesini engelle
        now = time.time()
        cooldown = min(self.RECONNECT_COOLDOWN * (2 ** min(self._connect_failures, 3)), 300)
        if now - self._last_connect_attempt < cooldown:
            return

        self._last_connect_attempt = now

        # Eski client'ı temizle (FD sızıntısı önleme)
        if self._mqtt is not None:
            try:
                self._mqtt.disconnect()
            except Exception:
                pass
            self._mqtt = None

        try:
            from bambu_client import BambuMQTTClient
        except ImportError:
            from .bambu_client import BambuMQTTClient

        self._mqtt = BambuMQTTClient(
            hostname=self._hostname,
            access_code=self._access_code,
            serial=self._serial,
        )
        connected = self._mqtt.connect()
        if connected:
            self._connect_failures = 0
            logger.info("Bambu MQTT baglandi: %s", self._name)
        else:
            self._connect_failures += 1
            cooldown_next = min(self.RECONNECT_COOLDOWN * (2 ** min(self._connect_failures, 3)), 300)
            logger.warning(
                "Bambu MQTT baglanti basarisiz (%s), deneme #%d, sonraki deneme: %ds",
                self._name, self._connect_failures, cooldown_next,
            )

    @property
    def printer_type(self) -> str:
        return "bambu"

    @property
    def printer_name(self) -> str:
        return self._name

    def is_printing(self) -> bool:
        self._ensure_mqtt()
        status = self._mqtt.get_status() if self._mqtt else None
        if status is None:
            return False
        return status.gcode_state in ("RUNNING", "PREPARE", "SLICING")

    def pause_print(self) -> bool:
        self._ensure_mqtt()
        if self._mqtt is None:
            return False
        return self._mqtt.pause_print()

    def resume_print(self) -> bool:
        self._ensure_mqtt()
        if self._mqtt is None:
            return False
        return self._mqtt.resume_print()

    def get_status(self) -> UnifiedPrinterStatus:
        self._ensure_mqtt()
        status = self._mqtt.get_status() if self._mqtt else None

        if status is None:
            return UnifiedPrinterStatus(
                printer_type="bambu",
                printer_name=self._name,
                state="idle",
            )

        return UnifiedPrinterStatus(
            printer_type="bambu",
            printer_name=self._name,
            is_printing=status.gcode_state in ("RUNNING", "PREPARE", "SLICING"),
            state=self.STATE_MAP.get(status.gcode_state, "idle"),
            progress_percent=float(status.mc_percent),
            nozzle_temp=status.nozzle_temper,
            nozzle_target=status.nozzle_target_temper,
            bed_temp=status.bed_temper,
            bed_target=status.bed_target_temper,
            current_layer=status.layer_num,
            total_layers=status.total_layer_num,
            filename=status.gcode_file,
            remaining_minutes=status.mc_remaining_time,
        )

    def is_available(self) -> bool:
        self._ensure_mqtt()
        return self._mqtt is not None and self._mqtt.is_connected

    def disconnect(self) -> None:
        """MQTT bağlantısını kapat."""
        if self._mqtt is not None:
            self._mqtt.disconnect()
            self._mqtt = None

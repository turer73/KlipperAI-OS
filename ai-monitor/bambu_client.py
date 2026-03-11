"""
KlipperOS-AI — Bambu Lab Printer Client
========================================
Bambu Lab yazıcılar için minimal protokol client.
TLS kamera stream (port 6000) ve MQTT durum/komut (port 8883).

bambu-connect kütüphanesine bağımlılık yok — kendi implementasyonumuz.
Protokol bilgisi: https://github.com/mattcar15/bambu-connect
"""

import io
import json
import logging
import select
import socket
import ssl
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("klipperos-ai.bambu")

# ---------------------------------------------------------------------------
# Bambu Printer Status (MQTT report verisi)
# ---------------------------------------------------------------------------


@dataclass
class BambuPrinterStatus:
    """Bambu Lab yazıcı durumu — MQTT report mesajından parse edilir."""

    gcode_state: str = "IDLE"  # IDLE, RUNNING, PAUSE, FINISH, FAILED
    mc_percent: int = 0  # baskı ilerleme %0-100
    nozzle_temper: float = 0.0
    nozzle_target_temper: float = 0.0
    bed_temper: float = 0.0
    bed_target_temper: float = 0.0
    chamber_temper: float = 0.0
    layer_num: int = 0
    total_layer_num: int = 0
    gcode_file: str = ""
    mc_remaining_time: int = 0  # dakika
    wifi_signal: str = ""
    print_error: int = 0
    timestamp: float = field(default_factory=time.time)

    # MQTT report → dataclass alan eşlemesi
    _FIELD_MAP = {
        "gcode_state": "gcode_state",
        "mc_percent": "mc_percent",
        "nozzle_temper": "nozzle_temper",
        "nozzle_target_temper": "nozzle_target_temper",
        "bed_temper": "bed_temper",
        "bed_target_temper": "bed_target_temper",
        "chamber_temper": "chamber_temper",
        "layer_num": "layer_num",
        "total_layer_num": "total_layer_num",
        "gcode_file": "gcode_file",
        "mc_remaining_time": "mc_remaining_time",
        "wifi_signal": "wifi_signal",
        "print_error": "print_error",
    }

    @classmethod
    def from_mqtt_report(cls, data: dict) -> "BambuPrinterStatus":
        """MQTT report JSON'dan BambuPrinterStatus oluştur (ilk tam mesaj için)."""
        p = data.get("print", {})
        return cls(
            gcode_state=p.get("gcode_state", "IDLE"),
            mc_percent=p.get("mc_percent", 0),
            nozzle_temper=p.get("nozzle_temper", 0.0),
            nozzle_target_temper=p.get("nozzle_target_temper", 0.0),
            bed_temper=p.get("bed_temper", 0.0),
            bed_target_temper=p.get("bed_target_temper", 0.0),
            chamber_temper=p.get("chamber_temper", 0.0),
            layer_num=p.get("layer_num", 0),
            total_layer_num=p.get("total_layer_num", 0),
            gcode_file=p.get("gcode_file", ""),
            mc_remaining_time=p.get("mc_remaining_time", 0),
            wifi_signal=p.get("wifi_signal", ""),
            print_error=p.get("print_error", 0),
            timestamp=time.time(),
        )

    def merge_update(self, data: dict) -> None:
        """Incremental MQTT mesajını mevcut duruma birleştir.

        Bambu yazıcılar her push_status'ta sadece değişen alanları gönderir.
        Bu metod yalnızca mesajda bulunan alanları günceller, geri kalanlar
        önceki değerlerini korur.
        """
        p = data.get("print", {})
        for mqtt_key, attr_name in self._FIELD_MAP.items():
            if mqtt_key in p:
                setattr(self, attr_name, p[mqtt_key])
        self.timestamp = time.time()


# ---------------------------------------------------------------------------
# Bambu Camera Stream (TLS port 6000)
# ---------------------------------------------------------------------------

# JPEG marker'lar
JPEG_SOI = b"\xff\xd8\xff\xe0"  # Start of Image + APP0
JPEG_EOI = b"\xff\xd9"  # End of Image

# Auth paketi yapısı (bambu-connect CameraClient'tan)
AUTH_PACKET_SIZE = 80  # 4+4+8+32+32 bytes


class BambuCameraStream:
    """Bambu Lab kamera TLS stream client (port 6000).

    Protokol:
    1. TLS bağlantısı (self-signed cert, doğrulama yok)
    2. Binary auth paketi gönder (username + access_code)
    3. Sürekli JPEG stream al (SOI/EOI delimiter ile)
    """

    def __init__(
        self,
        hostname: str,
        access_code: str,
        port: int = 6000,
        read_timeout: float = 10.0,
    ):
        self.hostname = hostname
        self.access_code = access_code
        self.port = port
        self.read_timeout = read_timeout

        self._sock: Optional[ssl.SSLSocket] = None
        self._lock = threading.Lock()
        self._connected = False
        self._buffer = bytearray()

    def connect(self) -> bool:
        """TLS bağlantısı kur ve auth paketi gönder."""
        with self._lock:
            try:
                self.disconnect()

                # TLS context — Bambu self-signed cert kullanır
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                raw_sock.settimeout(self.read_timeout)
                raw_sock.connect((self.hostname, self.port))

                self._sock = ctx.wrap_socket(raw_sock, server_hostname=self.hostname)

                # Auth paketi oluştur ve gönder
                auth_packet = self._build_auth_packet()
                self._sock.sendall(auth_packet)

                self._connected = True
                self._buffer.clear()
                logger.info(
                    "Bambu kamera bağlandı: %s:%d", self.hostname, self.port
                )
                return True

            except (socket.error, ssl.SSLError, OSError) as exc:
                logger.error("Bambu kamera bağlantı hatası: %s", exc)
                self._cleanup_socket()
                return False

    def _build_auth_packet(self) -> bytes:
        """Binary auth paketi oluştur.

        Format:
        - 4 bytes: 0x40 (little-endian uint32)
        - 4 bytes: 0x3000 (little-endian uint32)
        - 8 bytes: sıfır padding
        - 32 bytes: username ("bblp", null-padded)
        - 32 bytes: access_code (null-padded)
        """
        packet = bytearray(AUTH_PACKET_SIZE)
        struct.pack_into("<I", packet, 0, 0x40)
        struct.pack_into("<I", packet, 4, 0x3000)
        # 8 bytes padding (zaten sıfır)

        username = b"bblp"
        packet[16 : 16 + len(username)] = username

        code = self.access_code.encode("utf-8")[:32]
        packet[48 : 48 + len(code)] = code

        return bytes(packet)

    def read_frame(self) -> Optional[bytes]:
        """Bir JPEG frame oku ve raw bytes olarak döndür.

        Returns:
            JPEG bytes veya None (hata/timeout durumunda)
        """
        if not self._connected or self._sock is None:
            if not self.connect():
                return None

        try:
            return self._read_jpeg_frame()
        except (socket.timeout, socket.error, ssl.SSLError, OSError) as exc:
            logger.warning("Bambu kamera okuma hatası: %s", exc)
            self._connected = False
            return None

    def read_latest_frame(self) -> Optional[bytes]:
        """Buffer'ı drain edip en son (en güncel) JPEG frame'i döndür.

        read_frame() en eski frame'i döndürür ve gecikmeye neden olur.
        Bu metod:
        1. Socket'teki tüm bekleyen veriyi non-blocking okur (drain)
        2. Buffer'daki tüm JPEG frame'leri parse eder
        3. Sadece son (en güncel) frame'i döndürür
        4. Buffer'da frame yoksa blocking read_frame()'e fallback yapar

        Returns:
            En güncel JPEG bytes veya None (hata/timeout durumunda)
        """
        if not self._connected or self._sock is None:
            if not self.connect():
                return None

        try:
            # 1) Socket'teki tüm bekleyen veriyi drain et
            self._drain_socket()

            # 2) Buffer'daki tüm JPEG frame'leri çıkar, sadece sonuncuyu tut
            latest_frame = self._extract_latest_frame()

            if latest_frame is not None:
                return latest_frame

            # 3) Buffer'da hazır frame yok — blocking read ile bir tane al
            return self._read_jpeg_frame()

        except (socket.timeout, socket.error, ssl.SSLError, OSError) as exc:
            logger.warning("Bambu kamera okuma hatası: %s", exc)
            self._connected = False
            return None

    def _drain_socket(self) -> None:
        """Socket'teki tüm bekleyen veriyi non-blocking oku ve buffer'a ekle."""
        if self._sock is None:
            return

        chunk_size = 65536  # Büyük chunk — drain hızlı olsun
        max_drain = 10 * 1024 * 1024  # Güvenlik: max 10MB drain
        total_drained = 0

        while total_drained < max_drain:
            # select() ile veri var mı kontrol et (timeout=0 → non-blocking)
            try:
                readable, _, _ = select.select([self._sock], [], [], 0)
            except (ValueError, OSError):
                # Socket kapalı
                break

            if not readable:
                # Okunacak veri kalmadı
                break

            try:
                data = self._sock.recv(chunk_size)
                if not data:
                    self._connected = False
                    break
                self._buffer.extend(data)
                total_drained += len(data)
            except (socket.timeout, BlockingIOError):
                break
            except (socket.error, ssl.SSLError, OSError):
                self._connected = False
                break

        if total_drained > 0:
            logger.debug(
                "Bambu kamera buffer drain: %d KB okundu, buffer: %d KB",
                total_drained // 1024,
                len(self._buffer) // 1024,
            )

    def _extract_latest_frame(self) -> Optional[bytes]:
        """Buffer'daki tüm tam JPEG frame'leri parse et, sadece sonuncuyu döndür.

        Tüm eski frame'ler atılır — sadece en güncel frame döner.
        """
        latest = None

        while True:
            soi_pos = self._buffer.find(JPEG_SOI)
            if soi_pos < 0:
                break

            # SOI öncesi çöpü at
            if soi_pos > 0:
                del self._buffer[:soi_pos]

            # EOI ara
            eoi_pos = self._buffer.find(JPEG_EOI, len(JPEG_SOI))
            if eoi_pos < 0:
                # Tam frame yok — yarım frame buffer'da kalsın
                break

            # Tam frame bulundu
            frame_end = eoi_pos + len(JPEG_EOI)
            latest = bytes(self._buffer[:frame_end])
            del self._buffer[:frame_end]

        return latest

    def _read_jpeg_frame(self) -> Optional[bytes]:
        """Buffer'dan tam bir JPEG frame ayıkla."""
        chunk_size = 4096
        max_frame_size = 2 * 1024 * 1024  # 2MB max frame

        while True:
            # SOI marker ara
            soi_pos = self._buffer.find(JPEG_SOI)
            if soi_pos > 0:
                # SOI öncesi çöpü at
                del self._buffer[:soi_pos]
                soi_pos = 0

            if soi_pos >= 0:
                # EOI marker ara (SOI'den sonra)
                eoi_pos = self._buffer.find(JPEG_EOI, soi_pos + len(JPEG_SOI))
                if eoi_pos >= 0:
                    # Tam frame bulundu
                    frame_end = eoi_pos + len(JPEG_EOI)
                    frame = bytes(self._buffer[soi_pos:frame_end])
                    del self._buffer[:frame_end]
                    return frame

            # Buffer taşma koruması
            if len(self._buffer) > max_frame_size:
                logger.warning("Bambu kamera buffer taşması, temizleniyor")
                self._buffer.clear()
                return None

            # Daha fazla veri oku
            data = self._sock.recv(chunk_size)
            if not data:
                logger.warning("Bambu kamera bağlantısı kapandı")
                self._connected = False
                return None

            self._buffer.extend(data)

    def disconnect(self) -> None:
        """Bağlantıyı kapat."""
        self._connected = False
        self._cleanup_socket()

    def _cleanup_socket(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    @property
    def is_connected(self) -> bool:
        return self._connected


# ---------------------------------------------------------------------------
# Bambu MQTT Client (port 8883)
# ---------------------------------------------------------------------------


class BambuMQTTClient:
    """Bambu Lab yazıcı MQTT client — durum izleme ve komut gönderme.

    Subscribe: device/{serial}/report  → yazıcı durum güncellemeleri
    Publish:   device/{serial}/request → komutlar (pause, resume, gcode)
    """

    MQTT_USERNAME = "bblp"

    def __init__(
        self,
        hostname: str,
        access_code: str,
        serial: str,
        port: int = 8883,
    ):
        self.hostname = hostname
        self.access_code = access_code
        self.serial = serial
        self.port = port

        self._client = None  # paho.mqtt.client.Client (lazy import)
        self._connected = False
        self._status_lock = threading.Lock()
        self._last_status: Optional[BambuPrinterStatus] = None
        self._seq_id = 0
        self._on_status_callback: Optional[Callable] = None
        self._pushall_interval = 60  # saniye — periyodik tam durum isteği
        self._last_pushall_time: float = 0
        self._pushall_timer: Optional[threading.Timer] = None

    def connect(self, on_status: Optional[Callable] = None) -> bool:
        """MQTT broker'a bağlan ve report topic'ine subscribe ol.

        Args:
            on_status: Her durum güncellemesinde çağrılacak callback
                       (BambuPrinterStatus) -> None
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt kurulu değil: pip install paho-mqtt>=1.6")
            return False

        self._on_status_callback = on_status

        try:
            # paho-mqtt 2.x uyumlu client oluşturma
            import random
            import string
            suffix = "".join(random.choices(string.hexdigits[:16], k=8))
            client_id = f"kos_{self.serial[-6:]}_{suffix}"

            try:
                # paho-mqtt >= 2.0
                self._client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                    client_id=client_id,
                    protocol=mqtt.MQTTv311,
                )
            except (AttributeError, TypeError):
                # paho-mqtt < 2.0 fallback
                self._client = mqtt.Client(
                    client_id=client_id,
                    protocol=mqtt.MQTTv311,
                )

            self._client.username_pw_set(self.MQTT_USERNAME, self.access_code)

            # TLS — self-signed cert, doğrulama yok
            self._client.tls_set(cert_reqs=ssl.CERT_NONE)
            self._client.tls_insecure_set(True)

            # Callback'ler
            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message
            self._client.on_disconnect = self._on_disconnect

            # Reconnect ayarı
            self._client.reconnect_delay_set(min_delay=2, max_delay=60)

            self._client.connect(self.hostname, self.port, keepalive=30)
            self._client.loop_start()

            # Bağlantı için kısa bekleme
            deadline = time.time() + 10
            while not self._connected and time.time() < deadline:
                time.sleep(0.2)

            if self._connected:
                logger.info(
                    "Bambu MQTT bağlandı: %s (serial: %s)",
                    self.hostname,
                    self.serial,
                )
            else:
                logger.warning(
                    "Bambu MQTT bağlantı zaman aşımı: %s", self.hostname
                )

            return self._connected

        except Exception as exc:
            logger.error("Bambu MQTT bağlantı hatası: %s", exc)
            return False

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            topic = f"device/{self.serial}/report"
            client.subscribe(topic)
            logger.debug("Bambu MQTT subscribe: %s", topic)

            # İlk bağlantıda full status iste
            self._request_full_status()
            # Periyodik pushall timer'ını başlat
            self._schedule_pushall()
        else:
            rc_messages = {
                1: "Protokol versiyonu desteklenmiyor",
                2: "Client ID gecersiz",
                3: "Sunucu kullanilamiyor",
                4: "Kullanici/sifre hatali",
                5: "Yetki yok — access_code veya LAN-only modu kontrol edin",
            }
            msg = rc_messages.get(rc, f"Bilinmeyen hata")
            logger.error("Bambu MQTT baglanti reddedildi (rc=%d): %s", rc, msg)
            self._connected = False

            # rc=4,5: Auth hatasi — paho reconnect'i durdur (sureki deneme anlamsiz)
            if rc in (4, 5):
                logger.warning(
                    "Bambu MQTT auth hatasi kalici — otomatik reconnect durduruluyor. "
                    "Yazicida LAN-only modu aktif mi? Access code dogru mu?"
                )
                try:
                    client.loop_stop()
                    client.disconnect()
                except Exception:
                    pass

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            if "print" in data:
                with self._status_lock:
                    if self._last_status is None:
                        # İlk mesaj — tam obje oluştur
                        self._last_status = BambuPrinterStatus.from_mqtt_report(data)
                    else:
                        # Sonraki mesajlar — sadece gelen alanları birleştir
                        self._last_status.merge_update(data)
                    status = self._last_status
                if self._on_status_callback:
                    try:
                        self._on_status_callback(status)
                    except Exception as exc:
                        logger.debug("Status callback hatası: %s", exc)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.debug("Bambu MQTT mesaj parse hatası: %s", exc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            logger.warning("Bambu MQTT bağlantı koptu: rc=%d", rc)

    def _request_full_status(self) -> None:
        """pushall komutu ile tüm durumu iste."""
        if not self._connected or self._client is None:
            return
        payload = {
            "pushing": {
                "sequence_id": str(self._next_seq()),
                "command": "pushall",
            }
        }
        topic = f"device/{self.serial}/request"
        try:
            self._client.publish(topic, json.dumps(payload))
            self._last_pushall_time = time.time()
            logger.debug("Bambu pushall gönderildi: %s", self.serial)
        except Exception as exc:
            logger.debug("Bambu pushall gönderilemedi: %s", exc)

    def _schedule_pushall(self) -> None:
        """Periyodik pushall timer'ı planla."""
        self._cancel_pushall_timer()
        if self._connected:
            self._pushall_timer = threading.Timer(
                self._pushall_interval, self._periodic_pushall
            )
            self._pushall_timer.daemon = True
            self._pushall_timer.start()

    def _periodic_pushall(self) -> None:
        """Timer callback — full status iste ve sonraki timer'ı planla."""
        if self._connected:
            self._request_full_status()
            self._schedule_pushall()

    def _cancel_pushall_timer(self) -> None:
        """Aktif pushall timer'ını iptal et."""
        if self._pushall_timer is not None:
            self._pushall_timer.cancel()
            self._pushall_timer = None

    def _next_seq(self) -> int:
        self._seq_id += 1
        return self._seq_id

    def get_status(self) -> Optional[BambuPrinterStatus]:
        """En son alınan yazıcı durumunu döndür."""
        with self._status_lock:
            return self._last_status

    def send_command(self, command: dict) -> bool:
        """Bambu yazıcıya MQTT komutu gönder."""
        if not self._connected or self._client is None:
            logger.warning("Bambu MQTT bağlı değil, komut gönderilemedi")
            return False
        try:
            topic = f"device/{self.serial}/request"
            result = self._client.publish(topic, json.dumps(command))
            return result.rc == 0
        except Exception as exc:
            logger.error("Bambu MQTT komut gönderme hatası: %s", exc)
            return False

    def pause_print(self) -> bool:
        """Baskıyı duraklat."""
        cmd = {
            "print": {
                "command": "pause",
                "sequence_id": str(self._next_seq()),
            }
        }
        logger.warning("Bambu baskı duraklatılıyor: %s", self.hostname)
        return self.send_command(cmd)

    def resume_print(self) -> bool:
        """Baskıya devam et."""
        cmd = {
            "print": {
                "command": "resume",
                "sequence_id": str(self._next_seq()),
            }
        }
        logger.info("Bambu baskıya devam ediliyor: %s", self.hostname)
        return self.send_command(cmd)

    def send_gcode(self, gcode_line: str) -> bool:
        """G-code komutu gönder."""
        cmd = {
            "print": {
                "command": "gcode_line",
                "sequence_id": str(self._next_seq()),
                "param": gcode_line + "\n",
            }
        }
        return self.send_command(cmd)

    def disconnect(self) -> None:
        """MQTT bağlantısını kapat."""
        self._connected = False
        self._cancel_pushall_timer()
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    @property
    def is_connected(self) -> bool:
        return self._connected

"""
KlipperOS-AI — Multi-Printer AI Monitor Daemon
================================================
Birden fazla yazıcıyı (Klipper + Bambu Lab) eş zamanlı izler.
Tek SpaghettiDetector ONNX modeli paylaşılır, her yazıcı ayrı thread'de çalışır.

Systemd servisi olarak çalışır:
    systemctl start kos-bambu-monitor

Mevcut klipperos-ai-monitor (tek yazıcı) servisiyle çakışmaz —
ayrı daemon olarak çalışır.
"""

import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger("klipperos-ai.multi")

# Dual-import pattern (standalone + package uyumu)
try:
    from bambu_client import BambuMQTTClient
    from bambu_config import BambuConfig
    from bambu_frame_capture import BambuFrameCapture
    from frame_capture import FrameCapture
    from flow_guard import FlowGuard, FlowSignal, FlowVerdict
    from notification_manager import NotificationManager
    from printer_adapter import (
        BambuAdapter,
        KlipperAdapter,
        PrinterAdapter,
        UnifiedPrinterStatus,
    )
    from spaghetti_detect import SpaghettiDetector
except ImportError:
    from .bambu_client import BambuMQTTClient
    from .bambu_config import BambuConfig
    from .bambu_frame_capture import BambuFrameCapture
    from .frame_capture import FrameCapture
    from .flow_guard import FlowGuard, FlowSignal, FlowVerdict
    from .notification_manager import NotificationManager
    from .printer_adapter import (
        BambuAdapter,
        KlipperAdapter,
        PrinterAdapter,
        UnifiedPrinterStatus,
    )
    from .spaghetti_detect import SpaghettiDetector


# ---------------------------------------------------------------------------
# Per-Printer Monitor Thread
# ---------------------------------------------------------------------------


class PrinterMonitorThread:
    """Tek yazıcı için AI izleme döngüsü (thread içinde çalışır)."""

    # Ardışık uyarı eşiği → duraklat
    CONSECUTIVE_ALERTS_TO_PAUSE = 3
    RESTART_TOLERANCE_SECS = 60  # Yeniden baslatma sonrasi tolerans suresi (saniye)
    PAUSE_ENABLED = False  # True = otomatik duraklat, False = sadece uyari mesaji

    def __init__(
        self,
        printer: PrinterAdapter,
        frame_capture,
        detector: SpaghettiDetector,
        check_interval: int = 10,
        notifier: Optional[NotificationManager] = None,
    ):
        self.printer = printer
        self.capture = frame_capture
        self.detector = detector
        self.check_interval = check_interval
        self.notifier = notifier

        self.flow_guard = FlowGuard()
        self._stop_event = threading.Event()
        self._detect_lock = threading.Lock()  # TFLite backend thread-safe değilse

        # İstatistikler
        self._last_detection: dict = {}
        self._last_frame_jpeg: Optional[bytes] = None
        self._cycle_count: int = 0
        self._error_count: int = 0
        self._consecutive_alerts: int = 0
        self._start_time: float = time.time()  # warmup tolerans icin

    def run(self) -> None:
        """Ana izleme döngüsü (thread'den çağrılır, blocking)."""
        name = self.printer.printer_name
        ptype = self.printer.printer_type
        logger.info("[%s] Yazıcı izleme başladı (tip: %s, aralık: %ds)",
                     name, ptype, self.check_interval)

        while not self._stop_event.is_set():
            try:
                self._check_cycle()
            except Exception as exc:
                logger.error("[%s] İzleme döngüsü hatası: %s", name, exc)
                self._error_count += 1

            self._stop_event.wait(self.check_interval)

        logger.info("[%s] Yazıcı izleme durduruldu", name)

    def _check_cycle(self) -> None:
        """Tek bir izleme döngüsü — frame yakala, AI analiz, aksiyon al."""
        name = self.printer.printer_name
        self._cycle_count += 1

        # Kamera snapshot — baskı durumundan bağımsız (her 3 cycle ≈ 30s)
        # Dashboard'da canlı kamera görüntüsü için
        if self._cycle_count % 3 == 0:
            self._try_snapshot()

        # 1. Yazıcı baskı yapıyor mu kontrol et
        if not self.printer.is_printing():
            self._consecutive_alerts = 0
            return

        # 2. Frame yakala (AI analiz için — 224x224 numpy)
        frame = self.capture.capture()
        if frame is None:
            logger.debug("[%s] Frame yakalanamadı", name)
            return

        # Snapshot endpoint için JPEG önbelleği
        if hasattr(self.capture, "last_jpeg"):
            self._last_frame_jpeg = self.capture.last_jpeg

        # 3. AI tespit (thread-safe)
        with self._detect_lock:
            result = self.detector.detect(frame)

        self._last_detection = {
            **result,
            "printer_id": getattr(self.printer, "_name", name),
            "printer_type": self.printer.printer_type,
            "timestamp": time.time(),
        }

        detected_class = result.get("class", "unknown")
        confidence = result.get("confidence", 0.0)
        action = result.get("action", "none")

        logger.info(
            "[%s] AI tespit: %s (güven: %.1f%%, aksiyon: %s)",
            name, detected_class, confidence * 100, action,
        )

        # 4. FlowGuard değerlendirme
        # Bambu yazıcılar: sadece kamera katmanı aktif (L1-L3 = UNAVAILABLE)
        if self.printer.printer_type == "bambu":
            signals = [
                FlowSignal.UNAVAILABLE,  # L1: filament sensör
                FlowSignal.UNAVAILABLE,  # L2: heater duty
                FlowSignal.UNAVAILABLE,  # L3: TMC StallGuard
                FlowSignal.ANOMALY if action in ("pause", "notify") else FlowSignal.OK,  # L4: AI kamera
            ]
        else:
            # Klipper: sadece kamera (diğer katmanlar print_monitor'da)
            signals = [
                FlowSignal.UNAVAILABLE,
                FlowSignal.UNAVAILABLE,
                FlowSignal.UNAVAILABLE,
                FlowSignal.ANOMALY if action in ("pause", "notify") else FlowSignal.OK,
            ]

        verdict = self.flow_guard.evaluate(signals)

        # 5. Aksiyon al
        self._handle_action(action, result, verdict)

    def _handle_action(self, action: str, result: dict, verdict) -> None:
        """AI ve FlowGuard sonucuna göre aksiyon al."""
        name = self.printer.printer_name

        # Restart tolerans suresi icinde aksiyon alma (log goster ama duraklama)
        elapsed = time.time() - self._start_time
        in_warmup = elapsed < self.RESTART_TOLERANCE_SECS
        if in_warmup and action in ("pause", "notify"):
            logger.info(
                "[%s] Warmup tolerans: %.0fs/%ds - aksiyon atlaniyor (%s)",
                name, elapsed, self.RESTART_TOLERANCE_SECS, action,
            )
            return


        if action in ("pause", "notify"):
            self._consecutive_alerts += 1
        else:
            self._consecutive_alerts = 0

        # Ardışık uyarı eşiği aşıldıysa → duraklat
        if action == "pause" and self._consecutive_alerts >= self.CONSECUTIVE_ALERTS_TO_PAUSE:
            detected_class = result.get("class", "unknown")
            confidence = result.get("confidence", 0.0)

            logger.warning(
                "[%s] %d ardışık uyarı — BASKI DURDURULUYOR (sebep: %s, güven: %.1f%%)",
                name, self._consecutive_alerts, detected_class, confidence * 100,
            )
            if self.PAUSE_ENABLED:
                self.printer.pause_print()
                logger.warning("[%s] Yazici DURAKLATILDI", name)
            else:
                logger.warning(
                    "[%s] UYARI: Durdurma kosulu olustu ama PAUSE_ENABLED=False (sebep: %s, guven: %.1f%%)",
                    name, detected_class, confidence * 100,
                )
            self._consecutive_alerts = 0

            # Bildirim gönder
            if self.notifier:
                msg = (
                    f"⚠️ {name}: Baskı duraklatıldı!\n"
                    f"Tespit: {detected_class} ({confidence:.0%})\n"
                    f"Yazıcı tipi: {self.printer.printer_type}"
                )
                try:
                    self.notifier.send_all(msg, severity="critical")
                except Exception:
                    pass

        elif action == "notify":
            if self.notifier and self._consecutive_alerts == 1:
                detected_class = result.get("class", "unknown")
                confidence = result.get("confidence", 0.0)
                msg = (
                    f"⚡ {name}: Baskı uyarısı\n"
                    f"Tespit: {detected_class} ({confidence:.0%})"
                )
                try:
                    self.notifier.send_all(msg, severity="warning")
                except Exception:
                    pass

    def _try_snapshot(self) -> None:
        """Kamera frame'ini güncelle — dashboard preview ve snapshot endpoint için.

        Baskı durumundan bağımsız çalışır. BambuCameraStream persistent
        connection kullandığı için TLS overhead minimize.
        """
        try:
            if hasattr(self.capture, "_stream"):
                # BambuFrameCapture — doğrudan stream'den raw JPEG al
                jpeg = self.capture._stream.read_frame()
                if jpeg:
                    self._last_frame_jpeg = jpeg
        except Exception:
            pass  # Snapshot hataları sessiz — kritik değil

    def stop(self) -> None:
        """İzleme döngüsünü durdur."""
        self._stop_event.set()

    @property
    def last_detection(self) -> dict:
        return self._last_detection.copy()

    @property
    def last_frame_jpeg(self) -> Optional[bytes]:
        return self._last_frame_jpeg

    @property
    def stats(self) -> dict:
        result = {
            "printer_name": self.printer.printer_name,
            "printer_type": self.printer.printer_type,
            "cycle_count": self._cycle_count,
            "error_count": self._error_count,
            "consecutive_alerts": self._consecutive_alerts,
            "capture_stats": self.capture.stats if hasattr(self.capture, "stats") else {},
            "is_printing": self.printer.is_printing(),
        }

        # MQTT durum verileri (sıcaklık, ilerleme, katman vb.)
        try:
            status = self.printer.get_status()
            if status:
                result["mqtt_status"] = {
                    "state": status.state,
                    "progress_percent": status.progress_percent,
                    "nozzle_temp": status.nozzle_temp,
                    "nozzle_target": status.nozzle_target,
                    "bed_temp": status.bed_temp,
                    "bed_target": status.bed_target,
                    "current_layer": status.current_layer,
                    "total_layers": status.total_layers,
                    "filename": status.filename,
                    "remaining_minutes": status.remaining_minutes,
                }
            result["mqtt_connected"] = self.printer.is_available()
        except Exception:
            result["mqtt_connected"] = False

        # Son AI tespit sonucu
        if self._last_detection:
            result["last_detection"] = self._last_detection

        return result


# ---------------------------------------------------------------------------
# Multi-Printer Monitor
# ---------------------------------------------------------------------------


class MultiPrinterMonitor:
    """Birden fazla yazıcı için AI izleme orkestratörü.

    - Tek SpaghettiDetector instance (ONNX, thread-safe)
    - Her yazıcı ayrı thread'de izlenir
    - Config'den Bambu yazıcılar otomatik yüklenir
    """

    STATUS_FILE = "/var/lib/klipperos-ai/bambu-monitor-status.json"

    def __init__(self):
        self._detector: Optional[SpaghettiDetector] = None
        self._threads: dict[str, tuple[PrinterMonitorThread, threading.Thread]] = {}
        self._running = False
        self._notifier: Optional[NotificationManager] = None

    def start(self) -> None:
        """Model yükle, config oku, tüm yazıcı thread'lerini başlat."""
        self._running = True

        # 1. AI Model yükle (tek instance)
        self._detector = SpaghettiDetector()
        if not self._detector.load_model():
            logger.error("SpaghettiDetector model yüklenemedi!")
            logger.info("Model olmadan devam ediliyor — sadece bağlantı izleme")

        # 2. Bildirim yöneticisi (opsiyonel)
        try:
            self._notifier = NotificationManager()
            self._notifier.load_config()
        except Exception:
            self._notifier = None
            logger.info("Bildirim yöneticisi başlatılamadı (opsiyonel)")

        # 3. Bambu yazıcıları config'den yükle
        config = BambuConfig.load()
        for pc in config.get_enabled_printers():
            self._start_bambu_printer(pc)

        # 4. Klipper yazıcıyı env var'dan yükle (opsiyonel)
        klipper_url = os.environ.get("KLIPPER_MOONRAKER_URL")
        klipper_camera = os.environ.get("KLIPPER_CAMERA_URL")
        if klipper_url and klipper_camera:
            klipper_name = os.environ.get("KLIPPER_NAME", "klipper-1")
            adapter = KlipperAdapter(klipper_url, klipper_name)
            capture = FrameCapture(camera_url=klipper_camera)
            self.add_printer(
                klipper_name, adapter, capture,
                check_interval=int(os.environ.get("KLIPPER_CHECK_INTERVAL", "10")),
            )

        total = len(self._threads)
        if total == 0:
            logger.warning("Hiç yazıcı yapılandırılmamış! Config: %s", BambuConfig.DEFAULT_CONFIG_PATH if hasattr(BambuConfig, 'DEFAULT_CONFIG_PATH') else '/etc/klipperos-ai/bambu-printers.json')
        else:
            logger.info("Toplam %d yazıcı izleniyor", total)

        # Ana thread'i beklet + periyodik durum dosyası yaz
        self._write_status_file()  # ilk yazım
        cycle = 0
        try:
            while self._running:
                time.sleep(1)
                cycle += 1
                if cycle % 5 == 0:  # her 5 saniye
                    self._write_status_file()
        except KeyboardInterrupt:
            pass

    def _start_bambu_printer(self, pc) -> None:
        """Bambu yazıcı için izleme thread'i başlat."""
        try:
            adapter = BambuAdapter(
                hostname=pc.hostname,
                access_code=pc.access_code,
                serial=pc.serial,
                name=pc.name or pc.id,
            )
            capture = BambuFrameCapture(
                hostname=pc.hostname,
                access_code=pc.access_code,
            )
            self.add_printer(
                pc.id, adapter, capture,
                check_interval=pc.check_interval,
            )
        except Exception as exc:
            logger.error("Bambu yazıcı başlatma hatası (%s): %s", pc.id, exc)

    def add_printer(
        self,
        printer_id: str,
        printer: PrinterAdapter,
        frame_capture,
        check_interval: int = 10,
    ) -> None:
        """Yazıcıyı izlemeye ekle ve thread'ini başlat."""
        if printer_id in self._threads:
            logger.warning("Yazıcı zaten izleniyor: %s", printer_id)
            return

        monitor = PrinterMonitorThread(
            printer=printer,
            frame_capture=frame_capture,
            detector=self._detector,
            check_interval=check_interval,
            notifier=self._notifier,
        )

        thread = threading.Thread(
            target=monitor.run,
            name=f"monitor-{printer_id}",
            daemon=True,
        )
        thread.start()

        self._threads[printer_id] = (monitor, thread)
        logger.info(
            "Yazıcı izlemeye eklendi: %s (%s, aralık: %ds)",
            printer_id, printer.printer_type, check_interval,
        )

    def remove_printer(self, printer_id: str) -> bool:
        """Yazıcıyı izlemeden çıkar ve thread'ini durdur."""
        if printer_id not in self._threads:
            return False

        monitor, thread = self._threads.pop(printer_id)
        monitor.stop()
        thread.join(timeout=15)
        logger.info("Yazıcı izlemeden çıkarıldı: %s", printer_id)
        return True

    SNAPSHOT_DIR = "/var/lib/klipperos-ai/snapshots"

    def _write_status_file(self) -> None:
        """Durum dosyasını atomik olarak yaz — API bu dosyayı okur."""
        import json as _json
        import tempfile as _tmp

        # Thread-safe: dict kopyasi al (baska thread degistirebilir)
        threads_snap = dict(self._threads)
        
        status = {
            "monitor_running": True,
            "pid": os.getpid(),
            "printers": {
                pid: mon.stats
                for pid, (mon, _) in threads_snap.items()
            },
            "active_count": len(threads_snap),
            "printer_ids": list(threads_snap.keys()),
            "timestamp": time.time(),
        }
        try:
            fd, tmp_path = _tmp.mkstemp(
                dir="/var/lib/klipperos-ai", suffix=".tmp"
            )
            with os.fdopen(fd, "w") as f:
                _json.dump(status, f)
            os.replace(tmp_path, self.STATUS_FILE)
        except Exception as exc:
            logger.debug("Status dosyası yazılamadı: %s", exc)

        # Kamera snapshot'larını dosyaya kaydet (API servis edecek)
        self._save_snapshots()

    def _save_snapshots(self) -> None:
        """Son JPEG frame'leri dosyaya kaydet — API snapshot endpoint için.

        Atomik yazma: tempfile + os.replace ile yarış koşulu engellenir.
        """
        import tempfile as _tmp

        os.makedirs(self.SNAPSHOT_DIR, exist_ok=True)
        for pid, (mon, _) in list(self._threads.items()):
            jpeg = mon.last_frame_jpeg
            if jpeg:
                try:
                    snap_path = os.path.join(self.SNAPSHOT_DIR, f"{pid}.jpg")
                    fd, tmp_path = _tmp.mkstemp(
                        dir=self.SNAPSHOT_DIR, suffix=".tmp"
                    )
                    with os.fdopen(fd, "wb") as f:
                        f.write(jpeg)
                    os.replace(tmp_path, snap_path)
                except Exception:
                    pass

    def _remove_status_file(self) -> None:
        """Shutdown'da durum dosyasını sil — stale data kalmasın."""
        try:
            os.remove(self.STATUS_FILE)
        except FileNotFoundError:
            pass

    def stop(self) -> None:
        """Tüm thread'leri durdur ve kapat."""
        self._running = False
        logger.info("Tüm yazıcı izleme durduruluyor...")

        for pid, (monitor, thread) in list(self._threads.items()):
            monitor.stop()

        for pid, (monitor, thread) in list(self._threads.items()):
            thread.join(timeout=10)
            logger.debug("Thread durdu: %s", pid)

        self._threads.clear()
        self._remove_status_file()
        logger.info("MultiPrinterMonitor kapatıldı")

    # -- Query API'leri (REST router tarafından kullanılır) --

    def get_printer_stats(self, printer_id: str) -> Optional[dict]:
        if printer_id in self._threads:
            monitor, _ = self._threads[printer_id]
            return monitor.stats
        return None

    def get_printer_detection(self, printer_id: str) -> Optional[dict]:
        if printer_id in self._threads:
            monitor, _ = self._threads[printer_id]
            return monitor.last_detection
        return None

    def get_printer_snapshot(self, printer_id: str) -> Optional[bytes]:
        if printer_id in self._threads:
            monitor, _ = self._threads[printer_id]
            return monitor.last_frame_jpeg
        return None

    def get_all_stats(self) -> dict:
        return {pid: mon.stats for pid, (mon, _) in list(self._threads.items())}

    def get_printer_ids(self) -> list[str]:
        return list(self._threads.keys())


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


def main():
    """Systemd entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("/tmp/kos-bambu-monitor.log", mode="a"),
        ],
    )

    monitor = MultiPrinterMonitor()

    def _signal_handler(signum, frame):
        logger.info("Sinyal alındı (%d), kapatılıyor...", signum)
        monitor.stop()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info("KlipperOS-AI Multi-Printer Monitor başlatılıyor...")
    monitor.start()


if __name__ == "__main__":
    main()

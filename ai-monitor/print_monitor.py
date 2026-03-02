"""
KlipperOS-AI — AI Print Monitor Daemon
=======================================
Ana daemon: kameradan frame yakalar, AI ile analiz eder,
Moonraker API uzerinden aksiyon alir (duraklat, bildirim).

Systemd service olarak calisir:
    systemctl start klipperos-ai-monitor

Ortam degiskenleri:
    MOONRAKER_URL     — Moonraker API URL (default: http://127.0.0.1:7125)
    CAMERA_URL        — Kamera snapshot URL (default: http://127.0.0.1:8080/?action=snapshot)
    CHECK_INTERVAL    — Kontrol araligi saniye (default: 10)
    MODEL_PATH        — TFLite model yolu (default: models/spaghetti_detect.tflite)
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime

import requests

try:
    from frame_capture import FrameCapture
    from spaghetti_detect import SpaghettiDetector
    from flow_guard import FlowGuard, FlowSignal, FlowVerdict
    from heater_analyzer import HeaterDutyAnalyzer
    from extruder_monitor import ExtruderLoadMonitor
except ImportError:
    from .frame_capture import FrameCapture
    from .spaghetti_detect import SpaghettiDetector
    from .flow_guard import FlowGuard, FlowSignal, FlowVerdict
    from .heater_analyzer import HeaterDutyAnalyzer
    from .extruder_monitor import ExtruderLoadMonitor

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/klipperos-ai-monitor.log", mode="a"),
    ],
)
logger = logging.getLogger("klipperos-ai.monitor")

# --- Yapilandirma ---
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")
CAMERA_URL = os.environ.get("CAMERA_URL", "http://127.0.0.1:8080/?action=snapshot")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "10"))
MODEL_PATH = os.environ.get("MODEL_PATH", None)

# --- Moonraker API ---

class MoonrakerClient:
    """Moonraker REST API istemcisi."""

    def __init__(self, base_url: str = MOONRAKER_URL):
        self.base_url = base_url.rstrip("/")

    def get_printer_status(self) -> dict:
        """Yazici durumunu al."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"print_stats": "state,filename,total_duration"},
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json().get("result", {}).get("status", {})
        except Exception as e:
            logger.debug("Yazici durumu alinamadi: %s", e)
            return {}

    def is_printing(self) -> bool:
        """Yazici baski yapiyor mu?"""
        status = self.get_printer_status()
        print_stats = status.get("print_stats", {})
        return print_stats.get("state") == "printing"

    def pause_print(self) -> bool:
        """Baskiyi duraklat."""
        try:
            resp = requests.post(
                f"{self.base_url}/printer/print/pause",
                timeout=5,
            )
            resp.raise_for_status()
            logger.warning("BASKI DURAKLATILDI — AI hata tespiti")
            return True
        except Exception as e:
            logger.error("Baski duraklatma hatasi: %s", e)
            return False

    def send_notification(self, message: str) -> bool:
        """Moonraker uzerinden bildirim gonder."""
        try:
            resp = requests.post(
                f"{self.base_url}/server/notifications/create",
                json={"title": "KlipperOS-AI", "message": message},
                timeout=5,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.debug("Bildirim gonderilemedi: %s", e)
            return False

    def get_heater_duty(self) -> float:
        """Get extruder heater duty cycle (PWM power ratio)."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"extruder": "power"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("status", {})
            return data.get("extruder", {}).get("power", 0.0)
        except Exception:
            return -1.0  # Signal unavailable

    def get_tmc_sg_result(self) -> int:
        """Get TMC2209 StallGuard SG_RESULT for extruder."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"tmc2209 extruder": "drv_status"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("status", {})
            drv_status = data.get("tmc2209 extruder", {}).get("drv_status", {})
            return drv_status.get("sg_result", -1)
        except Exception:
            return -1  # Signal unavailable

    def get_filament_sensor(self) -> int:
        """Get filament motion sensor state. Returns 1=detected, 0=not, -1=unavailable."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"filament_motion_sensor btt_sfs": "filament_detected,enabled"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("status", {})
            sensor = data.get("filament_motion_sensor btt_sfs", {})
            if not sensor.get("enabled", False):
                return -1
            return 1 if sensor.get("filament_detected", True) else 0
        except Exception:
            return -1

    def get_print_layer_info(self) -> dict:
        """Get current print layer and Z info."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"print_stats": "info", "gcode_move": "gcode_position"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("status", {})
            info = data.get("print_stats", {}).get("info", {})
            gcode_pos = data.get("gcode_move", {}).get("gcode_position", [0, 0, 0, 0])
            return {
                "current_layer": info.get("current_layer", 0),
                "total_layer": info.get("total_layer", 0),
                "z_height": gcode_pos[2] if len(gcode_pos) > 2 else 0.0,
            }
        except Exception:
            return {"current_layer": 0, "total_layer": 0, "z_height": 0.0}

    def is_available(self) -> bool:
        """Moonraker erisilebilir mi?"""
        try:
            resp = requests.get(f"{self.base_url}/server/info", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False


# --- Monitor Daemon ---

class PrintMonitor:
    """Ana AI baski izleme daemon'u."""

    def __init__(self):
        self.capture = FrameCapture(camera_url=CAMERA_URL)
        self.detector = SpaghettiDetector(model_path=MODEL_PATH)
        self.moonraker = MoonrakerClient()
        self._running = False
        self._check_count = 0
        self._alert_count = 0
        self._consecutive_alerts = 0
        self._last_action_time = 0

        # FlowGuard 4-layer detection
        self.flow_guard = FlowGuard()
        self.heater_analyzer = HeaterDutyAnalyzer()
        self.extruder_monitor = ExtruderLoadMonitor()
        self._flowguard_enabled = os.environ.get("FLOWGUARD_ENABLED", "1").lower() not in ("0", "false", "no", "off")
        self._calibration_done = False
        self._calibration_count = 0
        self._calibration_heater_samples = []
        self._calibration_tmc_samples = []

    def start(self):
        """Monitor'u baslat."""
        logger.info("=" * 50)
        logger.info("KlipperOS-AI Print Monitor baslatiliyor")
        logger.info("  Moonraker: %s", MOONRAKER_URL)
        logger.info("  Kamera:    %s", CAMERA_URL)
        logger.info("  Aralik:    %d saniye", CHECK_INTERVAL)
        logger.info("=" * 50)

        # Sinyaller
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Model yukle
        model_loaded = self.detector.load_model()
        if not model_loaded:
            logger.warning("AI modeli yuklenemedi. Monitor pasif modda calisacak.")
            logger.warning("Model indirmek icin: kos_update download-models")

        # Moonraker'i bekle
        self._wait_for_moonraker()

        # FlowGuard baslatma
        if self._flowguard_enabled:
            logger.info("FlowGuard aktif. Kalibrasyon baski basladiginda yapilacak.")

        # Ana dongu
        self._running = True
        logger.info("Monitor aktif. Kontrol dongusu basliyor...")

        while self._running:
            try:
                self._check_cycle()
            except Exception as e:
                logger.error("Kontrol dongusu hatasi: %s", e)

            time.sleep(CHECK_INTERVAL)

    def _check_cycle(self):
        """Tek bir kontrol dongusu."""
        # Baski yapiliyor mu?
        if not self.moonraker.is_printing():
            if self._check_count > 0 and self._check_count % 30 == 0:
                logger.debug("Yazici bosta — bekleniyor...")
            self._consecutive_alerts = 0
            return

        # Kameradan frame yakala
        frame = self.capture.capture()
        if frame is None:
            return

        self._check_count += 1

        # AI tespiti
        result = self.detector.detect(frame)
        detected_class = result["class"]
        confidence = result["confidence"]
        action = result["action"]

        # Sonucu logla
        if detected_class != "normal":
            logger.info(
                "Tespit #%d: %s (guven: %.1f%%) -> aksiyon: %s",
                self._check_count,
                detected_class,
                confidence * 100,
                action,
            )

        # Aksiyon al
        self._handle_action(action, result)

        # --- FlowGuard 4-Layer Check ---
        if self._flowguard_enabled:
            self._flowguard_cycle(ai_action=action)

    def _handle_action(self, action: str, result: dict):
        """Tespit sonucuna gore aksiyon al."""
        now = time.time()

        if action == "pause":
            self._consecutive_alerts += 1

            # Ardi ardina 3 alert olduysa duraklat (false positive azaltma)
            if self._consecutive_alerts >= 3:
                # Son aksiyon en az 60 saniye onceyse
                if now - self._last_action_time > 60:
                    self.moonraker.pause_print()
                    self.moonraker.send_notification(
                        f"Baski hatasi tespit edildi: {result['class']} "
                        f"(guven: {result['confidence']:.0%}). Baski duraklatildi."
                    )
                    self._last_action_time = now
                    self._alert_count += 1
                    self._consecutive_alerts = 0

        elif action == "notify":
            self._consecutive_alerts = 0
            if now - self._last_action_time > 300:  # 5 dk arayla bildir
                self.moonraker.send_notification(
                    f"Baski uyarisi: {result['class']} "
                    f"(guven: {result['confidence']:.0%})"
                )
                self._last_action_time = now

        elif action == "complete":
            self._consecutive_alerts = 0
            self.moonraker.send_notification("Baski tamamlanmis gorunuyor.")

        else:
            # Normal — ardisik alert sayacini sifirla
            self._consecutive_alerts = 0

    def _wait_for_moonraker(self):
        """Moonraker'in hazir olmasini bekle."""
        logger.info("Moonraker bekleniyor...")
        for _ in range(30):
            if self.moonraker.is_available():
                logger.info("Moonraker hazir.")
                return
            time.sleep(2)
        logger.warning("Moonraker'a 60sn icinde ulasilamadi. Yine de baslatiliyor.")

    def _signal_handler(self, signum, frame):
        """Graceful shutdown."""
        logger.info("Sinyal alindi (%s). Monitor durduruluyor...", signum)
        self._running = False

    def _flowguard_cycle(self, ai_action: str = "none"):
        """FlowGuard 4-layer detection cycle."""
        # Kalibrasyon asamasi
        if not self._calibration_done:
            self._flowguard_calibrate()
            return

        # Layer bilgisi guncelle
        layer_info = self.moonraker.get_print_layer_info()
        self.flow_guard.update_layer(
            layer_info["current_layer"],
            layer_info["z_height"],
        )

        # 4 sinyal topla
        signals = []

        # L1: Filament sensor
        sensor = self.moonraker.get_filament_sensor()
        if sensor == -1:
            signals.append(FlowSignal.UNAVAILABLE)
        elif sensor == 0:
            signals.append(FlowSignal.ANOMALY)
        else:
            signals.append(FlowSignal.OK)

        # L2: Heater duty cycle
        duty = self.moonraker.get_heater_duty()
        if duty < 0:
            signals.append(FlowSignal.UNAVAILABLE)
        else:
            self.heater_analyzer.add_sample(duty)
            heater_state = self.heater_analyzer.check_flow()
            if heater_state.name == "ANOMALY":
                signals.append(FlowSignal.ANOMALY)
            else:
                signals.append(FlowSignal.OK)

        # L3: TMC SG_RESULT
        sg = self.moonraker.get_tmc_sg_result()
        if sg < 0:
            signals.append(FlowSignal.UNAVAILABLE)
        else:
            self.extruder_monitor.add_sample(sg)
            tmc_state = self.extruder_monitor.check_flow()
            if tmc_state.name == "ANOMALY":
                signals.append(FlowSignal.ANOMALY)
            else:
                signals.append(FlowSignal.OK)

        # L4: AI Camera — use actual AI detection result from _check_cycle
        if ai_action == "pause":
            signals.append(FlowSignal.ANOMALY)
        elif ai_action == "notify":
            signals.append(FlowSignal.OK)  # Warning but not anomaly yet
        else:
            signals.append(FlowSignal.OK)

        # Oylama
        verdict = self.flow_guard.evaluate(signals)

        if verdict == FlowVerdict.CRITICAL:
            logger.critical(
                "FlowGuard CRITICAL — Baski duraklatiliyor! "
                "Sinyaller: %s, Son OK katman: %d (Z=%.1f)",
                [s.name for s in signals],
                self.flow_guard.last_ok_layer,
                self.flow_guard.last_ok_z,
            )
            self.moonraker.pause_print()
            self.moonraker.send_notification(
                f"FlowGuard CRITICAL: Akis hatasi tespit edildi! "
                f"Son saglikli katman: {self.flow_guard.last_ok_layer} "
                f"(Z={self.flow_guard.last_ok_z:.1f}mm). Baski duraklatildi."
            )
        elif verdict == FlowVerdict.WARNING:
            logger.warning(
                "FlowGuard WARNING — Sinyaller: %s (ardisik: %d/%d)",
                [s.name for s in signals],
                self.flow_guard.warning_count,
                self.flow_guard.warning_threshold,
            )
        elif verdict == FlowVerdict.NOTICE:
            logger.info("FlowGuard NOTICE — Tek sinyal anomalisi: %s",
                         [s.name for s in signals])

    def _flowguard_calibrate(self):
        """FlowGuard kalibrasyon — ilk 30 ornekle baseline hesapla."""
        duty = self.moonraker.get_heater_duty()
        sg = self.moonraker.get_tmc_sg_result()

        if duty >= 0:
            self._calibration_heater_samples.append(duty)
        if sg >= 0:
            self._calibration_tmc_samples.append(sg)

        self._calibration_count += 1

        if self._calibration_count >= 30:
            # Heater baseline
            if self._calibration_heater_samples:
                for s in self._calibration_heater_samples:
                    self.heater_analyzer.add_sample(s)
                self.heater_analyzer.calibrate()
                logger.info("FlowGuard L2 baseline: %.3f", self.heater_analyzer.baseline)

            # TMC baseline
            if self._calibration_tmc_samples:
                mean_sg = sum(self._calibration_tmc_samples) / len(self._calibration_tmc_samples)
                self.extruder_monitor.set_baseline(mean_sg)
                logger.info("FlowGuard L3 baseline: %.1f", mean_sg)

            self._calibration_done = True
            logger.info("FlowGuard kalibrasyon tamamlandi. 4-katman tespit aktif.")

    @property
    def stats(self) -> dict:
        """Monitor istatistikleri."""
        return {
            "check_count": self._check_count,
            "alert_count": self._alert_count,
            "capture_stats": self.capture.stats,
            "model_loaded": self.detector.is_loaded,
            "flowguard_enabled": self._flowguard_enabled,
            "flowguard_calibrated": self._calibration_done,
            "flowguard_last_ok_layer": self.flow_guard.last_ok_layer,
            "flowguard_warning_count": self.flow_guard.warning_count,
        }


# --- Entry Point ---

def main():
    monitor = PrintMonitor()
    monitor.start()


if __name__ == "__main__":
    main()

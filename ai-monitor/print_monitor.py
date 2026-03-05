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
    from adaptive_thresholds import AdaptiveThresholdEngine
    from adaptive_print import AdaptivePrintController
    from predictive_maintenance import PredictiveMaintenanceEngine
    from autonomous_recovery import AutonomousRecoveryEngine
    from bed_level_analyzer import DriftDetector
except ImportError:
    from .frame_capture import FrameCapture
    from .spaghetti_detect import SpaghettiDetector
    from .flow_guard import FlowGuard, FlowSignal, FlowVerdict
    from .heater_analyzer import HeaterDutyAnalyzer
    from .extruder_monitor import ExtruderLoadMonitor
    from .adaptive_thresholds import AdaptiveThresholdEngine
    from .adaptive_print import AdaptivePrintController
    from .predictive_maintenance import PredictiveMaintenanceEngine
    from .autonomous_recovery import AutonomousRecoveryEngine
    from .bed_level_analyzer import DriftDetector

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

    def get_bed_mesh(self) -> dict:
        """Get current bed mesh data."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"bed_mesh": "profile_name,profiles,mesh_matrix"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("status", {})
            return data.get("bed_mesh", {})
        except Exception:
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

    def resume_print(self) -> bool:
        """Baskiyi devam ettir."""
        try:
            resp = requests.post(
                f"{self.base_url}/printer/print/resume",
                timeout=5,
            )
            resp.raise_for_status()
            logger.info("BASKI DEVAM EDIYOR — Recovery basarili")
            return True
        except Exception as e:
            logger.error("Baski devam ettirme hatasi: %s", e)
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

    def send_gcode(self, command: str) -> bool:
        """Send G-code command via Moonraker."""
        try:
            resp = requests.post(
                f"{self.base_url}/printer/gcode/script",
                json={"script": command},
                timeout=5,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("G-code gonderilemedi (%s): %s", command, e)
            return False

    def get_print_speed(self) -> float:
        """Get current print speed (mm/s) from velocity limit."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"toolhead": "max_velocity"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("status", {})
            return data.get("toolhead", {}).get("max_velocity", 0.0)
        except Exception:
            return 0.0

    def get_extruder_temp(self) -> float:
        """Get current extruder target temperature."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"extruder": "target"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("status", {})
            return data.get("extruder", {}).get("target", 0.0)
        except Exception:
            return 0.0

    def get_current_extruder_temp(self) -> float:
        """Get current extruder actual temperature."""
        try:
            resp = requests.get(
                f"{self.base_url}/printer/objects/query",
                params={"extruder": "temperature"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {}).get("status", {})
            return data.get("extruder", {}).get("temperature", 0.0)
        except Exception:
            return 0.0

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

        # Adaptive Print Intelligence (Phase 2)
        self.adaptive_thresholds = AdaptiveThresholdEngine()
        self.adaptive_print = AdaptivePrintController()
        self._adaptive_enabled = os.environ.get("ADAPTIVE_PRINT", "0").lower() in ("1", "true", "yes", "on")
        self._was_printing = False
        self._last_layer = -1

        # Predictive Maintenance (Phase 3)
        self.maintenance_engine = PredictiveMaintenanceEngine()
        self._maintenance_enabled = os.environ.get("PREDICTIVE_MAINT", "1").lower() not in ("0", "false", "no", "off")
        self._last_maintenance_check = 0.0
        self._print_start_time = 0.0

        # Autonomous Recovery (Phase 4)
        self.recovery_engine = AutonomousRecoveryEngine(
            gcode_sender=self.moonraker.send_gcode,
            pause_printer=self.moonraker.pause_print,
            resume_printer=self.moonraker.resume_print,
            sensor_reader=self.moonraker.get_filament_sensor,
            temp_reader=self.moonraker.get_current_extruder_temp,
            notifier=self.moonraker.send_notification,
        )
        self._autorecovery_enabled = os.environ.get("AUTORECOVERY_ENABLED", "0").lower() in ("1", "true", "yes", "on")

        # Bed Level Analyzer (Phase 5)
        self.drift_detector = DriftDetector()
        self._bed_level_enabled = os.environ.get("BED_LEVEL_CHECK", "1").lower() not in ("0", "false", "no", "off")
        self._bed_level_checked = False

        # Auto Recalibrate (opt-in)
        self._auto_recalibrate = os.environ.get("AUTO_RECALIBRATE", "0").lower() in ("1", "true", "yes", "on")
        self._last_auto_recal_date = ""  # YYYY-MM-DD — gunde max 1 kez

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

        # Adaptive Print baslatma
        if self._adaptive_enabled:
            logger.info("Adaptive Print aktif. Parametreler baski basladiginda ayarlanacak.")
        else:
            logger.info("Adaptive Print devre disi. ADAPTIVE_PRINT=1 ile aktiflestirebilirsiniz.")

        # Predictive Maintenance baslatma
        if self._maintenance_enabled:
            logger.info("Predictive Maintenance aktif. Baski saati: %.1f saat",
                        self.maintenance_engine._total_print_hours)
        else:
            logger.info("Predictive Maintenance devre disi. PREDICTIVE_MAINT=1 ile aktiflestirebilirsiniz.")

        # Autonomous Recovery baslatma
        if self._autorecovery_enabled:
            logger.info("Autonomous Recovery aktif. Max deneme: 2, Max sicaklik: 280°C")
        else:
            logger.info("Autonomous Recovery devre disi. AUTORECOVERY_ENABLED=1 ile aktiflestirebilirsiniz.")

        # Bed Level Check baslatma
        if self._bed_level_enabled:
            logger.info("Bed Level Check aktif. Baski oncesi mesh kontrol yapilacak.")
        else:
            logger.info("Bed Level Check devre disi. BED_LEVEL_CHECK=1 ile aktiflestirebilirsiniz.")

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
        is_printing = self.moonraker.is_printing()

        if not is_printing:
            if self._was_printing:
                # Baski bitti — adaptive state sifirla
                self._was_printing = False
                if self._adaptive_enabled:
                    self.adaptive_print.reset()
                    self.adaptive_thresholds = AdaptiveThresholdEngine()
                    logger.info("Adaptive: baski bitti, durum sifirlandi.")
                # Bed Level: post-print snapshot
                if self._bed_level_enabled:
                    self._bed_level_post_print()
                    self._bed_level_checked = False
                # Predictive Maintenance: baski saati ekle
                if self._maintenance_enabled and self._print_start_time > 0:
                    hours = (time.time() - self._print_start_time) / 3600
                    self.maintenance_engine.add_print_hours(hours)
                    self.maintenance_engine.save_state()
                    logger.info("Maintenance: +%.2f saat eklendi (toplam: %.1f)",
                                hours, self.maintenance_engine._total_print_hours)
                    self._print_start_time = 0.0
            if self._check_count > 0 and self._check_count % 30 == 0:
                logger.debug("Yazici bosta — bekleniyor...")
            self._consecutive_alerts = 0
            return

        # Yeni baski basladi mi?
        if not self._was_printing:
            self._was_printing = True
            self._print_start_time = time.time()
            if self._adaptive_enabled:
                speed = self.moonraker.get_print_speed()
                temp = self.moonraker.get_extruder_temp()
                if speed > 0 and temp > 0:
                    self.adaptive_print.set_base_params(speed=speed, temp=temp)
                    logger.info("Adaptive: baski basladi, base speed=%.0f temp=%.0f", speed, temp)

            # Bed Level Check
            if self._bed_level_enabled and not self._bed_level_checked:
                self._bed_level_pre_print_check()
                self._bed_level_checked = True

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

        # Feed AI confidence to adaptive thresholds
        if self._adaptive_enabled:
            self.adaptive_thresholds.update(ai_confidence=confidence)

        # --- FlowGuard 4-Layer Check ---
        if self._flowguard_enabled:
            self._flowguard_cycle(ai_action=action, ai_confidence=confidence, ai_class=detected_class)

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

    def _flowguard_cycle(self, ai_action: str = "none",
                         ai_confidence: float = 1.0, ai_class: str = "normal"):
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

        # Adaptive threshold besle
        if self._adaptive_enabled and duty >= 0:
            self.adaptive_thresholds.update(
                heater_duty=duty,
                sg_result=float(sg) if sg >= 0 else -1.0,
            )

        # Predictive Maintenance: feed trackers
        if self._maintenance_enabled:
            target_temp = self.moonraker.get_extruder_temp()
            self.maintenance_engine.update(
                heater_duty=duty,
                sg_result=float(sg) if sg >= 0 else -1.0,
                target_temp=target_temp,
            )
            # Periodic check (her 60 saniyede bir)
            now = time.time()
            if now - self._last_maintenance_check >= 60:
                self._last_maintenance_check = now
                alerts = self.maintenance_engine.check_maintenance()
                for alert in alerts:
                    logger.warning("Maintenance %s: %s — %s",
                                   alert.severity.upper() if hasattr(alert.severity, 'upper') else alert.severity,
                                   alert.message, alert.recommended_action)
                    if alert.severity in ("warning", "critical"):
                        self.moonraker.send_notification(
                            f"Bakim uyarisi ({alert.component}): {alert.message}")

        # Oylama
        verdict = self.flow_guard.evaluate(signals)

        # --- Adaptive Print Scoring ---
        if self._adaptive_enabled and self._calibration_done:
            self._adaptive_score_cycle(
                layer_info=layer_info,
                duty=duty,
                sg=sg,
            )

        if verdict == FlowVerdict.CRITICAL:
            logger.critical(
                "FlowGuard CRITICAL — Sinyaller: %s, Son OK katman: %d (Z=%.1f)",
                [s.name for s in signals],
                self.flow_guard.last_ok_layer,
                self.flow_guard.last_ok_z,
            )

            # Autonomous Recovery: teshis → plan → yurut
            if self._autorecovery_enabled:
                recovered = self._attempt_recovery(
                    sensor=sensor, sg=sg, duty=duty,
                    ai_class=ai_class, ai_confidence=ai_confidence,
                )
                if recovered:
                    return  # Kurtarma basarili, devam et

            # Fallback: durdur + bildirim
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

    def _attempt_recovery(self, sensor: int, sg: int, duty: float,
                          ai_class: str, ai_confidence: float) -> bool:
        """Otonom kurtarma dene. Basari durumunda True dondurur."""
        try:
            target_temp = self.moonraker.get_extruder_temp()
            current_temp = self.moonraker.get_current_extruder_temp()
            heater_baseline = self.heater_analyzer.baseline if hasattr(self.heater_analyzer, "baseline") else 0.0
            tmc_baseline = self.extruder_monitor._baseline if hasattr(self.extruder_monitor, "_baseline") else 0.0

            diagnosis = self.recovery_engine.diagnose(
                sensor_state=sensor,
                tmc_sg=sg,
                tmc_sg_baseline=tmc_baseline,
                heater_duty=duty,
                heater_baseline=heater_baseline,
                target_temp=target_temp,
                current_temp=current_temp,
                ai_class=ai_class,
                ai_confidence=ai_confidence,
            )

            if diagnosis is None:
                logger.info("Recovery: teshis sonucu yok, kurtarma atlanıyor.")
                return False

            if not diagnosis.auto_recoverable:
                logger.warning("Recovery: %s otomatik kurtarilamaz.", diagnosis.category.value)
                self.moonraker.send_notification(
                    f"Ariza tespit edildi: {diagnosis.category.value} — "
                    f"Otomatik kurtarma mumkun degil. Baski duraklatildi."
                )
                return False

            plan = self.recovery_engine.plan_recovery(
                diagnosis, current_temp=current_temp, target_temp=target_temp)
            if plan is None:
                logger.warning("Recovery: plan olusturulamadi (max deneme veya devre disi).")
                return False

            logger.info("Recovery: %s icin %d adimlik plan olusturuldu.",
                        diagnosis.category.value, len(plan.steps))
            self.moonraker.send_notification(
                f"Otonom kurtarma baslatiliyor: {diagnosis.category.value}")

            result = self.recovery_engine.execute_recovery(plan)
            if result.success:
                logger.info("Recovery BASARILI: %s (%.1fs)", diagnosis.category.value, result.duration_sec)
                self.moonraker.send_notification(
                    f"Kurtarma basarili! {diagnosis.category.value} — "
                    f"Baski devam ediyor ({result.duration_sec:.0f}s)")
                return True
            else:
                logger.error("Recovery BASARISIZ: %s — %s", diagnosis.category.value, result.failure_reason)
                self.moonraker.send_notification(
                    f"Kurtarma basarisiz: {result.failure_reason}. Baski durduruluyor.")
                return False

        except Exception as e:
            logger.error("Recovery hatasi: %s", e)
            return False

    def _adaptive_score_cycle(self, layer_info: dict, duty: float, sg: int):
        """Adaptive print scoring — her katmanda skor, her 5'te ayarlama."""
        current_layer = layer_info.get("current_layer", 0)
        z_height = layer_info.get("z_height", 0.0)

        # Ayni katmani tekrar skorlama
        if current_layer == self._last_layer:
            return
        self._last_layer = current_layer

        # Flow rate suggestion: extruder_monitor'den
        flow_suggestion = 1.0
        if hasattr(self.extruder_monitor, "suggest_flow_rate"):
            flow_suggestion = self.extruder_monitor.suggest_flow_rate()

        # Heater baseline
        heater_baseline = self.heater_analyzer.baseline if hasattr(self.heater_analyzer, "baseline") else 0.0

        # AI son tespit
        ai_conf = self.adaptive_thresholds.ai_confidence_stats.mean if self.adaptive_thresholds.ai_confidence_stats.n > 0 else 1.0

        # Skor hesapla
        score = self.adaptive_print.score_layer(
            layer=current_layer,
            z_height=z_height,
            flow_rate_suggestion=flow_suggestion,
            heater_duty=duty if duty >= 0 else 0.0,
            heater_baseline=heater_baseline,
            ai_confidence=ai_conf,
            ai_class="normal",  # FlowGuard zaten anomalileri yakaliyor
        )

        # Her 5 katmanda degerlendir
        if current_layer > 0 and current_layer % 5 == 0:
            adj = self.adaptive_print.evaluate_adaptation()
            if adj:
                self.adaptive_print.apply_adjustment(
                    adj,
                    gcode_sender=self.moonraker.send_gcode,
                )

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

    def _bed_level_pre_print_check(self):
        """Baski oncesi bed mesh kontrol."""
        mesh_data = self.moonraker.get_bed_mesh()
        profile = mesh_data.get("profile_name", "")
        if not profile:
            self.moonraker.send_notification(
                "KOS UYARI: Aktif bed mesh yok! "
                "KOS_BED_LEVEL_CALIBRATE calistirin."
            )
            logger.warning("Bed Level: aktif mesh yok")
            return

        mesh_matrix = mesh_data.get("mesh_matrix", [])
        if mesh_matrix:
            report = self.drift_detector.check_drift(profile, mesh_matrix)
            if report.recommendation == "recalibrate":
                if self._auto_recalibrate and self._last_auto_recal_date != time.strftime("%Y-%m-%d"):
                    logger.warning("Bed Level: drift %.3fmm — otomatik kalibrasyon tetikleniyor", report.max_point_drift)
                    self.moonraker.send_notification(
                        f"KOS: Kritik bed level drift ({report.max_point_drift:.2f}mm). "
                        "Otomatik kalibrasyon baslatiliyor..."
                    )
                    self.moonraker.send_gcode("KOS_BED_LEVEL_CALIBRATE")
                    self._last_auto_recal_date = time.strftime("%Y-%m-%d")
                else:
                    self.moonraker.send_notification(
                        f"KOS: Kritik bed level drift ({report.max_point_drift:.2f}mm). "
                        "Yeniden kalibrasyon onerilir."
                    )
                    logger.warning("Bed Level: drift %.3fmm — recalibrate", report.max_point_drift)
            elif report.recommendation == "check_screws":
                self.moonraker.send_notification(
                    f"KOS: Bed level drift algilandi ({report.max_point_drift:.2f}mm). "
                    "Vida kontrolu onerilir."
                )
                logger.info("Bed Level: drift %.3fmm — check screws", report.max_point_drift)
            else:
                logger.info("Bed Level: mesh OK (drift %.3fmm)", report.max_point_drift)

    def _bed_level_post_print(self):
        """Baski sonrasi mesh snapshot al."""
        mesh_data = self.moonraker.get_bed_mesh()
        profile = mesh_data.get("profile_name", "")
        mesh_matrix = mesh_data.get("mesh_matrix", [])
        if profile and mesh_matrix:
            self.drift_detector.add_snapshot(profile, mesh_matrix)
            logger.info("Bed Level: post-print snapshot kaydedildi (%s)", profile)

            # Trend analizi
            trend = self.drift_detector.get_drift_trend(profile)
            if trend.trend_direction == "worsening":
                msg = (
                    f"KOS: Bed level trend kotulesiyor "
                    f"({trend.avg_drift_per_day:.3f}mm/gun)."
                )
                if trend.forecast_days_to_recalibrate > 0:
                    msg += (
                        f" Tahmini kalibrasyon: "
                        f"{trend.forecast_days_to_recalibrate:.0f} gun"
                    )
                self.moonraker.send_notification(msg)
                logger.warning(
                    "Bed Level trend: %s (%.4f mm/gun)",
                    trend.trend_direction, trend.avg_drift_per_day,
                )
                # Otomatik kalibrasyon (idle ise)
                if self._auto_recalibrate and self._last_auto_recal_date != time.strftime("%Y-%m-%d"):
                    if not self.moonraker.is_printing():
                        logger.info("Bed Level: post-print otomatik kalibrasyon tetikleniyor")
                        self.moonraker.send_notification(
                            "KOS: Bed level trend kotulesiyor. Otomatik kalibrasyon baslatiliyor..."
                        )
                        self.moonraker.send_gcode("KOS_BED_LEVEL_CALIBRATE")
                        self._last_auto_recal_date = time.strftime("%Y-%m-%d")

    @property
    def stats(self) -> dict:
        """Monitor istatistikleri."""
        result = {
            "check_count": self._check_count,
            "alert_count": self._alert_count,
            "capture_stats": self.capture.stats,
            "model_loaded": self.detector.is_loaded,
            "flowguard_enabled": self._flowguard_enabled,
            "flowguard_calibrated": self._calibration_done,
            "flowguard_last_ok_layer": self.flow_guard.last_ok_layer,
            "flowguard_warning_count": self.flow_guard.warning_count,
            "adaptive_enabled": self._adaptive_enabled,
        }
        if self._adaptive_enabled:
            result["adaptive_adjustments"] = self.adaptive_print.current_adjustments
            result["adaptive_thresholds"] = self.adaptive_thresholds.summary
        if self._maintenance_enabled:
            result["maintenance"] = self.maintenance_engine.status
        result["autorecovery_enabled"] = self._autorecovery_enabled
        if self._autorecovery_enabled:
            result["recovery"] = self.recovery_engine.status
        return result


# --- Entry Point ---

def main():
    monitor = PrintMonitor()
    monitor.start()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
KlipperOS-AI — OOBE (Out of Box Experience) Orchestrator
==========================================================
Ilk acilis kurulum sihirbazi orkestratoru.
State machine mantigi ile calisir, KlipperScreen ve CLI ile JSON IPC uzerinden iletisir.

Mimarisi:
    Orchestrator (bu dosya)  ←→  JSON dosyalari  ←→  KlipperScreen Panel / CLI

Kullanim:
    kos-oobe run                          # Interaktif (UI bekler)
    kos-oobe run --non-interactive        # Headless otomasyon
    kos-oobe run --profile STANDARD       # Profili onceden belirle
    kos-oobe status                       # Mevcut durumu goster
    kos-oobe reset                        # OOBE'yi sifirla (tekrar calistir)
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "1.0.0"
TAG = "[kos-oobe]"

KOS_CONFIG_DIR = Path("/etc/klipperos-ai")
STATE_FILE = KOS_CONFIG_DIR / "oobe-state.json"
COMMAND_FILE = KOS_CONFIG_DIR / "oobe-command.json"
OOBE_DONE_MARKER = KOS_CONFIG_DIR / ".oobe-done"
PROFILE_FILE = KOS_CONFIG_DIR / "profile"
PROFILE_YML = KOS_CONFIG_DIR / "profile.yml"

# Step order
STEPS = ["welcome", "hw_detect", "wifi", "profile", "install", "tuning", "complete"]
STEP_NAMES_TR = {
    "welcome": "Hosgeldiniz",
    "hw_detect": "Donanim Algilama",
    "wifi": "Ag Yapilandirma",
    "profile": "Profil Secimi",
    "install": "Kurulum",
    "tuning": "Sistem Ayarlari",
    "complete": "Tamamlandi",
}

# Status constants
PENDING = "pending"
RUNNING = "running"
WAITING_INPUT = "waiting_input"
COMPLETED = "completed"
ERROR = "error"
SKIPPED = "skipped"

# Profile matrix (from kos_firstrun.py)
MODEL_MATRIX = {
    "LIGHT": [],
    "STANDARD": ["qwen3:1.7b"],
    "FULL": ["qwen3:4b", "qwen3:1.7b"],
}

PROFILE_DESC = {
    "LIGHT": "Temel — Klipper + Moonraker + Mainsail, yerel model yok",
    "STANDARD": "Dengeli — + KlipperScreen + Crowsnest + AI (qwen3:1.7b)",
    "FULL": "Tam — + Multi-printer + Timelapse + Gelismis AI (qwen3:4b)",
}

# Terminal colours (CLI mode)
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"

logger = logging.getLogger("kos-oobe")


# ---------------------------------------------------------------------------
# Atomic JSON I/O
# ---------------------------------------------------------------------------

def _write_json_atomic(path: Path, data: dict) -> None:
    """Write JSON atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix=".oobe-"
        )
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            f.write("\n")
        # Ensure file is world-readable (KlipperScreen runs as different user)
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(path))
    except OSError as exc:
        logger.error("JSON yazma hatasi %s: %s", path, exc)
        # Clean up temp file if rename failed
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _read_json(path: Path) -> Optional[dict]:
    """Read and parse a JSON file, return None on error."""
    try:
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("JSON okuma hatasi %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# System Helpers (reused from kos_firstrun.py)
# ---------------------------------------------------------------------------

def _check_command(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    try:
        return subprocess.run(
            ["which", cmd], capture_output=True, timeout=5
        ).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_cmd(cmd: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a command and return result (never raises)."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        logger.warning("Komut zaman asimi: %s", " ".join(cmd))
        return subprocess.CompletedProcess(cmd, -1, "", "timeout")
    except (FileNotFoundError, OSError) as exc:
        logger.error("Komut hatasi: %s — %s", " ".join(cmd), exc)
        return subprocess.CompletedProcess(cmd, -1, "", str(exc))


def _detect_hardware() -> dict:
    """Detect RAM, CPU, MCU devices, and cameras."""
    # RAM
    ram_mb = 1024
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    ram_mb = int(line.split()[1]) // 1024
                    break
    except (OSError, ValueError):
        pass

    # CPU
    cpu_model, cpu_cores, cpu_threads = "unknown", 1, 1
    try:
        with open("/proc/cpuinfo") as f:
            content = f.read()
        for line in content.splitlines():
            if line.startswith("model name") and cpu_model == "unknown":
                cpu_model = line.split(":", 1)[1].strip()
            if line.startswith("cpu cores"):
                cpu_cores = int(line.split(":", 1)[1].strip())
        cpu_threads = max(content.count("processor\t:"), 1)
    except (OSError, ValueError):
        pass

    # MCU serial devices
    import glob as _glob
    mcu_devices = []
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
        mcu_devices.extend(_glob.glob(pattern))

    # Cameras
    cameras = _glob.glob("/dev/video*")

    return {
        "ram_mb": ram_mb,
        "cpu": {"model": cpu_model, "cores": cpu_cores, "threads": cpu_threads},
        "mcu_devices": mcu_devices,
        "cameras": cameras,
    }


def _get_recommended_profile(ram_mb: int) -> str:
    """Determine recommended profile based on RAM."""
    if ram_mb <= 768:
        return "LIGHT"
    elif ram_mb <= 2048:
        return "STANDARD"
    return "FULL"


def _scan_wifi() -> List[dict]:
    """Scan WiFi networks via nmcli."""
    result = _run_cmd([
        "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
    ])
    if result.returncode != 0:
        return []
    networks = []
    seen = set()
    for line in result.stdout.strip().splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0] and parts[0] not in seen:
            seen.add(parts[0])
            try:
                sig = int(parts[1])
            except (ValueError, TypeError):
                sig = 0
            networks.append({
                "ssid": parts[0],
                "signal": sig,
                "security": parts[2],
            })
    return sorted(networks, key=lambda n: n["signal"], reverse=True)


def _connect_wifi(ssid: str, password: str) -> bool:
    """Connect to WiFi via nmcli."""
    result = _run_cmd([
        "nmcli", "dev", "wifi", "connect", ssid, "password", password,
    ], timeout=30)
    return result.returncode == 0


def _get_current_ip() -> dict:
    """Get current IP and interface."""
    import re
    result = _run_cmd(["ip", "route", "get", "1.1.1.1"])
    ip_addr, interface = "yok", "yok"
    if result.returncode == 0:
        dev_m = re.search(r"dev\s+(\S+)", result.stdout)
        src_m = re.search(r"src\s+(\S+)", result.stdout)
        if dev_m:
            interface = dev_m.group(1)
        if src_m:
            ip_addr = src_m.group(1)
    return {"ip": ip_addr, "interface": interface}


# ---------------------------------------------------------------------------
# OobeOrchestrator — State Machine
# ---------------------------------------------------------------------------

class OobeOrchestrator:
    """OOBE state machine orchestrator.

    Manages the step-by-step first boot setup, writing state to JSON
    for KlipperScreen and CLI to read, and reading commands from UI.
    """

    def __init__(
        self,
        non_interactive: bool = False,
        profile_override: Optional[str] = None,
        skip_models: bool = False,
    ):
        self.non_interactive = non_interactive
        self.profile_override = profile_override
        self.skip_models = skip_models
        self._running = True
        self._state: Dict[str, Any] = self._initial_state()
        self._hw_info: dict = {}

    # -- State management --

    def _initial_state(self) -> dict:
        """Create initial OOBE state."""
        steps = {}
        for step in STEPS:
            steps[step] = {"status": PENDING, "data": {}}
        return {
            "version": 1,
            "current_step": None,
            "steps": steps,
            "hw_info": {},
            "selected_profile": None,
            "error": None,
            "progress_percent": 0,
            "updated_at": datetime.now().isoformat(),
        }

    def _update_step(
        self,
        step: str,
        status: str,
        data: Optional[dict] = None,
    ) -> None:
        """Update a step's status and data, then write state file."""
        self._state["steps"][step]["status"] = status
        if data:
            self._state["steps"][step]["data"].update(data)
        self._state["current_step"] = step
        self._state["updated_at"] = datetime.now().isoformat()

        # Calculate progress
        completed = sum(
            1 for s in STEPS
            if self._state["steps"][s]["status"] in (COMPLETED, SKIPPED)
        )
        self._state["progress_percent"] = int(completed / len(STEPS) * 100)

        self._write_state()

    def _write_state(self) -> None:
        """Persist state to JSON file."""
        _write_json_atomic(STATE_FILE, self._state)

    def _read_command(self, timeout: float = 0.5) -> Optional[dict]:
        """Read and consume a command from the command file.

        Returns the command dict or None if no command pending.
        """
        cmd = _read_json(COMMAND_FILE)
        if cmd and cmd.get("command"):
            # Consume (delete) the command file
            try:
                COMMAND_FILE.unlink(missing_ok=True)
            except OSError:
                pass
            return cmd
        return None

    def _wait_for_command(
        self,
        expected: Optional[str] = None,
        timeout: float = 600,
    ) -> Optional[dict]:
        """Block until a matching command arrives or timeout.

        In non-interactive mode, returns None immediately.
        """
        if self.non_interactive:
            return None
        start = time.monotonic()
        while self._running and (time.monotonic() - start) < timeout:
            cmd = self._read_command()
            if cmd:
                if expected is None or cmd.get("command") == expected:
                    return cmd
                logger.debug("Beklenen '%s', gelen '%s' — yoksayildi",
                             expected, cmd.get("command"))
            time.sleep(1)
        return None

    # -- Signal handling --

    def _handle_signal(self, signum, _frame):
        """Gracefully stop on SIGTERM/SIGINT."""
        logger.info("Sinyal alindi (%s), durduruluyor...", signum)
        self._running = False

    # -- Step implementations --

    def step_welcome(self) -> None:
        """Step 1: Welcome screen."""
        self._update_step("welcome", RUNNING)
        logger.info("Hosgeldiniz — KlipperOS-AI OOBE v%s", VERSION)

        if self.non_interactive:
            self._update_step("welcome", COMPLETED)
            return

        # Wait for user to press "Start" in UI
        self._update_step("welcome", WAITING_INPUT)
        cmd = self._wait_for_command("start")
        self._update_step("welcome", COMPLETED)

    def step_hw_detect(self) -> None:
        """Step 2: Hardware detection (MCU, cameras, RAM, CPU)."""
        self._update_step("hw_detect", RUNNING)
        logger.info("Donanim algilama baslatiliyor...")

        self._hw_info = _detect_hardware()
        self._state["hw_info"] = self._hw_info

        hw_data = {
            "ram_mb": self._hw_info["ram_mb"],
            "cpu_model": self._hw_info["cpu"]["model"],
            "cpu_cores": self._hw_info["cpu"]["cores"],
            "mcu_count": len(self._hw_info.get("mcu_devices", [])),
            "mcu_devices": self._hw_info.get("mcu_devices", []),
            "camera_count": len(self._hw_info.get("cameras", [])),
            "cameras": self._hw_info.get("cameras", []),
            "recommended_profile": _get_recommended_profile(self._hw_info["ram_mb"]),
        }

        logger.info(
            "RAM: %dMB, CPU: %s, MCU: %d, Kamera: %d",
            hw_data["ram_mb"],
            hw_data["cpu_model"],
            hw_data["mcu_count"],
            hw_data["camera_count"],
        )

        self._update_step("hw_detect", COMPLETED, data=hw_data)

    def step_wifi(self) -> None:
        """Step 3: WiFi configuration."""
        self._update_step("wifi", RUNNING)
        logger.info("Ag taramasi baslatiliyor...")

        # Check if already connected
        ip_info = _get_current_ip()
        if ip_info["ip"] != "yok" and ip_info["interface"] != "yok":
            logger.info("Zaten bagli: %s (%s)", ip_info["ip"], ip_info["interface"])
            self._update_step("wifi", COMPLETED, data={
                "connected": True,
                "ip": ip_info["ip"],
                "interface": ip_info["interface"],
                "networks": [],
            })
            return

        # Scan networks
        networks = _scan_wifi()
        self._update_step("wifi", WAITING_INPUT, data={
            "connected": False,
            "networks": networks,
            "ip": "yok",
        })

        if self.non_interactive:
            logger.info("Non-interactive: WiFi adimi atlaniyor.")
            self._update_step("wifi", SKIPPED)
            return

        # Wait for wifi_connect command from UI
        while self._running:
            cmd = self._wait_for_command(timeout=30)
            if cmd is None:
                # Timeout — rescan and wait again
                networks = _scan_wifi()
                self._update_step("wifi", WAITING_INPUT, data={
                    "connected": False,
                    "networks": networks,
                    "ip": "yok",
                })
                continue

            if cmd.get("command") == "wifi_connect":
                args = cmd.get("args", {})
                ssid = args.get("ssid", "")
                password = args.get("password", "")
                logger.info("WiFi baglanti denemesi: %s", ssid)

                self._update_step("wifi", RUNNING, data={
                    "connecting_to": ssid,
                })

                success = _connect_wifi(ssid, password)
                if success:
                    time.sleep(2)  # Wait for IP assignment
                    ip_info = _get_current_ip()
                    logger.info("WiFi baglandi: %s", ip_info["ip"])
                    self._update_step("wifi", COMPLETED, data={
                        "connected": True,
                        "ip": ip_info["ip"],
                        "interface": ip_info["interface"],
                        "ssid": ssid,
                    })
                    return
                else:
                    logger.warning("WiFi baglanti basarisiz: %s", ssid)
                    self._update_step("wifi", WAITING_INPUT, data={
                        "connected": False,
                        "networks": networks,
                        "error": f"Baglanti basarisiz: {ssid}",
                    })

            elif cmd.get("command") == "wifi_skip":
                logger.info("WiFi adimi kullanici tarafindan atlandi.")
                self._update_step("wifi", SKIPPED)
                return

            elif cmd.get("command") == "wifi_rescan":
                networks = _scan_wifi()
                self._update_step("wifi", WAITING_INPUT, data={
                    "connected": False,
                    "networks": networks,
                    "ip": "yok",
                })

    def step_profile(self) -> None:
        """Step 4: Profile selection."""
        self._update_step("profile", RUNNING)

        ram_mb = self._hw_info.get("ram_mb", 1024)
        recommended = _get_recommended_profile(ram_mb)

        if self.profile_override:
            profile = self.profile_override.upper()
            if profile not in PROFILE_DESC:
                logger.warning("Gecersiz profil '%s', onerilen: %s", profile, recommended)
                profile = recommended
            logger.info("Profil override: %s", profile)
            self._state["selected_profile"] = profile
            self._update_step("profile", COMPLETED, data={
                "selected": profile,
                "recommended": recommended,
                "profiles": PROFILE_DESC,
            })
            return

        if self.non_interactive:
            logger.info("Non-interactive: onerilen profil secildi: %s", recommended)
            self._state["selected_profile"] = recommended
            self._update_step("profile", COMPLETED, data={
                "selected": recommended,
                "recommended": recommended,
                "profiles": PROFILE_DESC,
            })
            return

        # Wait for UI to select profile
        self._update_step("profile", WAITING_INPUT, data={
            "recommended": recommended,
            "ram_mb": ram_mb,
            "profiles": PROFILE_DESC,
        })

        cmd = self._wait_for_command("select_profile")
        if cmd:
            profile = cmd.get("args", {}).get("profile", recommended).upper()
            if profile not in PROFILE_DESC:
                profile = recommended
        else:
            profile = recommended

        logger.info("Secilen profil: %s", profile)
        self._state["selected_profile"] = profile
        self._update_step("profile", COMPLETED, data={
            "selected": profile,
            "recommended": recommended,
        })

    def step_install(self) -> None:
        """Step 5: Package and model installation based on profile."""
        self._update_step("install", RUNNING)
        profile = self._state.get("selected_profile", "STANDARD")
        models = MODEL_MATRIX.get(profile, [])

        # Save profile first
        self._save_profile(profile)

        if not models or self.skip_models:
            reason = "model yok" if not models else "skip-models"
            logger.info("Model kurulumu atlaniyor (%s)", reason)
            self._update_step("install", COMPLETED, data={
                "models_needed": models,
                "models_downloaded": [],
                "skipped": True,
            })
            return

        # Check Ollama
        if not _check_command("ollama"):
            logger.warning("Ollama bulunamadi, model indirilemez.")
            self._update_step("install", COMPLETED, data={
                "models_needed": models,
                "models_downloaded": [],
                "error": "Ollama bulunamadi",
            })
            return

        # Download models
        downloaded = []
        for i, model in enumerate(models):
            logger.info("Model indiriliyor (%d/%d): %s", i + 1, len(models), model)
            self._update_step("install", RUNNING, data={
                "models_needed": models,
                "current_model": model,
                "current_index": i + 1,
                "total_models": len(models),
                "models_downloaded": downloaded,
            })

            result = _run_cmd(["ollama", "pull", model], timeout=1800)
            if result.returncode == 0:
                downloaded.append(model)
                logger.info("Model indirildi: %s", model)
            else:
                logger.error("Model indirilemedi: %s", model)

        self._update_step("install", COMPLETED, data={
            "models_needed": models,
            "models_downloaded": downloaded,
            "success": len(downloaded) == len(models),
        })

    def step_tuning(self) -> None:
        """Step 6: System tuning (zram, memory limits, service optimizer)."""
        self._update_step("tuning", RUNNING)
        profile = self._state.get("selected_profile", "STANDARD")
        logger.info("Sistem ayarlari uygulaniyor (profil: %s)...", profile)

        results = {"zram": False, "memory_limits": False, "service_optimizer": False}

        # Service optimizer
        r = _run_cmd([
            sys.executable, "-m", "tools.kos_service_optimizer", "apply", profile,
        ])
        results["service_optimizer"] = r.returncode == 0
        self._update_step("tuning", RUNNING, data={"sub_step": "zram", **results})

        # zram
        r = _run_cmd(["modprobe", "zram"])
        if r.returncode == 0:
            ram_mb = self._hw_info.get("ram_mb", 1024)
            zram_mb = min(ram_mb // 2, 2048)
            zram_conf = "/etc/systemd/zram-generator.conf"
            try:
                with open(zram_conf, "w") as f:
                    f.write(
                        f"[zram0]\nzram-size = {zram_mb}\n"
                        "compression-algorithm = zstd\nswap-priority = 100\n"
                    )
                _run_cmd(["sysctl", "-w", "vm.swappiness=60"])
                results["zram"] = True
            except OSError:
                pass
        self._update_step("tuning", RUNNING, data={"sub_step": "memory_limits", **results})

        # Memory limits
        limits_map = {
            "LIGHT": {"klipper.service": "200M", "moonraker.service": "200M"},
            "STANDARD": {
                "klipper.service": "300M",
                "moonraker.service": "300M",
                "KlipperScreen.service": "200M",
                "crowsnest.service": "200M",
                "klipperos-ai-monitor.service": "300M",
            },
            "FULL": {
                "klipper.service": "400M",
                "moonraker.service": "400M",
                "KlipperScreen.service": "300M",
                "crowsnest.service": "300M",
                "klipperos-ai-monitor.service": "500M",
                "ollama.service": "4G",
            },
        }
        svc_limits = limits_map.get(profile, {})
        mem_ok = True
        for svc, limit in svc_limits.items():
            override_dir = f"/etc/systemd/system/{svc}.d"
            override_file = os.path.join(override_dir, "memory-limit.conf")
            try:
                os.makedirs(override_dir, exist_ok=True)
                with open(override_file, "w") as f:
                    f.write(f"[Service]\nMemoryMax={limit}\n")
            except OSError:
                mem_ok = False
        if svc_limits:
            _run_cmd(["systemctl", "daemon-reload"])
        results["memory_limits"] = mem_ok

        logger.info("Sistem ayarlari: %s", results)
        self._update_step("tuning", COMPLETED, data=results)

    def step_complete(self) -> None:
        """Step 7: Write completion marker and finalize."""
        self._update_step("complete", RUNNING)
        profile = self._state.get("selected_profile", "STANDARD")

        # Write .oobe-done marker
        try:
            KOS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(OOBE_DONE_MARKER, "w") as f:
                f.write(f"completed={datetime.now().isoformat()}\n")
                f.write(f"profile={profile}\nversion={VERSION}\n")
            logger.info("OOBE tamamlandi, isaret dosyasi olusturuldu.")
        except OSError as exc:
            logger.error("Isaret dosyasi yazilamadi: %s", exc)

        # Summary data
        hw = self._hw_info
        models = MODEL_MATRIX.get(profile, [])
        ip_info = _get_current_ip()
        self._update_step("complete", COMPLETED, data={
            "profile": profile,
            "ram_mb": hw.get("ram_mb", 0),
            "models": models,
            "ip": ip_info.get("ip", "yok"),
            "mcu_count": len(hw.get("mcu_devices", [])),
            "camera_count": len(hw.get("cameras", [])),
        })

        if not self.non_interactive:
            # Wait for reboot command from UI (optional)
            logger.info("Yeniden baslatma bekleniyor (UI'dan veya 60s sonra devam)...")
            cmd = self._wait_for_command("reboot", timeout=60)
            if cmd:
                logger.info("Yeniden baslatiliyor...")
                _run_cmd(["systemctl", "reboot"])

    # -- Profile save helper --

    def _save_profile(self, profile: str) -> None:
        """Save selected profile to config files."""
        try:
            KOS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(PROFILE_FILE, "w") as f:
                f.write(profile)

            # YAML/JSON profile
            try:
                import yaml
                use_yaml = True
            except ImportError:
                use_yaml = False

            data = {
                "version": VERSION,
                "profile": profile,
                "timestamp": datetime.now().isoformat(),
                "hardware": {
                    "ram_mb": self._hw_info.get("ram_mb", 0),
                    "cpu": self._hw_info.get("cpu", {}),
                },
                "models": MODEL_MATRIX.get(profile, []),
                "mcu_devices": self._hw_info.get("mcu_devices", []),
                "cameras": self._hw_info.get("cameras", []),
            }
            with open(PROFILE_YML, "w") as f:
                if use_yaml:
                    yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
                else:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.write("\n")

            logger.info("Profil kaydedildi: %s → %s", profile, PROFILE_FILE)
        except OSError as exc:
            logger.error("Profil kaydi basarisiz: %s", exc)

    # -- Main run loop --

    def run(self) -> None:
        """Execute the full OOBE wizard."""
        # Signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        logger.info("OOBE baslatiliyor (non_interactive=%s)", self.non_interactive)

        # Check if already done
        if OOBE_DONE_MARKER.exists():
            logger.info("OOBE zaten tamamlanmis. Tekrar calistirmak icin 'kos-oobe reset' kullanin.")
            return

        # Write initial state
        self._write_state()

        # Execute steps in order
        step_funcs = {
            "welcome": self.step_welcome,
            "hw_detect": self.step_hw_detect,
            "wifi": self.step_wifi,
            "profile": self.step_profile,
            "install": self.step_install,
            "tuning": self.step_tuning,
            "complete": self.step_complete,
        }

        for step_name in STEPS:
            if not self._running:
                logger.info("OOBE durduruldu (sinyal).")
                self._state["error"] = "Kullanici tarafindan durduruldu"
                self._write_state()
                return

            logger.info("Adim: %s (%s)", step_name, STEP_NAMES_TR[step_name])
            try:
                step_funcs[step_name]()
            except Exception as exc:
                logger.error("Adim '%s' hatasi: %s", step_name, exc, exc_info=True)
                self._update_step(step_name, ERROR, data={"error": str(exc)})
                self._state["error"] = f"Adim '{step_name}' hatasi: {exc}"
                self._write_state()
                # Continue to next step on error
                continue

        logger.info("OOBE tamamlandi!")


# ---------------------------------------------------------------------------
# CLI Entry Points
# ---------------------------------------------------------------------------

def cmd_run(args) -> None:
    """Run the OOBE wizard."""
    # Root check
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print(f"{RED}{TAG}{NC} Bu komut root yetkisi gerektirir.")
        print(f"  Kullanim: {BOLD}sudo kos-oobe run{NC}")
        sys.exit(1)

    oobe = OobeOrchestrator(
        non_interactive=args.non_interactive,
        profile_override=args.profile,
        skip_models=args.skip_models,
    )
    oobe.run()


def cmd_status(_args) -> None:
    """Show OOBE status."""
    print()
    if OOBE_DONE_MARKER.exists():
        print(f"{GREEN}{TAG}{NC} OOBE: {BOLD}TAMAMLANDI{NC}")
        try:
            with open(OOBE_DONE_MARKER) as f:
                for line in f:
                    k, _, v = line.strip().partition("=")
                    if k and v:
                        print(f"  {CYAN}{k}:{NC} {v}")
        except OSError:
            pass
    else:
        print(f"{YELLOW}{TAG}{NC} OOBE: {BOLD}HENUZ TAMAMLANMADI{NC}")

    # Show state file if exists
    state = _read_json(STATE_FILE)
    if state:
        print(f"\n  {CYAN}Mevcut adim:{NC}  {state.get('current_step', 'yok')}")
        print(f"  {CYAN}Ilerleme:{NC}     %{state.get('progress_percent', 0)}")
        print(f"  {CYAN}Son guncelleme:{NC} {state.get('updated_at', 'yok')}")

        steps = state.get("steps", {})
        print(f"\n  {BOLD}Adimlar:{NC}")
        for step in STEPS:
            info = steps.get(step, {})
            status = info.get("status", "?")
            name = STEP_NAMES_TR.get(step, step)
            icon = {
                COMPLETED: f"{GREEN}✓{NC}",
                RUNNING: f"{CYAN}►{NC}",
                WAITING_INPUT: f"{YELLOW}?{NC}",
                PENDING: f"{DIM}○{NC}",
                ERROR: f"{RED}✗{NC}",
                SKIPPED: f"{DIM}─{NC}",
            }.get(status, "?")
            print(f"    {icon} {name:20s} [{status}]")
    else:
        print(f"\n  {DIM}Durum dosyasi bulunamadi.{NC}")
    print()


def cmd_reset(_args) -> None:
    """Reset OOBE state to allow re-running."""
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print(f"{RED}{TAG}{NC} Root yetkisi gerekli: sudo kos-oobe reset")
        sys.exit(1)

    removed = []
    for path in (OOBE_DONE_MARKER, STATE_FILE, COMMAND_FILE):
        try:
            if path.exists():
                path.unlink()
                removed.append(str(path))
        except OSError as exc:
            print(f"{RED}{TAG}{NC} Silinemedi: {path} — {exc}")

    if removed:
        print(f"{GREEN}{TAG}{NC} Sifirlandi: {', '.join(removed)}")
    else:
        print(f"{YELLOW}{TAG}{NC} Silinecek dosya bulunamadi.")
    print(f"  OOBE'yi tekrar calistirmak icin: {BOLD}sudo kos-oobe run{NC}")


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="KlipperOS-AI — OOBE (Ilk Acilis Sihirbazi)",
        prog="kos-oobe",
    )
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="OOBE sihirbazini baslat")
    p_run.add_argument("--non-interactive", action="store_true",
                       help="Soru sormadan varsayilanlarla calistir")
    p_run.add_argument("--profile", type=str, default=None,
                       help="Profili onceden belirle (LIGHT/STANDARD/FULL)")
    p_run.add_argument("--skip-models", action="store_true",
                       help="Model indirme adimini atla")
    p_run.set_defaults(func=cmd_run)

    # status
    p_status = sub.add_parser("status", help="OOBE durumunu goster")
    p_status.set_defaults(func=cmd_status)

    # reset
    p_reset = sub.add_parser("reset", help="OOBE'yi sifirla")
    p_reset.set_defaults(func=cmd_reset)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()

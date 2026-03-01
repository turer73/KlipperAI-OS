# KlipperOS-AI v2.1 Implementation Plan: System Management UI & AI Config Manager

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform KlipperOS-AI into a full appliance OS with KlipperScreen system management panels, AI-driven config editing, and 2GB RAM optimization via zram+zstd.

**Architecture:** KlipperScreen native GTK3 panels communicate through a shared KOS System API module. AI Config Manager uses Moonraker File API for config read/write with automatic backup. zram with zstd compression provides ~3x effective swap memory. All panels lazy-load to minimize RAM usage.

**Tech Stack:** Python 3.9+, GTK3 (gi), VTE3, psutil, nmcli, systemctl, Moonraker REST API, zram, zstd, systemd cgroups

**Existing patterns to follow:**
- Tools: `tools/kos_update.py`, `tools/kos_backup.py` (argparse + subprocess.run)
- AI: `ai-monitor/print_monitor.py` (MoonrakerClient class, requests-based)
- Tests: `tests/test_flow_guard.py` (pytest, sys.path injection, class-based)
- Python 3.9 compat: `from typing import Optional, List, Dict` (not `X | None`)

---

### Task 1: KOS System API Module

Core shared module that all KlipperScreen panels use for system operations.

**Files:**
- Create: `ks-panels/kos_system_api.py`
- Create: `tests/test_kos_system_api.py`

**Step 1: Write the failing tests**

```python
# tests/test_kos_system_api.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import pytest
from unittest.mock import patch, MagicMock
from kos_system_api import KosSystemAPI


class TestSystemInfo:
    def test_get_cpu_info_returns_dict(self):
        api = KosSystemAPI()
        info = api.get_cpu_info()
        assert isinstance(info, dict)
        assert "usage_percent" in info
        assert "temperature" in info
        assert "frequency_mhz" in info

    def test_get_memory_info_returns_dict(self):
        api = KosSystemAPI()
        info = api.get_memory_info()
        assert isinstance(info, dict)
        assert "total_mb" in info
        assert "used_mb" in info
        assert "percent" in info
        assert "zram_total_mb" in info

    def test_get_disk_info_returns_dict(self):
        api = KosSystemAPI()
        info = api.get_disk_info()
        assert isinstance(info, dict)
        assert "total_gb" in info
        assert "used_gb" in info
        assert "percent" in info

    def test_get_uptime_returns_string(self):
        api = KosSystemAPI()
        uptime = api.get_uptime()
        assert isinstance(uptime, str)


class TestNetworkOperations:
    @patch("kos_system_api.subprocess.run")
    def test_get_wifi_networks_returns_list(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="MyWiFi:80:WPA2\nGuest:50:OPEN\n"
        )
        api = KosSystemAPI()
        networks = api.get_wifi_networks()
        assert isinstance(networks, list)
        assert len(networks) == 2
        assert networks[0]["ssid"] == "MyWiFi"
        assert networks[0]["signal"] == 80

    @patch("kos_system_api.subprocess.run")
    def test_get_current_ip_returns_dict(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="192.168.1.100\n"
        )
        api = KosSystemAPI()
        ip_info = api.get_current_ip()
        assert isinstance(ip_info, dict)
        assert "ip" in ip_info

    @patch("kos_system_api.subprocess.run")
    def test_connect_wifi(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        api = KosSystemAPI()
        result = api.connect_wifi("MySSID", "password123")
        assert result is True


class TestServiceOperations:
    @patch("kos_system_api.subprocess.run")
    def test_get_service_status(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="active\n"
        )
        api = KosSystemAPI()
        status = api.get_service_status("klipper")
        assert status == "active"

    @patch("kos_system_api.subprocess.run")
    def test_list_kos_services(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="active\n")
        api = KosSystemAPI()
        services = api.list_kos_services()
        assert isinstance(services, list)
        assert len(services) > 0
        assert services[0]["name"] in [
            "klipper", "moonraker", "nginx",
            "KlipperScreen", "crowsnest", "klipperos-ai-monitor"
        ]

    @patch("kos_system_api.subprocess.run")
    def test_restart_service(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        api = KosSystemAPI()
        result = api.restart_service("klipper")
        assert result is True


class TestTailscale:
    @patch("kos_system_api.subprocess.run")
    def test_get_tailscale_status(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"BackendState":"Running","Self":{"TailscaleIPs":["100.64.0.1"]}}\n'
        )
        api = KosSystemAPI()
        status = api.get_tailscale_status()
        assert isinstance(status, dict)
        assert "connected" in status
        assert "ip" in status

    @patch("kos_system_api.subprocess.run")
    def test_tailscale_up(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        api = KosSystemAPI()
        result = api.tailscale_up()
        assert result is True


class TestPowerOperations:
    @patch("kos_system_api.subprocess.run")
    def test_shutdown(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        api = KosSystemAPI()
        result = api.shutdown()
        assert result is True
        mock_run.assert_called_once()

    @patch("kos_system_api.subprocess.run")
    def test_reboot(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        api = KosSystemAPI()
        result = api.reboot()
        assert result is True


class TestMoonrakerFileAPI:
    @patch("kos_system_api.requests.get")
    def test_read_config(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text="[extruder]\nrotation_distance: 33.5\n"
        )
        api = KosSystemAPI()
        content = api.read_config("printer.cfg")
        assert "[extruder]" in content

    @patch("kos_system_api.requests.post")
    def test_write_config(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"result": "ok"})
        api = KosSystemAPI()
        result = api.write_config("printer.cfg", "[extruder]\nrotation_distance: 33.5\n")
        assert result is True

    @patch("kos_system_api.requests.get")
    def test_read_config_failure(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        api = KosSystemAPI()
        content = api.read_config("printer.cfg")
        assert content is None
```

**Step 2: Run tests to verify they fail**

Run: `cd C:/linux_ai/KlipperOS-AI && python -m pytest tests/test_kos_system_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kos_system_api'`

**Step 3: Implement KOS System API**

```python
# ks-panels/kos_system_api.py
"""KlipperOS-AI System API — shared module for all KlipperScreen panels."""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, List, Dict

import requests

logger = logging.getLogger("KOS-SystemAPI")

MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")
KLIPPER_HOME = Path(os.environ.get("KLIPPER_HOME", "/home/klipper"))

KOS_SERVICES = [
    "klipper", "moonraker", "nginx",
    "KlipperScreen", "crowsnest", "klipperos-ai-monitor",
]


def _run(cmd: List[str], timeout: int = 10) -> subprocess.CompletedProcess:
    """Run command with captured output."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


class KosSystemAPI:
    """Unified system API for KlipperScreen panels."""

    def __init__(self, moonraker_url: str = MOONRAKER_URL):
        self.moonraker_url = moonraker_url

    # ── CPU / Memory / Disk ─────────────────────────────────────────

    def get_cpu_info(self) -> Dict:
        try:
            import psutil
            temp = -1.0
            temps = psutil.sensors_temperatures()
            if temps:
                for name in ("cpu_thermal", "coretemp", "soc_thermal"):
                    if name in temps and temps[name]:
                        temp = temps[name][0].current
                        break
            freq = psutil.cpu_freq()
            return {
                "usage_percent": psutil.cpu_percent(interval=0.5),
                "temperature": temp,
                "frequency_mhz": freq.current if freq else 0,
                "core_count": psutil.cpu_count(logical=True),
            }
        except ImportError:
            return {"usage_percent": 0, "temperature": -1, "frequency_mhz": 0, "core_count": 0}

    def get_memory_info(self) -> Dict:
        try:
            import psutil
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            return {
                "total_mb": round(mem.total / 1048576),
                "used_mb": round(mem.used / 1048576),
                "available_mb": round(mem.available / 1048576),
                "percent": mem.percent,
                "zram_total_mb": round(swap.total / 1048576),
                "zram_used_mb": round(swap.used / 1048576),
            }
        except ImportError:
            return {"total_mb": 0, "used_mb": 0, "available_mb": 0,
                    "percent": 0, "zram_total_mb": 0, "zram_used_mb": 0}

    def get_disk_info(self) -> Dict:
        try:
            import psutil
            disk = psutil.disk_usage("/")
            return {
                "total_gb": round(disk.total / 1073741824, 1),
                "used_gb": round(disk.used / 1073741824, 1),
                "free_gb": round(disk.free / 1073741824, 1),
                "percent": disk.percent,
            }
        except ImportError:
            return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0}

    def get_uptime(self) -> str:
        try:
            import psutil
            import time
            boot = psutil.boot_time()
            elapsed = int(time.time() - boot)
            days, remainder = divmod(elapsed, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)
            if days > 0:
                return f"{days}g {hours}s {minutes}dk"
            return f"{hours}s {minutes}dk"
        except ImportError:
            return "bilinmiyor"

    # ── Network / WiFi ──────────────────────────────────────────────

    def get_wifi_networks(self) -> List[Dict]:
        try:
            result = _run([
                "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"
            ])
            if result.returncode != 0:
                return []
            networks = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(":")
                if len(parts) >= 3:
                    networks.append({
                        "ssid": parts[0],
                        "signal": int(parts[1]) if parts[1].isdigit() else 0,
                        "security": parts[2],
                    })
            return networks
        except Exception:
            return []

    def get_current_ip(self) -> Dict:
        result = {"ip": "bilinmiyor", "interface": "bilinmiyor", "hostname": "klipperos"}
        try:
            r = _run(["hostname", "-I"])
            if r.returncode == 0 and r.stdout.strip():
                result["ip"] = r.stdout.strip().split()[0]
            r2 = _run(["hostname"])
            if r2.returncode == 0:
                result["hostname"] = r2.stdout.strip()
        except Exception:
            pass
        return result

    def connect_wifi(self, ssid: str, password: str) -> bool:
        try:
            result = _run(["nmcli", "dev", "wifi", "connect", ssid, "password", password])
            return result.returncode == 0
        except Exception:
            return False

    def disconnect_wifi(self) -> bool:
        try:
            result = _run(["nmcli", "dev", "disconnect", "wlan0"])
            return result.returncode == 0
        except Exception:
            return False

    # ── Tailscale ───────────────────────────────────────────────────

    def get_tailscale_status(self) -> Dict:
        try:
            result = _run(["tailscale", "status", "--json"])
            if result.returncode != 0:
                return {"connected": False, "ip": "", "hostname": ""}
            data = json.loads(result.stdout)
            state = data.get("BackendState", "Stopped")
            ip = ""
            self_info = data.get("Self", {})
            ips = self_info.get("TailscaleIPs", [])
            if ips:
                ip = ips[0]
            return {
                "connected": state == "Running",
                "state": state,
                "ip": ip,
                "hostname": self_info.get("HostName", ""),
            }
        except Exception:
            return {"connected": False, "ip": "", "hostname": ""}

    def tailscale_up(self) -> bool:
        try:
            result = _run(["sudo", "tailscale", "up"], timeout=30)
            return result.returncode == 0
        except Exception:
            return False

    def tailscale_down(self) -> bool:
        try:
            result = _run(["sudo", "tailscale", "down"])
            return result.returncode == 0
        except Exception:
            return False

    # ── Services ────────────────────────────────────────────────────

    def get_service_status(self, name: str) -> str:
        try:
            result = _run(["systemctl", "is-active", name])
            return result.stdout.strip()
        except Exception:
            return "unknown"

    def list_kos_services(self) -> List[Dict]:
        services = []
        for name in KOS_SERVICES:
            status = self.get_service_status(name)
            services.append({"name": name, "status": status})
        return services

    def restart_service(self, name: str) -> bool:
        if name not in KOS_SERVICES:
            return False
        try:
            result = _run(["sudo", "systemctl", "restart", name])
            return result.returncode == 0
        except Exception:
            return False

    def stop_service(self, name: str) -> bool:
        if name not in KOS_SERVICES:
            return False
        try:
            result = _run(["sudo", "systemctl", "stop", name])
            return result.returncode == 0
        except Exception:
            return False

    def start_service(self, name: str) -> bool:
        if name not in KOS_SERVICES:
            return False
        try:
            result = _run(["sudo", "systemctl", "start", name])
            return result.returncode == 0
        except Exception:
            return False

    # ── Power ───────────────────────────────────────────────────────

    def shutdown(self) -> bool:
        try:
            result = _run(["sudo", "systemctl", "poweroff"])
            return result.returncode == 0
        except Exception:
            return False

    def reboot(self) -> bool:
        try:
            result = _run(["sudo", "systemctl", "reboot"])
            return result.returncode == 0
        except Exception:
            return False

    # ── Moonraker File API ──────────────────────────────────────────

    def read_config(self, filename: str) -> Optional[str]:
        try:
            url = f"{self.moonraker_url}/server/files/config/{filename}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return resp.text
            return None
        except Exception:
            return None

    def write_config(self, filename: str, content: str) -> bool:
        try:
            url = f"{self.moonraker_url}/server/files/upload"
            files = {"file": (filename, content)}
            data = {"root": "config"}
            resp = requests.post(url, files=files, data=data, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def restart_klipper(self) -> bool:
        try:
            resp = requests.post(f"{self.moonraker_url}/printer/restart", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def firmware_restart(self) -> bool:
        try:
            resp = requests.post(f"{self.moonraker_url}/printer/firmware_restart", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def get_mcu_info(self) -> List[Dict]:
        """Query Moonraker for all MCU temperature/voltage info."""
        try:
            resp = requests.get(
                f"{self.moonraker_url}/printer/objects/query",
                params={"mcu": ""},
                timeout=5,
            )
            if resp.status_code != 200:
                return []
            data = resp.json().get("result", {}).get("status", {})
            mcus = []
            for key, val in data.items():
                if key.startswith("mcu"):
                    name = key if key == "mcu" else key.replace("mcu ", "")
                    mcu_data = {
                        "name": name,
                        "temperature": val.get("mcu_temp", {}).get("temperature", -1),
                        "version": val.get("mcu_version", ""),
                        "last_stats": val.get("last_stats", {}),
                    }
                    mcus.append(mcu_data)
            return mcus
        except Exception:
            return []

    # ── Log Reading ─────────────────────────────────────────────────

    def read_log_tail(self, log_name: str, lines: int = 50) -> str:
        log_paths = {
            "klippy": KLIPPER_HOME / "printer_data" / "logs" / "klippy.log",
            "moonraker": KLIPPER_HOME / "printer_data" / "logs" / "moonraker.log",
            "crowsnest": KLIPPER_HOME / "printer_data" / "logs" / "crowsnest.log",
            "ai-monitor": Path("/var/log/klipperos-ai-monitor.log"),
        }
        log_path = log_paths.get(log_name)
        if not log_path or not log_path.exists():
            return f"Log dosyasi bulunamadi: {log_name}"
        try:
            result = _run(["tail", f"-n{lines}", str(log_path)])
            return result.stdout if result.returncode == 0 else "Okunamadi"
        except Exception as e:
            return f"Hata: {e}"
```

**Step 4: Run tests to verify they pass**

Run: `cd C:/linux_ai/KlipperOS-AI && python -m pytest tests/test_kos_system_api.py -v`
Expected: All 15+ tests PASS

**Step 5: Commit**

```bash
git add ks-panels/kos_system_api.py tests/test_kos_system_api.py
git commit -m "feat: add KOS System API module for KlipperScreen panels"
```

---

### Task 2: AI Config Manager Module

Moonraker File API uzerinden Klipper config dosyalarini otomatik duzenleyen modul.

**Files:**
- Create: `ai-monitor/config_manager.py`
- Create: `tests/test_config_manager.py`

**Step 1: Write the failing tests**

```python
# tests/test_config_manager.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
from unittest.mock import patch, MagicMock
from config_manager import ConfigManager, ConfigChange


class TestConfigParsing:
    def test_parse_config_sections(self):
        cm = ConfigManager(moonraker_url="http://localhost:7125")
        content = "[extruder]\nrotation_distance: 33.5\nnozzle_diameter: 0.4\n\n[heater_bed]\nmax_temp: 120\n"
        sections = cm.parse_sections(content)
        assert "extruder" in sections
        assert "heater_bed" in sections
        assert sections["extruder"]["rotation_distance"] == "33.5"

    def test_update_config_value(self):
        cm = ConfigManager(moonraker_url="http://localhost:7125")
        content = "[extruder]\nrotation_distance: 33.5\nnozzle_diameter: 0.4\n"
        updated = cm.update_value(content, "extruder", "rotation_distance", "33.68")
        assert "rotation_distance: 33.68" in updated
        assert "nozzle_diameter: 0.4" in updated

    def test_update_nonexistent_key_appends(self):
        cm = ConfigManager(moonraker_url="http://localhost:7125")
        content = "[extruder]\nnozzle_diameter: 0.4\n"
        updated = cm.update_value(content, "extruder", "pressure_advance", "0.05")
        assert "pressure_advance: 0.05" in updated


class TestWhitelist:
    def test_allowed_parameter(self):
        cm = ConfigManager(moonraker_url="http://localhost:7125")
        assert cm.is_allowed("extruder", "pid_kp") is True
        assert cm.is_allowed("extruder", "pressure_advance") is True
        assert cm.is_allowed("input_shaper", "shaper_freq_x") is True

    def test_blocked_parameter(self):
        cm = ConfigManager(moonraker_url="http://localhost:7125")
        assert cm.is_allowed("extruder", "step_pin") is False
        assert cm.is_allowed("stepper_x", "position_max") is False
        assert cm.is_allowed("mcu", "serial") is False


class TestConfigChange:
    def test_config_change_creation(self):
        change = ConfigChange(
            section="extruder",
            key="pid_kp",
            old_value="22.20",
            new_value="23.45",
            reason="PID_CALIBRATE result"
        )
        assert change.section == "extruder"
        assert change.key == "pid_kp"
        assert change.reason == "PID_CALIBRATE result"

    def test_config_change_str(self):
        change = ConfigChange("extruder", "pid_kp", "22.20", "23.45", "PID tune")
        s = str(change)
        assert "extruder" in s
        assert "pid_kp" in s


class TestApplyChanges:
    @patch("config_manager.requests.get")
    @patch("config_manager.requests.post")
    def test_apply_single_change(self, mock_post, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text="[extruder]\npid_kp: 22.20\npid_ki: 1.10\npid_kd: 114.00\n"
        )
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"result": "ok"})

        cm = ConfigManager(moonraker_url="http://localhost:7125")
        change = ConfigChange("extruder", "pid_kp", "22.20", "23.45", "PID tune")
        result = cm.apply_changes("printer.cfg", [change])
        assert result is True

    @patch("config_manager.requests.get")
    def test_apply_change_blocked_param(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text="[mcu]\nserial: /dev/ttyUSB0\n"
        )
        cm = ConfigManager(moonraker_url="http://localhost:7125")
        change = ConfigChange("mcu", "serial", "/dev/ttyUSB0", "/dev/ttyACM0", "bad")
        result = cm.apply_changes("printer.cfg", [change])
        assert result is False
```

**Step 2: Run tests to verify they fail**

Run: `cd C:/linux_ai/KlipperOS-AI && python -m pytest tests/test_config_manager.py -v`
Expected: FAIL

**Step 3: Implement Config Manager**

```python
# ai-monitor/config_manager.py
"""KlipperOS-AI Config Manager — AI-driven Klipper config editing via Moonraker File API."""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict

import requests

logger = logging.getLogger("KOS-ConfigManager")

MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")

# Whitelist: only these section/key combinations can be auto-edited
ALLOWED_PARAMS: Dict[str, List[str]] = {
    "extruder": [
        "pid_kp", "pid_ki", "pid_kd",
        "pressure_advance", "pressure_advance_smooth_time",
        "rotation_distance",
    ],
    "heater_bed": ["pid_kp", "pid_ki", "pid_kd"],
    "input_shaper": [
        "shaper_freq_x", "shaper_freq_y",
        "shaper_type", "shaper_type_x", "shaper_type_y",
    ],
    "kos_flowguard": [
        "heater_threshold", "sg_clog_threshold", "sg_empty_threshold",
        "ai_spaghetti_threshold", "ai_no_extrusion_threshold",
        "warning_escalation_count",
    ],
}


@dataclass
class ConfigChange:
    section: str
    key: str
    old_value: str
    new_value: str
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def __str__(self) -> str:
        return f"[{self.section}] {self.key}: {self.old_value} -> {self.new_value} ({self.reason})"


class ConfigManager:
    """Manages Klipper config file edits via Moonraker File API."""

    def __init__(self, moonraker_url: str = MOONRAKER_URL):
        self.moonraker_url = moonraker_url
        self.change_log: List[ConfigChange] = []

    def is_allowed(self, section: str, key: str) -> bool:
        """Check if a parameter is in the edit whitelist."""
        allowed_keys = ALLOWED_PARAMS.get(section, [])
        return key in allowed_keys

    def parse_sections(self, content: str) -> Dict[str, Dict[str, str]]:
        """Parse config content into {section: {key: value}} dict."""
        sections: Dict[str, Dict[str, str]] = {}
        current_section = None
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            section_match = re.match(r"^\[(.+)\]$", line)
            if section_match:
                current_section = section_match.group(1)
                sections[current_section] = {}
                continue
            if current_section and ":" in line:
                key, _, value = line.partition(":")
                sections[current_section][key.strip()] = value.strip()
        return sections

    def update_value(self, content: str, section: str, key: str, new_value: str) -> str:
        """Update a single key in config content. Appends if key doesn't exist."""
        lines = content.split("\n")
        in_section = False
        found = False
        result = []
        section_header = f"[{section}]"

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == section_header:
                in_section = True
                result.append(line)
                continue
            if in_section and stripped.startswith("["):
                if not found:
                    result.append(f"{key}: {new_value}")
                    found = True
                in_section = False
            if in_section and stripped.startswith(f"{key}:"):
                result.append(f"{key}: {new_value}")
                found = True
                continue
            result.append(line)

        if in_section and not found:
            result.append(f"{key}: {new_value}")

        return "\n".join(result)

    def read_config(self, filename: str) -> Optional[str]:
        """Read config file via Moonraker File API."""
        try:
            url = f"{self.moonraker_url}/server/files/config/{filename}"
            resp = requests.get(url, timeout=5)
            return resp.text if resp.status_code == 200 else None
        except Exception as e:
            logger.error("Config okuma hatasi: %s", e)
            return None

    def write_config(self, filename: str, content: str) -> bool:
        """Write config file via Moonraker File API."""
        try:
            url = f"{self.moonraker_url}/server/files/upload"
            files = {"file": (filename, content)}
            data = {"root": "config"}
            resp = requests.post(url, files=files, data=data, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error("Config yazma hatasi: %s", e)
            return False

    def send_notification(self, message: str) -> None:
        """Send notification via Moonraker."""
        try:
            requests.post(
                f"{self.moonraker_url}/server/notifications/create",
                json={"title": "KOS Config Manager", "message": message},
                timeout=5,
            )
        except Exception:
            pass

    def apply_changes(self, filename: str, changes: List[ConfigChange]) -> bool:
        """Apply a list of config changes to a file. Returns True on success."""
        # Validate all changes against whitelist
        for change in changes:
            if not self.is_allowed(change.section, change.key):
                logger.warning("Blocked config change: %s", change)
                return False

        # Read current config
        content = self.read_config(filename)
        if content is None:
            logger.error("Config okunamadi: %s", filename)
            return False

        # Apply each change
        for change in changes:
            content = self.update_value(content, change.section, change.key, change.new_value)

        # Write updated config
        if not self.write_config(filename, content):
            logger.error("Config yazilamadi: %s", filename)
            return False

        # Log and notify
        for change in changes:
            self.change_log.append(change)
            logger.info("Config degistirildi: %s", change)

        msg = f"{len(changes)} parametre guncellendi: " + ", ".join(
            f"{c.section}.{c.key}" for c in changes
        )
        self.send_notification(msg)
        return True

    def apply_pid_result(self, heater: str, kp: float, ki: float, kd: float) -> bool:
        """Apply PID calibration results."""
        section = heater  # "extruder" or "heater_bed"
        changes = [
            ConfigChange(section, "pid_kp", "", f"{kp:.3f}", "PID_CALIBRATE"),
            ConfigChange(section, "pid_ki", "", f"{ki:.3f}", "PID_CALIBRATE"),
            ConfigChange(section, "pid_kd", "", f"{kd:.3f}", "PID_CALIBRATE"),
        ]
        return self.apply_changes("printer.cfg", changes)

    def apply_pressure_advance(self, pa_value: float) -> bool:
        """Apply pressure advance calibration result."""
        change = ConfigChange(
            "extruder", "pressure_advance", "", f"{pa_value:.4f}", "PA Calibration"
        )
        return self.apply_changes("printer.cfg", [change])

    def apply_input_shaper(self, freq_x: float, freq_y: float,
                           type_x: str = "mzv", type_y: str = "mzv") -> bool:
        """Apply input shaper calibration results."""
        changes = [
            ConfigChange("input_shaper", "shaper_freq_x", "", f"{freq_x:.1f}", "Shaper Cal"),
            ConfigChange("input_shaper", "shaper_freq_y", "", f"{freq_y:.1f}", "Shaper Cal"),
            ConfigChange("input_shaper", "shaper_type_x", "", type_x, "Shaper Cal"),
            ConfigChange("input_shaper", "shaper_type_y", "", type_y, "Shaper Cal"),
        ]
        return self.apply_changes("printer.cfg", changes)
```

**Step 4: Run tests to verify they pass**

Run: `cd C:/linux_ai/KlipperOS-AI && python -m pytest tests/test_config_manager.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add ai-monitor/config_manager.py tests/test_config_manager.py
git commit -m "feat: add AI Config Manager with Moonraker File API"
```

---

### Task 3: zram + Memory Optimization Setup

zram+zstd script, systemd service, cgroup memory limits, log rotation.

**Files:**
- Create: `scripts/setup-zram.sh`
- Create: `config/systemd/kos-zram.service`
- Create: `config/systemd/memory-limits/klipper.conf`
- Create: `config/systemd/memory-limits/moonraker.conf`
- Create: `config/systemd/memory-limits/klipperscreen.conf`
- Create: `config/systemd/memory-limits/ai-monitor.conf`
- Create: `config/systemd/memory-limits/crowsnest.conf`
- Create: `config/systemd/memory-limits/nginx.conf`
- Create: `config/logrotate/klipperos`

**Step 1: Create zram setup script**

```bash
# scripts/setup-zram.sh
#!/bin/bash
# KlipperOS-AI — zram + zstd Memory Optimization
set -euo pipefail

GREEN='\033[0;32m'
NC='\033[0m'
log() { echo -e "${GREEN}[ZRAM]${NC} $*"; }

setup_zram() {
    log "zram yapilandiriliyor..."

    # Load zram module
    modprobe zram num_devices=1

    # Calculate size: 50% of total RAM
    local total_kb
    total_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local zram_size=$(( total_kb * 1024 / 2 ))

    # Configure zram0
    echo zstd > /sys/block/zram0/comp_algorithm
    echo "$zram_size" > /sys/block/zram0/disksize

    # Format and enable
    mkswap /dev/zram0
    swapon -p 100 /dev/zram0

    log "zram aktif: $(( zram_size / 1048576 )) MB, algoritma: zstd"
}

setup_kernel_params() {
    log "Kernel parametreleri ayarlaniyor..."

    # zram icin yuksek swappiness
    sysctl -w vm.swappiness=150
    sysctl -w vm.page-cluster=0
    sysctl -w vm.dirty_expire_centisecs=1500
    sysctl -w vm.dirty_writeback_centisecs=500

    # Kalici ayarlar
    cat > /etc/sysctl.d/99-kos-zram.conf << 'SYSCTL'
vm.swappiness=150
vm.page-cluster=0
vm.dirty_expire_centisecs=1500
vm.dirty_writeback_centisecs=500
SYSCTL
}

install_earlyoom() {
    log "earlyoom kuruluyor..."
    if ! command -v earlyoom &>/dev/null; then
        apt-get install -y earlyoom 2>/dev/null || true
    fi
    if command -v earlyoom &>/dev/null; then
        systemctl enable earlyoom 2>/dev/null || true
        systemctl start earlyoom 2>/dev/null || true
        log "earlyoom aktif."
    fi
}

main() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Root yetkisi gerekli." >&2
        exit 1
    fi
    setup_zram
    setup_kernel_params
    install_earlyoom
    log "Bellek optimizasyonu tamamlandi."
}

main "$@"
```

**Step 2: Create systemd service for zram**

```ini
# config/systemd/kos-zram.service
[Unit]
Description=KlipperOS-AI zram Compressed Swap
DefaultDependencies=false
After=local-fs.target
Before=sysinit.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/klipperos-ai/scripts/setup-zram.sh
ExecStop=/bin/bash -c 'swapoff /dev/zram0 2>/dev/null; echo 1 > /sys/block/zram0/reset 2>/dev/null || true'

[Install]
WantedBy=sysinit.target
```

**Step 3: Create cgroup memory limits (one file per service)**

```ini
# config/systemd/memory-limits/klipper.conf
[Service]
MemoryMax=256M
MemoryHigh=200M
```

```ini
# config/systemd/memory-limits/moonraker.conf
[Service]
MemoryMax=200M
MemoryHigh=160M
```

```ini
# config/systemd/memory-limits/klipperscreen.conf
[Service]
MemoryMax=150M
MemoryHigh=120M
```

```ini
# config/systemd/memory-limits/ai-monitor.conf
[Service]
MemoryMax=200M
MemoryHigh=160M
```

```ini
# config/systemd/memory-limits/crowsnest.conf
[Service]
MemoryMax=100M
MemoryHigh=80M
```

```ini
# config/systemd/memory-limits/nginx.conf
[Service]
MemoryMax=50M
MemoryHigh=40M
```

**Step 4: Create log rotation config**

```
# config/logrotate/klipperos
/home/klipper/printer_data/logs/*.log {
    daily
    rotate 3
    compress
    compresscmd /usr/bin/zstd
    compressext .zst
    uncompresscmd /usr/bin/unzstd
    missingok
    notifempty
    maxsize 10M
    copytruncate
}

/var/log/klipperos-*.log {
    daily
    rotate 3
    compress
    compresscmd /usr/bin/zstd
    compressext .zst
    uncompresscmd /usr/bin/unzstd
    missingok
    notifempty
    maxsize 5M
    copytruncate
}
```

**Step 5: Commit**

```bash
git add scripts/setup-zram.sh config/systemd/ config/logrotate/
git commit -m "feat: add zram+zstd memory optimization, cgroup limits, log rotation"
```

---

### Task 4: KlipperScreen Panel Base — Power Panel (Simplest First)

Start with the simplest panel to establish the pattern all other panels follow.

**Files:**
- Create: `ks-panels/kos_power.py`
- Create: `tests/test_ks_panels.py`

**Step 1: Write the test**

```python
# tests/test_ks_panels.py
"""Tests for KlipperScreen panels — import and basic structure checks."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))

import pytest
from unittest.mock import patch, MagicMock


class TestPowerPanel:
    def test_import(self):
        from kos_power import PANEL_TITLE, PANEL_ACTIONS
        assert PANEL_TITLE == "Guc Yonetimi"
        assert "shutdown" in PANEL_ACTIONS
        assert "reboot" in PANEL_ACTIONS
        assert "restart_klipper" in PANEL_ACTIONS

    @patch("kos_system_api.subprocess.run")
    def test_shutdown_action(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from kos_power import execute_action
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = execute_action(api, "shutdown")
        assert result is True

    @patch("kos_system_api.subprocess.run")
    def test_reboot_action(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from kos_power import execute_action
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        result = execute_action(api, "reboot")
        assert result is True
```

**Step 2: Run tests to verify they fail**

Run: `cd C:/linux_ai/KlipperOS-AI && python -m pytest tests/test_ks_panels.py::TestPowerPanel -v`

**Step 3: Implement Power Panel**

```python
# ks-panels/kos_power.py
"""KlipperOS-AI — Power Management Panel for KlipperScreen."""

import logging
from typing import Optional

from kos_system_api import KosSystemAPI

logger = logging.getLogger("KOS-Power")

PANEL_TITLE = "Guc Yonetimi"
PANEL_ACTIONS = {
    "shutdown": "Sistemi Kapat",
    "reboot": "Yeniden Baslat",
    "restart_klipper": "Klipper Yeniden Baslat",
    "restart_moonraker": "Moonraker Yeniden Baslat",
    "restart_firmware": "Firmware Restart",
}


def execute_action(api: KosSystemAPI, action: str) -> bool:
    """Execute a power action."""
    if action == "shutdown":
        return api.shutdown()
    elif action == "reboot":
        return api.reboot()
    elif action == "restart_klipper":
        return api.restart_service("klipper")
    elif action == "restart_moonraker":
        return api.restart_service("moonraker")
    elif action == "restart_firmware":
        return api.firmware_restart()
    return False


def get_panel_data(api: KosSystemAPI) -> dict:
    """Get data for the power panel display."""
    return {
        "title": PANEL_TITLE,
        "actions": PANEL_ACTIONS,
        "uptime": api.get_uptime(),
    }


# --- GTK Panel (used by KlipperScreen) ---
# NOTE: GTK imports are conditional — only when running inside KlipperScreen
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    class PowerPanel:
        """KlipperScreen power management panel."""

        def __init__(self, api: Optional[KosSystemAPI] = None):
            self.api = api or KosSystemAPI()

        def build_ui(self) -> Gtk.Box:
            """Build the GTK panel UI."""
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.set_margin_top(20)
            box.set_margin_start(20)
            box.set_margin_end(20)

            # Title
            title = Gtk.Label()
            title.set_markup(f"<b>{PANEL_TITLE}</b>")
            title.set_halign(Gtk.Align.CENTER)
            box.pack_start(title, False, False, 10)

            # Uptime
            uptime_label = Gtk.Label(label=f"Calisma Suresi: {self.api.get_uptime()}")
            box.pack_start(uptime_label, False, False, 5)

            # Action buttons
            for action_id, label in PANEL_ACTIONS.items():
                btn = Gtk.Button(label=label)
                btn.connect("clicked", self._on_action, action_id)
                btn.set_size_request(-1, 50)
                box.pack_start(btn, False, False, 5)

            return box

        def _on_action(self, _button, action_id: str) -> None:
            """Handle action button click."""
            result = execute_action(self.api, action_id)
            if result:
                logger.info("Power action basarili: %s", action_id)
            else:
                logger.error("Power action basarisiz: %s", action_id)

except ImportError:
    pass  # GTK not available (headless/test environment)
```

**Step 4: Run tests**

Run: `cd C:/linux_ai/KlipperOS-AI && python -m pytest tests/test_ks_panels.py::TestPowerPanel -v`
Expected: PASS

**Step 5: Commit**

```bash
git add ks-panels/kos_power.py tests/test_ks_panels.py
git commit -m "feat: add Power Management panel for KlipperScreen"
```

---

### Task 5: System Info Panel (CPU/RAM/Disk + MCU)

**Files:**
- Create: `ks-panels/kos_sysinfo.py`
- Modify: `tests/test_ks_panels.py` (append TestSysInfoPanel)

**Step 1: Write tests (append to tests/test_ks_panels.py)**

```python
class TestSysInfoPanel:
    def test_import(self):
        from kos_sysinfo import PANEL_TITLE, get_panel_data
        assert PANEL_TITLE == "Sistem Bilgisi"

    def test_get_panel_data(self):
        from kos_sysinfo import get_panel_data
        from kos_system_api import KosSystemAPI
        api = KosSystemAPI()
        data = get_panel_data(api)
        assert "cpu" in data
        assert "memory" in data
        assert "disk" in data
        assert "uptime" in data
```

**Step 2: Implement** (`ks-panels/kos_sysinfo.py`)

Module providing: `PANEL_TITLE`, `get_panel_data(api)`, `SysInfoPanel` GTK class.
Panel data: `api.get_cpu_info()`, `api.get_memory_info()`, `api.get_disk_info()`, `api.get_uptime()`, `api.get_mcu_info()`.
GTK UI: Labels showing CPU%, temp, RAM used/total, disk used/total, MCU temps. Auto-refresh every 2 seconds via `GLib.timeout_add_seconds`.

**Step 3: Run tests, commit**

```bash
git commit -m "feat: add System Info panel with MCU monitoring"
```

---

### Task 6: Network Panel (WiFi/Ethernet)

**Files:**
- Create: `ks-panels/kos_network.py`
- Modify: `tests/test_ks_panels.py`

Panel provides: WiFi SSID list, signal strength, connect/disconnect buttons, current IP display.
Uses `api.get_wifi_networks()`, `api.get_current_ip()`, `api.connect_wifi(ssid, password)`.
Password entry via `Gtk.Entry` with visibility toggle — works with both physical and on-screen keyboard.

**Commit:** `"feat: add Network panel with WiFi management"`

---

### Task 7: Tailscale VPN Panel

**Files:**
- Create: `ks-panels/kos_tailscale.py`
- Modify: `tests/test_ks_panels.py`

Panel provides: Connection status, Tailscale IP, connect/disconnect buttons.
Uses `api.get_tailscale_status()`, `api.tailscale_up()`, `api.tailscale_down()`.

**Commit:** `"feat: add Tailscale VPN panel"`

---

### Task 8: Service Management Panel

**Files:**
- Create: `ks-panels/kos_services.py`
- Modify: `tests/test_ks_panels.py`

Panel provides: List of KOS services with status (active/inactive), start/stop/restart buttons.
Uses `api.list_kos_services()`, `api.restart_service()`, `api.stop_service()`, `api.start_service()`.

**Commit:** `"feat: add Service Management panel"`

---

### Task 9: Update Panel

**Files:**
- Create: `ks-panels/kos_updates.py`
- Modify: `tests/test_ks_panels.py`

Panel provides: Check for updates, update individual components, progress indicator.
Imports from `tools.kos_update`: `git_check_updates()`, `git_update()`.

**Commit:** `"feat: add Update Management panel"`

---

### Task 10: Backup Panel

**Files:**
- Create: `ks-panels/kos_backup_panel.py`
- Modify: `tests/test_ks_panels.py`

Panel provides: List backups, create new, restore selected, delete selected.
Imports from `tools.kos_backup` module functions.

**Commit:** `"feat: add Backup Management panel"`

---

### Task 11: MCU Management Panel

**Files:**
- Create: `ks-panels/kos_mcu_panel.py`
- Modify: `tests/test_ks_panels.py`

Panel provides: Scan MCU boards, show board info, flash firmware.
Imports from `tools.kos_mcu`: `find_serial_ports()`, `load_board_db()`.

**Commit:** `"feat: add MCU Management panel"`

---

### Task 12: AI Settings Panel

**Files:**
- Create: `ks-panels/kos_ai_settings.py`
- Modify: `tests/test_ks_panels.py`

Panel provides: AI Monitor on/off toggle, check interval slider (5-30s), detection threshold sliders, model info, FlowGuard enable/disable.
Reads/writes AI monitor environment config via Moonraker File API.

**Commit:** `"feat: add AI Settings panel"`

---

### Task 13: Log Viewer Panel

**Files:**
- Create: `ks-panels/kos_logs.py`
- Modify: `tests/test_ks_panels.py`

Panel provides: Dropdown to select log source (klippy/moonraker/crowsnest/ai-monitor), scrollable text view with last 50 lines, refresh button, auto-scroll to bottom.
Uses `api.read_log_tail(log_name, lines=50)`.

**Commit:** `"feat: add Log Viewer panel"`

---

### Task 14: VTE3 Terminal Panel

**Files:**
- Create: `ks-panels/kos_terminal.py`
- Modify: `tests/test_ks_panels.py`

Panel provides: Full VTE3 terminal emulator, runs as `klipper` user shell, font size +/- buttons, copy/paste support.
Uses `gi.require_version("Vte", "2.91")`, `Vte.Terminal()`.
Lazy-load: terminal process spawns only when panel opens, killed on panel close.

**Commit:** `"feat: add VTE3 Terminal panel with keyboard/mouse support"`

---

### Task 15: Installer Updates & KlipperScreen Menu Configuration

**Files:**
- Modify: `scripts/install-standard.sh`
- Modify: `scripts/install-light.sh`
- Modify: `config/klipperscreen/KlipperScreen.conf`

**Changes to install-standard.sh:**

Add new function `install_system_panels()`:
- Install `psutil`, `gir1.2-vte-2.91`, `matchbox-keyboard` packages
- Copy `ks-panels/*.py` to `${KLIPPER_HOME}/KlipperScreen/ks_includes/panels/`
- Run `scripts/setup-zram.sh`
- Install cgroup memory limit overrides to `/etc/systemd/system/<service>.d/memory.conf`
- Install logrotate config to `/etc/logrotate.d/klipperos`
- Enable `kos-zram.service`

Add `install_system_panels` call in `main()` after `install_ai_monitor`.

**Changes to install-light.sh:**

Add `setup_zram()` function:
- Run `scripts/setup-zram.sh`
- Install earlyoom
- Install cgroup memory limits

Add `setup_zram` call in `main()`.

**Changes to KlipperScreen.conf:**

Add system menu entries:
```ini
[menu __main system]
name: Sistem
icon: settings

[menu __main system network]
name: Ag Ayarlari
icon: network
panel: kos_network

[menu __main system tailscale]
name: Tailscale VPN
icon: network
panel: kos_tailscale

[menu __main system updates]
name: Guncelleme
icon: refresh
panel: kos_updates

[menu __main system backup]
name: Yedekleme
icon: sd
panel: kos_backup_panel

[menu __main system mcu]
name: MCU Yonetimi
icon: chip
panel: kos_mcu_panel

[menu __main system sysinfo]
name: Sistem Bilgisi
icon: info
panel: kos_sysinfo

[menu __main system ai]
name: AI Ayarlari
icon: klipper
panel: kos_ai_settings

[menu __main system services]
name: Servis Yonetimi
icon: settings
panel: kos_services

[menu __main system logs]
name: Log Goruntule
icon: logs
panel: kos_logs

[menu __main system terminal]
name: Terminal
icon: console
panel: kos_terminal

[menu __main system power]
name: Guc
icon: shutdown
panel: kos_power
```

**Commit:**

```bash
git commit -m "feat: installer updates with zram, panels, KlipperScreen menus"
```

---

### Task 16: README Update

**Files:**
- Modify: `README.md`

Add sections:
- System Management UI overview (panel list)
- AI Config Manager description
- zram + Memory Optimization section
- Terminal access section
- Updated profile table (STANDARD now includes system panels)
- Updated project tree

**Commit:** `"docs: update README with v2.1 system management features"`

---

### Task 17: Final Integration Test

**Run all tests:**
```bash
cd C:/linux_ai/KlipperOS-AI && python -m pytest tests/ -v
```
Expected: All tests pass.

**Verify all new files exist:**
```bash
ls ks-panels/kos_*.py
ls ai-monitor/config_manager.py
ls scripts/setup-zram.sh
ls config/systemd/kos-zram.service
ls config/systemd/memory-limits/*.conf
ls config/logrotate/klipperos
```

**Verify CLI tools still parse:**
```bash
python -c "from tools.kos_profile import main"
python -c "from tools.kos_update import main"
python -c "from tools.kos_backup import main"
python -c "from tools.kos_mcu import main"
python -c "from tools.kos_calibrate import main"
```

**Verify panel imports:**
```bash
cd C:/linux_ai/KlipperOS-AI
python -c "from ks_panels.kos_system_api import KosSystemAPI; print('API OK')"
python -c "from ks_panels.kos_power import PANEL_TITLE; print('Power OK')"
python -c "from ks_panels.kos_sysinfo import PANEL_TITLE; print('SysInfo OK')"
python -c "from ai_monitor.config_manager import ConfigManager; print('ConfigMgr OK')"
```

**Commit:** `"test: final v2.1 integration verification"`

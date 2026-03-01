"""KOS System API - Unified system interface for KlipperScreen panels.

Provides a single class `KosSystemAPI` that all KlipperScreen panels use
to query system information, manage services, interact with Moonraker,
and perform network/power operations.

Designed for Raspberry Pi / SBC running KlipperOS with Python 3.9+.
"""
import io
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import requests

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore[assignment]
    HAS_PSUTIL = False

logger = logging.getLogger("kos_system_api")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MOONRAKER_URL: str = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")
KLIPPER_HOME: Path = Path(os.environ.get("KLIPPER_HOME", "/home/klipper"))

KOS_SERVICES: List[str] = [
    "klipper",
    "moonraker",
    "nginx",
    "KlipperScreen",
    "crowsnest",
    "klipperos-ai-monitor",
]

LOG_PATHS: Dict[str, Path] = {
    "klippy": KLIPPER_HOME / "printer_data" / "logs" / "klippy.log",
    "moonraker": KLIPPER_HOME / "printer_data" / "logs" / "moonraker.log",
    "crowsnest": KLIPPER_HOME / "printer_data" / "logs" / "crowsnest.log",
    "ai-monitor": KLIPPER_HOME / "printer_data" / "logs" / "ai-monitor.log",
}


class KosSystemAPI:
    """Unified system API for KlipperScreen panels."""

    # -------------------------------------------------------------------
    # Internal helper
    # -------------------------------------------------------------------
    def _run(
        self,
        cmd: List[str],
        timeout: int = 10,
    ) -> subprocess.CompletedProcess:
        """Run a subprocess command and return the CompletedProcess result.

        Captures stdout/stderr as text.  Never raises on non-zero exit code;
        callers should inspect ``returncode`` instead.
        """
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out: %s", " ".join(cmd))
            cp = subprocess.CompletedProcess(cmd, returncode=-1, stdout="", stderr="timeout")
            return cp
        except Exception as exc:  # noqa: BLE001
            logger.error("Command failed: %s — %s", " ".join(cmd), exc)
            cp = subprocess.CompletedProcess(cmd, returncode=-1, stdout="", stderr=str(exc))
            return cp

    # ===================================================================
    # System Info (psutil)
    # ===================================================================
    def get_cpu_info(self) -> Dict:
        """Return CPU usage, temperature, frequency, and core count."""
        if not HAS_PSUTIL:
            try:
                import psutil as _ps
            except ImportError:
                return {
                    "usage_percent": 0.0,
                    "temperature": 0.0,
                    "frequency_mhz": 0.0,
                    "core_count": 0,
                }
            local_psutil = _ps
        else:
            local_psutil = psutil

        usage = local_psutil.cpu_percent(interval=0.5)
        freq_info = local_psutil.cpu_freq()
        frequency = freq_info.current if freq_info else 0.0
        cores = local_psutil.cpu_count() or 0

        temperature = 0.0
        try:
            temps = local_psutil.sensors_temperatures()
            for key in ("cpu_thermal", "coretemp", "soc_thermal"):
                if key in temps and temps[key]:
                    temperature = temps[key][0].current
                    break
        except (AttributeError, KeyError):
            pass

        return {
            "usage_percent": usage,
            "temperature": temperature,
            "frequency_mhz": frequency,
            "core_count": cores,
        }

    def get_memory_info(self) -> Dict:
        """Return RAM and ZRAM usage information in MB."""
        if not HAS_PSUTIL:
            try:
                import psutil as _ps
            except ImportError:
                return {
                    "total_mb": 0.0,
                    "used_mb": 0.0,
                    "available_mb": 0.0,
                    "percent": 0.0,
                    "zram_total_mb": 0.0,
                    "zram_used_mb": 0.0,
                }
            local_psutil = _ps
        else:
            local_psutil = psutil

        vm = local_psutil.virtual_memory()
        swap = local_psutil.swap_memory()

        mb = 1024 * 1024
        return {
            "total_mb": round(vm.total / mb, 1),
            "used_mb": round(vm.used / mb, 1),
            "available_mb": round(vm.available / mb, 1),
            "percent": vm.percent,
            "zram_total_mb": round(swap.total / mb, 1),
            "zram_used_mb": round(swap.used / mb, 1),
        }

    def get_disk_info(self) -> Dict:
        """Return root partition disk usage in GB."""
        if not HAS_PSUTIL:
            try:
                import psutil as _ps
            except ImportError:
                return {
                    "total_gb": 0.0,
                    "used_gb": 0.0,
                    "free_gb": 0.0,
                    "percent": 0.0,
                }
            local_psutil = _ps
        else:
            local_psutil = psutil

        du = local_psutil.disk_usage("/")
        gb = 1024 ** 3
        return {
            "total_gb": round(du.total / gb, 1),
            "used_gb": round(du.used / gb, 1),
            "free_gb": round(du.free / gb, 1),
            "percent": du.percent,
        }

    def get_uptime(self) -> str:
        """Return system uptime as a human-readable string (Xg Ys Zdk)."""
        result = self._run(["cat", "/proc/uptime"])
        if result.returncode != 0:
            return "bilinmiyor"

        try:
            raw = result.stdout.strip().split()[0] if " " in result.stdout else result.stdout.strip()
            total = int(float(raw))
        except (ValueError, IndexError):
            return "bilinmiyor"

        days = total // 86400
        hours = (total % 86400) // 3600
        minutes = (total % 3600) // 60

        parts: List[str] = []
        if days:
            parts.append(f"{days}g")
        if hours:
            parts.append(f"{hours}s")
        if minutes:
            parts.append(f"{minutes}dk")
        return " ".join(parts) if parts else "0dk"

    # ===================================================================
    # Network (nmcli)
    # ===================================================================
    def get_wifi_networks(self) -> List[Dict]:
        """Scan and return visible WiFi networks via nmcli."""
        result = self._run([
            "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
        ])
        if result.returncode != 0:
            return []

        networks: List[Dict] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 3:
                networks.append({
                    "ssid": parts[0],
                    "signal": parts[1],
                    "security": parts[2],
                })
        return networks

    def get_current_ip(self) -> Dict:
        """Return current IP address, interface, and hostname."""
        hostname_result = self._run(["hostname"])
        hostname = hostname_result.stdout.strip() if hostname_result.returncode == 0 else "unknown"

        ip_result = self._run(["ip", "route", "get", "1.1.1.1"])
        ip_addr = "unknown"
        interface = "unknown"

        if ip_result.returncode == 0:
            output = ip_result.stdout
            # Parse "dev <iface>" and "src <ip>"
            dev_match = re.search(r"dev\s+(\S+)", output)
            src_match = re.search(r"src\s+(\S+)", output)
            if dev_match:
                interface = dev_match.group(1)
            if src_match:
                ip_addr = src_match.group(1)

        return {
            "ip": ip_addr,
            "interface": interface,
            "hostname": hostname,
        }

    def connect_wifi(self, ssid: str, password: str) -> bool:
        """Connect to a WiFi network using nmcli."""
        result = self._run([
            "nmcli", "dev", "wifi", "connect", ssid, "password", password,
        ], timeout=30)
        return result.returncode == 0

    def disconnect_wifi(self) -> bool:
        """Disconnect the active WiFi connection."""
        result = self._run(["nmcli", "dev", "disconnect", "wlan0"], timeout=10)
        return result.returncode == 0

    # ===================================================================
    # Tailscale
    # ===================================================================
    def get_tailscale_status(self) -> Dict:
        """Query tailscale status and return connection info."""
        result = self._run(["tailscale", "status"], timeout=10)

        default = {
            "connected": False,
            "state": "unknown",
            "ip": "",
            "hostname": "",
        }

        if result.returncode != 0:
            return default

        output = result.stdout.strip()
        if not output:
            return default

        # Parse the first non-comment line for our own node info
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            # Format: <IP>  <hostname>  <user@>  <OS>  <flags>
            parts = line.split()
            if len(parts) >= 2:
                return {
                    "connected": True,
                    "state": "running",
                    "ip": parts[0],
                    "hostname": parts[1],
                }

        return default

    def tailscale_up(self) -> bool:
        """Bring Tailscale connection up."""
        result = self._run(["tailscale", "up"], timeout=30)
        return result.returncode == 0

    def tailscale_down(self) -> bool:
        """Bring Tailscale connection down."""
        result = self._run(["tailscale", "down"], timeout=10)
        return result.returncode == 0

    # ===================================================================
    # Services (systemctl)
    # ===================================================================
    def get_service_status(self, name: str) -> str:
        """Return service status: 'active', 'inactive', or 'unknown'."""
        result = self._run([
            "systemctl", "is-active", name,
        ])
        status = result.stdout.strip() if result.returncode == 0 else "unknown"
        return status if status in ("active", "inactive") else "unknown"

    def list_kos_services(self) -> List[Dict]:
        """Return status of all KOS-managed services."""
        services: List[Dict] = []
        for name in KOS_SERVICES:
            status = self.get_service_status(name)
            services.append({"name": name, "status": status})
        return services

    def _service_action(self, action: str, name: str) -> bool:
        """Execute a systemctl action on a whitelisted service."""
        if name not in KOS_SERVICES:
            logger.warning("Service '%s' not in KOS whitelist, refusing %s", name, action)
            return False
        result = self._run(["sudo", "systemctl", action, name], timeout=15)
        return result.returncode == 0

    def restart_service(self, name: str) -> bool:
        """Restart a whitelisted KOS service."""
        return self._service_action("restart", name)

    def stop_service(self, name: str) -> bool:
        """Stop a whitelisted KOS service."""
        return self._service_action("stop", name)

    def start_service(self, name: str) -> bool:
        """Start a whitelisted KOS service."""
        return self._service_action("start", name)

    # ===================================================================
    # Power (systemctl)
    # ===================================================================
    def shutdown(self) -> bool:
        """Shut down the system."""
        result = self._run(["sudo", "systemctl", "poweroff"], timeout=10)
        return result.returncode == 0

    def reboot(self) -> bool:
        """Reboot the system."""
        result = self._run(["sudo", "systemctl", "reboot"], timeout=10)
        return result.returncode == 0

    # ===================================================================
    # Moonraker File API (HTTP / requests)
    # ===================================================================
    def read_config(self, filename: str) -> Optional[str]:
        """Read a configuration file via Moonraker's file API.

        GET /server/files/config/{filename}
        """
        url = f"{MOONRAKER_URL}/server/files/config/{filename}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.text
            logger.warning("read_config %s returned %d", filename, resp.status_code)
            return None
        except requests.RequestException as exc:
            logger.error("read_config %s failed: %s", filename, exc)
            return None

    def write_config(self, filename: str, content: str) -> bool:
        """Write a configuration file via Moonraker's upload API.

        POST /server/files/upload  (multipart form with 'root=config')
        """
        url = f"{MOONRAKER_URL}/server/files/upload"
        try:
            files = {
                "file": (filename, io.BytesIO(content.encode("utf-8")), "text/plain"),
            }
            data = {"root": "config"}
            resp = requests.post(url, files=files, data=data, timeout=10)
            return resp.status_code == 200
        except requests.RequestException as exc:
            logger.error("write_config %s failed: %s", filename, exc)
            return False

    def restart_klipper(self) -> bool:
        """Send a printer restart command to Moonraker.

        POST /printer/restart
        """
        try:
            resp = requests.post(f"{MOONRAKER_URL}/printer/restart", timeout=10)
            return resp.status_code == 200
        except requests.RequestException as exc:
            logger.error("restart_klipper failed: %s", exc)
            return False

    def firmware_restart(self) -> bool:
        """Send a firmware restart command to Moonraker.

        POST /printer/firmware_restart
        """
        try:
            resp = requests.post(f"{MOONRAKER_URL}/printer/firmware_restart", timeout=10)
            return resp.status_code == 200
        except requests.RequestException as exc:
            logger.error("firmware_restart failed: %s", exc)
            return False

    def get_mcu_info(self) -> List[Dict]:
        """Query MCU temperatures from Moonraker printer objects API."""
        url = f"{MOONRAKER_URL}/printer/objects/query"
        try:
            resp = requests.get(
                url,
                params={"mcu": ""},
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            result = data.get("result", {}).get("status", {})
            mcus: List[Dict] = []
            for key, val in result.items():
                if isinstance(val, dict) and "mcu_temp" in val:
                    mcus.append({
                        "name": key,
                        "temperature": val["mcu_temp"],
                    })
            return mcus
        except (requests.RequestException, ValueError) as exc:
            logger.error("get_mcu_info failed: %s", exc)
            return []

    # ===================================================================
    # Log Reading
    # ===================================================================
    def read_log_tail(self, log_name: str, lines: int = 50) -> str:
        """Read the last N lines of a known KOS log file."""
        log_path = LOG_PATHS.get(log_name)
        if log_path is None:
            return f"Unknown log: {log_name}"

        result = self._run(["tail", "-n", str(lines), str(log_path)])
        if result.returncode == 0:
            return result.stdout
        return f"Could not read {log_name}: {result.stderr}"

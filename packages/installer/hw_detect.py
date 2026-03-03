"""Donanim tespiti — /proc ve /sys dosyalarindan donanim bilgisi okur."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


def recommend_profile(ram_mb: int, cpu_cores: int) -> str:
    """RAM ve CPU'ya gore profil oner."""
    if ram_mb < 1536:
        return "LIGHT"
    if ram_mb >= 4096 and cpu_cores >= 4:
        return "FULL"
    return "STANDARD"


@dataclass
class HardwareInfo:
    """Donanim bilgileri."""

    cpu_model: str
    cpu_cores: int
    cpu_freq_mhz: int
    ram_total_mb: int
    disk_total_mb: int
    has_wifi: bool
    has_ethernet: bool
    board_type: str
    recommended_profile: str

    @property
    def is_force_light(self) -> bool:
        """RAM < 1.5GB ise LIGHT zorunlu."""
        return self.ram_total_mb < 1536

    @classmethod
    def detect(cls) -> HardwareInfo:
        """Sistem donanimini tespit et."""
        # CPU
        cpu_model = "Unknown"
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass

        cpu_cores = os.cpu_count() or 1

        cpu_freq_mhz = 0
        freq_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
        if freq_path.exists():
            try:
                cpu_freq_mhz = int(freq_path.read_text().strip()) // 1000
            except (ValueError, OSError):
                pass

        # RAM
        ram_total_mb = 0
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        ram_total_mb = int(line.split()[1]) // 1024
                        break
        except OSError:
            pass

        # Disk
        disk_total_mb = 0
        try:
            result = subprocess.run(
                ["df", "-BM", "/"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    disk_total_mb = int(lines[1].split()[1].rstrip("M"))
        except (subprocess.TimeoutExpired, ValueError, IndexError):
            pass

        # Network
        has_wifi = False
        has_ethernet = False
        net_dir = Path("/sys/class/net")
        if net_dir.exists():
            for iface in net_dir.iterdir():
                if iface.name == "lo":
                    continue
                if (iface / "wireless").is_dir():
                    has_wifi = True
                elif (iface / "type").exists():
                    try:
                        itype = (iface / "type").read_text().strip()
                        if itype == "1":
                            has_ethernet = True
                    except OSError:
                        pass

        # Board type
        board_type = "x86"
        dt_model = Path("/proc/device-tree/model")
        if dt_model.exists():
            try:
                model_str = dt_model.read_text().strip("\x00").lower()
                if "raspberry" in model_str:
                    board_type = "rpi"
                elif "orange" in model_str:
                    board_type = "orangepi"
                else:
                    board_type = "sbc"
            except OSError:
                pass

        profile = recommend_profile(ram_total_mb, cpu_cores)

        return cls(
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            cpu_freq_mhz=cpu_freq_mhz,
            ram_total_mb=ram_total_mb,
            disk_total_mb=disk_total_mb,
            has_wifi=has_wifi,
            has_ethernet=has_ethernet,
            board_type=board_type,
            recommended_profile=profile,
        )

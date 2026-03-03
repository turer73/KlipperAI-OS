"""Sistem bilgi endpoint'leri."""
from __future__ import annotations

import subprocess

from fastapi import APIRouter

from ..models.printer import SystemInfo, ServiceStatus

router = APIRouter(prefix="/api/v1/system", tags=["system"])

MONITORED_SERVICES = [
    "klipper",
    "moonraker",
    "crowsnest",
    "KlipperScreen",
    "klipperos-ai-monitor",
    "ollama",
]


@router.get("/info", response_model=SystemInfo)
async def get_system_info():
    """CPU / RAM / disk kullanimi."""
    try:
        import psutil

        disk = psutil.disk_usage("/")
        mem = psutil.virtual_memory()
        return SystemInfo(
            cpu_percent=psutil.cpu_percent(interval=0.1),
            ram_used_mb=int(mem.used / 1024 / 1024),
            ram_total_mb=int(mem.total / 1024 / 1024),
            disk_used_gb=round(disk.used / 1024**3, 1),
            disk_total_gb=round(disk.total / 1024**3, 1),
            uptime_seconds=int(psutil.boot_time()),
        )
    except ImportError:
        return SystemInfo()


@router.get("/services", response_model=list[ServiceStatus])
async def get_services():
    """Klipper ekosistemi servis durumlari."""
    results: list[ServiceStatus] = []
    for svc in MONITORED_SERVICES:
        active = False
        enabled = False
        try:
            r = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True,
                text=True,
                timeout=5,
            )
            active = r.stdout.strip() == "active"
            r2 = subprocess.run(
                ["systemctl", "is-enabled", svc],
                capture_output=True,
                text=True,
                timeout=5,
            )
            enabled = r2.stdout.strip() == "enabled"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        results.append(ServiceStatus(name=svc, active=active, enabled=enabled))
    return results

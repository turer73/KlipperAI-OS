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
    "kos-bambu-monitor",
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


@router.post("/services/{service_name}/{action}")
async def toggle_service(service_name: str, action: str):
    """Servis baslat / durdur / yeniden baslat.

    Sadece beyaz listede olan servislere izin verilir.
    """
    ALLOWED = {"kos-bambu-monitor", "crowsnest", "KlipperScreen", "ollama"}
    if service_name not in ALLOWED:
        from fastapi import HTTPException
        raise HTTPException(400, f"'{service_name}' servisi kontrol edilemez")

    if action not in ("start", "stop", "restart"):
        from fastapi import HTTPException
        raise HTTPException(400, f"Gecersiz aksiyon: {action}")

    try:
        r = subprocess.run(
            ["sudo", "systemctl", action, service_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        success = r.returncode == 0

        # Kisa bekle — servis durumunu kontrol et
        import time
        time.sleep(2)

        r2 = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True, text=True, timeout=5,
        )
        is_active = r2.stdout.strip() == "active"

        return {
            "service": service_name,
            "action": action,
            "success": success,
            "is_active": is_active,
            "message": f"{service_name} {action} {'basarili' if success else 'basarisiz'}",
        }
    except subprocess.TimeoutExpired:
        return {"service": service_name, "action": action, "success": False, "message": "Zaman asimi"}

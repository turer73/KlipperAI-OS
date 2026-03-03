"""Ongorucu bakim API endpoint'leri."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/maintenance", tags=["maintenance"])

# PredictiveMaintenanceEngine instance'i global olarak set edilir
_engine = None


def set_engine(engine):
    global _engine
    _engine = engine


@router.get("/status")
async def get_maintenance_status():
    """Mevcut bakim uyarilari ve izleyici durumu."""
    if _engine is None:
        return {"error": "Maintenance engine not initialized"}
    return _engine.status


@router.get("/alerts")
async def get_maintenance_alerts():
    """Aktif bakim uyarilari."""
    if _engine is None:
        return {"alerts": [], "count": 0}
    alerts = _engine.check_maintenance()
    return {
        "alerts": [a.to_dict() for a in alerts],
        "count": len(alerts),
    }


@router.get("/history")
async def get_maintenance_history():
    """Trend verileri ve baski saatleri."""
    if _engine is None:
        return {"error": "Maintenance engine not initialized"}
    return {
        "print_hours": _engine._total_print_hours,
        "trackers": _engine.status["trackers"],
    }


@router.post("/check")
async def trigger_maintenance_check():
    """Talep uzerine bakim kontrolu calistir."""
    if _engine is None:
        return {"error": "Maintenance engine not initialized"}
    _engine._last_check_time = 0  # Cache'i temizle
    alerts = _engine.check_maintenance()
    return {
        "alerts": [a.to_dict() for a in alerts],
        "count": len(alerts),
        "status": "check_complete",
    }

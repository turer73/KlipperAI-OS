"""Sistem kaynak yonetimi API endpoint'leri."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/system/resources", tags=["resources"])


class ResourcePolicyUpdate(BaseModel):
    memory_warning_pct: float | None = None
    memory_critical_pct: float | None = None
    cpu_temp_warning: float | None = None
    cpu_temp_critical: float | None = None


# Resource Manager instance'i global olarak set edilir (main.py'de)
_manager = None


def set_manager(manager):
    global _manager
    _manager = manager


@router.get("")
async def get_resources():
    """Mevcut sistem kaynakları, governor ve aksiyonlar."""
    if _manager is None:
        return {"error": "Resource manager not initialized"}
    return _manager.status


@router.get("/history")
async def get_resource_history():
    """Son 60 metrik noktasi (2sn aralik = 2dk)."""
    if _manager is None:
        return {"history": [], "count": 0}
    history = _manager.history
    return {"history": history, "count": len(history)}


@router.get("/actions")
async def get_recent_actions():
    """Son kaynak yonetimi aksiyonlari."""
    if _manager is None:
        return {"actions": [], "count": 0}
    actions = _manager.recent_actions
    return {"actions": actions, "count": len(actions)}


@router.post("/policy")
async def update_policy(update: ResourcePolicyUpdate):
    """Esik degerlerini guncelle."""
    if _manager is None:
        return {"error": "Resource manager not initialized"}
    if update.memory_warning_pct is not None:
        _manager.policy.memory_warning_pct = update.memory_warning_pct
    if update.memory_critical_pct is not None:
        _manager.policy.memory_critical_pct = update.memory_critical_pct
    if update.cpu_temp_warning is not None:
        _manager.policy.cpu_temp_warning = update.cpu_temp_warning
    if update.cpu_temp_critical is not None:
        _manager.policy.cpu_temp_critical = update.cpu_temp_critical
    return {"status": "ok", "policy": _manager.status["policy"]}

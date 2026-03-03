"""
KlipperOS-AI — Recovery API Router
===================================
Otonom kurtarma motoru REST API.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/recovery", tags=["recovery"])

# Global engine referansi — uygulama baslangicinda set edilir
_engine = None


def set_engine(engine) -> None:
    """Recovery engine referansini ayarla."""
    global _engine
    _engine = engine


@router.get("/status")
async def get_status():
    """Kurtarma motoru durumu."""
    if _engine is None:
        return {"error": "Recovery engine baslatilmamis", "enabled": False}
    return _engine.status


@router.get("/history")
async def get_history():
    """Son kurtarma sonuclari."""
    if _engine is None:
        return {"results": []}
    return {
        "results": [r.to_dict() for r in _engine._history],
        "attempt_counts": dict(_engine._attempt_counts),
    }


@router.post("/enable")
async def set_enabled(enabled: bool = True):
    """Otonom kurtarmayi ac/kapat."""
    if _engine is None:
        return {"error": "Recovery engine baslatilmamis"}
    _engine.set_enabled(enabled)
    return {"enabled": _engine._enabled}


@router.post("/reset-attempts")
async def reset_attempts(category: str = None):
    """Deneme sayacini sifirla."""
    if _engine is None:
        return {"error": "Recovery engine baslatilmamis"}
    _engine.reset_attempts(category)
    return {"attempt_counts": dict(_engine._attempt_counts)}

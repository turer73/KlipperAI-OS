"""
KlipperOS-AI — Calibration API Router
======================================
Auto-calibration orchestrator REST endpoint'leri.

Endpoint'ler:
    POST /api/v1/calibration/start   — Kalibrasyon baslat
    POST /api/v1/calibration/abort   — Kalibrasyonu iptal et
    GET  /api/v1/calibration/status  — Guncel durum
    GET  /api/v1/calibration/history — Onceki kalibrasyon sonucu
"""

from __future__ import annotations

import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import get_moonraker_client
from ..moonraker_client import MoonrakerClient

router = APIRouter(prefix="/api/v1/calibration", tags=["calibration"])

# Global orchestrator — lazy init
_orchestrator = None
_init_lock = threading.Lock()

STATE_PATH = "/var/lib/klipperos-ai/calibration-state.json"


def _import_orchestrator_class():
    """ai-monitor dizini tire icerdigi icin importlib ile yukle."""
    import importlib
    import sys
    from pathlib import Path

    # /opt/klipperos-ai/ai-monitor veya yerel dizin
    base = Path(__file__).resolve().parents[3]  # packages/api/routers -> proje kok
    ai_dir = base / "ai-monitor"
    if str(ai_dir) not in sys.path:
        sys.path.insert(0, str(ai_dir))

    from calibration_orchestrator import CalibrationOrchestrator
    return CalibrationOrchestrator


def _get_orchestrator(mr: MoonrakerClient):
    """Lazy singleton orchestrator."""
    global _orchestrator
    with _init_lock:
        if _orchestrator is None:
            CalibrationOrchestrator = _import_orchestrator_class()
            _orchestrator = CalibrationOrchestrator(
                moonraker=mr,
                state_path=STATE_PATH,
            )
    return _orchestrator


# -- Request / Response Models --

class CalibStartRequest(BaseModel):
    """Kalibrasyon baslatma parametreleri."""
    extruder_temp: int = Field(default=210, ge=150, le=300)
    bed_temp: int = Field(default=60, ge=0, le=120)
    skip_pid: bool = False
    skip_shaper: bool = False
    skip_pa: bool = False
    skip_flow: bool = False
    pa_start: float = Field(default=0.0, ge=0.0, le=2.0)
    pa_end: float = Field(default=0.1, ge=0.0, le=2.0)
    pa_step: float = Field(default=0.005, ge=0.001, le=0.1)


class CalibStatusResponse(BaseModel):
    """Kalibrasyon durumu cevabi."""
    running: bool
    current_step: str
    progress_percent: int
    error: Optional[str] = None
    steps: dict


# -- Endpoints --

@router.post("/start")
async def start_calibration(
    req: CalibStartRequest,
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    """Otomatik kalibrasyon sekansini arka planda baslat."""
    orch = _get_orchestrator(mr)

    if orch.is_running:
        raise HTTPException(409, "Kalibrasyon zaten calisiyor")

    orch.start_async(
        extruder_temp=req.extruder_temp,
        bed_temp=req.bed_temp,
        skip_pid=req.skip_pid,
        skip_shaper=req.skip_shaper,
        skip_pa=req.skip_pa,
        skip_flow=req.skip_flow,
        pa_start=req.pa_start,
        pa_end=req.pa_end,
        pa_step=req.pa_step,
    )
    return {"message": "Kalibrasyon baslatildi", "started": True}


@router.post("/abort")
async def abort_calibration(
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    """Devam eden kalibrasyonu iptal et."""
    orch = _get_orchestrator(mr)

    if not orch.is_running:
        raise HTTPException(409, "Aktif kalibrasyon yok")

    orch.abort()
    return {"message": "Iptal istegi gonderildi", "aborted": True}


@router.get("/status", response_model=CalibStatusResponse)
async def get_calibration_status(
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    """Kalibrasyon durumunu getir."""
    orch = _get_orchestrator(mr)
    state = orch.to_dict()
    return CalibStatusResponse(
        running=orch.is_running,
        current_step=state.get("current_step", "idle"),
        progress_percent=state.get("progress_percent", 0),
        error=state.get("error"),
        steps=state.get("steps", {}),
    )


@router.get("/history")
async def get_calibration_history(
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    """Onceki kalibrasyon sonucunu dosyadan oku."""
    CalibrationOrchestrator = _import_orchestrator_class()
    data = CalibrationOrchestrator.load_state(STATE_PATH)
    if data is None:
        return {"history": None, "message": "Onceki kalibrasyon bulunamadi"}
    return {"history": data}

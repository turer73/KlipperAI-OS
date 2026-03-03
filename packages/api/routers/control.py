"""Yazici kontrol endpoint'leri -- baski duraklat/devam/iptal, G-code, sicaklik."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..dependencies import get_moonraker_client
from ..moonraker_client import MoonrakerClient

router = APIRouter(prefix="/api/v1/printer/control", tags=["control"])

DANGEROUS_GCODE = {"M112", "FIRMWARE_RESTART", "SAVE_CONFIG", "SET_KINEMATIC_POSITION"}
TEMP_LIMITS = {"extruder": 300, "heater_bed": 120}

class GCodeRequest(BaseModel):
    script: str

class TemperatureRequest(BaseModel):
    heater: str
    target: float = Field(ge=0, le=300)

class ActionResponse(BaseModel):
    success: bool
    message: str = ""

@router.post("/pause", response_model=ActionResponse)
async def pause_print(mr: MoonrakerClient = Depends(get_moonraker_client)):
    result = mr.post("/printer/print/pause")
    return ActionResponse(success=result is not None, message="Baski duraklatildi")

@router.post("/resume", response_model=ActionResponse)
async def resume_print(mr: MoonrakerClient = Depends(get_moonraker_client)):
    result = mr.post("/printer/print/resume")
    return ActionResponse(success=result is not None, message="Baski devam ediyor")

@router.post("/cancel", response_model=ActionResponse)
async def cancel_print(mr: MoonrakerClient = Depends(get_moonraker_client)):
    result = mr.post("/printer/print/cancel")
    return ActionResponse(success=result is not None, message="Baski iptal edildi")

@router.post("/gcode", response_model=ActionResponse)
async def send_gcode(
    req: GCodeRequest,
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    cmd = req.script.strip().split()[0].upper() if req.script.strip() else ""
    if cmd in DANGEROUS_GCODE:
        raise HTTPException(403, f"Tehlikeli G-code: {cmd}")
    ok = mr.send_gcode(req.script)
    return ActionResponse(success=ok, message=f"G-code gonderildi: {req.script[:50]}")

@router.post("/temperature", response_model=ActionResponse)
async def set_temperature(
    req: TemperatureRequest,
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    limit = TEMP_LIMITS.get(req.heater, 300)
    if req.target > limit:
        raise HTTPException(422, f"{req.heater} max {limit}C")
    ok = mr.send_gcode(f"SET_HEATER_TEMPERATURE HEATER={req.heater} TARGET={req.target}")
    return ActionResponse(success=ok, message=f"{req.heater}={req.target}C")

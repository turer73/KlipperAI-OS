"""FlowGuard AI monitor endpoint'leri."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from ..models.printer import FlowGuardStatus

router = APIRouter(prefix="/api/v1/flowguard", tags=["flowguard"])

FLOWGUARD_LOG = Path("/var/log/klipperos-ai/flowguard.jsonl")


@router.get("/status", response_model=FlowGuardStatus)
async def get_flowguard_status():
    """Son FlowGuard verdikti."""
    if FLOWGUARD_LOG.exists():
        try:
            lines = FLOWGUARD_LOG.read_text().strip().split("\n")
            if lines:
                last = json.loads(lines[-1])
                return FlowGuardStatus(
                    verdict=last.get("verdict", "OK"),
                    filament_detected=last.get("filament_detected", True),
                    heater_duty=last.get("heater_duty", 0.0),
                    tmc_sg_result=last.get("tmc_sg_result", 0),
                    ai_class=last.get("ai_class", "normal"),
                    current_layer=last.get("current_layer", 0),
                    z_height=last.get("z_height", 0.0),
                )
        except (json.JSONDecodeError, OSError):
            pass
    return FlowGuardStatus()


@router.get("/history", response_model=list[FlowGuardStatus])
async def get_flowguard_history():
    """Son 50 FlowGuard event'i."""
    events: list[FlowGuardStatus] = []
    if FLOWGUARD_LOG.exists():
        try:
            lines = FLOWGUARD_LOG.read_text().strip().split("\n")
            for line in lines[-50:]:
                try:
                    data = json.loads(line)
                    events.append(
                        FlowGuardStatus(
                            verdict=data.get("verdict", "OK"),
                            filament_detected=data.get("filament_detected", True),
                            heater_duty=data.get("heater_duty", 0.0),
                            tmc_sg_result=data.get("tmc_sg_result", 0),
                            ai_class=data.get("ai_class", "normal"),
                            current_layer=data.get("current_layer", 0),
                            z_height=data.get("z_height", 0.0),
                        )
                    )
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
    return events

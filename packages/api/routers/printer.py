"""Yazici durum endpoint'leri -- salt-okunur sorgular."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from ..dependencies import get_moonraker_client
from ..moonraker_client import MoonrakerClient
from ..models.printer import PrintStatus, TemperatureReading

router = APIRouter(prefix="/api/v1/printer", tags=["printer"])

@router.get("/status", response_model=PrintStatus)
async def get_printer_status(
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    data = mr.get_printer_objects("print_stats", "display_status", "extruder", "heater_bed")
    return PrintStatus.from_moonraker(data)

@router.get("/temperatures", response_model=TemperatureReading)
async def get_temperatures(
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    data = mr.get_printer_objects("extruder", "heater_bed")
    return TemperatureReading.from_moonraker(data)

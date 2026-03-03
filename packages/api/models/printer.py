"""Yazici veri modelleri."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PrintStatus(BaseModel):
    state: str = "standby"
    filename: Optional[str] = None
    progress: float = 0.0
    print_duration: int = 0
    total_duration: int = 0
    filament_used: float = 0.0
    current_layer: int = 0
    total_layers: int = 0

    @classmethod
    def from_moonraker(cls, data: dict) -> PrintStatus:
        ps = data.get("print_stats", {})
        ds = data.get("display_status", {})
        info = ps.get("info", {})
        return cls(
            state=ps.get("state", "standby"),
            filename=ps.get("filename"),
            progress=ds.get("progress", 0.0),
            print_duration=int(ps.get("print_duration", 0)),
            total_duration=int(ps.get("total_duration", 0)),
            filament_used=float(ps.get("filament_used", 0.0)),
            current_layer=info.get("current_layer", 0) or 0,
            total_layers=info.get("total_layer", 0) or 0,
        )


class TemperatureReading(BaseModel):
    extruder_current: float = 0.0
    extruder_target: float = 0.0
    bed_current: float = 0.0
    bed_target: float = 0.0
    mcu_temperature: Optional[float] = None

    @classmethod
    def from_moonraker(cls, data: dict) -> TemperatureReading:
        ext = data.get("extruder", {})
        bed = data.get("heater_bed", {})
        return cls(
            extruder_current=ext.get("temperature", 0.0),
            extruder_target=ext.get("target", 0.0),
            bed_current=bed.get("temperature", 0.0),
            bed_target=bed.get("target", 0.0),
        )


class GCodeFileInfo(BaseModel):
    filename: str
    size: int = 0
    modified: float = 0.0


class FlowGuardStatus(BaseModel):
    verdict: str = "OK"
    filament_detected: bool = True
    heater_duty: float = 0.0
    tmc_sg_result: int = 0
    ai_class: str = "normal"
    current_layer: int = 0
    z_height: float = 0.0


class ServiceStatus(BaseModel):
    name: str
    active: bool = False
    enabled: bool = False
    memory_mb: float = 0.0


class SystemInfo(BaseModel):
    cpu_percent: float = 0.0
    ram_used_mb: int = 0
    ram_total_mb: int = 0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    uptime_seconds: int = 0


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "3.0.0"
    moonraker_connected: bool = False
    klipper_state: str = "unknown"

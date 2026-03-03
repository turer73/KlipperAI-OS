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


# --- Level 1: AI Resource Manager ---


class ResourceMetrics(BaseModel):
    cpu_percent: float = 0.0
    cpu_per_core: list[float] = []
    memory_percent: float = 0.0
    memory_available_mb: int = 0
    cpu_temperature: float = 0.0
    disk_io_percent: float = 0.0
    load_avg_1m: float = 0.0


class ResourcePolicyModel(BaseModel):
    memory_warning_pct: float = 80.0
    memory_critical_pct: float = 90.0
    cpu_temp_warning: float = 75.0
    cpu_temp_critical: float = 82.0


class ResourceStatus(BaseModel):
    metrics: Optional[ResourceMetrics] = None
    governor: str = "unknown"
    policy: Optional[ResourcePolicyModel] = None
    recent_actions: list[dict] = []


# --- Level 2: Adaptive Print ---


class LayerScore(BaseModel):
    layer: int = 0
    flow_consistency: float = 1.0
    thermal_stability: float = 1.0
    visual_score: float = 1.0
    composite_score: float = 1.0


class AdaptivePrintStatus(BaseModel):
    enabled: bool = False
    current_speed_factor: float = 1.0
    current_flow_factor: float = 1.0
    current_temp_offset: float = 0.0
    layers_scored: int = 0
    last_score: Optional[LayerScore] = None
    adjustments_made: int = 0


# --- Level 3: Predictive Maintenance ---


class MaintenanceAlertModel(BaseModel):
    component: str
    severity: str = "info"
    message: str = ""
    probability: float = 0.0
    recommended_action: str = ""


class MaintenanceStatus(BaseModel):
    alerts: list[MaintenanceAlertModel] = []
    print_hours: float = 0.0
    trackers: dict = {}


# --- Level 4: Autonomous Recovery ---


class RecoveryAttemptModel(BaseModel):
    failure_type: str
    auto_recoverable: bool = False
    success: bool = False
    timestamp: float = 0.0
    steps_executed: int = 0


class RecoveryStatus(BaseModel):
    enabled: bool = False
    total_attempts: int = 0
    successful_recoveries: int = 0
    failed_recoveries: int = 0
    last_attempt: Optional[RecoveryAttemptModel] = None

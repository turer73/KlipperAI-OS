"""
KlipperOS-AI — Bambu Lab Printer API Router
=============================================
Bambu Lab yazıcı yönetimi ve AI izleme REST endpoint'leri.

Endpoint'ler:
    GET    /api/v1/bambu/printers                    — Yazıcı listesi
    POST   /api/v1/bambu/printers                    — Yazıcı ekle
    DELETE /api/v1/bambu/printers/{id}               — Yazıcı sil
    GET    /api/v1/bambu/printers/{id}/status         — Durum
    GET    /api/v1/bambu/printers/{id}/camera/snapshot — Kamera frame
    GET    /api/v1/bambu/printers/{id}/detection       — AI tespit sonucu
    GET    /api/v1/bambu/status                        — Tüm yazıcılar özet
"""

from __future__ import annotations

import threading
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/bambu", tags=["bambu"])

# Global monitor reference — lazy init
_monitor = None
_config_mod = None
_init_lock = threading.Lock()


def _ensure_ai_monitor_path():
    """ai-monitor dizinini sys.path'e ekle (tire yüzünden normal import çalışmaz)."""
    import sys
    from pathlib import Path

    base = Path(__file__).resolve().parents[3]
    ai_dir = base / "ai-monitor"
    if str(ai_dir) not in sys.path:
        sys.path.insert(0, str(ai_dir))
    return ai_dir


def _import_config():
    """Sadece BambuConfig import et — hafif, AI bağımlılığı yok."""
    _ensure_ai_monitor_path()
    from bambu_config import BambuConfig, BambuPrinterConfig
    return BambuConfig, BambuPrinterConfig


def _import_monitor():
    """MultiPrinterMonitor import et — ağır (AI + kamera bağımlılıkları).

    multi_printer_monitor.py dual-import pattern kullanıyor:
      try: from bambu_client import X   (standalone)
      except: from .bambu_client import X  (relative / package)
    sys.path'e ai-monitor ekliyse standalone import çalışmalı, ama
    bazı alt modüller (spaghetti_detect, frame_capture) ağır dep'ler
    gerektirebilir. Bu yüzden monitor import'u opsiyonel tutuyoruz.
    """
    _ensure_ai_monitor_path()
    from multi_printer_monitor import MultiPrinterMonitor
    return MultiPrinterMonitor


def _get_config():
    """BambuConfig lazy import ve yükleme."""
    global _config_mod
    with _init_lock:
        if _config_mod is None:
            BambuConfig, _ = _import_config()
            _config_mod = BambuConfig
    return _config_mod.load()


def _get_monitor():
    """MultiPrinterMonitor lazy singleton — henüz çalışmıyorsa None."""
    global _monitor
    return _monitor


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class BambuPrinterConfigModel(BaseModel):
    id: str = ""
    name: str = Field(..., min_length=1, max_length=64)
    hostname: str = Field(..., min_length=7)  # en az "1.2.3.4"
    access_code: str = Field(..., min_length=8, max_length=8)
    serial: str = Field(..., min_length=5)
    enabled: bool = True
    check_interval: int = Field(default=10, ge=5, le=120)


class BambuPrinterStatusModel(BaseModel):
    id: str
    name: str
    printer_type: str = "bambu"
    is_printing: bool = False
    state: str = "idle"
    progress_percent: float = 0.0
    nozzle_temp: float = 0.0
    nozzle_target: float = 0.0
    bed_temp: float = 0.0
    bed_target: float = 0.0
    current_layer: int = 0
    total_layers: int = 0
    filename: str = ""
    remaining_minutes: int = 0
    mqtt_connected: bool = False
    camera_connected: bool = False


class DetectionResultModel(BaseModel):
    printer_id: str = ""
    printer_type: str = ""
    detection_class: str = "unknown"
    confidence: float = 0.0
    action: str = "none"
    scores: dict = {}
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/printers")
async def list_printers() -> list[dict]:
    """Tüm yapılandırılmış Bambu yazıcıları listele."""
    config = _get_config()
    return [
        {
            "id": pc.id,
            "name": pc.name,
            "hostname": pc.hostname,
            "serial": pc.serial,
            "enabled": pc.enabled,
            "check_interval": pc.check_interval,
        }
        for pc in config.printers
    ]


@router.post("/printers")
async def add_printer(data: BambuPrinterConfigModel) -> dict:
    """Yeni Bambu yazıcı ekle."""
    _, BambuPrinterConfig = _import_config()

    config = _get_config()
    pc = BambuPrinterConfig(
        id=data.id or "",
        name=data.name,
        hostname=data.hostname,
        access_code=data.access_code,
        serial=data.serial,
        enabled=data.enabled,
        check_interval=data.check_interval,
    )
    config.add_printer(pc)
    if not config.save():
        raise HTTPException(500, "Config kaydedilemedi")

    return {"status": "ok", "printer_id": pc.id, "message": f"Yazıcı eklendi: {pc.name}"}


@router.delete("/printers/{printer_id}")
async def remove_printer(printer_id: str) -> dict:
    """Bambu yazıcı sil."""
    config = _get_config()
    if not config.remove_printer(printer_id):
        raise HTTPException(404, f"Yazıcı bulunamadı: {printer_id}")
    if not config.save():
        raise HTTPException(500, "Config kaydedilemedi")

    # Çalışan monitörden de kaldır
    monitor = _get_monitor()
    if monitor:
        monitor.remove_printer(printer_id)

    return {"status": "ok", "message": f"Yazıcı silindi: {printer_id}"}


@router.get("/printers/{printer_id}/status")
async def get_printer_status(printer_id: str) -> BambuPrinterStatusModel:
    """Bambu yazıcı durumunu getir."""
    # 1. In-process monitor (varsa)
    monitor = _get_monitor()
    if monitor is not None:
        stats = monitor.get_printer_stats(printer_id)
        if stats is not None:
            mqtt = stats.get("mqtt_status", {})
            return BambuPrinterStatusModel(
                id=printer_id,
                name=stats.get("printer_name", ""),
                printer_type=stats.get("printer_type", "bambu"),
                is_printing=stats.get("is_printing", False),
                state=mqtt.get("state", "idle"),
                progress_percent=mqtt.get("progress_percent", 0.0),
                nozzle_temp=mqtt.get("nozzle_temp", 0.0),
                nozzle_target=mqtt.get("nozzle_target", 0.0),
                bed_temp=mqtt.get("bed_temp", 0.0),
                bed_target=mqtt.get("bed_target", 0.0),
                current_layer=mqtt.get("current_layer", 0),
                total_layers=mqtt.get("total_layers", 0),
                filename=mqtt.get("filename", ""),
                remaining_minutes=mqtt.get("remaining_minutes", 0),
                mqtt_connected=stats.get("mqtt_connected", False),
                camera_connected=stats.get("capture_stats", {}).get("frame_count", 0) > 0,
            )

    # 2. Status file fallback (ayrı process'teki monitor)
    stats = _read_printer_from_status(printer_id)
    if stats is not None:
        mqtt = stats.get("mqtt_status", {})
        return BambuPrinterStatusModel(
            id=printer_id,
            name=stats.get("printer_name", ""),
            printer_type=stats.get("printer_type", "bambu"),
            is_printing=stats.get("is_printing", False),
            state=mqtt.get("state", "idle"),
            progress_percent=mqtt.get("progress_percent", 0.0),
            nozzle_temp=mqtt.get("nozzle_temp", 0.0),
            nozzle_target=mqtt.get("nozzle_target", 0.0),
            bed_temp=mqtt.get("bed_temp", 0.0),
            bed_target=mqtt.get("bed_target", 0.0),
            current_layer=mqtt.get("current_layer", 0),
            total_layers=mqtt.get("total_layers", 0),
            filename=mqtt.get("filename", ""),
            remaining_minutes=mqtt.get("remaining_minutes", 0),
            mqtt_connected=stats.get("mqtt_connected", False),
            camera_connected=stats.get("capture_stats", {}).get("frame_count", 0) > 0,
        )

    raise HTTPException(404, f"Yazıcı bulunamadı: {printer_id}")


@router.get("/printers/{printer_id}/camera/snapshot")
async def get_camera_snapshot(printer_id: str):
    """Son kamera frame'ini JPEG olarak döndür."""
    import os

    # 1. In-process monitor (varsa)
    monitor = _get_monitor()
    if monitor is not None:
        jpeg_data = monitor.get_printer_snapshot(printer_id)
        if jpeg_data:
            return Response(content=jpeg_data, media_type="image/jpeg")

    # 2. Dosyadan oku (ayrı process'teki monitor kaydetmiş olabilir)
    snap_path = os.path.join(_SNAPSHOT_DIR, f"{printer_id}.jpg")
    try:
        with open(snap_path, "rb") as f:
            data = f.read()
        if data:
            return Response(content=data, media_type="image/jpeg")
    except FileNotFoundError:
        pass

    raise HTTPException(503, "Kamera frame'i mevcut değil")


@router.get("/printers/{printer_id}/detection")
async def get_detection_result(printer_id: str) -> DetectionResultModel:
    """Son AI tespit sonucunu getir."""
    # 1. In-process monitor (varsa)
    monitor = _get_monitor()
    if monitor is not None:
        result = monitor.get_printer_detection(printer_id)
        if result:
            return DetectionResultModel(
                printer_id=result.get("printer_id", printer_id),
                printer_type=result.get("printer_type", "bambu"),
                detection_class=result.get("class", "unknown"),
                confidence=result.get("confidence", 0.0),
                action=result.get("action", "none"),
                scores=result.get("scores", {}),
                timestamp=result.get("timestamp", 0.0),
            )

    # 2. Status file fallback
    stats = _read_printer_from_status(printer_id)
    if stats is not None:
        det = stats.get("last_detection")
        if det:
            return DetectionResultModel(
                printer_id=det.get("printer_id", printer_id),
                printer_type=det.get("printer_type", "bambu"),
                detection_class=det.get("class", "unknown"),
                confidence=det.get("confidence", 0.0),
                action=det.get("action", "none"),
                scores=det.get("scores", {}),
                timestamp=det.get("timestamp", 0.0),
            )

    # 3. Yazıcı mevcut ama henüz detection yok
    if stats is not None:
        raise HTTPException(404, f"Tespit sonucu yok: {printer_id}")

    raise HTTPException(404, f"Yazıcı bulunamadı: {printer_id}")


_STATUS_FILE = "/var/lib/klipperos-ai/bambu-monitor-status.json"
_SNAPSHOT_DIR = "/var/lib/klipperos-ai/snapshots"


def _read_monitor_status() -> Optional[dict]:
    """Monitor'un yazdığı durum dosyasını oku — 30sn'den eskiyse stale say."""
    import json, time
    try:
        with open(_STATUS_FILE, "r") as f:
            data = json.load(f)
        # 30 saniyeden eski mi?
        if time.time() - data.get("timestamp", 0) > 30:
            return None  # stale
        return data
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def _read_printer_from_status(printer_id: str) -> Optional[dict]:
    """Status file'dan tek yazıcının verisini oku."""
    data = _read_monitor_status()
    if data is None:
        return None
    return data.get("printers", {}).get(printer_id)


@router.get("/status")
async def get_all_status() -> dict:
    """Tüm Bambu yazıcıların özet durumu."""
    # 1. Önce monitor status dosyasını oku (ayrı process iletişimi)
    live = _read_monitor_status()
    if live is not None:
        return {
            "monitor_running": True,
            "printers": live.get("printers", {}),
            "active_count": live.get("active_count", 0),
            "printer_ids": live.get("printer_ids", []),
        }

    # 2. In-process monitor (varsa)
    monitor = _get_monitor()
    if monitor is not None:
        return {
            "monitor_running": True,
            "printers": monitor.get_all_stats(),
            "active_count": len(monitor.get_printer_ids()),
        }

    # 3. Hiçbiri yoksa config'den statik bilgi
    config = _get_config()
    return {
        "monitor_running": False,
        "printers": [
            {"id": pc.id, "name": pc.name, "enabled": pc.enabled}
            for pc in config.printers
        ],
    }

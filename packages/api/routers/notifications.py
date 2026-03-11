"""
KlipperOS-AI — Notifications API Router
========================================
Bildirim yapilandirma + test endpoint'leri.

Endpoint'ler:
    GET  /api/v1/notifications/config   — Bildirim ayarlarini getir
    PUT  /api/v1/notifications/config   — Bildirim ayarlarini kaydet
    POST /api/v1/notifications/test     — Test bildirimi gonder
    GET  /api/v1/notifications/history  — Son bildirimler
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

# Lazy import — ai-monitor path sorunu
_manager = None
_init_lock = threading.Lock()
CONFIG_PATH = "/var/lib/klipperos-ai/notifications.json"


def _ensure_path():
    """ai-monitor'u sys.path'e ekle."""
    base = Path(__file__).resolve().parents[3]
    ai_dir = base / "ai-monitor"
    if str(ai_dir) not in sys.path:
        sys.path.insert(0, str(ai_dir))


def _get_manager():
    """Lazy singleton notification manager."""
    global _manager
    with _init_lock:
        if _manager is None:
            _ensure_path()
            from notification_manager import NotificationManager
            _manager = NotificationManager(config_path=CONFIG_PATH)
            _manager.load_config()
    return _manager


# -- Models --

class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    min_severity: str = "warning"


class DiscordConfig(BaseModel):
    enabled: bool = False
    webhook_url: str = ""
    min_severity: str = "info"


class NotificationConfig(BaseModel):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    cooldown_seconds: int = 60


class TestRequest(BaseModel):
    title: str = "KlipperOS-AI Test"
    message: str = "Bildirim sistemi calisiyor!"
    severity: str = "info"
    channel: Optional[str] = None  # None = tum kanallar


# -- Endpoints --

@router.get("/config")
async def get_notification_config():
    """Bildirim yapilandirmasini getir."""
    config_path = Path(CONFIG_PATH)
    if not config_path.exists():
        return NotificationConfig().model_dump()

    import json
    try:
        data = json.loads(config_path.read_text())
        # Hassas bilgileri maskele
        if "telegram" in data and data["telegram"].get("bot_token"):
            token = data["telegram"]["bot_token"]
            data["telegram"]["bot_token"] = token[:8] + "..." if len(token) > 8 else "***"
        if "discord" in data and data["discord"].get("webhook_url"):
            url = data["discord"]["webhook_url"]
            data["discord"]["webhook_url"] = url[:40] + "..." if len(url) > 40 else "***"
        return data
    except (json.JSONDecodeError, OSError):
        return NotificationConfig().model_dump()


@router.put("/config")
async def update_notification_config(config: NotificationConfig):
    """Bildirim yapilandirmasini kaydet ve provider'lari yeniden yukle."""
    mgr = _get_manager()

    config_dict = config.model_dump()
    if not mgr.save_config(config_dict):
        raise HTTPException(500, "Ayar dosyasi kaydedilemedi")

    # Provider'lari sifirla ve yeniden yukle
    global _manager
    with _init_lock:
        _ensure_path()
        from notification_manager import NotificationManager
        _manager = NotificationManager(config_path=CONFIG_PATH)
        _manager.load_config()

    return {
        "message": "Bildirim ayarlari kaydedildi",
        "providers": _manager.provider_names,
    }


@router.post("/test")
async def send_test_notification(req: TestRequest):
    """Test bildirimi gonder."""
    mgr = _get_manager()

    if not mgr.provider_names:
        raise HTTPException(
            400, "Aktif bildirim kanali yok. Once /config ile yapilandirin."
        )

    _ensure_path()
    from notification_manager import Notification, Severity

    severity_map = {
        "info": Severity.INFO,
        "notice": Severity.NOTICE,
        "warning": Severity.WARNING,
        "critical": Severity.CRITICAL,
    }
    sev = severity_map.get(req.severity.lower(), Severity.INFO)

    n = Notification(
        title=req.title,
        message=req.message,
        severity=sev,
        category="test",
    )

    results = mgr.notify(n)
    return {
        "sent": results,
        "message": "Test bildirimi gonderildi"
        if any(results.values())
        else "Gonderim basarisiz",
    }


@router.get("/history")
async def get_notification_history():
    """Son bildirimleri getir."""
    mgr = _get_manager()
    return {"history": mgr.history}

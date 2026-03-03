"""FastAPI dependency injection."""
from __future__ import annotations
from .moonraker_client import MoonrakerClient
from .config import settings

_moonraker_client: MoonrakerClient | None = None

def get_moonraker_client() -> MoonrakerClient:
    global _moonraker_client
    if _moonraker_client is None:
        _moonraker_client = MoonrakerClient(settings.moonraker_url)
    return _moonraker_client

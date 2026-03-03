"""API yapilandirma ayarlari."""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, field
import os

@dataclass
class Settings:
    """API backend ayarlari — env vars ile override edilebilir."""
    moonraker_url: str = field(
        default_factory=lambda: os.getenv("KOS_MOONRAKER_URL", "http://127.0.0.1:7125")
    )
    db_path: str = field(
        default_factory=lambda: os.getenv(
            "KOS_DB_PATH", str(Path("/var/lib/klipperos-ai/kos.db"))
        )
    )
    jwt_secret: str = field(
        default_factory=lambda: os.getenv("KOS_JWT_SECRET", "")
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 saat
    cache_ttl_fast: float = 2.0     # sicaklik cache (saniye)
    cache_ttl_slow: float = 30.0    # servis/ollama cache
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    host: str = "0.0.0.0"
    port: int = 8470

settings = Settings()

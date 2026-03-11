"""API yapilandirma ayarlari."""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, field
import os
import secrets

def _default_jwt_secret() -> str:
    """JWT secret: env'den al, yoksa dosyadan oku/olustur."""
    env = os.getenv("KOS_JWT_SECRET", "")
    if env:
        return env
    secret_file = Path("/var/lib/klipperos-ai/.jwt-secret")
    try:
        if secret_file.exists():
            return secret_file.read_text().strip()
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_hex(32)
        secret_file.write_text(secret)
        secret_file.chmod(0o600)
        return secret
    except OSError:
        # Fallback: dosya yazma basarisiz (dev ortami vb.)
        return secrets.token_hex(32)

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
    jwt_secret: str = field(default_factory=_default_jwt_secret)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 saat
    cache_ttl_fast: float = 2.0     # sicaklik cache (saniye)
    cache_ttl_slow: float = 30.0    # servis/ollama cache
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    host: str = "0.0.0.0"
    port: int = 8470

settings = Settings()

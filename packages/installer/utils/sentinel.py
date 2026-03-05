"""Idempotent kurulum kontrol dosyalari."""
from __future__ import annotations

from pathlib import Path

from .target import target_path


class Sentinel:
    """Bilesen kurulum durumunu dosya ile izler."""

    def __init__(self, base_dir: str = "/opt/klipperos-ai"):
        self.base_dir = Path(base_dir)

    def _path(self, component: str) -> Path:
        # Lazy resolution: target_path her cagride degerlendirilir,
        # boylece set_target() sonrasi dogru yolu dondurur.
        raw = str(self.base_dir / f".installed-{component}")
        return Path(target_path(raw))

    def is_done(self, component: str) -> bool:
        """Bilesen zaten kuruldu mu?"""
        return self._path(component).exists()

    def mark_done(self, component: str) -> None:
        """Bileseni kuruldu olarak isaretle."""
        self._path(component).parent.mkdir(parents=True, exist_ok=True)
        self._path(component).touch()

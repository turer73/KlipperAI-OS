"""Hedef kok dizin yonetimi — live vs disk kurulum.

Live CD modunda target=None → dosyalar dogrudan yazilir.
Disk kurulumda target="/mnt/target" → dosyalar hedef diske yonlendirilir.
"""
from __future__ import annotations

from pathlib import Path

_target_root: str | None = None


def set_target(root: str | None) -> None:
    """Hedef kok dizini ayarla (None=live CD, "/mnt/target"=disk)."""
    global _target_root
    _target_root = root


def get_target() -> str | None:
    """Mevcut hedef kok dizini dondur."""
    return _target_root


def target_path(absolute_path: str) -> str:
    """Mutlak yolu hedef koke gore donustur.

    >>> set_target(None)
    >>> target_path("/etc/hostname")
    '/etc/hostname'

    >>> set_target("/mnt/target")
    >>> target_path("/etc/hostname")
    '/mnt/target/etc/hostname'
    """
    if _target_root is None:
        return absolute_path
    stripped = absolute_path.lstrip("/")
    return str(Path(_target_root) / stripped)

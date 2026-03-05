"""Base installer sinifi."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..utils.logger import get_logger
from ..utils.sentinel import Sentinel
from ..utils.target import target_path

logger = get_logger()


class BaseInstaller(ABC):
    """Tum bilesen kurucularinin base sinifi."""

    name: str = ""

    def __init__(self, sentinel: Sentinel | None = None):
        self.sentinel = sentinel or Sentinel()

    def _open_target(self, path: str, mode: str = "w"):
        """Hedef diske yonlendirilmis dosya ac.

        Live CD'de dogrudan path'e yazar.
        Disk kurulumda target_path() ile /mnt/target altina yonlendirir.
        """
        real = target_path(path)
        Path(real).parent.mkdir(parents=True, exist_ok=True)
        return open(real, mode)

    def install(self) -> bool:
        """Bileseni kur. Zaten kuruluysa atla."""
        if self.sentinel.is_done(self.name):
            logger.info("[%s] Zaten kurulu — atlaniyor.", self.name)
            return True

        logger.info("[%s] Kurulum basliyor...", self.name)
        try:
            success = self._install()
        except Exception as e:
            logger.error("[%s] Kurulum hatasi: %s", self.name, e)
            return False

        if success:
            self.sentinel.mark_done(self.name)
            logger.info("[%s] Kurulum tamamlandi.", self.name)
        else:
            logger.error("[%s] Kurulum basarisiz.", self.name)
        return success

    @abstractmethod
    def _install(self) -> bool:
        """Alt sinif tarafindan implement edilir."""
        ...

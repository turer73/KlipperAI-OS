"""
KlipperOS-AI — Bambu Lab Printer Configuration
================================================
Bambu yazıcı bağlantı bilgilerini JSON dosyasında yönetir.
Atomik yazma ile veri kaybını önler.

Dosya: /etc/klipperos-ai/bambu-printers.json
"""

import json
import logging
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("klipperos-ai.bambu.config")

DEFAULT_CONFIG_PATH = "/etc/klipperos-ai/bambu-printers.json"


@dataclass
class BambuPrinterConfig:
    """Tek bir Bambu Lab yazıcının bağlantı yapılandırması."""

    id: str = ""  # benzersiz ID (auto-generated UUID)
    name: str = ""  # görüntü adı ("Workshop X1C")
    hostname: str = ""  # IP veya hostname ("192.168.1.50")
    access_code: str = ""  # 8 karakter erişim kodu (LCD'den)
    serial: str = ""  # seri numarası (MQTT topic için)
    enabled: bool = True
    check_interval: int = 10  # AI kontrol aralığı (saniye)

    def __post_init__(self):
        if not self.id:
            self.id = f"bambu-{uuid.uuid4().hex[:8]}"


@dataclass
class BambuConfig:
    """Tüm Bambu yazıcı yapılandırması."""

    printers: list[BambuPrinterConfig] = field(default_factory=list)

    @staticmethod
    def load(path: str | Path = DEFAULT_CONFIG_PATH) -> "BambuConfig":
        """Config dosyasından yükle. Dosya yoksa boş config döndür."""
        p = Path(path)
        if not p.exists():
            logger.info("Bambu config dosyası bulunamadı: %s (boş başlatılıyor)", p)
            return BambuConfig()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            printers = [
                BambuPrinterConfig(**pc) for pc in data.get("printers", [])
            ]
            logger.info("%d Bambu yazıcı config yüklendi: %s", len(printers), p)
            return BambuConfig(printers=printers)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.error("Bambu config parse hatası: %s", exc)
            return BambuConfig()

    def save(self, path: str | Path = DEFAULT_CONFIG_PATH) -> bool:
        """Config dosyasına atomik olarak kaydet."""
        p = Path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {"printers": [asdict(pc) for pc in self.printers]}
            content = json.dumps(data, indent=2, ensure_ascii=False)

            # Atomik yazma: tempfile → rename
            fd, tmp_path = tempfile.mkstemp(
                dir=str(p.parent), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                os.replace(tmp_path, str(p))
            except Exception:
                os.unlink(tmp_path)
                raise

            logger.info("Bambu config kaydedildi: %s (%d yazıcı)", p, len(self.printers))
            return True
        except OSError as exc:
            logger.error("Bambu config kayıt hatası: %s", exc)
            return False

    def add_printer(self, config: BambuPrinterConfig) -> None:
        """Yeni yazıcı ekle."""
        # Aynı hostname+serial varsa güncelle
        for i, existing in enumerate(self.printers):
            if existing.hostname == config.hostname and existing.serial == config.serial:
                self.printers[i] = config
                logger.info("Bambu yazıcı güncellendi: %s (%s)", config.name, config.id)
                return
        self.printers.append(config)
        logger.info("Bambu yazıcı eklendi: %s (%s)", config.name, config.id)

    def remove_printer(self, printer_id: str) -> bool:
        """ID ile yazıcı sil."""
        for i, pc in enumerate(self.printers):
            if pc.id == printer_id:
                removed = self.printers.pop(i)
                logger.info("Bambu yazıcı silindi: %s (%s)", removed.name, removed.id)
                return True
        return False

    def get_printer(self, printer_id: str) -> Optional[BambuPrinterConfig]:
        """ID ile yazıcı bul."""
        for pc in self.printers:
            if pc.id == printer_id:
                return pc
        return None

    def get_enabled_printers(self) -> list[BambuPrinterConfig]:
        """Aktif yazıcıları listele."""
        return [pc for pc in self.printers if pc.enabled]

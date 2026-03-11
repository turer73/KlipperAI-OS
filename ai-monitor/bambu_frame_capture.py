"""
KlipperOS-AI — Bambu Lab Camera Frame Capture
===============================================
Bambu Lab kamerasından frame yakalama — FrameCapture ile aynı interface.
SpaghettiDetector modeline doğrudan beslenebilir çıktı üretir.

Mevcut FrameCapture (Crowsnest/MJPEG) ile birebir uyumlu API:
    capture(target_size) -> Optional[np.ndarray]   (float32, [0,1], H×W×3)
    capture_raw()        -> Optional[Image.Image]
    stats                -> dict
    is_camera_available() -> bool
"""

import io
import logging
import time
from typing import Optional

import numpy as np
from PIL import Image

try:
    from bambu_client import BambuCameraStream
except ImportError:
    from .bambu_client import BambuCameraStream

logger = logging.getLogger("klipperos-ai.bambu.capture")


class BambuFrameCapture:
    """Bambu Lab kamerasından frame yakalama — FrameCapture uyumlu adapter.

    FrameCapture ile aynı çıktı formatı:
        - capture(): float32 numpy array (H, W, 3), [0, 1] normalize
        - capture_raw(): PIL.Image.Image (RGB)
    """

    def __init__(
        self,
        hostname: str,
        access_code: str,
        port: int = 6000,
        read_timeout: float = 10.0,
    ):
        self._stream = BambuCameraStream(
            hostname=hostname,
            access_code=access_code,
            port=port,
            read_timeout=read_timeout,
        )
        self._last_frame_time: float = 0
        self._frame_count: int = 0
        self._error_count: int = 0
        self._last_jpeg: Optional[bytes] = None  # Snapshot endpoint için önbellek

    def capture(
        self, target_size: tuple[int, int] = (224, 224)
    ) -> Optional[np.ndarray]:
        """Bambu kameradan frame yakala ve numpy array olarak döndür.

        Args:
            target_size: Model girişi için hedef boyut (genişlik, yükseklik)

        Returns:
            numpy array (H, W, 3) RGB, float32, [0, 1] veya None
        """
        # read_latest_frame: buffer'ı drain edip en güncel frame'i al
        # Eski read_frame() en eski frame'i döndürüp gecikmeye neden oluyordu
        jpeg_bytes = self._stream.read_latest_frame()
        if jpeg_bytes is None:
            self._error_count += 1
            return None

        try:
            self._last_jpeg = jpeg_bytes

            image = Image.open(io.BytesIO(jpeg_bytes))
            image = image.convert("RGB")
            image = image.resize(target_size, Image.BILINEAR)

            # Normalizasyon: [0, 255] -> [0, 1]
            # frame_capture.py:50 ile birebir aynı
            frame = np.array(image, dtype=np.float32)
            frame = frame / 255.0

            self._last_frame_time = time.time()
            self._frame_count += 1
            self._error_count = 0

            return frame

        except Exception as e:
            logger.error("Bambu frame işleme hatası: %s", e)
            self._error_count += 1
            return None

    def capture_raw(self) -> Optional[Image.Image]:
        """Ham PIL Image olarak frame yakala (görselleştirme için)."""
        jpeg_bytes = self._stream.read_latest_frame()
        if jpeg_bytes is None:
            self._error_count += 1
            return None
        try:
            self._last_jpeg = jpeg_bytes
            return Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        except Exception as e:
            logger.error("Bambu raw frame hatası: %s", e)
            self._error_count += 1
            return None

    @property
    def last_jpeg(self) -> Optional[bytes]:
        """Son yakalanan JPEG bytes — snapshot endpoint için."""
        return self._last_jpeg

    @property
    def stats(self) -> dict:
        """Frame yakalama istatistikleri (FrameCapture.stats ile aynı key'ler)."""
        return {
            "frame_count": self._frame_count,
            "error_count": self._error_count,
            "last_frame_time": self._last_frame_time,
        }

    def is_camera_available(self) -> bool:
        """Bambu kamera stream'inin bağlı olup olmadığını kontrol et."""
        return self._stream.is_connected

    def disconnect(self) -> None:
        """Kamera stream bağlantısını kapat."""
        self._stream.disconnect()

"""
KlipperOS-AI — Camera Frame Capture Module
===========================================
Crowsnest/MJPEG kameradan frame yakalar.
Snapshot URL uzerinden goruntuyu indirir ve numpy array olarak dondurur.
"""

import io
import logging
import time
from typing import Optional

import numpy as np
import requests
from PIL import Image

logger = logging.getLogger("klipperos-ai.capture")

DEFAULT_CAMERA_URL = "http://127.0.0.1:8080/?action=snapshot"
DEFAULT_TIMEOUT = 5


class FrameCapture:
    """Kameradan frame yakalama sinifi."""

    def __init__(self, camera_url: str = DEFAULT_CAMERA_URL, timeout: int = DEFAULT_TIMEOUT):
        self.camera_url = camera_url
        self.timeout = timeout
        self._last_frame_time: float = 0
        self._frame_count: int = 0
        self._error_count: int = 0

    def capture(self, target_size: tuple[int, int] = (224, 224)) -> Optional[np.ndarray]:
        """Kameradan bir frame yakala ve numpy array olarak dondur.

        Args:
            target_size: Model girisi icin hedef boyut (genislik, yukseklik)

        Returns:
            numpy array (H, W, 3) RGB formatinda veya None (hata durumunda)
        """
        try:
            response = requests.get(self.camera_url, timeout=self.timeout)
            response.raise_for_status()

            image = Image.open(io.BytesIO(response.content))
            image = image.convert("RGB")
            image = image.resize(target_size, Image.BILINEAR)

            frame = np.array(image, dtype=np.float32)
            # Normalizasyon: [0, 255] -> [0, 1]
            frame = frame / 255.0

            self._last_frame_time = time.time()
            self._frame_count += 1
            self._error_count = 0

            return frame

        except requests.exceptions.ConnectionError:
            if self._error_count == 0:
                logger.warning("Kamera baglantisi kurulamadi: %s", self.camera_url)
            self._error_count += 1
            return None

        except requests.exceptions.Timeout:
            logger.warning("Kamera zaman asimi: %s", self.camera_url)
            self._error_count += 1
            return None

        except Exception as e:
            logger.error("Frame yakalama hatasi: %s", e)
            self._error_count += 1
            return None

    def capture_raw(self) -> Optional[Image.Image]:
        """Ham PIL Image olarak frame yakala (gorsellestirme icin)."""
        try:
            response = requests.get(self.camera_url, timeout=self.timeout)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content)).convert("RGB")
        except Exception as e:
            logger.error("Ham frame yakalama hatasi: %s", e)
            return None

    @property
    def stats(self) -> dict:
        """Frame yakalama istatistikleri."""
        return {
            "frame_count": self._frame_count,
            "error_count": self._error_count,
            "last_frame_time": self._last_frame_time,
        }

    def is_camera_available(self) -> bool:
        """Kameranin erisilebilir olup olmadigini kontrol et."""
        try:
            response = requests.head(self.camera_url, timeout=2)
            return response.status_code == 200
        except Exception:
            return False

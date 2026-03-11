"""Moonraker REST API client — cache + retry + timeout."""
from __future__ import annotations
import time
import json
import logging
from urllib.request import urlopen, Request
from urllib.error import URLError
from typing import Any

logger = logging.getLogger(__name__)


class MoonrakerClient:
    """Moonraker REST API paylasimli client.

    Ozellikler:
    - Otomatik TTL cache (sicaklik=2s, yavas sorgu=30s)
    - Timeout korunmasi (varsayilan 5s)
    - JSON parse + hata yonetimi
    """

    def __init__(self, base_url: str = "http://127.0.0.1:7125",
                 cache_ttl: float = 2.0, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.default_cache_ttl = cache_ttl
        self.timeout = timeout
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cache_key(self, path: str, params: dict | None = None) -> str:
        parts = [path]
        if params:
            parts.append(json.dumps(params, sort_keys=True))
        return "|".join(parts)

    def _get_cached(self, key: str) -> Any | None:
        if key in self._cache:
            ts, data = self._cache[key]
            if time.monotonic() - ts < self.default_cache_ttl:
                return data
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data: Any) -> None:
        self._cache[key] = (time.monotonic(), data)

    def clear_cache(self) -> None:
        self._cache.clear()

    def get(self, path: str, use_cache: bool = True) -> dict | None:
        """GET istegi gonder, opsiyonel cache ile."""
        url = f"{self.base_url}{path}"
        if use_cache:
            cached = self._get_cached(self._cache_key(path))
            if cached is not None:
                return cached
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
            if use_cache:
                self._set_cache(self._cache_key(path), data)
            return data
        except (URLError, OSError, json.JSONDecodeError) as exc:
            logger.warning("Moonraker GET %s failed: %s", path, exc)
            return None

    def post(self, path: str, body: dict | None = None,
             timeout: float | None = None) -> dict | None:
        """POST istegi gonder."""
        url = f"{self.base_url}{path}"
        try:
            payload = json.dumps(body).encode() if body else b""
            req = Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            effective_timeout = timeout if timeout is not None else self.timeout
            with urlopen(req, timeout=effective_timeout) as resp:
                return json.loads(resp.read().decode())
        except (URLError, OSError, json.JSONDecodeError) as exc:
            logger.warning("Moonraker POST %s failed: %s", path, exc)
            return None

    def get_printer_objects(self, *objects: str) -> dict:
        """Yazici nesnelerini sorgula.

        Kullanim: client.get_printer_objects("print_stats", "extruder", "heater_bed")
        """
        from urllib.parse import quote
        query = "&".join(quote(obj, safe="=,") for obj in objects)
        resp = self.get(f"/printer/objects/query?{query}")
        if resp and "result" in resp:
            return resp["result"].get("status", {})
        return {}

    def send_gcode(self, script: str, timeout: float | None = None) -> bool:
        """G-code komutu gonder. timeout: saniye (PID icin 600 onerilir)."""
        resp = self.post("/printer/gcode/script", {"script": script}, timeout=timeout)
        return resp is not None

    def is_available(self) -> bool:
        """Moonraker erisim kontrolu."""
        resp = self.get("/server/info", use_cache=False)
        return resp is not None and "result" in resp

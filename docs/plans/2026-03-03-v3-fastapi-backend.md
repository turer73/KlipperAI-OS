# v3.0 Track 2: FastAPI Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** KlipperOS-AI icin REST + WebSocket API backend'i olusturmak — mevcut Moonraker API'yi sarar, genisletir ve SQLite veri katmani ekler.

**Architecture:** FastAPI backend Moonraker'a proxy gorevi gorur. Pydantic sema dogrulamasi, JWT kimlik dogrulama, WebSocket gercek zamanli stream ve SQLite baski gecmisi barindiri. Mevcut `_moonraker_get()` deseni paylasimli `MoonrakerClient` sinifina tasir.

**Tech Stack:** FastAPI 0.110+, uvicorn, Pydantic v2, SQLAlchemy 2.0 (async), aiosqlite, python-jose (JWT), websockets

**Monorepo yolu:** `packages/api/` (mevcut `tools/` ve `ai-monitor/` yaninda)

---

## Dosya Yapisi (Olusturulacak)

```
packages/
  api/
    __init__.py
    main.py                  # FastAPI app factory + lifespan
    config.py                # Ayarlar (env vars, Moonraker URL, JWT secret)
    dependencies.py          # Dependency injection (MoonrakerClient, DB session)
    moonraker_client.py      # Paylasimli Moonraker REST client (cache + retry)
    models/
      __init__.py
      printer.py             # Pydantic schemas: PrintStatus, Temperature, vb.
      auth.py                # User, Token schemas
      history.py             # PrintHistory, FlowGuardEvent schemas
    routers/
      __init__.py
      printer.py             # GET /api/v1/printer/* endpoints
      control.py             # POST /api/v1/printer/control/* endpoints
      files.py               # GET/POST /api/v1/files/* endpoints
      flowguard.py           # GET /api/v1/flowguard/* endpoints
      system.py              # GET /api/v1/system/* endpoints
      auth.py                # POST /api/v1/auth/* endpoints
      ws.py                  # WebSocket /api/v1/ws/printer endpoint
    db/
      __init__.py
      engine.py              # SQLAlchemy async engine + session
      tables.py              # ORM models (print_history, flowguard_events, users)
      migrations.py          # Auto-create tables on startup
    middleware/
      __init__.py
      auth.py                # JWT verification middleware
tests/
  test_api/
    __init__.py
    conftest.py              # Fixtures: test client, mock Moonraker
    test_moonraker_client.py
    test_printer_router.py
    test_control_router.py
    test_files_router.py
    test_flowguard_router.py
    test_system_router.py
    test_auth_router.py
    test_ws.py
    test_db.py
```

---

## Task 1: Proje Iskelesi + Bagimliliklar

**Files:**
- Create: `packages/api/__init__.py`
- Create: `packages/api/config.py`
- Create: `packages/api/main.py`
- Modify: `pyproject.toml` — yeni optional dep grubu

**Step 1: pyproject.toml'a api dependency grubu ekle**

```toml
# [project.optional-dependencies] altina ekle:
api = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "python-jose[cryptography]>=3.3",
    "aiosqlite>=0.19",
    "sqlalchemy[asyncio]>=2.0",
    "websockets>=12.0",
    "httpx>=0.27",
]
```

`full` grubunu guncelle:
```toml
full = ["klipperos-ai[ai,dashboard,agent,api]"]
```

**Step 2: packages/api/__init__.py olustur**

```python
"""KlipperOS-AI — FastAPI Backend."""
```

**Step 3: packages/api/config.py olustur**

```python
"""API yapilandirma ayarlari."""
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
```

**Step 4: packages/api/main.py olustur**

```python
"""FastAPI application factory."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # TODO: DB init, MoonrakerClient init
    yield
    # TODO: cleanup

def create_app() -> FastAPI:
    app = FastAPI(
        title="KlipperOS-AI API",
        version="3.0.0",
        description="KlipperOS-AI REST + WebSocket API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app

app = create_app()

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}

def main():
    import uvicorn
    uvicorn.run(
        "packages.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )

if __name__ == "__main__":
    main()
```

**Step 5: setuptools packages.find guncelle**

`pyproject.toml` `[tool.setuptools.packages.find]` satirini guncelle:
```toml
include = ["tools*", "ai-monitor*", "ks-panels*", "packages*"]
```

Entry point ekle:
```toml
kos-api = "packages.api.main:main"
```

**Step 6: Test — import dogrulama**

Run: `python -c "from packages.api.main import app; print(type(app))"`
Expected: `<class 'fastapi.applications.FastAPI'>`

**Step 7: Commit**

```bash
git add packages/ pyproject.toml
git commit -m "feat(api): scaffold FastAPI backend with config and health endpoint"
```

---

## Task 2: MoonrakerClient — Paylasimli HTTP Client

**Files:**
- Create: `packages/api/moonraker_client.py`
- Create: `tests/test_api/__init__.py`
- Create: `tests/test_api/conftest.py`
- Create: `tests/test_api/test_moonraker_client.py`

**Step 1: Test dosyalarini olustur**

```python
# tests/test_api/conftest.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_moonraker_response():
    """Ornek Moonraker yaniti."""
    return {
        "result": {
            "status": {
                "print_stats": {"state": "printing", "filename": "test.gcode"},
                "extruder": {"temperature": 210.0, "target": 210.0, "power": 0.8},
                "heater_bed": {"temperature": 60.0, "target": 60.0, "power": 0.5},
                "display_status": {"progress": 0.45},
            }
        }
    }
```

```python
# tests/test_api/test_moonraker_client.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

def test_moonraker_client_import():
    from packages.api.moonraker_client import MoonrakerClient
    client = MoonrakerClient("http://127.0.0.1:7125")
    assert client.base_url == "http://127.0.0.1:7125"

def test_cache_key_generation():
    from packages.api.moonraker_client import MoonrakerClient
    client = MoonrakerClient("http://127.0.0.1:7125")
    key = client._cache_key("/printer/objects/query", {"print_stats": ""})
    assert isinstance(key, str)
    assert len(key) > 0

def test_cache_expiry():
    from packages.api.moonraker_client import MoonrakerClient
    client = MoonrakerClient("http://127.0.0.1:7125", cache_ttl=0.0)
    client._cache["test_key"] = (0, {"data": True})
    assert client._get_cached("test_key") is None  # expired
```

**Step 2: Testi calistir — basarisiz olmali**

Run: `pytest tests/test_api/test_moonraker_client.py -v`
Expected: FAIL — module not found

**Step 3: MoonrakerClient implementasyonu**

```python
# packages/api/moonraker_client.py
"""Moonraker REST API client — cache + retry + timeout."""
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

    def _set_cache(self, key: str, data: Any, ttl: float | None = None) -> None:
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

    def post(self, path: str, body: dict | None = None) -> dict | None:
        """POST istegi gonder."""
        url = f"{self.base_url}{path}"
        try:
            payload = json.dumps(body).encode() if body else b""
            req = Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except (URLError, OSError, json.JSONDecodeError) as exc:
            logger.warning("Moonraker POST %s failed: %s", path, exc)
            return None

    def get_printer_objects(self, *objects: str) -> dict:
        """Yazici nesnelerini sorgula.

        Kullanim: client.get_printer_objects("print_stats", "extruder", "heater_bed")
        """
        query = "&".join(objects)
        resp = self.get(f"/printer/objects/query?{query}")
        if resp and "result" in resp:
            return resp["result"].get("status", {})
        return {}

    def send_gcode(self, script: str) -> bool:
        """G-code komutu gonder."""
        resp = self.post("/printer/gcode/script", {"script": script})
        return resp is not None

    def is_available(self) -> bool:
        """Moonraker erisim kontrolu."""
        resp = self.get("/server/info", use_cache=False)
        return resp is not None and "result" in resp
```

**Step 4: Testleri calistir**

Run: `pytest tests/test_api/test_moonraker_client.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add packages/api/moonraker_client.py tests/test_api/
git commit -m "feat(api): add MoonrakerClient with caching and retry"
```

---

## Task 3: Pydantic Data Modelleri

**Files:**
- Create: `packages/api/models/__init__.py`
- Create: `packages/api/models/printer.py`
- Create: `tests/test_api/test_models.py`

**Step 1: Test yaz**

```python
# tests/test_api/test_models.py
def test_print_status_model():
    from packages.api.models.printer import PrintStatus
    status = PrintStatus(
        state="printing", filename="test.gcode",
        progress=0.45, print_duration=1800,
        total_duration=3600, filament_used=123.4,
        current_layer=45, total_layers=100,
    )
    assert status.state == "printing"
    assert status.progress == 0.45

def test_temperature_model():
    from packages.api.models.printer import TemperatureReading
    temps = TemperatureReading(
        extruder_current=210.0, extruder_target=210.0,
        bed_current=60.0, bed_target=60.0,
    )
    assert temps.extruder_current == 210.0

def test_print_status_from_moonraker():
    from packages.api.models.printer import PrintStatus
    raw = {
        "print_stats": {"state": "printing", "filename": "test.gcode",
                        "total_duration": 3600, "print_duration": 1800,
                        "filament_used": 100.0,
                        "info": {"current_layer": 10, "total_layer": 50}},
        "display_status": {"progress": 0.2},
    }
    status = PrintStatus.from_moonraker(raw)
    assert status.state == "printing"
    assert status.progress == 0.2
    assert status.current_layer == 10
    assert status.total_layers == 50
```

**Step 2: Testi calistir — basarisiz**

Run: `pytest tests/test_api/test_models.py -v`
Expected: FAIL

**Step 3: Modelleri implement et**

```python
# packages/api/models/__init__.py
"""Pydantic data models."""

# packages/api/models/printer.py
"""Yazici veri modelleri."""
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional

class PrintStatus(BaseModel):
    state: str = "standby"
    filename: Optional[str] = None
    progress: float = 0.0
    print_duration: int = 0
    total_duration: int = 0
    filament_used: float = 0.0
    current_layer: int = 0
    total_layers: int = 0

    @classmethod
    def from_moonraker(cls, data: dict) -> PrintStatus:
        ps = data.get("print_stats", {})
        ds = data.get("display_status", {})
        info = ps.get("info", {})
        return cls(
            state=ps.get("state", "standby"),
            filename=ps.get("filename"),
            progress=ds.get("progress", 0.0),
            print_duration=int(ps.get("print_duration", 0)),
            total_duration=int(ps.get("total_duration", 0)),
            filament_used=float(ps.get("filament_used", 0.0)),
            current_layer=info.get("current_layer", 0) or 0,
            total_layers=info.get("total_layer", 0) or 0,
        )

class TemperatureReading(BaseModel):
    extruder_current: float = 0.0
    extruder_target: float = 0.0
    bed_current: float = 0.0
    bed_target: float = 0.0
    mcu_temperature: Optional[float] = None

    @classmethod
    def from_moonraker(cls, data: dict) -> TemperatureReading:
        ext = data.get("extruder", {})
        bed = data.get("heater_bed", {})
        return cls(
            extruder_current=ext.get("temperature", 0.0),
            extruder_target=ext.get("target", 0.0),
            bed_current=bed.get("temperature", 0.0),
            bed_target=bed.get("target", 0.0),
        )

class GCodeFileInfo(BaseModel):
    filename: str
    size: int = 0
    modified: float = 0.0

class FlowGuardStatus(BaseModel):
    verdict: str = "OK"
    filament_detected: bool = True
    heater_duty: float = 0.0
    tmc_sg_result: int = 0
    ai_class: str = "normal"
    current_layer: int = 0
    z_height: float = 0.0

class ServiceStatus(BaseModel):
    name: str
    active: bool = False
    enabled: bool = False
    memory_mb: float = 0.0

class SystemInfo(BaseModel):
    cpu_percent: float = 0.0
    ram_used_mb: int = 0
    ram_total_mb: int = 0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    uptime_seconds: int = 0

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "3.0.0"
    moonraker_connected: bool = False
    klipper_state: str = "unknown"
```

**Step 4: Testleri calistir**

Run: `pytest tests/test_api/test_models.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add packages/api/models/ tests/test_api/test_models.py
git commit -m "feat(api): add Pydantic data models with Moonraker factory methods"
```

---

## Task 4: Printer Status Router

**Files:**
- Create: `packages/api/routers/__init__.py`
- Create: `packages/api/routers/printer.py`
- Create: `packages/api/dependencies.py`
- Create: `tests/test_api/test_printer_router.py`
- Modify: `packages/api/main.py` — router kaydi

**Step 1: Test yaz**

```python
# tests/test_api/test_printer_router.py
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

MOCK_PRINTER_DATA = {
    "print_stats": {"state": "printing", "filename": "test.gcode",
                    "total_duration": 3600, "print_duration": 1800,
                    "filament_used": 100.0,
                    "info": {"current_layer": 10, "total_layer": 50}},
    "display_status": {"progress": 0.2},
    "extruder": {"temperature": 210.0, "target": 210.0, "power": 0.8},
    "heater_bed": {"temperature": 60.0, "target": 60.0, "power": 0.5},
}

@pytest.fixture
def client():
    mock_mr = MagicMock()
    mock_mr.get_printer_objects.return_value = MOCK_PRINTER_DATA
    mock_mr.is_available.return_value = True

    with patch("packages.api.dependencies.get_moonraker_client", return_value=mock_mr):
        from packages.api.main import app
        with TestClient(app) as c:
            yield c

def test_get_printer_status(client):
    resp = client.get("/api/v1/printer/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "printing"
    assert data["progress"] == 0.2

def test_get_temperatures(client):
    resp = client.get("/api/v1/printer/temperatures")
    assert resp.status_code == 200
    data = resp.json()
    assert data["extruder_current"] == 210.0
    assert data["bed_current"] == 60.0

def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

**Step 2: Testi calistir — basarisiz**

Run: `pytest tests/test_api/test_printer_router.py -v`
Expected: FAIL

**Step 3: Dependencies + Router implement et**

```python
# packages/api/dependencies.py
"""FastAPI dependency injection."""
from .moonraker_client import MoonrakerClient
from .config import settings

_moonraker_client: MoonrakerClient | None = None

def get_moonraker_client() -> MoonrakerClient:
    global _moonraker_client
    if _moonraker_client is None:
        _moonraker_client = MoonrakerClient(settings.moonraker_url)
    return _moonraker_client
```

```python
# packages/api/routers/__init__.py
"""API routers."""

# packages/api/routers/printer.py
"""Yazici durum endpoint'leri — salt-okunur sorgular."""
from fastapi import APIRouter, Depends
from ..dependencies import get_moonraker_client
from ..moonraker_client import MoonrakerClient
from ..models.printer import PrintStatus, TemperatureReading

router = APIRouter(prefix="/api/v1/printer", tags=["printer"])

@router.get("/status", response_model=PrintStatus)
async def get_printer_status(
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    data = mr.get_printer_objects("print_stats", "display_status", "extruder", "heater_bed")
    return PrintStatus.from_moonraker(data)

@router.get("/temperatures", response_model=TemperatureReading)
async def get_temperatures(
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    data = mr.get_printer_objects("extruder", "heater_bed")
    return TemperatureReading.from_moonraker(data)
```

**Step 4: main.py'ye router ekle**

```python
# main.py create_app() icine ekle:
from .routers import printer as printer_router
app.include_router(printer_router.router)
```

**Step 5: Testleri calistir**

Run: `pytest tests/test_api/test_printer_router.py -v`
Expected: 3 PASS

**Step 6: Commit**

```bash
git add packages/api/dependencies.py packages/api/routers/ tests/test_api/test_printer_router.py
git commit -m "feat(api): add printer status and temperature endpoints"
```

---

## Task 5: Print Control Router

**Files:**
- Create: `packages/api/routers/control.py`
- Create: `tests/test_api/test_control_router.py`
- Modify: `packages/api/main.py` — router kaydi

**Step 1: Test yaz**

```python
# tests/test_api/test_control_router.py
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    mock_mr = MagicMock()
    mock_mr.post.return_value = {"result": "ok"}
    mock_mr.send_gcode.return_value = True
    mock_mr.is_available.return_value = True
    mock_mr.get_printer_objects.return_value = {
        "print_stats": {"state": "printing"},
    }

    with patch("packages.api.dependencies.get_moonraker_client", return_value=mock_mr):
        from packages.api.main import app
        with TestClient(app) as c:
            yield c, mock_mr

def test_pause_print(client):
    c, mock_mr = client
    resp = c.post("/api/v1/printer/control/pause")
    assert resp.status_code == 200
    mock_mr.post.assert_called_with("/printer/print/pause")

def test_resume_print(client):
    c, mock_mr = client
    resp = c.post("/api/v1/printer/control/resume")
    assert resp.status_code == 200

def test_cancel_print(client):
    c, mock_mr = client
    resp = c.post("/api/v1/printer/control/cancel")
    assert resp.status_code == 200

def test_send_gcode(client):
    c, mock_mr = client
    resp = c.post("/api/v1/printer/control/gcode", json={"script": "G28"})
    assert resp.status_code == 200
    mock_mr.send_gcode.assert_called_with("G28")

def test_dangerous_gcode_rejected(client):
    c, _ = client
    resp = c.post("/api/v1/printer/control/gcode", json={"script": "M112"})
    assert resp.status_code == 403

def test_set_temperature(client):
    c, mock_mr = client
    resp = c.post("/api/v1/printer/control/temperature",
                  json={"heater": "extruder", "target": 200})
    assert resp.status_code == 200

def test_temperature_out_of_range(client):
    c, _ = client
    resp = c.post("/api/v1/printer/control/temperature",
                  json={"heater": "extruder", "target": 999})
    assert resp.status_code == 422
```

**Step 2: Testi calistir — basarisiz**

Run: `pytest tests/test_api/test_control_router.py -v`
Expected: FAIL

**Step 3: Control router implement et**

```python
# packages/api/routers/control.py
"""Yazici kontrol endpoint'leri — baski duraklat/devam/iptal, G-code, sicaklik."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..dependencies import get_moonraker_client
from ..moonraker_client import MoonrakerClient

router = APIRouter(prefix="/api/v1/printer/control", tags=["control"])

DANGEROUS_GCODE = {"M112", "FIRMWARE_RESTART", "SAVE_CONFIG", "SET_KINEMATIC_POSITION"}
TEMP_LIMITS = {"extruder": 300, "heater_bed": 120}

class GCodeRequest(BaseModel):
    script: str

class TemperatureRequest(BaseModel):
    heater: str
    target: float = Field(ge=0, le=300)

class ActionResponse(BaseModel):
    success: bool
    message: str = ""

@router.post("/pause", response_model=ActionResponse)
async def pause_print(mr: MoonrakerClient = Depends(get_moonraker_client)):
    result = mr.post("/printer/print/pause")
    return ActionResponse(success=result is not None, message="Baski duraklatildi")

@router.post("/resume", response_model=ActionResponse)
async def resume_print(mr: MoonrakerClient = Depends(get_moonraker_client)):
    result = mr.post("/printer/print/resume")
    return ActionResponse(success=result is not None, message="Baski devam ediyor")

@router.post("/cancel", response_model=ActionResponse)
async def cancel_print(mr: MoonrakerClient = Depends(get_moonraker_client)):
    result = mr.post("/printer/print/cancel")
    return ActionResponse(success=result is not None, message="Baski iptal edildi")

@router.post("/gcode", response_model=ActionResponse)
async def send_gcode(
    req: GCodeRequest,
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    cmd = req.script.strip().split()[0].upper() if req.script.strip() else ""
    if cmd in DANGEROUS_GCODE:
        raise HTTPException(403, f"Tehlikeli G-code: {cmd}")
    ok = mr.send_gcode(req.script)
    return ActionResponse(success=ok, message=f"G-code gonderildi: {req.script[:50]}")

@router.post("/temperature", response_model=ActionResponse)
async def set_temperature(
    req: TemperatureRequest,
    mr: MoonrakerClient = Depends(get_moonraker_client),
):
    limit = TEMP_LIMITS.get(req.heater, 300)
    if req.target > limit:
        raise HTTPException(422, f"{req.heater} max {limit}C")
    ok = mr.send_gcode(f"SET_HEATER_TEMPERATURE HEATER={req.heater} TARGET={req.target}")
    return ActionResponse(success=ok, message=f"{req.heater}={req.target}C")
```

**Step 4: main.py'ye control router ekle**

```python
from .routers import control as control_router
app.include_router(control_router.router)
```

**Step 5: Testleri calistir**

Run: `pytest tests/test_api/test_control_router.py -v`
Expected: 7 PASS

**Step 6: Commit**

```bash
git add packages/api/routers/control.py tests/test_api/test_control_router.py packages/api/main.py
git commit -m "feat(api): add print control endpoints with G-code safety"
```

---

## Task 6: Files Router

**Files:**
- Create: `packages/api/routers/files.py`
- Create: `tests/test_api/test_files_router.py`

**Step 1: Test yaz**

```python
# tests/test_api/test_files_router.py
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

MOCK_FILES = {
    "result": [
        {"path": "test.gcode", "size": 1024000, "modified": 1709500000},
        {"path": "benchy.gcode", "size": 512000, "modified": 1709400000},
    ]
}

@pytest.fixture
def client():
    mock_mr = MagicMock()
    mock_mr.get.return_value = MOCK_FILES
    mock_mr.is_available.return_value = True

    with patch("packages.api.dependencies.get_moonraker_client", return_value=mock_mr):
        from packages.api.main import app
        with TestClient(app) as c:
            yield c

def test_list_gcode_files(client):
    resp = client.get("/api/v1/files/gcodes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["filename"] == "test.gcode"
```

**Step 2: Testi calistir — basarisiz**

**Step 3: Files router implement et**

```python
# packages/api/routers/files.py
"""G-code dosya yonetimi endpoint'leri."""
from fastapi import APIRouter, Depends
from ..dependencies import get_moonraker_client
from ..moonraker_client import MoonrakerClient
from ..models.printer import GCodeFileInfo

router = APIRouter(prefix="/api/v1/files", tags=["files"])

@router.get("/gcodes", response_model=list[GCodeFileInfo])
async def list_gcode_files(mr: MoonrakerClient = Depends(get_moonraker_client)):
    resp = mr.get("/server/files/list?root=gcodes")
    files = []
    if resp and "result" in resp:
        for f in resp["result"]:
            files.append(GCodeFileInfo(
                filename=f.get("path", ""),
                size=f.get("size", 0),
                modified=f.get("modified", 0),
            ))
    return files
```

**Step 4: main.py'ye ekle, testleri calistir**

**Step 5: Commit**

```bash
git add packages/api/routers/files.py tests/test_api/test_files_router.py
git commit -m "feat(api): add G-code file listing endpoint"
```

---

## Task 7: System + FlowGuard Routers

**Files:**
- Create: `packages/api/routers/system.py`
- Create: `packages/api/routers/flowguard.py`
- Create: `tests/test_api/test_system_router.py`
- Create: `tests/test_api/test_flowguard_router.py`

**Step 1-3: Ayni TDD dongusu** — testleri yaz, basarisiz calistir, implement et.

System router: `/api/v1/system/info` (CPU/RAM/disk via psutil), `/api/v1/system/services` (systemctl durumu)

FlowGuard router: `/api/v1/flowguard/status` (son FlowGuard verdikti), `/api/v1/flowguard/history` (son 50 event)

**Step 4: Commit**

```bash
git commit -m "feat(api): add system info and FlowGuard status endpoints"
```

---

## Task 8: SQLite Veritabani Katmani

**Files:**
- Create: `packages/api/db/__init__.py`
- Create: `packages/api/db/engine.py`
- Create: `packages/api/db/tables.py`
- Create: `packages/api/db/migrations.py`
- Create: `tests/test_api/test_db.py`

**Step 1: Test yaz**

```python
# tests/test_api/test_db.py
import pytest
import sqlite3
import tempfile
from pathlib import Path

def test_tables_created():
    from packages.api.db.tables import TABLES_SQL
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        conn = sqlite3.connect(tmp.name)
        for sql in TABLES_SQL:
            conn.execute(sql)
        conn.commit()
        # Tablolarin var oldugundan emin ol
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor}
        assert "print_history" in tables
        assert "flowguard_events" in tables
        assert "config_changes" in tables
        conn.close()
```

**Step 2: Testi calistir — basarisiz**

**Step 3: DB katmanini implement et**

```python
# packages/api/db/tables.py
"""SQLite tablo tanimlari."""
TABLES_SQL = [
    """CREATE TABLE IF NOT EXISTS print_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        ended_at TEXT,
        duration_seconds INTEGER DEFAULT 0,
        status TEXT DEFAULT 'started',
        filament_used_mm REAL DEFAULT 0,
        layers_total INTEGER DEFAULT 0,
        layers_printed INTEGER DEFAULT 0,
        notes TEXT DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS flowguard_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        verdict TEXT NOT NULL,
        layer INTEGER DEFAULT 0,
        z_height REAL DEFAULT 0,
        filament_ok INTEGER DEFAULT 1,
        heater_duty REAL DEFAULT 0,
        tmc_sg INTEGER DEFAULT 0,
        ai_class TEXT DEFAULT 'normal',
        action_taken TEXT DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS config_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        section TEXT NOT NULL,
        key TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        changed_by TEXT DEFAULT 'api'
    )""",
]
```

```python
# packages/api/db/engine.py
"""SQLite engine — senkron (SBC icin basit)."""
import sqlite3
import logging
from pathlib import Path
from .tables import TABLES_SQL

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        for sql in TABLES_SQL:
            self._conn.execute(sql)
        self._conn.commit()
        logger.info("Database connected: %s", self.db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        assert self._conn is not None, "Database not connected"
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        if self._conn:
            self._conn.commit()

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None
```

**Step 4: Testleri calistir**

Run: `pytest tests/test_api/test_db.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/api/db/ tests/test_api/test_db.py
git commit -m "feat(api): add SQLite database layer with print history tables"
```

---

## Task 9: JWT Kimlik Dogrulama

**Files:**
- Create: `packages/api/middleware/__init__.py`
- Create: `packages/api/middleware/auth.py`
- Create: `packages/api/routers/auth.py`
- Create: `packages/api/models/auth.py`
- Create: `tests/test_api/test_auth_router.py`

**Step 1: Test yaz**

```python
# tests/test_api/test_auth_router.py
def test_login_returns_token():
    # POST /api/v1/auth/login ile token al
    pass

def test_protected_endpoint_without_token():
    # 401 donmeli
    pass

def test_protected_endpoint_with_valid_token():
    # 200 donmeli
    pass
```

**Step 2-4: TDD dongusu** — JWT encode/decode (python-jose), login endpoint, bearer token middleware.

**Not:** Ilk asamada basit kullanici/sifre (config'den). v4'te kullanici DB'si.

**Step 5: Commit**

```bash
git commit -m "feat(api): add JWT authentication with login endpoint"
```

---

## Task 10: WebSocket Gercek Zamanli Stream

**Files:**
- Create: `packages/api/routers/ws.py`
- Create: `tests/test_api/test_ws.py`

**Step 1: Test yaz**

```python
# tests/test_api/test_ws.py
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

def test_websocket_connection():
    # /api/v1/ws/printer endpoint'ine baglan
    # Sicaklik + durum JSON mesaji almali
    pass

def test_websocket_sends_periodic_data():
    # Her 2 saniyede veri gonderildigini dogrula
    pass
```

**Step 2-3: Implement et**

```python
# packages/api/routers/ws.py
"""WebSocket gercek zamanli yazici stream."""
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..dependencies import get_moonraker_client

router = APIRouter(tags=["websocket"])

@router.websocket("/api/v1/ws/printer")
async def ws_printer_stream(ws: WebSocket):
    await ws.accept()
    mr = get_moonraker_client()
    try:
        while True:
            data = mr.get_printer_objects(
                "print_stats", "extruder", "heater_bed", "display_status"
            )
            await ws.send_json({
                "type": "printer_update",
                "data": data,
            })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
```

**Step 4: Commit**

```bash
git commit -m "feat(api): add WebSocket real-time printer data stream"
```

---

## Task 11: Lifespan + Router Kayit + Entegrasyon Testi

**Files:**
- Modify: `packages/api/main.py` — tum router'lari kaydet, DB init
- Create: `tests/test_api/test_integration.py`

**Step 1: main.py'yi tamamla**

Lifespan'a DB init ekle, tum router'lari kaydet.

**Step 2: Entegrasyon testi**

```python
# tests/test_api/test_integration.py
def test_all_endpoints_registered():
    from packages.api.main import app
    routes = [r.path for r in app.routes]
    assert "/api/v1/health" in routes
    assert "/api/v1/printer/status" in routes
    assert "/api/v1/printer/temperatures" in routes
    assert "/api/v1/printer/control/pause" in routes
    assert "/api/v1/files/gcodes" in routes

def test_openapi_schema_valid():
    from packages.api.main import app
    schema = app.openapi()
    assert "paths" in schema
    assert "/api/v1/printer/status" in schema["paths"]
```

**Step 3: Commit**

```bash
git commit -m "feat(api): complete FastAPI backend with all routers and OpenAPI"
```

---

## Task 12: Ruff Lint + Son Dogrulama

**Step 1:** `python -m ruff check packages/api/ tests/test_api/ --fix`
**Step 2:** `pytest tests/test_api/ -v --tb=short`
**Step 3:** `python -c "from packages.api.main import app; print(app.openapi()['info'])"`
**Step 4:** Final commit

```bash
git commit -m "chore(api): lint fixes and final validation"
```

---

## Ozet: 12 Task, Tahmini 45-60 Dakika

| Task | Icerik | Dosya Sayisi |
|------|--------|:---:|
| 1 | Proje iskelesi + bagimliliklar | 4 |
| 2 | MoonrakerClient (cache+retry) | 4 |
| 3 | Pydantic data modelleri | 3 |
| 4 | Printer status router | 4 |
| 5 | Print control router | 2 |
| 6 | Files router | 2 |
| 7 | System + FlowGuard routers | 4 |
| 8 | SQLite veritabani katmani | 4 |
| 9 | JWT kimlik dogrulama | 5 |
| 10 | WebSocket stream | 2 |
| 11 | Entegrasyon + OpenAPI | 2 |
| 12 | Lint + dogrulama | 0 |

**Toplam**: ~36 yeni dosya, 12 commit, TDD tum adimlar

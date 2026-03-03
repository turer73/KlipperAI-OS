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

    from packages.api.main import app
    from packages.api.dependencies import get_moonraker_client
    app.dependency_overrides[get_moonraker_client] = lambda: mock_mr
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

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

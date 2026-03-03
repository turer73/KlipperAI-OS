import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from packages.api.dependencies import get_moonraker_client

@pytest.fixture
def client():
    mock_mr = MagicMock()
    mock_mr.post.return_value = {"result": "ok"}
    mock_mr.send_gcode.return_value = True
    mock_mr.is_available.return_value = True
    mock_mr.get_printer_objects.return_value = {
        "print_stats": {"state": "printing"},
    }

    from packages.api.main import app
    app.dependency_overrides[get_moonraker_client] = lambda: mock_mr
    with TestClient(app) as c:
        yield c, mock_mr
    app.dependency_overrides.clear()

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

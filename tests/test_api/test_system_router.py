"""System router endpoint testleri."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from packages.api.main import app
    with TestClient(app) as c:
        yield c


def test_system_info_endpoint(client):
    resp = client.get("/api/v1/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "cpu_percent" in data
    assert "ram_total_mb" in data
    assert "ram_used_mb" in data
    assert "disk_used_gb" in data
    assert "disk_total_gb" in data
    assert "uptime_seconds" in data


def test_system_info_returns_numeric_values(client):
    resp = client.get("/api/v1/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["cpu_percent"], (int, float))
    assert isinstance(data["ram_total_mb"], int)
    assert isinstance(data["ram_used_mb"], int)
    assert isinstance(data["disk_used_gb"], (int, float))
    assert isinstance(data["disk_total_gb"], (int, float))
    assert isinstance(data["uptime_seconds"], int)


def test_system_info_without_psutil(client):
    """psutil import edilemezse varsayilan degerler doner."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("No psutil")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        resp = client.get("/api/v1/system/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cpu_percent"] == 0.0
        assert data["ram_total_mb"] == 0
        assert data["ram_used_mb"] == 0


def test_services_endpoint(client):
    resp = client.get("/api/v1/system/services")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_services_returns_expected_service_names(client):
    resp = client.get("/api/v1/system/services")
    assert resp.status_code == 200
    data = resp.json()
    names = [s["name"] for s in data]
    assert "klipper" in names
    assert "moonraker" in names
    assert "ollama" in names


def test_services_structure(client):
    resp = client.get("/api/v1/system/services")
    assert resp.status_code == 200
    data = resp.json()
    if data:
        svc = data[0]
        assert "name" in svc
        assert "active" in svc
        assert "enabled" in svc

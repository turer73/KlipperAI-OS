import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from packages.api.dependencies import get_moonraker_client

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

    from packages.api.main import app
    app.dependency_overrides[get_moonraker_client] = lambda: mock_mr
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_list_gcode_files(client):
    resp = client.get("/api/v1/files/gcodes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["filename"] == "test.gcode"

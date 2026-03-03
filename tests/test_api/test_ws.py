"""WebSocket stream tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from packages.api.main import create_app


MOCK_PRINTER_DATA = {
    "print_stats": {"state": "printing", "filename": "test.gcode"},
    "extruder": {"temperature": 210.0, "target": 210.0},
    "heater_bed": {"temperature": 60.0, "target": 60.0},
    "display_status": {"progress": 0.45},
}


def _mock_moonraker():
    mock = MagicMock()
    mock.get_printer_objects.return_value = MOCK_PRINTER_DATA
    return mock


def test_websocket_connection():
    """WebSocket baglantisi acilir ve printer_update mesaji alinir."""
    app = create_app()
    mock = _mock_moonraker()
    with patch("packages.api.routers.ws.get_moonraker_client", return_value=mock):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/printer") as ws:
            data = ws.receive_json()
            assert data["type"] == "printer_update"
            assert "data" in data
            assert data["data"]["extruder"]["temperature"] == 210.0


def test_websocket_sends_printer_data():
    """WebSocket mesaji yazici verilerini icerir."""
    app = create_app()
    mock = _mock_moonraker()
    with patch("packages.api.routers.ws.get_moonraker_client", return_value=mock):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/printer") as ws:
            msg = ws.receive_json()
            assert msg["data"]["print_stats"]["state"] == "printing"
            assert msg["data"]["heater_bed"]["temperature"] == 60.0

"""FlowGuard router endpoint testleri."""
import pytest
import json
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from packages.api.main import app
    with TestClient(app) as c:
        yield c


def test_flowguard_status_no_log(client):
    """Log dosyasi yoksa varsayilan FlowGuardStatus doner."""
    with patch("packages.api.routers.flowguard.FLOWGUARD_LOG", Path("/nonexistent")):
        resp = client.get("/api/v1/flowguard/status")
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "OK"
        assert resp.json()["filament_detected"] is True
        assert resp.json()["ai_class"] == "normal"


def test_flowguard_status_with_log(client, tmp_path):
    """Log dosyasi varsa son satirdaki veriyi doner."""
    log_file = tmp_path / "flowguard.jsonl"
    log_file.write_text(
        json.dumps({"verdict": "WARNING", "ai_class": "stringing"}) + "\n"
    )
    with patch("packages.api.routers.flowguard.FLOWGUARD_LOG", log_file):
        resp = client.get("/api/v1/flowguard/status")
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "WARNING"
        assert resp.json()["ai_class"] == "stringing"


def test_flowguard_status_reads_last_line(client, tmp_path):
    """Birden fazla satir varsa son satiri okur."""
    log_file = tmp_path / "flowguard.jsonl"
    lines = [
        json.dumps({"verdict": "OK", "ai_class": "normal"}),
        json.dumps({"verdict": "CRITICAL", "ai_class": "spaghetti", "z_height": 5.2}),
    ]
    log_file.write_text("\n".join(lines) + "\n")
    with patch("packages.api.routers.flowguard.FLOWGUARD_LOG", log_file):
        resp = client.get("/api/v1/flowguard/status")
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "CRITICAL"
        assert resp.json()["ai_class"] == "spaghetti"
        assert resp.json()["z_height"] == 5.2


def test_flowguard_status_corrupt_json(client, tmp_path):
    """Bozuk JSON satirlari varsayilan deger dondurur."""
    log_file = tmp_path / "flowguard.jsonl"
    log_file.write_text("this is not json\n")
    with patch("packages.api.routers.flowguard.FLOWGUARD_LOG", log_file):
        resp = client.get("/api/v1/flowguard/status")
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "OK"


def test_flowguard_history_empty(client):
    """Log dosyasi yoksa bos liste doner."""
    with patch("packages.api.routers.flowguard.FLOWGUARD_LOG", Path("/nonexistent")):
        resp = client.get("/api/v1/flowguard/history")
        assert resp.status_code == 200
        assert resp.json() == []


def test_flowguard_history_with_events(client, tmp_path):
    """Log dosyasindan son 50 eventi okur."""
    log_file = tmp_path / "flowguard.jsonl"
    lines = [
        json.dumps({"verdict": "OK", "ai_class": "normal", "current_layer": i})
        for i in range(5)
    ]
    log_file.write_text("\n".join(lines) + "\n")
    with patch("packages.api.routers.flowguard.FLOWGUARD_LOG", log_file):
        resp = client.get("/api/v1/flowguard/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        assert data[0]["current_layer"] == 0
        assert data[4]["current_layer"] == 4


def test_flowguard_history_max_50(client, tmp_path):
    """50'den fazla event varsa son 50'yi dondurur."""
    log_file = tmp_path / "flowguard.jsonl"
    lines = [
        json.dumps({"verdict": "OK", "current_layer": i})
        for i in range(80)
    ]
    log_file.write_text("\n".join(lines) + "\n")
    with patch("packages.api.routers.flowguard.FLOWGUARD_LOG", log_file):
        resp = client.get("/api/v1/flowguard/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 50
        # Son 50 satir: layer 30-79
        assert data[0]["current_layer"] == 30
        assert data[-1]["current_layer"] == 79


def test_flowguard_history_skips_bad_lines(client, tmp_path):
    """Bozuk JSON satirlari atlanir."""
    log_file = tmp_path / "flowguard.jsonl"
    lines = [
        json.dumps({"verdict": "OK", "current_layer": 1}),
        "bad json line",
        json.dumps({"verdict": "WARNING", "current_layer": 3}),
    ]
    log_file.write_text("\n".join(lines) + "\n")
    with patch("packages.api.routers.flowguard.FLOWGUARD_LOG", log_file):
        resp = client.get("/api/v1/flowguard/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["current_layer"] == 1
        assert data[1]["current_layer"] == 3

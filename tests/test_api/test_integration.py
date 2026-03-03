"""Integration tests — endpoint registration and OpenAPI schema."""
from __future__ import annotations


def test_all_endpoints_registered():
    from packages.api.main import app

    routes = [r.path for r in app.routes]
    assert "/api/v1/health" in routes
    assert "/api/v1/printer/status" in routes
    assert "/api/v1/printer/temperatures" in routes
    assert "/api/v1/printer/control/pause" in routes
    assert "/api/v1/printer/control/resume" in routes
    assert "/api/v1/printer/control/cancel" in routes
    assert "/api/v1/printer/control/gcode" in routes
    assert "/api/v1/printer/control/temperature" in routes
    assert "/api/v1/files/gcodes" in routes
    assert "/api/v1/system/info" in routes
    assert "/api/v1/system/services" in routes
    assert "/api/v1/flowguard/status" in routes
    assert "/api/v1/flowguard/history" in routes
    assert "/api/v1/auth/login" in routes
    assert "/api/v1/ws/printer" in routes


def test_openapi_schema_valid():
    from packages.api.main import app

    schema = app.openapi()
    assert "paths" in schema
    assert "/api/v1/printer/status" in schema["paths"]
    assert "/api/v1/auth/login" in schema["paths"]
    assert schema["info"]["title"] == "KlipperOS-AI API"
    assert schema["info"]["version"] == "3.0.0"


def test_openapi_schema_has_all_tags():
    from packages.api.main import app

    schema = app.openapi()
    paths = schema["paths"]
    # Verify we have paths from all router groups
    path_prefixes = {p.rsplit("/", 1)[0] for p in paths}
    assert "/api/v1/printer" in path_prefixes
    assert "/api/v1/printer/control" in path_prefixes
    assert "/api/v1/files" in path_prefixes
    assert "/api/v1/system" in path_prefixes
    assert "/api/v1/flowguard" in path_prefixes
    assert "/api/v1/auth" in path_prefixes

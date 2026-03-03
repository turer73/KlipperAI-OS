"""JWT authentication tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from packages.api.main import create_app


def get_app():
    app = create_app()
    return app


def test_login_returns_token():
    app = get_app()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "klipperos"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials():
    app = get_app()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_protected_endpoint_without_token():
    """verify_token dependency rejects requests with no credentials."""
    from packages.api.middleware.auth import verify_token

    from fastapi import Depends, FastAPI

    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected(user: str = Depends(verify_token)):
        return {"user": user}

    client = TestClient(test_app)
    resp = client.get("/protected")
    assert resp.status_code in (401, 403)  # HTTPBearer rejects missing credentials


def test_protected_endpoint_with_valid_token():
    from packages.api.middleware.auth import create_access_token, verify_token

    from fastapi import Depends, FastAPI

    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected(user: str = Depends(verify_token)):
        return {"user": user}

    client = TestClient(test_app)
    token = create_access_token("admin")
    resp = client.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["user"] == "admin"


def test_protected_endpoint_with_invalid_token():
    from packages.api.middleware.auth import verify_token

    from fastapi import Depends, FastAPI

    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected(user: str = Depends(verify_token)):
        return {"user": user}

    client = TestClient(test_app)
    resp = client.get(
        "/protected", headers={"Authorization": "Bearer invalid-token"}
    )
    assert resp.status_code == 401

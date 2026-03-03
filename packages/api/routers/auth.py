"""Auth router -- login endpoint."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, status

from ..middleware.auth import create_access_token
from ..models.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

API_USER = os.getenv("KOS_API_USER", "admin")
API_PASS = os.getenv("KOS_API_PASS", "klipperos")


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate and return a JWT access token."""
    if body.username != API_USER or body.password != API_PASS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(subject=body.username)
    return TokenResponse(access_token=token)

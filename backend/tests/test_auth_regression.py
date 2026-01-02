"""Auth regression tests (HTTP)

These tests intentionally hit a running backend (no TestClient) to avoid
lifespan/event-loop issues from heavy runtime initializers.

Run:
  API_URL=https://your-backend-url pytest -q /app/backend/tests/test_auth_regression.py

If API_URL is not provided, this reads frontend/.env REACT_APP_BACKEND_URL.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from jose import jwt


def _read_frontend_backend_url() -> str:
    try:
        with open("/app/frontend/.env", "r") as f:
            for raw in f:
                line = raw.strip()
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


@pytest.fixture(scope="session")
def api_url() -> str:
    url = os.environ.get("API_URL") or _read_frontend_backend_url()
    assert url, "API_URL env var required (or frontend/.env REACT_APP_BACKEND_URL)"
    return url.rstrip("/")


@pytest.fixture(scope="session")
def jwt_secret() -> str:
    # Prefer env, fallback to backend/.env
    secret = os.environ.get("JWT_SECRET_KEY")
    if secret:
        return secret

    try:
        with open("/app/backend/.env", "r") as f:
            for raw in f:
                line = raw.strip()
                if line.startswith("JWT_SECRET_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass

    raise AssertionError("JWT_SECRET_KEY must be set")


def _post(url: str, path: str, json_body: dict, headers: dict | None = None):
    return requests.post(f"{url}{path}", json=json_body, headers=headers or {}, timeout=30)


def _get(url: str, path: str, headers: dict | None = None):
    return requests.get(f"{url}{path}", headers=headers or {}, timeout=30)


def test_auth_me_requires_auth(api_url: str):
    res = _get(api_url, "/api/auth/me")
    assert res.status_code == 401


def test_owner_login_success(api_url: str):
    res = _post(
        api_url,
        "/api/auth/login",
        {"username_or_email": "owner", "password": "Haven!2026_Strong#Auth"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert body.get("token_type") == "bearer"


def test_owner_login_wrong_password_fails(api_url: str):
    res = _post(
        api_url,
        "/api/auth/login",
        {"username_or_email": "owner", "password": "WRONG_PASSWORD"},
    )
    assert res.status_code == 401


def test_auth_me_invalid_token_401(api_url: str):
    res = _get(api_url, "/api/auth/me", headers={"Authorization": "Bearer invalid"})
    assert res.status_code == 401


def test_auth_me_expired_token_401(api_url: str, jwt_secret: str):
    payload = {
        "sub": "test",
        "username": "test",
        "role": "user",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")

    res = _get(api_url, "/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401

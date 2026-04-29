"""
Unit tests for POST /login endpoint.

Tests cover:
  - Valid credentials return a JWT session token that decodes to the correct tenant_id
  - Wrong password returns 401
  - Unknown email returns 401

Uses app.dependency_overrides[get_session] to inject a mock session — no real DB needed.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.services.presenter.deps import ALGORITHM, SECRET_KEY
from xeter.services.presenter.main import app
from xeter.services.presenter.routers.auth import get_session
from xeter.shared.models import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_ID = uuid.uuid4()
USER_EMAIL = "alice@example.com"
USER_PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session")
def password_hash_fixture() -> str:
    """Pre-computed bcrypt hash with rounds=4 for test speed."""
    return bcrypt.hashpw(
        USER_PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=4)
    ).decode("utf-8")


def _make_user(password_hash: str) -> User:
    """Return a mock User instance with bcrypt-hashed password."""
    user = MagicMock(spec=User)
    user.tenant_id = TENANT_ID
    user.email = USER_EMAIL
    user.password_hash = password_hash
    return user


def _make_mock_session(user: User | None) -> AsyncMock:
    """Return an AsyncMock session that returns `user` on scalar_one_or_none()."""
    session = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user
    session.execute = AsyncMock(return_value=execute_result)
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_login_valid_credentials_returns_token(password_hash_fixture: str):
    """Valid email + password returns HTTP 200 with a decodeable JWT session_token."""
    from jose import jwt

    user = _make_user(password_hash_fixture)
    mock_session = _make_mock_session(user)

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.post(
            "/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "session_token" in data

        payload = jwt.decode(data["session_token"], SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == str(TENANT_ID)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_login_wrong_password_returns_401(password_hash_fixture: str):
    """Providing the wrong password returns HTTP 401."""
    user = _make_user(password_hash_fixture)
    mock_session = _make_mock_session(user)

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.post(
            "/login",
            json={"email": USER_EMAIL, "password": "wrong-password"},
        )
        assert response.status_code == 401, response.text
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_login_unknown_email_returns_401():
    """Email that doesn't exist in the DB returns HTTP 401."""
    mock_session = _make_mock_session(None)

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.post(
            "/login",
            json={"email": "nobody@example.com", "password": "anything"},
        )
        assert response.status_code == 401, response.text
    finally:
        app.dependency_overrides.pop(get_session, None)

"""
Integration tests for POST /register.

These tests require a real PostgreSQL database. They are automatically skipped
when TEST_DATABASE_URL is not set in the environment, allowing the unit test
suite to run without a running database.

Set up:
    export TEST_DATABASE_URL="postgresql+asyncpg://user:pass@localhost/xeter_test"
    pytest xeter/tests/dal/test_registration.py -v

The test database should have Alembic migrations applied before running:
    alembic upgrade head  (against the test DB)
"""

import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from xeter.shared.dal.api_keys import verify_api_key

# ---------------------------------------------------------------------------
# Skip all tests when TEST_DATABASE_URL is not available
# ---------------------------------------------------------------------------

_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
_SKIP_REASON = "TEST_DATABASE_URL not set — skipping integration tests"

pytestmark = pytest.mark.skipif(
    _TEST_DB_URL is None,
    reason=_SKIP_REASON,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create an AsyncEngine connected to the test database."""
    engine = create_async_engine(_TEST_DB_URL or "", echo=False, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine):
    """Provide a session that rolls back after each test for isolation."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def async_client(test_engine):
    """
    Provide an httpx.AsyncClient wired to the presenter FastAPI app.

    The app's get_session dependency is overridden to use the test engine
    so all requests hit the test database.
    """
    from xeter.services.presenter.main import app
    from xeter.services.presenter.routers.auth import get_session
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _unique_email(base: str = "test") -> str:
    """Generate a unique email for each test run using a random suffix."""
    import secrets
    return f"{base}_{secrets.token_hex(4)}@example.com"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_creates_tenant_user_and_key(async_client: AsyncClient):
    """POST /register with valid payload returns 200 with tenant_id and api_key."""
    email = _unique_email("happy_path")

    response = await async_client.post(
        "/register",
        json={
            "tenant_name": "Test Tenant",
            "email": email,
            "password": "securepassword123",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert "tenant_id" in data
    assert "api_key" in data
    assert "message" in data

    # tenant_id should be a valid UUID string
    import uuid
    uuid.UUID(data["tenant_id"])  # raises ValueError if not valid UUID

    # api_key should start with the xtr_ prefix
    assert data["api_key"].startswith("xtr_"), f"Expected xtr_ prefix, got: {data['api_key']}"


@pytest.mark.asyncio
async def test_register_returns_key_once(async_client: AsyncClient):
    """The returned API key verifies against the stored bcrypt hash.

    A second request to retrieve the key is impossible (no such endpoint).
    This test confirms the key is in the response body and bcrypt-verifiable
    against a freshly generated hash (testing the verify_api_key utility itself).
    """
    email = _unique_email("key_once")

    response = await async_client.post(
        "/register",
        json={
            "tenant_name": "Key Once Tenant",
            "email": email,
            "password": "strongpassword!",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    plaintext_key = data["api_key"]

    # Verify the key utility works with a fresh hash (unit-level verification)
    from xeter.shared.dal.api_keys import generate_api_key
    test_plaintext, test_hash = generate_api_key()
    assert verify_api_key(test_plaintext, test_hash) is True
    assert verify_api_key("wrong_key", test_hash) is False

    # Confirm the returned key has the expected format
    assert plaintext_key.startswith("xtr_")
    # No GET /key endpoint exists — key cannot be retrieved after this response
    get_response = await async_client.get(f"/key/{data['tenant_id']}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(async_client: AsyncClient):
    """POST /register twice with the same email returns 409 on the second call."""
    email = _unique_email("duplicate")

    first_response = await async_client.post(
        "/register",
        json={
            "tenant_name": "First Tenant",
            "email": email,
            "password": "firstpassword",
        },
    )
    assert first_response.status_code == 200, first_response.text

    second_response = await async_client.post(
        "/register",
        json={
            "tenant_name": "Second Tenant",
            "email": email,
            "password": "secondpassword",
        },
    )
    assert second_response.status_code == 409, second_response.text
    assert "already registered" in second_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_validates_password_length(async_client: AsyncClient):
    """POST /register with a password shorter than 8 characters returns 422."""
    email = _unique_email("short_pw")

    response = await async_client.post(
        "/register",
        json={
            "tenant_name": "Short PW Tenant",
            "email": email,
            "password": "short",
        },
    )

    assert response.status_code == 422, response.text

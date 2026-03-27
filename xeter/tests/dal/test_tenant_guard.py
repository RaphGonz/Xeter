"""
TDD tests for the DAL tenant guard and repository guard enforcement.

All tests are pure unit tests — no database connection is required.
The SQLAlchemy session is mocked via AsyncMock.

Behaviors covered:
  - require_tenant() raises MissingTenantError for None, "", whitespace
  - require_tenant() returns value unchanged for a valid tenant_id
  - TenantRepository.get_by_id(id, tenant_id=None) raises MissingTenantError
  - UserRepository.get_by_email(email, tenant_id=None) raises MissingTenantError
  - ApiKeyRepository.verify(key, tenant_id=None) raises MissingTenantError
  - generate_api_key() returns (plaintext, hash) where plaintext starts with "xtr_"
  - Two generate_api_key() calls return different keys
  - verify_api_key(plaintext, hash) returns True for matching key
  - verify_api_key("wrong", hash) returns False
"""

import pytest

from xeter.shared.dal.base import MissingTenantError, require_tenant
from xeter.shared.dal.tenants import TenantRepository
from xeter.shared.dal.users import UserRepository
from xeter.shared.dal.api_keys import (
    ApiKeyRepository,
    generate_api_key,
    verify_api_key,
)


# ---------------------------------------------------------------------------
# require_tenant() unit tests
# ---------------------------------------------------------------------------

class TestRequireTenant:
    """Guard function raises MissingTenantError for absent/empty tenant IDs."""

    def test_none_raises(self):
        with pytest.raises(MissingTenantError):
            require_tenant(None)

    def test_empty_string_raises(self):
        with pytest.raises(MissingTenantError):
            require_tenant("")

    def test_whitespace_raises(self):
        with pytest.raises(MissingTenantError):
            require_tenant("   ")

    def test_valid_uuid_returns_unchanged(self):
        tid = "00000000-0000-0000-0000-000000000001"
        result = require_tenant(tid)
        assert result == tid

    def test_missing_tenant_error_is_runtime_error(self):
        """MissingTenantError must be a subclass of RuntimeError."""
        assert issubclass(MissingTenantError, RuntimeError)


# ---------------------------------------------------------------------------
# Repository guard tests — no DB call should be made
# ---------------------------------------------------------------------------

class TestRepositoryGuards:
    """Each repository method raises MissingTenantError before touching DB."""

    @pytest.mark.asyncio
    async def test_tenant_repo_get_by_id_no_tenant(self, mock_session):
        repo = TenantRepository(session=mock_session)
        with pytest.raises(MissingTenantError):
            await repo.get_by_id(tenant_id=None)
        # No DB call should have been made
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_repo_get_by_email_no_tenant(self, mock_session):
        repo = UserRepository(session=mock_session)
        with pytest.raises(MissingTenantError):
            await repo.get_by_email(email="user@example.com", tenant_id=None)
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_key_repo_get_by_tenant_no_tenant(self, mock_session):
        repo = ApiKeyRepository(session=mock_session)
        with pytest.raises(MissingTenantError):
            await repo.get_by_tenant(tenant_id=None)
        mock_session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# generate_api_key() and verify_api_key() unit tests
# ---------------------------------------------------------------------------

class TestApiKeyGeneration:
    """API key generation and verification without any database interaction."""

    def test_generate_returns_tuple(self):
        result = generate_api_key()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_plaintext_has_xtr_prefix(self):
        plaintext, _ = generate_api_key()
        assert plaintext.startswith("xtr_"), (
            f"Expected key to start with 'xtr_', got: {plaintext!r}"
        )

    def test_two_keys_are_different(self):
        key1, _ = generate_api_key()
        key2, _ = generate_api_key()
        assert key1 != key2, "Two generated keys should never be identical"

    def test_verify_correct_key_returns_true(self):
        plaintext, stored_hash = generate_api_key()
        assert verify_api_key(plaintext, stored_hash) is True

    def test_verify_wrong_key_returns_false(self):
        _, stored_hash = generate_api_key()
        assert verify_api_key("wrong_key", stored_hash) is False

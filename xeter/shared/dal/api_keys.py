"""
ApiKeyRepository and API key generation/verification utilities.

API keys are generated with a recognisable ``xtr_`` prefix followed by
32 random URL-safe bytes. The plaintext key is returned exactly once
(to be shown to the user) and NEVER persisted. Only the bcrypt hash
is stored in the database.

Exports:
  - generate_api_key() -> tuple[str, str]   — (plaintext, bcrypt_hash)
  - verify_api_key(plaintext, stored_hash)  — True if matching
  - ApiKeyRepository                        — CRUD for api_keys table

Usage::

    plaintext, key_hash = generate_api_key()
    # show plaintext to user once, then discard
    repo = ApiKeyRepository(session=session)
    record = await repo.create(tenant_id="<uuid>", key_hash=key_hash)

    # Verification at auth time:
    ok = verify_api_key(supplied_key, stored_hash)
"""

import secrets
import uuid

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.shared.dal.base import require_tenant
from xeter.shared.models import ApiKey

# Prefix applied to every generated API key for easy identification.
_API_KEY_PREFIX = "xtr_"


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key and its bcrypt hash.

    Returns a tuple of:
      - plaintext: The raw key string (must be shown to the user and discarded).
                   Always starts with ``xtr_``.
      - stored_hash: bcrypt hash of plaintext (safe to persist in the database).

    The plaintext must NEVER be stored. The stored_hash is what goes in
    the ``api_keys.key_hash`` column.

    Returns:
        (plaintext, stored_hash) — both are str.
    """
    raw = secrets.token_urlsafe(32)
    plaintext = f"{_API_KEY_PREFIX}{raw}"
    stored_hash = bcrypt.hashpw(
        plaintext.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    return plaintext, stored_hash


def verify_api_key(plaintext: str, stored_hash: str) -> bool:
    """Verify a plaintext API key against a stored bcrypt hash.

    Args:
        plaintext:   The raw key provided by the caller.
        stored_hash: The bcrypt hash stored in the database.

    Returns:
        True if the key matches the hash, False otherwise.
    """
    try:
        return bcrypt.checkpw(
            plaintext.encode("utf-8"), stored_hash.encode("utf-8")
        )
    except Exception:
        return False


class ApiKeyRepository:
    """Repository for API key CRUD operations within a tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, tenant_id: str | None, key_hash: str) -> ApiKey:
        """Insert a new API key record for the given tenant.

        The caller is responsible for generating the key hash via
        generate_api_key() and storing the plaintext safely before calling this.

        Args:
            tenant_id: UUID string of the owning tenant.
            key_hash:  bcrypt hash of the plaintext API key.

        Returns:
            The freshly inserted ApiKey ORM object.

        Raises:
            MissingTenantError: If tenant_id is None, empty, or whitespace-only.
        """
        require_tenant(tenant_id)
        api_key = ApiKey(
            tenant_id=uuid.UUID(str(tenant_id)),
            key_hash=key_hash,
        )
        self._session.add(api_key)
        await self._session.flush()
        await self._session.refresh(api_key)
        return api_key

    async def get_by_tenant(self, tenant_id: str | None) -> list[ApiKey]:
        """Return all API key records for the given tenant.

        Args:
            tenant_id: UUID string of the owning tenant.

        Returns:
            List of ApiKey ORM objects (may be empty).

        Raises:
            MissingTenantError: If tenant_id is None, empty, or whitespace-only.
        """
        require_tenant(tenant_id)
        result = await self._session.execute(
            select(ApiKey).where(
                ApiKey.tenant_id == uuid.UUID(str(tenant_id))
            )
        )
        return list(result.scalars().all())

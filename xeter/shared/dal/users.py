"""
UserRepository — DAL for the users table.

All methods call require_tenant(tenant_id) as their first operation.
The guard raises MissingTenantError before any database interaction if
tenant_id is absent or empty — this is the Python-boundary enforcement.

Usage::

    repo = UserRepository(session=session)
    user = await repo.create(
        tenant_id="<uuid>",
        email="user@example.com",
        password_hash="<bcrypt-hash>",
    )
    found = await repo.get_by_email(email="user@example.com", tenant_id="<uuid>")
"""

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.shared.dal.base import require_tenant
from xeter.shared.models import User


class UserRepository:
    """Repository for user CRUD operations within a tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, tenant_id: str | None, email: str, password_hash: str
    ) -> User:
        """Insert a new user row for the given tenant.

        Args:
            tenant_id:     UUID string of the owning tenant.
            email:         User's email address (must be unique within the tenant).
            password_hash: Pre-hashed password (never store plaintext).

        Returns:
            The freshly inserted User ORM object.

        Raises:
            MissingTenantError: If tenant_id is None, empty, or whitespace-only.
        """
        require_tenant(tenant_id)
        user = User(
            tenant_id=uuid.UUID(str(tenant_id)),
            email=email,
            password_hash=password_hash,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def get_by_email(
        self, email: str, tenant_id: str | None
    ) -> User | None:
        """Look up a user by email within the given tenant.

        Args:
            email:     Email address to search for.
            tenant_id: UUID string of the owning tenant.

        Returns:
            The matching User or None if not found.

        Raises:
            MissingTenantError: If tenant_id is None, empty, or whitespace-only.
        """
        require_tenant(tenant_id)
        result = await self._session.execute(
            select(User).where(
                User.email == email,
                User.tenant_id == uuid.UUID(str(tenant_id)),
            )
        )
        return result.scalar_one_or_none()

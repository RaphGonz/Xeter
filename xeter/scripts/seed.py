"""
Seed script: creates a fixed dev tenant, user, and API key for local development.
Run: python -m xeter.scripts.seed  (or: make seed)

Idempotent: if the dev tenant already exists, prints a warning and exits without error.
Dev API key: dev-api-key-local (fixed, hardcoded — consistent with .env.example)

Prerequisites:
  DATABASE_URL   — postgresql+asyncpg://... (required)
  CLICKHOUSE_*   — optional, defaults to localhost:8123

Usage::

    make seed
    # or
    python -m xeter.scripts.seed
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.shared.db.postgres import get_async_session_factory
from xeter.shared.db.clickhouse import get_clickhouse_client, create_spans_table
from xeter.shared.models import Tenant, User, ApiKey

# ---------------------------------------------------------------------------
# Fixed dev credentials — consistent with .env.example
# ---------------------------------------------------------------------------
_DEV_TENANT_NAME = "dev-tenant"
_DEV_USER_EMAIL = "dev@example.com"
_DEV_USER_PASSWORD = "dev_password_local"
_DEV_API_KEY = "dev-api-key-local"


async def _seed_postgres(session: AsyncSession) -> None:
    """Insert the dev tenant, user, and API key into PostgreSQL.

    Idempotent: exits cleanly if dev-tenant already exists.
    """
    async with session.begin():
        # Check if dev-tenant already exists
        result = await session.execute(
            select(Tenant).where(Tenant.name == _DEV_TENANT_NAME)
        )
        existing_tenant = result.scalar_one_or_none()

        if existing_tenant is not None:
            print("Seed already applied. Run `make reset` to start fresh.")
            return

        # Create tenant
        tenant = Tenant(name=_DEV_TENANT_NAME)
        session.add(tenant)
        await session.flush()
        await session.refresh(tenant)

        tenant_id = tenant.tenant_id

        # Create user with hashed password
        password_hash = bcrypt.hashpw(
            _DEV_USER_PASSWORD.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        user = User(
            tenant_id=tenant_id,
            email=_DEV_USER_EMAIL,
            password_hash=password_hash,
        )
        session.add(user)

        # Create API key with hash of fixed dev key
        # The fixed key "dev-api-key-local" is hashed and stored — consistent
        # with how generate_api_key() works (only hash persisted, never plaintext).
        key_hash = bcrypt.hashpw(
            _DEV_API_KEY.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        api_key = ApiKey(
            tenant_id=tenant_id,
            key_hash=key_hash,
        )
        session.add(api_key)

    print(f"Seed complete. Dev API key: {_DEV_API_KEY}")


def _seed_clickhouse() -> None:
    """Ensure the ClickHouse spans table exists."""
    client = get_clickhouse_client()
    create_spans_table(client)


async def main() -> None:
    """Run the seed script end to end."""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        await _seed_postgres(session)

    _seed_clickhouse()


if __name__ == "__main__":
    asyncio.run(main())

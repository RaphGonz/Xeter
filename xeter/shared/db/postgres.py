"""
PostgreSQL async session factory and tenant RLS context manager.

Provides:
  - get_async_engine()          — creates AsyncEngine from DATABASE_URL env var
  - get_async_session_factory() — returns async_sessionmaker bound to engine
  - tenant_session()            — context manager that sets SET LOCAL app.current_tenant_id

RLS enforcement requires SET LOCAL to run inside an open transaction. This is
why tenant_session() always opens session.begin() explicitly before injecting
the variable. Never use autocommit mode on RLS-protected connections.

Usage::

    async with get_async_session_factory()() as session:
        async with tenant_session(session, tenant_id) as s:
            result = await s.execute(select(User).where(...))
"""

import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text


def get_async_engine():
    """Create an AsyncEngine from the DATABASE_URL environment variable.

    Expects DATABASE_URL to use the postgresql+asyncpg:// scheme for
    async operation. Raises KeyError if DATABASE_URL is not set.
    """
    database_url = os.environ["DATABASE_URL"]
    return create_async_engine(database_url, echo=False, pool_pre_ping=True)


def get_async_session_factory():
    """Return an async_sessionmaker bound to the engine from DATABASE_URL.

    Each call to the returned factory produces a new AsyncSession.
    """
    engine = get_async_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(session: AsyncSession, tenant_id: str):
    """Async context manager that injects the tenant RLS variable for a session.

    Opens an explicit transaction via session.begin(), executes
    SET LOCAL app.current_tenant_id = :tid, then yields the session.
    The transaction is committed on clean exit and rolled back on exception.

    SET LOCAL scopes the variable to the current transaction — it is cleared
    automatically when the transaction ends. Never use string interpolation
    to build the SQL; always use parameterised text() to avoid injection.

    Args:
        session:   An open AsyncSession (not yet in a transaction).
        tenant_id: The tenant UUID string to set as the RLS variable.

    Yields:
        The same session, now operating inside the tenant-scoped transaction.

    Example::

        async with tenant_session(session, "some-uuid") as s:
            result = await s.execute(select(User).where(User.email == email))
    """
    async with session.begin():
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": tenant_id},
        )
        yield session

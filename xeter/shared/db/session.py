"""
Shared FastAPI session dependency for PostgreSQL AsyncSession.

Provides a reusable get_session dependency that can be imported by any
service in the xeter package. Previously, each service defined its own
local get_session function (e.g. in presenter/routers/auth.py). This
shared version is the canonical location used by the Analyser and any
future services.

Created in Plan 02-02 to support the Analyser auth module import chain.
Plan 03 wires this dependency into the Analyser FastAPI app.

Usage::

    from xeter.shared.db.session import get_session
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    async def my_handler(session: AsyncSession = Depends(get_session)):
        ...
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from xeter.shared.db.postgres import get_async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an AsyncSession for the request lifetime.

    Creates a session from the shared session factory (DATABASE_URL env var).
    The session is closed when the request ends.

    Yields:
        An open AsyncSession bound to the PostgreSQL database.

    Raises:
        KeyError: If DATABASE_URL is not set in the environment.
    """
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        yield session

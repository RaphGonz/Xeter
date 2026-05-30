# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
API key authentication dependency for the Analyser service.

Provides:
  - verify_api_key_header: FastAPI dependency that validates the x-api-key
    header against bcrypt hashes stored in PostgreSQL. Returns the tenant_id
    string on success, raises HTTP 401 on failure.

Dependencies (provided by wiring layer in Plan 03):
  - xeter.shared.db.session.get_session: AsyncSession FastAPI dependency
    Interface: async def get_session() -> AsyncGenerator[AsyncSession, None]
    Must yield an AsyncSession connected to the PostgreSQL DATABASE_URL.

Note: get_session is expected at xeter.shared.db.session (Plan 03 scope).
If that module does not yet exist, this module will raise ImportError at
startup until Plan 03 creates it.
"""

import asyncio
import logging

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.shared.dal.api_keys import verify_api_key
from xeter.shared.models import ApiKey

# get_session will be provided in Plan 03 at xeter.shared.db.session.
# Expected interface:
#   async def get_session() -> AsyncGenerator[AsyncSession, None]:
#       """FastAPI dependency yielding an AsyncSession for the request lifetime."""
from xeter.shared.db.session import get_session  # noqa: E402  (Plan 03 creates this)

logger = logging.getLogger(__name__)


async def verify_api_key_header(
    x_api_key: str = Header(...),
    session: AsyncSession = Depends(get_session),
) -> str:
    """FastAPI dependency: validate x-api-key header against PostgreSQL bcrypt hashes.

    Iterates all api_keys rows. For each row, runs bcrypt.checkpw via
    asyncio.to_thread (bcrypt is CPU-bound, ~100ms — must not block the event loop).
    Returns the tenant_id string on the first match.

    Args:
        x_api_key: API key value from the x-api-key request header.
        session:   AsyncSession from the shared DB session dependency (Plan 03).

    Returns:
        tenant_id as a string UUID on successful authentication.

    Raises:
        HTTPException(401): If no key matches the supplied header value.
    """
    stmt = select(ApiKey)
    result = await session.execute(stmt)
    records = result.scalars().all()

    for record in records:
        match = await asyncio.to_thread(verify_api_key, x_api_key, record.key_hash)
        if match:
            logger.debug("auth: matched tenant %s", record.tenant_id)
            return str(record.tenant_id)

    raise HTTPException(status_code=401, detail="Invalid or missing API key")

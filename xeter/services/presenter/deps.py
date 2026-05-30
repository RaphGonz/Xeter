# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Presenter service — FastAPI dependencies.

Provides session token creation and verification for the Presenter dashboard.
All dashboard endpoints MUST use verify_session_token as a Depends() parameter
to enforce authentication.

Token format: JWT HS256, payload {"sub": tenant_id_str, "exp": unix_timestamp}
"""

import os
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import clickhouse_connect
from fastapi import Header, HTTPException
from jose import JWTError, jwt

from xeter.shared.db.clickhouse import get_clickhouse_client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ClickHouse dependency
# ---------------------------------------------------------------------------


def get_ch_client() -> Generator[clickhouse_connect.driver.Client, None, None]:
    """FastAPI dependency that creates a fresh ClickHouse client per request.

    clickhouse_connect clients are not safe for concurrent use within the same
    session. Creating one client per request avoids the
    "Attempt to execute concurrent queries within the same session" error when
    multiple requests arrive simultaneously.

    Yields:
        A ClickHouse client. The client is closed after the request completes.
    """
    client = get_clickhouse_client()
    try:
        yield client
    finally:
        client.close()


SECRET_KEY = os.environ["SECRET_KEY"]  # KeyError on startup if unset
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def create_session_token(tenant_id: str) -> str:
    """Encode a JWT session token for the given tenant.

    Args:
        tenant_id: String representation of the tenant UUID.

    Returns:
        Signed JWT string.
    """
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {"sub": tenant_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(tenant_id: str) -> str:
    """Encode a long-lived JWT refresh token for the given tenant.

    Args:
        tenant_id: String representation of the tenant UUID.

    Returns:
        Signed JWT string valid for 30 days.
    """
    expire = datetime.now(tz=timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": tenant_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def verify_session_token(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency that validates the Authorization: Bearer <token> header.

    Decodes and verifies the JWT. Returns the tenant_id string on success.

    Args:
        authorization: Value of the Authorization header (injected by FastAPI).

    Returns:
        tenant_id string extracted from the token's 'sub' claim.

    Raises:
        HTTPException 401: If token is missing, malformed, expired, or has no 'sub'.
    """
    _unauthorized = HTTPException(
        status_code=401,
        detail={"error": "unauthorized", "message": "Invalid or missing session token"},
    )

    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized

    token = authorization.removeprefix("Bearer ")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise _unauthorized

    tenant_id: str | None = payload.get("sub")
    if not tenant_id:
        raise _unauthorized

    return tenant_id

"""
Presenter service — FastAPI dependencies.

Provides session token creation and verification for the Presenter dashboard.
All dashboard endpoints MUST use verify_session_token as a Depends() parameter
to enforce authentication.

Token format: JWT HS256, payload {"sub": tenant_id_str, "exp": unix_timestamp}
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException
from jose import JWTError, jwt

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

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
    expire = datetime.now(tz=timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": tenant_id, "exp": expire}
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

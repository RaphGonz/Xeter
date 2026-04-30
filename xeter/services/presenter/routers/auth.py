"""
Presenter auth router — tenant registration and session login.

POST /register
  Creates a new tenant, user, and API key in a single transaction.
  Returns the plaintext API key exactly once — it cannot be retrieved again.

POST /login
  Verifies email + password against the users table.
  Returns a JWT session token on success.
  Returns 401 on any credential failure — no distinction between "user not found"
  and "wrong password" to prevent user enumeration.

Error responses:
  401 Unauthorized — invalid credentials (login only)
  409 Conflict     — email already registered (register only)
  422 Unprocessable Entity — validation failure (FastAPI default)
  500 Internal Server Error — unexpected DB error (details logged, never exposed)
"""

import asyncio
import logging

import bcrypt
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from jose import JWTError, jwt

from xeter.services.presenter.deps import (
    ALGORITHM,
    SECRET_KEY,
    create_refresh_token,
    create_session_token,
)
from xeter.shared.dal.api_keys import ApiKeyRepository, generate_api_key
from xeter.shared.dal.tenants import TenantRepository
from xeter.shared.dal.users import UserRepository
from xeter.shared.db.postgres import get_async_session_factory
from xeter.shared.models import User

logger = structlog.get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Session dependency
# ---------------------------------------------------------------------------


async def get_session() -> AsyncSession:
    """FastAPI dependency that yields an AsyncSession for the request lifetime."""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Registration payload for creating a new tenant account."""

    tenant_name: str
    email: str
    password: str

    @field_validator("tenant_name")
    @classmethod
    def tenant_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("tenant_name must not be empty")
        if len(v) > 100:
            raise ValueError("tenant_name must be at most 100 characters")
        return v

    @field_validator("email")
    @classmethod
    def email_looks_valid(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("email must be a valid email address")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class RegisterResponse(BaseModel):
    """
    Response returned after successful tenant registration.

    IMPORTANT: api_key is the plaintext API key, returned exactly once.
    It is never stored in the database — only its bcrypt hash is kept.
    After this response, the key cannot be retrieved again.
    """

    tenant_id: str
    api_key: str
    message: str


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/register", response_model=RegisterResponse, status_code=200)
async def register(
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegisterResponse:
    """Create a new tenant, user, and API key.

    The plaintext API key is returned in this response and cannot be retrieved
    again. Store it securely immediately.

    Steps:
      1. Check email uniqueness across all tenants (409 if duplicate)
      2. Create tenant row
      3. Hash password and create user row (inside tenant_session for RLS)
      4. Generate API key and store hash (inside same tenant_session)
      5. Return tenant_id + plaintext key
    """
    try:
        async with session.begin():
            # --- Step 1: Check email uniqueness across all tenants ---
            existing = await session.execute(
                select(User).where(User.email == body.email)
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(status_code=409, detail="Email already registered")

            # --- Step 2: Create tenant (bootstrap — no tenant_id yet, no RLS) ---
            tenant_repo = TenantRepository(session)
            tenant = await tenant_repo.create(name=body.tenant_name)
            await session.flush()

            tenant_id_str = str(tenant.tenant_id)

            # --- Step 3: Set RLS variable for remaining inserts ---
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                {"tid": tenant_id_str},
            )

            # --- Step 4: Hash password and create user ---
            password_hash = bcrypt.hashpw(
                body.password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")

            user_repo = UserRepository(session)
            await user_repo.create(
                tenant_id=tenant_id_str,
                email=body.email,
                password_hash=password_hash,
            )

            # --- Step 5: Generate API key and store hash ---
            plaintext, key_hash = generate_api_key()

            key_repo = ApiKeyRepository(session)
            await key_repo.create(tenant_id=tenant_id_str, key_hash=key_hash)

        # --- Step 6: Return response ---
        return RegisterResponse(
            tenant_id=tenant_id_str,
            api_key=plaintext,
            message="API key shown once. Store it securely — it cannot be retrieved.",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("register.failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Registration failed") from exc


# ---------------------------------------------------------------------------
# Login request / response models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Login payload for obtaining a session token."""

    email: str
    password: str


class LoginResponse(BaseModel):
    """Response returned after successful login."""

    session_token: str
    refresh_token: str


# ---------------------------------------------------------------------------
# Login route
# ---------------------------------------------------------------------------

_LOGIN_UNAUTHORIZED = HTTPException(
    status_code=401,
    detail={"error": "unauthorized", "message": "Invalid or missing session token"},
)


@router.post("/login", response_model=LoginResponse, status_code=200)
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    """Authenticate with email and password, return a JWT session token.

    Returns 401 for any credential failure — deliberately no distinction
    between "user not found" and "wrong password" (prevents user enumeration).
    """
    try:
        result = await session.execute(select(User).where(User.email == body.email))
        user: User | None = result.scalar_one_or_none()

        if user is None:
            raise _LOGIN_UNAUTHORIZED

        password_matches = await asyncio.to_thread(
            bcrypt.checkpw,
            body.password.encode("utf-8"),
            user.password_hash.encode("utf-8"),
        )

        if not password_matches:
            raise _LOGIN_UNAUTHORIZED

        token = create_session_token(str(user.tenant_id))
        refresh = create_refresh_token(str(user.tenant_id))
        return LoginResponse(session_token=token, refresh_token=refresh)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("login.failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Login failed") from exc


# ---------------------------------------------------------------------------
# Refresh token request / response models
# ---------------------------------------------------------------------------


class RefreshRequest(BaseModel):
    """Payload containing the long-lived refresh token."""

    refresh_token: str


class RefreshResponse(BaseModel):
    """Response containing a new short-lived session token."""

    session_token: str


_REFRESH_UNAUTHORIZED = HTTPException(
    status_code=401,
    detail={"error": "unauthorized", "message": "Invalid or expired refresh token"},
)


# ---------------------------------------------------------------------------
# Refresh route
# ---------------------------------------------------------------------------


@router.post("/auth/refresh", response_model=RefreshResponse, status_code=200)
async def refresh_token(body: RefreshRequest) -> RefreshResponse:
    """Issue a new access token from a valid refresh token.

    Stateless — no DB lookup. Just verifies the refresh JWT and issues a new
    short-lived session token. Refresh token revocation is deferred (AUTH-F01).
    """
    try:
        payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        tenant_id: str | None = payload.get("sub")
        if not tenant_id:
            raise _REFRESH_UNAUTHORIZED
    except JWTError:
        raise _REFRESH_UNAUTHORIZED
    new_token = create_session_token(tenant_id)
    return RefreshResponse(session_token=new_token)

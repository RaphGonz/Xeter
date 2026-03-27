"""
Presenter auth router — tenant registration.

POST /register
  Creates a new tenant, user, and API key in a single transaction.
  Returns the plaintext API key exactly once — it cannot be retrieved again.

Error responses:
  409 Conflict     — email already registered
  422 Unprocessable Entity — validation failure (FastAPI default)
  500 Internal Server Error — unexpected DB error (details logged, never exposed)
"""

import logging

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

import bcrypt

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

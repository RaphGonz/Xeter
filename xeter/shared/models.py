"""
SQLAlchemy 2.0 ORM models for Xeter's PostgreSQL schema.

Five tables:
  - tenants       : top-level tenant registry
  - users         : users belonging to a tenant
  - api_keys      : hashed API keys per tenant (never plaintext)
  - flags         : anomaly flags raised by analysers (flag_type is open String, never enum — FLAG-03)
  - diagnostics   : per-span diagnostic results from analysers

RLS is enabled on all five tables. The session variable ``app.current_tenant_id``
must be set at the start of each transaction by the data access layer.
"""

import uuid

from sqlalchemy import UUID, DateTime, Float, ForeignKey, JSON, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.tenant_id"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.tenant_id"),
        nullable=False,
    )
    # key_hash stores bcrypt/argon2 hash of the raw API key. Plaintext is NEVER stored.
    key_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Flag(Base):
    """
    Anomaly flag raised by an analyser for a specific span.

    flag_type is a plain VARCHAR string, never a PostgreSQL enum type.
    This allows future analysers to introduce new flag types (e.g. "tool_injection",
    "hallucination", "prompt_leak") without any schema migration — per FLAG-03.
    """

    __tablename__ = "flags"

    flag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    span_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    # Open string, NOT enum — per FLAG-03. Never change to Enum.
    flag_type: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Diagnostic(Base):
    """
    Per-span diagnostic result produced by an analyser.

    Stores the LLM backend used and the full structured result as JSON.
    """

    __tablename__ = "diagnostics"

    diagnostic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    span_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    llm_backend: Mapped[str | None] = mapped_column(String, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

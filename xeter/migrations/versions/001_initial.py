# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Initial schema: tenants, users, api_keys, flags, diagnostics + RLS

Revision ID: 001
Revises:
Create Date: 2026-03-27

Tables created:
  - tenants       (tenant_id PK, name, created_at)
  - users         (user_id PK, tenant_id FK, email unique, password_hash, created_at)
  - api_keys      (key_id PK, tenant_id FK, key_hash, created_at) — plaintext NEVER stored
  - flags         (flag_id PK, tenant_id, span_id, trace_id, flag_type String, score, detail JSON, created_at)
  - diagnostics   (diagnostic_id PK, tenant_id, span_id, trace_id, llm_backend, result JSON, created_at)

RLS enabled on all five tables with tenant_isolation policies using
the session variable app.current_tenant_id set per-transaction by the DAL.

IMPORTANT: flag_type is VARCHAR (String), never a PostgreSQL enum.
Future analysers add new flag types without schema changes — per FLAG-03.

IMPORTANT: The migration role must be a superuser or BYPASSRLS role to
run this migration. A regular tenant-scoped role will be blocked by the
RLS policies it creates (chicken-and-egg). Set DATABASE_URL accordingly.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. tenants
    # ------------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
    )

    # ------------------------------------------------------------------
    # 2. users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("email"),
    )

    # ------------------------------------------------------------------
    # 3. api_keys  — key_hash only; plaintext NEVER stored
    # ------------------------------------------------------------------
    op.create_table(
        "api_keys",
        sa.Column(
            "key_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("key_id"),
    )

    # ------------------------------------------------------------------
    # 4. flags — flag_type is String (VARCHAR), NEVER an enum — FLAG-03
    # ------------------------------------------------------------------
    op.create_table(
        "flags",
        sa.Column(
            "flag_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        # Open string type — future flag types require zero schema changes.
        sa.Column("flag_type", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("flag_id"),
    )

    # Indexes on flags for Phase 3 query performance.
    op.create_index("ix_flags_tenant_span", "flags", ["tenant_id", "span_id"])
    op.create_index("ix_flags_tenant_trace", "flags", ["tenant_id", "trace_id"])

    # ------------------------------------------------------------------
    # 5. diagnostics
    # ------------------------------------------------------------------
    op.create_table(
        "diagnostics",
        sa.Column(
            "diagnostic_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("llm_backend", sa.String(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("diagnostic_id"),
    )

    # ------------------------------------------------------------------
    # Enable Row Level Security on all five tables
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE flags ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE diagnostics ENABLE ROW LEVEL SECURITY;")

    # ------------------------------------------------------------------
    # Create tenant_isolation policies using session variable.
    #
    # current_setting('app.current_tenant_id', true) — the second argument
    # (true) means "return NULL instead of raising an error when the
    # variable is not set". This allows the BYPASSRLS migration user to
    # create and run migrations without setting the session variable.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE POLICY tenant_isolation ON tenants
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON users
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON api_keys
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON flags
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON diagnostics
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
        """
    )


def downgrade() -> None:
    # Drop in reverse dependency order (children before parents).
    # RLS policies are dropped automatically when the table is dropped.
    op.drop_index("ix_flags_tenant_trace", table_name="flags")
    op.drop_index("ix_flags_tenant_span", table_name="flags")
    op.drop_table("diagnostics")
    op.drop_table("flags")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("tenants")

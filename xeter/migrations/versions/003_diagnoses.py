# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Add diagnoses table with RLS and tenant isolation.

Adds a new `diagnoses` table for LLM root-cause diagnoses (Phase 11 v1.2).
This is DISTINCT from the existing `diagnostics` placeholder table (migration 001).
Do NOT modify `diagnostics`.

Revision ID: 003
Revises: 002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnoses",
        sa.Column(
            "diagnosis_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("affected_field", sa.String(), nullable=True),
        sa.Column("fix", sa.Text(), nullable=True),
        sa.Column("raw_llm_response", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(), nullable=False),
        sa.Column("provider_used", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("diagnosis_id"),
    )
    # Enable RLS — same pattern as flags and diagnostics tables in migration 001
    op.execute("ALTER TABLE diagnoses ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON diagnoses
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
        """
    )
    # Index for per-tenant span lookup (most frequent query pattern)
    op.create_index(
        "ix_diagnoses_tenant_span",
        "diagnoses",
        ["tenant_id", "span_id"],
    )
    # Index for time-ordered retrieval (frontend always wants the latest diagnosis)
    op.create_index(
        "ix_diagnoses_tenant_span_created",
        "diagnoses",
        ["tenant_id", "span_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_diagnoses_tenant_span_created", table_name="diagnoses")
    op.drop_index("ix_diagnoses_tenant_span", table_name="diagnoses")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON diagnoses;")
    op.drop_table("diagnoses")

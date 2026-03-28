"""Add span_scores table for embedding similarity calibration data

Revision ID: 002
Revises: 001
Create Date: 2026-03-28

Tables created:
  - span_scores  (score_id PK, span_id, tenant_id, analyzer_name, metric_name, score, created_at)

RLS intentionally omitted — worker connects as BYPASSRLS role.
Phase 4 will add per-tenant filtering at the read path layer.

The span_scores table stores every similarity score computed by every analyzer
for every span, regardless of whether it triggered a flag. This calibration
dataset is the foundation for threshold tuning in Phase 6.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # span_scores — calibration data for all analyzers
    #
    # RLS intentionally omitted — worker connects as BYPASSRLS role.
    # Phase 4 will add per-tenant filtering at the read path layer.
    # ------------------------------------------------------------------
    op.create_table(
        "span_scores",
        sa.Column(
            "score_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analyzer_name", sa.String(), nullable=False),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("score_id"),
    )

    op.create_index("ix_span_scores_span", "span_scores", ["span_id"])
    op.create_index(
        "ix_span_scores_tenant", "span_scores", ["tenant_id", "analyzer_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_span_scores_tenant", table_name="span_scores")
    op.drop_index("ix_span_scores_span", table_name="span_scores")
    op.drop_table("span_scores")

# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""span_scores: make span_id nullable for trace-level scores.

Changes (Phase 22 bug-fixes):
  INFRA-02: span_id column made nullable — trace-level scores produced by
            TraceAnalyzer have no single span; span-level scores continue
            to populate span_id as before.

Revision ID: 006
Revises: 005
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make span_id nullable — trace-level scores have no single span.
    # Span-level scores continue to populate span_id; trace-level scores use NULL.
    op.execute("ALTER TABLE span_scores ALTER COLUMN span_id DROP NOT NULL;")


def downgrade() -> None:
    # Revert span_id to NOT NULL. WARNING: any trace-level score rows
    # (span_id IS NULL) will block this.
    op.execute("ALTER TABLE span_scores ALTER COLUMN span_id SET NOT NULL;")

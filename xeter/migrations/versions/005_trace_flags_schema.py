"""Flags table schema extension for trace-level flags.

Changes (Phase 19 v1.4 TraceAnalyzer Scaffold):
  TANA-04: span_id column made nullable — trace-level flags (produced by
           TraceAnalyzer) have no single span; span-level flags continue
           to populate span_id as before.
           trace_id remains NOT NULL (was already NOT NULL since migration 001).

Revision ID: 005
Revises: 004
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Make span_id nullable — trace-level flags have no single span.
    # Span-level flags continue to populate span_id; trace-level flags use NULL.
    op.execute("ALTER TABLE flags ALTER COLUMN span_id DROP NOT NULL;")

    # Step 2: trace_id backfill note.
    # trace_id has been NOT NULL since migration 001. Every row written by
    # flag_writer.py includes trace_id (passed from ClickHouse span record).
    # No data migration required. Alembic migrations are PostgreSQL-only;
    # cross-database backfills must be done via application scripts, not here.
    # If any NULL trace_id rows exist (they should not), they would block a
    # future NOT NULL constraint — run:
    #   SELECT COUNT(*) FROM flags WHERE trace_id IS NULL;
    # before applying this migration if data integrity is uncertain.


def downgrade() -> None:
    # Revert span_id to NOT NULL. WARNING: any trace-level flag rows
    # (span_id IS NULL) will cause this to fail until they are removed.
    op.execute("ALTER TABLE flags ALTER COLUMN span_id SET NOT NULL;")

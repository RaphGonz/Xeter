# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""DB Foundation — span_scores RLS, FORCE RLS on all tables, diagnoses CHECK constraints.

Changes (Phase 14 v1.3 Security Hardening):
  DB-01: span_scores gains tenant_isolation RLS policy + FORCE ROW LEVEL SECURITY.
         score_writer.py updated separately to use SET LOCAL inside explicit transaction.
  DB-02: FORCE ROW LEVEL SECURITY retroactively applied to all tables that already
         have ENABLE ROW LEVEL SECURITY: tenants, users, api_keys, flags, diagnostics,
         diagnoses (from migration 001/003), plus span_scores (added here).
         Prevents table owner role from silently bypassing tenant isolation.
         NOTE: Superusers and BYPASSRLS roles still bypass regardless of FORCE —
         this protects table owner, not superuser.
  DB-03: CHECK constraints on diagnoses.verdict and diagnoses.severity using
         NOT VALID + VALIDATE two-step (SHARE UPDATE EXCLUSIVE lock, non-blocking).
         Vocabulary must match DiagnosisResult Literal in providers/base.py
         (updated in Phase 14 Plan 01).

Pre-flight requirement (DB-03):
  Run: python xeter/scripts/preflight_diagnoses_audit.py
  Must return exit 0 before applying this migration.

Revision ID: 004
Revises: 003
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ DB-01
    # span_scores: enable RLS + create tenant_isolation policy + force RLS
    # ------------------------------------------------------------------ DB-01
    op.execute("ALTER TABLE span_scores ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON span_scores
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
        """
    )
    op.execute("ALTER TABLE span_scores FORCE ROW LEVEL SECURITY;")

    # ------------------------------------------------------------------ DB-02
    # FORCE ROW LEVEL SECURITY on all existing RLS-enabled tables.
    # This prevents the table owner role from bypassing tenant_isolation.
    # ------------------------------------------------------------------ DB-02
    for _table in ("tenants", "users", "api_keys", "flags", "diagnostics", "diagnoses"):
        op.execute(f"ALTER TABLE {_table} FORCE ROW LEVEL SECURITY;")

    # ------------------------------------------------------------------ DB-03
    # diagnoses CHECK constraints via NOT VALID + VALIDATE two-step.
    # NOT VALID: acquires SHARE UPDATE EXCLUSIVE (non-blocking, no table scan).
    # VALIDATE CONSTRAINT: acquires SHARE UPDATE EXCLUSIVE (allows concurrent DML).
    # REQUIRES: pre-flight audit returns 0 violations before this upgrade runs.
    # ------------------------------------------------------------------ DB-03
    op.execute(
        """
        ALTER TABLE diagnoses
            ADD CONSTRAINT diagnoses_verdict_check
            CHECK (verdict IN ('model', 'architecture', 'prompt', 'unknown'))
            NOT VALID;
        """
    )
    op.execute(
        """
        ALTER TABLE diagnoses
            ADD CONSTRAINT diagnoses_severity_check
            CHECK (severity IN ('low', 'medium', 'high'))
            NOT VALID;
        """
    )
    # Validate constraints (scans existing rows — must be zero violations)
    op.execute("ALTER TABLE diagnoses VALIDATE CONSTRAINT diagnoses_verdict_check;")
    op.execute("ALTER TABLE diagnoses VALIDATE CONSTRAINT diagnoses_severity_check;")


def downgrade() -> None:
    # Remove constraints in reverse order
    op.execute(
        "ALTER TABLE diagnoses DROP CONSTRAINT IF EXISTS diagnoses_severity_check;"
    )
    op.execute(
        "ALTER TABLE diagnoses DROP CONSTRAINT IF EXISTS diagnoses_verdict_check;"
    )
    # Remove FORCE RLS from tables that had it added here
    for _table in ("tenants", "users", "api_keys", "flags", "diagnostics", "diagnoses"):
        op.execute(f"ALTER TABLE {_table} NO FORCE ROW LEVEL SECURITY;")
    # Remove span_scores RLS
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON span_scores;")
    op.execute("ALTER TABLE span_scores DISABLE ROW LEVEL SECURITY;")

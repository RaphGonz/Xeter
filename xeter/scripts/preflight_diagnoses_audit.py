#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Pre-flight audit for migration 004 CHECK constraints.

Run before: alembic upgrade head (when upgrading to revision 004).
Purpose: Confirm zero diagnoses rows violate the forthcoming
         diagnoses_verdict_check and diagnoses_severity_check constraints.

Exit 0: Safe to migrate.
Exit 1: Violations found — repair query printed to stdout.
"""
from __future__ import annotations

import os
import sys

import psycopg2

VALID_VERDICTS = ("model", "architecture", "prompt", "unknown")
VALID_SEVERITIES = ("low", "medium", "high")

_AUDIT_SQL = """
    SELECT COUNT(*) FROM diagnoses
    WHERE verdict NOT IN %s
       OR severity NOT IN %s;
"""


def _get_dsn() -> str:
    url = os.environ["DATABASE_URL"]
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres+asyncpg://", "postgresql://")
    )


def main() -> None:
    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(_AUDIT_SQL, (VALID_VERDICTS, VALID_SEVERITIES))
        count = cur.fetchone()[0]
    conn.close()

    if count == 0:
        print("PRE-FLIGHT OK: 0 violating diagnoses rows. Safe to run migration 004.")
        sys.exit(0)
    else:
        print(f"VIOLATION COUNT: {count} rows would fail migration 004 CHECK constraints.")
        print()
        print("Run this repair query before applying migration 004:")
        print("  UPDATE diagnoses SET verdict = 'unknown'")
        print("    WHERE verdict NOT IN ('model', 'architecture', 'prompt', 'unknown');")
        print("  UPDATE diagnoses SET severity = 'high'")
        print("    WHERE severity NOT IN ('low', 'medium', 'high');")
        print()
        print("Then re-run this script to confirm 0 violations.")
        sys.exit(1)


if __name__ == "__main__":
    main()

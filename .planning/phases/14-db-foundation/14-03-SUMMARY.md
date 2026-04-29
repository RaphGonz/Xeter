---
phase: 14-db-foundation
plan: "03"
subsystem: database
tags: [postgres, rls, alembic, psycopg2, migrations, security]

# Dependency graph
requires:
  - phase: 14-01
    provides: Provider vocabulary aligned to DB-approved enums — ensures pre-flight audit exits 0 before VALIDATE CONSTRAINT runs
provides:
  - Migration 004: span_scores RLS + tenant_isolation policy + FORCE ROW LEVEL SECURITY
  - FORCE ROW LEVEL SECURITY on all 7 PostgreSQL tables (tenants, users, api_keys, flags, diagnostics, diagnoses, span_scores)
  - diagnoses CHECK constraints (verdict + severity) via NOT VALID + VALIDATE two-step
  - score_writer.py uses SET LOCAL app.current_tenant_id inside explicit psycopg2 transaction
  - 5 unit tests proving SET LOCAL, commit, rollback, and row-shape behaviour
affects: [phase-15, phase-16, score_writer, diagnosticer, db-security]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "NOT VALID + VALIDATE two-step for non-blocking CHECK constraint addition"
    - "SET LOCAL app.current_tenant_id in explicit autocommit=False transaction (flag_writer.py pattern)"

key-files:
  created:
    - xeter/migrations/versions/004_db_foundation.py
    - xeter/tests/worker/test_score_writer.py
  modified:
    - xeter/services/worker/score_writer.py

key-decisions:
  - "Pre-flight DATABASE_URL not available during execution — migration written correctly; pre-flight must be run manually before alembic upgrade head in production"
  - "FORCE RLS applies to 7 tables: tenants, users, api_keys, flags, diagnostics, diagnoses (all pre-existing RLS tables) + span_scores (new)"
  - "score_writer uses autocommit=False + explicit commit/rollback — SET LOCAL must be inside same transaction as INSERT"

patterns-established:
  - "score_writer SET LOCAL pattern: matches flag_writer.py — autocommit=False, SET LOCAL first, executemany, explicit commit/rollback/close"
  - "Migration NOT VALID + VALIDATE: ADD CONSTRAINT NOT VALID (no table scan), then VALIDATE CONSTRAINT (SHARE UPDATE EXCLUSIVE lock, allows concurrent DML)"

requirements-completed:
  - DB-01
  - DB-02
  - DB-03

# Metrics
duration: 15min
completed: 2026-04-29
---

# Phase 14-03: Migration 004 + score_writer SET LOCAL Summary

**Migration 004 adds span_scores tenant isolation RLS, FORCE ROW LEVEL SECURITY on all 7 tables, and non-blocking diagnoses CHECK constraints; score_writer updated to satisfy RLS with SET LOCAL in explicit transaction**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-04-29
- **Tasks:** 2/2
- **Files modified:** 3 (1 created migration, 1 updated service, 1 new test file)

## Accomplishments

- Migration 004 written covering DB-01 (span_scores RLS), DB-02 (FORCE RLS on all 7 tables), DB-03 (diagnoses CHECK constraints via NOT VALID + VALIDATE)
- score_writer.py updated to use `SET LOCAL app.current_tenant_id` as first execute call inside `autocommit=False` transaction — matching flag_writer.py pattern
- 5 unit tests: empty short-circuit, SET LOCAL ordering, commit on success, rollback+re-raise on error, row tuple shape
- Full worker suite: 48 tests pass (no regressions)

## Task Commits

1. **Task 1: Migration 004** — `cdb19f0` (feat)
2. **Task 2: score_writer SET LOCAL + unit tests** — `328a914` (feat)

## Files Created/Modified

- `xeter/migrations/versions/004_db_foundation.py` — Alembic migration: span_scores ENABLE/FORCE RLS + tenant_isolation policy, FORCE RLS on 6 existing tables, diagnoses_verdict_check + diagnoses_severity_check NOT VALID + VALIDATE
- `xeter/services/worker/score_writer.py` — Replaced `with psycopg2.connect()` context manager with explicit `autocommit=False` transaction; added `SET LOCAL` before `executemany`; updated docstring
- `xeter/tests/worker/test_score_writer.py` — 5 unit tests with mocked psycopg2 connections

## Decisions Made

- Pre-flight DATABASE_URL not available during execution. Migration is written correctly; the `preflight_diagnoses_audit.py` script (created in plan 01) must be run manually before `alembic upgrade head` in production.
- FORCE RLS table list: 7 tables (tenants, users, api_keys, flags, diagnostics, diagnoses, span_scores). "spans" is a ClickHouse table with no PostgreSQL presence — excluded correctly.

## Deviations from Plan

None — plan executed exactly as written. Pre-flight skip was pre-specified in the plan's Step 0 instructions.

## Issues Encountered

None.

## User Setup Required

Before running `alembic upgrade head` in production:
```bash
python xeter/scripts/preflight_diagnoses_audit.py
```
Must exit 0. If exit 1, run the printed repair SQL then re-run the script.

## Next Phase Readiness

- Phase 14 DB Foundation complete: all 3 plans done
- span_scores has RLS + FORCE RLS; score_writer satisfies the policy via SET LOCAL
- All 7 PostgreSQL tables now have FORCE ROW LEVEL SECURITY — table owner cannot bypass tenant isolation
- diagnoses.verdict and diagnoses.severity have CHECK constraints enforcing DB-approved vocabulary
- Phase 15 (next) can proceed

---
*Phase: 14-db-foundation*
*Completed: 2026-04-29*

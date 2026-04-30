---
phase: 17-gdpr-data-deletion
plan: 01
subsystem: infra
tags: [gdpr, deletion, clickhouse, postgres, s3, redis, boto3, psycopg2]

# Dependency graph
requires:
  - phase: 16-auth-hardening
    provides: v1.3 security hardening baseline — auth, secrets, CORS complete before data erasure tooling
  - phase: 15-secrets-hardening
    provides: env var patterns (DATABASE_URL, S3_ENDPOINT_URL, REDIS_URL) used by delete_tenant.py
provides:
  - GDPR Art. 17 operator deletion script (xeter/scripts/delete_tenant.py) with dry-run and --confirm gate
  - Operator runbook (docs/GDPR_DELETION_RUNBOOK.md) covering full erasure procedure
  - Idempotent multi-store deletion: ClickHouse ALTER TABLE mutation, PostgreSQL FK-ordered DELETEs, S3 paginated batch, Redis documented procedure
affects: [future-compliance, operator-runbooks]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GDPR Art. 17 dry-run-first pattern: default is read-only summary; --confirm required to execute"
    - "PostgreSQL FK deletion order: span_scores → diagnostics → diagnoses → flags → api_keys → users → tenants"
    - "ClickHouse async mutation: ALTER TABLE ... DELETE submitted and returns immediately; verify after 30s"
    - "S3 paginated batch delete: list_objects_v2 paginator + delete_objects up to 1000 keys per call"

key-files:
  created:
    - xeter/scripts/delete_tenant.py
    - docs/GDPR_DELETION_RUNBOOK.md
  modified: []

key-decisions:
  - "Redis flush is documented procedure only — no scripted LREM automation (global analysis_queue; flushing specific tenant spans requires manual span_id identification)"
  - "ClickHouse uses ALTER TABLE spans DELETE mutation (async) not standard SQL DELETE — script prints 30s wait notice"
  - "S3 uses paginated list_objects_v2 + batch delete_objects (not per-object deletion) for efficiency and rate-limit safety"
  - "Script is idempotent by design: DELETE WHERE on non-existent rows is a no-op; no tenant-existence pre-check"
  - "UUID validation via uuid.UUID() before any DB connection — exits 1 with clear error on invalid input"
  - "PostgreSQL deletions use single connection with autocommit=False and single commit() after all 7 DELETEs"

patterns-established:
  - "Operator script pattern: argparse + _get_dsn() psycopg2 + dry-run-first with --confirm gate (matches preflight_diagnoses_audit.py style)"
  - "Multi-store deletion order: ClickHouse → PostgreSQL (FK order) → S3 → Redis documented"

requirements-completed: [GDPR-01]

# Metrics
duration: ~45min
completed: 2026-04-30
---

# Phase 17 Plan 01: GDPR Data Deletion Summary

**GDPR Art. 17 delete_tenant.py with dry-run-first gate, FK-ordered PostgreSQL deletion across 7 tables, ClickHouse ALTER TABLE mutation, paginated S3 batch delete, and operator runbook**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-04-30
- **Completed:** 2026-04-30
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint, approved)
- **Files modified:** 2

## Accomplishments

- Implemented xeter/scripts/delete_tenant.py (302 lines): UUID validation, dry-run summary across all four data stores, --confirm-gated deletion in correct FK order, idempotent by design
- Created docs/GDPR_DELETION_RUNBOOK.md (216 lines): step-by-step procedure with exact expected output, env var table, Redis manual flush procedure, ClickHouse async mutation explanation
- Human verification passed: --help, invalid UUID exit 1, dry-run all-zero counts, idempotent second run all confirmed

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement delete_tenant.py** - `d7867a0` (feat)
2. **Task 2: Create GDPR Deletion Runbook** - `4a5f30c` (docs)
3. **Task 3: Human Verify Deletion Tooling** - checkpoint approved (no code commit — verification only)

## Files Created/Modified

- `xeter/scripts/delete_tenant.py` - GDPR Art. 17 deletion script: argparse CLI, UUID validation, dry-run summary (_count_all), --confirm deletion (_delete_all) across ClickHouse/PostgreSQL/S3 with Redis procedure inline
- `docs/GDPR_DELETION_RUNBOOK.md` - Operator runbook: overview, when to use, step-by-step commands with expected output, Redis flush procedure, ClickHouse async note, env var table, related files

## Decisions Made

- Redis flush is documented only — the analysis_queue is global; automated per-tenant LREM requires identifying span_ids manually. FLUSHDB explicitly prohibited in runbook.
- ClickHouse ALTER TABLE DELETE is asynchronous (MergeTree background mutation). Script prints the 30-second wait notice after submitting; dry-run re-run is verification method.
- PostgreSQL uses a single connection with autocommit=False and one commit() after all 7 DELETEs — ensures atomicity across tables.
- S3 paginator + batch delete_objects (up to 1000 keys/call) chosen over per-object deletion for performance and MinIO compatibility.
- Script never pre-checks tenant existence — DELETE WHERE on absent rows is a no-op (idempotency by construction).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. All env vars (DATABASE_URL, CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD, S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET, REDIS_URL, REDIS_PASSWORD) were already documented in docs/GDPR_DELETION_RUNBOOK.md and match the existing deploy/docker-compose.yml configuration.

## Next Phase Readiness

- GDPR-01 requirement satisfied: operator can execute right-to-erasure in one command with dry-run preview
- v1.3 Security Hardening milestone complete — all requirements (AUTH-01 through AUTH-04, DB-04, OPS-04, GDPR-01) done
- No blockers for future phases

---
*Phase: 17-gdpr-data-deletion*
*Completed: 2026-04-30*

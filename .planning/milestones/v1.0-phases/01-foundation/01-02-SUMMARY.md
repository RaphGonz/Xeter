---
phase: 01-foundation
plan: 02
subsystem: database
tags: [postgresql, clickhouse, sqlalchemy, alembic, rls, multi-tenancy, orm]

# Dependency graph
requires: []
provides:
  - SQLAlchemy 2.0 ORM models for all five PostgreSQL tables (tenants, users, api_keys, flags, diagnostics)
  - Alembic async migration 001_initial.py with full schema + RLS policies
  - ClickHouse spans table DDL with immutable MergeTree ORDER BY
  - ClickHouse client factory and schema initializer
affects: [02-ingestion, 03-analysis, 04-read-path, 05-frontend, 06-hardening]

# Tech tracking
tech-stack:
  added: [sqlalchemy==2.0.48, clickhouse-connect==0.15.0, alembic]
  patterns:
    - SQLAlchemy 2.0 declarative models with Mapped[] typed columns
    - Alembic async env.py reading DATABASE_URL from environment
    - ClickHouse schema initialized via CREATE TABLE IF NOT EXISTS on startup
    - RLS tenant isolation via session variable app.current_tenant_id

key-files:
  created:
    - xeter/shared/models.py
    - xeter/migrations/alembic.ini
    - xeter/migrations/env.py
    - xeter/migrations/script.py.mako
    - xeter/migrations/versions/001_initial.py
    - xeter/shared/db/clickhouse.py
  modified: []

key-decisions:
  - "flag_type is String (VARCHAR) not PostgreSQL enum — allows new flag types without schema migrations (FLAG-03)"
  - "RLS uses current_setting('app.current_tenant_id', true) with true parameter to avoid errors when variable unset during migrations"
  - "Migration role must be superuser or BYPASSRLS — documented in env.py comment"
  - "ClickHouse ORDER BY (tenant_id, trace_id, time_begin) is locked — one-way door set before any data flows"
  - "tool_arguments stored as Nullable(String) JSON; S3 overflow path deferred to Phase 2"
  - "api_keys stores key_hash only — plaintext API keys are never persisted"

patterns-established:
  - "All five PostgreSQL tables have RLS enabled with tenant_isolation policy using session variable"
  - "Alembic env.py always reads DATABASE_URL from os.environ, never hardcoded"
  - "ClickHouse schema managed via idempotent create_spans_table() called at startup"
  - "Flags use open-string flag_type to allow analyser extension without schema changes"

requirements-completed: [STOR-01, AUTH-01, AUTH-04]

# Metrics
duration: 14min
completed: 2026-03-27
---

# Phase 1 Plan 02: PostgreSQL Schema + ClickHouse Spans Table Summary

**Five-table PostgreSQL schema with RLS tenant isolation and immutable ClickHouse MergeTree spans table using ORDER BY (tenant_id, trace_id, time_begin)**

## Performance

- **Duration:** 14 min
- **Started:** 2026-03-27T12:11:37Z
- **Completed:** 2026-03-27T12:24:38Z
- **Tasks:** 2
- **Files modified:** 10 created, 0 modified

## Accomplishments

- Five SQLAlchemy 2.0 ORM models (Tenant, User, ApiKey, Flag, Diagnostic) with typed Mapped[] columns
- Alembic async migration 001_initial.py: all five tables, RLS enabled on each, five tenant_isolation policies
- ClickHouse spans table DDL with 19 columns and locked MergeTree ORDER BY (tenant_id, trace_id, time_begin)
- ClickHouse client factory, idempotent schema initializer, and EXPLAIN index verification helper

## Task Commits

Each task was committed atomically:

1. **Task 1: PostgreSQL schema — SQLAlchemy models and Alembic migration** - `cea2904` (feat)
2. **Task 2: ClickHouse client setup and spans table DDL** - `2893c23` (feat)

**Plan metadata:** (docs commit — see final commit below)

## Files Created/Modified

- `xeter/shared/models.py` — Five SQLAlchemy 2.0 ORM models with Mapped[] typed columns
- `xeter/migrations/alembic.ini` — Alembic config with empty sqlalchemy.url (read from env at runtime)
- `xeter/migrations/env.py` — Async env.py reading DATABASE_URL from environment; BYPASSRLS requirement documented
- `xeter/migrations/script.py.mako` — Alembic revision template
- `xeter/migrations/versions/001_initial.py` — Initial migration: 5 tables, 5 RLS enables, 5 tenant_isolation policies, 2 indexes
- `xeter/shared/db/clickhouse.py` — Client factory, SPANS_TABLE_DDL constant, create_spans_table(), verify_index_usage()
- `xeter/__init__.py`, `xeter/shared/__init__.py`, `xeter/shared/db/__init__.py`, `xeter/migrations/__init__.py`, `xeter/migrations/versions/__init__.py` — Python package init files

## Decisions Made

- **flag_type as String:** The flags.flag_type column is VARCHAR, never a PostgreSQL enum. This allows future analysers to introduce new flag types (e.g. "tool_injection", "hallucination") without any schema migration — per FLAG-03.
- **RLS current_setting with true parameter:** Using `current_setting('app.current_tenant_id', true)` prevents errors when the session variable is not set. The migration runner (superuser/BYPASSRLS role) does not set this variable, so the policy must not raise on absence.
- **ClickHouse ORDER BY locked:** `(tenant_id, trace_id, time_begin)` is set here as a one-way door. Confirmed in plan that changing it after data is written requires a full table rebuild.
- **No hardcoded credentials:** DATABASE_URL is always read from environment in env.py; ClickHouse connection also reads from environment variables.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing sqlalchemy package**
- **Found during:** Task 1 (model import verification)
- **Issue:** SQLAlchemy not installed; `from xeter.shared.models import ...` raised ModuleNotFoundError
- **Fix:** Ran `pip install sqlalchemy[asyncio]` — installed sqlalchemy 2.0.48
- **Verification:** Models import without errors
- **Committed in:** cea2904 (part of Task 1 commit)

**2. [Rule 3 - Blocking] Installed missing clickhouse-connect package**
- **Found during:** Task 2 (clickhouse module import verification)
- **Issue:** clickhouse-connect not installed; module import raised ModuleNotFoundError
- **Fix:** Ran `pip install clickhouse-connect` — installed clickhouse-connect 0.15.0
- **Verification:** Module imports, SPANS_TABLE_DDL assertion passes
- **Committed in:** 2893c23 (part of Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking — missing dependencies)
**Impact on plan:** Both dependency installs are required for the module imports to work. No scope creep.

## Issues Encountered

- Python package `xeter` needed `__init__.py` files at each level (`xeter/`, `xeter/shared/`, `xeter/shared/db/`, `xeter/migrations/`, `xeter/migrations/versions/`) to be importable as a namespace package. Created all five init files as part of Task 1.

## User Setup Required

None — no external service configuration required for the schema files themselves. Running migrations against a live PostgreSQL instance requires `DATABASE_URL` to be set and the database role to have superuser or BYPASSRLS privileges.

## Next Phase Readiness

- All five PostgreSQL tables and RLS policies are defined and ready for migration against a live DB
- ClickHouse spans table DDL is locked — schema is correct before any data flows (one-way door set)
- SQLAlchemy models are importable and available for use by all subsequent phases
- Phase 1 Plan 03 (Docker Compose + environment setup) can now reference these schemas for service wiring

---
*Phase: 01-foundation*
*Completed: 2026-03-27*

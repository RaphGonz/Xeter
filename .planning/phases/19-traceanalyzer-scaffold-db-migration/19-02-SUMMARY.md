---
phase: 19-traceanalyzer-scaffold-db-migration
plan: "02"
subsystem: database
tags: [alembic, postgresql, sqlalchemy, flags, migration, nullable]

# Dependency graph
requires:
  - phase: 19-01
    provides: BaseTraceAnalyzer stub and phase 19 scaffold structure
provides:
  - Migration 005 making flags.span_id nullable for trace-level flags
  - Flag ORM model with span_id as Mapped[str | None]
  - write_flags() accepting Optional span_id (None -> SQL NULL via psycopg2)
affects: [19-03, worker, flag_writer, TraceAnalyzer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Nullable foreign-key-style column via ALTER COLUMN DROP NOT NULL in Alembic op.execute()"
    - "Defensive migration comment pattern: explain why backfill is a no-op rather than silently omitting"
    - "psycopg2 None -> SQL NULL passthrough — no SQL change needed in INSERT for nullable columns"

key-files:
  created:
    - xeter/migrations/versions/005_trace_flags_schema.py
  modified:
    - xeter/shared/models.py
    - xeter/services/worker/flag_writer.py

key-decisions:
  - "trace_id backfill is a no-op: column has been NOT NULL since migration 001; no ClickHouse cross-database backfill needed in a PG migration"
  - "span_id: str | None in flag_writer — psycopg2 maps None to SQL NULL automatically; _INSERT_SQL string unchanged"
  - "Flag.span_id nullable=True in ORM model mirrors DB schema change in migration 005"

patterns-established:
  - "Nullable span_id pattern: trace-level flags (TraceAnalyzer) set span_id=None; span-level flags populate as before"

requirements-completed: [TANA-04]

# Metrics
duration: 8min
completed: 2026-05-14
---

# Phase 19 Plan 02: Trace Flags Schema Migration Summary

**Alembic migration 005 makes flags.span_id nullable (DROP NOT NULL) and wires ORM + flag_writer for trace-level flag writes with span_id=None**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-14T14:00:38Z
- **Completed:** 2026-05-14T14:08:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Migration 005 created: `ALTER TABLE flags ALTER COLUMN span_id DROP NOT NULL` with documented no-op backfill note and reversible downgrade()
- Flag ORM model updated: `span_id: Mapped[str | None]` with `nullable=True` and updated class docstring
- write_flags() signature updated: `span_id: str | None` — psycopg2 maps Python None to SQL NULL without SQL changes
- 11/11 worker tests pass confirming no regressions in existing span-level write path

## Task Commits

Each task was committed atomically:

1. **Task 1: Write migration 005 — nullable span_id, non-nullable trace_id, backfill** - `d0d3f59` (feat)
2. **Task 2: Update Flag ORM model and flag_writer.py for nullable span_id** - `55940d9` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified
- `xeter/migrations/versions/005_trace_flags_schema.py` - Alembic migration 005: DROP NOT NULL on span_id, downgrade() reverts to SET NOT NULL
- `xeter/shared/models.py` - Flag.span_id changed to Mapped[str | None] with nullable=True; docstring updated
- `xeter/services/worker/flag_writer.py` - write_flags() span_id param changed to str | None; docstring updated

## Decisions Made
- trace_id backfill is a no-op: the column has been NOT NULL since migration 001 and every flag_writer.py call passes trace_id. No ClickHouse cross-database query belongs in a PG-only Alembic migration; a comment explaining the reasoning was included instead.
- The `_INSERT_SQL` string and psycopg2 tuple construction are unchanged — psycopg2 automatically maps Python `None` to SQL `NULL` for `%s` placeholders.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Migration filename `005_trace_flags_schema.py` starts with a digit, making `import xeter.migrations.versions.005_trace_flags_schema` a SyntaxError. Used `importlib.util.spec_from_file_location` for verification instead. This is consistent with how Alembic discovers migrations (by file path, not Python import path).

## User Setup Required
None - no external service configuration required. Migration 005 will be applied on next `alembic upgrade head` run against the target database.

## Next Phase Readiness
- flags.span_id is now nullable in schema, ORM, and writer — ready for 19-03 to wire TraceAnalyzer.write() calls with span_id=None
- Existing span-level flag writes (span_id=str) continue to work unchanged

---
*Phase: 19-traceanalyzer-scaffold-db-migration*
*Completed: 2026-05-14*

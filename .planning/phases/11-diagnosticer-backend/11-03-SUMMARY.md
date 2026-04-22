---
phase: 11-diagnosticer-backend
plan: "03"
subsystem: diagnosticer
tags: [dal, context-assembly, clickhouse, postgres, s3, rls]

# Dependency graph
requires:
  - phase: 11-01
    provides: "Diagnosis SQLAlchemy ORM model in shared/models.py"
  - phase: 11-02
    provides: "LLM provider factory (consumed by Plan 04 endpoint)"
provides:
  - "DiagnosisRepository with create() and get_latest_for_span() in xeter/shared/dal/diagnoses.py"
  - "assemble_context() in xeter/services/diagnosticer/context_assembly.py"
affects: [11-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DAL repository pattern: require_tenant() first line, flush+refresh after add (mirrors api_keys.py)"
    - "asyncio.to_thread wrapping sync clickhouse_connect client for async context"
    - "asyncio.wait_for (5s timeout) around parallel S3 fetches via asyncio.gather"
    - "S3 {'value': '...'} envelope unwrap via json.loads().get('value')"
    - "tenant_session() context manager for RLS-protected PostgreSQL flag queries"

key-files:
  created:
    - xeter/shared/dal/diagnoses.py
    - xeter/services/diagnosticer/context_assembly.py
  modified: []

key-decisions:
  - "assemble_context() returns (context_string, trace_id) tuple — trace_id extracted from ClickHouse span row needed for diagnosis row storage in Plan 04"
  - "S3 timeout substitutes '[S3 fetch timed out]' rather than raising — LLM can still diagnose from tool_name, tool_arguments, and flag data"
  - "Flags and S3 payloads fetched in parallel via asyncio.gather — reduces latency for context assembly"

# Metrics
duration: 8min
completed: 2026-04-22
---

# Phase 11 Plan 03: DAL and Context Assembly Summary

**DiagnosisRepository DAL (create/get_latest_for_span with RLS guard) and context_assembly module pulling ClickHouse span + PostgreSQL flags + S3 payloads into a single formatted LLM prompt string**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-22T18:00:10Z
- **Completed:** 2026-04-22T18:08:14Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `xeter/shared/dal/diagnoses.py` with `DiagnosisRepository` — `create()` inserts a diagnosis row with flush+refresh pattern (mirrors `api_keys.py`); `get_latest_for_span()` returns the most recent diagnosis ordered by `created_at DESC`; both methods call `require_tenant()` as first line
- Created `xeter/services/diagnosticer/context_assembly.py` with `assemble_context()` — fetches span from ClickHouse via `asyncio.to_thread` (sync client), fetches all flag rows from PostgreSQL via `tenant_session()` RLS context manager, fetches S3 prompt/response payloads with 5s timeout via `asyncio.wait_for`, formats everything into a single LLM-ready context string

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement DiagnosisRepository DAL** - `a09042f` (feat)
2. **Task 2: Implement context_assembly module** - `429ee69` (feat)

## Files Created/Modified

- `xeter/shared/dal/diagnoses.py` - New: DiagnosisRepository with create() and get_latest_for_span()
- `xeter/services/diagnosticer/context_assembly.py` - New: assemble_context() with ClickHouse + PostgreSQL + S3 data sources

## Decisions Made

- `assemble_context()` returns `(context_string, trace_id)` tuple — `trace_id` is extracted from the ClickHouse span row and passed back to the caller (Plan 04 endpoint) for storing the diagnosis row without a second ClickHouse query
- S3 timeout uses `asyncio.wait_for` with 5s covering both prompt and response fetches in parallel — on timeout, both fields become `'[S3 fetch timed out]'` so the LLM receives partial context rather than an error
- Flags and S3 fetches run via `asyncio.gather` in parallel — minimizes latency in the hot path of the diagnose endpoint

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- `xeter/shared/dal/diagnoses.py` — FOUND
- `xeter/services/diagnosticer/context_assembly.py` — FOUND
- Commit `a09042f` — FOUND
- Commit `429ee69` — FOUND

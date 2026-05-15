---
phase: 20-trace-api
plan: "01"
subsystem: api
tags: [fastapi, clickhouse, postgresql, sqlalchemy, pydantic, traces]

# Dependency graph
requires:
  - phase: 19-trace-analyzer-scaffold
    provides: "TraceAnalyzer scaffold; flags.span_id nullable; flags.trace_id always set"
  - phase: 04-read-path
    provides: "Presenter service, spans router patterns, deps.py, get_ch_client, verify_session_token"
provides:
  - "GET /traces — paginated trace list with span_count, flag_count, start_time, duration"
  - "GET /traces/{trace_id} — full trace detail: TraceObject + flat SpanInTrace list"
  - "Two-phase 404: checks CH then PG; no-spans-yet returns 200 with spans=[]"
  - "Trace-level flags (span_id IS NULL) surfaced on trace.flags"
  - "Cross-tenant stealth 404 via tenant_id filter on both CH and PG queries"
affects: [frontend-trace-view, v1.5-trace-checks, trace-api-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Concurrent CH queries via asyncio.gather (list + count in parallel)"
    - "Sequential PG queries on shared AsyncSession (concurrent execute raises IllegalStateChangeError)"
    - "Two-phase existence check: CH zero rows → PG fallback before 404"
    - "Belt-and-suspenders tenant isolation: explicit WHERE tenant_id on every CH and PG query"
    - "Trace-level flags identified by span_id IS NULL; span-level flags indexed by span_id"

key-files:
  created:
    - xeter/services/presenter/routers/traces.py
  modified:
    - xeter/services/presenter/main.py

key-decisions:
  - "Two-phase 404 for GET /traces/{trace_id}: zero CH rows triggers PG fallback; only 404 when both return nothing — preserves no-spans-yet 200 case (locked user decision from plan)"
  - "Cross-tenant stealth 404: WHERE tenant_id in both CH and PG queries makes other tenant data invisible; no explicit 403 needed"
  - "Trace-level flags (span_id IS NULL) go on trace.flags not on any span; span-level flags go inline on SpanInTrace"
  - "input_tokens/output_tokens set to None — not in current ClickHouse schema, reserved for future"
  - "PG queries in GET /traces/{trace_id} run sequentially on shared AsyncSession — concurrent execute causes IllegalStateChangeError"

patterns-established:
  - "Trace router follows spans.py structure: docstring, imports, router = APIRouter(), models, handlers"
  - "asyncio.gather used for concurrent CH queries only; PG queries always sequential on same session"

requirements-completed: [TRACE-01, TRACE-02]

# Metrics
duration: 13min
completed: "2026-05-15"
---

# Phase 20 Plan 01: Trace API Summary

**GET /traces and GET /traces/{trace_id} FastAPI endpoints with two-phase 404, no-spans-yet 200, and per-tenant isolation on both ClickHouse and PostgreSQL**

## Performance

- **Duration:** 13 min
- **Started:** 2026-05-15T09:00:53Z
- **Completed:** 2026-05-15T09:14:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Implemented `routers/traces.py` with full response model hierarchy (TraceListResponse, TraceDetailResponse, TraceObject, SpanInTrace, TraceFlagItem, ScoreItem, TraceListItem)
- GET /traces: concurrent ClickHouse aggregation + total count via asyncio.gather, PG flag counts via raw text() query, offset/limit pagination (default 50, max 100)
- GET /traces/{trace_id}: spans from ClickHouse sorted ASC, two-phase existence check (CH then PG), no-spans-yet returns 200 with spans=[], trace-level flags separated from span-level flags
- Registered traces router in main.py alongside existing auth/spans/diagnose routers

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement GET /traces and GET /traces/{trace_id} in routers/traces.py** - `d3dd9ea` (feat)
2. **Task 2: Register traces router in main.py** - `d39b8da` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `xeter/services/presenter/routers/traces.py` - New traces router with both endpoint handlers and all response models
- `xeter/services/presenter/main.py` - Added traces import and include_router call; updated docstring

## Decisions Made
- Two-phase 404 implemented as specified: zero CH rows triggers secondary PG flag existence check before raising 404 — preserves the no-spans-yet case where flags exist before spans arrive
- Cross-tenant stealth via WHERE tenant_id filters on both CH and PG; requesting tenant's filter causes other tenant data to disappear silently, no 403 needed
- PG queries in the detail handler run sequentially (flags then scores) — concurrent execute() on a single AsyncSession causes IllegalStateChangeError per spans.py precedent
- Concurrent ClickHouse queries (list + count) run via asyncio.gather since each uses a separate asyncio.to_thread call

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Verification commands required `SECRET_KEY` and `INTERNAL_API_KEY` env vars — these are `os.environ["KEY"]` module-level fetches in deps.py and diagnosis_service.py (intentional fail-fast design). Ran verification with stub values; no code change needed.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GET /traces and GET /traces/{trace_id} are live on the Presenter app; both routes verified via route registration check
- TRACE-01 and TRACE-02 satisfied
- Ready for integration tests or frontend trace-view wiring
- No blockers

---
*Phase: 20-trace-api*
*Completed: 2026-05-15*

---
phase: 20-trace-api
plan: "02"
subsystem: testing
tags: [fastapi, pytest, unittest.mock, clickhouse, postgresql, traces, tenant-isolation]

# Dependency graph
requires:
  - phase: 20-trace-api
    plan: "01"
    provides: "GET /traces and GET /traces/{trace_id} endpoints with two-phase 404 and no-spans-yet 200"
provides:
  - "14 pytest unit tests for GET /traces and GET /traces/{trace_id}"
  - "Coverage: empty list, populated list, flag_count, tenant isolation, pagination, missing auth (401)"
  - "Coverage: trace detail basic shape, trace-level flags on trace.flags, span-level flags on span, scores inline"
  - "Coverage: not-found 404, cross-tenant stealth 404, no-spans-yet 200 with spans=[], missing auth 401"
affects: [frontend-trace-view, future-trace-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CH list query mocked with side_effect=[list_result, count_result] for asyncio.gather simulation"
    - "PG sequential execute mocked with side_effect=[flags_result, scores_result] for AsyncSession"
    - "No-spans-yet two-call PG pattern: side_effect=[pg_existence, pg_trace_flags]"
    - "Auth 401 tests remove verify_session_token override, keep session and CH mocks to prevent KeyError"

key-files:
  created:
    - xeter/tests/presenter/test_traces.py
  modified: []

key-decisions:
  - "CH side_effect list used for asyncio.gather simulation — two independent query results in order"
  - "Missing-auth tests retain get_session and get_ch_client overrides while removing verify_session_token, matching the pattern established in test_spans_list.py"
  - "No-spans-yet test asserts 200 and spans==[] confirming the two-phase existence check is exercised"

patterns-established:
  - "Trace test helpers: _make_flag, _make_session_mock, _make_ch_mock follow same naming convention as spans tests"
  - "_cleanup() restores dependency_overrides in every test via try/finally"

requirements-completed: [TRACE-01, TRACE-02]

# Metrics
duration: 6min
completed: "2026-05-15"
---

# Phase 20 Plan 02: Trace API Tests Summary

**14 pytest unit tests for GET /traces and GET /traces/{trace_id}: empty list, populated list, flag counts, tenant isolation, pagination, missing auth, trace/span-level flag separation, scores inline, not-found, cross-tenant stealth 404, and no-spans-yet 200**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-15T09:27:17Z
- **Completed:** 2026-05-15T09:33:35Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `xeter/tests/presenter/test_traces.py` with 14 independent pytest tests
- Covered all must-have truths from the plan: 401 on missing auth, empty-list shape, per-item field correctness, tenant isolation, two-phase 404 paths (true not-found + cross-tenant stealth), no-spans-yet 200
- Established CH side_effect pattern for asyncio.gather (two concurrent queries) and PG side_effect pattern for sequential AsyncSession queries
- Full presenter suite: 51 tests pass, no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Write unit tests for GET /traces and GET /traces/{trace_id}** - `bd1eef3` (test)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `xeter/tests/presenter/test_traces.py` - 14 unit tests for both trace endpoints, all helpers and mocking patterns inline

## Decisions Made

- CH `side_effect` list used to simulate two concurrent queries (list + count) from `asyncio.gather`; this matches how the handler calls `ch_client.query` twice via `asyncio.to_thread`
- Auth-401 tests retain `get_session` and `get_ch_client` mocks while removing the `verify_session_token` override — FastAPI resolves all dependencies concurrently before raising 401, so session and CH mocks prevent unrelated KeyError/connection failures

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All trace API unit tests complete; both TRACE-01 and TRACE-02 requirements satisfied
- Presenter suite: 51 tests pass
- Ready for v1.5 checks (real TraceAnalyzer analysis) or frontend trace-view wiring

---
*Phase: 20-trace-api*
*Completed: 2026-05-15*

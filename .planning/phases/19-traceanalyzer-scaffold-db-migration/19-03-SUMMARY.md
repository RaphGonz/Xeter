---
phase: 19-traceanalyzer-scaffold-db-migration
plan: "03"
subsystem: worker
tags: [python, redis, trace-buffer, flush-timeout, TraceAnalyzer, pytest]

# Dependency graph
requires:
  - phase: 19-traceanalyzer-scaffold-db-migration/19-01
    provides: TraceAnalyzer scaffold (analyze returns [])
  - phase: 19-traceanalyzer-scaffold-db-migration/19-02
    provides: write_flags(span_id=None, ...) for trace-level flags
provides:
  - Worker trace buffer: dict[trace_id -> list[SpanData]] accumulated in main()
  - Flush-timeout loop: TraceAnalyzer.analyze() called after WORKER_TRACE_FLUSH_TIMEOUT_S seconds of inactivity
  - process_span() returns SpanData (minimal interface extension for buffer accumulation)
  - WORKER_TRACE_FLUSH_TIMEOUT_S env var constant (default 30s)
  - 5 unit tests in test_trace_buffer.py covering buffer and flush contract
affects: [20-diagnosticer-trace-analysis, v1.5-trace-checks]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Trace buffer: in-memory dict keyed by trace_id accumulates SpanData across BRPOP iterations"
    - "Flush-timeout check runs inline after every successful span: O(n traces) but n is small"
    - "Inner try/finally on flush ensures trace_buffer and trace_last_seen always cleaned up even on error"
    - "process_span() return value used only by caller — backward-compatible with existing test mocks"

key-files:
  created:
    - xeter/tests/worker/test_trace_buffer.py
  modified:
    - xeter/services/worker/main.py

key-decisions:
  - "process_span() returns SpanData (Option A from plan) — minimal interface extension; existing callers ignore return value"
  - "Flush loop iterates all trace_ids on every span — simple, correct for low trace counts; revisit if cardinality grows"
  - "Inner try/finally on each flush: trace evicted even on TraceAnalyzer error — prevents unbounded buffer growth"
  - "tenant_id for trace flush sourced from trace_buffer[tid][0].tenant_id — all spans in a trace share tenant"

patterns-established:
  - "Trace-level write: write_flags(None, tenant_id, trace_id, flags) — span_id=None denotes trace-level flag"

requirements-completed: [TANA-03]

# Metrics
duration: 10min
completed: 2026-05-14
---

# Phase 19 Plan 03: Trace Buffer and Flush-Timeout Logic Summary

**Worker accumulates SpanData by trace_id in an in-memory buffer and invokes TraceAnalyzer.analyze() after WORKER_TRACE_FLUSH_TIMEOUT_S (30s) of inactivity, writing any returned flags via write_flags(None, ...)**

## Performance

- **Duration:** 10 min
- **Started:** 2026-05-14T14:22:39Z
- **Completed:** 2026-05-14T14:32:34Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Wired trace buffer (trace_buffer, trace_last_seen dicts) into worker main() — spans accumulate per trace_id after every successful process_span() call
- Flush-timeout loop fires after WORKER_TRACE_FLUSH_TIMEOUT_S inactivity; trace evicted from buffer even on TraceAnalyzer error (finally block)
- process_span() extended to return SpanData (minimal change; all 6 existing tests pass unchanged)
- 5 unit tests added in test_trace_buffer.py; 21/21 worker tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Add trace buffer and flush-timeout logic to worker main.py** - `2b276a4` (feat)
2. **Task 2: Write unit tests for trace buffer and flush-timeout behavior** - `7b5f798` (test)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `xeter/services/worker/main.py` - Added TraceAnalyzer import, SpanData import, WORKER_TRACE_FLUSH_TIMEOUT_S constant, process_span returns SpanData, trace_buffer/trace_last_seen dicts in main(), flush loop in BRPOP iteration
- `xeter/tests/worker/test_trace_buffer.py` - 5 tests: process_span return value, flush timeout default, analyze call contract, write_flags with flags, write_flags suppressed when empty

## Decisions Made
- process_span() returns SpanData (Option A from plan context) — keeps buffer logic in the BRPOP loop without a redundant fetch_span call
- Inner try/finally on each trace flush: trace_buffer and trace_last_seen are cleaned up unconditionally, preventing unbounded buffer growth if TraceAnalyzer raises
- Flush loop iterates all trace_ids on every span arrival (simple, linear in open-trace count; acceptable for expected cardinality)

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Phase 19 is complete: TraceAnalyzer scaffold created (19-01), DB migration for nullable span_id executed (19-02), worker flush path wired (19-03)
- v1.5 can now add real checks to TraceAnalyzer.analyze() — the infrastructure is in place
- Phase 20 (diagnosticer trace analysis) can rely on trace-level flags being written to the flags table via write_flags(None, ...)

---
*Phase: 19-traceanalyzer-scaffold-db-migration*
*Completed: 2026-05-14*

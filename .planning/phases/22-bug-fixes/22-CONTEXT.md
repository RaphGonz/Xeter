# Phase 22: Bug Fixes - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix two infrastructure bugs in the worker's BRPOP loop that block all trace-level analysis in v1.5:

1. **INFRA-01 (Idle flush):** When BRPOP times out (`result is None`), the stale-trace flush check is skipped — the last trace in a queue is silently dropped. Fix: extract `_flush_stale_traces()` and call it on both the timeout path and post-span path.
2. **INFRA-02 (Score persistence):** After `trace_analyzer.analyze()`, `flush_scores()` is never called — trace-level scores accumulate in `self._scores` and are never written to `span_scores`. Fix: call `flush_scores()` after trace analysis and write results with `span_id=None`.

No new flag types, no schema additions beyond confirming/enabling nullable `span_id` in `span_scores`. These are surgical bug fixes that gate all Phase 23–27 work.

</domain>

<decisions>
## Implementation Decisions

### Flush Check Placement (INFRA-01)

- **D-01:** Extract `_flush_stale_traces(trace_buffer, trace_last_seen, trace_analyzer)` as a **module-level function** in `xeter/services/worker/main.py` (not nested inside `main()`).
- **D-02:** The helper is called from **both** branches: `if result is None:` (BRPOP timeout) and after successful span processing. Eliminates the DRY violation that would result from inlining the check twice.
- **D-03:** Function signature: `(trace_buffer: dict, trace_last_seen: dict, trace_analyzer) -> None`. Mutates both dicts in place. Calls `time.monotonic()` internally (not a parameter — time is patched in tests).
- **D-04:** `_flush_stale_traces()` is importable from `xeter.services.worker.main` in tests, consistent with `process_span()` being module-level.

### Trace Score Write Semantics (INFRA-02)

- **D-05:** After `trace_analyzer.analyze(spans_for_trace)`, call `trace_analyzer.flush_scores()` and pass results to `write_scores(None, tenant_id_for_trace, trace_scores)`.
- **D-06:** `write_scores` is **always** called for trace scores (even if the list is empty) — consistent with span-level behavior. `score_writer.py` already early-returns for empty lists, so this is safe.
- **D-07:** `span_id=None` for trace-level score writes — consistent with how `write_flags(None, ...)` handles trace flags.
- **D-08:** Check `span_scores` migration for nullable `span_id`. If it has a `NOT NULL` constraint, add a migration to make it nullable. Update `write_scores` signature from `span_id: str` to `span_id: Optional[str]`.

### Test Coverage

- **D-09:** New test file: `xeter/tests/worker/test_flush_stale_traces.py` — dedicated to testing `_flush_stale_traces()` directly.
- **D-10:** Time control: patch `time.monotonic` via `unittest.mock.patch('xeter.services.worker.main.time.monotonic', return_value=<far future>)`. No `time.sleep` in tests.
- **D-11:** Required test scenarios:
  1. Idle flush fires when called from `result is None` path (BRPOP timeout case)
  2. Trace scores written via `write_scores(None, tenant_id, scores)` after `flush_scores()` is called
  3. Non-stale traces (recent `last_seen`) are NOT flushed
  4. Exception from `trace_analyzer.analyze()` is logged and trace is still removed from buffer (no memory leak)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Worker Core
- `xeter/services/worker/main.py` — BRPOP loop with both bugs. `process_span()` (module-level, line ~78) and `main()` (line ~122). The trace buffer and flush logic lives inline in `main()` (lines ~162–188).
- `xeter/services/worker/base.py` — `BaseAnalyzer.flush_scores()` (line ~123), `BaseTraceAnalyzer` class (line ~153). The `_scores` list accumulation pattern.

### Writers
- `xeter/services/worker/score_writer.py` — `write_scores(span_id: str, tenant_id: str, scores: list[...])`. Already early-returns for empty lists. Type update needed: `span_id: Optional[str]`.
- `xeter/services/worker/flag_writer.py` — Reference for how `span_id=None` is handled for trace flags. Check whether the pattern applies to `score_writer.py` too.

### Requirements
- `.planning/REQUIREMENTS.md` §INFRA — INFRA-01 (idle flush) and INFRA-02 (score persistence) are the two requirements this phase addresses.

### Existing Tests (patterns to follow)
- `xeter/tests/worker/test_worker_loop.py` — mock-all-IO pattern for `process_span()` tests. Follow this pattern for new tests.
- `xeter/tests/worker/test_trace_buffer.py` — existing trace buffer tests (simulate flush inline). New `test_flush_stale_traces.py` supersedes the inline simulation with real helper calls.

### Schema (check before writing migration)
- DB migration files — grep `span_scores` CREATE TABLE for `NOT NULL` on `span_id`. Location: likely `xeter/migrations/` or `alembic/versions/`. Confirm nullable before writing migration.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `process_span()` — already module-level; `_flush_stale_traces()` follows the same pattern.
- `flush_scores()` on `BaseAnalyzer` — already implemented and tested for span analyzers. Trace analyzer inherits it; just needs to be called.
- `write_scores()` / `write_flags()` — already handle the DB write contract. `write_flags(None, ...)` for traces already works; `write_scores` needs a type update.

### Established Patterns
- Mock-all-IO in tests: `patch(fetch_span)` + `patch(write_scores)` + `patch(write_flags)` — all tests use this pattern. Follow it for `test_flush_stale_traces.py`.
- `BRPOP_TIMEOUT = 2` (seconds) — the timeout that triggers `result is None`. The flush timeout is `WORKER_TRACE_FLUSH_TIMEOUT_S = 30`. A trace can only be idle for up to `BRPOP_TIMEOUT` seconds past the flush window before being caught.
- Error handling in flush loop: `try/except Exception` with `logger.error` + `finally` to clean up `trace_buffer` and `trace_last_seen`. New helper must preserve this.

### Integration Points
- `main()` in `xeter/services/worker/main.py` — the `while running:` loop is where the idle fix lives. `_flush_stale_traces()` replaces the inlined flush block at line ~167–187.
- `score_writer.py` — the `write_scores` type update (`span_id: Optional[str]`) is the only change outside `main.py`.

</code_context>

<specifics>
## Specific Ideas

- The flush helper should preserve the existing `try/except/finally` structure from the inline flush block — specifically, the `finally: trace_buffer.pop(tid, None); trace_last_seen.pop(tid, None)` that prevents memory leaks on exceptions.
- The idle flush scenario test should simulate: BRPOP times out → `_flush_stale_traces()` is called with a stale trace in the buffer → trace is flushed and removed.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 22-Bug Fixes*
*Context gathered: 2026-05-19*

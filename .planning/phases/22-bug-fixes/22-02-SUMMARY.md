---
phase: 22-bug-fixes
plan: "02"
subsystem: worker
tags: [bug-fix, idle-flush, score-persistence, trace-analyzer]
dependency_graph:
  requires:
    - 22-01 (span_scores.span_id nullable, write_scores accepts str | None)
  provides:
    - _flush_stale_traces module-level function with two call sites
    - INFRA-01 fix: stale traces flushed on BRPOP timeout
    - INFRA-02 fix: trace scores written via flush_scores() + write_scores(None, ...)
  affects:
    - xeter/services/worker/main.py
    - xeter/tests/worker/test_flush_stale_traces.py
tech_stack:
  added: []
  patterns:
    - Extract inline block to module-level helper (accepts explicit params, no implicit globals)
    - All I/O mocked in tests; time.monotonic patched via module reference
key_files:
  created:
    - xeter/tests/worker/test_flush_stale_traces.py
  modified:
    - xeter/services/worker/main.py
decisions:
  - "Placed _flush_stale_traces immediately after process_span (before entry-point comment) — consistent with existing module structure"
  - "flush_scores() called before write_scores() inside the try block — same ordering as process_span()"
  - "time.monotonic called internally in _flush_stale_traces (not passed as param) per D-03 — simplifies call sites"
metrics:
  duration: "12m"
  completed: "2026-05-19"
---

# Phase 22 Plan 02: Idle Flush + Trace Score Persistence Summary

Extracted inline trace-flush logic from `main()` into a module-level `_flush_stale_traces()` function, added `flush_scores()` + `write_scores(None, ...)` inside the function body, wired both call sites (BRPOP timeout branch + post-span branch), and wrote four tests covering all D-11 scenarios.

## What Was Done

### Task 1: Extract _flush_stale_traces and add score persistence in main.py

Three coordinated edits to `xeter/services/worker/main.py`:

**EDIT 1 — New module-level function `_flush_stale_traces`**

Added immediately after `process_span` (before `# ---- entry point ----` comment). Signature: `def _flush_stale_traces(trace_buffer: dict, trace_last_seen: dict, trace_analyzer) -> None`. Full docstring with Args block. Body taken verbatim from the inline flush block with two lines added inside the try block:

```python
trace_scores = trace_analyzer.flush_scores()           # INFRA-02 fix
write_scores(None, tenant_id_for_trace, trace_scores)  # INFRA-02 fix
```

**EDIT 2 — INFRA-01 fix: result is None branch**

Replaced `continue` with `_flush_stale_traces(trace_buffer, trace_last_seen, trace_analyzer)` then `continue`. Stale traces are now flushed on every BRPOP timeout.

**EDIT 3 — Replace inline flush block in main()**

Removed the `# Check all traces for flush timeout` comment and the 22-line loop it introduced. Replaced with a single call: `_flush_stale_traces(trace_buffer, trace_last_seen, trace_analyzer)`.

**Commit:** `cdadc88`

### Task 2: test_flush_stale_traces.py — four D-11 scenarios

Created `xeter/tests/worker/test_flush_stale_traces.py` with:

- `make_test_span(span_id, trace_id, tenant_id)` helper (keyword args with defaults, matching test_trace_buffer.py)
- `make_mock_trace_analyzer(flags, scores)` helper returning a MagicMock
- Four test functions — all using `patch("xeter.services.worker.main.time.monotonic", return_value=9999.0)` to control staleness deterministically

| Test | What it covers |
|------|----------------|
| `test_idle_flush_fires_when_stale` | trace-A (last_seen=0) → flushed + removed from both dicts |
| `test_trace_scores_written_with_none_span_id` | `write_scores(None, tenant_id, scores)` — INFRA-02 verified |
| `test_non_stale_trace_not_flushed` | trace-C (last_seen=9998, now=9999 → delta=1s < 30s) → NOT flushed |
| `test_exception_in_analyze_logs_and_cleans_buffer` | RuntimeError from analyze() caught; trace-D removed (no memory leak) |

**Commit:** `118c684`

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| 1. import ok | `python -c "from xeter.services.worker.main import _flush_stale_traces, WORKER_TRACE_FLUSH_TIMEOUT_S; print('import ok')"` | import ok |
| 2. call sites = 2 | `grep -c "_flush_stale_traces(trace_buffer" main.py` | 2 |
| 3. write_scores(None) | `grep -n "write_scores(None" main.py` | line 148: one match inside _flush_stale_traces |
| 4. inline block removed | `grep -n "Check all traces for flush timeout" main.py` | no match (correct) |
| 5. new tests | `python -m pytest xeter/tests/worker/test_flush_stale_traces.py -v` | 4 passed |
| 6. patch target count | `grep -c "xeter.services.worker.main.time.monotonic" test_flush_stale_traces.py` | 4 |
| 7. full suite | `python -m pytest xeter/tests/ -x -q` | 99 passed, 9 skipped, 1 pre-existing failure (spaCy) |

### Pre-existing failure note

`test_tool_call_analyzer.py::test_analyze_returns_list` fails with `ModuleNotFoundError: No module named 'spacy'` — identical to Plan 01. No regressions introduced.

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Commit | Message | Files |
|--------|---------|-------|
| `cdadc88` | `feat(22-02): extract _flush_stale_traces and add trace score persistence` | `xeter/services/worker/main.py` |
| `118c684` | `test(22-02): add test_flush_stale_traces with four D-11 scenarios` | `xeter/tests/worker/test_flush_stale_traces.py` (new) |

## Self-Check: PASSED

- `xeter/services/worker/main.py` contains `def _flush_stale_traces` at line 119
- `xeter/tests/worker/test_flush_stale_traces.py` exists with 4 test functions
- `grep -c "_flush_stale_traces(trace_buffer" main.py` = 2 (lines 196, 210)
- `grep -n "write_scores(None" main.py` = line 148 (one match)
- `grep -n "Check all traces for flush timeout" main.py` = no match
- Commits `cdadc88` and `118c684` exist in git log

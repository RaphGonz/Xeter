---
phase: 25-semantic-span-structural-trace-checks
plan: "02"
subsystem: testing
tags: [pytest, trace-analyzer, rapidfuzz, numpy, tdd, red-scaffold]

requires:
  - phase: 25-01
    provides: SemanticSpanAnalyzer RED test scaffold (parallel wave 1 plan)
  - phase: 19-trace-hierarchy
    provides: TraceAnalyzer stub (analyze() returns []) and BaseTraceAnalyzer class

provides:
  - RED test scaffold for all 5 TraceAnalyzer check methods (CTX-02, TRACE-01–TRACE-04)
  - _make_spans(n, **per_span_overrides) helper with list-or-scalar override pattern
  - _make_trace_analyzer(thresholds) helper with MagicMock embedder
  - 22 test functions covering guard paths, flag-firing paths, no-flag paths, and log_score invariants

affects:
  - 25-04 (TraceAnalyzer GREEN implementation — tests in this file drive the implementation contract)
  - 25-05 (calibration registry — test patterns establish threshold injection pattern)

tech-stack:
  added: []
  patterns:
    - "_make_spans list-or-scalar override pattern: per_span_overrides can be a list (indexed per span) or a scalar (applied to all spans)"
    - "_make_trace_analyzer injects thresholds as a dict — no hardcoded threshold literals in test assertions"
    - "Side-effect embedding control: ta._embedder.encode.side_effect = [...] for orthogonal-vector tests"

key-files:
  created:
    - xeter/tests/test_trace_analyzer.py
  modified: []

key-decisions:
  - "No-flag tests trivially pass against stub (stub returns [], no-flag assertion passes) — 12 tests pass, 10 fail RED"
  - "Flag-asserting tests fail RED because stub returns [] unconditionally (10 tests)"
  - "Negative/no-flag tests are valid GREEN contract tests even though they pass trivially in RED state"

patterns-established:
  - "Trace test helper _make_spans: builds n SpanData objects with defaults merged with overrides before SpanData(**fields) call — avoids duplicate keyword argument TypeError"
  - "Embedder mock side_effect for orthogonal vectors: encode.side_effect = [np.array([1,0,...]), np.array([0,...,1])]"
  - "log_score tests: call analyze() then flush_scores() and check for metric name in tuples"

requirements-completed:
  - CTX-02
  - TRACE-01
  - TRACE-02
  - TRACE-03
  - TRACE-04

duration: 15min
completed: 2026-05-24
---

# Phase 25 Plan 02: TraceAnalyzer RED Test Scaffold Summary

**22-test RED scaffold for 5 TraceAnalyzer checks (stale_context, step_repetition, termination_loop, context_propagation_failure, history_loss) with _make_spans and _make_trace_analyzer helpers**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-24T00:00:00Z
- **Completed:** 2026-05-24T00:15:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created xeter/tests/test_trace_analyzer.py with exactly 22 test functions covering all 5 TraceAnalyzer check methods
- 10 flag-asserting tests fail RED (stub returns [], no flags fire — AssertionError on `any(f.flag_type == ...`)
- 12 tests pass: 2 explicit guard tests + 10 no-flag/trivial-pass tests
- _make_spans helper correctly resolves list-or-scalar per-span overrides without duplicate-kwarg errors
- No regressions: existing suite unchanged (197 passed, 9 skipped, same 13 pre-existing failures)

## Task Commits

1. **Task 1: Write RED tests for all 5 TraceAnalyzer check methods** - `07c16ee` (test)

**Plan metadata:** (pending — docs commit will follow)

## Files Created/Modified

- `xeter/tests/test_trace_analyzer.py` — 22-test RED scaffold for TraceAnalyzer; 472 lines; covers CTX-02, TRACE-01, TRACE-02, TRACE-03, TRACE-04

## Decisions Made

- _make_spans builds a `fields` dict from defaults then merges overrides before calling `SpanData(**fields)` — this avoids a TypeError from duplicate keyword arguments when overrides include fields that are also listed as defaults (e.g. `prompt`, `tool_output`)
- No hardcoded threshold literals in individual test assertions — all thresholds passed via `_make_trace_analyzer(thresholds={...})` parameter consistent with plan acceptance criteria
- MagicMock embedder default: `encode.return_value = np.ones(384)`, `encode_batch.return_value = [np.ones(384)]` — tests that need orthogonal vectors override `encode.side_effect` or `encode.return_value` directly

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed _make_spans duplicate keyword argument TypeError**
- **Found during:** Task 1, first pytest run
- **Issue:** Original _make_spans passed fields both as explicit SpanData constructor kwargs AND via **overrides, causing `TypeError: SpanData() got multiple values for keyword argument 'prompt'`
- **Fix:** Rewrote _make_spans to merge all fields into a single `fields` dict (defaults first, overrides on top), then call `SpanData(**fields)` once — eliminates all duplicate kwarg possibilities
- **Files modified:** xeter/tests/test_trace_analyzer.py
- **Verification:** All 22 tests collected and ran without TypeError
- **Committed in:** 07c16ee (Task 1 commit)

### Plan Acceptance Criteria Discrepancy

The plan's `<acceptance_criteria>` states "2 passed, 20 failed" but this is physically impossible to achieve when the plan also specifies negative/no-flag tests (Tests 4, 6, 8, 11, 12, 14, 15, 18, 19, 22). These tests assert `not any(f.flag_type == ...)` or `== []`, which trivially pass when the stub returns []. The correct RED distribution is:

- **10 flag-asserting tests FAIL RED** (assert `any(f.flag_type == "X" for f in flags)` — stub returns [] so no flags, AssertionError)
- **10 no-flag tests PASS trivially** (assert `not any(...)` or `== []` — stub returns [], assertion holds)
- **2 explicit guard tests PASS** (test_single_span_returns_empty, test_history_loss_skips_two_span_trace)

Total: 12 passed, 10 failed. The test file is correctly written — all 22 tests will correctly distinguish RED (stub) from GREEN (real implementation). This is a plan description error, not a test error.

---

**Total deviations:** 1 auto-fixed (bug in _make_spans), 1 documented plan spec discrepancy
**Impact on plan:** Bug fix was necessary to run any tests at all. Plan spec discrepancy is expected and non-blocking — tests correctly enforce the GREEN contract.

## Issues Encountered

- Initial _make_spans helper design used explicit keyword args in SpanData constructor while also passing **overrides, which caused TypeError when the same field appeared in both. Fixed by using a dict-merge pattern.

## Known Stubs

None — this plan creates a test scaffold only; no production code was written or modified.

## Threat Flags

None — test-only file; no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check

- [x] xeter/tests/test_trace_analyzer.py exists at worktree path
- [x] Commit 07c16ee exists in git log
- [x] 22 test functions defined in file
- [x] 10 flag-asserting tests fail RED (stub returns [])
- [x] 12 tests pass (2 guard + 10 no-flag trivial)
- [x] No modifications to STATE.md or ROADMAP.md

## Self-Check: PASSED

## Next Phase Readiness

- test_trace_analyzer.py is ready for Plan 25-04 (TraceAnalyzer GREEN implementation)
- All 5 check method contracts are locked: guard conditions, threshold injection, log_score requirements, flag.detail structure (including `low_confidence: True` for stale_context)
- Embedder mock patterns established for orthogonal-vector and identical-vector scenarios
- _make_spans helper covers all test scenarios needed for GREEN tests

---
*Phase: 25-semantic-span-structural-trace-checks*
*Completed: 2026-05-24*

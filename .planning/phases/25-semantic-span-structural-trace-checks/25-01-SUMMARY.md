---
phase: 25-semantic-span-structural-trace-checks
plan: "01"
subsystem: testing
tags: [pytest, tdd, red-scaffold, numpy, semantic-span-analyzer, missing-details]

# Dependency graph
requires:
  - phase: 24-structural-span-checks
    provides: OutputSchemaAnalyzer class boundary and log_score invariant patterns used as analogs
  - phase: 23-infrastructure
    provides: SpanData, Flag, BaseSpanAnalyzer, hybrid_score, bow_score from base.py

provides:
  - RED test scaffold (10 failing tests) defining the SemanticSpanAnalyzer._check_missing_details contract

affects:
  - 25-03-PLAN.md (GREEN implementation — must make all 10 tests pass)
  - 25-04-PLAN.md (integration wiring — tests indirectly constrain constructor signature)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deferred production imports in test helpers (import inside function body) allow collection before module exists"
    - "encode.side_effect list for multi-call orthogonal vector control"
    - "Two-instance threshold test proving no hardcoded literal (threshold=0.99 vs threshold=0.0)"

key-files:
  created:
    - xeter/tests/test_semantic_span_analyzer.py
  modified: []

key-decisions:
  - "All SemanticSpanAnalyzer imports deferred inside _make_analyzer() helper and test bodies — allows pytest collection in RED state"
  - "Test 10 uses two separate analyzer instances with contrasting thresholds (0.99 / 0.0) to prove threshold configurability without hardcoded literals"
  - "Orthogonal vectors [1.0]*192+[0.0]*192 vs [0.0]*192+[1.0]*192 produce cosine=0 deterministically; combined with unrelated strings for low bow"

patterns-established:
  - "Deferred-import helper pattern: from xeter.services.worker.X import Y inside helper function body"
  - "RED scaffold TDD: 10 tests covering guards, flag-firing, no-flag, log_score invariant, detail structure, name, dispatch, threshold"

requirements-completed:
  - CTX-04

# Metrics
duration: 8min
completed: 2026-05-24
---

# Phase 25 Plan 01: SemanticSpanAnalyzer RED Test Scaffold Summary

**10-test RED scaffold defining the full _check_missing_details contract via guard, flag-firing, log_score invariant, detail-key, name, dispatch, and threshold-configurability assertions**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-24T00:00:00Z
- **Completed:** 2026-05-24T00:08:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created xeter/tests/test_semantic_span_analyzer.py with exactly 10 test functions matching the names required by the plan
- All 10 tests fail RED with `ModuleNotFoundError: No module named 'xeter.services.worker.semantic_span_analyzer'`
- No production module imported at module level — all SemanticSpanAnalyzer and SpanData imports are deferred inside helper functions and test bodies, ensuring pytest collection succeeds in RED state
- Zero regressions: existing 197-pass / 13-pre-existing-fail baseline is unchanged

## Task Commits

1. **Task 1: Write RED tests for SemanticSpanAnalyzer._check_missing_details** - `ef9fb36` (test)

## Files Created/Modified

- `xeter/tests/test_semantic_span_analyzer.py` — 10 RED tests for SemanticSpanAnalyzer._check_missing_details: guards (prompt=None, response=None), log_score invariant, flag-fires, no-flag, detail "metric"/"cosine"/"bow" keys, name property, dispatch spy, threshold configurability

## Decisions Made

- Deferred all production imports inside `_make_analyzer()` helper and individual test bodies rather than at module level — allows pytest collection when the production module does not yet exist
- Test 10 uses two independent SemanticSpanAnalyzer instances with threshold=0.99 and threshold=0.0 on the same moderate-similarity vectors, proving no hardcoded literal exists
- Orthogonal vectors ([1.0]*192+[0.0]*192 vs [0.0]*192+[1.0]*192, each dim-384) produce exact cosine=0, making flag-firing tests deterministic

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- RED scaffold complete and committed; Plan 25-02 (TraceAnalyzer RED scaffold) can execute in parallel in wave 1
- Plan 25-03 (GREEN implementation of SemanticSpanAnalyzer) can proceed once wave 1 completes — it must make all 10 tests pass without modifying them
- Test names are fixed contracts; the GREEN implementation must satisfy exactly: test_missing_details_no_flag_when_prompt_is_none, test_missing_details_no_flag_when_response_is_none, test_missing_details_logs_score_before_threshold_check, test_missing_details_returns_flag_when_score_below_threshold, test_missing_details_no_flag_when_score_above_threshold, test_missing_details_flag_has_metric_key, test_missing_details_flag_has_cosine_and_bow_keys, test_semantic_span_analyzer_name_property, test_analyze_dispatches_to_check_missing_details, test_missing_details_uses_thresholds_dict_not_literal

---

## Self-Check

### Files Exist

- `xeter/tests/test_semantic_span_analyzer.py` — FOUND (313 lines, created in worktree)

### Commits Exist

- `ef9fb36` — FOUND (`test(25-01): RED scaffold for SemanticSpanAnalyzer._check_missing_details`)

## Self-Check: PASSED

---

*Phase: 25-semantic-span-structural-trace-checks*
*Completed: 2026-05-24*

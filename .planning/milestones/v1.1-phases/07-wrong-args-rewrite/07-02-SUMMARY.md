---
phase: 07-wrong-args-rewrite
plan: "02"
subsystem: worker
tags: [bow_score, hybrid_score, jaccard, cosine, similarity, utility]

# Dependency graph
requires:
  - phase: 07-wrong-args-rewrite
    provides: base.py BaseAnalyzer class with embed/compare/log_score helpers
provides:
  - bow_score(text_a, text_b) -> float: Jaccard token overlap, module-level in base.py
  - hybrid_score(cosine, bow, weight=0.5) -> float: weighted blend, module-level in base.py
affects:
  - 07-03-wrong-args-rewrite
  - 08-wrong-tool
  - 09-no-tool-tool-use-violation
  - 10-excessive-tool

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "HYBRID-01: module-level utility functions in base.py for shared cross-analyzer use"
    - "Jaccard set overlap for BOW similarity with stdlib only (no new deps)"
    - "Weighted cosine+BOW blend with configurable weight defaulting to 0.5"

key-files:
  created: []
  modified:
    - xeter/services/worker/base.py
    - xeter/tests/worker/test_tool_call_analyzer.py

key-decisions:
  - "HYBRID-01 utility functions placed at module level in base.py so all current and future analyzers can import without gymnastics"
  - "BOW implemented using stdlib set operations only — no new dependencies added"
  - "Default weight=0.5 for hybrid_score establishes equal cosine/BOW contribution as per HYBRID-01 spec"

patterns-established:
  - "Module-level pure functions in base.py: importable from xeter.services.worker.base without instantiating BaseAnalyzer"
  - "bow_score returns 0.0 for empty string inputs (no crash, avoids division by zero)"

requirements-completed:
  - HYBRID-01

# Metrics
duration: 8min
completed: 2026-04-06
---

# Phase 7 Plan 02: Hybrid Scoring Utility Functions Summary

**Pure Jaccard BOW and weighted cosine+BOW blend functions added to base.py as module-level HYBRID-01 foundation for all v1.1 similarity rewrites**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-06T08:53:16Z
- **Completed:** 2026-04-06T09:01:21Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added `bow_score(text_a, text_b)` module-level function to `base.py` — Jaccard token overlap using stdlib set operations, returns 0.0 on empty input
- Added `hybrid_score(cosine, bow, weight=0.5)` module-level function to `base.py` — weighted blend, defaults to 50/50 as per HYBRID-01 spec
- Added 7 new unit tests covering partial overlap, identical strings, no overlap, empty string edge cases, equal weight, custom weight, and both-max cases
- All 23 tests pass (16 original + 7 new)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add bow_score and hybrid_score functions to base.py** - `f42f123` (feat)
2. **Task 2: Add unit tests for bow_score and hybrid_score** - `2735404` (test)

**Plan metadata:** (pending docs commit)

## Files Created/Modified
- `xeter/services/worker/base.py` - Added `bow_score` and `hybrid_score` as module-level functions after the `BaseAnalyzer` class
- `xeter/tests/worker/test_tool_call_analyzer.py` - Added `bow_score`/`hybrid_score` to import line; appended 7 new unit tests

## Decisions Made
- Functions placed at module level in `base.py` rather than inside `BaseAnalyzer` — enables importing without instantiating the class, which is the right pattern for pure utility functions with no instance state
- No new dependencies: stdlib `set` operations are sufficient for Jaccard overlap (`tokens_a & tokens_b` / `tokens_a | tokens_b`)
- Default `weight=0.5` is the HYBRID-01 canonical value; callers can override for task-specific tuning in plans 07-03 through 10

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `bow_score` and `hybrid_score` are importable from `xeter.services.worker.base` — plan 07-03 can now add `from xeter.services.worker.base import bow_score, hybrid_score` to `tool_call_analyzer.py` and use them in `_check_wrong_tool_args`
- HYBRID-01 requirement satisfied; all four v1.1 analyzer rewrites (phases 7–10) have their shared utility available

## Self-Check: PASSED

- xeter/services/worker/base.py: FOUND
- xeter/tests/worker/test_tool_call_analyzer.py: FOUND
- 07-02-SUMMARY.md: FOUND
- Commit f42f123: FOUND
- Commit 2735404: FOUND

---
*Phase: 07-wrong-args-rewrite*
*Completed: 2026-04-06*

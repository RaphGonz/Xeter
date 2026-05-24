---
phase: 25-semantic-span-structural-trace-checks
plan: "04"
subsystem: worker
tags: [trace-analyzer, rapidfuzz, numpy, embeddings, detection-checks, tdd]

# Dependency graph
requires:
  - phase: 25-02
    provides: RED test scaffold — 22 tests for 5 TraceAnalyzer check methods
  - phase: 25-03
    provides: SemanticSpanAnalyzer GREEN (same worker, same base pattern)
provides:
  - TraceAnalyzer with 5 _check_*() methods (CTX-02, TRACE-01, TRACE-02, TRACE-03, TRACE-04)
  - All 22 test_trace_analyzer tests passing GREEN
affects:
  - 25-05 (wiring TraceAnalyzer into calibrate.py + main.py)
  - Phase 27 (calibration dataset from flush_scores)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "fuzz.ratio for character-level stale content detection (0-100 scale)"
    - "fuzz.token_sort_ratio for word-order-invariant step repetition detection"
    - "consecutive run_length tracking for termination_loop (not total count)"
    - "hybrid cosine+BOW scoring via hybrid_score() for context_propagation_failure"
    - "np.mean centroid of encode_batch results for history_loss detection"
    - "log_score BEFORE threshold comparison (D-04 invariant — every check method)"

key-files:
  created:
    - xeter/services/worker/trace_analyzer.py
  modified:
    - xeter/services/worker/base.py (worktree Rule 3 fix — added BaseSpanAnalyzer + BaseTraceAnalyzer)
    - xeter/tests/test_trace_analyzer.py (copied from Plan 25-02 RED commit — not in worktree branch)

key-decisions:
  - "stale_context uses fuzz.ratio (character-level), not token_sort_ratio — literal reuse is the signal"
  - "termination_loop tracks consecutive runs not total count — resets on different tool_name or None"
  - "history_loss guards len(spans) < 3 (needs >= 2 prior prompts for meaningful centroid)"
  - "No numeric threshold literals in check methods — always self._thresholds[key]"
  - "low_confidence: True in stale_context flag detail only (D-06)"

patterns-established:
  - "TraceAnalyzer._check_*() pattern: guard → loop → skip-on-None → score → log_score → threshold comparison → Flag"
  - "log_score invariant: called BEFORE threshold comparison, after score computation (D-04)"

requirements-completed:
  - CTX-02
  - TRACE-01
  - TRACE-02
  - TRACE-03
  - TRACE-04

# Metrics
duration: 12min
completed: 2026-05-24
---

# Phase 25 Plan 04: TraceAnalyzer GREEN Implementation Summary

**TraceAnalyzer stub replaced with 5 detection methods using rapidfuzz (stale_context, step_repetition), consecutive counting (termination_loop), and hybrid cosine+BOW scoring (context_propagation_failure, history_loss) — all 22 tests GREEN**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-24T14:25:00Z
- **Completed:** 2026-05-24T14:37:00Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Replaced the 38-line Phase 19 stub `analyze() return []` with a 287-line full implementation
- All 5 trace-level check methods implemented per CTX-02 and TRACE-01 through TRACE-04
- All 22 tests in test_trace_analyzer.py pass GREEN (was 10 failing RED)
- log_score invariant (D-04) enforced in all 4 similarity-based methods; termination_loop correctly omits log_score (count-based)
- No numeric threshold literals in any check method body

## Task Commits

1. **Task 1: Implement all 5 TraceAnalyzer check methods** - `b09ab10` (feat)

## Files Created/Modified
- `xeter/services/worker/trace_analyzer.py` - Full implementation of TraceAnalyzer with 5 _check_*() methods (287 lines)
- `xeter/services/worker/base.py` - Updated with BaseSpanAnalyzer and BaseTraceAnalyzer (Rule 3 auto-fix — worktree branch was missing these classes from Phase 24)
- `xeter/tests/test_trace_analyzer.py` - 22-test RED scaffold from Plan 25-02 (copied into worktree branch which predates Phase 25-02 commits)

## Decisions Made
- Followed plan exactly as specified for all 5 check methods
- No architectural changes required
- fuzz.ratio selected for stale_context (character-level similarity), fuzz.token_sort_ratio for step_repetition (word-order invariant)
- history_loss uses encode_batch for all prior prompts then np.mean centroid

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated base.py with missing BaseSpanAnalyzer and BaseTraceAnalyzer**
- **Found during:** Task 1 (import of TraceAnalyzer failed with ImportError)
- **Issue:** Worktree branch predates Phase 24 commits; base.py in worktree was missing `BaseSpanAnalyzer` and `BaseTraceAnalyzer` classes that were added in Phase 24
- **Fix:** Copied updated `base.py` from main repo into the worktree's `xeter/services/worker/base.py`
- **Files modified:** `xeter/services/worker/base.py`
- **Verification:** Tests pass with import after fix
- **Committed in:** `b09ab10` (Task 1 commit)

**2. [Rule 3 - Blocking] Added test_trace_analyzer.py to worktree (from Plan 25-02 RED phase)**
- **Found during:** Test run setup
- **Issue:** Worktree branch predates Plan 25-02 commit (07c16ee) that wrote the RED test scaffold; test file not present in worktree
- **Fix:** Copied test file from main repo (`xeter/tests/test_trace_analyzer.py`) into worktree
- **Files modified:** `xeter/tests/test_trace_analyzer.py`
- **Verification:** 22 tests collected and run correctly
- **Committed in:** `b09ab10` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking issues from worktree branch predating Phase 24/25-02)
**Impact on plan:** Both auto-fixes essential for the worktree to run the tests. No scope creep — base.py and test file are exact copies of what main branch already has.

## Issues Encountered
- Worktree branch (`worktree-agent-a6a44fa7c0b7287a2`) was created before Phase 24 commits, so it lacked `BaseTraceAnalyzer` in base.py and the RED test scaffold from Plan 25-02. Both resolved via Rule 3 auto-fix by copying from main repo.

## Known Stubs
None - all 5 check methods are fully implemented with no placeholders.

## Threat Flags
None - no new network endpoints, auth paths, file access patterns, or schema changes introduced. All content stays within existing trust boundaries (spans → embedder → rapidfuzz, per T-25-04-01 through T-25-04-SC in PLAN.md threat register).

## Next Phase Readiness
- TraceAnalyzer is production-ready
- Plan 25-05: wire TraceAnalyzer into calibrate.py and main.py (register CTX-02 + TRACE-01-04 flag types, add thresholds to WORKER_THRESHOLD_*)
- All 5 checks will contribute to calibration dataset via flush_scores() on every trace analysis

---
*Phase: 25-semantic-span-structural-trace-checks*
*Completed: 2026-05-24*

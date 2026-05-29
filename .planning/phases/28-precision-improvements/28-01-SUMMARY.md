---
phase: 28-precision-improvements
plan: 01
subsystem: testing
tags: [calibration, rapidfuzz, spacy, trace-analyzer, precision, false-positives]

dependency_graph:
  requires:
    - phase: 27-calibration-pass
      provides: Calibration results showing scale mismatch and over-broad detection in 9 trace-level check methods
  provides:
    - Fixed _check_stale_context() and _check_step_repetition() with fuzz output normalized to 0.0–1.0
    - Fixed _check_termination_loop() with log_score for calibration signal
    - Tightened preconditions for _check_context_propagation_failure, _check_history_loss, _check_wrong_agent_handoff, _check_information_withholding, _check_conversation_reset, _check_no_verification
  affects:
    - 28-02 (tool_call_analyzer.py fixes) — same file pattern, consistent approach
    - 28-03 (re-calibration run) — blocked on these fixes; can now run meaningful calibration for all 9 types

tech-stack:
  added: []
  patterns:
    - "D-04 invariant: log_score called before flag/clean decision in all _check_*() methods"
    - "Streak counter pattern for sustained-drop detection (low_score_streak >= 2)"
    - "Positive membership check for routing graph: src in graph AND dst not in graph[src]"
    - "Hard precondition guard exits do NOT call log_score (D-04 consistency)"

key-files:
  created: []
  modified:
    - xeter/services/worker/trace_analyzer.py

key-decisions:
  - "Normalize fuzz.ratio/fuzz.token_sort_ratio by dividing by 100: scores now 0.0–1.0 consistent with all other metrics"
  - "wrong_agent_handoff: positive membership check (src in graph) prevents unknown agents from triggering false positives"
  - "information_withholding: score >= 0.5 is a guard exit (no log_score), not a threshold comparison"
  - "no_verification: write/mutate precondition uses local frozenset (not module-level) to keep guard self-contained"
  - "conversation_reset: prev_score initialized to 1.0 so first evaluated span always has a valid prior score"

patterns-established:
  - "Streak counter pattern: low_score_streak += 1 on failure, reset to 0 on pass, flag only when >= 2"
  - "Guard exit vs threshold comparison: guard exits (preconditions not met) skip log_score; only threshold comparisons come after log_score"

requirements-completed: []

duration: 13min
completed: "2026-05-29"
---

# Phase 28 Plan 01: Algorithm Precision Fixes for 9 Trace-Level Flag Types

**Normalized fuzz scale mismatch, added log_score to termination_loop, and tightened preconditions for 6 over-broad trace-level checks in trace_analyzer.py**

## Performance

- **Duration:** 13 min
- **Started:** 2026-05-29T18:51:06Z
- **Completed:** 2026-05-29T19:04:49Z
- **Tasks:** 3
- **Files modified:** 1

## Accomplishments

- Fixed D-05: stale_context and step_repetition now use 0.0–1.0 normalized scores (fuzz output / 100) — resolves always-fires bug at threshold=0.95
- Fixed D-06: termination_loop now emits log_score on every span, giving calibration harness a meaningful signal
- Fixed D-09/D-10/D-12/D-13/D-16/D-08: six methods have tighter preconditions — 2+ hop streak, span count gates, write/mutate check, NE count gate, abruptness delta

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix scale mismatch in _check_stale_context and _check_step_repetition** - `d994289` (fix)
2. **Task 2: Fix termination_loop consecutive-run logic** - `625714f` (fix)
3. **Task 3: Tighten 6 trace-level check preconditions** - `e529705` (fix)

## Files Created/Modified

- `xeter/services/worker/trace_analyzer.py` — 9 _check_*() methods modified: 2 scale fixes, 1 log_score addition, 6 precondition tightenings

## Decisions Made

- `wrong_agent_handoff` positive membership check: `src in self._routing_graph and dst not in self._routing_graph[src]` — ensures only known-but-misrouted agents trigger flags; unknown agents (None or unregistered) are silently skipped
- `information_withholding` score >= 0.5 hard precondition exits WITHOUT log_score — this is a guard exit per D-04 invariant, not a threshold comparison
- `no_verification` WRITE_MUTATE_KEYWORDS defined as local frozenset inside the method — avoids module-level pollution and keeps the guard self-contained
- `conversation_reset` prev_score initialized to 1.0 — ensures first evaluation at i=4 compares against a neutral baseline rather than an undefined value

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — all six methods modified cleanly without unexpected behavior.

## Verification Results

- `python -m py_compile xeter/services/worker/trace_analyzer.py` — exits 0
- `python -c "from xeter.services.worker.trace_analyzer import TraceAnalyzer"` — exits 0
- `python -m pytest xeter/tests/test_calibrate_routing.py -q` — 28 passed, 0 failed
- `grep -n "/ 100" xeter/services/worker/trace_analyzer.py` — shows lines 128 and 169 (both normalizations)
- `grep -n "log_score.*termination_loop" xeter/services/worker/trace_analyzer.py` — shows line 219

## Known Stubs

None — all fixes are complete algorithm changes; no placeholder values or hardcoded returns.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes. All changes are internal to in-memory _check_*() logic.

## Next Phase Readiness

- Plan 28-02 (tool_call_analyzer.py fixes for tool_not_available, wrong_tool_choice, wrong_tool_args, response_anomaly, missing_details) — ready to execute independently
- Plan 28-03 (re-calibration run) — blocked on 28-01 and 28-02 completing; after both finish, calibration should produce meaningful thresholds for all 9 fixed types

## Self-Check

| Item | Status |
|------|--------|
| xeter/services/worker/trace_analyzer.py | FOUND |
| Commit d994289 (Task 1 — fuzz normalization) | FOUND |
| Commit 625714f (Task 2 — termination_loop log_score) | FOUND |
| Commit e529705 (Task 3 — 6 precondition fixes) | FOUND |
| 28 routing tests pass | VERIFIED |
| fuzz.ratio / 100 in _check_stale_context | VERIFIED (line 128) |
| fuzz.token_sort_ratio / 100 in _check_step_repetition | VERIFIED (line 169) |
| log_score in _check_termination_loop before flags.append | VERIFIED (line 219) |
| low_score_streak in _check_context_propagation_failure | VERIFIED |
| range(3, ...) in _check_history_loss | VERIFIED |
| src in self._routing_graph positive check | VERIFIED |
| len(produced) >= 2 guard in _check_information_withholding | VERIFIED |
| range(4, ...) and prev_score in _check_conversation_reset | VERIFIED |
| has_write_mutate guard in _check_no_verification | VERIFIED |

## Self-Check: PASSED

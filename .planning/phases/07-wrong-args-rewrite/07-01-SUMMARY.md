---
phase: 07-wrong-args-rewrite
plan: "01"
subsystem: infra
tags: [calibration, argparse, cli, hill-climbing, thresholds]

# Dependency graph
requires: []
provides:
  - calibrate.py --flag-type CLI argument for per-flag-type isolation runs
  - BINARY_FLAG_TYPES set for non-numeric detectors (empty; Phase 9 placeholder)
  - wrong_tool_args re-included in FLAG_TYPES (calibratable after Phase 7 rewrite)
affects: [08-no-tool-rewrite, 09-tool-use-violation, 10-calibration-run]

# Tech tracking
tech-stack:
  added: [argparse]
  patterns:
    - "BINARY_FLAG_TYPES set separates numeric vs. binary detectors at calibration time"
    - "parse_args() + active_flag_types filter pattern for per-run isolation"

key-files:
  created: []
  modified:
    - xeter/scripts/calibrate.py

key-decisions:
  - "Use set() not {} for BINARY_FLAG_TYPES — Python {} literal is always dict, not set"
  - "Guard threshold_output serialization: round(x, 4) only when x is not None (binary types have None P/R)"
  - "plot_pr_curves() filters to plottable results (non-empty history) so binary-only runs do not crash matplotlib"

patterns-established:
  - "active_flag_types: the run-time filtered list from FLAG_TYPES; use this in loops, not FLAG_TYPES directly"
  - "binary flag result shape: {best_threshold: 1.0, best_precision: None, best_recall: None, history: [], steps: 0, binary: True}"

requirements-completed: [CAL-01, CAL-02]

# Metrics
duration: 12min
completed: 2026-04-06
---

# Phase 7 Plan 01: Calibrate Infrastructure Summary

**calibrate.py extended with --flag-type isolation CLI arg, BINARY_FLAG_TYPES set, and wrong_tool_args re-included in FLAG_TYPES after Phase 7 rewrite**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-06T08:53:34Z
- **Completed:** 2026-04-06T09:05:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Added `parse_args()` using argparse with `--flag-type` argument; main() now filters `active_flag_types` when flag given
- Added `BINARY_FLAG_TYPES: set[str] = set()` immediately after `FLAG_TYPES` — empty placeholder for Phase 9 `tool_use_violation`
- Re-added `wrong_tool_args` to `FLAG_TYPES` (was commented out; the Phase 7 rewrite removes the low_confidence design constraint)
- Removed stale `NOTE: wrong_tool_args excluded` print from main()
- Guarded summary loop, plot_pr_curves(), and threshold_output serialization for binary result entries where `best_precision` is None

## Task Commits

Each task was committed atomically:

1. **Task 1: Add BINARY_FLAG_TYPES, parse_args(), --flag-type filter** - `c18dc11` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `xeter/scripts/calibrate.py` - Added parse_args(), BINARY_FLAG_TYPES, wrong_tool_args in FLAG_TYPES, filtered loops, removed stale NOTE

## Decisions Made

- Used `set()` literal instead of `{}` for BINARY_FLAG_TYPES because Python `{}` is always a dict, making the type annotation misleading and the isinstance check fail.
- Added None guards throughout (summary print, plot filter, JSON serialization) so binary flag types with no P/R values never cause TypeErrors at runtime.
- Kept `DEFAULT_THRESHOLDS["wrong_tool_args"] = 0.4` — it remains the calibration starting point; only the in-loop exclusion was removed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed BINARY_FLAG_TYPES being parsed as dict instead of set**
- **Found during:** Task 1 (verification step)
- **Issue:** Plan specified `BINARY_FLAG_TYPES: set[str] = { # "tool_use_violation", ... }` — but `{}` in Python is an empty dict, so `isinstance(BINARY_FLAG_TYPES, set)` returned False
- **Fix:** Changed initializer to `set()` with the Phase 9 placeholder comment above it
- **Files modified:** xeter/scripts/calibrate.py
- **Verification:** `python -c "from xeter.scripts.calibrate import BINARY_FLAG_TYPES; assert isinstance(BINARY_FLAG_TYPES, set)"` passes
- **Committed in:** c18dc11 (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added None guards for binary results in threshold_output serialization**
- **Found during:** Task 1 (code review before commit)
- **Issue:** `threshold_output` called `round(res["best_precision"], 4)` unconditionally; binary results have `best_precision=None` which would raise TypeError at runtime
- **Fix:** Added `round(x, 4) if x is not None else None` guards for precision and recall in threshold_output dict comprehension
- **Files modified:** xeter/scripts/calibrate.py
- **Verification:** All 86 tests pass
- **Committed in:** c18dc11 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical guard)
**Impact on plan:** Both fixes required for correctness. No scope creep.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## Next Phase Readiness

- Phase 8 (no-tool rewrite) can use `calibrate.py --flag-type no_tool` for isolated calibration runs
- Phase 9 only needs to add `"tool_use_violation"` to `BINARY_FLAG_TYPES` — infrastructure already in place
- All 86 existing tests still pass; calibrate.py import is clean

---
*Phase: 07-wrong-args-rewrite*
*Completed: 2026-04-06*

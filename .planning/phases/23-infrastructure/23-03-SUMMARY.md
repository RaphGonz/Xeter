---
phase: 23-infrastructure
plan: 03
subsystem: infra
tags: [calibrate, registry, routing, recall-floor, tdd, python]

# Dependency graph
requires:
  - phase: 23-infrastructure
    plan: 01
    provides: SpanData fields and calibrate.py build_span_data() foundation
provides:
  - FLAG_TYPE_TO_ANALYZER_CLASS registry at module level in calibrate.py
  - evaluate_flag_type() routes to analyzer class via registry lookup (not hardcoded)
  - _check_recall_floor() helper function blocking degenerate P=1.0, R=0.0 convergence
  - main() loop calls _check_recall_floor() after each hill_climb()
  - 10 tests in xeter/tests/test_calibrate_routing.py
affects:
  - 24-structural-checks (can add new analyzer class to registry without touching evaluate_flag_type)
  - 25-semantic-checks (same registry extension point)
  - 26-response-anomaly (same)
  - 27-trace-checks (same)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Static registry dict[str, type] for analyzer class routing (D-05)
    - Module-level import replaces deferred inline import inside function body
    - Extracted helper function (_check_recall_floor) for testable side-effectful guard
    - TDD: RED commit (ImportError on FLAG_TYPE_TO_ANALYZER_CLASS) then GREEN commit

key-files:
  created:
    - xeter/tests/test_calibrate_routing.py
  modified:
    - xeter/scripts/calibrate.py

key-decisions:
  - "D-05: Static registry FLAG_TYPE_TO_ANALYZER_CLASS dict[str, type] at module level — all 7 existing flag types map to ToolCallAnalyzer (zero behavior change)"
  - "D-06: All existing flag types continue to map to ToolCallAnalyzer in the registry"
  - "D-07: evaluate_flag_type() uses FLAG_TYPE_TO_ANALYZER_CLASS[flag_type] for instantiation"
  - "D-08: Recall floor enforced via _check_recall_floor() helper; sys.exit(1) with human-readable message when best_recall < 0.10"

# Metrics
duration: 20min
completed: 2026-05-20
---

# Phase 23 Plan 03: Analyzer Registry and Recall Floor Summary

**FLAG_TYPE_TO_ANALYZER_CLASS registry added to calibrate.py replacing hardcoded ToolCallAnalyzer instantiation in evaluate_flag_type(); recall floor guard (_check_recall_floor) blocks degenerate P=1.0 R=0.0 convergence; 10 tests pass**

## Performance

- **Duration:** 20 min
- **Started:** 2026-05-20T19:33:00Z
- **Completed:** 2026-05-20T19:53:02Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 1 (+ 1 created)

## Accomplishments

- Added `from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer` at module level (moved from inside `evaluate_flag_type()`)
- Added `FLAG_TYPE_TO_ANALYZER_CLASS: dict[str, type]` immediately after `FLAG_TYPE_ALIAS` with all 7 flag types mapped to `ToolCallAnalyzer`
- Replaced the two hardcoded lines in `evaluate_flag_type()` (`from ... import ToolCallAnalyzer` + `analyzer = ToolCallAnalyzer(...)`) with `analyzer_cls = FLAG_TYPE_TO_ANALYZER_CLASS[flag_type]` + `analyzer = analyzer_cls(embedder, thresholds)`
- Added `_check_recall_floor(flag_type, best_recall)` helper function that prints `RECALL FLOOR ERROR` and calls `sys.exit(1)` when `best_recall < 0.10`
- Wired `_check_recall_floor()` into main()'s calibration loop immediately after `hill_climb()` returns and before `calibrated[flag_type] = best_threshold`
- Created `xeter/tests/test_calibrate_routing.py` with 10 tests covering registry content (1-4), no inline import (5), registry monkeypatching (6), and recall floor boundary conditions (7-10)
- All 10 tests pass

## Task Commits

Each task was committed atomically following TDD RED → GREEN sequence:

1. **Task 1 RED: Failing tests for FLAG_TYPE_TO_ANALYZER_CLASS registry** - `3d15b2e` (test)
2. **Task 1 GREEN: Add registry and update evaluate_flag_type routing** - `532d188` (feat)
3. **Task 2: Recall floor guard in main()** - `b7d2bc5` (feat)
4. **Task 2: Recall floor tests 7-10** - `5cff94f` (test)

## Files Created/Modified

- `xeter/scripts/calibrate.py` — module-level ToolCallAnalyzer import, FLAG_TYPE_TO_ANALYZER_CLASS registry, evaluate_flag_type() registry lookup, _check_recall_floor() helper, main() recall floor call
- `xeter/tests/test_calibrate_routing.py` — 10 tests: 6 for registry (tests 1-6), 4 for recall floor (tests 7-10)

## Decisions Made

- **D-05:** Static registry dict — avoids modifying evaluate_flag_type() when adding new analyzer classes in phases 24-27
- **D-06:** All 7 existing flag types → ToolCallAnalyzer; zero behavior change from before
- **D-07:** evaluate_flag_type() uses `FLAG_TYPE_TO_ANALYZER_CLASS[flag_type]`; KeyError on unknown type is acceptable (main() already validates flag_type before calling evaluate_flag_type)
- **D-08:** recall floor = 0.10; exact boundary (best_recall == 0.10) is acceptable (not below floor); sys.exit(1) with RECALL FLOOR ERROR message containing flag_type and recall value
- **Helper extraction:** `_check_recall_floor()` extracted to standalone function so tests can call it directly without mocking main()'s full dependency chain (httpx, EmbedderClient, fixture loading)

## Deviations from Plan

**1. [Rule 2 - Missing critical functionality] Extracted _check_recall_floor() helper**

- **Found during:** Task 2 test design
- **Issue:** The plan suggested testing main()'s recall floor by mocking hill_climb and running the full main() loop, or by extracting a helper. Testing through main() requires mocking httpx, EmbedderClient, load_fixture, parse_args — brittle and complex. The plan explicitly offered option (a) "extract the recall floor logic into a small helper function".
- **Fix:** Added `_check_recall_floor(flag_type, best_recall)` at module level. main() calls this helper. Tests call the helper directly — no main() plumbing needed. This is cleaner and directly tests the actual implementation code.
- **Files modified:** xeter/scripts/calibrate.py, xeter/tests/test_calibrate_routing.py
- **Commits:** b7d2bc5, 5cff94f

**2. [Rule 3 - Blocking issue] Tests 7-10 initially wrote inline duplicate logic**

- **Found during:** Task 2 test writing
- **Issue:** The original test helper `_run_recall_floor_from_source` duplicated the recall floor conditional inline rather than calling the actual calibrate.py code. If the implementation changed, tests would still pass (testing the wrong thing).
- **Fix:** Rewrote tests 7-10 to call `_check_recall_floor()` from `xeter.scripts.calibrate` directly. Tests now exercise the real implementation.
- **Commits:** 5cff94f (included in test rewrite)

## Issues Encountered

None blocking. The two deviations above improved test quality and are documented as expected plan-directed choices.

## User Setup Required

None — no external service configuration required.

## Known Stubs

None — all code is fully wired. FLAG_TYPE_TO_ANALYZER_CLASS is used in evaluate_flag_type(). _check_recall_floor() is called in main(). Tests exercise real code paths.

## Threat Flags

No new network endpoints, auth paths, or trust boundaries introduced. Threat T-23-03-01 (registry dict) accepted per plan threat model (developer-facing, code-reviewed). Threat T-23-03-02 (sys.exit in CI) accepted per plan threat model (by design).

## Self-Check

**Files exist:**
- xeter/scripts/calibrate.py: FOUND
- xeter/tests/test_calibrate_routing.py: FOUND

**Commits exist:**
- 3d15b2e: FOUND
- 532d188: FOUND
- b7d2bc5: FOUND
- 5cff94f: FOUND

**Test run:** 10 passed, 0 failed

## Self-Check: PASSED

## Next Phase Readiness

- Phase 23 is complete — all 3 plans done
- Phases 24-27 can extend FLAG_TYPE_TO_ANALYZER_CLASS with new analyzer classes without modifying evaluate_flag_type()
- The recall floor guard protects calibration quality in all future phases

---
*Phase: 23-infrastructure*
*Completed: 2026-05-20*

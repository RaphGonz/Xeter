---
phase: 24-structural-span-checks
plan: "03"
subsystem: worker/calibration/wiring
tags: [wiring, registry, calibration, output-schema, span-analyzer]
dependency_graph:
  requires:
    - 24-02 (OutputSchemaAnalyzer class — created in GREEN phase)
  provides:
    - Worker bootstrap wired to OutputSchemaAnalyzer with context_overflow threshold
    - calibrate.py 4 registries extended (12-key FLAG_TYPES + FLAG_TYPE_TO_ANALYZER_CLASS, 7-key BINARY_FLAG_TYPES, 6-key DEFAULT_THRESHOLDS)
    - test_calibrate_routing.py updated to 15 tests covering post-Phase-24 12-key registry
  affects:
    - xeter/services/worker/main.py
    - xeter/scripts/calibrate.py
    - xeter/tests/test_calibrate_routing.py
tech_stack:
  added: []
  patterns:
    - Pure registration wiring — no new logic, no new classes
    - WORKER_THRESHOLD_* env var convention applied to WORKER_THRESHOLD_CONTEXT_OVERFLOW
    - BINARY_FLAG_TYPES set pattern for deterministic (non-threshold) checks
    - FLAG_TYPE_TO_ANALYZER_CLASS open registry pattern (established Phase 23)
key_files:
  created: []
  modified:
    - xeter/services/worker/main.py
    - xeter/scripts/calibrate.py
    - xeter/tests/test_calibrate_routing.py
decisions:
  - D-03 applied: WORKER_THRESHOLD_CONTEXT_OVERFLOW defaults to "8000" (string → float coercion)
  - D-05 applied: 4 binary schema checks in BINARY_FLAG_TYPES; context_overflow excluded (threshold-tunable)
  - WORKER_THRESHOLD_CONTEXT_OVERFLOW naming follows SCREAMING_SNAKE WORKER_THRESHOLD_* convention
metrics:
  duration: "10 minutes"
  completed: "2026-05-21"
  tasks_completed: 3
  files_changed: 3
---

# Phase 24 Plan 03: OutputSchemaAnalyzer Wiring Summary

## One-liner

OutputSchemaAnalyzer wired into the worker ANALYZERS list and all 4 calibrate.py registries — 5 Phase 24 flag types reachable end-to-end with 15 routing tests passing.

## What Was Built

Modified three files to complete Phase 24 wiring — no new classes, no new logic; pure registration so the OutputSchemaAnalyzer class (created in 24-02) is now reachable from both the worker process and the calibration harness.

### Task 1: xeter/services/worker/main.py

- Added `from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer` import after ToolCallAnalyzer import
- Extended THRESHOLDS dict with `"context_overflow": float(os.environ.get("WORKER_THRESHOLD_CONTEXT_OVERFLOW", "8000"))` as the 6th entry (D-03 default, SCREAMING_SNAKE env var convention)
- Extended ANALYZERS list from `[ToolCallAnalyzer(embedder, THRESHOLDS)]` to a 2-element list including `OutputSchemaAnalyzer(embedder, THRESHOLDS)`

### Task 2: xeter/scripts/calibrate.py

- Added `from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer` import
- Extended FLAG_TYPES from 7 to 12 entries (5 new: output_schema_violation, required_fields_missing, output_truncated, type_coercion_error, context_overflow)
- Extended FLAG_TYPE_TO_ANALYZER_CLASS from 7 to 12 entries (all 5 new → OutputSchemaAnalyzer; 7 existing → ToolCallAnalyzer unchanged)
- Extended BINARY_FLAG_TYPES from 3 to 7 entries (4 new binary Phase 24 schema checks; context_overflow correctly excluded per D-05)
- Extended DEFAULT_THRESHOLDS from 5 to 6 entries (`context_overflow: 8000` added as final entry)

### Task 3: xeter/tests/test_calibrate_routing.py

- Renamed test_1 to `test_1_registry_has_exactly_12_keys` (assert == 12, not 7)
- Renamed test_2 to `test_2_existing_7_keys_still_map_to_tool_call_analyzer` (iterates 7 known ToolCallAnalyzer keys; not all-values assertion)
- Tests 3-10 unchanged (still valid post-Phase-24)
- Added test_11 through test_15 covering all Phase 24 routing assertions

### Test Results

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| test_calibrate_routing.py | 10 passed | 15 passed | +5 |
| test_worker_loop.py | 6 passed | 6 passed | 0 |
| Full suite (xeter/tests/) | 197 passed, 9 skipped, 13 pre-existing failures | 197 passed, 9 skipped, 13 pre-existing failures | 0 regressions |

## Commits

| Hash | Message |
|------|---------|
| f4a277b | feat(24-03): wire OutputSchemaAnalyzer into worker main.py |
| bae51f6 | feat(24-03): extend calibrate.py registries with 5 Phase 24 flag types |
| 50af312 | feat(24-03): update test_calibrate_routing.py — 12-key registry + 5 Phase 24 routing tests |

## Deviations from Plan

None — plan executed exactly as written. All three tasks completed in sequence without auto-fixes needed.

## Known Stubs

None. All registrations are fully wired. OutputSchemaAnalyzer is now instantiated on every worker start and its 5 flag types are reachable from calibrate.py.

## Threat Flags

None. This plan performs pure registration with no new API endpoints, no new auth paths, and no new trust boundaries. T-24-10 (WORKER_THRESHOLD_CONTEXT_OVERFLOW env var → float() type coercion) is mitigated: the float() call will raise ValueError on malformed input, causing fail-fast worker startup.

## Self-Check: PASSED

- `xeter/services/worker/main.py` import exists: FOUND (OutputSchemaAnalyzer import on line 45)
- `xeter/services/worker/main.py` THRESHOLDS has 6 entries: VERIFIED (len == 6, context_overflow == 8000.0)
- `xeter/services/worker/main.py` ANALYZERS has 2 entries: VERIFIED (ToolCallAnalyzer + OutputSchemaAnalyzer)
- `xeter/scripts/calibrate.py` FLAG_TYPES has 12 entries: VERIFIED
- `xeter/scripts/calibrate.py` FLAG_TYPE_TO_ANALYZER_CLASS has 12 entries: VERIFIED (set(keys) == set(FLAG_TYPES))
- `xeter/scripts/calibrate.py` BINARY_FLAG_TYPES has 7 entries: VERIFIED (context_overflow excluded)
- `xeter/scripts/calibrate.py` DEFAULT_THRESHOLDS has 6 entries: VERIFIED (context_overflow == 8000)
- `xeter/tests/test_calibrate_routing.py` has 15 tests: VERIFIED (15 passed)
- Commit f4a277b exists: FOUND
- Commit bae51f6 exists: FOUND
- Commit 50af312 exists: FOUND
- Full suite regression check: 13 pre-existing failures unchanged, 0 new failures

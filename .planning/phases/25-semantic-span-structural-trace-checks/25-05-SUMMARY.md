---
phase: 25-semantic-span-structural-trace-checks
plan: "05"
subsystem: worker-calibration-wiring
tags: [wiring, calibration, trace-analyzer, semantic-span-analyzer, phase25]
dependency_graph:
  requires:
    - 25-03  # SemanticSpanAnalyzer implementation
    - 25-04  # TraceAnalyzer implementation
  provides:
    - SemanticSpanAnalyzer wired into worker ANALYZERS list
    - TraceAnalyzer reachable via calibrate.py evaluate_flag_type()
    - 18-entry FLAG_TYPE_TO_ANALYZER_CLASS with correct routing for all Phase 25 types
  affects:
    - xeter/services/worker/main.py
    - xeter/scripts/calibrate.py
    - xeter/tests/test_calibrate_routing.py
tech_stack:
  added: []
  patterns:
    - isinstance(analyzer, BaseTraceAnalyzer) branch to route analyze([span]) vs analyze(span)
    - float(os.environ.get(...)) pattern for all 6 new THRESHOLDS entries
key_files:
  created: []
  modified:
    - xeter/services/worker/main.py
    - xeter/scripts/calibrate.py
    - xeter/tests/test_calibrate_routing.py
decisions:
  - "evaluate_flag_type() uses isinstance(analyzer, BaseTraceAnalyzer) inline branch (not a separate function) — minimal diff, preserves existing call sites"
  - "No entries added to BINARY_FLAG_TYPES (D-12) — Phase 27 decides after full calibration dataset exists"
  - "SemanticSpanAnalyzer appended as 3rd entry in ANALYZERS list — TraceAnalyzer construction unchanged"
metrics:
  duration: "~15 minutes"
  completed: "2026-05-24"
  tasks_completed: 3
  files_modified: 3
---

# Phase 25 Plan 05: Worker + Calibration Wiring Summary

**One-liner:** SemanticSpanAnalyzer wired into ANALYZERS; 18-entry calibrate.py registry with BaseTraceAnalyzer isinstance fix; 21 routing tests pass.

## What Was Built

All 6 Phase 25 flag types are now reachable end-to-end from both the worker process and the calibration harness.

### Task 1 — main.py (commit 63e5736)

Three additive edits to `xeter/services/worker/main.py`:

1. Added `from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer` after the `OutputSchemaAnalyzer` import.
2. Added 6 new THRESHOLDS entries (D-11 starting values, all using `float(os.environ.get(...))` pattern, no bare numeric literals):
   - `missing_details`: 0.6 (hybrid cosine)
   - `stale_context`: 85.0 (rapidfuzz ratio, 0-100 scale)
   - `context_propagation_failure`: 0.5 (hybrid cosine)
   - `history_loss`: 0.4 (embedding cosine)
   - `step_repetition`: 85.0 (rapidfuzz token_sort_ratio)
   - `termination_loop_n`: 3 (consecutive count threshold)
3. Extended ANALYZERS list from 2 to 3 entries by appending `SemanticSpanAnalyzer(embedder, THRESHOLDS)`.

THRESHOLDS now has 12 keys. TraceAnalyzer construction on its own line is unchanged.

### Task 2 — calibrate.py (commit e9533cb)

Five additive changes to `xeter/scripts/calibrate.py`:

1. Added 3 new imports: `SemanticSpanAnalyzer`, `TraceAnalyzer`, `BaseTraceAnalyzer`.
2. Extended FLAG_TYPES from 12 to 18 entries (6 new Phase 25 types).
3. Extended FLAG_TYPE_TO_ANALYZER_CLASS from 12 to 18 entries:
   - `missing_details` → SemanticSpanAnalyzer
   - `stale_context`, `step_repetition`, `termination_loop`, `context_propagation_failure`, `history_loss` → TraceAnalyzer
4. Extended DEFAULT_THRESHOLDS from 6 to 12 entries with D-11 starting values.
5. Fixed architectural bug in `evaluate_flag_type()`: added `isinstance(analyzer, BaseTraceAnalyzer)` branch that calls `analyzer.analyze([span])` (wrapping single SpanData in a list) when the analyzer is a trace-level analyzer, preserving existing `analyzer.analyze(span)` path for span-level analyzers.

BINARY_FLAG_TYPES unchanged — 7 entries (D-12).

### Task 3 — test_calibrate_routing.py (commit cadfd04)

Updated `xeter/tests/test_calibrate_routing.py` from 15 to 21 tests:

1. Renamed `test_1_registry_has_exactly_12_keys` → `test_1_registry_has_exactly_18_keys` (assert len == 18).
2. Renamed `test_15_flag_types_list_has_12_entries` → `test_15_flag_types_list_has_18_entries` (assert len == 18; added all 6 Phase 25 types to in-list assertions).
3. Added 6 new tests:
   - test_16: `missing_details` → SemanticSpanAnalyzer routing
   - test_17: all 5 trace flag types → TraceAnalyzer routing
   - test_18: Phase 25 DEFAULT_THRESHOLDS keys present with correct D-11 values
   - test_19: No Phase 25 type in BINARY_FLAG_TYPES (D-12 enforcement)
   - test_20: `evaluate_flag_type` source contains BaseTraceAnalyzer isinstance branch
   - test_21: `set(registry.keys()) == set(FLAG_TYPES)` — no drift

All 21 tests pass. Full suite: 235 passed, 13 pre-existing spaCy env failures, 0 new failures.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 63e5736 | feat(25-05): wire SemanticSpanAnalyzer into ANALYZERS + 6 new THRESHOLDS entries |
| 2 | e9533cb | feat(25-05): update calibrate.py — 18-entry registry + TraceAnalyzer evaluation fix |
| 3 | cadfd04 | test(25-05): update routing tests — 21 tests covering all Phase 25 flag types |

## Deviations from Plan

None — plan executed exactly as written.

The plan anticipated the TraceAnalyzer type error as an "architectural alert" and provided the exact fix approach (`isinstance(analyzer, BaseTraceAnalyzer)` branch). This was applied as specified.

## Known Stubs

None. All 6 Phase 25 flag types are fully wired:
- `missing_details` → SemanticSpanAnalyzer (fully implemented in Plan 25-03)
- `stale_context`, `step_repetition`, `termination_loop`, `context_propagation_failure`, `history_loss` → TraceAnalyzer (fully implemented in Plan 25-04)

The only deferral is calibration thresholds — starting values from D-11 are in place; actual calibrated values await Phase 27.

## Threat Flags

None. No new network endpoints, auth paths, or schema changes introduced. The `isinstance(analyzer, BaseTraceAnalyzer)` branch is a pure routing decision with no privilege escalation (T-25-05-02: accepted per threat model).

## Self-Check: PASSED

- xeter/services/worker/main.py: FOUND and verified (12 THRESHOLDS keys, 3 ANALYZERS, SemanticSpanAnalyzer import)
- xeter/scripts/calibrate.py: FOUND and verified (18 FLAG_TYPES, 18 registry entries, 12 DEFAULT_THRESHOLDS, isinstance branch)
- xeter/tests/test_calibrate_routing.py: FOUND and verified (21 tests, all pass)
- Commit 63e5736: FOUND
- Commit e9533cb: FOUND
- Commit cadfd04: FOUND

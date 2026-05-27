---
phase: 27-calibration-pass
plan: 01
subsystem: calibration
tags: [fixture, calibration, trace-evaluation, phase-24, phase-25, phase-26]
dependency_graph:
  requires: []
  provides:
    - fixtures/labelled_spans.jsonl extended with 17 new flag types
    - generate_labelled_fixture.py with 17 new builder functions
    - calibrate.py with TRACE_LEVEL_TYPES grouped evaluation path
  affects:
    - xeter/scripts/calibrate.py (evaluate_flag_type, new constants)
    - xeter/scripts/generate_labelled_fixture.py (new builders, generate_new_type_spans)
    - fixtures/labelled_spans.jsonl (100 → 738 rows)
tech_stack:
  added: []
  patterns:
    - Separate rng instance (NEW_SEED=27) keeps existing fixture rows stable
    - Trace-level builders return list[dict] sharing trace_id; last row carries label
    - group_spans_by_trace() groups by trace_id preserving insertion order
    - CALIBRATION_ROUTING_GRAPH injected at TraceAnalyzer instantiation for wrong_agent_handoff
key_files:
  created: []
  modified:
    - xeter/scripts/generate_labelled_fixture.py
    - fixtures/labelled_spans.jsonl
    - xeter/scripts/calibrate.py
decisions:
  - "NEW_SEED=27 rng instance separate from SEED=42 ensures existing 100 rows are byte-identical on regeneration"
  - "Trace-level builders return list[dict] not dict — uniform interface via isinstance check in generate_new_type_spans"
  - "_apply_defaults() centralises default field population for all new rows; span_id assigned if builder did not set one"
  - "TRACE_LEVEL_TYPES excludes clarification_skipped (syntactic, single-span) and missing_details (SemanticSpanAnalyzer)"
  - "group_spans_by_trace uses stdlib dict+list (no itertools) — no new module imports"
  - "CALIBRATION_ROUTING_GRAPH hardcoded as calibration constant — matches fixture topology; accepted as T-27-01-02"
metrics:
  duration_minutes: 25
  completed_date: "2026-05-27"
  tasks_completed: 2
  files_modified: 3
---

# Phase 27 Plan 01: Fixture Extension and Calibrator Trace Grouping Summary

Fixture generator and calibration evaluator extended so all 17 new flag types (Phases 24/25/26) have labelled calibration data and can be evaluated without errors. The `fixtures/labelled_spans.jsonl` file grew from 100 rows to 738 rows covering all 17 new types with ≥8 flagged groups each. The `calibrate.py` evaluator now routes trace-level types through a grouped evaluation path, enabling recall > 0 for all multi-span checks.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend generate_labelled_fixture.py with 17 new span-builder functions | 5a71f15 | xeter/scripts/generate_labelled_fixture.py, fixtures/labelled_spans.jsonl |
| 2 | Update evaluate_flag_type() in calibrate.py to support multi-span trace groups | 6b81442 | xeter/scripts/calibrate.py |

## What Was Built

**Task 1 — Fixture Generator Extension:**
- Added `NEW_SEED = 27` constant; separate `rng_new = random.Random(NEW_SEED)` used by all new builders
- 6 span-level builder functions: `make_output_schema_violation_span`, `make_required_fields_missing_span`, `make_output_truncated_span`, `make_type_coercion_error_span`, `make_context_overflow_span`, `make_missing_details_span`
- 11 trace-level builder functions returning `list[dict]` with shared `trace_id`: `make_stale_context_spans`, `make_step_repetition_spans`, `make_termination_loop_spans`, `make_context_propagation_failure_spans`, `make_history_loss_spans`, `make_wrong_agent_handoff_spans`, `make_information_withholding_spans`, `make_conversation_reset_spans`, `make_clarification_skipped_spans`, `make_no_verification_spans`, `make_incomplete_verification_spans`
- `_apply_defaults()` helper normalises all new rows (assigns span_id, trace_id, SpanData field defaults)
- `generate_new_type_spans()` orchestrates 8 flagged + 8 clean groups per type via `_NEW_TYPE_BUILDERS` table
- `main()` extended to call `generate_new_type_spans()` and append to existing spans before shuffle

**Task 2 — Calibrator Trace Grouping:**
- `TRACE_LEVEL_TYPES: frozenset[str]` — 10 entries for checks requiring multi-span context
- `CALIBRATION_ROUTING_GRAPH: dict[str, list[str]]` — hardcoded calibration routing topology matching fixture
- `group_spans_by_trace(spans)` — groups rows by `trace_id`, preserves insertion order, stdlib only
- `evaluate_flag_type()` — new `TRACE_LEVEL_TYPES` branch: calls `group_spans_by_trace()`, feeds full group to `analyzer.analyze()`, uses last row's label for TP/FP/FN counting, attaches `last_row.span_id` to FP/FN diagnostic records
- `wrong_agent_handoff` special case: instantiates `TraceAnalyzer(embedder, thresholds, routing_graph=CALIBRATION_ROUTING_GRAPH)`
- All 27 `test_calibrate_routing.py` tests pass (no regression)

## Verification Results

- `python xeter/scripts/generate_labelled_fixture.py` exits 0, prints "Written 738 spans"
- All 17 new flag types have ≥8 flagged rows in fixture (minimum 5 required)
- `python -m pytest xeter/tests/test_calibrate_routing.py -q` — 27 passed, 0 failed
- `from xeter.scripts.calibrate import TRACE_LEVEL_TYPES, CALIBRATION_ROUTING_GRAPH, group_spans_by_trace` — imports OK
- All 17 types present in fixture: verified via set assertion

## Deviations from Plan

**1. [Rule 1 - Bug] Rows missing span_id in generate_new_type_spans()**
- **Found during:** Task 1 verification
- **Issue:** New builder functions set span_id inside trace-group rows via string templates, but the `generate_new_type_spans()` function did not guarantee span_id assignment for rows that didn't set it themselves. 112 rows were written without `span_id`.
- **Fix:** Extracted `_apply_defaults()` helper that assigns `span_id = f"new-{flag_type}-g{group_idx:04d}-{row_idx}"` when not already set by builder. Builder-set IDs (e.g. `new-stale-ctx-0000-1`) take priority.
- **Files modified:** xeter/scripts/generate_labelled_fixture.py
- **Commit:** 5a71f15

**2. [Rule 2 - Info] Plan acceptance test uses wrong span_id format**
- The plan's acceptance criteria test checks `r['span_id']=='clean-001'` (3-digit format) but the actual fixture uses `clean-0001` (4-digit format from the original generator). The original rows are preserved correctly — this is a documentation inconsistency in the plan, not a code issue.
- Verified: `len([r for r in rows if r.get('span_id')=='clean-0001']) == 1` passes.

## Known Stubs

None — all 17 flag types have real test data in the fixture; no placeholder spans.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. The `CALIBRATION_ROUTING_GRAPH` constant is developer-authored calibration data (T-27-01-02, accepted).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| fixtures/labelled_spans.jsonl | FOUND |
| xeter/scripts/generate_labelled_fixture.py | FOUND |
| xeter/scripts/calibrate.py | FOUND |
| .planning/phases/27-calibration-pass/27-01-SUMMARY.md | FOUND |
| Commit 5a71f15 (Task 1) | FOUND |
| Commit 6b81442 (Task 2) | FOUND |

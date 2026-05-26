---
phase: 26-best-effort-proxy-checks
plan: "01"
type: tdd
subsystem: worker/trace-analyzer
tags: [tdd, red, trace-analyzer, phase26]
dependency_graph:
  requires: []
  provides: [test-scaffold-26-checks]
  affects: [xeter/tests/worker/test_trace_analyzer_phase26.py]
tech_stack:
  added: []
  patterns: [tdd-red-scaffold, _make_trace_analyzer-helper, spacy-mock-pattern]
key_files:
  created:
    - xeter/tests/worker/test_trace_analyzer_phase26.py
  modified: []
decisions:
  - "_make_trace_analyzer helper extended with routing_graph=None param and 11 threshold keys (5 Phase 25 + 6 Phase 26) matching the planned GREEN interface"
  - "Tests fail with TypeError (unexpected routing_graph kwarg) — correct RED failure mode confirming method absence, not import/collection error"
  - "mutual-exclusion test (test_no_verification_and_incomplete_verification_never_both_fire) verifies D-12 contract"
  - "spaCy patching pattern uses patch('xeter.services.worker.trace_analyzer._get_spacy') with side_effect for per-call doc mocks"
metrics:
  duration: "~24 minutes"
  completed: "2026-05-26"
  tasks_completed: 1
  files_created: 1
  files_modified: 0
---

# Phase 26 Plan 01: RED Test Scaffold for 6 Best-Effort Proxy Checks

**One-liner:** 30-test RED scaffold defining the exact contract for TRACE-05 through TRACE-10 — all tests fail with TypeError on routing_graph kwarg, import clean.

## What Was Built

Created `xeter/tests/worker/test_trace_analyzer_phase26.py` — a new test file establishing the behavioral contract for all 6 Phase 26 TraceAnalyzer checks before any implementation exists.

The file contains:
- **30 failing tests** across 6 check groups (TRACE-05 through TRACE-10)
- **`_make_spans` helper** — copied verbatim from Phase 25 test file
- **`_make_trace_analyzer` helper** — extended with `routing_graph=None` param and all 11 threshold keys (5 Phase 25 + 6 Phase 26)
- **Mutual exclusion test** — `test_no_verification_and_incomplete_verification_never_both_fire` verifying D-12
- **6 `low_confidence` references** (assertions for TRACE-05, TRACE-07, TRACE-08)

## Test Groups

| Group | Check | Tests | RED Reason |
|-------|-------|-------|-----------|
| TRACE-05 | wrong_agent_handoff | 5 (fires/no-flag ×3, low_confidence, same-agent) | TypeError: routing_graph kwarg |
| TRACE-06 | information_withholding | 4 (fires, no-flag ×2, logs_score) | TypeError: routing_graph kwarg |
| TRACE-07 | conversation_reset | 5 (fires, no-flag, guard, low_confidence, logs_score) | TypeError: routing_graph kwarg |
| TRACE-08 | clarification_skipped | 5 (fires ×2, no-flag ×2, low_confidence) | TypeError: routing_graph kwarg |
| TRACE-09 | no_verification | 5 (fires, no-flag ×3, case-insensitive) | TypeError: routing_graph kwarg |
| TRACE-10 | incomplete_verification | 5 (fires, no-flag, skipped-mutual-excl, never-both-fire, logs_score) | TypeError: routing_graph kwarg |

## Verification Results

```
30 tests collected in 0.48s  (collection: exit 0, 0 errors)
30 failed in 0.57s           (all fail RED — TypeError on routing_graph kwarg)
```

Pre-existing suite: 13 failures, 235 passed, 9 skipped — unchanged by this plan.

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write RED test scaffold for all 6 Phase 26 checks | 05e87f7 | xeter/tests/worker/test_trace_analyzer_phase26.py |

## Deviations from Plan

None — plan executed exactly as written.

The test count of 30 meets the 30+ minimum (plan spec: acceptance criterion says "30+ test items"). The extra test added (`test_wrong_agent_handoff_same_agent_consecutive_no_flag`) covers the edge case where the same agent appears consecutively — not a handoff transition, should not fire.

## TDD Gate Compliance

- RED gate: `test(26-01)` commit present at 05e87f7
- GREEN gate: pending (26-02-PLAN.md)
- REFACTOR gate: not applicable to RED phase

## Known Stubs

None — this is a pure test file; no stub data flows to UI rendering.

## Threat Flags

None — test file only; no new network endpoints, auth paths, or schema changes.

## Self-Check: PASSED

- xeter/tests/worker/test_trace_analyzer_phase26.py: FOUND
- .planning/phases/26-best-effort-proxy-checks/26-01-SUMMARY.md: FOUND
- Commit 05e87f7: FOUND

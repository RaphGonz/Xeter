---
phase: 08-wrong-tool-rewrite
plan: "01"
subsystem: worker
tags: [wrong_tool, threshold-rename, three-branch-logic, hybrid-score, wtool]
dependency_graph:
  requires: []
  provides: [wrong_tool_called threshold key, three-branch _check_wrong_tool, 4 new unit tests]
  affects: [tool_call_analyzer.py, main.py, calibrate.py, docker-compose.yml, calibrated_thresholds.json]
tech_stack:
  added: []
  patterns: [three-branch detection, hybrid scoring (cosine + BOW), immediate flag without embed call]
key_files:
  created: []
  modified:
    - xeter/services/worker/tool_call_analyzer.py
    - xeter/services/worker/main.py
    - xeter/scripts/calibrate.py
    - deploy/docker-compose.yml
    - fixtures/calibrated_thresholds.json
    - xeter/tests/worker/test_tool_call_analyzer.py
decisions:
  - "Three-branch logic replaces old inverted AND gate: no_available_tools (immediate), better tool existed (Case B), no appropriate tool (Case C)"
  - "Threshold key renamed wrong_tool -> wrong_tool_called across all 6 affected files"
  - "Env var renamed WORKER_THRESHOLD_WRONG_TOOL -> WORKER_THRESHOLD_WRONG_TOOL_CALLED"
  - "Hybrid score (50/50 cosine + BOW) used for tool ranking per WTOOL-04"
metrics:
  duration: "12min"
  completed_date: "2026-04-07"
  tasks_completed: 2
  files_modified: 6
---

# Phase 8 Plan 01: Wrong Tool Rewrite Summary

**One-liner:** Three-branch `_check_wrong_tool` with hybrid scoring and `wrong_tool_called` threshold key replacing old inverted AND gate across 6 files.

## What Was Built

Rewrote `_check_wrong_tool` in `ToolCallAnalyzer` to use three-branch single-threshold logic:

1. **Case A (WTOOL-03):** Tool called but `available_tools` is `None` or `[]` — immediate flag (`score=1.0`), no embedding call made.
2. **Case B:** `top1_tool != called_tool` AND `top1_score >= threshold` — a better tool existed; flag with `top1_score`.
3. **Case C:** `top1_score < threshold` — no tool was appropriate for the prompt; flag with `top1_score`.
4. **Correct case:** `top1_tool == called_tool` AND `top1_score >= threshold` — no flag.

Scoring uses 50/50 cosine + BOW hybrid (`hybrid_score`) per WTOOL-04. The `top1_score` is always the reported `flag.score` (WTOOL-02).

## Threshold Key Rename

Renamed `"wrong_tool"` → `"wrong_tool_called"` in:

| File | Change |
|------|--------|
| `xeter/services/worker/tool_call_analyzer.py` | `_thresholds["wrong_tool_called"]` lookup |
| `xeter/services/worker/main.py` | `THRESHOLDS` dict key + `WORKER_THRESHOLD_WRONG_TOOL_CALLED` env var |
| `xeter/scripts/calibrate.py` | `FLAG_TYPES`, `DEFAULT_THRESHOLDS`, `key_to_env` dict |
| `deploy/docker-compose.yml` | `WORKER_THRESHOLD_WRONG_TOOL_CALLED: "0.5"` |
| `fixtures/calibrated_thresholds.json` | `"wrong_tool_called": 0.5` |
| `xeter/tests/worker/test_tool_call_analyzer.py` | `DEFAULT_THRESHOLDS` + inline overrides |

## New Tests Added

4 new tests added after existing wrong_tool tests:

| Test | Covers |
|------|--------|
| `test_wrong_tool_immediate_flag_no_available_tools` | WTOOL-03 None case — no embed call |
| `test_wrong_tool_immediate_flag_empty_available_tools` | WTOOL-03 empty list case — no embed call |
| `test_wrong_tool_score_is_top1_hybrid` | WTOOL-02 — flag.score is top1 hybrid, not sentinel |
| `test_wrong_tool_no_flag_correct_tool_above_threshold` | WTOOL-01 correct case — no flag |

## Verification Results

- All 30 `test_tool_call_analyzer.py` tests pass (26 original + 4 new)
- Full worker test suite: 36 passed
- No stale `"wrong_tool"` threshold key references remain (only `wrong_tool_args` and `wrong_tool_called` in threshold contexts)

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | `34fefd6` | feat(08-01): rewrite _check_wrong_tool and rename threshold key to wrong_tool_called |
| Task 2 | `3fb1852` | test(08-01): add 4 new test cases for three-branch wrong_tool logic |

## Self-Check: PASSED

- `xeter/services/worker/tool_call_analyzer.py` modified — contains `wrong_tool_called` threshold lookup at line 191
- `xeter/services/worker/main.py` modified — contains `WORKER_THRESHOLD_WRONG_TOOL_CALLED`
- `xeter/scripts/calibrate.py` modified — `wrong_tool_called` in FLAG_TYPES and DEFAULT_THRESHOLDS
- `deploy/docker-compose.yml` modified — `WORKER_THRESHOLD_WRONG_TOOL_CALLED: "0.5"`
- `fixtures/calibrated_thresholds.json` modified — `"wrong_tool_called": 0.5`
- `xeter/tests/worker/test_tool_call_analyzer.py` modified — 4 new tests, 30 total pass
- Commits `34fefd6` and `3fb1852` exist on main branch

---
phase: 07-wrong-args-rewrite
plan: "03"
subsystem: worker
tags: [wrong-args, hybrid-scoring, tdd, refactor]
dependency_graph:
  requires:
    - 07-02  # bow_score and hybrid_score utilities in base.py
  provides:
    - ARGS-01  # output-error priority path (no embedding)
    - ARGS-02  # flatten argument values only (no key noise)
    - ARGS-03  # hybrid scoring for semantic mismatch
    - ARGS-04  # skip embedding when all-numeric values
    - ARGS-05  # remove low_confidence from flag detail
  affects:
    - xeter/services/worker/tool_call_analyzer.py
    - xeter/tests/worker/test_tool_call_analyzer.py
tech_stack:
  added: []
  patterns:
    - Two-path detection (error regex priority over embedding)
    - _flatten_arg_values extracts dict values only (not keys)
    - _should_skip_embedding guards empty/all-numeric text
    - hybrid_score(cosine, bow_score) for semantic mismatch path
key_files:
  created: []
  modified:
    - xeter/services/worker/tool_call_analyzer.py
    - xeter/tests/worker/test_tool_call_analyzer.py
decisions:
  - ARGS-05 removes low_confidence from flag detail; no longer excluded from calibration
  - Module-level _flatten_arg_values and _should_skip_embedding (not methods) for testability
metrics:
  duration: ~10min
  completed: "2026-04-06"
  tasks_completed: 2
  files_modified: 2
---

# Phase 7 Plan 03: wrong_args Rewrite — Detection Logic Summary

One-liner: Two-path _check_wrong_args using error-regex priority (ARGS-01) and hybrid cosine+BOW scoring on flattened arg values (ARGS-02/03/04), with low_confidence removed (ARGS-05).

## What Was Built

Replaced the old `_check_wrong_args` implementation in `ToolCallAnalyzer` with a two-path detector that fixes the core signal problems.

**Old implementation (replaced):**
- Embedded the raw JSON string (keys + values) — key names polluted cosine similarity
- Always attached `low_confidence: True` to flag detail — caused exclusion from calibration
- No error pattern check — missed obvious arg-error cases

**New implementation:**

Path 1 (ARGS-01 — error pattern priority):
- Checks `tool_output` against `_WRONG_ARGS_ERROR_PATTERNS` (13 compiled regexes)
- If any pattern matches: returns `Flag(score=1.0)` immediately — no `embed()` call
- Patterns cover: invalid argument, missing required, HTTP 4xx, validation error, etc.

Path 2 (ARGS-02/03/04 — semantic mismatch):
- `_flatten_arg_values()`: extracts dict values only (not keys) — removes key-name noise
- `_should_skip_embedding()`: skips if flattened text is empty or all-numeric/operator tokens
- Embeds flattened values and prompt, computes `hybrid_score(cosine, bow_score(...))`
- Flags if hybrid score is below `wrong_tool_args` threshold

ARGS-05: `low_confidence` removed from all flag details.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite _check_wrong_args | 638125e | xeter/services/worker/tool_call_analyzer.py |
| 2 | Update test_7 and add ARGS-01/04/05 tests | 2e0b28a | xeter/tests/worker/test_tool_call_analyzer.py |

## Test Results

All 26 tests pass:
- `test_wrong_args_flag_has_no_low_confidence` — renamed from test_7, updated assertion
- `test_wrong_args_error_pattern_fires_without_embedding` — ARGS-01 short-circuit
- `test_wrong_args_skips_all_numeric_flattened_values` — ARGS-04 numeric guard
- `test_wrong_args_no_low_confidence_in_detail` — ARGS-05 key absent

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `xeter/services/worker/tool_call_analyzer.py` — modified, contains `_WRONG_ARGS_ERROR_PATTERNS`, `_flatten_arg_values`, `_should_skip_embedding`
- `xeter/tests/worker/test_tool_call_analyzer.py` — modified, 26 tests pass
- Commit 638125e — feat(07-03): rewrite _check_wrong_args
- Commit 2e0b28a — test(07-03): update test_7 and add new tests
- `low_confidence` appears only in comments in tool_call_analyzer.py (verified with grep)

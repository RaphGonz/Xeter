---
phase: 24-structural-span-checks
plan: "02"
subsystem: worker/analyzer
tags: [tdd, implementation, output-schema, span-analyzer, green-phase, jsonschema, tiktoken]
dependency_graph:
  requires:
    - 24-01 (test scaffold — all 31 tests authored)
  provides:
    - OutputSchemaAnalyzer class with 5 deterministic span-level checks
  affects:
    - xeter/services/worker/output_schema_analyzer.py
tech_stack:
  added: []
  patterns:
    - TDD GREEN phase — all 31 RED tests now pass
    - Lazy import cache pattern (_TIKTOKEN_ENCODING / _get_tiktoken) mirroring _get_spacy
    - jsonschema.Draft7Validator.iter_errors() with e.validator filter (required / type)
    - Provider-agnostic finish_reason parsing (OpenAI choices[] / Anthropic stop_reason)
    - Unclosed-delimiter heuristic for truncation detection (end-char check, Pitfall 3 safe)
    - log_score() BEFORE threshold comparison (D-04 calibration invariant)
key_files:
  created:
    - xeter/services/worker/output_schema_analyzer.py
  modified: []
decisions:
  - D-01 sub-case A: output_schema_violation fires only on response not parseable as JSON (sub-case B deferred)
  - D-04 invariant: log_score recorded on all non-None paths before any flag decision; early guards when all fields None produce empty flush_scores
  - D-05: 4 binary checks log 0.0/1.0; context_overflow logs numeric token_count as calibration signal
  - D-06: no __init__ override — inherited (embedder, thresholds) constructor from BaseAnalyzer
  - Pitfall 3 mitigated: _has_unclosed_delimiter returns False when string ends with closing delimiter even if JSON is malformed
  - Pitfall 4 mitigated: _parse_finish_reason normalizes Anthropic stop_reason="max_tokens" to "length"
  - Auto-fix: added early guard to _check_output_truncated when raw_response+response+tool_arguments all None to satisfy D-04 invariant per test_early_guards_do_not_log_score
metrics:
  duration: "15 minutes"
  completed: "2026-05-21"
  tasks_completed: 2
  files_changed: 1
---

# Phase 24 Plan 02: OutputSchemaAnalyzer GREEN Phase Implementation Summary

## One-liner

OutputSchemaAnalyzer with 5 deterministic schema/context checks using jsonschema Draft7Validator and lazy tiktoken cl100k_base — all 31 TDD RED tests now pass.

## What Was Built

Created `xeter/services/worker/output_schema_analyzer.py` (284 lines) — the TDD GREEN phase implementation of `OutputSchemaAnalyzer`. The file implements all 5 span-level checks from Phase 24 requirements (SCHEMA-01 through CTX-01) with no embedding calls, no numeric threshold literals, and full log_score() coverage before every flag/clean decision.

### Check Implementation Summary

| Check | Method | Key Logic | Tests |
|-------|--------|-----------|-------|
| SCHEMA-01 | `_check_output_schema_violation` | early guard on schema/response None; json.loads(response) fail → flag | 5 |
| SCHEMA-02 | `_check_required_fields_missing` | Draft7Validator.iter_errors() filtered by e.validator=="required"; json.loads both strings | 4 |
| SCHEMA-03 | `_check_output_truncated` | _parse_finish_reason (OpenAI+Anthropic) OR _has_unclosed_delimiter; early guard when all 3 fields None | 7 |
| SCHEMA-04 | `_check_type_coercion_error` | Draft7Validator.iter_errors() filtered by e.validator=="type"; Flag.detail key "type_errors" | 4 |
| CTX-01 | `_check_context_overflow` | _get_tiktoken() lazy load; log_score(token_count) BEFORE threshold; self._thresholds["context_overflow"] | 5 |
| Contract | name, analyze, constructor | name=="output_schema"; analyze() dispatches all 5; no __init__ | 3 |
| log_score | D-04 invariant | 4 binary + prompt_token_count metrics logged on clean span; early guards log nothing | 3 |

### Structural Notes

- File: 284 lines — exceeds 180-line minimum
- No `__init__` override — D-06 satisfied by inheritance from BaseAnalyzer
- `_TIKTOKEN_ENCODING = None` module-level cache + `_get_tiktoken()` lazy loader mirrors `_get_spacy()` pattern
- No top-level `import tiktoken` (Pitfall 6 mitigated)
- No numeric literal `8000` anywhere in code (only in a comment explaining why)
- `jsonschema` imported at module level (no lazy load needed — fast import, no external file load)
- Two private helper methods: `_parse_finish_reason()` and `_has_unclosed_delimiter()`

## Commits

| Hash | Message |
|------|---------|
| cb35921 | feat(24-02): create OutputSchemaAnalyzer with class skeleton and SCHEMA-01/SCHEMA-03 checks |
| 2533d1d | feat(24-02): implement SCHEMA-02, SCHEMA-04, and CTX-01 checks — all 31 tests pass |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added early guard to _check_output_truncated when all span fields are None**
- **Found during:** Task 1 verification (`test_early_guards_do_not_log_score`)
- **Issue:** The plan spec described `_check_output_truncated` as "always logs a score because it always runs (no field-None early guard at the top)". However the test `test_early_guards_do_not_log_score` asserts that when raw_response, response, and tool_arguments are all None, `flush_scores()` returns `[]`. The plan description conflicted with the test specification.
- **Fix:** Added `if span.raw_response is None and span.response is None and span.tool_arguments is None: return []` at the top of `_check_output_truncated`. This correctly applies D-04 invariant: early exits (when there is no signal to examine) do not contribute to span_scores.
- **Files modified:** `xeter/services/worker/output_schema_analyzer.py`
- **Commit:** cb35921

## Known Stubs

None. All 5 check methods are fully implemented.

## Threat Flags

None. This plan creates a single new Python module with no new API endpoints, no auth paths, and no trust boundaries beyond those already documented in the plan's threat model (T-24-04 through T-24-09).

T-24-04 mitigated: json.loads on expected_output_schema wrapped in try/except in both SCHEMA-02 and SCHEMA-04; malformed input returns [] without calling Draft7Validator.

T-24-05 mitigated: _parse_finish_reason wraps json.loads in try/except; returns None on failure; _check_output_truncated tolerates None and falls through to delimiter heuristic.

## Self-Check: PASSED

- `xeter/services/worker/output_schema_analyzer.py` exists: FOUND (284 lines)
- Commit cb35921 exists: FOUND
- Commit 2533d1d exists: FOUND
- All 31 tests pass: VERIFIED (31 passed, 0 failed)
- No `__init__` override: VERIFIED
- No numeric literal 8000 in code: VERIFIED
- No top-level `import tiktoken`: VERIFIED
- `e.validator == "required"` present exactly once: VERIFIED
- `e.validator == "type"` present exactly once (in code): VERIFIED
- `_get_tiktoken()` called from `_check_context_overflow`: VERIFIED
- `self._thresholds["context_overflow"]` present: VERIFIED
- Worker test suite: 80 passed, 13 pre-existing spaCy failures (unchanged), 0 regressions

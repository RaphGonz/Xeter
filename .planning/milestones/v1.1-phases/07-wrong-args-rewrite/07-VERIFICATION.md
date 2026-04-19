---
phase: 07-wrong-args-rewrite
verified: 2026-04-06T00:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 7: wrong-args-rewrite Verification Report

**Phase Goal:** `_check_wrong_args` produces trustworthy flags backed by output error patterns and correctly-embedded argument values; shared hybrid scoring utility exists for all subsequent phases; calibration script supports binary flags and per-method runs
**Verified:** 2026-04-06
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `_check_wrong_args` error path fires (score=1.0) when tool_output matches error pattern, without calling embed() | VERIFIED | `_WRONG_ARGS_ERROR_PATTERNS` list (13 patterns), Path 1 in `_check_wrong_args` L254-263; test `test_wrong_args_error_pattern_fires_without_embedding` passes |
| 2 | `_check_wrong_args` semantic path embeds flattened arg values (not raw JSON keys+values) and scores with hybrid(cosine, BOW) | VERIFIED | `_flatten_arg_values()` extracts dict values only (L58-72); `hybrid_score(cosine, bow_score(...))` called at L274-275 |
| 3 | All-numeric / code-string flattened values are skipped without embedding | VERIFIED | `_should_skip_embedding()` guards empty, numeric, and code-syntax strings (L75-89); `test_wrong_args_skips_all_numeric_flattened_values` passes |
| 4 | No `wrong_tool_args` flag detail contains the key `low_confidence` | VERIFIED | `low_confidence` appears only in comments in `tool_call_analyzer.py` (L249, L284 comment); 2 ARGS-05 tests pass |
| 5 | `bow_score` and `hybrid_score` exist as module-level functions in `base.py`, importable and numerically correct | VERIFIED | Both defined at L139-165 of `base.py`; all 7 unit tests pass (Jaccard overlap, empty string, equal/custom weight) |
| 6 | `tool_call_analyzer.py` imports and uses `bow_score` and `hybrid_score` from `base.py` | VERIFIED | `from xeter.services.worker.base import ... bow_score, hybrid_score` at L29; both called in `_check_wrong_args` at L274-275 |
| 7 | `calibrate.py` accepts `--flag-type` CLI arg and filters to that flag type only | VERIFIED | `parse_args()` with argparse at module level; `active_flag_types` filter at L340-350; `python -c` import test passes |
| 8 | `wrong_tool_args` is in `FLAG_TYPES`; stale exclusion NOTE removed; `BINARY_FLAG_TYPES` is a `set` | VERIFIED | `FLAG_TYPES` L45-52 includes `wrong_tool_args`; no `NOTE:` print in file; `BINARY_FLAG_TYPES: set[str] = set()` at L56 |
| 9 | `calibrated_thresholds.json` contains `wrong_tool_args` threshold (0.30) with P=0.40, R=0.90 from hill-climb | VERIFIED | `fixtures/calibrated_thresholds.json` — `thresholds.wrong_tool_args = 0.3`, `per_flag_type.wrong_tool_args = {threshold: 0.3, precision: 0.4, recall: 0.9, steps: 6}` |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `xeter/scripts/calibrate.py` | `parse_args()`, `BINARY_FLAG_TYPES`, `--flag-type` filter, `wrong_tool_args` in `FLAG_TYPES`, stale NOTE removed | VERIFIED | All changes confirmed; 89 tests pass |
| `xeter/services/worker/base.py` | `bow_score()` and `hybrid_score()` module-level functions | VERIFIED | Defined L139-165; Jaccard + weighted blend; importable |
| `xeter/services/worker/tool_call_analyzer.py` | Rewritten `_check_wrong_args` with two-path detection; `_WRONG_ARGS_ERROR_PATTERNS` list | VERIFIED | Two-path detector at L236-286; 13-pattern list at L37-51; no `low_confidence` in flag detail |
| `xeter/tests/worker/test_tool_call_analyzer.py` | Updated test_7 (renamed, ARGS-05 assertion); new ARGS-01/04/05 tests; bow/hybrid unit tests | VERIFIED | 26 tests total; all pass; `test_wrong_args_flag_has_no_low_confidence` confirmed |
| `xeter/services/worker/detection_patterns.yml` | Valid YAML; `negation_motifs` + `tool_triggering_terms` sections; user-approved | VERIFIED | 10 negation motifs, 12 tool triggering terms; `yaml.safe_load` parses cleanly; hybrid detection design documented inline |
| `fixtures/calibrated_thresholds.json` | `wrong_tool_args` threshold written after hill-climb | VERIFIED | `thresholds.wrong_tool_args = 0.3`; `per_flag_type` block with P/R/steps |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tool_call_analyzer.py _check_wrong_args()` | `base.py bow_score, hybrid_score` | `from xeter.services.worker.base import bow_score, hybrid_score` | WIRED | Import at L29; `bow_score` called L274, `hybrid_score` called L275 |
| `_check_wrong_args() error path` | `_WRONG_ARGS_ERROR_PATTERNS list` | `any(p.search(span.tool_output) for p in _WRONG_ARGS_ERROR_PATTERNS)` | WIRED | Pattern present at L255-257 |
| `calibrate.py main()` | `active_flag_types list` | `cli_args.flag_type filter` | WIRED | Filter logic at L340-350; `for flag_type in active_flag_types:` at L356 |
| `calibrate.py hill_climb()` | `fixtures/calibrated_thresholds.json` | `json.dump` via `THRESHOLDS_PATH` | WIRED | `THRESHOLDS_PATH` defined L39; written at L421 |
| `Phase 9 _check_tool_use_violation()` | `xeter/services/worker/detection_patterns.yml` | `yaml.safe_load at init` (future) | PREPARED | File exists and parses; Phase 9 wiring is future work, correctly documented |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| HYBRID-01 | 07-02 | Shared hybrid scoring utility — 50/50 cosine + BOW | SATISFIED | `bow_score` + `hybrid_score` in `base.py`; imported and used in `tool_call_analyzer.py` |
| ARGS-01 | 07-03 | Error pattern path fires first (no embedding) | SATISFIED | Path 1 in `_check_wrong_args`; `test_wrong_args_error_pattern_fires_without_embedding` passes with `encode.call_count == 0` |
| ARGS-02 | 07-03 | Flattened arg values embedded (not raw JSON) | SATISFIED | `_flatten_arg_values()` extracts dict values only; verified import test shows keys excluded |
| ARGS-03 | 07-03 | Hybrid scoring (cosine + BOW) on semantic path | SATISFIED | `hybrid_score(cosine, bow_score(span.prompt, flattened))` at L274-275 |
| ARGS-04 | 07-03 | Skip embedding for empty or all-numeric values | SATISFIED | `_should_skip_embedding()` guards at L84-89; numeric test passes |
| ARGS-05 | 07-03 | `low_confidence: True` removed from flag detail | SATISFIED | Only appears in comments; 2 test assertions confirm absence |
| ARGS-06 | 07-05 | Per-method calibration ran and reported metrics | SATISFIED (user-accepted) | Calibration ran to completion; P=0.40, R=0.90 at threshold=0.30; user explicitly accepted P deviation — recall is prioritised, false negatives are primary risk. REQUIREMENTS.md still shows `[ ]` (documentation gap, not a code gap) |
| CAL-01 | 07-01 | `calibrate.py` supports binary flag type (skips numeric sweep) | SATISFIED | `BINARY_FLAG_TYPES: set[str] = set()` at L56; binary branch in loop L357-367 |
| CAL-02 | 07-01 | `calibrate.py` supports per-method mode | SATISFIED | `parse_args()` + `active_flag_types` filter; verified with import test |

**Note on ARGS-06:** REQUIREMENTS.md shows `- [ ]` (Pending) and the status table shows "Pending". The user has explicitly confirmed ARGS-06 is satisfied in the verification instructions — the requirement criterion is "calibration ran without crash and reported metrics", which is met. The REQUIREMENTS.md checkbox should be updated to `[x]` as a documentation cleanup task. This is a doc-only gap, not a blocking code gap.

---

### Anti-Patterns Found

No blockers or warnings found in key files.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TODOs, stubs, or placeholder returns found in phase deliverables | — | — |

**Specific checks:**
- `NOTE: wrong_tool_args excluded` print: ABSENT (correctly removed)
- `low_confidence` in Flag detail dict: ABSENT (only in comments)
- `return null` / `return {}` stubs: NONE in `_check_wrong_args`, `bow_score`, `hybrid_score`
- `_WRONG_ARGS_ERROR_PATTERNS`: 13 compiled patterns (substantive, not empty)
- `detection_patterns.yml` hybrid design: documented with inline comments explaining Stage 1 / Stage 2 approach

---

### Human Verification Required

None — all phase deliverables are verifiable programmatically.

The calibration P/R result (P=0.40, R=0.90) was already confirmed by the user at the Plan 05 checkpoint. No additional human verification is needed for this phase.

---

## Summary

Phase 7 goal is fully achieved. All nine observable truths hold:

1. The `_check_wrong_args` rewrite correctly implements two-path detection — error-regex priority (ARGS-01) short-circuits before any embed() call, and the semantic path uses flattened arg values with hybrid scoring (ARGS-02/03/04). The `low_confidence` key is absent (ARGS-05).

2. The shared hybrid scoring utility (`bow_score` + `hybrid_score`) exists as module-level functions in `base.py`, imported and actively used in `tool_call_analyzer.py`. All seven unit tests pass.

3. The calibration script has `--flag-type` isolation (CAL-02), `BINARY_FLAG_TYPES` infrastructure (CAL-01), and `wrong_tool_args` correctly re-included in `FLAG_TYPES`. The hill-climb ran to completion writing threshold=0.30 (P=0.40, R=0.90) to `calibrated_thresholds.json` — accepted by user with recall prioritised.

4. `detection_patterns.yml` exists, is valid YAML, was user-approved, and documents the Phase 9 hybrid detection design. NOTOOL-06 blocker is resolved.

5. 89 tests pass (26 worker tests + full suite). No regressions.

One documentation-only gap: REQUIREMENTS.md ARGS-06 checkbox remains `[ ]` (Pending) despite user acceptance. This should be updated to `[x]` (Complete) as a housekeeping task before the milestone closes.

---

_Verified: 2026-04-06_
_Verifier: Claude (gsd-verifier)_

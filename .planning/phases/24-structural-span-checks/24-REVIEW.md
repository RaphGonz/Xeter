---
phase: 24-structural-span-checks
reviewed: 2026-05-21T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - xeter/services/worker/output_schema_analyzer.py
  - xeter/tests/worker/test_output_schema_analyzer.py
  - xeter/services/worker/main.py
  - xeter/scripts/calibrate.py
  - xeter/tests/test_calibrate_routing.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 24: Code Review Report

**Reviewed:** 2026-05-21
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 24 adds `OutputSchemaAnalyzer` (5 deterministic checks), registers it in `main.py`, and extends `calibrate.py` with routing and `BINARY_FLAG_TYPES` membership for the 4 binary checks plus a threshold entry for `context_overflow`. The analyzer logic itself and the test suite for the analyzer are correct and well-structured.

The critical defects are both in `calibrate.py` and concern the `context_overflow` flag type. `context_overflow` is a token-count threshold (default 8000) but the hill-climbing algorithm operates in the normalized cosine-similarity range `[0.10, 0.95]`. Running calibration will produce a nonsensical calibrated threshold (~0.95 tokens) that makes the check fire on every span with a non-trivial prompt. A second independent defect: even if a correct threshold were somehow produced, `patch_docker_compose` does not include `WORKER_THRESHOLD_CONTEXT_OVERFLOW` in its `key_to_env` map, so the docker-compose file is never updated for this threshold.

---

## Critical Issues

### CR-01: `context_overflow` routed through `hill_climb()` with incompatible scale

**File:** `xeter/scripts/calibrate.py:504-526`

**Issue:** `context_overflow` is absent from `BINARY_FLAG_TYPES` (correctly, per test 13 — it is threshold-tunable). As a result, `main()` routes it through `hill_climb()`, which sweeps the threshold from `HILL_CLIMB_START = 0.10` to `HILL_CLIMB_MAX = 0.95` in steps of `0.05`. The `context_overflow` threshold is measured in **tiktoken tokens** (default 8000) — an entirely different scale. During a real calibration run:

1. At threshold `0.10`: every span whose prompt has even 1 token triggers the check — precision collapses to `tp / (tp + every_clean_span)`.
2. At threshold `0.95`: same result (0.95 tokens still fires on anything with a word).
3. Precision never improves, so hill climbing runs to `HILL_CLIMB_MAX`, and `calibrated['context_overflow']` is written as `0.95`.
4. Any downstream consumer of `fixtures/calibrated_thresholds.json` that sets the worker threshold to `0.95` tokens would cause `context_overflow` to fire on virtually every production span.

The recall floor guard (`_check_recall_floor`) does not protect against this: if the fixture contains any `context_overflow` samples, recall will be high at all thresholds and the guard passes.

**Fix:** Add `context_overflow` to `BINARY_FLAG_TYPES`, or (if threshold tuning is truly needed) add a dedicated token-scale calibration path with a range such as `[1000, 16000]` in token units. The simplest correct fix given the current architecture is to treat it as binary (evaluated at the default threshold only):

```python
BINARY_FLAG_TYPES: set[str] = {
    "tool_not_available",
    "wrong_tool_choice",
    "parsing_error",
    "output_schema_violation",
    "required_fields_missing",
    "output_truncated",
    "type_coercion_error",
    "context_overflow",   # add this — token-scale threshold incompatible with hill_climb range
}
```

Note: adding it to `BINARY_FLAG_TYPES` will break `test_13_context_overflow_not_in_binary_flag_types`. That test encodes the wrong design constraint and must be updated alongside the fix.

---

### CR-02: `patch_docker_compose` does not patch `WORKER_THRESHOLD_CONTEXT_OVERFLOW`

**File:** `xeter/scripts/calibrate.py:400-425`

**Issue:** `key_to_env` inside `patch_docker_compose` maps six threshold keys to their `WORKER_THRESHOLD_*` env var names. `context_overflow` is absent from this map. Even in the hypothetical scenario where `hill_climb()` produced a sensible token-scale threshold for `context_overflow`, the docker-compose file would never be updated. The `calibrated` dict written to JSON would contain `context_overflow: <value>` but the worker container would continue using the hard-coded default `"8000"` from `main.py`. This silently breaks the calibration-to-deployment pipeline for this check.

**Fix:** Add the missing entry to `key_to_env`:

```python
key_to_env = {
    "tool_not_available":    "WORKER_THRESHOLD_TOOL_NOT_AVAILABLE",
    "wrong_tool_choice":     "WORKER_THRESHOLD_WRONG_TOOL_CHOICE",
    "unnecessary_tool_call": "WORKER_THRESHOLD_UNNECESSARY_TOOL_CALL",
    "wrong_tool_args":       "WORKER_THRESHOLD_WRONG_TOOL_ARGS",
    "no_tool":               "WORKER_THRESHOLD_NO_TOOL",
    "response_anomaly":      "WORKER_THRESHOLD_RESPONSE_ANOMALY",
    "context_overflow":      "WORKER_THRESHOLD_CONTEXT_OVERFLOW",  # add this
}
```

This is also a prerequisite for CR-01's resolution: if `context_overflow` is converted to a binary type (single-pass evaluation at the default), the entry in `key_to_env` with a `None` value check on line 412 (`if value is None: continue`) will safely no-op, so adding the mapping is harmless either way.

---

## Warnings

### WR-01: `_has_unclosed_delimiter` produces false positives for non-JSON text containing `{`

**File:** `xeter/services/worker/output_schema_analyzer.py:134-152`

**Issue:** The heuristic checks `has_open = "{" in text or "[" in text`. If `span.response` or `span.tool_arguments` is a non-JSON string (e.g., a plain-English error message such as `"Tool call failed: unexpected { in config parameter"`) that fails `json.loads` and ends with a character other than `}`, `]`, or `"`, the method returns `True` and `SCHEMA-03` fires. This is a logic error: the heuristic is supposed to detect truncated JSON structure, not arbitrary text containing brace characters.

Example of a false positive:
```
response = "Execution error: missing field {name} in template"
```
`json.loads` fails, `has_open = True`, last char `e` not in closing set → `_has_unclosed_delimiter` returns `True` → `output_truncated` fires incorrectly.

**Fix:** Tighten the heuristic to require that the text *starts* with an opening delimiter (i.e., is attempting to be JSON) before applying the truncation test:

```python
def _has_unclosed_delimiter(self, text: Optional[str]) -> bool:
    if not text:
        return False
    text = text.rstrip()
    try:
        json.loads(text)
        return False
    except (json.JSONDecodeError, ValueError):
        pass
    stripped = text.lstrip()
    last = text[-1] if text else ""
    # Only flag if the text begins with a JSON structure opener
    starts_with_open = stripped and stripped[0] in ("{", "[")
    return starts_with_open and last not in ("}", "]", '"')
```

---

### WR-02: `n_flagged` in `calibrate.py` crashes with `KeyError` on malformed fixture lines

**File:** `xeter/scripts/calibrate.py:484`

**Issue:** `n_flagged = sum(1 for s in spans if s["label"] == "flagged")` uses a hard key lookup. `load_fixture()` performs no schema validation on loaded JSON lines; if any fixture row lacks a `"label"` key, this line raises `KeyError` and aborts the entire calibration run before any flag type is evaluated. The rest of the fixture access uses `.get()` defensively (e.g., `row.get("anomaly_types")`), making this raw subscript inconsistent.

**Fix:**
```python
n_flagged = sum(1 for s in spans if s.get("label") == "flagged")
```

---

### WR-03: `--verbose` diagnostic output is blind to all `OutputSchemaAnalyzer` metrics

**File:** `xeter/scripts/calibrate.py:253, 263`

**Issue:** `_print_failures` builds `scores_str` using a filter that only passes metric names containing `"tool"`, `"containment"`, `"embedding"`, or `"coherence"`. All `OutputSchemaAnalyzer` metric names (`output_schema_violation`, `required_fields_missing`, `output_truncated`, `type_coercion_error`, `prompt_token_count`) are excluded by this filter. Additionally, the FP detail display reads `rank` and `top_candidate` from `flag_detail` — fields that `OutputSchemaAnalyzer` flags never include.

The result is that `calibrate.py --flag-type output_schema_violation --verbose` prints completely empty diagnostic information for every false positive and false negative. This defeats the purpose of the `--verbose` flag for Phase 24 flag types.

**Fix:** Either generalize the filter to include all scores (removing the keyword filter entirely), or add Phase 24 metric names to the filter:

```python
# Option A — show all scores (simplest):
scores_str = "  ".join(f"{m}={s}" for m, s in fp["scores"])

# Option B — extend keyword set:
SCORE_FILTER_KEYWORDS = ("tool", "containment", "embedding", "coherence",
                         "schema", "token", "truncat", "coercion", "missing")
scores_str = "  ".join(
    f"{m}={s}" for m, s in fp["scores"]
    if any(kw in m for kw in SCORE_FILTER_KEYWORDS)
)
```

The same fix applies to the false-negative path (line 263) and to the `rank`/`top_candidate` display (add a guard: `if "rank" in detail:`).

---

## Info

### IN-01: Test suite lacks coverage for the `context_overflow` calibration path

**File:** `xeter/tests/test_calibrate_routing.py`

**Issue:** `test_13_context_overflow_not_in_binary_flag_types` asserts that `context_overflow` is **not** in `BINARY_FLAG_TYPES`. No test verifies what happens when `context_overflow` actually goes through calibration (hill climbing or single-pass). The suite does not test that a hill-climb call for `context_overflow` stays within a meaningful token range, nor does it test the `patch_docker_compose` mapping completeness for Phase 24 thresholds. This test gap allowed CR-01 and CR-02 to exist undetected.

**Fix:** After resolving CR-01, add a test asserting `context_overflow` is handled by the single-pass binary path (or whatever path produces a sensible threshold). Also add a test that `patch_docker_compose`'s `key_to_env` contains `WORKER_THRESHOLD_CONTEXT_OVERFLOW` if that key remains threshold-tunable.

---

_Reviewed: 2026-05-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

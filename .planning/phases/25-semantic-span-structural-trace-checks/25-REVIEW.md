---
phase: 25-semantic-span-structural-trace-checks
reviewed: 2026-05-24T15:58:30Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - xeter/services/worker/semantic_span_analyzer.py
  - xeter/services/worker/trace_analyzer.py
  - xeter/services/worker/main.py
  - xeter/scripts/calibrate.py
  - xeter/tests/test_semantic_span_analyzer.py
  - xeter/tests/test_trace_analyzer.py
  - xeter/tests/test_calibrate_routing.py
  - xeter/tests/worker/test_trace_analyzer.py
findings:
  critical: 3
  warning: 5
  info: 3
  total: 11
status: issues_found
---

# Phase 25: Code Review Report

**Reviewed:** 2026-05-24T15:58:30Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 25 introduces `SemanticSpanAnalyzer` (CTX-04 missing_details check) and `TraceAnalyzer` (5 trace-level checks: CTX-02, TRACE-01 through TRACE-04), wires both into `main.py`, and extends `calibrate.py` with routing for the new analyzers. The implementations are generally well-structured. Three blockers were found: `SemanticSpanAnalyzer` extends the wrong base class (skipping the `BaseSpanAnalyzer` contract), `calibrate.py` silently drops all Phase 25 calibration results when patching docker-compose, and `calibrate.py`'s hill-climb range is incompatible with `termination_loop_n`'s integer semantics — causing the check to fire on every span during calibration sweeps. Five warnings cover score-scale inconsistency, dead spaCy code whose presence contradicts the module docstring, a latent KeyError, a missing recall-floor guard for binary types, and a termination-loop count-capture issue.

---

## Critical Issues

### CR-01: `SemanticSpanAnalyzer` extends `BaseAnalyzer` instead of `BaseSpanAnalyzer`

**File:** `xeter/services/worker/semantic_span_analyzer.py:52`
**Issue:** `SemanticSpanAnalyzer` inherits directly from `BaseAnalyzer`, not `BaseSpanAnalyzer`. `BaseSpanAnalyzer` is the contract class that declares `analyze(span: SpanData) -> list[Flag]` as an `@abstractmethod`. By skipping it, `SemanticSpanAnalyzer`:

1. Is not identified as a span-level analyzer by `isinstance(analyzer, BaseSpanAnalyzer)` checks.
2. Violates the class hierarchy documented in `base.py` ("To add a new span-level analyzer: subclass `BaseSpanAnalyzer`").
3. Would not be caught by any future type-safety enforcement that distinguishes span- vs trace-level analyzers at the `main.py` dispatch layer.

The existing tests do not check the inheritance chain, so this passes the test suite undetected.

**Fix:**
```python
# semantic_span_analyzer.py — change line 52
from xeter.services.worker.base import BaseSpanAnalyzer, Flag, SpanData, bow_score, hybrid_score

class SemanticSpanAnalyzer(BaseSpanAnalyzer):   # was BaseAnalyzer
    ...
```

---

### CR-02: `calibrate.py` — `patch_docker_compose` silently drops all Phase 25 calibrated thresholds

**File:** `xeter/scripts/calibrate.py:429-453`
**Issue:** `patch_docker_compose` contains a hardcoded `key_to_env` dict with only 6 pre-Phase-25 keys. The 6 new Phase 25 env vars (`WORKER_THRESHOLD_MISSING_DETAILS`, `WORKER_THRESHOLD_STALE_CONTEXT`, `WORKER_THRESHOLD_CONTEXT_PROPAGATION_FAILURE`, `WORKER_THRESHOLD_HISTORY_LOSS`, `WORKER_THRESHOLD_STEP_REPETITION`, `WORKER_THRESHOLD_TERMINATION_LOOP_N`) are absent. When `patch_docker_compose(calibrated)` is called at the end of a full calibration run, it iterates only the 6 old keys; the newly calibrated Phase 25 thresholds are computed, printed to stdout, and written to `calibrated_thresholds.json`, but the `docker-compose.yml` env vars used in production are never updated. Operators who rely on the calibration script to tune the live system will deploy with the hardcoded default values (0.6, 85.0, 0.5, 0.4, 85.0, 3) regardless of what the calibration found.

**Fix:**
```python
key_to_env = {
    # existing entries ...
    "tool_not_available": "WORKER_THRESHOLD_TOOL_NOT_AVAILABLE",
    "wrong_tool_choice":  "WORKER_THRESHOLD_WRONG_TOOL_CHOICE",
    "unnecessary_tool_call": "WORKER_THRESHOLD_UNNECESSARY_TOOL_CALL",
    "wrong_tool_args":    "WORKER_THRESHOLD_WRONG_TOOL_ARGS",
    "no_tool":            "WORKER_THRESHOLD_NO_TOOL",
    "response_anomaly":   "WORKER_THRESHOLD_RESPONSE_ANOMALY",
    # Phase 25 additions
    "missing_details":              "WORKER_THRESHOLD_MISSING_DETAILS",
    "stale_context":                "WORKER_THRESHOLD_STALE_CONTEXT",
    "context_propagation_failure":  "WORKER_THRESHOLD_CONTEXT_PROPAGATION_FAILURE",
    "history_loss":                 "WORKER_THRESHOLD_HISTORY_LOSS",
    "step_repetition":              "WORKER_THRESHOLD_STEP_REPETITION",
    "termination_loop_n":           "WORKER_THRESHOLD_TERMINATION_LOOP_N",
}
```

---

### CR-03: `calibrate.py` — hill-climb sweeps [0.10, 0.95] for `termination_loop_n`, making `int(threshold)` always 0 during calibration

**File:** `xeter/scripts/calibrate.py:136-138, 323-345` (hill-climb) and `xeter/services/worker/trace_analyzer.py:174`
**Issue:** `HILL_CLIMB_START = 0.10` and `HILL_CLIMB_STEP = 0.05` and `HILL_CLIMB_MAX = 0.95`. `termination_loop` is not in `BINARY_FLAG_TYPES`, so it goes through `hill_climb()`, receiving threshold values of 0.10, 0.15, 0.20, …, 0.95 — all floats < 1.

`_check_termination_loop` casts the threshold to int: `n = int(self._thresholds["termination_loop_n"])`. `int(0.10)` through `int(0.95)` all equal `0`. The guard `if run_length >= n` becomes `run_length >= 0`, which is always True from the first span onward. Every span with a non-None `tool_name` will trigger the flag on every iteration.

This means:
- Calibration precision for `termination_loop` is meaningless — every span is flagged regardless of actual consecutive-run behavior.
- The best calibrated threshold will be whichever sweep value happened to produce the least-bad P/R (likely whichever happened to match recall = 1.0 and lowest feasible precision), and it will still be cast to `n=0` in production.
- The recall floor guard (`_check_recall_floor`) will not catch this because recall will be 1.0 (all actual positives flagged), not below 0.10.

The correct approach is to exempt `termination_loop_n` from the cosine-range hill-climb and calibrate it separately over integer values [2, 3, 4, 5].

**Fix:**
```python
# calibrate.py — add termination_loop_n to a separate integer sweep

TERMINATION_LOOP_N_VALUES = [2, 3, 4, 5]  # integer grid, not cosine range

# In the main() loop, before the standard hill_climb block:
if flag_type == "termination_loop":
    best_p, best_r, best_n = -1, 0.0, 3
    for n_val in TERMINATION_LOOP_N_VALUES:
        p, r = evaluate_flag_type(
            flag_type, float(n_val), spans, embedder, calibrated
        )
        if p > best_p:
            best_p, best_r, best_n = p, r, n_val
    calibrated["termination_loop_n"] = float(best_n)
    results["termination_loop"] = {
        "best_threshold": float(best_n),
        "best_precision": best_p,
        "best_recall": best_r,
        "history": [],
        "steps": len(TERMINATION_LOOP_N_VALUES),
    }
    continue  # skip the standard hill_climb call
```

---

## Warnings

### WR-01: `stale_context` and `step_repetition` log scores on a 0–100 scale; all other metrics use 0–1

**File:** `xeter/services/worker/trace_analyzer.py:105, 146`
**Issue:** `fuzz.ratio` and `fuzz.token_sort_ratio` return values in [0, 100] (rapidfuzz convention). Both `_check_stale_context` and `_check_step_repetition` pass these raw values directly to `self.log_score(...)` and store them in `Flag.score`. All other metrics (cosine, bow, hybrid) are in [0, 1]. The `span_scores` table in PostgreSQL will therefore contain scores of 85.0 next to scores of 0.42 for the same span, making the calibration dataset misleading and any cross-metric analysis incorrect. The thresholds in `THRESHOLDS` (85.0 for stale_context and step_repetition) are consistent with 0–100, so detection is not wrong, but the persisted scores are on a different scale.

**Fix:** Normalize before logging and storing in Flag.score:
```python
# In both _check_stale_context and _check_step_repetition:
raw_score = fuzz.ratio(...)         # 0–100
score = raw_score / 100.0           # normalize to 0–1
self.log_score("stale_context", score)
if score >= self._thresholds["stale_context"] / 100.0:   # threshold also normalized
    flags.append(Flag(..., score=score, ...))
```
Alternatively, document explicitly that these two metrics use a 0–100 scale and adjust the DB schema accordingly.

---

### WR-02: Dead spaCy code in `semantic_span_analyzer.py` contradicts the module docstring

**File:** `xeter/services/worker/semantic_span_analyzer.py:22-44`
**Issue:** `_get_spacy()` and `_lemma_set()` are defined at module level but are never called anywhere in the file. The module docstring states "spaCy lemma entity recall as the BOW component" — but `_check_missing_details` calls `bow_score(span.prompt, span.response)` from `base.py`, which is a simple Jaccard whitespace-token overlap. The spaCy-based lemma scoring described in the docstring was never wired in. This is not just stale code — it creates a false specification that misrepresents what the check actually does, which matters for calibration interpretation and for future developers.

**Fix (option A — remove dead code and fix docstring):**
```python
# Remove lines 22-44 (_NLP, _get_spacy, _lemma_set) entirely.
# Update module docstring to read:
# "Detection via hybrid cosine + bag-of-words scoring (Jaccard token overlap)."
```

**Fix (option B — wire in the lemma-based BOW as specified):**
```python
# In _check_missing_details, replace:
bow = bow_score(span.prompt, span.response)
# with:
lemmas_prompt = _lemma_set(span.prompt)
lemmas_response = _lemma_set(span.response)
if lemmas_prompt and lemmas_response:
    bow = len(lemmas_prompt & lemmas_response) / len(lemmas_prompt | lemmas_response)
else:
    bow = 0.0
```

---

### WR-03: `_flush_stale_traces` — `trace_buffer[tid]` will raise `KeyError` if the buffer is modified between list comprehension and loop

**File:** `xeter/services/worker/main.py:149-170`
**Issue:** `ready_trace_ids` is computed as a list comprehension from `trace_last_seen`. The subsequent for-loop accesses `trace_buffer[tid]` without guarding for a missing key. In the current single-threaded implementation this cannot happen naturally, but `trace_last_seen` and `trace_buffer` are mutated by the main loop between calls to `_flush_stale_traces`. More importantly, if `trace_buffer` and `trace_last_seen` ever become desynchronized (e.g., a future refactor inserts only into one dict, or a bug causes a partial write), the `trace_buffer[tid]` access will raise `KeyError`, crashing the flush and leaving traces permanently stale in the last-seen dict (they are removed in `finally`, but `trace_buffer.pop(tid, None)` will no-op while `trace_last_seen.pop(tid, None)` does remove the entry — creating permanent `trace_last_seen` entries with no corresponding buffer entry on next call).

**Fix:**
```python
spans_for_trace = trace_buffer.get(tid)
if spans_for_trace is None:
    # buffer and last_seen are desynchronized — clean up and skip
    trace_last_seen.pop(tid, None)
    continue
```

---

### WR-04: `_check_termination_loop` captures run-length at first threshold crossing, not at trace end

**File:** `xeter/services/worker/trace_analyzer.py:193-203`
**Issue:** When a tool is called N times consecutively and the run continues beyond N (e.g., N=3, actual run=7), the flag fires at `run_length=3` and `detail["count"]=3`. The `flagged_tools` set then suppresses all further flags for that tool. The final run length (7) is never recorded. Dashboard consumers reading `flag.detail["count"]` will undercount the severity of the loop. This is likely intentional as a design choice to fire once, but the captured count is misleading because it does not represent the final length of the run.

**Fix:** Capture the final run length at trace end by adding a post-loop pass:
```python
# After the for-loop, update the count in any fired flags to the final run length
for flag in flags:
    if flag.flag_type == "termination_loop":
        tool = flag.detail["tool_name"]
        # Compute final run length for this tool
        final_run = sum(
            1 for s in reversed(spans)
            if s.tool_name == tool
        )  # or track final lengths per-tool during the loop
```
A simpler approach: track `run_length` per tool in a dict so the final run can be recorded.

---

### WR-05: `calibrate.py` — `_check_recall_floor` is never called for binary flag types

**File:** `xeter/scripts/calibrate.py:533-551`
**Issue:** In the main calibration loop, binary flag types and `--eval-only` runs go through the `continue` branch, which records results but never calls `_check_recall_floor`. If a binary detector (e.g., `output_schema_violation`) produces recall=0 (never fires), the summary prints a `WARN` but does NOT exit with code 1, and the script reports `all_pass=False` but completes normally. For threshold-tunable types, a recall=0 causes `sys.exit(1)` via `_check_recall_floor`. This inconsistency means a completely broken binary analyzer is silently accepted by CI.

**Fix:**
```python
# After binary evaluation, add recall floor check:
if flag_type in active_binary:
    _check_recall_floor(flag_type, recall)  # exits if recall < 0.10
```

---

## Info

### IN-01: `SemanticSpanAnalyzer` imports `Optional` from `typing` but never uses it

**File:** `xeter/services/worker/semantic_span_analyzer.py:12`
**Issue:** `from typing import Optional` is imported but `Optional` does not appear anywhere in the file. The `_check_missing_details` signature uses `SpanData` directly (not `Optional[SpanData]`).

**Fix:** Remove the unused import:
```python
# Delete line 12:
from typing import Optional
```

---

### IN-02: `calibrate.py` — `_PROJECT_ROOT_EARLY` and `PROJECT_ROOT` are computed identically (duplicate)

**File:** `xeter/scripts/calibrate.py:38-42`
**Issue:** `_PROJECT_ROOT_EARLY = Path(__file__).parent.parent.parent` (line 38) and `PROJECT_ROOT = Path(__file__).parent.parent.parent` (line 42) compute the same path. `_PROJECT_ROOT_EARLY` is used only to conditionally insert into `sys.path` on lines 39-40, then `PROJECT_ROOT` is used for all path construction. The variable name and the redundant computation add noise with no benefit.

**Fix:**
```python
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
```

---

### IN-03: `test_trace_analyzer.py` (worker/) — test file path is a duplicate of `tests/test_trace_analyzer.py`

**File:** `xeter/tests/worker/test_trace_analyzer.py`
**Issue:** There are two test files covering `TraceAnalyzer`: `xeter/tests/test_trace_analyzer.py` (22 tests, comprehensive) and `xeter/tests/worker/test_trace_analyzer.py` (5 tests, minimal scaffold). The worker-subdirectory file tests only the basic contract (subclass, name, empty returns) and overlaps with tests 1-2 of the comprehensive file. There is no documented reason for two separate locations; this creates confusion about which file is authoritative for `TraceAnalyzer` tests and risks the comprehensive tests being discovered inconsistently depending on pytest configuration.

**Fix:** Either consolidate into a single file (`xeter/tests/test_trace_analyzer.py`) or rename `xeter/tests/worker/test_trace_analyzer.py` to `xeter/tests/worker/test_trace_analyzer_contract.py` with a comment explaining its scope (smoke tests only, not the full behavioral suite).

---

_Reviewed: 2026-05-24T15:58:30Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

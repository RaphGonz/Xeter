---
phase: 26-best-effort-proxy-checks
reviewed: 2026-05-26T21:25:56Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - xeter/tests/worker/test_trace_analyzer_phase26.py
  - xeter/services/worker/trace_analyzer.py
  - xeter/services/worker/main.py
  - xeter/scripts/calibrate.py
  - xeter/tests/test_calibrate_routing.py
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 26: Code Review Report

**Reviewed:** 2026-05-26T21:25:56Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 26 adds six trace-level proxy checks (TRACE-05 through TRACE-10) to `TraceAnalyzer`,
registers them in `calibrate.py`, and wires up environment-variable thresholds in `main.py`.
The analyzer implementation and tests are structurally sound, but three blockers make calibration
non-functional for multiple new checks, and two additional design defects will mislead operators
who try to tune thresholds. The binary-check threshold config issue compounds the calibration
breakage by making hill climbing produce meaningless results even when the span-wrapping bug
were fixed.

---

## Critical Issues

### CR-01: `evaluate_flag_type` wraps every span in a single-element list — all multi-span trace checks always return empty, making calibration non-functional

**File:** `xeter/scripts/calibrate.py:246-248`

**Issue:** `evaluate_flag_type` dispatches trace-level analyzers via `analyzer.analyze([span])`,
passing a single-span list. Every check in `TraceAnalyzer` that guards `len(spans) < 2`
(all of them except `_check_clarification_skipped`) silently returns `[]`. As a result:

- `wrong_agent_handoff`, `information_withholding`, `conversation_reset`,
  `no_verification`, `incomplete_verification` — all return no flags regardless of the span's
  content, making `tp = 0` and `fn = all positives`.
- `best_recall = 0.0` for every fixture that has labeled examples for these checks.
- `_check_recall_floor` will call `sys.exit(1)` immediately when any of these is calibrated
  in a run that includes labelled examples. Calibration of Phase 26 trace checks is
  completely broken.
- `_check_clarification_skipped` is the only Phase 26 check that can be calibrated under
  the current design (`len(spans) >= 1` guard).

Trace-level calibration requires grouping spans by `trace_id` into multi-span lists before
calling `analyze()`. Passing one span at a time is a correct approach for span-level analyzers
(`BaseSpanAnalyzer`) but wrong for `BaseTraceAnalyzer`.

**Fix:** The calibration fixture should store spans grouped by trace, and `evaluate_flag_type`
must reconstruct the trace list for `BaseTraceAnalyzer`. Alternatively, add a per-trace
fixture format and a dedicated trace-calibration path:

```python
if isinstance(analyzer, BaseTraceAnalyzer):
    # Group spans by trace_id, evaluate each trace as a unit
    from itertools import groupby
    spans_by_trace = {}
    for row in spans:
        tid = row.get("trace_id", "default")
        spans_by_trace.setdefault(tid, []).append(build_span_data(row))
    for trace_spans in spans_by_trace.values():
        flags = analyzer.analyze(trace_spans)
        ...
```

---

### CR-02: `wrong_agent_handoff` calibration is doubly broken — `TraceAnalyzer` instantiated without `routing_graph`

**File:** `xeter/scripts/calibrate.py:235-236`

**Issue:** In addition to the single-span wrapping in CR-01, `evaluate_flag_type` instantiates
`TraceAnalyzer` as `analyzer_cls(embedder, thresholds)`, omitting the `routing_graph` keyword
argument. `TraceAnalyzer.__init__` defaults `routing_graph=None`, and
`_check_wrong_agent_handoff` guards `if not self._routing_graph: return []`.

This means `wrong_agent_handoff` always returns an empty flag list in calibration even if:
- CR-01 were fixed to pass multi-span lists, AND
- The fixture contains labeled `wrong_agent_handoff` examples.

The calibration result for this check is permanently `P=0.0, R=0.0` regardless of fixture
quality. `_check_recall_floor` will `sys.exit(1)` immediately on any calibration run that
includes labeled examples for this check.

**Fix:** When instantiating `TraceAnalyzer` for calibration, supply a permissive routing
graph sourced from fixture metadata, or accept a `routing_graph` column in the fixture:

```python
# In evaluate_flag_type, after determining analyzer_cls == TraceAnalyzer:
routing_graph = None
if flag_type == "wrong_agent_handoff":
    # Build routing graph from fixture or use a universal-deny sentinel
    # If fixture includes trace-level routing_graph metadata, extract it here.
    pass
analyzer = analyzer_cls(embedder, thresholds, routing_graph=routing_graph)
```

At minimum, document that `wrong_agent_handoff` requires a fixture with routing-graph
metadata and cannot be calibrated via the current harness.

---

### CR-03: Three binary checks (`wrong_agent_handoff`, `no_verification`, `clarification_skipped`) ignore their threshold keys — operator env-var tuning has zero effect

**File:** `xeter/services/worker/trace_analyzer.py:340-354` (wrong_agent_handoff),
`xeter/services/worker/trace_analyzer.py:519-527` (no_verification),
`xeter/services/worker/trace_analyzer.py:472-487` (clarification_skipped)

**Issue:** All three checks compute a binary score (0.0 or 1.0) and fire via a direct
boolean test, never consulting `self._thresholds`. Yet `main.py` stores threshold keys for all
three (`wrong_agent_handoff: 1.0`, `no_verification: 1.0`, `clarification_skipped: 1.0`) and
the module docstring implies these are tunable. The corresponding env vars
`WORKER_THRESHOLD_WRONG_AGENT_HANDOFF`, `WORKER_THRESHOLD_NO_VERIFICATION`, and
`WORKER_THRESHOLD_CLARIFICATION_SKIPPED` have zero effect on runtime behavior.

An operator who reads the docker-compose.yml or main.py and lowers these values (e.g. to 0.5)
expecting to make the checks less aggressive will see no change. This is a silent config
correctness trap.

Additionally, `calibrate.py`'s hill-climbing loop will iterate all threshold steps for these
three types, compute identical P/R at every step (since the threshold is never read), and
select `HILL_CLIMB_MAX = 0.95` as the "best" threshold — a meaningless result stored to
`calibrated_thresholds.json`.

**Fix:** Either:

a) Add threshold comparisons to each check (so the threshold actually gates the flag):
```python
# wrong_agent_handoff — fire only when score >= threshold
if violation and score >= self._thresholds.get("wrong_agent_handoff", 1.0):
    flags.append(...)
```

b) Or move these three into `BINARY_FLAG_TYPES` in `calibrate.py` to skip hill climbing and
document them as non-configurable, and remove their threshold keys from `THRESHOLDS` in
`main.py` (or leave them with a prominent comment that they are unused).

Option (a) enables future softening of these checks; option (b) is simpler and more honest.

---

## Warnings

### WR-01: `patch_docker_compose` does not include any Phase 26 threshold env vars — calibration results cannot be deployed

**File:** `xeter/scripts/calibrate.py:450-474`

**Issue:** `patch_docker_compose` maps only 6 pre-Phase-24 threshold keys to env var names.
All Phase 25 and Phase 26 keys (`conversation_reset`, `information_withholding`,
`incomplete_verification`, etc.) are absent from `key_to_env`. After a successful calibration
run, the calibrated values are written to `calibrated_thresholds.json` but never patched into
`deploy/docker-compose.yml`. The worker container continues to use the hardcoded defaults in
`main.py`.

Furthermore, `deploy/docker-compose.yml` itself has no `WORKER_THRESHOLD_*` entries for any
Phase 25 or 26 key, so even if `patch_docker_compose` were extended, there would be no
placeholder lines to match the regex substitution.

**Fix:** Extend `key_to_env` to include all calibratable Phase 25 and 26 keys, and add
corresponding placeholder entries in `deploy/docker-compose.yml`:

```python
key_to_env = {
    ...existing entries...,
    # Phase 25
    "stale_context":                 "WORKER_THRESHOLD_STALE_CONTEXT",
    "context_propagation_failure":   "WORKER_THRESHOLD_CONTEXT_PROPAGATION_FAILURE",
    "history_loss":                  "WORKER_THRESHOLD_HISTORY_LOSS",
    "step_repetition":               "WORKER_THRESHOLD_STEP_REPETITION",
    "missing_details":               "WORKER_THRESHOLD_MISSING_DETAILS",
    # Phase 26
    "conversation_reset":            "WORKER_THRESHOLD_CONVERSATION_RESET",
    "information_withholding":       "WORKER_THRESHOLD_INFORMATION_WITHHOLDING",
    "incomplete_verification":       "WORKER_THRESHOLD_INCOMPLETE_VERIFICATION",
}
```

---

### WR-02: `_check_conversation_reset` and `_check_history_loss` use identical logic — both can fire simultaneously on the same span, double-flagging the same signal

**File:** `xeter/services/worker/trace_analyzer.py:409-446` (conversation_reset) and
`xeter/services/worker/trace_analyzer.py:276-312` (history_loss)

**Issue:** Both checks compute centroid cosine distance of current prompt against all prior
prompts. The only difference is the metric name and threshold value
(`conversation_reset` default 0.25 vs `history_loss` default 0.40). Because
`conversation_reset` has the lower threshold, any span that fires `history_loss` (score < 0.40)
will also fire `conversation_reset` (score < 0.25) when the score is in `[0, 0.25)`. There is
no mutual exclusion between them (unlike `no_verification` / `incomplete_verification`).

This results in the same semantic event generating two flags with different names in the output,
inflating flag counts for dashboard consumers and making it harder to distinguish a
"mild history drift" (history_loss only) from an "abrupt reset" (both).

**Fix:** Add mutual exclusion: if `history_loss` fires for span `i`, skip emitting
`conversation_reset` for that same span. Or give each check a non-overlapping threshold
range and document the semantics explicitly:

```python
# In _check_conversation_reset, skip when history_loss threshold would also trigger:
if score >= self._thresholds["history_loss"]:  # strictly below history_loss range
    # Only fire conversation_reset for severe drops not already covered by history_loss
    if score < self._thresholds.get("conversation_reset", 0.25):
        flags.append(...)
```

---

### WR-03: Inconsistent threshold access pattern — new checks use `.get(key, default)` while existing checks use `self._thresholds[key]`

**File:** `xeter/services/worker/trace_analyzer.py:393` (information_withholding),
`xeter/services/worker/trace_analyzer.py:435` (conversation_reset),
`xeter/services/worker/trace_analyzer.py:582` (incomplete_verification)

**Issue:** The Phase 26 checks use `self._thresholds.get("key", default)` with hardcoded
fallbacks, while all Phase 25 checks use `self._thresholds["key"]` (raises `KeyError` if the
key is absent). The `.get()` form silently falls back to the hardcoded default rather than
failing loudly when a threshold is misconfigured or omitted from the constructor call. In
tests, `_make_trace_analyzer` always supplies all keys, so neither pattern fails today — but
the inconsistency means a future caller who omits a Phase 26 threshold key gets silent
wrong-default behavior while omitting a Phase 25 key raises `KeyError`.

**Fix:** Use `self._thresholds["key"]` uniformly for all checks. This forces callers to supply
all required thresholds at construction time, which is already enforced by the `THRESHOLDS`
dict in `main.py`. Remove the `.get()` fallbacks:

```python
# Before (Phase 26 pattern):
if score < self._thresholds.get("conversation_reset", 0.25):

# After (consistent with Phase 25):
if score < self._thresholds["conversation_reset"]:
```

---

### WR-04: `_check_wrong_agent_handoff` does not guard against `None` agent names — routing graph lookup will misfire

**File:** `xeter/services/worker/trace_analyzer.py:335-355`

**Issue:** `SpanData.agent_name` is typed `str` (non-optional), but no validation enforces
this at ingestion. If a span has `agent_name=None` (possible through ClickHouse NULL or
fixture data with missing fields), the check proceeds with `src=None` or `dst=None`.

- `None not in self._routing_graph` evaluates to `True` (None is not a dict key) → violation
  fires as a false positive.
- `self._routing_graph.get(None)` would be `None`, but the code uses direct subscript
  `self._routing_graph[src]` — this raises `KeyError` when `src` is `None` and `None` is not
  in the graph. Wait, re-reading: `violation = (src not in self._routing_graph) or ...` —
  short-circuit evaluation means if `src not in graph` is `True` the second operand is never
  evaluated. So for `src=None`: `None not in graph` → True → violation fires immediately.
  No `KeyError`. But the flag is a false positive.

**Fix:** Add a guard at the top of the transition loop:

```python
for i in range(1, len(spans)):
    src = spans[i - 1].agent_name
    dst = spans[i].agent_name
    if src is None or dst is None:
        continue  # cannot evaluate routing without agent names
    if src == dst:
        continue
    ...
```

---

## Info

### IN-01: `known = set(FLAG_TYPES) | BINARY_FLAG_TYPES` in `calibrate.py` — redundant union since `BINARY_FLAG_TYPES` is a strict subset of `FLAG_TYPES`

**File:** `xeter/scripts/calibrate.py:539`

**Issue:** `BINARY_FLAG_TYPES` only contains types that are also present in `FLAG_TYPES`. The
`|` union is a no-op. Any future type added to `BINARY_FLAG_TYPES` but forgotten in `FLAG_TYPES`
would be silently accepted by the `known` check but still unreachable via `active_flag_types`,
making it difficult to detect the omission.

**Fix:** Assert the invariant explicitly and simplify:

```python
# Replace:
known = set(FLAG_TYPES) | BINARY_FLAG_TYPES

# With:
assert BINARY_FLAG_TYPES <= set(FLAG_TYPES), (
    f"BINARY_FLAG_TYPES contains types not in FLAG_TYPES: {BINARY_FLAG_TYPES - set(FLAG_TYPES)}"
)
known = set(FLAG_TYPES)
```

---

### IN-02: `_check_incomplete_verification` only checks the first verification span — subsequent verification spans are silently ignored

**File:** `xeter/services/worker/trace_analyzer.py:546-553`

**Issue:** The method finds `ver_idx` by breaking on the first span with a verification keyword.
In traces with multiple verification passes (e.g. a mid-trace partial check followed by a
final full check), only the first verifier's coverage is evaluated. All entities produced
between the first and second verifier are never checked. The check comment says "best-effort"
but this gap is not documented in the method docstring.

**Fix:** At minimum, document the limitation in the docstring:

```python
"""...
Note: only the first verification span is evaluated. Traces with multiple
verification spans have all but the first verifier ignored by this check.
"""
```

A more complete fix would iterate all verification spans, computing coverage for each against
entities produced before that span.

---

_Reviewed: 2026-05-26T21:25:56Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

# Phase 26: Best-Effort Proxy Checks - Pattern Map

**Mapped:** 2026-05-26
**Files analyzed:** 4 (3 modified, 1 new)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `xeter/services/worker/trace_analyzer.py` | service (extend existing class) | event-driven / batch | self (Phase 25 implementation) | exact — same file, adding methods |
| `xeter/services/worker/main.py` | config / wiring | request-response | self (Phase 25 THRESHOLDS block) | exact — same file, extending THRESHOLDS dict + constructor call |
| `xeter/scripts/calibrate.py` | config / registry | batch | self (Phase 25 FLAG_TYPE_TO_ANALYZER_CLASS block) | exact — same file, extending registries |
| `xeter/tests/test_trace_analyzer.py` (new Phase 26 file) | test | batch | `xeter/tests/test_trace_analyzer.py` (Phase 25 version) | exact — same structure, same helper factories |

---

## Pattern Assignments

### `xeter/services/worker/trace_analyzer.py` — extend TraceAnalyzer

**Analog:** same file, `xeter/services/worker/trace_analyzer.py`

#### `__init__` signature to replace (lines 54-55):
```python
def __init__(self, embedder: EmbedderClient, thresholds: dict[str, float]) -> None:
    super().__init__(embedder, thresholds)
```
Phase 26 replacement — add `routing_graph` optional param (D-06):
```python
def __init__(
    self,
    embedder: EmbedderClient,
    thresholds: dict[str, float],
    routing_graph: dict[str, list[str]] | None = None,
) -> None:
    super().__init__(embedder, thresholds)
    self._routing_graph = routing_graph
```

#### `analyze()` dispatch pattern to extend (lines 62-80):
```python
def analyze(self, spans: list[SpanData]) -> list[Flag]:
    flags: list[Flag] = []
    flags.extend(self._check_stale_context(spans))
    flags.extend(self._check_step_repetition(spans))
    flags.extend(self._check_termination_loop(spans))
    flags.extend(self._check_context_propagation_failure(spans))
    flags.extend(self._check_history_loss(spans))
    return flags
```
Phase 26: append 6 new `flags.extend(...)` calls after the existing 5, with special mutual-exclusion logic for `no_verification` / `incomplete_verification` (D-12):
```python
    # Phase 26 additions
    flags.extend(self._check_wrong_agent_handoff(spans))
    flags.extend(self._check_information_withholding(spans))
    flags.extend(self._check_conversation_reset(spans))
    flags.extend(self._check_clarification_skipped(spans))
    no_ver_flags = self._check_no_verification(spans)
    flags.extend(no_ver_flags)
    if not no_ver_flags:                          # D-12 mutual exclusion
        flags.extend(self._check_incomplete_verification(spans))
    return flags
```

#### Module-level `_VERIFICATION_KEYWORDS` frozenset (new, insert after `_NLP = None`):
```python
_VERIFICATION_KEYWORDS: frozenset[str] = frozenset({
    "verify", "check", "validate", "assert", "test", "confirm"
})
```

#### Centroid cosine pattern — `_check_history_loss` (lines 251-287, the template for `_check_conversation_reset`):
```python
def _check_history_loss(self, spans: list[SpanData]) -> list[Flag]:
    if len(spans) < 3:
        return []

    flags: list[Flag] = []
    for i in range(2, len(spans)):
        if spans[i].prompt is None:
            continue

        prior_prompts = [s.prompt for s in spans[:i] if s.prompt is not None]
        if not prior_prompts:
            continue

        prior_vecs = self._embedder.encode_batch(prior_prompts)
        centroid = np.mean(prior_vecs, axis=0)
        current_vec = self.embed(spans[i].prompt)
        score = self.compare(current_vec, centroid)
        # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
        self.log_score("history_loss", score)
        if score < self._thresholds["history_loss"]:
            flags.append(Flag(
                flag_type="history_loss",
                score=score,
                detail={
                    "metric": "history_loss",
                    "span_index": i,
                },
            ))

    return flags
```
`_check_conversation_reset` copies this exactly, replacing every `"history_loss"` literal with `"conversation_reset"` and adding `"low_confidence": True` to `detail` (D-01, D-04).

#### Flag construction patterns — `low_confidence` vs plain detail:

Low-confidence flag (TRACE-05, TRACE-07, TRACE-08) — copy from `_check_stale_context` lines 107-115:
```python
flags.append(Flag(
    flag_type="stale_context",
    score=score,
    detail={
        "metric": "stale_context",
        "span_index": i,
        "low_confidence": True,
    },
))
```

Plain detail flag (TRACE-09, TRACE-10, TRACE-06) — copy from `_check_context_propagation_failure` lines 238-244:
```python
flags.append(Flag(
    flag_type="context_propagation_failure",
    score=score,
    detail={
        "metric": "context_propagation_failure",
        "span_index": i,
    },
))
```

#### `log_score` before threshold — mandatory invariant (applies to every check that computes a score):
```python
# CRITICAL: log BEFORE threshold comparison (D-04 invariant)
self.log_score("metric_name", score)
if score < self._thresholds["metric_name"]:
    ...
```
Checks that are binary 0.0/1.0 (`wrong_agent_handoff`, `clarification_skipped`, `no_verification`): still call `self.log_score("metric_name", score)` with `score = 1.0` before appending the flag (score must be logged unconditionally for calibration data completeness).

#### Guard patterns to copy:

Two-span guard (all checks except `conversation_reset`):
```python
if len(spans) < 2:
    return []
```

Three-span guard (`conversation_reset` only, same as `history_loss`):
```python
if len(spans) < 3:
    return []
```

No-op guard for `wrong_agent_handoff` when routing graph absent (D-07):
```python
if not self._routing_graph:
    return []
```

#### spaCy lazy-loader (already in file, lines 35-43 — reuse directly for `information_withholding` and `incomplete_verification`):
```python
_NLP = None

def _get_spacy():
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load("en_core_web_md")
    return _NLP
```
Usage pattern: `nlp = _get_spacy(); doc = nlp(text); entities = {ent.text.lower() for ent in doc.ents}`

---

### `xeter/services/worker/main.py` — THRESHOLDS + constructor wiring

**Analog:** same file, lines 54-68 (Phase 25 threshold block) and line 194 (TraceAnalyzer instantiation).

#### THRESHOLDS dict Phase 25 block (lines 62-68) — add 6 entries after `"termination_loop_n"`:
```python
# Phase 25 — TraceAnalyzer
"stale_context": float(os.environ.get("WORKER_THRESHOLD_STALE_CONTEXT", "85.0")),  # [safe-default] calibration value; tune via calibration scripts
"context_propagation_failure": float(os.environ.get("WORKER_THRESHOLD_CONTEXT_PROPAGATION_FAILURE", "0.5")),  # [safe-default] calibration value; tune via calibration scripts
"history_loss": float(os.environ.get("WORKER_THRESHOLD_HISTORY_LOSS", "0.4")),  # [safe-default] calibration value; tune via calibration scripts
"step_repetition": float(os.environ.get("WORKER_THRESHOLD_STEP_REPETITION", "85.0")),  # [safe-default] calibration value; tune via calibration scripts
"termination_loop_n": float(os.environ.get("WORKER_THRESHOLD_TERMINATION_LOOP_N", "3")),  # [safe-default] calibration value; tune via calibration scripts
```
Phase 26 entries to add immediately after (same comment+os.environ.get pattern):
```python
# Phase 26 — TraceAnalyzer (best-effort proxy checks)
"conversation_reset": float(os.environ.get("WORKER_THRESHOLD_CONVERSATION_RESET", "0.25")),  # [safe-default] calibration value; tune via calibration scripts
"information_withholding": float(os.environ.get("WORKER_THRESHOLD_INFORMATION_WITHHOLDING", "0.5")),  # [safe-default] calibration value; tune via calibration scripts
"wrong_agent_handoff": float(os.environ.get("WORKER_THRESHOLD_WRONG_AGENT_HANDOFF", "1.0")),  # [safe-default] binary 0.0/1.0; tune via calibration scripts
"clarification_skipped": float(os.environ.get("WORKER_THRESHOLD_CLARIFICATION_SKIPPED", "1.0")),  # [safe-default] binary 0.0/1.0; tune via calibration scripts
"no_verification": float(os.environ.get("WORKER_THRESHOLD_NO_VERIFICATION", "1.0")),  # [safe-default] binary 0.0/1.0; tune via calibration scripts
"incomplete_verification": float(os.environ.get("WORKER_THRESHOLD_INCOMPLETE_VERIFICATION", "0.7")),  # [safe-default] calibration value; tune via calibration scripts
```

#### `WORKER_AGENT_ROUTING_GRAPH` env var parse — add near other env var reads, before `main()` (D-05):
```python
import json as _json

_routing_graph_raw = os.environ.get("WORKER_AGENT_ROUTING_GRAPH", "")
AGENT_ROUTING_GRAPH: dict[str, list[str]] | None = (
    _json.loads(_routing_graph_raw) if _routing_graph_raw.strip() else None
)
```

#### TraceAnalyzer instantiation (line 194) — add `routing_graph=` kwarg (D-06):
```python
# Before (Phase 25):
trace_analyzer = TraceAnalyzer(embedder, THRESHOLDS)

# After (Phase 26):
trace_analyzer = TraceAnalyzer(embedder, THRESHOLDS, routing_graph=AGENT_ROUTING_GRAPH)
```

---

### `xeter/scripts/calibrate.py` — FLAG_TYPE_TO_ANALYZER_CLASS + DEFAULT_THRESHOLDS

**Analog:** same file, lines 83-105 (Phase 25 registry block) and lines 120-134 (DEFAULT_THRESHOLDS block).

#### FLAG_TYPES list (lines 51-73) — append 6 new entries after `"history_loss"`:
```python
# Phase 25 — TraceAnalyzer
"stale_context",
"step_repetition",
"termination_loop",
"context_propagation_failure",
"history_loss",
```
Add:
```python
# Phase 26 — TraceAnalyzer (best-effort proxy checks)
"wrong_agent_handoff",
"information_withholding",
"conversation_reset",
"clarification_skipped",
"no_verification",
"incomplete_verification",
```

#### FLAG_TYPE_TO_ANALYZER_CLASS (lines 99-105) — append 6 entries after Phase 25 TraceAnalyzer block:
```python
# Phase 25 — TraceAnalyzer
"stale_context":                 TraceAnalyzer,
"step_repetition":               TraceAnalyzer,
"termination_loop":              TraceAnalyzer,
"context_propagation_failure":   TraceAnalyzer,
"history_loss":                  TraceAnalyzer,
```
Add:
```python
# Phase 26 — TraceAnalyzer (best-effort proxy checks)
"wrong_agent_handoff":           TraceAnalyzer,
"information_withholding":       TraceAnalyzer,
"conversation_reset":            TraceAnalyzer,
"clarification_skipped":         TraceAnalyzer,
"no_verification":               TraceAnalyzer,
"incomplete_verification":       TraceAnalyzer,
```

#### DEFAULT_THRESHOLDS (lines 126-134) — append 6 entries after Phase 25 block:
```python
# Phase 25
"missing_details": 0.6,
"stale_context": 85.0,
"context_propagation_failure": 0.5,
"history_loss": 0.4,
"step_repetition": 85.0,
"termination_loop_n": 3,
```
Add:
```python
# Phase 26
"conversation_reset": 0.25,
"information_withholding": 0.5,
"wrong_agent_handoff": 1.0,
"clarification_skipped": 1.0,
"no_verification": 1.0,
"incomplete_verification": 0.7,
```

Note: no `BINARY_FLAG_TYPES` entries for any Phase 26 type — deferred to Phase 27 per D-14.

---

### New test file for Phase 26 checks

**Location:** `xeter/tests/test_trace_analyzer_phase26.py`
**Analog:** `xeter/tests/test_trace_analyzer.py` (Phase 25 version, lines 1-473)

#### File header + imports pattern (lines 1-23):
```python
"""Tests for TraceAnalyzer — Phase 26 proxy checks.

Covers all 6 new check methods:
  - _check_wrong_agent_handoff       (TRACE-05)
  - _check_information_withholding   (TRACE-06)
  - _check_conversation_reset        (TRACE-07)
  - _check_clarification_skipped     (TRACE-08)
  - _check_no_verification           (TRACE-09)
  - _check_incomplete_verification   (TRACE-10)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from xeter.services.worker.trace_analyzer import TraceAnalyzer
```

#### `_make_spans` helper (lines 29-60) — copy exactly, same signature:
```python
def _make_spans(n: int, **per_span_overrides) -> list:
    from xeter.services.worker.base import SpanData

    spans = []
    for i in range(n):
        fields = dict(
            span_id=f"s{i}",
            tenant_id="t1",
            trace_id="tr1",
            agent_name="ag",
            agent_model="gpt-4o",
            tool_name=None,
            tool_description=None,
            tool_arguments=None,
            tool_output=None,
            prompt=None,
            response=None,
            raw_response=None,
            available_tools=None,
        )
        for k, v in per_span_overrides.items():
            fields[k] = v[i] if isinstance(v, list) else v
        spans.append(SpanData(**fields))
    return spans
```

#### `_make_trace_analyzer` helper (lines 63-82) — extend thresholds dict for Phase 26:
```python
def _make_trace_analyzer(thresholds=None, routing_graph=None) -> TraceAnalyzer:
    mock_emb = MagicMock()
    mock_emb.encode.return_value = np.ones(384)
    mock_emb.encode_batch.return_value = [np.ones(384)]

    default_thresholds = {
        # Phase 25 (required for analyze() dispatch to existing checks)
        "stale_context": 85.0,
        "step_repetition": 85.0,
        "termination_loop_n": 3,
        "context_propagation_failure": 0.5,
        "history_loss": 0.4,
        # Phase 26
        "conversation_reset": 0.25,
        "information_withholding": 0.5,
        "wrong_agent_handoff": 1.0,
        "clarification_skipped": 1.0,
        "no_verification": 1.0,
        "incomplete_verification": 0.7,
    }
    if thresholds is not None:
        default_thresholds.update(thresholds)

    return TraceAnalyzer(mock_emb, default_thresholds, routing_graph=routing_graph)
```

#### Test structure pattern — fires / no-fires / detail / logs-score (copy per-check group from Phase 25):

Each check gets 3–4 tests following this exact naming convention:
```
test_{check_name}_fires_when_{condition}
test_{check_name}_no_flag_when_{condition}
test_{check_name}_detail_has_low_confidence_true   # only for low_confidence checks
test_{check_name}_logs_score                        # only for score-logging checks
```

Pattern for a flag-fires assertion (copy from Phase 25 test line 117-131):
```python
def test_conversation_reset_fires_when_prompt_disconnected_abruptly():
    ta = _make_trace_analyzer({"conversation_reset": 0.25})
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    ta._embedder.encode.return_value = np.zeros(384)
    spans = _make_spans(3, prompt=["a", "b", "totally unrelated reset"])
    flags = ta.analyze(spans)
    assert any(f.flag_type == "conversation_reset" for f in flags)
```

Pattern for `low_confidence` detail assertion (copy from Phase 25 test line 159-174):
```python
def test_conversation_reset_detail_has_low_confidence_true():
    ta = _make_trace_analyzer({"conversation_reset": 0.25})
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    ta._embedder.encode.return_value = np.zeros(384)
    spans = _make_spans(3, prompt=["a", "b", "totally unrelated reset"])
    flags = [f for f in ta.analyze(spans) if f.flag_type == "conversation_reset"]
    assert len(flags) > 0, "Expected at least one conversation_reset flag"
    assert flags[0].detail.get("low_confidence") is True
```

Pattern for log_score assertion (copy from Phase 25 test line 352-367):
```python
def test_conversation_reset_logs_score():
    ta = _make_trace_analyzer({"conversation_reset": 0.25})
    ta._embedder.encode.return_value = np.ones(384)
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    spans = _make_spans(3, prompt=["a", "b", "c"])
    ta.analyze(spans)
    scores = ta.flush_scores()
    assert any(metric == "conversation_reset" for _, metric, _ in scores)
```

#### Mutual-exclusion test pattern (D-12 — unique to Phase 26):
```python
def test_no_verification_and_incomplete_verification_never_both_fire():
    ta = _make_trace_analyzer()
    # Provide a trace with no verification keyword → no_verification fires
    spans = _make_spans(2, tool_name=["search", "fetch"], tool_description=["find", "retrieve"])
    flags = ta.analyze(spans)
    no_ver = [f for f in flags if f.flag_type == "no_verification"]
    inc_ver = [f for f in flags if f.flag_type == "incomplete_verification"]
    assert not (no_ver and inc_ver), "no_verification and incomplete_verification must not both fire"
```

---

## Shared Patterns

### log_score BEFORE threshold — mandatory invariant
**Source:** `xeter/services/worker/trace_analyzer.py` lines 104-106, 145-147, 233-235, 274-277
**Apply to:** Every `_check_*` method that computes a numeric score
```python
# CRITICAL: log BEFORE threshold comparison (D-04 invariant)
self.log_score("metric_key", score)
if score < self._thresholds["metric_key"]:   # or >=, depending on check direction
    flags.append(...)
```
Binary checks (wrong_agent_handoff, clarification_skipped, no_verification) log `1.0` when fired, `0.0` when not, still before any conditional append.

### Flag.detail always has "metric" key
**Source:** `xeter/services/worker/trace_analyzer.py` lines 108-115, 150-156, 194-201, 240-243, 280-285
**Apply to:** All 6 new `_check_*` methods
```python
detail={
    "metric": "<flag_type>",
    # optional: "span_index": i, "low_confidence": True
}
```

### No numeric threshold literals in check methods
**Source:** `xeter/services/worker/base.py` lines 23-24 (docstring) + every `_check_*` method
**Apply to:** All 6 new `_check_*` methods — always read from `self._thresholds["key"]`

### span_id=None for trace-level flags
**Source:** Established in v1.4; `Flag` dataclass in `xeter/services/worker/base.py` line 40 has no `span_id` field — flags are written at the trace level, span_id column is NULL (handled by `write_flags` call in `_flush_stale_traces` line 161 which passes `None` as span_id)

### Guard early return before any computation
**Source:** `xeter/services/worker/trace_analyzer.py` lines 93-94, 128-129, 166-167, 218-219, 259-260
**Apply to:** All 6 new `_check_*` methods — `return []` before any embedding/NE computation

---

## No Analog Found

All files have close analogs. No entries.

---

## Metadata

**Analog search scope:** `xeter/services/worker/`, `xeter/scripts/`, `xeter/tests/`
**Files scanned:** 5 source files, 1 test file
**Pattern extraction date:** 2026-05-26

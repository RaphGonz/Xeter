# Phase 25: Semantic Span + Structural Trace Checks - Pattern Map

**Mapped:** 2026-05-24
**Files analyzed:** 6 (2 new, 4 modified)
**Analogs found:** 6 / 6

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `xeter/services/worker/semantic_span_analyzer.py` | service/analyzer | request-response | `xeter/services/worker/output_schema_analyzer.py` | exact |
| `xeter/services/worker/trace_analyzer.py` | service/analyzer | event-driven (batch flush) | `xeter/services/worker/tool_call_analyzer.py` | role-match |
| `xeter/services/worker/main.py` | config/wiring | request-response | self (existing file, additive) | self |
| `xeter/scripts/calibrate.py` | config/registry | batch | self (existing file, additive) | self |
| `xeter/tests/test_semantic_span_analyzer.py` | test | request-response | `xeter/tests/test_calibrate_routing.py` | role-match |
| `xeter/tests/test_trace_analyzer.py` | test | event-driven | `xeter/tests/test_calibrate_routing.py` | role-match |

---

## Pattern Assignments

### `xeter/services/worker/semantic_span_analyzer.py` (new, service, request-response)

**Analog:** `xeter/services/worker/output_schema_analyzer.py`
**Secondary analog for spaCy helpers:** `xeter/services/worker/tool_call_analyzer.py`

**Imports pattern** (output_schema_analyzer.py lines 18-26, tool_call_analyzer.py lines 18-37):
```python
from __future__ import annotations

from typing import Optional

import numpy as np

from xeter.services.worker.base import BaseSpanAnalyzer, Flag, SpanData, bow_score, hybrid_score
```
Notes:
- `bow_score` and `hybrid_score` are imported from `base.py` — both are needed for `missing_details` hybrid scoring.
- No `jsonschema` or `tiktoken` — this analyzer uses spaCy + embeddings.
- `numpy` needed for embedding operations.

**Lazy-load pattern for spaCy** (tool_call_analyzer.py lines 43-51):
```python
_NLP = None


def _get_spacy():
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load("en_core_web_md")
    return _NLP
```
Copy this pattern verbatim into `semantic_span_analyzer.py`. Rationale: spaCy model load is ~1s cold — lazy init avoids paying it at import time.

**Class signature + constructor** (output_schema_analyzer.py lines 48-59):
```python
class OutputSchemaAnalyzer(BaseSpanAnalyzer):
    """Deterministic span-level schema and context-overflow checks.

    Does not override __init__ — inherits (embedder, thresholds) constructor
    from BaseAnalyzer (D-06). The embedder is accepted for interface consistency
    but never called by any check method in this class.
    """

    @property
    def name(self) -> str:
        """Stable analyzer name used as analyzer_name in span_scores rows."""
        return "output_schema"

    def analyze(self, span: SpanData) -> list[Flag]:
        ...
        flags: list[Flag] = []
        flags.extend(self._check_output_schema_violation(span))
        ...
        return flags
```
For `SemanticSpanAnalyzer`, replicate exactly:
- No `__init__` override — inherits `(embedder, thresholds)` from `BaseAnalyzer`.
- `name` property returns `"semantic_span"`.
- `analyze()` dispatches to a single `_check_missing_details(span)` helper and returns the combined list.

**Core check method structure — guard + log_score + flag** (output_schema_analyzer.py lines 79-101):
```python
def _check_output_schema_violation(self, span: SpanData) -> list[Flag]:
    if span.expected_output_schema is None:
        return []
    if span.response is None:
        return []
    try:
        json.loads(span.response)
        self.log_score("output_schema_violation", 0.0)
        return []
    except (json.JSONDecodeError, ValueError):
        self.log_score("output_schema_violation", 1.0)
        return [Flag(
            flag_type="output_schema_violation",
            score=1.0,
            detail={"metric": "output_schema_violation"},
        )]
```
For `_check_missing_details`, the structure is:
1. Guard: `if span.prompt is None: return []` then `if span.response is None: return []`.
2. Compute hybrid score (cosine + BOW).
3. `self.log_score("missing_details", score)` — BEFORE threshold comparison (mandatory invariant).
4. `if score < self._thresholds["missing_details"]:` → return Flag; else return `[]`.

Flag shape to use:
```python
Flag(
    flag_type="missing_details",
    score=score,
    detail={
        "metric": "missing_details",
        "cosine": round(cosine, 4),
        "bow": round(bow, 4),
    },
)
```

**Entity-recall helper pattern** (tool_call_analyzer.py lines 110-121 — `_lemma_set`):
```python
def _lemma_set(text: str) -> set[str]:
    """Return the set of lowercase content-word lemmas from text (spaCy)."""
    nlp = _get_spacy()
    return {
        token.lemma_.lower()
        for token in nlp(text)
        if token.is_alpha and not token.is_stop
    }
```
For `missing_details`, "items explicitly requested in prompt" can be extracted via spaCy noun chunks or NER. The planner should use a similar lemma-set approach: extract lemma set from `span.prompt`, compute overlap fraction against `span.response` lemma set, and combine with cosine as the hybrid signal.

**log_score invariant** (output_schema_analyzer.py line 271-274, tool_call_analyzer.py line 447):
```python
# CRITICAL: log BEFORE threshold comparison (D-04 invariant)
self.log_score("prompt_token_count", float(token_count))
threshold = self._thresholds["context_overflow"]
if token_count > threshold:
```
Every check must call `self.log_score(metric, score)` before `if score < self._thresholds[key]`.

---

### `xeter/services/worker/trace_analyzer.py` (modify — fill stub)

**Analog:** `xeter/services/worker/tool_call_analyzer.py`

**Current stub** (trace_analyzer.py lines 1-38, full file):
```python
from __future__ import annotations
from xeter.services.worker.base import BaseTraceAnalyzer, EmbedderClient, Flag, SpanData

class TraceAnalyzer(BaseTraceAnalyzer):
    def __init__(self, embedder: EmbedderClient, thresholds: dict[str, float]) -> None:
        super().__init__(embedder, thresholds)

    @property
    def name(self) -> str:
        return "trace_analyzer"

    def analyze(self, spans: list[SpanData]) -> list[Flag]:
        return []
```

**Imports to add** (derive from tool_call_analyzer.py lines 18-37 + base.py imports):
```python
from __future__ import annotations

import numpy as np
from rapidfuzz import fuzz

from xeter.services.worker.base import BaseTraceAnalyzer, EmbedderClient, Flag, SpanData, bow_score, hybrid_score
```
Notes:
- `rapidfuzz.fuzz` needed for `stale_context` (ratio) and `step_repetition` (token_sort_ratio).
- `numpy` needed for `history_loss` centroid computation (`np.mean`).
- `bow_score`, `hybrid_score` from `base.py` for `context_propagation_failure`.

**spaCy lazy-load** (tool_call_analyzer.py lines 43-51) — copy verbatim into trace_analyzer.py:
```python
_NLP = None

def _get_spacy():
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load("en_core_web_md")
    return _NLP
```

**analyze() dispatch pattern** (tool_call_analyzer.py lines 150-160, output_schema_analyzer.py lines 61-73):
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
Replace the current stub `return []` with this dispatch. Each helper returns `list[Flag]`.

**Trace-level guard pattern** (from CONTEXT.md § Established Patterns + specifics):
```python
def _check_stale_context(self, spans: list[SpanData]) -> list[Flag]:
    if len(spans) < 2:
        return []
    flags: list[Flag] = []
    for i in range(1, len(spans)):
        if spans[i - 1].tool_output is None:
            continue
        if spans[i].prompt is None:
            continue
        # ... compute score ...
        self.log_score("stale_context", score)
        if score >= self._thresholds["stale_context"]:
            flags.append(Flag(
                flag_type="stale_context",
                score=score,
                detail={"metric": "stale_context", "span_index": i, "low_confidence": True},
            ))
    return flags
```
Key invariants:
- `span_id=None` for all trace-level flags (flags writer called with `span_id=None` — already established in main.py lines 151-152).
- `low_confidence: True` in detail for `stale_context` only (D-06).
- Guard `if len(spans) < 2: return []` for all 5 trace checks.
- Guard `if len(spans) < 3: return []` for `_check_history_loss` specifically.

**Flag.detail structure** (tool_call_analyzer.py lines 196-205, base.py lines 39-42):
```python
@dataclass
class Flag:
    flag_type: str
    score: float
    detail: dict        # always includes "metric" key
```
All flags must have `"metric"` key in detail. Trace-specific flags add `"span_index": i` where relevant.

**rapidfuzz pattern** (from CONTEXT.md D-05, D-06, requirements):
```python
from rapidfuzz import fuzz

# stale_context — character-level edit ratio (0–100)
score = fuzz.ratio(spans[i].prompt, spans[i - 1].tool_output)

# step_repetition — word-order-invariant ratio (0–100)
key_a = f"{span_a.tool_name} {span_a.tool_arguments}"
key_b = f"{span_b.tool_name} {span_b.tool_arguments}"
score = fuzz.token_sort_ratio(key_a, key_b)
```

**history_loss centroid pattern** (from CONTEXT.md D-07, D-08):
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
        self.log_score("history_loss", score)
        if score < self._thresholds["history_loss"]:
            flags.append(Flag(
                flag_type="history_loss",
                score=score,
                detail={"metric": "history_loss", "span_index": i},
            ))
    return flags
```
Uses `self._embedder.encode_batch()` (base.py lines 77-81) for batch efficiency. `np.mean(..., axis=0)` computes the centroid.

---

### `xeter/services/worker/main.py` (modify — additive)

**Analog:** self (existing file)

**Import addition** (after line 46 in current file):
```python
from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer
```
Insert after the existing `from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer` import on line 45.

**THRESHOLDS additions** (current THRESHOLDS dict lines 53-60):
```python
THRESHOLDS: dict[str, float] = {
    # ... existing entries ...
    # Phase 25 — SemanticSpanAnalyzer
    "missing_details": float(os.environ.get("WORKER_THRESHOLD_MISSING_DETAILS", "0.6")),
    # Phase 25 — TraceAnalyzer
    "stale_context": float(os.environ.get("WORKER_THRESHOLD_STALE_CONTEXT", "85.0")),
    "context_propagation_failure": float(os.environ.get("WORKER_THRESHOLD_CONTEXT_PROPAGATION_FAILURE", "0.5")),
    "history_loss": float(os.environ.get("WORKER_THRESHOLD_HISTORY_LOSS", "0.4")),
    "step_repetition": float(os.environ.get("WORKER_THRESHOLD_STEP_REPETITION", "85.0")),
    "termination_loop_n": float(os.environ.get("WORKER_THRESHOLD_TERMINATION_LOOP_N", "3")),
}
```
Pattern: each entry follows `"key": float(os.environ.get("WORKER_THRESHOLD_KEY", "default"))`. No bare numeric literals. Comments reference the phase that added the entry.

**ANALYZERS list addition** (current lines 179-182):
```python
analyzers = [
    ToolCallAnalyzer(embedder, THRESHOLDS),
    OutputSchemaAnalyzer(embedder, THRESHOLDS),
    SemanticSpanAnalyzer(embedder, THRESHOLDS),   # Phase 25 — span-level semantic check
]
```
`TraceAnalyzer` is already constructed separately on line 184 — no change needed there.

---

### `xeter/scripts/calibrate.py` (modify — additive)

**Analog:** self (existing file)

**Import addition** (after line 27):
```python
from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer
from xeter.services.worker.trace_analyzer import TraceAnalyzer
```
Insert after the existing `from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer` import.

**FLAG_TYPES list additions** (current lines 48-62):
```python
FLAG_TYPES = [
    # ... existing 12 entries ...
    # Phase 25 — SemanticSpanAnalyzer
    "missing_details",
    # Phase 25 — TraceAnalyzer
    "stale_context",
    "step_repetition",
    "termination_loop",
    "context_propagation_failure",
    "history_loss",
]
```

**FLAG_TYPE_TO_ANALYZER_CLASS additions** (current lines 72-86):
```python
FLAG_TYPE_TO_ANALYZER_CLASS: dict[str, type] = {
    # ... existing 12 entries ...
    # Phase 25 — SemanticSpanAnalyzer
    "missing_details":               SemanticSpanAnalyzer,
    # Phase 25 — TraceAnalyzer
    "stale_context":                 TraceAnalyzer,
    "step_repetition":               TraceAnalyzer,
    "termination_loop":              TraceAnalyzer,
    "context_propagation_failure":   TraceAnalyzer,
    "history_loss":                  TraceAnalyzer,
}
```

**DEFAULT_THRESHOLDS additions** (current lines 101-108):
```python
DEFAULT_THRESHOLDS: dict[str, float] = {
    # ... existing entries ...
    # Phase 25
    "missing_details": 0.6,
    "stale_context": 85.0,
    "context_propagation_failure": 0.5,
    "history_loss": 0.4,
    "step_repetition": 85.0,
    "termination_loop_n": 3,
}
```
No BINARY_FLAG_TYPES additions in Phase 25 (D-12).

**CRITICAL: calibrate.py uses `analyzer.analyze(span)` for span analyzers** (lines 198-200). TraceAnalyzer takes `spans: list[SpanData]`. The `evaluate_flag_type()` function currently passes a single span. For trace-level flag types, either:
1. The planner must wrap the single span in a list when calling `analyzer.analyze([span])`, OR
2. A dedicated `evaluate_trace_flag_type()` function is needed.
The planner should decide the cleanest approach; the pattern to reference is lines 195-203 of calibrate.py.

---

### `xeter/tests/test_semantic_span_analyzer.py` (new test)

**Analog:** `xeter/tests/test_calibrate_routing.py` + `xeter/tests/test_span_data_fields.py`

**File header pattern** (test_calibrate_routing.py lines 1-11):
```python
"""Tests for SemanticSpanAnalyzer — missing_details check.

Plan: 25-XX
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
```

**Minimal SpanData factory** (test_span_data_fields.py lines 19-37):
```python
def _minimal_span(**kwargs):
    from xeter.services.worker.base import SpanData
    defaults = dict(
        span_id="s1", tenant_id="t1", trace_id="tr1",
        agent_name="ag", agent_model="gpt-4o",
        tool_name=None, tool_description=None, tool_arguments=None,
        tool_output=None, prompt=None, response=None,
        raw_response=None, available_tools=None,
    )
    defaults.update(kwargs)
    return SpanData(**defaults)
```

**Mock embedder factory** (test_calibrate_routing.py lines 73-89 pattern):
```python
def _mock_embedder(vector=None):
    import numpy as np
    mock = MagicMock()
    vec = vector if vector is not None else np.ones(384)
    mock.encode.return_value = vec
    mock.encode_batch.return_value = [vec]
    return mock
```

**Test structure for a span-level check method** (pattern from test_calibrate_routing.py lines 68-119):
```python
def test_missing_details_returns_no_flag_when_prompt_is_none():
    from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer
    embedder = _mock_embedder()
    thresholds = {"missing_details": 0.6}
    analyzer = SemanticSpanAnalyzer(embedder, thresholds)
    span = _minimal_span(prompt=None, response="some response")
    flags = analyzer.analyze(span)
    assert flags == []

def test_missing_details_returns_flag_when_score_below_threshold():
    from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer
    import numpy as np
    # Return orthogonal vectors to force cosine=0 → hybrid score below threshold
    embedder = _mock_embedder()
    embedder.encode.side_effect = [np.array([1,0]*192), np.array([0,1]*192)]
    thresholds = {"missing_details": 0.6}
    analyzer = SemanticSpanAnalyzer(embedder, thresholds)
    span = _minimal_span(prompt="specific details about X and Y", response="vague answer")
    flags = analyzer.analyze(span)
    assert any(f.flag_type == "missing_details" for f in flags)

def test_missing_details_logs_score_before_threshold():
    # Verify log_score is called (calibration invariant)
    from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer
    import numpy as np
    embedder = _mock_embedder()
    thresholds = {"missing_details": 0.6}
    analyzer = SemanticSpanAnalyzer(embedder, thresholds)
    span = _minimal_span(prompt="do X", response="I did X")
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    assert any(metric == "missing_details" for _, metric, _ in scores)
```

---

### `xeter/tests/test_trace_analyzer.py` (new test)

**Analog:** `xeter/tests/test_calibrate_routing.py` + `xeter/tests/test_span_data_fields.py`

**Minimal trace factory** (derive from `_minimal_span` pattern):
```python
def _make_spans(n: int, **per_span_overrides) -> list:
    """Build a list of n minimal SpanData objects sharing trace_id='tr1'."""
    from xeter.services.worker.base import SpanData
    spans = []
    for i in range(n):
        overrides = {k: v[i] if isinstance(v, list) else v
                     for k, v in per_span_overrides.items()}
        spans.append(SpanData(
            span_id=f"s{i}", tenant_id="t1", trace_id="tr1",
            agent_name="ag", agent_model="gpt-4o",
            tool_name=None, tool_description=None, tool_arguments=None,
            tool_output=None, prompt=None, response=None,
            raw_response=None, available_tools=None,
            **overrides,
        ))
    return spans
```

**TraceAnalyzer instantiation pattern**:
```python
def _make_trace_analyzer(thresholds=None):
    from xeter.services.worker.trace_analyzer import TraceAnalyzer
    mock_emb = MagicMock()
    mock_emb.encode.return_value = np.ones(384)
    mock_emb.encode_batch.return_value = [np.ones(384)]
    return TraceAnalyzer(mock_emb, thresholds or {
        "stale_context": 85.0,
        "step_repetition": 85.0,
        "termination_loop_n": 3,
        "context_propagation_failure": 0.5,
        "history_loss": 0.4,
    })
```

**Test structure per check**:
```python
def test_analyze_returns_empty_list_for_single_span():
    """All 5 checks guard len(spans) < 2; single-span trace returns []."""
    ta = _make_trace_analyzer()
    spans = _make_spans(1, prompt="hello", tool_output="world")
    assert ta.analyze(spans) == []

def test_stale_context_fires_when_prompt_copies_prior_tool_output():
    ta = _make_trace_analyzer({"stale_context": 50.0, ...})
    text = "the exact same text repeated verbatim"
    spans = _make_spans(2, prompt=[None, text], tool_output=[text, None])
    flags = ta.analyze(spans)
    assert any(f.flag_type == "stale_context" for f in flags)

def test_stale_context_detail_has_low_confidence_true():
    ta = _make_trace_analyzer({"stale_context": 50.0, ...})
    text = "verbatim content that triggers stale_context"
    spans = _make_spans(2, prompt=[None, text], tool_output=[text, None])
    flags = [f for f in ta.analyze(spans) if f.flag_type == "stale_context"]
    assert flags[0].detail.get("low_confidence") is True

def test_history_loss_skips_traces_shorter_than_3():
    ta = _make_trace_analyzer()
    spans = _make_spans(2, prompt=["a", "b"])
    flags = [f for f in ta.analyze(spans) if f.flag_type == "history_loss"]
    assert flags == []
```

---

## Shared Patterns

### log_score Before Threshold (mandatory invariant — all check methods)
**Source:** `xeter/services/worker/output_schema_analyzer.py` lines 92-93, 171-172, 204-205, 250-251 and `xeter/services/worker/tool_call_analyzer.py` lines 447-448
**Apply to:** Every `_check_*()` method in both new/modified files
```python
# Compute score first
score = <similarity computation>
# MUST log BEFORE threshold comparison — calibration dataset completeness
self.log_score("<metric_name>", score)
# THEN compare
if score <op> self._thresholds["<key>"]:
    return [Flag(...)]
return []
```

### No Numeric Literals in Check Methods
**Source:** `xeter/services/worker/base.py` lines 22-25, `xeter/services/worker/output_schema_analyzer.py` line 273
**Apply to:** All check methods
```python
# BAD:
if score > 0.6:
# GOOD:
threshold = self._thresholds["missing_details"]
if score > threshold:
```

### Guard Pattern — Early Return Without log_score
**Source:** `xeter/services/worker/output_schema_analyzer.py` lines 86-89, 162-163, 193-194
**Apply to:** All check methods
```python
if span.prompt is None:
    return []   # no log_score — span did not participate in this check
```
For trace checks: `if len(spans) < 2: return []` (all 5 checks); `if len(spans) < 3: return []` (`_check_history_loss` specifically).

### Flag.detail Always Has "metric" Key
**Source:** `xeter/services/worker/base.py` lines 39-42, `xeter/services/worker/output_schema_analyzer.py` lines 96-101
**Apply to:** All Flag constructions
```python
Flag(
    flag_type="<flag_type>",
    score=score,
    detail={"metric": "<metric_name>", ...extra_keys...},
)
```

### Lazy-Load Heavy Imports (spaCy)
**Source:** `xeter/services/worker/tool_call_analyzer.py` lines 43-51
**Apply to:** `semantic_span_analyzer.py`, `trace_analyzer.py`
```python
_NLP = None

def _get_spacy():
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load("en_core_web_md")
    return _NLP
```

### Test Mock Embedder Pattern
**Source:** `xeter/tests/test_calibrate_routing.py` lines 73-89
**Apply to:** Both new test files
```python
mock_embedder = MagicMock()
mock_embedder.analyze.return_value = []
mock_embedder.flush_scores.return_value = []
```

---

## No Analog Found

No files fall into this category — all 6 files have close analogs.

---

## Key Constraints Extracted from Canonical Refs

| Constraint | Source | Applies To |
|---|---|---|
| `log_score` BEFORE threshold | base.py line 117 comment; output_schema_analyzer.py throughout | All check methods |
| No numeric literals in check methods | base.py lines 22-25 | All check methods |
| `Flag.detail` always has `"metric"` key | base.py line 42 comment | All Flag constructions |
| `span_id=None` for trace-level flags | main.py lines 151-152 (write_flags call pattern) | All TraceAnalyzer flags |
| `low_confidence: True` in detail | CONTEXT.md D-06 | `stale_context` only |
| SemanticSpanAnalyzer: no `__init__` override | output_schema_analyzer.py lines 53-54 | semantic_span_analyzer.py |
| TraceAnalyzer: existing `__init__` takes `(embedder, thresholds)` | trace_analyzer.py line 18 | trace_analyzer.py |
| `_check_history_loss` guard: `< 3` spans | CONTEXT.md D-08 + specifics | trace_analyzer.py |
| All other trace checks guard: `< 2` spans | CONTEXT.md code_context section | trace_analyzer.py |
| `stale_context` uses `fuzz.ratio` (not `token_sort_ratio`) | CONTEXT.md D-05 | _check_stale_context |
| `step_repetition` uses `fuzz.token_sort_ratio` | REQUIREMENTS.md TRACE-01 | _check_step_repetition |
| `termination_loop_n` = consecutive occurrences, not total | CONTEXT.md specifics | _check_termination_loop |
| `history_loss` uses `encode_batch` for centroid | base.py lines 77-81 | _check_history_loss |

---

## Metadata

**Analog search scope:** `xeter/services/worker/`, `xeter/scripts/`, `xeter/tests/`
**Files scanned:** 8 (output_schema_analyzer.py, tool_call_analyzer.py, trace_analyzer.py, base.py, main.py, calibrate.py, test_calibrate_routing.py, test_span_data_fields.py)
**Pattern extraction date:** 2026-05-24

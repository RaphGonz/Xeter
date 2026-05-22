# Phase 25: Semantic Span + Structural Trace Checks - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 25 delivers 6 new detection checks across two analyzers — no new schema migrations, no new infra (all deps landed in Phase 23):

**Span-level (new `SemanticSpanAnalyzer(BaseSpanAnalyzer)`):**
1. **`missing_details`** (CTX-04): `response` does not semantically cover items explicitly requested in `prompt` — hybrid cosine + spaCy entity-recall

**Trace-level (filling the `TraceAnalyzer` stub):**
2. **`stale_context`** (CTX-02): span[i].prompt closely matches span[i-1].tool_output via rapidfuzz.fuzz.ratio — marked `low_confidence: true`
3. **`step_repetition`** (TRACE-01): trace contains duplicate/near-duplicate (tool_name, tool_arguments) pairs via rapidfuzz.fuzz.token_sort_ratio
4. **`termination_loop`** (TRACE-02): same tool called N+ times in sequence without a distinct exit
5. **`context_propagation_failure`** (TRACE-03): span[i].prompt is missing key information from span[i-1].tool_output — spaCy lemma overlap or hybrid cosine
6. **`history_loss`** (TRACE-04): span[i].prompt is semantically disconnected from the centroid of all prior span prompts — embedding cosine; minimum 3 spans

Also: calibrate.py registry entries (FLAG_TYPE_TO_ANALYZER_CLASS + starting thresholds) for all 6 new flag types — no BINARY_FLAG_TYPES entries yet (Phase 27 decides).

</domain>

<decisions>
## Implementation Decisions

### CTX-02 class placement
- **D-01:** `stale_context` (CTX-02) moves to `TraceAnalyzer` as `_check_stale_context(spans)`. `BaseSpanAnalyzer` contract is unchanged — no signature changes. CTX-02 needs trace context (comparing span[i] prompt vs span[i-1] tool_output) so it belongs in the trace analyzer where all spans are available.
- **D-02:** `missing_details` (CTX-04) lives in a new `SemanticSpanAnalyzer(BaseSpanAnalyzer)` class in `xeter/services/worker/semantic_span_analyzer.py` — parallel file structure to `output_schema_analyzer.py`.
- **D-03:** `TraceAnalyzer.analyze(spans)` uses `_check_*()` helper methods for all 5 trace checks, matching the ToolCallAnalyzer pattern. Each helper returns `list[Flag]`; results are combined in `analyze()`.

### Stale context detection
- **D-04:** `_check_stale_context(spans)` compares each span[i].prompt against span[i-1].tool_output ONLY (immediately prior span). No sliding window, no multi-hop — simple O(n) pass. Guard: skip if span has no prior span (i == 0) or if prior span has no tool_output.
- **D-05:** Similarity via `rapidfuzz.fuzz.ratio` (character-level edit distance ratio, returns 0–100). Not token_sort_ratio — literal/near-literal reuse is the signal.
- **D-06:** Starting threshold `THRESHOLDS['stale_context'] = 85.0`. Flag includes `"low_confidence": True` in `Flag.detail`.

### history_loss centroid
- **D-07:** Centroid = mean of embeddings of ALL prior span prompts (span[0]...span[i-1]) for each span[i]. Full history, stable signal — traces are short enough that cost is minimal.
- **D-08:** Minimum trace length guard — `_check_history_loss` skips entirely on traces with < 3 spans (returns `[]`). Need at least 2 prior prompts to establish a meaningful centroid.
- **D-09:** `_check_context_propagation_failure(spans)` compares span[i].prompt against span[i-1].tool_output ONLY (immediately prior), consistent with D-04 for stale_context. Detection method: spaCy lemma overlap OR hybrid cosine, whichever the planner determines is most appropriate given the existing `hybrid_score()` utility.

### Calibration scaffolding
- **D-10:** Phase 25 adds all 6 new flag types to `FLAG_TYPE_TO_ANALYZER_CLASS` in `calibrate.py`: `missing_details` → `SemanticSpanAnalyzer`; `stale_context`, `step_repetition`, `termination_loop`, `context_propagation_failure`, `history_loss` → `TraceAnalyzer`. This prevents a KeyError if calibrate.py is invoked before Phase 27.
- **D-11:** Starting threshold values added to `THRESHOLDS` / `DEFAULT_THRESHOLDS`:
  - `stale_context`: 85.0 (rapidfuzz ratio, 0–100 scale)
  - `missing_details`: 0.6 (hybrid cosine, consistent with `no_tool` baseline)
  - `context_propagation_failure`: 0.5 (spaCy/hybrid cosine)
  - `history_loss`: 0.4 (embedding cosine; lower bar given centroid noise)
  - `step_repetition`: 85.0 (token_sort_ratio, 0–100 scale)
  - `termination_loop_n`: 3 (integer count — same tool called 3+ times in sequence)
- **D-12:** No `BINARY_FLAG_TYPES` entries in Phase 25. Phase 27 makes the final binary vs threshold decision for each check after all v1.5 checks land and a full calibration dataset exists.

### Claude's Discretion
- Missing_details detection detail: hybrid cosine + spaCy entity-recall exact implementation (how to extract "entities explicitly requested in prompt" via spaCy — NER, noun chunks, or named entities). Planner to decide based on existing spaCy patterns in tool_call_analyzer.py.
- step_repetition key: whether to compare `(tool_name + " " + tool_arguments)` as a single string or as a tuple; planner decides based on what produces the clearest rapidfuzz comparison.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Analyzer base classes and patterns
- `xeter/services/worker/base.py` — `BaseSpanAnalyzer`, `BaseTraceAnalyzer`, `SpanData` dataclass, `Flag` dataclass, `log_score()` contract, `hybrid_score()`, `bow_score()`, `EmbedderClient.encode()` + `EmbedderClient.encode_batch()`
- `xeter/services/worker/tool_call_analyzer.py` — canonical `_check_*()` helper pattern, `_get_spacy()` lazy-load pattern, `Flag.detail` structure with `"metric"` key
- `xeter/services/worker/output_schema_analyzer.py` — parallel file structure for `SemanticSpanAnalyzer`; same `__init__(self, embedder, thresholds)` constructor signature

### Stub to fill
- `xeter/services/worker/trace_analyzer.py` — current stub: `analyze()` returns `[]`. Phase 25 fills it with 5 `_check_*()` method calls for CTX-02 + TRACE-01–04.

### Registration points (must update)
- `xeter/services/worker/main.py` — `ANALYZERS` list: add `SemanticSpanAnalyzer(embedder, THRESHOLDS)`; `THRESHOLDS` dict: add 6 new entries (D-11)
- `xeter/scripts/calibrate.py` — `FLAG_TYPE_TO_ANALYZER_CLASS` registry: add 6 entries (D-10); `DEFAULT_THRESHOLDS`: add starting values (D-11); NO `BINARY_FLAG_TYPES` entries yet

### Prior phase context (constraint sources)
- `.planning/phases/24-structural-span-checks/24-CONTEXT.md` — D-04 (log_score invariant: log BEFORE threshold), D-06 (OutputSchemaAnalyzer constructor pattern — SemanticSpanAnalyzer must match)
- `.planning/phases/23-infrastructure/23-CONTEXT.md` — D-05 (registry pattern), D-08 (recall floor R≥0.10), D-09 (jsonschema/tiktoken/rapidfuzz in pyproject.toml + Dockerfile)

### Requirements (phase scope source)
- `.planning/REQUIREMENTS.md` — §CTX-02, §CTX-04, §TRACE-01, §TRACE-02, §TRACE-03, §TRACE-04 — exact detection logic per requirement

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BaseSpanAnalyzer` in `base.py` — subclass for `SemanticSpanAnalyzer`; `analyze(span: SpanData) -> list[Flag]`
- `BaseTraceAnalyzer` in `base.py` — already wired into worker; `TraceAnalyzer` subclasses it; `analyze(spans: list[SpanData]) -> list[Flag]`
- `_get_spacy()` lazy-loader in `tool_call_analyzer.py` — copy this pattern for `SemanticSpanAnalyzer` (spaCy load is slow; lazy init avoids paying it at import time)
- `hybrid_score(cosine, bow)` + `bow_score(a, b)` in `base.py` — reuse for `missing_details` and `context_propagation_failure` hybrid scoring
- `self._embedder.encode(text)` → np.ndarray; `self.compare(a, b)` → cosine similarity — available on all `BaseAnalyzer` subclasses

### Established Patterns
- `log_score(metric, score)` called BEFORE threshold comparison — mandatory invariant (every span/trace must contribute to calibration dataset regardless of flag outcome)
- `Flag(flag_type=..., score=..., detail={"metric": "...", ...})` — `detail` always has `"metric"` key; add `"low_confidence": True` for CTX-02 (`stale_context`)
- No numeric threshold literals in check methods — always `self._thresholds["key"]`
- Guard pattern: `if span.field is None: return []` early in each check method before processing
- For trace checks: guard `if len(spans) < 2: return []` before iterating (handle degenerate single-span traces)

### Integration Points
- New file: `xeter/services/worker/semantic_span_analyzer.py` — parallel to `output_schema_analyzer.py`
- `xeter/services/worker/trace_analyzer.py` — add `_check_stale_context`, `_check_step_repetition`, `_check_termination_loop`, `_check_context_propagation_failure`, `_check_history_loss` methods; replace stub `return []` in `analyze()` with calls to these helpers
- `xeter/services/worker/main.py` ANALYZERS list — append `SemanticSpanAnalyzer(embedder, THRESHOLDS)`
- `xeter/services/worker/main.py` THRESHOLDS dict — add 6 new keys (D-11)
- `xeter/scripts/calibrate.py` `FLAG_TYPE_TO_ANALYZER_CLASS` — add 6 entries (D-10)
- `xeter/scripts/calibrate.py` `DEFAULT_THRESHOLDS` — add 6 starting values (D-11)

</code_context>

<specifics>
## Specific Ideas

- `stale_context` uses `rapidfuzz.fuzz.ratio` (not token_sort_ratio) — literal/near-literal reuse is the signal, not word-order similarity
- `step_repetition` uses `rapidfuzz.fuzz.token_sort_ratio` on `(tool_name, tool_arguments)` pairs per REQUIREMENTS.md spec
- `termination_loop_n = 3` — configurable as `THRESHOLDS['termination_loop_n']`; the check counts consecutive occurrences of the same `tool_name` without interruption, not total count in trace
- `history_loss` minimum: 3 spans (guard: `if len(spans) < 3: return []` in `_check_history_loss`)
- All trace checks write span_id=None to flags (established in v1.4 when flags.span_id was made nullable for trace-level flags)

</specifics>

<deferred>
## Deferred Ideas

- BINARY_FLAG_TYPES classification for the 6 new checks — Phase 27 scope after full calibration dataset exists
- Actual calibration run for new flag types — Phase 27 scope
- CTX-03 (`prompt_injection`) — permanently cut from v1.5 scope (per Phase 24 context D-02)

</deferred>

---

*Phase: 25-semantic-span-structural-trace-checks*
*Context gathered: 2026-05-22*

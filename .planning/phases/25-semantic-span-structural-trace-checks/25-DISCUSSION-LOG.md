# Phase 25: Semantic Span + Structural Trace Checks - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 25-semantic-span-structural-trace-checks
**Areas discussed:** CTX-02 class placement, Stale context lookup window, history_loss centroid scope, Phase 25 calibration scaffolding

---

## CTX-02 Class Placement

| Option | Description | Selected |
|--------|-------------|----------|
| TraceAnalyzer — iterate spans in order | CTX-02 moves to TraceAnalyzer. When the trace flushes, iterate spans and compare each span's prompt vs prior span's tool_output via rapidfuzz. Cleanest — no signature changes needed. | ✓ |
| SemanticSpanAnalyzer with trace history | Change analyze() signature to accept optional trace_history: list[SpanData]. Worker passes buffered prior spans at dispatch time. | |
| Fetch prior span from ClickHouse at check time | SpanData has parent_span_id. Span analyzer makes a DB fetch inside _check_stale_context(). Avoids architecture changes but adds a network call per span. | |

**User's choice:** TraceAnalyzer — iterate spans in order

**Sub-question: SemanticSpanAnalyzer file structure?**

| Option | Description | Selected |
|--------|-------------|----------|
| New file: semantic_span_analyzer.py | Parallel to output_schema_analyzer.py. One class, one file. | ✓ |
| Add CTX-04 to OutputSchemaAnalyzer | Fewer files, but conflates structural schema checks with semantic embedding checks. | |

**Sub-question: TraceAnalyzer internal structure for 5 new checks?**

| Option | Description | Selected |
|--------|-------------|----------|
| _check_*() helper methods | Same pattern as ToolCallAnalyzer. Each method returns list[Flag]. Easy to test in isolation. | ✓ |
| All inline in analyze() | Single method, no helpers. Simpler for now but hard to read with 5 checks. | |

**Notes:** The key constraint is that BaseSpanAnalyzer.analyze(span) only receives a single SpanData. CTX-02 needs prior span context, so it naturally belongs in the trace path. CTX-04 (prompt vs response within one span) stays span-level.

---

## Stale Context Lookup Window

| Option | Description | Selected |
|--------|-------------|----------|
| Immediately prior span only | For span[i], compare prompt against span[i-1].tool_output only. O(n) across trace. | ✓ |
| Last N spans (configurable) | Compare against the last N spans' tool_outputs. Catches multi-hop reuse but produces more comparisons. | |
| All prior spans in trace | Compare prompt against every prior span's tool_output. O(n²) but traces are typically short. | |

**User's choice:** Immediately prior span only

**Sub-question: rapidfuzz function?**

| Option | Description | Selected |
|--------|-------------|----------|
| rapidfuzz.fuzz.ratio | Character-level edit distance ratio. Good at detecting verbatim or near-verbatim reuse. | ✓ |
| rapidfuzz.fuzz.token_sort_ratio | Tokenizes and sorts before comparing — better for word-order variations. | |
| rapidfuzz.fuzz.partial_ratio | Substring matching — could produce false positives on short tool outputs. | |

**Sub-question: starting threshold?**

| Option | Description | Selected |
|--------|-------------|----------|
| 85.0 | rapidfuzz ratio returns 0–100. 85 = 85% character overlap. High enough to avoid false positives. | ✓ |
| 75.0 | More aggressive — higher false positive rate. | |
| You decide | Leave to calibration. | |

**Notes:** stale_context is marked low_confidence: true regardless of threshold, so erring toward precision with 85.0 is appropriate.

---

## history_loss Centroid Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Mean of ALL prior spans' embeddings | For span[i], centroid = mean of embeddings of span[0]...span[i-1] prompts. Full history, stable signal. | ✓ |
| Sliding window of last N spans | Centroid from last N span prompts only. More sensitive to recent drift but adds second threshold parameter. | |
| Fixed centroid from first 3 spans | Anchor topic using only first 3 spans. Stable but doesn't account for legitimate topic evolution. | |

**User's choice:** Mean of ALL prior spans' embeddings

**Sub-question: minimum trace length?**

| Option | Description | Selected |
|--------|-------------|----------|
| 3 spans minimum | Need at least 2 prior spans to establish a meaningful centroid before checking span[2+]. | ✓ |
| 2 spans minimum | Centroid from span[0] only — single-vector 'centroid'. Technically valid but noisy. | |
| No minimum | Skip guard entirely. | |

**Sub-question: TRACE-03 context_propagation_failure scope?**

| Option | Description | Selected |
|--------|-------------|----------|
| Immediately prior span's tool_output only | Consistent with stale_context approach. Check span[i].prompt vs span[i-1].tool_output. | ✓ |
| Any prior span's tool_output (max scan) | Check against ALL prior spans' tool_outputs, take minimum similarity. Noisier. | |

**Notes:** history_loss is about the trace drifting from its established topic — mean of all prior spans is the cleanest centroid signal.

---

## Phase 25 Calibration Scaffolding

| Option | Description | Selected |
|--------|-------------|----------|
| Registry + starting thresholds, no calibration run | Add all 6 new flag types to FLAG_TYPE_TO_ANALYZER_CLASS and starting THRESHOLDS. No BINARY_FLAG_TYPES entries yet — Phase 27 decides. | ✓ |
| Full scaffolding including BINARY_FLAG_TYPES | Also register structural trace checks in BINARY_FLAG_TYPES now. | |
| Defer entirely to Phase 27 | Zero calibration scaffolding — risk: calibrate.py crashes on new flag types. | |

**User's choice:** Registry + starting thresholds, no calibration run

**Sub-question: starting threshold values?**

| Option | Description | Selected |
|--------|-------------|----------|
| Use proposed defaults | stale_context: 85.0, missing_details: 0.6, context_propagation_failure: 0.5, history_loss: 0.4, step_repetition: 85.0 | ✓ |
| You decide | Leave all starting values to the planner. | |

**Sub-question: termination_loop repeat threshold?**

| Option | Description | Selected |
|--------|-------------|----------|
| N=3 | Same tool called 3+ times in sequence. Catches real loops without firing on legitimate retries. | ✓ |
| N=4 | More conservative. | |
| N=2 | Too aggressive — fires on any back-to-back duplicate. | |

**Notes:** Phase 27 will make the final binary vs threshold call for each check. Phase 25 just needs the registry entries to prevent crashes.

---

## Claude's Discretion

- **missing_details entity extraction approach:** How to extract "entities explicitly requested in prompt" via spaCy (NER, noun chunks, or named entities). Planner to decide based on existing spaCy patterns in tool_call_analyzer.py.
- **step_repetition key format:** Whether to compare (tool_name + " " + tool_arguments) as a single string or as a tuple. Planner decides based on what produces the clearest rapidfuzz comparison.
- **context_propagation_failure detection method:** spaCy lemma overlap OR hybrid cosine — planner picks based on hybrid_score() utility already in base.py.

## Deferred Ideas

- BINARY_FLAG_TYPES classification for all 6 new checks — Phase 27 scope
- Actual calibration run for new flag types — Phase 27 scope
- CTX-03 (prompt_injection) — permanently cut from v1.5 scope (per Phase 24)

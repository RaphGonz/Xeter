# Feature Research — Silent Failure Detection Checks

**Domain:** AI observability — silent failure detection for AI agent spans and traces (v1.5 milestone)
**Researched:** 2026-05-18
**Confidence:** HIGH (span-level heuristic checks), MEDIUM (trace-level pattern checks), LOW (multi-agent handoff checks — signal depends heavily on what instrumentation upstream agents emit)

---

## Context

v1.4 shipped. The existing `ToolCallAnalyzer` (span-level) covers A-category checks. The
`TraceAnalyzer` scaffold (`analyze() → []`) is wired and ready. This research covers
**18 new detection checks** across two categories:

- **Span-level (8 checks):** B1–B4, D3, D5, E3, H2 — implemented in a new `SilentFailureAnalyzer`
  subclassing `BaseSpanAnalyzer`
- **Trace-level (10 checks):** C3, C4, D1, D2, F1, F2, F4, F5, G1, G2 — implemented inside
  `TraceAnalyzer.analyze(spans)`, which already receives the full flushed span list

---

## Table Stakes

Features that any serious AI observability tool targeting silent failures must have.
Missing these means the platform cannot claim B/C/D/G category coverage.

| Check | Name | Why Expected | Detection Signal | Span vs Trace | Complexity |
|-------|------|--------------|-----------------|---------------|------------|
| B1 | Output schema not respected | Free text when structured output expected is the most common LLM output failure in production pipelines | `response` field JSON-parse attempt; if fails AND prompt contains schema keywords (`json`, `schema`, `structured`, `format`, `output as`) → flag | Single span | LOW |
| B2 | Required fields missing | Structural schema validation — downstream consumers silently get None/KeyError | Parse `response` as JSON; compare keys against expected schema (if declared in span metadata) or check for null/empty values in parsed object | Single span | LOW–MEDIUM |
| B3 | Output truncated | JSON/response cut before close is a common context-window side-effect that passes HTTP 200 | Response ends without closing delimiter: unclosed `{`, `[`, or trailing `...`, or response token count near model's max_tokens | Single span | LOW |
| D3 | Context truncation / prompt overflow | Prompt exceeds context window causes silent oldest-content drop; models don't warn | Token-count estimate (chars / 4 heuristic) vs known model context limits; OR check `raw_response` for finish_reason=`length` | Single span | LOW |
| G1 | No verification | Agent produces output with no self-check step in the trace | Count of spans in trace that mention verify/check/confirm/validate in tool_name or response; 0 = flag | Trace | LOW–MEDIUM |
| C3 | Step repetition | Agent loops on same action without new information justifying it | Across spans in trace: hash (tool_name + normalized tool_arguments) and count duplicates; threshold ≥ 2 identical hashes | Trace | LOW |
| C4 | Termination loop / unaware of stopping | Agent cannot halt; loops indefinitely | Span count in trace exceeds configurable threshold (e.g., 20 spans); OR repeated identical response embeddings across consecutive spans | Trace | LOW |
| D1 | Context propagation failure | Critical upstream output not passed to dependent agent — the most common multi-agent failure | Compare key entities/values from span N's response with span N+1's prompt using lemma-set overlap or embedding similarity; low overlap = flag | Trace (2-span window) | MEDIUM |

---

## Differentiators

Features beyond baseline that distinguish Xeter's silent failure coverage. These require
semantic understanding, not just structural inspection.

| Check | Name | Value Proposition | Detection Signal | Span vs Trace | Complexity |
|-------|------|-------------------|-----------------|---------------|------------|
| B4 | Type coercion errors | Catches semantically wrong but structurally valid outputs that pass JSON parsing | Parse `response` JSON; for each field, check if numeric string where number expected, boolean as 0/1 where bool expected, date as integer epoch, etc. | Single span | MEDIUM |
| D5 | Stale context | Agent cites prior turn data that has been superseded in the same trace | Across trace spans: if a tool output in span N explicitly supersedes an earlier value (same entity, newer timestamp or explicit "updated" signal), check if span N+2+ still references the old value via embedding similarity | Trace (windowed) | MEDIUM–HIGH |
| E3 | Prompt injection / hijacking | Detects adversarial content in tool outputs redirecting agent behavior | Tool output contains imperative overrides: regex for `ignore previous instructions`, `disregard`, `you are now`, `new task`, `forget` + variants; OR embedding distance between original task vector and post-tool-call action vector exceeds threshold | Single span | MEDIUM |
| H2 | Missing details | Response succeeds but omits explicitly requested information | Embed prompt and response; extract key noun phrases / named entities from prompt; check entity recall in response using lemma-set overlap; flag when recall < threshold | Single span | MEDIUM–HIGH |
| D2 | Conversation history loss | Agent forgets prior state mid-trace and re-derives known facts | In trace, later spans re-ask questions already answered in earlier spans — detect via embedding similarity between later prompt and earlier response content | Trace | MEDIUM |
| F1 | Wrong agent handoff | Routing to wrong downstream agent based on agent_name changes across spans | Across trace spans: when `agent_name` transitions, compare the handing-off span's response with the receiving span's declared role/description; semantic mismatch flags | Trace | MEDIUM (depends on agent metadata) |
| F2 | Information withholding | Agent passes incomplete context to next agent | When `agent_name` transitions: compare entity coverage between handing-off span's response and receiving span's prompt; below-threshold overlap = flag | Trace | MEDIUM |
| G2 | Incomplete verification | Verification step exists but checks only a subset | Identify spans with verify-related tool/response content; check that verified entities in that span cover the entities claimed in the preceding production span | Trace (2-span window) | HIGH |
| F4 | Conversation reset | An agent resets shared state, losing prior context | Early spans in trace accumulate context; later span prompt length drops dramatically (>50% token reduction) AND earlier unique entities absent from current prompt | Trace | MEDIUM |
| F5 | Fail to clarify | Agent proceeds on ambiguous instruction instead of requesting clarification | High ambiguity signal in prompt (multiple conflicting intents, pronouns without referents, disjunctive instructions "do X or Y") + no clarification request in response + downstream error flag | Single span + trace correlation | HIGH |

---

## Anti-Features

Checks to explicitly NOT build in v1.5.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| LLM-as-judge for every check | Every check → LLM call makes the worker 10–50x slower per span; cost is unbounded | Reserve LLM judgment for the Diagnosticer (on-demand). All 18 checks must use heuristics, regex, token counting, or embeddings only |
| Real schema registry | Requiring agents to register output schemas creates a major SDK burden; most agents don't have formal schemas | Infer expected structure from prompt keywords; check for JSON-parse success + non-empty result |
| Per-field type inference | Deep type inference (e.g., "this field should be a UUID") requires schema knowledge that isn't available | Flag obvious coercions: number-as-string, bool-as-0/1 — leave edge cases unflagged rather than false-positive |
| Cross-tenant trace comparison | Comparing traces across tenants to detect "unusual" behavior | Per-tenant calibration is safer and avoids data leakage |
| Streaming/real-time trace analysis | Per-span flush would fire trace checks before the trace is complete | Trace-level checks run only after flush timeout, as designed in v1.4 |

---

## Feature Dependencies

```
[B1 output_schema_not_respected]
    └──shares JSON-parse logic──> [B2 required_fields_missing]
                                      └──shares JSON-parse logic──> [B3 output_truncated]
                                                                         └──shares token-count──> [D3 context_truncation]

[E3 prompt_injection]
    └──uses embed()──> [D5 stale_context]

[H2 missing_details]
    └──uses lemma-set overlap (same as _check_wrong_tool containment guard)──> [D2 conversation_history_loss]

[D1 context_propagation_failure]
    └──2-span window pattern──> [F2 information_withholding]
                                    └──agent_name transition guard──> [F1 wrong_agent_handoff]
                                                                           └──same agent boundary detection──> [F4 conversation_reset]

[G1 no_verification]
    └──identifies verify-spans first──> [G2 incomplete_verification]

[C3 step_repetition]
    └──span count accumulation──> [C4 termination_loop]
```

### Dependency Notes

- **B1–B3 share the same JSON-parse attempt.** A single `_try_parse_json(response)` helper returns `(parsed, error)` and all three checks consume it. This avoids three redundant parse calls per span.
- **G2 requires G1's span identification.** G2 only runs when G1 identifies a verification span in the trace; without G1 pinpointing which spans are verification steps, G2 has no anchor to evaluate completeness against.
- **F1/F2/F4 require agent_name transitions.** If all spans in a trace have the same `agent_name`, these checks short-circuit immediately and produce no flags. They only activate in multi-agent traces.
- **D1 and F2 are closely related** but D1 fires on any span-to-span context gap (same or different agent), while F2 fires specifically at agent_name transition boundaries.
- **C3 must run before C4** in the same pass — C3's duplicate-hash set is cheap and informs whether C4's loop count is genuinely new work or repetition.

---

## Single-Span vs Multi-Span Boundary

This boundary is architecturally load-bearing. Span-level checks run in `ToolCallAnalyzer`-style span processors; trace-level checks run in `TraceAnalyzer.analyze(spans)` after flush timeout.

### Single-Span Checks (implement in new `SilentFailureAnalyzer(BaseSpanAnalyzer)`)

| Check | Primary Signal | Secondary Signal |
|-------|---------------|-----------------|
| B1 | JSON parse fail on `response` + prompt schema keywords | — |
| B2 | JSON parse success + null/missing key check | Optional: compare against schema if declared |
| B3 | Unclosed JSON delimiters OR `finish_reason=length` in `raw_response` | Response char length near model limit |
| B4 | Type mismatch patterns in parsed JSON values | Regex: `"[0-9]+"` where bare int expected |
| D3 | Token estimate (len/4) > model_context_limit | `finish_reason=length` in `raw_response` |
| D5 | Temporal/version signal in tool output vs prior span response (requires recent prior span reference — BORDERLINE) | Can be approximated single-span with tool output timestamp vs prompt timestamp |
| E3 | Injection regex on `tool_output` field | Embedding drift: pre-call task vec vs post-call action vec |
| H2 | Lemma recall: prompt entities in response | Embedding similarity (prompt vs response) — already available via `response_anomaly` score |

Note: D5 is marked borderline — its best detection requires comparing tool output recency against prior-span data. A single-span approximation (does the tool output contain a timestamp newer than the prompt?) is feasible but misses the case where staleness comes from the agent ignoring a tool result already available in the same trace.

### Multi-Span (Trace-Level) Checks (implement in `TraceAnalyzer.analyze(spans)`)

| Check | Window Size | Primary Signal |
|-------|------------|----------------|
| C3 | All spans | Duplicate (tool_name + args_hash) count ≥ threshold |
| C4 | All spans | Total span count ≥ threshold OR consecutive identical response hashes |
| D1 | Rolling 2-span window | Entity/embedding overlap between span[N].response and span[N+1].prompt below threshold |
| D2 | Full trace | Later span re-derives a value already present in an earlier span response |
| F1 | Agent transition boundary | Semantic mismatch between handing-off span's response topic and receiving agent's declared role |
| F2 | Agent transition boundary | Entity coverage gap: span[N].response entities not present in span[N+1].prompt |
| F4 | Full trace | Prompt token count drops >50% at any span transition |
| F5 | Single span + trace | High ambiguity score on prompt AND no clarifying question in response AND subsequent error flag |
| G1 | Full trace | Zero spans with verification signals (tool_name or response contains verify/check/validate) |
| G2 | 2-span window (production → verify) | Entity recall: what G1 identified as verified vs what was produced |

---

## Table Stakes vs Differentiators Summary

| Category | Checks | Detection Approach | Calibration Difficulty | False Positive Risk |
|----------|---------|--------------------|----------------------|---------------------|
| **Table stakes** | B1, B3, D3, C3, C4, G1 | Structural/heuristic (JSON parse, token count, hash comparison, span count, keyword search) | LOW — thresholds are count-based or binary | LOW — structural signals are unambiguous |
| **Table stakes** | B2 | Structural + light semantic | LOW–MEDIUM | MEDIUM — depends on whether schema is known |
| **Differentiators** | B4, E3, H2, D1, F4 | Regex + embedding + lemma overlap | MEDIUM | MEDIUM — embedding thresholds need calibration |
| **Differentiators** | D2, D5, F1, F2, G2, F5 | Semantic + multi-span reasoning | HIGH | HIGH — prone to false positives without careful calibration |

---

## Calibration Difficulty Per Check

| Check | Difficulty | Reason | Calibration Approach |
|-------|-----------|--------|---------------------|
| B1 | LOW | Binary: JSON parse succeeds or fails | No threshold needed; keyword guard prevents false positives when response is legitimately plain text |
| B2 | LOW–MEDIUM | Needs schema expectation; null check is reliable, missing-field check needs field name list | Flag only when response is valid JSON but has null/empty values across all fields |
| B3 | LOW | Structural: unclosed delimiter or `finish_reason=length` is unambiguous | `finish_reason=length` in `raw_response` is the most reliable signal; delimiter check has edge cases (embedded strings) |
| B4 | MEDIUM | Type patterns require careful regex to avoid flagging legitimate string representations | Restrict to clear cases: `"true"/"false"` as strings, numeric strings in known-numeric contexts |
| D3 | LOW | Token count heuristic (chars/4) is approximate but directionally reliable; `finish_reason=length` is exact | Use `finish_reason=length` when available; fall back to token estimate with a safety margin (90% of limit) |
| D5 | HIGH | "Staleness" is inherently relative — what counts as outdated requires a reference timeline | Best-effort: flag only when tool output contains an explicit newer timestamp than what appears in prior span context |
| E3 | MEDIUM | Regex catches known patterns; novel injections evade it; embedding drift is noisy | Maintain a curated injection phrase list; embedding drift threshold needs calibration against known-clean traces |
| H2 | HIGH | Entity recall requires reliable NER; short responses to complex prompts are legitimate AND flaggable | Set conservative threshold; use spaCy NER (already lazy-loaded) for entity extraction |
| C3 | LOW | Hash comparison is exact; "same args" is unambiguous | Normalize args (sort keys, lowercase strings) before hashing to catch semantic duplicates with minor formatting differences |
| C4 | LOW | Span count threshold is a blunt but reliable signal | Default threshold of 20 spans; expose as `WORKER_THRESHOLD_C4_MAX_SPANS` env var |
| D1 | MEDIUM | Entity/embedding overlap between sequential spans — legitimate topic changes look like propagation failures | Use combined lemma-set + embedding hybrid (existing `hybrid_score()`) |
| D2 | HIGH | Must distinguish "agent re-derives because it forgot" from "agent re-confirms for accuracy" | Compare whether re-derived value matches original; mismatch = likely D2; match = likely G2 (verification) |
| F1 | MEDIUM | Agent role metadata may not be available in spans; depends on instrumentation quality | Best-effort: if agent_name metadata is absent from spans, skip check rather than false-flag |
| F2 | MEDIUM | Distinguishing intentional summarization from information withholding is hard | Threshold on entity recall at handoff boundaries; calibrate against known-good multi-agent traces |
| F4 | LOW–MEDIUM | Token count drop is structural; 50% is a heuristic threshold | Flag only when drop is large AND the dropped content contained unique named entities |
| F5 | HIGH | Ambiguity detection in prompts requires semantic reasoning; "proceed confidently" and "proceed with ambiguity" look identical | Restrict to clear signals: multiple disjunctive instructions (`or`/`either`) + no `?` in response |
| G1 | LOW–MEDIUM | Keyword search for verification signals is fast; absence of verification is structural | Use both tool_name keywords AND response content keywords; at least one span in trace must show verification |
| G2 | HIGH | Requires identifying what was "supposed to be verified" from prior production span | Anchor on G1's identified verification span; compare entity coverage with the immediately preceding non-verification span |

---

## Known False Positive Risks

| Check | False Positive Scenario | Mitigation |
|-------|------------------------|------------|
| B1 | Prompt asks for a "summary" or "explanation" — plain text is correct | Guard: only flag when prompt contains explicit schema keywords (`json`, `{`, `schema`, `format`, `structured output`) |
| B2 | Partial response is intentional (agent returns subset of schema on first step) | Guard: only flag when ALL non-nullable fields are null/missing simultaneously |
| B3 | Legitimate responses that end with an ellipsis in markdown | Guard: delimiter check only for JSON responses (B1 preceded it); exclude plain-text responses |
| D3 | Large prompts for summarization tasks (expected to be large) | Guard: only flag when `finish_reason=length` is explicit; avoid flagging large-but-valid prompts without this signal |
| E3 | Tool output legitimately contains instructional text (e.g., a README being processed) | Restrict injection patterns to clear override keywords; avoid flagging instructional content |
| H2 | Agent intentionally defers part of the answer to a subsequent tool call | Low-confidence flag only; correlate with subsequent spans to see if deferred content is later produced |
| D1 | Agent intentionally reformulates context (e.g., summarizes before passing) | Use entity recall not verbatim matching; reformulation preserves key entities |
| D2 | Agent re-confirms a known fact as part of verification (G2 pattern) | Check whether the re-derived value matches the original; if it matches, it's likely G2 not D2 |
| F1 | Single-agent traces with varying `agent_name` (versioning or tool names) | Short-circuit if only one unique `agent_name` in trace |
| G1 | Very short traces (1–2 spans) where verification step is in a subsequent unflushed trace | Set minimum trace length guard: G1 only fires on traces with ≥ 3 spans |
| C3 | Polling patterns (legitimate repeated queries for status updates) | Guard: require that args contain identical content (not just same tool); polling has incrementing parameters |
| C4 | Batch processing traces (legitimately many spans for multi-item processing) | Correlate with C3: if C3 fires, C4 is likely real; if C3 does not fire (no repetition), raise C4 threshold |

---

## MVP Recommendation

### Build First (v1.5 Phase 1 — table stakes + simple heuristics)

These are low-complexity, low-false-positive-risk, and form the core "silent failure" story:

1. **B1** (output_schema_not_respected) — JSON parse + schema keyword guard
2. **B3** (output_truncated) — `finish_reason=length` + unclosed delimiter
3. **D3** (context_truncation) — token estimate + `finish_reason=length`
4. **C3** (step_repetition) — hash comparison across spans
5. **C4** (termination_loop) — span count threshold
6. **G1** (no_verification) — keyword scan across trace spans

### Build Second (v1.5 Phase 2 — semantic checks with calibration)

7. **B2** (required_fields_missing) — JSON + null field detection
8. **B4** (type_coercion) — regex type mismatch patterns
9. **E3** (prompt_injection) — injection regex on tool_output
10. **H2** (missing_details) — entity recall via spaCy NER
11. **D1** (context_propagation_failure) — hybrid overlap between adjacent spans
12. **F4** (conversation_reset) — token count drop detection
13. **D2** (conversation_history_loss) — re-derivation detection

### Defer or Best-Effort (v1.5 Phase 3 — high calibration difficulty)

14. **D5** (stale_context) — best-effort timestamp comparison
15. **F1** (wrong_agent_handoff) — requires agent metadata; best-effort
16. **F2** (information_withholding) — entity recall at handoff boundaries
17. **G2** (incomplete_verification) — anchored on G1; high calibration cost
18. **F5** (fail_to_clarify) — disjunctive prompt detection; high false positive risk

---

## Implementation Notes

### New `SilentFailureAnalyzer(BaseSpanAnalyzer)`

A second concrete span-level analyzer. Add to `ANALYZERS` list in `worker/main.py` alongside
`ToolCallAnalyzer`. The existing worker dispatch loop (iterates over `analyzers`) handles this
with zero structural changes.

Checks that share logic (B1/B2/B3 JSON parse, H2/D2 entity overlap) should use shared
`_try_parse_json()` and `_extract_entities()` private methods to avoid redundant computation.

### `TraceAnalyzer` — Implement `analyze(spans)`

The scaffold already exists. Implement checks in this priority order per Phase:
- Phase 1: C3, C4, G1 (structural, zero embedding calls)
- Phase 2: D1, D2, F4 (embedding calls, use `hybrid_score()`)
- Phase 3: F1, F2, G2, F5, D5 (high complexity, best-effort)

Each check should be a private `_check_*` method matching the pattern established in
`ToolCallAnalyzer`. This makes unit testing and calibration per-method straightforward.

### Threshold Keys (add to `THRESHOLDS` dict in `worker/main.py`)

```python
# Span-level
"output_schema_not_respected":   0.0,   # binary — no threshold, keyword guard only
"output_truncated":               0.0,   # binary — structural signal
"context_truncation":             0.9,   # fraction of model context limit (token estimate)
"type_coercion":                  0.0,   # binary — pattern match
"prompt_injection":               0.0,   # binary — regex match
"missing_details":                0.5,   # entity recall threshold

# Trace-level
"step_repetition_min_count":      2,     # duplicate hashes needed to flag
"termination_loop_max_spans":    20,     # trace span count upper bound
"context_propagation_min_sim":    0.3,   # hybrid overlap floor between adjacent spans
"conversation_history_loss":      0.7,   # similarity floor for re-derivation detection
"conversation_reset_drop":        0.5,   # fraction of token count drop to flag
"no_verification_min_spans":      3,     # minimum trace length before G1 fires
```

All keys follow the existing pattern: `self._thresholds["key"]` — no numeric literals in check methods.

### spaCy Reuse

`_get_spacy()` and `_extract_non_negated_clauses()` are already in `tool_call_analyzer.py`.
Move these to `base.py` as shared helpers, or create a `xeter/services/worker/nlp_helpers.py`
module. Both `SilentFailureAnalyzer` and `ToolCallAnalyzer` need spaCy.

---

## Sources

- IBM Research: Detecting Silent Failures in Multi-Agentic AI Trajectories (arXiv 2511.04032) — taxonomy source for B/D/E/H category descriptions
- Berkeley MAST: Why Do Multi-Agent LLM Systems Fail? (arXiv 2503.13657, NeurIPS 2025) — taxonomy source for C/F/G category descriptions and failure mode definitions; κ = 0.88 inter-annotator agreement confirms these are real, observable failure modes
- [Detecting AI Agent Failure Modes in Production — Latitude](https://latitude.so/blog/ai-agent-failure-detection-guide) — observability-driven diagnosis patterns, span-level vs trace-level signal
- [Why Multi-Agent Systems Fail — Galileo](https://galileo.ai/blog/why-multi-agent-systems-fail) — context propagation, handoff failure patterns
- [Context Window Overflow — Redis](https://redis.io/blog/context-window-overflow/) — token count detection, `finish_reason=length` as primary D3 signal
- [How to Detect Prompt Injection — ARMO](https://www.armosec.io/blog/how-to-detect-prompt-injection-in-production-ai-agent-workloads/) — three-layer detection (regex, heuristic, semantic); tool output scanning for E3
- Codebase direct review: `worker/base.py`, `worker/tool_call_analyzer.py`, `worker/trace_analyzer.py`, `worker/main.py`, `documentation/silent_failures_ai_agents.md`, `.planning/PROJECT.md`

---

*Feature research for: Xeter v1.5 Silent Failure Detection*
*Researched: 2026-05-18*

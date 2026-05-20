# Requirements: Xeter v1.5

**Defined:** 2026-05-18
**Core Value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.

## v1.5 Requirements

### INFRA — Infrastructure Prerequisites

- [x] **INFRA-01**: Worker processes pending trace flushes on BRPOP timeout — idle traces (last trace in queue, no subsequent span arrival) are flushed and analyzed correctly; trace flags fire in test conditions that send exactly N spans and stop
- [x] **INFRA-02**: TraceAnalyzer score data is persisted — `flush_scores()` called and results written to `span_scores` after each trace flush; calibration dataset includes trace-level metrics
- [ ] **INFRA-03**: `calibrate.py` supports multiple analyzer classes — new flag types route to the correct analyzer instance; hill-climb enforces a minimum recall floor (R ≥ 0.10) to prevent degenerate `P=1.0, R=0.0` convergence
- [x] **INFRA-04**: Worker `pyproject.toml` includes `jsonschema==4.26.0`, `tiktoken==0.13.0`, `rapidfuzz==3.14.5`
- [x] **INFRA-05**: `SpanData` has `expected_output_schema: Optional[dict]` field; corresponding ClickHouse column added (additive, nullable); `span_fetcher.py` maps it
- [x] **INFRA-06**: `SpanData` has `parent_span_id: Optional[str]` field; confirmed present or added to ClickHouse `spans` table; `span_fetcher.py` maps it

### SCHEMA — Output/Schema Failure Checks (span-level, new OutputSchemaAnalyzer)

- [ ] **SCHEMA-01** (B1): System flags `output_schema_violation` when model returns free text instead of structured output — detected via JSON parse failure on `response` when `expected_output_schema` is set or `raw_response` shows no tool_use/function_call blocks despite `available_tools` being present
- [ ] **SCHEMA-02** (B2): System flags `required_fields_missing` when `tool_arguments` validates against `expected_output_schema` but required fields are absent or null — detected via `jsonschema` `required` validator errors
- [ ] **SCHEMA-03** (B3): System flags `output_truncated` when model output is cut short — primary signal: `finish_reason=length` in `raw_response`; fallback: unclosed JSON delimiter in `response` or `tool_arguments`
- [ ] **SCHEMA-04** (B4): System flags `type_coercion_error` when `tool_arguments` contains type violations against `expected_output_schema` — detected via `jsonschema` `type` validator errors (number-as-string, boolean-as-integer, etc.)

### CTX — Context/Content Checks (span-level, new OutputSchemaAnalyzer)

- [ ] **CTX-01** (D3): System flags `context_overflow` when prompt token count exceeds a model-context threshold — counted via `tiktoken` with `cl100k_base` fallback; threshold configurable per `THRESHOLDS` dict
- [ ] **CTX-02** (D5): System flags `stale_context` (best-effort) when tool output appears reused across spans without re-query — detected via `rapidfuzz` similarity between current span's prompt and a prior span's `tool_output` in the same trace context passed via span metadata; marked `low_confidence: true` in flag detail
- [ ] **CTX-03** (E3): System flags `prompt_injection` when `tool_output` contains patterns consistent with adversarial instruction injection — detected via curated `_INJECTION_PATTERNS` regex list compiled at module load; optional semantic gate via embedder if regex precision is low post-calibration
- [ ] **CTX-04** (H2): System flags `missing_details` when `response` does not semantically cover items explicitly requested in `prompt` — detected via hybrid cosine + spaCy entity-recall score between prompt and response; threshold configurable

### TRACE — Trace-Level Checks (TraceAnalyzer real implementation)

- [ ] **TRACE-01** (C3): System flags `step_repetition` when a trace contains duplicate or near-duplicate tool calls — detected via `rapidfuzz.fuzz.token_sort_ratio` on `(tool_name, tool_arguments)` pairs across spans; fires when ratio exceeds threshold for any two spans
- [ ] **TRACE-02** (C4): System flags `termination_loop` when the same tool is called N+ times in a trace without a distinct exit condition — detected via span count per `tool_name` exceeding a configurable repeat threshold
- [ ] **TRACE-03** (D1): System flags `context_propagation_failure` when a later span's prompt is missing key information from an earlier span's `tool_output` — detected via spaCy lemma overlap or hybrid cosine below threshold between prior `tool_output` and subsequent `prompt`
- [ ] **TRACE-04** (D2): System flags `history_loss` when a later span's prompt is semantically disconnected from the trace's established topic — detected via embedding cosine between the later span's prompt and a centroid of earlier spans' prompts falling below threshold
- [ ] **TRACE-05** (F1): System flags `wrong_agent_handoff` (best-effort) when the sequence of `agent_name` values in a trace deviates from an expected pattern — detected via unexpected agent transitions using a configurable `AGENT_ROUTING_GRAPH` dict (defaults to no-flag if not configured); marked `low_confidence: true`
- [ ] **TRACE-06** (F2): System flags `information_withholding` when an agent's `response` contains key entities not passed to the subsequent span's `prompt` — detected via spaCy named-entity recall between current `response` and next span's `prompt`
- [ ] **TRACE-07** (F4): System flags `conversation_reset` (best-effort) when an abrupt topic shift occurs mid-trace — detected via embedding cosine between a span's prompt and the trace centroid of prior prompts falling below a reset threshold; marked `low_confidence: true`
- [ ] **TRACE-08** (F5): System flags `clarification_skipped` when a span proceeds on an ambiguous prompt without asking for clarification — detected syntactically: prompt contains disjunctive markers (`or`, `either`, `which`) with no question mark in `response`; marked `low_confidence: true`
- [ ] **TRACE-09** (G1): System flags `no_verification` when a completed trace contains no span with a verification-type tool call — detected via keyword scan of `tool_name` and `tool_description` against a `_VERIFICATION_KEYWORDS` set (verify, check, validate, assert, test, confirm)
- [ ] **TRACE-10** (G2): System flags `incomplete_verification` when a trace has a verification span (G1 negative) but the verification covers fewer entities than were produced — detected via named-entity count ratio between the verification span's input context and its scope; gated on G1 not firing

### CAL — Calibration

- [ ] **CAL-01**: All 18 new flag types calibrated via extended `calibrate.py`; each check has a threshold key in `THRESHOLDS`; recall floor R ≥ 0.10 enforced; full-suite mean precision ≥ 95% verified

---

## Future Requirements (deferred)

- python-jose → PyJWT migration (AUTH-F02)
- Refresh token revocation store (AUTH-F01)
- Rate limiting on Analyser ingestion (OPS-F01)
- TypeScript/Node.js SDK (SDK-F01)
- Per-tenant Redis queue keys (OPS-F02)

## Out of Scope

- G3 (incorrect verification), C1 (task derailment), C2 (premature termination), C5 (reasoning-action mismatch) — insufficient OTel signal to detect reliably without LLM-in-the-loop evaluation
- H3 (confabulated tool output), H4 (response-prompt mismatch) — overlap with existing `response_anomaly` check (A category); separate detection adds marginal signal
- E1/E2 (disobey task/role specification) — requires declared role/objective metadata not present in SpanData
- A5 (tool output ignored), A6 (silent tool failure) — require cross-span tool lifecycle tracking; deferred to v1.6

## Traceability

| Requirement | Phase | Phase Name | Status |
|-------------|-------|------------|--------|
| INFRA-01 | Phase 22 | Bug Fixes | Complete |
| INFRA-02 | Phase 22 | Bug Fixes | Complete |
| INFRA-03 | Phase 23 | Infrastructure | Pending |
| INFRA-04 | Phase 23 | Infrastructure | Pending |
| INFRA-05 | Phase 23 | Infrastructure | Pending |
| INFRA-06 | Phase 23 | Infrastructure | Pending |
| SCHEMA-01 | Phase 24 | Structural Span Checks | Pending |
| SCHEMA-02 | Phase 24 | Structural Span Checks | Pending |
| SCHEMA-03 | Phase 24 | Structural Span Checks | Pending |
| SCHEMA-04 | Phase 24 | Structural Span Checks | Pending |
| CTX-01 | Phase 24 | Structural Span Checks | Pending |
| CTX-03 | Phase 24 | Structural Span Checks | Pending |
| CTX-02 | Phase 25 | Semantic Span + Structural Trace Checks | Pending |
| CTX-04 | Phase 25 | Semantic Span + Structural Trace Checks | Pending |
| TRACE-01 | Phase 25 | Semantic Span + Structural Trace Checks | Pending |
| TRACE-02 | Phase 25 | Semantic Span + Structural Trace Checks | Pending |
| TRACE-03 | Phase 25 | Semantic Span + Structural Trace Checks | Pending |
| TRACE-04 | Phase 25 | Semantic Span + Structural Trace Checks | Pending |
| TRACE-05 | Phase 26 | Best-Effort Proxy Checks | Pending |
| TRACE-06 | Phase 26 | Best-Effort Proxy Checks | Pending |
| TRACE-07 | Phase 26 | Best-Effort Proxy Checks | Pending |
| TRACE-08 | Phase 26 | Best-Effort Proxy Checks | Pending |
| TRACE-09 | Phase 26 | Best-Effort Proxy Checks | Pending |
| TRACE-10 | Phase 26 | Best-Effort Proxy Checks | Pending |
| CAL-01 | Phase 27 | Calibration Pass | Pending |

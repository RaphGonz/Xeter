# Phase 26: Best-Effort Proxy Checks - Context

**Gathered:** 2026-05-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 26 adds 6 new `_check_*()` methods to the existing `TraceAnalyzer` class in `trace_analyzer.py`. No new analyzer class. No schema migrations. All 6 implement TRACE-05 through TRACE-10 from REQUIREMENTS.md.

**New checks (all trace-level, added to `TraceAnalyzer`):**
1. **`wrong_agent_handoff`** (TRACE-05): unexpected agent-name transition given `AGENT_ROUTING_GRAPH` — marked `low_confidence: true`
2. **`information_withholding`** (TRACE-06): span[i].response NEs not passed to span[i+1].prompt — forward-looking NE recall
3. **`conversation_reset`** (TRACE-07): abrupt centroid cosine drop mid-trace — same mechanism as `history_loss`, lower threshold — marked `low_confidence: true`
4. **`clarification_skipped`** (TRACE-08): disjunctive prompt with no question mark in response — purely syntactic — marked `low_confidence: true`
5. **`no_verification`** (TRACE-09): completed trace has no span with verification keyword in `tool_name`/`tool_description`
6. **`incomplete_verification`** (TRACE-10): verification span exists but covers < threshold of entities produced — gated on TRACE-09 not firing

Also: register all 6 in `calibrate.py` `FLAG_TYPE_TO_ANALYZER_CLASS` + add starting threshold values to `THRESHOLDS` in `main.py` and `DEFAULT_THRESHOLDS` in `calibrate.py`.

</domain>

<decisions>
## Implementation Decisions

### conversation_reset vs history_loss differentiation
- **D-01:** `_check_conversation_reset` uses the **same centroid cosine mechanism** as `_check_history_loss` (Phase 25): compute centroid of all prior span prompts [0..i-1], compare span[i].prompt cosine to centroid. The two checks differ only in threshold and semantic label. Same minimum span guard: `if len(spans) < 3: return []`.
- **D-02:** Separate `log_score("conversation_reset", score)` call and separate threshold key `THRESHOLDS["conversation_reset"]`. The checks are independent — both can fire on the same trace if both thresholds are exceeded.
- **D-03:** Default starting threshold for `conversation_reset` = **0.25** (stricter than `history_loss` at 0.40). Rationale: `conversation_reset` represents abrupt hard resets, `history_loss` is gradual drift — lower threshold required for the abrupt signal. Phase 27 calibration will tune.
- **D-04:** `conversation_reset` marks `"low_confidence": True` in `Flag.detail` per REQUIREMENTS.md TRACE-07.

### AGENT_ROUTING_GRAPH configuration
- **D-05:** New environment variable `WORKER_AGENT_ROUTING_GRAPH` holds the routing graph as an **inline JSON string** (e.g., `'{"orchestrator": ["search_agent", "write_agent"], "search_agent": ["orchestrator"]}'`). Parsed once at worker startup in `main.py` alongside other env var reads. If the var is absent or an empty string, parsed value is `None`.
- **D-06:** Parsed graph (`dict[str, list[str]] | None`) injected into `TraceAnalyzer.__init__` as a new optional parameter: `routing_graph: dict[str, list[str]] | None = None`. Stored as `self._routing_graph`. Constructor remains backward-compatible (existing callers pass no `routing_graph` arg).
- **D-07:** `_check_wrong_agent_handoff` is a **no-op** (returns `[]`, logs nothing) when `self._routing_graph` is `None` or empty dict.
- **D-08:** Flag fires when iterating consecutive `agent_name` pairs `(span[i].agent_name → span[i+1].agent_name)`:
  - Source agent IS in the routing graph but the destination is NOT in its allowed list → flag
  - Source agent is NOT in the routing graph at all → flag (unknown source treated as violation)
  Marks `"low_confidence": True` in `Flag.detail`.

### incomplete_verification scope
- **D-09:** "Entities produced" = spaCy NEs extracted from **all prior span `response` fields** in the trace (every span before the verification span, excluding the verification span itself).
- **D-10:** "Entities verified" = spaCy NEs extracted from the **verification span's `prompt`** (what the verifier was asked to check).
- **D-11:** Recall ratio = `len(verified_entities ∩ produced_entities) / len(produced_entities)`. Fires when ratio < `THRESHOLDS["incomplete_verification"]`. Default starting threshold = **0.7**. Phase 27 calibration will tune.
- **D-12:** **Mutual exclusion enforced in `analyze()`**: compute `_check_no_verification(spans)` first. If it returns a non-empty list (TRACE-09 fired), **skip** `_check_incomplete_verification()` entirely. `no_verification` and `incomplete_verification` never both fire on the same trace.

### Verification keywords
- **D-13:** `_VERIFICATION_KEYWORDS` module-level frozenset in `trace_analyzer.py`:
  `{"verify", "check", "validate", "assert", "test", "confirm"}`. Scans both `span.tool_name` and `span.tool_description` (case-insensitive substring match). If either field contains any keyword → span qualifies as a verification span.

### Calibration registration
- **D-14:** No `BINARY_FLAG_TYPES` entries added in Phase 26 — consistent with Phase 25 D-12. Phase 27 makes the final binary vs threshold classification for all 6 new checks after a full calibration dataset exists. Starting threshold values added to `THRESHOLDS` (main.py) and `DEFAULT_THRESHOLDS` (calibrate.py) for all 6 types.

### Claude's Discretion
- Starting threshold for `information_withholding` NE recall — planner picks; suggest 0.5 (consistent with `context_propagation_failure` baseline; Phase 27 tunes).
- Starting threshold for `wrong_agent_handoff` — planner picks; suggest 1.0 logged as binary 0.0/1.0 (topology check is deterministic).
- `clarification_skipped` and `no_verification` implementation details — purely syntactic/keyword checks; log 0.0/1.0; planner implements per REQUIREMENTS.md spec.
- NE extraction method for `information_withholding` and `incomplete_verification` — reuse `_get_spacy()` lazy-loader already in `trace_analyzer.py`; planner decides whether to use `doc.ents` (named entities only) or `doc.noun_chunks` (broader) based on what produces cleaner signal.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Current TraceAnalyzer (primary file to extend)
- `xeter/services/worker/trace_analyzer.py` — Phase 25 implementation with 5 existing `_check_*()` methods; Phase 26 adds 6 more to this file. Study the `_check_history_loss` method for the centroid pattern that `conversation_reset` reuses.

### Base classes and utilities
- `xeter/services/worker/base.py` — `BaseTraceAnalyzer`, `SpanData` dataclass (all fields), `Flag` dataclass, `log_score()` contract, `hybrid_score()`, `bow_score()`, `EmbedderClient.encode_batch()`
- `xeter/services/worker/tool_call_analyzer.py` — `_get_spacy()` lazy-load pattern (same pattern already in trace_analyzer.py — use the one there)

### Registration points (must update)
- `xeter/services/worker/main.py` — `THRESHOLDS` dict (add 6 new keys); `TraceAnalyzer(...)` instantiation (add `routing_graph=` kwarg, parsed from `WORKER_AGENT_ROUTING_GRAPH` env var)
- `xeter/scripts/calibrate.py` — `FLAG_TYPE_TO_ANALYZER_CLASS` registry (add 6 entries pointing to `TraceAnalyzer`); `DEFAULT_THRESHOLDS` (add 6 starting values); NO `BINARY_FLAG_TYPES` entries yet

### Prior phase decisions (constraint sources)
- `.planning/phases/25-semantic-span-structural-trace-checks/25-CONTEXT.md` — D-03 (`analyze()` dispatches via `_check_*()` helpers), D-04 (`log_score()` BEFORE threshold invariant), D-12 (BINARY_FLAG_TYPES deferral to Phase 27)
- `.planning/phases/24-structural-span-checks/24-CONTEXT.md` — D-04 (`log_score` called even when guard returns early — actually NOT: guard `return []` before any computation skips log_score too; this is correct)

### Requirements (phase scope source)
- `.planning/REQUIREMENTS.md` — §TRACE-05 through §TRACE-10: exact detection logic, field names, low_confidence markers, mutual exclusion rule for G1/G2

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_get_spacy()` lazy-loader — already in `trace_analyzer.py` (imported via the global `_NLP` pattern); reuse directly for `information_withholding` and `incomplete_verification` NE extraction
- `self.embed()` + `self.compare()` from `BaseAnalyzer` — available for `conversation_reset` centroid cosine (same as `history_loss`)
- `self._embedder.encode_batch()` + `np.mean(..., axis=0)` centroid pattern — already in `_check_history_loss`; copy directly for `_check_conversation_reset`
- `hybrid_score()`, `bow_score()` from `base.py` — available if needed for `information_withholding`

### Established Patterns
- `log_score(metric, score)` BEFORE threshold comparison — mandatory invariant (every span must contribute to calibration dataset)
- `Flag(flag_type=..., score=..., detail={"metric": "...", ...})` — `detail` always has `"metric"` key; add `"low_confidence": True` for TRACE-05, TRACE-07, TRACE-08
- No numeric threshold literals in check methods — always `self._thresholds["key"]`
- Guard pattern: `if len(spans) < 2: return []` at top of trace check methods
- `if len(spans) < 3: return []` for checks requiring centroid (conversation_reset, like history_loss)
- All trace-level flags write `span_id=None` (established in v1.4; flags.span_id is nullable)

### Integration Points
- `xeter/services/worker/trace_analyzer.py` — extend `TraceAnalyzer.analyze()` to call 6 new `_check_*()` methods; update `__init__` to accept `routing_graph` param
- `xeter/services/worker/main.py` — parse `WORKER_AGENT_ROUTING_GRAPH` env var + inject into `TraceAnalyzer(embedder, THRESHOLDS, routing_graph=...)` + add 6 threshold keys to `THRESHOLDS`
- `xeter/scripts/calibrate.py` — add 6 entries to `FLAG_TYPE_TO_ANALYZER_CLASS` + 6 starting values to `DEFAULT_THRESHOLDS`

</code_context>

<specifics>
## Specific Ideas

- `conversation_reset` threshold = 0.25 (user confirmed; stricter than `history_loss` at 0.4 to represent abrupt hard resets, not gradual drift)
- `incomplete_verification` threshold = 0.7 (user confirmed; fires when verifier's prompt covers < 70% of entities produced across the trace)
- `WORKER_AGENT_ROUTING_GRAPH` env var format: inline JSON string like `'{"orchestrator": ["search_agent"], "search_agent": ["orchestrator"]}'`
- Unknown source agent (not in routing graph) → always flag wrong_agent_handoff (routing graph is a whitelist — anything not listed is invalid)
- `incomplete_verification` entity scope: NEs from ALL prior span responses (not just immediately prior) vs NEs in verification span's prompt

</specifics>

<deferred>
## Deferred Ideas

- BINARY_FLAG_TYPES classification for all 6 Phase 26 checks — Phase 27 scope after full calibration dataset exists
- Actual calibration run for new flag types — Phase 27 scope
- Per-tenant AGENT_ROUTING_GRAPH configuration — current design is a single global graph per worker instance; per-tenant graphs would require routing_graph to be a `dict[tenant_id, dict]` (out of scope v1.5)

</deferred>

---

*Phase: 26-best-effort-proxy-checks*
*Context gathered: 2026-05-26*

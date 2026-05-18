# Architecture Patterns: v1.5 Silent Failure Detection

**Domain:** Adding 18 new analyser checks to an existing AI observability platform
**Researched:** 2026-05-18
**Confidence:** HIGH (all claims verified directly against codebase)

---

## Recommended Architecture

### System Overview (unchanged topology, extended worker internals)

```
Analyser (ingestion FastAPI)
    └── Redis queue (analysis_queue, BRPOP FIFO)
            └── Worker (embedding + flagging)
                    ├── ANALYZERS list (span-level)
                    │       ├── ToolCallAnalyzer (existing — A-category checks)
                    │       └── OutputSchemaAnalyzer (NEW — B1–B4, D3, D5, E3, H2)
                    │
                    └── trace_analyzer (trace-level, flush-timeout)
                            └── TraceAnalyzer (EXTEND — C3, C4, D1, D2, F1, F2, F4, F5, G1, G2)
                                    ↓
                    PostgreSQL flags table (span_id nullable, flag_type open string)
                    PostgreSQL span_scores table (calibration data)
```

No new services, no new Docker containers, no topology changes.

---

## Component Boundaries

| Component | Responsibility | v1.5 Change |
|-----------|---------------|-------------|
| `ToolCallAnalyzer` | A-category tool-call anomaly detection (7 checks) | None — do not add B/D/E/H checks here |
| `OutputSchemaAnalyzer` (NEW) | B1–B4 output/schema failures + D3/D5/E3/H2 context checks | New file, new class |
| `TraceAnalyzer` | Trace-level pattern detection across all spans in a completed trace | Implement 10 checks (currently stub) |
| `base.py` | `SpanData`, `Flag`, `BaseSpanAnalyzer`, `BaseTraceAnalyzer`, `BaseAnalyzer` | Add 2 optional fields to `SpanData` |
| `main.py` | BRPOP loop, trace buffer flush, ANALYZERS registry | Add `OutputSchemaAnalyzer` to `ANALYZERS` list; add new thresholds |
| `flag_writer.py` | Writes flags to PostgreSQL | No changes needed |
| `score_writer.py` | Writes calibration scores to PostgreSQL | No changes needed |
| `calibrate.py` | Threshold hill-climbing per flag_type | Add new flag types to `FLAG_TYPES` list |
| `migrations/` | PostgreSQL schema | Migration 006 for `flags` index only (optional, no schema changes required) |

---

## Question 1: Where Do B1–B4, D3, D5, E3, H2 Belong?

**Decision: New `OutputSchemaAnalyzer` class, NOT added to `ToolCallAnalyzer`.**

`ToolCallAnalyzer` is scoped to tool-call mechanics (was the right tool called, with the right args, in the right format). B1–B4 check what the model returned as output; D3/D5/E3/H2 check context and content quality. These are a different detection domain.

Adding them to `ToolCallAnalyzer` would:
- Violate the single-responsibility boundary that makes `ToolCallAnalyzer` testable in isolation
- Make `_check_parsing_error` confusable with B3 (truncated output is not a format error)
- Break the one-class-per-concern pattern already established

`OutputSchemaAnalyzer` subclasses `BaseSpanAnalyzer` — same contract, same registration pattern, slotted into `ANALYZERS` list in `main.py` alongside `ToolCallAnalyzer`. The worker loop already iterates `for analyzer in analyzers:` with no hardcoded count, so adding a second span-level analyzer is a zero-friction extension point.

### OutputSchemaAnalyzer check catalogue

| Check ID | Flag type | Approach | Needs embedding? |
|----------|-----------|----------|-----------------|
| B1 | `output_schema_violation` | Detect free text when response contains no JSON-parseable object/array when tool_output or prompt implies structured output | No — regex/parse |
| B2 | `missing_required_fields` | Parse tool_output as JSON, check for null/missing keys | No — parse |
| B3 | `truncated_output` | Detect unclosed JSON structures in tool_output or response | No — parse |
| B4 | `type_coercion_error` | Detect type mismatches (string where int expected) in parsed tool_output | No — parse |
| D3 | `context_overflow` | Estimate token count of prompt; flag if approaching model context limit heuristic | No — token count |
| D5 | `stale_context` | Compare tool_output to prompt: if tool_output appears to reference an earlier prompt topic (low similarity to current prompt but high to prior spans), flag | Yes — cosine |
| E3 | `prompt_injection` | Detect injection patterns in tool_output (instructions addressed to an AI embedded in external data) | No — regex + heuristic |
| H2 | `missing_details` | Compare prompt-requested entities to response content; flag when response omits named entities or quantities present in prompt | Yes — entity overlap |

All eight checks operate on a single span — correct for `BaseSpanAnalyzer`.

D5 is the only check in this group that needs cross-span comparison. It requires looking at prior tool outputs from the same trace. **Do not attempt cross-span lookups in a span-level analyzer.** Instead, implement D5 as a simpler single-span heuristic: compare `tool_output` to `prompt` and flag when the output content does not address the prompt's explicit topic (cosine similarity below threshold). True stale-context detection (D5 in its full form) belongs in `TraceAnalyzer` as a trace-level check — but the single-span approximation is good enough for v1.5 and avoids architectural complexity.

---

## Question 2: How Should TraceAnalyzer Be Structured for 10 Checks?

The current scaffold has a single `analyze()` method that returns `[]`. For 10 checks, the same private-method pattern used in `ToolCallAnalyzer` is the right model: one `_check_*` method per check, all called from `analyze()`, with a flat flag list accumulation.

### TraceAnalyzer check catalogue

| Check ID | Flag type | Key signal | Min spans needed |
|----------|-----------|-----------|-----------------|
| C3 | `step_repetition` | Tool + args sequence repeats within trace | 2 |
| C4 | `termination_loop` | Same tool called N+ times with no response change | 3 |
| D1 | `context_propagation_failure` | Agent name changes mid-trace; prior agent's output not referenced by successor | 2 |
| D2 | `conversation_history_loss` | Prompt in later span does not mention or embed-reference earlier span's topic | 2 |
| F1 | `wrong_agent_handoff` | Handoff to agent whose tool set is semantically unrelated to current task | 2 |
| F2 | `information_withholding` | Agent produces tool_output with key entities; next span's prompt omits those entities | 2 |
| F4 | `conversation_reset` | Prompt in later span references no prior span content (near-zero embedding overlap) | 2 |
| F5 | `clarification_not_requested` | Prompt contains ambiguous placeholder terms; agent proceeds without a clarification span | 2 |
| G1 | `no_verification` | Trace has no span where response content overlaps with earlier span's tool_output (no self-check signal) | 2 |
| G2 | `incomplete_verification` | Trace has a verification-pattern span but coverage is partial (not all outputs checked) | 3 |

### Recommended internal structure

```python
class TraceAnalyzer(BaseTraceAnalyzer):

    def analyze(self, spans: list[SpanData]) -> list[Flag]:
        if len(spans) < 2:           # nearly all trace checks need ≥2 spans
            return []
        flags: list[Flag] = []
        flags.extend(self._check_step_repetition(spans))
        flags.extend(self._check_termination_loop(spans))
        flags.extend(self._check_context_propagation_failure(spans))
        flags.extend(self._check_conversation_history_loss(spans))
        flags.extend(self._check_wrong_agent_handoff(spans))
        flags.extend(self._check_information_withholding(spans))
        flags.extend(self._check_conversation_reset(spans))
        flags.extend(self._check_clarification_not_requested(spans))
        flags.extend(self._check_no_verification(spans))
        flags.extend(self._check_incomplete_verification(spans))
        return flags
```

The `len(spans) < 2` early-return is the right guard: single-span traces have no inter-span patterns to detect. All 10 checks need at least 2 spans; `_check_termination_loop` and `_check_incomplete_verification` effectively need 3.

**On embedding use in TraceAnalyzer:** F-category and G-category checks are best-effort heuristic. For v1.5, prefer token-overlap (BOW), entity-set comparison, and tool-name equality over embedding calls. Cross-span cosine comparisons are expensive (each call hits the embedder service over HTTP). Use embeddings only where string similarity is truly insufficient: D2 (conversation history loss) and G2 (incomplete verification coverage) justify embedding calls because topic drift is the signal. The other 8 checks can be implemented with string/set operations.

---

## Question 3: Does SpanData Need New Fields?

**Two optional fields should be added. No others are needed.**

Current `SpanData` dataclass (in `base.py`):
```
span_id, tenant_id, trace_id, agent_name, agent_model,
tool_name, tool_description, tool_arguments, tool_output,
prompt, response, raw_response, available_tools
```

### Add: `expected_output_schema: Optional[dict]`

**Why:** B1–B4 checks need to know what structure the model was supposed to return. Without this field, B1 must infer structure from the prompt text (fragile) or from tool_description (approximate). When the SDK caller passes an explicit JSON Schema, the checks become exact.

**How populated:** `span_fetcher.py` reads an `expected_schema_ref` key from the ClickHouse row (S3 reference, same pattern as `available_tools_ref`). If absent, returns `None` — all B-checks degrade gracefully to heuristic mode.

**ClickHouse schema change required:** Add `expected_schema_ref String DEFAULT ''` column to the `spans` table. The analyser SDK must populate it when the caller passes a response schema. This is additive; existing rows default to empty string, which `span_fetcher` maps to `None`.

### Add: `parent_span_id: Optional[str]`

**Why:** D1 (context propagation failure) and F1 (wrong agent handoff) need to know the predecessor span in a multi-agent trace. The trace buffer in `main.py` accumulates spans by `trace_id` but does not preserve ordering beyond arrival sequence. Having `parent_span_id` on `SpanData` allows `TraceAnalyzer` to reconstruct the execution DAG rather than relying on arrival order.

**How populated:** `span_fetcher.py` reads `parent_span_id` from the ClickHouse row. This column already exists in OTel trace semantics; the Analyser likely stores it. Verify — if absent, add `parent_span_id String DEFAULT ''` to the ClickHouse `spans` table. Fall back to arrival-order if `None` on all spans (single-path traces).

**All other `SpanData` fields are sufficient for v1.5.** D3 uses `prompt` (token-count it directly). D5 uses `tool_output` + `prompt`. E3 uses `tool_output` (scan for injection patterns). H2 uses `prompt` + `response`. C3/C4 use `tool_name` + `tool_arguments`. G1/G2 use `response` + `tool_output`.

---

## Question 4: Does the flags Table Need Changes?

**No schema changes required for new flag_types.**

The `flag_type` column is `VARCHAR` (not a PostgreSQL enum) — this was a deliberate design decision (FLAG-03, confirmed in migration 001 comment). New flag types are additive with zero migration cost.

The 18 new flag types to be introduced:

**Span-level (OutputSchemaAnalyzer):**
- `output_schema_violation`
- `missing_required_fields`
- `truncated_output`
- `type_coercion_error`
- `context_overflow`
- `stale_context`
- `prompt_injection`
- `missing_details`

**Trace-level (TraceAnalyzer):**
- `step_repetition`
- `termination_loop`
- `context_propagation_failure`
- `conversation_history_loss`
- `wrong_agent_handoff`
- `information_withholding`
- `conversation_reset`
- `clarification_not_requested`
- `no_verification`
- `incomplete_verification`

All are open strings that insert into the existing flags table without any migration.

**Optional: Migration 006 (performance index)**

If query volume grows, an index on `flag_type` for dashboard filtering becomes worthwhile:

```sql
CREATE INDEX ix_flags_tenant_flag_type ON flags (tenant_id, flag_type);
```

This is a `CREATE INDEX CONCURRENTLY` operation at runtime — no Alembic migration required for performance tuning. Defer until query profiling shows it's needed; don't add it speculatively in v1.5.

**`span_id` is already nullable** (migration 005, v1.4). Trace-level flags written by `TraceAnalyzer` correctly pass `span_id=None` to `write_flags()`, which maps to SQL NULL. No change needed.

---

## Question 5: Build Order

Dependencies flow top-to-bottom. Items at the same level are independent.

```
Phase 1 — SpanData + ClickHouse schema extension (unblocks everything downstream)
    - Add expected_schema_ref column to ClickHouse spans table
    - Add parent_span_id column to ClickHouse spans table (if missing)
    - Update SpanData dataclass in base.py (2 new Optional fields)
    - Update span_fetcher.py to read + map new fields
    - No PostgreSQL migration needed
    - Tests: update test_tool_call_analyzer.py fixtures to include new fields (no behavior change)

        ↓

Phase 2 — OutputSchemaAnalyzer: heuristic checks (B1–B4, E3)
    - New file: xeter/services/worker/output_schema_analyzer.py
    - Subclasses BaseSpanAnalyzer
    - B1: free-text detection (no embedding), B2: missing fields, B3: truncation, B4: type mismatch
    - E3: prompt injection regex
    - All checks degrade gracefully when expected_output_schema is None
    - Register in main.py ANALYZERS list
    - New flag types added to calibrate.py FLAG_TYPES (binary detectors — BINARY_FLAG_TYPES)
    - Tests: xeter/tests/worker/test_output_schema_analyzer.py

        ↓

Phase 3 — OutputSchemaAnalyzer: embedding checks (D3, D5, H2)
    - Add to output_schema_analyzer.py: D3 (token count, no embedding), D5 (cosine), H2 (entity overlap)
    - New thresholds in main.py THRESHOLDS dict: stale_context, missing_details
    - New env vars: WORKER_THRESHOLD_STALE_CONTEXT, WORKER_THRESHOLD_MISSING_DETAILS
    - Calibration: add stale_context + missing_details to FLAG_TYPES in calibrate.py
    - Tests: extend test_output_schema_analyzer.py

        ↓

Phase 4 — TraceAnalyzer: string/set checks (C3, C4, F1, F2, F4, F5)
    - Implement 6 checks in trace_analyzer.py using BOW + tool-name equality
    - New flag types in calibrate.py (binary or threshold)
    - Tests: extend test_trace_analyzer.py

        ↓

Phase 5 — TraceAnalyzer: embedding checks (D1, D2, G1, G2)
    - Implement 4 checks using cosine similarity for topic drift detection
    - New thresholds: conversation_history_loss, no_verification, incomplete_verification
    - New env vars: WORKER_THRESHOLD_CONVERSATION_HISTORY_LOSS, etc.
    - Calibration dataset additions for trace-level flag types
    - Tests: extend test_trace_analyzer.py

        ↓

Phase 6 — Calibration pass
    - Run calibrate.py against labelled_spans.jsonl extended with B/C/D/E/F/G/H examples
    - Tune all new thresholds
    - Update docker-compose.yml WORKER_THRESHOLD_* env vars
    - Verify full-suite mean precision ≥ 95% still holds
```

**Rationale for this order:**

- Phase 1 first because both new analyzers depend on the expanded `SpanData` fields.
- OutputSchemaAnalyzer (Phases 2–3) before TraceAnalyzer (Phases 4–5) because span-level analyzers are simpler to test in isolation (single span, deterministic inputs) and build calibration confidence before trace-level complexity is added.
- Heuristic checks (B1–B4, E3, C3/C4, F-category) before embedding checks (D5, H2, D1/D2, G1/G2) because they have zero embedding cost, can be tested with pure unit tests, and establish the `OutputSchemaAnalyzer` and `TraceAnalyzer` structure before adding the network-dependent paths.
- Calibration last: threshold tuning is only meaningful once all checks are implemented and the labelled dataset covers the new categories.

---

## New vs Modified Files

### New files

| File | What it is |
|------|-----------|
| `xeter/services/worker/output_schema_analyzer.py` | `OutputSchemaAnalyzer(BaseSpanAnalyzer)` — 8 checks for B/D/E/H categories |
| `xeter/tests/worker/test_output_schema_analyzer.py` | Unit tests mirroring test_tool_call_analyzer.py pattern |

### Modified files

| File | Change |
|------|--------|
| `xeter/services/worker/base.py` | Add `expected_output_schema: Optional[dict]` and `parent_span_id: Optional[str]` to `SpanData` |
| `xeter/services/worker/span_fetcher.py` | Read `expected_schema_ref` and `parent_span_id` from ClickHouse row; resolve S3 ref for schema; map to new SpanData fields |
| `xeter/services/worker/trace_analyzer.py` | Replace stub `analyze()` with 10 `_check_*` methods |
| `xeter/services/worker/main.py` | Add `OutputSchemaAnalyzer` to `ANALYZERS` list; add new threshold keys and env vars |
| `xeter/scripts/calibrate.py` | Add new flag types to `FLAG_TYPES`; add binary-detector entries to `BINARY_FLAG_TYPES` |
| `xeter/tests/worker/test_trace_analyzer.py` | Replace scaffold tests with check-specific tests |
| `xeter/tests/worker/test_tool_call_analyzer.py` | Update `SpanData` fixture construction to include new optional fields |

### No changes needed

| Component | Reason |
|-----------|--------|
| `flag_writer.py` | Flag insertion is generic — `flag_type` is a string, schema unchanged |
| `score_writer.py` | Score writing is generic — `analyzer_name` + `metric_name` strings, no schema dependence |
| `xeter/migrations/` | `flag_type` is open string (FLAG-03); no PostgreSQL schema migration needed |
| Presenter, Diagnosticer, View | Flags are surfaced via existing `/flags` endpoint filtering — new flag types appear automatically |

---

## Data Flow: New Span-Level Path

```
Redis → process_span(span_id, analyzers=[ToolCallAnalyzer, OutputSchemaAnalyzer])
    │
    ├── ToolCallAnalyzer.analyze(span)
    │       → A-category flags (unchanged)
    │
    ├── OutputSchemaAnalyzer.analyze(span)
    │       → B1: parse response/tool_output for JSON structure
    │       → B2: check required fields against expected_output_schema
    │       → B3: detect unclosed brackets/braces
    │       → B4: detect type mismatches against schema
    │       → D3: estimate prompt token length vs model context limit
    │       → D5: cosine(tool_output, prompt) < stale_context threshold
    │       → E3: regex scan tool_output for injection patterns
    │       → H2: entity overlap between prompt requests and response
    │
    └── write_flags(span_id, tenant_id, trace_id, all_flags)
        write_scores(span_id, tenant_id, all_scores)
```

## Data Flow: New Trace-Level Path

```
Trace buffer flush (30s timeout) → TraceAnalyzer.analyze(spans)
    │
    ├── C3: compare (tool_name, tool_arguments) tuples across spans
    ├── C4: count consecutive same-tool calls with identical args
    ├── D1: detect agent_name change + check prompt reference to prior output
    ├── D2: cosine(prior_span.prompt, later_span.prompt) — topic drift
    ├── F1: compare agent tool sets across handoff boundary
    ├── F2: entity extraction from tool_output; check presence in next span prompt
    ├── F4: cosine(all_prior_content, later_span.prompt) — near-zero = reset
    ├── F5: detect ambiguous placeholder terms in prompt; no clarification span follows
    ├── G1: check for any verification-pattern span in trace
    └── G2: count unique outputs covered by verification span(s) vs total outputs
    │
    └── write_flags(span_id=None, tenant_id, trace_id, trace_flags)
        (span_id=None — trace-level flags, span_id column already nullable since migration 005)
```

---

## Patterns to Follow

### Pattern: Check method returns `list[Flag]`, never raises

Every `_check_*` method must return `[]` for any missing/null field — never raise `AttributeError` or `TypeError`. The span data is ingested from external agents; fields will be missing.

```python
def _check_output_schema_violation(self, span: SpanData) -> list[Flag]:
    if span.response is None:
        return []
    # ... logic
```

### Pattern: log_score before threshold comparison

Every similarity score computed must be logged via `self.log_score()` BEFORE the threshold test. This rule (established in calibration Phase 6) ensures non-flagged spans contribute to the calibration dataset. The new analyzers must follow it.

### Pattern: No numeric literals in check methods

All thresholds read from `self._thresholds[key]`. Add new keys to `THRESHOLDS` dict in `main.py` with corresponding env vars. This allows calibration changes with zero code edits.

### Pattern: BINARY_FLAG_TYPES in calibrate.py

Checks that are deterministic (B1–B4, E3, C3) do not need threshold sweeping. Add them to `BINARY_FLAG_TYPES` in `calibrate.py` so the calibration harness skips threshold hill-climbing and reports precision/recall directly.

### Pattern: Graceful degradation on missing schema

B2 and B4 are exact only when `expected_output_schema` is present. When it is `None`, fall back to heuristic: check that `tool_output` or `response` is valid JSON at minimum. Document this fallback in the docstring.

---

## Anti-Patterns to Avoid

### Anti-Pattern: Cross-span lookup inside a span-level analyzer

`OutputSchemaAnalyzer.analyze(span)` receives exactly one span. It must not query ClickHouse or the trace buffer to look up prior spans. D5 (stale context) should approximate using the single span's `tool_output` vs `prompt` comparison only. Full cross-span D5 detection moves to `TraceAnalyzer`.

### Anti-Pattern: Raising exceptions on malformed input

Span payloads come from external instrumented agents. `tool_arguments` may be invalid JSON, `response` may be empty, `expected_output_schema` may be `None`. Every check method must guard defensively. Unhandled exceptions in `analyze()` propagate up to `process_span()` which logs-and-skips the span — valid span flagging is lost.

### Anti-Pattern: Adding new flag types to ToolCallAnalyzer

`ToolCallAnalyzer` tests cover exactly 7 check methods. Adding B/D/E/H checks there entangles two detection domains in one class, bloats its `analyze()` return path, and makes future refactors harder. The extension point is the `ANALYZERS` list in `main.py`.

### Anti-Pattern: Expensive embedding calls for all 10 trace checks

10 embedding calls per trace flush would hit the embedder service 10 times for every completed trace. The embedder is an HTTP microservice with 30s timeout configured. Use string/set operations for C3, C4, F1, F2, F4, F5; reserve embedding calls for the 4 checks (D1, D2, G1, G2) that genuinely require semantic similarity.

---

## Scalability Considerations

| Concern | Current (v1.5) | At higher volume |
|---------|---------------|-----------------|
| Span-level analyzer count | 2 analyzers per span | Open-closed: add to ANALYZERS list, no loop change |
| Trace buffer memory | Dict of `trace_id → list[SpanData]` in Worker process | At high span volume, move trace buffer to Redis sorted set (score = timestamp); Worker pulls and clears |
| Embedding calls per span | ~3 (D5, H2) in OutputSchemaAnalyzer vs ~5 in ToolCallAnalyzer | Consider batching across analyzers in `process_span()` |
| Trace-level embedding calls | 2–4 per trace flush (D2, G1, G2) | Acceptable; traces flush once |
| B-category false positive risk | High if `expected_output_schema` is absent | Heuristic-only mode must be conservative; threshold should be tuned on known-bad examples |

---

## Sources

All claims verified directly against:
- `xeter/services/worker/base.py` — SpanData, BaseSpanAnalyzer, BaseTraceAnalyzer, BaseAnalyzer
- `xeter/services/worker/tool_call_analyzer.py` — check method structure, log_score pattern
- `xeter/services/worker/trace_analyzer.py` — current stub, extension point confirmed
- `xeter/services/worker/main.py` — ANALYZERS list, trace buffer, THRESHOLDS dict, flush-timeout wiring
- `xeter/services/worker/flag_writer.py` — write_flags signature (span_id nullable)
- `xeter/services/worker/score_writer.py` — write_scores signature
- `xeter/services/worker/span_fetcher.py` — SpanData construction, S3 field mapping
- `xeter/migrations/versions/001_initial.py` — flag_type as VARCHAR, FLAG-03 decision
- `xeter/migrations/versions/005_trace_flags_schema.py` — span_id nullable confirmed
- `xeter/scripts/calibrate.py` — FLAG_TYPES, BINARY_FLAG_TYPES pattern
- `xeter/tests/worker/test_tool_call_analyzer.py` — test pattern for span-level analyzers
- `xeter/tests/worker/test_trace_analyzer.py` — test pattern for trace-level analyzers
- `.planning/PROJECT.md` — v1.5 scope, FLAG-03 decision, constraint list

---
*Architecture research for: Xeter v1.5 Silent Failure Detection*
*Researched: 2026-05-18*

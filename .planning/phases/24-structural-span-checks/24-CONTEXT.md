# Phase 24: Structural Span Checks - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 24 delivers 5 deterministic/heuristic span-level checks in a new `OutputSchemaAnalyzer(BaseSpanAnalyzer)` class. No embedding calls. No schema migrations (all required fields landed in Phase 23).

Five checks:
1. **`output_schema_violation`** (SCHEMA-01, sub-case A): `expected_output_schema` is set and `response` is not valid JSON
2. **`required_fields_missing`** (SCHEMA-02): `tool_arguments` parses as JSON but fails `jsonschema` `required` validator against `expected_output_schema`
3. **`output_truncated`** (SCHEMA-03): `finish_reason=length` in `raw_response` OR unclosed JSON delimiter in `response`/`tool_arguments`
4. **`type_coercion_error`** (SCHEMA-04): `tool_arguments` fails `jsonschema` `type` validator against `expected_output_schema` (number-as-string, boolean-as-integer, etc.)
5. **`context_overflow`** (CTX-01): prompt token count via `tiktoken` `cl100k_base` exceeds `THRESHOLDS['context_overflow']`

CTX-03 (`prompt_injection`) is out of Phase 24 scope — see Deferred.

</domain>

<decisions>
## Implementation Decisions

### SCHEMA-01 detection scope
- **D-01:** `output_schema_violation` fires only on sub-case A: `expected_output_schema` is set AND `response` is not parseable as valid JSON. Sub-case B (available_tools present but no tool_use block in raw_response) is deferred — it overlaps with the existing `no_tool_used` check and adds marginal signal.

### CTX-03 deferral
- **D-02:** `prompt_injection` (CTX-03) is removed from Phase 24 scope. Phase 24 is structural schema validation only. CTX-03 belongs in a later phase once the core schema checks are shipped and calibrated.

### Context overflow threshold
- **D-03:** `THRESHOLDS['context_overflow'] = 8000` as the default starting value. Rationale: target users run local models (Ollama, Llama 3, Mistral) with 4k–32k context windows; 8k flags genuinely long prompts without firing on normal multi-turn conversations. Calibration will tune from this baseline.

### Scoring for binary/deterministic checks
- **D-04:** All 5 checks log `log_score(metric, 1.0)` when the flag fires, `log_score(metric, 0.0)` when the span is clean. Consistent with the `tool_not_available` binary pattern established in Phase 23. Keeps span_scores values in [0, 1] — compatible with calibration P/R measurement.

### BINARY_FLAG_TYPES and THRESHOLDS registration
- **D-05:** The 4 purely schema-validation checks (`output_schema_violation`, `required_fields_missing`, `output_truncated`, `type_coercion_error`) are registered in `BINARY_FLAG_TYPES` in `calibrate.py` — deterministic, no threshold sweep. `context_overflow` is NOT in `BINARY_FLAG_TYPES`; it gets `THRESHOLDS['context_overflow'] = 8000` so calibration can tune the token limit.

### OutputSchemaAnalyzer constructor
- **D-06:** Same `__init__(self, embedder, thresholds)` signature as `BaseSpanAnalyzer` for interface consistency. Phase 24 checks don't call `self.embed()` but keeping the embedder parameter avoids any future re-wiring if a semantic gate is ever added.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Analyzer base classes and patterns
- `xeter/services/worker/base.py` — `BaseSpanAnalyzer`, `SpanData` dataclass (note `expected_output_schema: Optional[str]` and `parent_span_id: Optional[str]` fields added in Phase 23), `Flag` dataclass, `log_score()` contract
- `xeter/services/worker/tool_call_analyzer.py` — canonical example of a `BaseSpanAnalyzer` implementation; study the `_check_*()` method pattern, `log_score()` before threshold, `Flag.detail` with `"metric"` key

### Registration points (must update in Phase 24)
- `xeter/services/worker/main.py` — `ANALYZERS` list and `THRESHOLDS` dict; append `OutputSchemaAnalyzer(embedder, THRESHOLDS)` to `ANALYZERS`; add `context_overflow: 8000` to `THRESHOLDS`
- `xeter/scripts/calibrate.py` — `FLAG_TYPE_TO_ANALYZER_CLASS` registry (add 5 new entries pointing to `OutputSchemaAnalyzer`); `BINARY_FLAG_TYPES` (add 4 binary checks); `DEFAULT_THRESHOLDS` (add `context_overflow: 8000`)

### Phase 23 context (prior decisions that constrain this phase)
- `.planning/phases/23-infrastructure/23-CONTEXT.md` — D-05 (registry pattern), D-08 (recall floor), D-09 (new deps); confirms `jsonschema`, `tiktoken` are already in pyproject.toml and Dockerfile

### Requirements
- `.planning/REQUIREMENTS.md` §SCHEMA — SCHEMA-01 through SCHEMA-04 with exact detection logic
- `.planning/REQUIREMENTS.md` §CTX-01 — context_overflow: tiktoken cl100k_base, threshold in THRESHOLDS dict

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BaseSpanAnalyzer` in `base.py` — subclass this; `analyze(span: SpanData) -> list[Flag]`
- `jsonschema` — already in `xeter/pyproject.toml` and `services/worker/Dockerfile` (Phase 23); use `jsonschema.validate()` and catch `ValidationError` for SCHEMA-02 and SCHEMA-04; use `ValidationError.validator` to distinguish `required` vs `type` errors
- `tiktoken` — already installed; `tiktoken.get_encoding("cl100k_base").encode(text)` for token count

### Established Patterns
- `log_score(metric, score)` BEFORE threshold comparison — mandatory for calibration completeness (every span must contribute to span_scores regardless of flag outcome)
- `Flag(flag_type=..., score=..., detail={"metric": "...", ...})` — `detail` always has `"metric"` key
- No numeric threshold literals in check methods — always `self._thresholds["key"]`
- Lazy imports for heavy libraries (see `_get_spacy()` in `tool_call_analyzer.py`) — use same pattern for any slow-import library if needed
- Guard pattern: check `if span.field is None: return []` early before any processing

### Integration Points
- New file: `xeter/services/worker/output_schema_analyzer.py` — parallel to `tool_call_analyzer.py`
- `xeter/services/worker/main.py` lines 177+ — `ANALYZERS` list and `THRESHOLDS` dict: add new entries
- `xeter/scripts/calibrate.py` lines 65+ — `FLAG_TYPE_TO_ANALYZER_CLASS` registry: add 5 entries; `BINARY_FLAG_TYPES`: add 4 entries; `DEFAULT_THRESHOLDS`: add `context_overflow`
- `finish_reason` parsed from `raw_response` JSON at check time — not a SpanData field. `raw_response` is the full API JSON body; parse with `json.loads()` and navigate provider-specific paths (e.g. `choices[0].finish_reason` for OpenAI, `stop_reason` for Anthropic). Guard for None and parse failure.

</code_context>

<specifics>
## Specific Ideas

- Target users run local models (Ollama, Llama 3, Mistral 7B/8B). The 8,000-token default for `context_overflow` was chosen with this in mind.
- `output_schema_violation` only fires when `expected_output_schema` is explicitly set on the span — don't fire on spans where the decorator was used without a schema.
- For SCHEMA-03 (`output_truncated`), the two sub-conditions are OR: either signal is sufficient. `finish_reason` parsing should be resilient to different provider formats (OpenAI vs Anthropic raw_response shapes differ).

</specifics>

<deferred>
## Deferred Ideas

- **CTX-03 (`prompt_injection`)**: Scans `tool_output` for adversarial instruction-override patterns (e.g. "ignore previous instructions"). Removed from Phase 24 — the phase is structural schema validation only. Belongs in a later phase, possibly alongside other content-quality checks.
- **SCHEMA-01 sub-case B**: `raw_response` shows no tool_use block despite `available_tools` being present. Deferred — overlaps with existing `no_tool_used` check; revisit if calibration shows a coverage gap.

</deferred>

---

*Phase: 24-structural-span-checks*
*Context gathered: 2026-05-21*

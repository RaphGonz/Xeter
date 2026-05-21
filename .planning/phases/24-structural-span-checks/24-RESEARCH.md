# Phase 24: Structural Span Checks - Research

**Researched:** 2026-05-21
**Domain:** Deterministic/heuristic span-level schema and context checks — no embeddings
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `output_schema_violation` fires only on sub-case A: `expected_output_schema` is set AND `response` is not parseable as valid JSON. Sub-case B deferred.
- **D-02:** `prompt_injection` (CTX-03) is removed from Phase 24 scope entirely.
- **D-03:** `THRESHOLDS['context_overflow'] = 8000` as the default starting value.
- **D-04:** All 5 checks log `log_score(metric, 1.0)` on flag, `log_score(metric, 0.0)` on clean span.
- **D-05:** 4 schema-validation checks (`output_schema_violation`, `required_fields_missing`, `output_truncated`, `type_coercion_error`) registered in `BINARY_FLAG_TYPES`. `context_overflow` gets `THRESHOLDS['context_overflow'] = 8000`.
- **D-06:** `OutputSchemaAnalyzer.__init__(self, embedder, thresholds)` — same signature as `BaseSpanAnalyzer`.

### Claude's Discretion

None specified — all implementation decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

- **CTX-03 (`prompt_injection`)**: Removed from Phase 24. Belongs in a later phase.
- **SCHEMA-01 sub-case B**: `raw_response` shows no tool_use block despite `available_tools` being present. Deferred — overlaps with existing `no_tool_used` check.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHEMA-01 | Flag `output_schema_violation` when `expected_output_schema` is set and `response` is not valid JSON | `json.loads(response)` + guard `if span.expected_output_schema is None: skip` |
| SCHEMA-02 | Flag `required_fields_missing` when `tool_arguments` JSON fails `required` validator against `expected_output_schema` | `jsonschema.Draft7Validator.iter_errors()` with `e.validator == "required"` filter |
| SCHEMA-03 | Flag `output_truncated` when `finish_reason=length` in `raw_response` OR unclosed JSON delimiter in `response`/`tool_arguments` | `raw_response` JSON parse + provider-specific path lookup; unclosed-delimiter heuristic |
| SCHEMA-04 | Flag `type_coercion_error` when `tool_arguments` contains type violations against `expected_output_schema` | `jsonschema.Draft7Validator.iter_errors()` with `e.validator == "type"` filter |
| CTX-01 | Flag `context_overflow` when prompt token count exceeds `THRESHOLDS['context_overflow']` | `tiktoken.get_encoding("cl100k_base").encode(prompt)` — VERIFIED working at 8000 token threshold |
</phase_requirements>

---

## Summary

Phase 24 delivers a single new analyzer class `OutputSchemaAnalyzer` with five deterministic check methods. No embedding calls are made — every check is pure logic over JSON fields already present in `SpanData`. All required dependencies (`jsonschema==4.26.0`, `tiktoken==0.12.0`) are already installed via Phase 23 infrastructure work and verified working in the current environment.

The implementation follows the established `tool_call_analyzer.py` pattern exactly: subclass `BaseSpanAnalyzer`, implement `_check_*()` private methods, call `log_score()` before any flag decision, return `Flag` instances with `"metric"` key in `detail`. Three registration points require updates: `main.py` (add to `ANALYZERS` list and `THRESHOLDS` dict), `calibrate.py` (add 5 entries to `FLAG_TYPE_TO_ANALYZER_CLASS`, 4 to `BINARY_FLAG_TYPES`, 1 to `DEFAULT_THRESHOLDS`).

The most nuanced implementation concern is `finish_reason` parsing for SCHEMA-03: OpenAI and Anthropic use different field paths (`choices[0].finish_reason` vs `stop_reason`), and the raw_response may be `None` or not valid JSON. The unclosed-delimiter fallback for SCHEMA-03 requires distinguishing "parse failed because truncated" from "parse failed for other reasons" — the heuristic approach is to check whether the string ends without a closing `}` or `]` after a failed parse attempt.

**Primary recommendation:** Implement `OutputSchemaAnalyzer` as a single new file `xeter/services/worker/output_schema_analyzer.py`, register it in `main.py` and `calibrate.py`, write tests in TDD order before implementation, then ship.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| output_schema_violation detection | Worker (span analyzer) | — | Pure JSON parse of `response` field — no network, no embedding |
| required_fields_missing detection | Worker (span analyzer) | — | jsonschema validation of `tool_arguments` against parsed schema |
| output_truncated detection | Worker (span analyzer) | — | Two sub-signals both live in span fields (`raw_response`, `response`, `tool_arguments`) |
| type_coercion_error detection | Worker (span analyzer) | — | jsonschema type validation of `tool_arguments` |
| context_overflow detection | Worker (span analyzer) | — | tiktoken token counting of `prompt` field against threshold |
| Calibration routing | calibrate.py | — | `FLAG_TYPE_TO_ANALYZER_CLASS` registry routes all 5 new flag types to `OutputSchemaAnalyzer` |
| Threshold management | main.py THRESHOLDS dict | calibrate.py DEFAULT_THRESHOLDS | `context_overflow` needs threshold; 4 binary checks do not |

---

## Standard Stack

### Core (already installed — Phase 23)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| jsonschema | 4.26.0 | Schema validation via `Draft7Validator.iter_errors()` | Already in `xeter/pyproject.toml` [VERIFIED: confirmed `import jsonschema; jsonschema.__version__` == 4.26.0] |
| tiktoken | 0.12.0 | Prompt token counting via `cl100k_base` encoding | Already in `xeter/pyproject.toml` [VERIFIED: confirmed `tiktoken.__version__` == 0.12.0] |

### No New Packages Required

All libraries needed for Phase 24 are already installed. No `pip install` step is required.

---

## Package Legitimacy Audit

No new packages are installed in this phase. All dependencies (`jsonschema`, `tiktoken`) were audited and installed in Phase 23. No audit required.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
SpanData (from span_fetcher)
        |
        v
OutputSchemaAnalyzer.analyze(span)
        |
        +---> _check_output_schema_violation(span)
        |         if span.expected_output_schema is None: return []
        |         json.loads(response) fails? -> flag
        |
        +---> _check_required_fields_missing(span)
        |         if schema or tool_arguments None: return []
        |         json.loads(tool_arguments) -> validate against schema
        |         any e.validator == "required"? -> flag
        |
        +---> _check_output_truncated(span)
        |         Sub-signal A: raw_response JSON -> finish_reason == "length" (OpenAI)
        |                                         or stop_reason == "max_tokens" (Anthropic)
        |         Sub-signal B: json.loads(response or tool_arguments) fails AND
        |                       ends without closing } or ]
        |         Either sub-signal triggers flag
        |
        +---> _check_type_coercion_error(span)
        |         if schema or tool_arguments None: return []
        |         Draft7Validator.iter_errors() -> any e.validator == "type"? -> flag
        |
        +---> _check_context_overflow(span)
                  if span.prompt is None: return []
                  tiktoken cl100k_base encode(prompt) -> len > THRESHOLDS["context_overflow"]
                  log_score("prompt_token_count", token_count)
                  -> flag if exceeded

        |
        v
list[Flag]  (each has flag_type, score, detail with "metric" key)
```

### Recommended Project Structure

```
xeter/services/worker/
├── output_schema_analyzer.py    # NEW — OutputSchemaAnalyzer class (Phase 24)
├── tool_call_analyzer.py        # existing — reference implementation
├── base.py                      # existing — BaseSpanAnalyzer, SpanData, Flag
└── main.py                      # existing — add ANALYZERS entry + THRESHOLDS entry

xeter/scripts/
└── calibrate.py                 # existing — add 5 registry entries, 4 BINARY entries, 1 threshold

xeter/tests/worker/
└── test_output_schema_analyzer.py  # NEW — TDD tests for OutputSchemaAnalyzer
```

### Pattern 1: OutputSchemaAnalyzer Class Skeleton

```python
# Source: xeter/services/worker/tool_call_analyzer.py (canonical pattern)
from __future__ import annotations
import json
from typing import Optional
from xeter.services.worker.base import BaseSpanAnalyzer, Flag, SpanData

class OutputSchemaAnalyzer(BaseSpanAnalyzer):

    @property
    def name(self) -> str:
        return "output_schema"

    def analyze(self, span: SpanData) -> list[Flag]:
        flags: list[Flag] = []
        flags.extend(self._check_output_schema_violation(span))
        flags.extend(self._check_required_fields_missing(span))
        flags.extend(self._check_output_truncated(span))
        flags.extend(self._check_type_coercion_error(span))
        flags.extend(self._check_context_overflow(span))
        return flags
```

### Pattern 2: Binary Check with log_score (D-04 pattern)

```python
# Source: ToolCallAnalyzer._check_tool_not_available() in tool_call_analyzer.py
def _check_output_schema_violation(self, span: SpanData) -> list[Flag]:
    if span.expected_output_schema is None:
        return []
    if span.response is None:
        return []
    score = 0.0  # will be set to 1.0 if flagged
    try:
        json.loads(span.response)
        # Valid JSON — no violation
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

### Pattern 3: jsonschema Validation with Error Filtering

```python
# Source: VERIFIED by running jsonschema.Draft7Validator.iter_errors() in this session
import json, jsonschema

def _check_required_fields_missing(self, span: SpanData) -> list[Flag]:
    if span.expected_output_schema is None or span.tool_arguments is None:
        return []
    try:
        schema = json.loads(span.expected_output_schema)
        instance = json.loads(span.tool_arguments)
    except (json.JSONDecodeError, ValueError):
        return []  # malformed schema or args — not this check's concern
    errors = [
        e for e in jsonschema.Draft7Validator(schema).iter_errors(instance)
        if e.validator == "required"
    ]
    if errors:
        self.log_score("required_fields_missing", 1.0)
        return [Flag(
            flag_type="required_fields_missing",
            score=1.0,
            detail={
                "metric": "required_fields_missing",
                "missing_fields": [e.message for e in errors],
            },
        )]
    self.log_score("required_fields_missing", 0.0)
    return []
```

### Pattern 4: finish_reason Parsing (Provider-Agnostic)

```python
# Source: VERIFIED by parsing OpenAI + Anthropic response shapes in this session
def _parse_finish_reason(self, raw_response: Optional[str]) -> str | None:
    """Extract finish reason from raw_response JSON. Provider-agnostic.
    Returns 'length' if truncation detected, None otherwise or on parse failure.
    """
    if raw_response is None:
        return None
    try:
        parsed = json.loads(raw_response)
    except (json.JSONDecodeError, ValueError):
        return None
    # OpenAI shape: {"choices": [{"finish_reason": "length"}]}
    choices = parsed.get("choices")
    if isinstance(choices, list) and choices:
        reason = choices[0].get("finish_reason")
        if reason is not None:
            return reason
    # Anthropic shape: {"stop_reason": "max_tokens"}
    stop_reason = parsed.get("stop_reason")
    if stop_reason == "max_tokens":
        return "length"
    return stop_reason
```

### Pattern 5: Unclosed Delimiter Heuristic (SCHEMA-03 fallback)

```python
# Source: research verification — json.loads fails, check structural integrity
def _has_unclosed_delimiter(self, text: Optional[str]) -> bool:
    """Return True if text fails JSON parse AND ends without a closing delimiter."""
    if not text:
        return False
    text = text.rstrip()
    try:
        json.loads(text)
        return False  # valid JSON — not truncated
    except (json.JSONDecodeError, ValueError):
        pass
    # Heuristic: contains opening delimiter but last char is not a closing one
    last = text[-1] if text else ''
    has_open = '{' in text or '[' in text
    return has_open and last not in ('}', ']', '"')
```

### Pattern 6: tiktoken Token Count

```python
# Source: VERIFIED by running tiktoken.get_encoding("cl100k_base").encode() in this session
def _check_context_overflow(self, span: SpanData) -> list[Flag]:
    if span.prompt is None:
        return []
    enc = tiktoken.get_encoding("cl100k_base")
    token_count = len(enc.encode(span.prompt))
    self.log_score("prompt_token_count", float(token_count))
    threshold = self._thresholds["context_overflow"]
    if token_count > threshold:
        return [Flag(
            flag_type="context_overflow",
            score=1.0,
            detail={
                "metric": "prompt_token_count",
                "token_count": token_count,
                "threshold": threshold,
            },
        )]
    return []
```

### Pattern 7: main.py Registration

```python
# Source: xeter/services/worker/main.py (existing ANALYZERS/THRESHOLDS pattern)
# In main.py, add after existing ToolCallAnalyzer import:
from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer

# In THRESHOLDS dict, add:
"context_overflow": float(os.environ.get("WORKER_THRESHOLD_CONTEXT_OVERFLOW", "8000")),

# In main() function, update analyzers list:
analyzers = [
    ToolCallAnalyzer(embedder, THRESHOLDS),
    OutputSchemaAnalyzer(embedder, THRESHOLDS),
]
```

### Pattern 8: calibrate.py Registration

```python
# Source: xeter/scripts/calibrate.py (existing registration patterns)
from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer

# Add 5 entries to FLAG_TYPE_TO_ANALYZER_CLASS:
FLAG_TYPE_TO_ANALYZER_CLASS: dict[str, type] = {
    # ... existing 7 entries ...
    "output_schema_violation":  OutputSchemaAnalyzer,
    "required_fields_missing":  OutputSchemaAnalyzer,
    "output_truncated":         OutputSchemaAnalyzer,
    "type_coercion_error":      OutputSchemaAnalyzer,
    "context_overflow":         OutputSchemaAnalyzer,
}

# Add 4 entries to BINARY_FLAG_TYPES:
BINARY_FLAG_TYPES: set[str] = {
    "tool_not_available", "wrong_tool_choice", "parsing_error",
    "output_schema_violation", "required_fields_missing",
    "output_truncated", "type_coercion_error",
}

# Add 1 entry to DEFAULT_THRESHOLDS:
DEFAULT_THRESHOLDS: dict[str, float] = {
    # ... existing entries ...
    "context_overflow": 8000,
}

# Add 5 entries to FLAG_TYPES list:
FLAG_TYPES = [
    # ... existing 7 ...
    "output_schema_violation",
    "required_fields_missing",
    "output_truncated",
    "type_coercion_error",
    "context_overflow",
]
```

### Anti-Patterns to Avoid

- **Using `jsonschema.validate()` instead of `Draft7Validator.iter_errors()`**: `validate()` raises on the first error only. `iter_errors()` is needed to collect all errors and filter by `e.validator` to distinguish `required` from `type` failures. [VERIFIED]
- **Hardcoding `8000` in the check method**: Always `self._thresholds["context_overflow"]`. The codebase enforces this: "No numeric threshold literal should appear in any check method." [CITED: xeter/services/worker/base.py docstring]
- **Calling `log_score()` after the threshold comparison**: Must be called before. This is the core calibration invariant — every span contributes to `span_scores` regardless of flag outcome. [CITED: xeter/services/worker/base.py log_score() docstring]
- **Assuming `expected_output_schema` is a dict**: It is `Optional[str]` in `SpanData` — a JSON string stored inline in ClickHouse. Always `json.loads()` before passing to jsonschema. [VERIFIED: base.py line 61]
- **Raising on malformed `raw_response` JSON**: Guard with try/except and return gracefully. The span may have been traced before raw_response was available.
- **Assuming `finish_reason` is always present**: Both provider paths may be missing. Return `None` and skip the sub-signal.
- **Not adding `"context_overflow"` to `FLAG_TYPES` list in calibrate.py**: The `FLAG_TYPES` list controls which types are included in calibration runs. Binary checks added to `BINARY_FLAG_TYPES` still need an entry in `FLAG_TYPE_TO_ANALYZER_CLASS` and `FLAG_TYPES` for the single-evaluation pass.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON Schema validation | Custom field presence checker | `jsonschema.Draft7Validator.iter_errors()` | Handles nested schemas, allOf/anyOf, draft selection; edge cases in custom code are high |
| Token counting | Split-on-whitespace count | `tiktoken.get_encoding("cl100k_base").encode()` | Matches actual LLM tokenization (BPE subword); word-split systematically under-counts multi-word tokens |
| JSON parse failure classification | Regex on error message | `json.JSONDecodeError` exception + end-char heuristic | `json.JSONDecodeError` is a clean exception; message text is implementation-dependent |
| Finish reason extraction | String search on raw_response | Parse as JSON, access by key | Raw response is JSON; string search has false-positive risk on multi-choice response content |

**Key insight:** All validation problems in this domain have well-maintained library solutions with comprehensive edge case handling. The value is in the integration (calling them correctly with the right guards), not in building custom parsers.

---

## Common Pitfalls

### Pitfall 1: `expected_output_schema` and `tool_arguments` both need `json.loads()`

**What goes wrong:** Passing `span.expected_output_schema` (a string) directly to `jsonschema.Draft7Validator(schema)` raises `jsonschema.exceptions.SchemaError` because the validator expects a dict.

**Why it happens:** `SpanData.expected_output_schema: Optional[str]` — stored as a JSON string in ClickHouse (same as `tool_arguments`). Both must be `json.loads()`'d before use.

**How to avoid:** Parse both before entering the jsonschema call. Wrap in try/except for malformed input.

**Warning signs:** `SchemaError` or `ValidationError` on the schema object itself (not the instance) during testing.

### Pitfall 2: SCHEMA-02 and SCHEMA-04 can fire on the same span

**What goes wrong:** A `tool_arguments` dict can have both missing required fields AND type violations. If only one flag is emitted, the other is silently dropped.

**Why it happens:** Both `required` and `type` errors may appear in the same `iter_errors()` output.

**How to avoid:** Implement as two separate check methods (already the design). Each collects errors filtered by `e.validator`. Both methods run independently in `analyze()`.

**Warning signs:** Fixture span has both missing field and type error, but only one flag appears.

### Pitfall 3: SCHEMA-03 unclosed-delimiter heuristic fires on non-truncated invalid JSON

**What goes wrong:** A response that is simply malformed JSON (not truncated) triggers `output_truncated`. E.g., `{"key": undefined}` has no closing issue but fails to parse.

**Why it happens:** Overly broad heuristic that treats any JSON parse failure as truncation.

**How to avoid:** Only consider a parse failure "truncated" if the string ends without a closing `}` or `]` AND has an opening delimiter. A string like `{"key": undefined}` ends with `}` and should not trigger the unclosed-delimiter fallback. [VERIFIED: heuristic tested in session]

**Warning signs:** Clean spans with intentionally malformed JSON being flagged as `output_truncated`.

### Pitfall 4: `finish_reason` path differs between OpenAI and Anthropic

**What goes wrong:** Code checks only `choices[0].finish_reason` and misses Anthropic's `stop_reason: max_tokens`.

**Why it happens:** Different API conventions across providers.

**How to avoid:** Implement a `_parse_finish_reason()` helper that checks both paths. Anthropic uses `stop_reason: "max_tokens"` (not `"length"`), so normalize to `"length"` semantics. [VERIFIED: both shapes tested in session]

**Warning signs:** Anthropic-traced spans with `stop_reason: max_tokens` not receiving `output_truncated` flag.

### Pitfall 5: `context_overflow` not added to `FLAG_TYPES` list in calibrate.py

**What goes wrong:** `calibrate.py --flag-type context_overflow` exits with "Unknown flag type" error. The calibration run silently skips `context_overflow`.

**Why it happens:** `FLAG_TYPES` controls which types are included in calibration. `BINARY_FLAG_TYPES` and `FLAG_TYPE_TO_ANALYZER_CLASS` are checked but `FLAG_TYPES` must also include the entry. `context_overflow` is NOT binary — it goes through hill climbing.

**How to avoid:** Add `"context_overflow"` to `FLAG_TYPES` list. The 4 binary schema checks also need entries but will follow the single-evaluation pass branch (not hill climbing).

**Warning signs:** `context_overflow` missing from calibration output summary.

### Pitfall 6: tiktoken lazy import omitted — slow cold start

**What goes wrong:** `import tiktoken` at module level adds startup time to the worker process.

**Why it happens:** tiktoken loads the `cl100k_base` vocab file on first use; the module import itself is fast but the encoding load is not.

**How to avoid:** Follow the `_get_spacy()` lazy import pattern in `tool_call_analyzer.py`. Use a module-level `_TIKTOKEN_ENCODING = None` cache, load on first call to `_check_context_overflow`.

**Warning signs:** Worker startup time increases noticeably after adding the OutputSchemaAnalyzer.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `jsonschema.validate()` for single error | `Draft7Validator.iter_errors()` for all errors | Always available, just underused | Enables separate `required` vs `type` flag types from a single validation pass |
| Parse `finish_reason` with string search | Parse `raw_response` as JSON, access by key | Phase 24 design decision | Eliminates false positives from response content containing the word "length" |

**Deprecated/outdated patterns in this codebase:**
- Using `jsonschema.validate()` with a bare `except ValidationError` — Phase 24 uses `iter_errors()` + `e.validator` filtering to distinguish violation types

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Anthropic `stop_reason: "max_tokens"` maps to truncation semantics equivalent to OpenAI `finish_reason: "length"` | Pattern 4, Pitfall 4 | May produce false positives if Anthropic uses `max_tokens` for non-truncation stops | [ASSUMED] |
| A2 | tiktoken `cl100k_base` is a reasonable token counter for Ollama/local models (Llama 3, Mistral) | CTX-01 implementation | Local models may use different BPE vocabularies; `cl100k_base` may under- or over-count | [ASSUMED] — CONTEXT.md D-03 acknowledges this as a "fallback" encoding |

**Note:** Both assumptions are consistent with CONTEXT.md decisions. A1 is low-risk (safe over-flagging). A2 is explicitly accepted in D-03.

---

## Open Questions

1. **Does `context_overflow` need to be added to `FLAG_TYPES` list in calibrate.py?**
   - What we know: `FLAG_TYPES` controls hill-climbing targets. `context_overflow` is NOT in `BINARY_FLAG_TYPES`. It has a threshold, so hill climbing applies.
   - What's unclear: The current `FLAG_TYPES` list has 7 entries (all for `ToolCallAnalyzer`). Adding 5 new entries (the 4 binary ones + `context_overflow`) requires them all in `FLAG_TYPE_TO_ANALYZER_CLASS`. The 4 binary ones will branch to single-evaluation pass (same as `tool_not_available`); `context_overflow` will hill climb.
   - Recommendation: Add all 5 to `FLAG_TYPES` AND `FLAG_TYPE_TO_ANALYZER_CLASS`. Add 4 binary ones to `BINARY_FLAG_TYPES`. This is the complete registration.

2. **Should `_check_output_schema_violation` fire when `response` is None?**
   - What we know: `expected_output_schema` being set means a structured response was expected. `response is None` means the span has no response at all.
   - What's unclear: Is `response=None` already an indicator of a different problem (parsing_error, etc.)?
   - Recommendation: Guard with `if span.response is None: return []` — do not double-flag. The absence of a response is handled by other checks.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| jsonschema | SCHEMA-02, SCHEMA-04 | Yes | 4.26.0 | None needed |
| tiktoken | CTX-01 | Yes | 0.12.0 | None needed |
| pytest | Test suite | Yes | installed | — |

**Missing dependencies with no fallback:** None.

**Note:** `tiktoken` version 0.12.0 is installed (not 0.13.0 as listed in REQUIREMENTS.md INFRA-04). This is inconsequential for Phase 24 — the `cl100k_base` encoding API has not changed. The version discrepancy is a pre-existing condition from Phase 23.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (configured in `xeter/pyproject.toml` `[tool.pytest.ini_options]`) |
| Config file | `xeter/pyproject.toml` — `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| Quick run command | `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py -x -q` |
| Full suite command | `python -m pytest xeter/tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCHEMA-01 | `output_schema_violation` fires when schema set + response not valid JSON | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k schema_violation -x` | No — Wave 0 |
| SCHEMA-01 | `output_schema_violation` NOT fired when schema is None | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k schema_violation -x` | No — Wave 0 |
| SCHEMA-01 | `output_schema_violation` NOT fired when response is valid JSON | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k schema_violation -x` | No — Wave 0 |
| SCHEMA-02 | `required_fields_missing` fires when required field absent in tool_arguments | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k required_fields -x` | No — Wave 0 |
| SCHEMA-02 | `required_fields_missing` NOT fired when all required fields present | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k required_fields -x` | No — Wave 0 |
| SCHEMA-03 | `output_truncated` fires when finish_reason=length in raw_response (OpenAI) | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k output_truncated -x` | No — Wave 0 |
| SCHEMA-03 | `output_truncated` fires when stop_reason=max_tokens (Anthropic) | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k output_truncated -x` | No — Wave 0 |
| SCHEMA-03 | `output_truncated` fires on unclosed JSON delimiter in response | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k output_truncated -x` | No — Wave 0 |
| SCHEMA-04 | `type_coercion_error` fires when tool_arguments has type violation | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k type_coercion -x` | No — Wave 0 |
| SCHEMA-04 | `type_coercion_error` NOT fired when types are correct | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k type_coercion -x` | No — Wave 0 |
| CTX-01 | `context_overflow` fires when prompt tokens exceed threshold | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k context_overflow -x` | No — Wave 0 |
| CTX-01 | `context_overflow` NOT fired when prompt tokens under threshold | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k context_overflow -x` | No — Wave 0 |
| D-04 | `log_score()` called for every span regardless of flag outcome | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k log_score -x` | No — Wave 0 |
| D-05 | calibrate.py registry contains 5 new entries + 4 in BINARY_FLAG_TYPES | unit | `pytest xeter/tests/test_calibrate_routing.py -x` | Yes — extend |
| D-06 | `OutputSchemaAnalyzer(embedder, thresholds)` signature compatible | unit | `pytest xeter/tests/worker/test_output_schema_analyzer.py -k name -x` | No — Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py -x -q`
- **Per wave merge:** `python -m pytest xeter/tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `xeter/tests/worker/test_output_schema_analyzer.py` — covers all SCHEMA-01 through CTX-01 check behaviors
- [ ] Extend `xeter/tests/test_calibrate_routing.py` — add tests for 5 new `FLAG_TYPE_TO_ANALYZER_CLASS` entries + 4 `BINARY_FLAG_TYPES` entries + `context_overflow` in `DEFAULT_THRESHOLDS`

*(Existing `xeter/tests/test_calibrate_routing.py` covers the existing 7-entry registry. It needs extension but the file exists.)*

---

## Security Domain

Security enforcement is not relevant to this phase. Phase 24 is purely internal worker logic — no new API endpoints, no auth, no user input surfaces. The checks operate on span data already stored in ClickHouse, fetched by the worker. No ASVS categories apply.

---

## Sources

### Primary (HIGH confidence)

- `xeter/services/worker/tool_call_analyzer.py` — canonical analyzer implementation pattern; studied `_check_tool_not_available()` as the binary check reference
- `xeter/services/worker/base.py` — `BaseSpanAnalyzer`, `SpanData` field definitions, `log_score()` contract
- `xeter/services/worker/main.py` — `ANALYZERS` list and `THRESHOLDS` dict registration pattern
- `xeter/scripts/calibrate.py` — `FLAG_TYPE_TO_ANALYZER_CLASS`, `BINARY_FLAG_TYPES`, `DEFAULT_THRESHOLDS`, `FLAG_TYPES` list
- `xeter/services/worker/span_fetcher.py` — confirmed `expected_output_schema` is in `_FETCH_COLUMNS` (line 49)
- `.planning/phases/24-structural-span-checks/24-CONTEXT.md` — all 6 locked decisions

### Secondary (MEDIUM confidence)

- VERIFIED: `jsonschema.Draft7Validator.iter_errors()` returns `ValidationError` with `.validator` == `"required"` or `"type"` — confirmed by running in this session
- VERIFIED: `tiktoken.get_encoding("cl100k_base").encode()` works on prompt strings — confirmed in this session
- VERIFIED: OpenAI `choices[0].finish_reason` and Anthropic `stop_reason` parsing logic — confirmed with sample payloads in this session
- VERIFIED: Unclosed-delimiter heuristic correctly classifies truncated vs. valid JSON — confirmed with test cases in this session

### Tertiary (LOW confidence)

None.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and verified working
- Architecture: HIGH — implementation follows the exact established pattern from `tool_call_analyzer.py`
- Pitfalls: HIGH — verified through direct execution of edge cases in this session

**Research date:** 2026-05-21
**Valid until:** Stable — no external dependencies changing; valid until project architecture changes

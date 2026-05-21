---
phase: 24-structural-span-checks
verified: 2026-05-21T00:00:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
---

# Phase 24: Structural Span Checks — Verification Report

**Phase Goal:** System detects output schema violations, truncated outputs, type errors, token overflow, and prompt injection at the span level using only deterministic/heuristic signals — no embedding calls
**Verified:** 2026-05-21
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `output_schema_analyzer.py` implements `OutputSchemaAnalyzer(BaseSpanAnalyzer)` with `name` returning `"output_schema"` | VERIFIED | Line 48: `class OutputSchemaAnalyzer(BaseSpanAnalyzer)` — line 57-59: `@property name` returns `"output_schema"`. No `__init__` override (D-06). |
| 2 | `analyze()` dispatches to all 5 `_check_*` methods and returns `list[Flag]` | VERIFIED | Lines 61-73: `flags.extend()` chain calling all 5 methods. 31/31 tests pass. |
| 3 | SCHEMA-01 fires only on response-not-JSON when schema set (sub-case A); embedder never called | VERIFIED | `_check_output_schema_violation` at lines 79-101: guards on `None`, then `json.loads(span.response)`. 5 tests pass. |
| 4 | SCHEMA-02 fires when `tool_arguments` missing required fields via `jsonschema.Draft7Validator` | VERIFIED | `_check_required_fields_missing` at lines 184-215: `e.validator == "required"` filter. 4 tests pass. |
| 5 | SCHEMA-03 fires on `finish_reason=length` (OpenAI), `stop_reason=max_tokens` (Anthropic), or unclosed delimiter | VERIFIED | `_parse_finish_reason` normalizes Anthropic path (line 130-131); `_has_unclosed_delimiter` implements Pitfall 3 end-char heuristic. 7 tests pass. |
| 6 | SCHEMA-04 fires on type violations via `jsonschema.Draft7Validator` filtered by `e.validator == "type"` | VERIFIED | `_check_type_coercion_error` at lines 221-251. Detail key `"type_errors"`. 4 tests pass. |
| 7 | CTX-01 counts tokens via lazy tiktoken `cl100k_base` and fires when `>self._thresholds["context_overflow"]`; logs numeric token count BEFORE threshold | VERIFIED | `_get_tiktoken()` lazy loader at lines 36-41; `_check_context_overflow` lines 257-284: `log_score("prompt_token_count", float(token_count))` before threshold. No numeric literal `8000` in implementation (comment only). 5 tests pass. |
| 8 | Worker process instantiates `OutputSchemaAnalyzer` alongside `ToolCallAnalyzer`; `THRESHOLDS` includes `context_overflow=8000` | VERIFIED | `main.py` line 45 import; line 59 `context_overflow` in THRESHOLDS dict; lines 179-182 ANALYZERS list has both analyzers. |
| 9 | `calibrate.py` registries extended: 12-entry `FLAG_TYPES`, 12-entry `FLAG_TYPE_TO_ANALYZER_CLASS`, 7-entry `BINARY_FLAG_TYPES` (context_overflow excluded), 6-entry `DEFAULT_THRESHOLDS` | VERIFIED | Lines 48-61 FLAG_TYPES (12 entries), lines 72-85 FLAG_TYPE_TO_ANALYZER_CLASS (12 entries), lines 90-97 BINARY_FLAG_TYPES (7 entries, context_overflow absent), lines 101-108 DEFAULT_THRESHOLDS (6 entries). All confirmed by 5 new tests in `test_calibrate_routing.py`. |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `xeter/tests/worker/test_output_schema_analyzer.py` | 31-test RED-then-GREEN scaffold | VERIFIED | 511 lines, 31 test functions. All 31 pass. |
| `xeter/services/worker/output_schema_analyzer.py` | OutputSchemaAnalyzer with 5 checks | VERIFIED | 284 lines. No stubs. All check methods implemented. |
| `xeter/services/worker/main.py` | OutputSchemaAnalyzer wired into ANALYZERS + context_overflow in THRESHOLDS | VERIFIED | Import line 45; THRESHOLDS line 59; ANALYZERS lines 179-182. |
| `xeter/scripts/calibrate.py` | 4 registries extended with 5 Phase 24 flag types | VERIFIED | All 4 registries extended correctly per plan spec. |
| `xeter/tests/test_calibrate_routing.py` | 2 tests updated, 5 new tests (tests 11-15) | VERIFIED | 15 tests total, all pass. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `test_output_schema_analyzer.py` | `xeter.services.worker.output_schema_analyzer.OutputSchemaAnalyzer` | `from` import at line 15 | WIRED | Import present verbatim as required |
| `OutputSchemaAnalyzer.analyze` | 5 private `_check_*` methods | `flags.extend()` dispatch chain | WIRED | Lines 68-72: all 5 extend calls |
| `_check_context_overflow` | module-level `_TIKTOKEN_ENCODING` cache | `_get_tiktoken()` lazy loader | WIRED | `_get_tiktoken()` called at line 269 |
| `_check_required_fields_missing` | `jsonschema.Draft7Validator.iter_errors()` filtered by `e.validator == "required"` | list comprehension | WIRED | Line 201-203 |
| `_check_type_coercion_error` | `jsonschema.Draft7Validator.iter_errors()` filtered by `e.validator == "type"` | list comprehension | WIRED | Lines 236-239 |
| `main.py THRESHOLDS` | `OutputSchemaAnalyzer._check_context_overflow` | `OutputSchemaAnalyzer(embedder, THRESHOLDS)` | WIRED | Line 181: both analyzers share THRESHOLDS dict |
| `calibrate.py FLAG_TYPE_TO_ANALYZER_CLASS` | `OutputSchemaAnalyzer` class | dict values lines 81-85 | WIRED | All 5 Phase 24 keys map to `OutputSchemaAnalyzer` class object |

---

### Data-Flow Trace (Level 4)

Not applicable — `OutputSchemaAnalyzer` is a pure computation module (no dynamic DB-sourced data to trace). Span data is passed in directly from the worker pipeline; the checks transform input fields deterministically. The 31 unit tests with explicit `make_span()` fixtures are the appropriate verification channel.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 31 OutputSchemaAnalyzer tests pass | `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py -v` | 31 passed, 0 failed | PASS |
| All 15 calibrate routing tests pass | `python -m pytest xeter/tests/test_calibrate_routing.py -v` | 15 passed, 0 failed | PASS |
| Worker loop tests unaffected | `python -m pytest xeter/tests/worker/test_worker_loop.py -v` | 6 passed, 0 failed | PASS |
| Full suite: 13 pre-existing spaCy failures, 0 new failures | `python -m pytest xeter/tests/ -q` | 197 passed, 9 skipped, 13 pre-existing `ModuleNotFoundError: No module named 'spacy'` failures (unchanged from Phase 23 baseline) | PASS |

---

### Probe Execution

No probe scripts declared for Phase 24. The behavioral spot-checks above serve as equivalent verification.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SCHEMA-01 | 24-01, 24-02, 24-03 | Flag `output_schema_violation` — JSON parse failure on `response` when schema set | SATISFIED | `_check_output_schema_violation` implemented; 5 passing tests; registered in all 4 calibrate.py registries |
| SCHEMA-02 | 24-01, 24-02, 24-03 | Flag `required_fields_missing` — jsonschema `required` validator errors | SATISFIED | `_check_required_fields_missing` implemented; 4 passing tests |
| SCHEMA-03 | 24-01, 24-02, 24-03 | Flag `output_truncated` — `finish_reason=length` or unclosed delimiter | SATISFIED | `_check_output_truncated` with `_parse_finish_reason` (OpenAI+Anthropic) and `_has_unclosed_delimiter`; 7 passing tests |
| SCHEMA-04 | 24-01, 24-02, 24-03 | Flag `type_coercion_error` — jsonschema `type` validator errors | SATISFIED | `_check_type_coercion_error` implemented; 4 passing tests |
| CTX-01 | 24-01, 24-02, 24-03 | Flag `context_overflow` — tiktoken cl100k_base exceeds threshold | SATISFIED | `_check_context_overflow` with lazy tiktoken; 5 passing tests; `context_overflow` in THRESHOLDS and DEFAULT_THRESHOLDS |
| CTX-03 | NONE (orphaned in REQUIREMENTS.md) | Flag `prompt_injection` — injection patterns in tool_output | NOT SATISFIED — see note below | REQUIREMENTS.md maps CTX-03 to Phase 24, but Phase 24 CONTEXT.md decision D-02 explicitly removes it from scope with rationale ("belongs in a later phase once the core schema checks are shipped and calibrated"). No later phase currently claims CTX-03 per ROADMAP. |

**Note on CTX-03 (orphaned requirement):** REQUIREMENTS.md line 80 maps CTX-03 to Phase 24, but the Phase 24 CONTEXT.md (decision D-02) explicitly removes it from scope. No plan in Phase 24 lists CTX-03 in its `requirements:` field. CTX-03 is not implemented anywhere in the codebase. This is a known intentional deferral documented in the phase context — but REQUIREMENTS.md has not been updated to reflect the deferral. This is classified as a WARNING (incomplete bookkeeping), not a BLOCKER, because:
1. The phase goal statement says "detects output schema violations, truncated outputs, type errors, token overflow, and **prompt injection**" — the goal text includes prompt injection
2. CTX-03 is not implemented
3. D-02 is an internal planning decision, not a REQUIREMENTS.md update
4. No later phase currently claims CTX-03 in the ROADMAP

**This requires a human decision** — see Human Verification Required section below.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

No `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, or `PLACEHOLDER` markers in any Phase 24 file. No stub returns that flow to user-visible output. The `return []` occurrences in `output_schema_analyzer.py` are legitimate early-exit guards with documented D-04 rationale, not stubs — the corresponding check simply did not participate (early guard path). No top-level `import tiktoken` (only inside `_get_tiktoken()`). No numeric literal `8000` in implementation code (appears only in a comment).

---

### Human Verification Required

#### 1. CTX-03 Scope Decision

**Test:** Determine whether CTX-03 (`prompt_injection`) should be in Phase 24 scope.

**Expected:** One of:
- REQUIREMENTS.md is updated to move CTX-03 to a future phase (e.g., Phase 25 or Phase 26), removing it from the Phase 24 row — then Phase 24 passes cleanly on all 5 declared requirements
- Or a new plan for Phase 24 is created implementing `prompt_injection` via `_INJECTION_PATTERNS` regex list in `OutputSchemaAnalyzer`

**Why human:** The phase goal statement ("...prompt injection...") and REQUIREMENTS.md both reference CTX-03 for Phase 24. Decision D-02 removed it from scope, but this was an internal planning decision that was not propagated back to REQUIREMENTS.md. The verifier cannot determine whether the intent was to (a) complete Phase 24 without CTX-03 and update the requirements table, or (b) defer CTX-03 to a future phase while keeping Phase 24's goal statement inaccurate. This is a scope/requirements bookkeeping decision requiring human judgment.

---

## Gaps Summary

No implementation gaps exist. The 5 requirement IDs listed in all three plans (SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04, CTX-01) are fully implemented, tested (31 passing tests), and wired end-to-end. The implementation is substantive (not stubbed), all key links are verified, and no pre-existing test regressions were introduced.

The only unresolved item is a **requirements bookkeeping gap**: REQUIREMENTS.md maps CTX-03 to Phase 24 but Phase 24 did not implement it. Phase goal text includes "prompt injection." This was explicitly deferred by decision D-02, but REQUIREMENTS.md was not updated. This is a documentation/scope alignment issue, not an implementation defect.

---

_Verified: 2026-05-21_
_Verifier: Claude (gsd-verifier)_

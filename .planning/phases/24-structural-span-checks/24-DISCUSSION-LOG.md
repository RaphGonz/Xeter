# Phase 24: Structural Span Checks - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 24-structural-span-checks
**Areas discussed:** SCHEMA-01 sub-case B scope, Phase 24 scope clarification, Context overflow threshold, Binary check scoring strategy

---

## Phase Scope Clarification

User clarified during the injection pattern discussion: Phase 24 should be structural schema validation only — checking that the structure asked in the prompt matches the output. This led to removing CTX-03 (prompt_injection) from the phase.

| Option | Description | Selected |
|--------|-------------|----------|
| Schema checks only (SCHEMA-01–04 + CTX-01) | Drop CTX-03 from Phase 24 | ✓ |
| Schema checks + prompt injection (CTX-03) | Keep CTX-03 in Phase 24 | |

**User's choice:** Schema checks only
**Notes:** User said "we just want to check if the structure asked in the prompt is the same in output" — confirming Phase 24 is purely structural schema validation. CTX-03 deferred to a later phase.

---

## SCHEMA-01 Sub-Case B Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Both sub-cases | Sub-case A (schema mismatch) + sub-case B (no tool_use in raw_response) | |
| Sub-case A only | Only fire when expected_output_schema is set and response is free text | ✓ |
| Sub-case B as separate flag type | Sub-case B as `tool_call_suppressed` distinct from `output_schema_violation` | |

**User's choice:** Sub-case A only
**Notes:** Sub-case B overlaps with existing `no_tool_used` check; deferred to avoid redundant signal.

---

## Context Overflow Threshold

| Option | Description | Selected |
|--------|-------------|----------|
| 100,000 tokens | Conservative for large cloud models | |
| 128,000 tokens | Matches GPT-4 Turbo / Claude 3 context limit | |
| You decide | Delegate to Claude | |
| 8,000 tokens | Covers local model context windows | ✓ |
| 4,000 tokens | Smallest local models | |
| 32,000 tokens | Larger local models only | |

**User's choice:** 8,000 tokens
**Notes:** User noted target users run local models (Ollama, Llama, Mistral) with 4k–32k context windows. 100k default was too high and would never fire in practice. 8k was agreed as the right baseline for the actual deployment target.

---

## Binary Check Scoring Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Binary 1.0/0.0 | log_score 1.0 on flag, 0.0 on pass — consistent with tool_not_available | ✓ |
| Continuous quantity | log actual count (token count, violation count) where meaningful | |

**User's choice:** Binary 1.0/0.0
**Notes:** Keeps span_scores values in [0, 1], consistent with existing binary check pattern. Calibration hill-climb designed for this value range.

---

## Claude's Discretion

- **D-06 (OutputSchemaAnalyzer constructor):** Keep `__init__(self, embedder, thresholds)` signature identical to `BaseSpanAnalyzer` for interface consistency, even though Phase 24 checks don't use the embedder.
- **finish_reason parsing approach:** Parse from `raw_response` JSON at check time (not a new SpanData field). Resilient to provider format differences (OpenAI vs Anthropic).

---

## Deferred Ideas

- **CTX-03 (prompt_injection):** Removed from Phase 24 scope entirely. Future phase.
- **SCHEMA-01 sub-case B:** `available_tools` present + no tool_use in raw_response. Deferred — overlaps with `no_tool_used`.

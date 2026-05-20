# Phase 23: Infrastructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 23-infrastructure
**Areas discussed:** expected_output_schema scope, calibrate.py multi-analyzer routing, ClickHouse schema change strategy

---

## expected_output_schema scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full pipeline (SDK + ingest + CH + SpanData + fetcher) | Phase 23 wires the field end-to-end so Phases 24+ only need to write check logic | ✓ |
| Backend only (CH column + SpanData + fetcher) | Defer SDK/ingest to Phase 24 when the check is first exercised. Simpler phase. | |

**User's choice:** Full pipeline
**Notes:** User explicitly stated: "The following phases should only focus on the new checks." Confirms full pipeline is deliberate — not about feature completeness, but about keeping later phases clean.

Follow-up — decorator-level vs call-time:

| Option | Description | Selected |
|--------|-------------|----------|
| Decorator-level | Schema fixed at decoration time — same pattern as tool_name, parent_span_id | ✓ |
| Call-time (runtime kwarg) | Schema varies per invocation | |

**User's choice:** Decorator-level
**Notes:** No clarification needed — user accepted the recommended option immediately.

---

## calibrate.py multi-analyzer routing

| Option | Description | Selected |
|--------|-------------|----------|
| Static registry dict | `FLAG_TYPE_TO_ANALYZER_CLASS: dict[str, type]` in calibrate.py — same pattern as FLAG_TYPE_ALIAS | ✓ |
| Class-level declaration | Each analyzer carries `HANDLED_FLAG_TYPES: frozenset[str]`; calibrate.py scans KNOWN_ANALYZERS | |
| You decide | Planner picks the cleanest approach | |

**User's choice:** Static registry dict
**Notes:** User asked for clarification about the overall context of the discussion before answering. After explanation, accepted the recommended option.

---

## ClickHouse schema change strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Idempotent ALTER TABLE at startup | `ALTER TABLE spans ADD COLUMN IF NOT EXISTS` in analyser startup lifespan, after create_spans_table(). No-op if column exists. | ✓ |
| Update DDL only (new deployments) | Add column to SPANS_TABLE_DDL. Existing volumes need manual ALTER TABLE + docs. | |

**User's choice:** Idempotent ALTER TABLE at startup
**Notes:** User accepted the recommended option without hesitation.

---

## Claude's Discretion

None — user provided clear direction on all three areas.

## Deferred Ideas

None — discussion stayed within phase scope.

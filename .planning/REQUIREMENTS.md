# Requirements: Xeter v1.4

**Defined:** 2026-05-12
**Core Value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.

## v1.4 Requirements

### Cleanup (CLEAN) — v1.3 Tech Debt

- [x] **CLEAN-01**: Dead `verify_session_token()` function removed from `diagnosticer/main.py` (lines 78–94); INTERNAL_API_KEY middleware via `InternalApiKeyMiddleware` is the sole auth boundary on Diagnosticer
- [x] **CLEAN-02**: Stale "NO PostgreSQL RLS" comments corrected in `spans.py` (lines 9/442); comments updated to reflect migration 004 which added RLS
- [x] **CLEAN-03**: Env var defaults audit completed — all `:- fallback` patterns and development defaults reviewed against production requirements; dangerous defaults documented or removed

### Trace API (TRACE) — Presenter Endpoints

- [x] **TRACE-01**: Operator can list all traces for their tenant via `GET /traces` — response includes trace_id, span count, flag count, time_begin, time_end per trace; results ordered by time_begin descending; scoped to authenticated tenant via RLS
- [x] **TRACE-02**: Operator can fetch a full trace via `GET /traces/{trace_id}` — response includes all spans in the trace with their flags and scores, assembled from ClickHouse (spans) + PostgreSQL (flags, scores); returns 404 if trace_id not found or belongs to another tenant

### Trace UI (UI) — Dashboard Views

- [ ] **UI-01**: Dashboard includes a Traces list page — shows all traces with span count, flag count, and time range; accessible from main navigation
- [ ] **UI-02**: Trace detail page renders a collapsible span tree using `parent_span_id` — spans with no parent rendered at root level; children nested beneath parent; each span row shows flag type badges
- [ ] **UI-03**: Span detail view includes a "Back to trace" link — navigates to the parent `GET /traces/{trace_id}` view with the span highlighted or scrolled into view

### TraceAnalyzer Foundation (TANA) — Worker Infrastructure

- [x] **TANA-01**: `BaseAnalyzer` in `worker/base.py` refactored into: (a) generic `BaseAnalyzer` root retaining `name`, `embed`, `compare`, `log_score`, `flush_scores`; (b) `BaseSpanAnalyzer(BaseAnalyzer)` with abstract `analyze(span: SpanData) -> list[Flag]`; (c) `BaseTraceAnalyzer(BaseAnalyzer)` with abstract `analyze(spans: list[SpanData]) -> list[Flag]`; `ToolCallAnalyzer` updated to inherit `BaseSpanAnalyzer`; all import paths updated
- [x] **TANA-02**: `TraceAnalyzer(BaseTraceAnalyzer)` scaffold created in `worker/trace_analyzer.py` — implements `analyze(spans)` returning `[]`; registered in worker alongside span analyzers
- [x] **TANA-03**: Worker accumulates processed spans by `trace_id` in an in-memory buffer; after each span is processed, checks whether the flush timeout has elapsed for that trace_id; invokes `TraceAnalyzer.analyze(spans)` and writes any returned flags; timeout duration configurable via `WORKER_TRACE_FLUSH_TIMEOUT_S` env var (default: 30s)
- [x] **TANA-04**: PostgreSQL `flags` table extended via migration — `span_id` column made nullable (trace-level flags have no single span); `trace_id` column made non-nullable (all flags, span-level and trace-level, reference their trace); existing rows migrated with `trace_id` backfilled from ClickHouse spans table; flag_writer.py and score_writer.py updated

## v2 Requirements (Deferred to v1.5+)

### New Analyser Checks

- **B1–B4**: Output/Schema Failures — free text vs schema, missing fields, truncated output, type mismatches
- **C3–C4**: Reasoning/Planning — step repetition, unaware of termination condition
- **D1–D3, D5**: Context/Memory — context propagation failure, conversation history loss, prompt overflow, stale context
- **E3**: Instruction Following — prompt injection in tool output
- **F1–F2, F4–F5**: Multi-Agent/Handoff — wrong agent, information withholding, conversation reset, fail to clarify
- **G1–G2**: Verification — no verification span, incomplete verification
- **H2**: Output Content — missing details

### Auth & Security

- **AUTH-F01**: Refresh token revocation store — server-side blacklist for stolen token detection
- **AUTH-F02**: python-jose → PyJWT migration — python-jose near-abandoned, CVE risk
- **OPS-F01**: Rate limiting on Analyser ingestion — per-API-key sliding window, Redis, 429 with Retry-After

### SDK Expansion

- **SDK-F01**: TypeScript/Node.js SDK for instrumenting JS-based agents

## Out of Scope

| Feature | Reason |
|---------|--------|
| Prompt management / versioning | Competes with Langfuse on their home turf; not our moat |
| LLM cost attribution / billing analytics | General observability breadth, not diagnosis |
| Multi-model A/B comparison | Established players own this |
| LLM-as-a-judge eval pipelines | HoneyHive and LangSmith have mature offerings |
| On-premise distribution | SaaS only per constraints |
| Clerk auth migration | Deferred; schema supports it; needed when multi-member tenants required |
| Per-service MinIO IAM accounts | Single bucket policy sufficient for current threat model |
| ClickHouse per-service read-only users + row policies | Python DAL is enforcement layer |
| Per-tenant Redis queue keys | Worker refactor independent from current priorities |
| Real-time SSE for trace streaming | Deferred; REST polling sufficient for v1.4 scale |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLEAN-01 | Phase 18 | Complete |
| CLEAN-02 | Phase 18 | Complete |
| CLEAN-03 | Phase 18 | Complete |
| TANA-01 | Phase 18 | Complete |
| TANA-02 | Phase 19 | Complete |
| TANA-03 | Phase 19 | Complete |
| TANA-04 | Phase 19 | Complete |
| TRACE-01 | Phase 20 | Complete |
| TRACE-02 | Phase 20 | Complete |
| UI-01 | Phase 21 | Pending |
| UI-02 | Phase 21 | Pending |
| UI-03 | Phase 21 | Pending |

**Coverage:**
- v1.4 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-12*
*Last updated: 2026-05-12 after v1.4 milestone initialization*

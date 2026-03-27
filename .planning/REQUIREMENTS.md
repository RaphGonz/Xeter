# Requirements: Xeter

**Defined:** 2026-03-27
**Core Value:** When an AI agent silently fails, tell the developer what went wrong, where in the pipeline it happened, and why — starting with tool-call anomalies as the first detection category.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### SDK & Ingestion

- [ ] **SDK-01**: Python SDK wraps OTel instrumentation and emits spans via OTLP HTTP to the Analyser
- [ ] **SDK-02**: SDK captures all span fields: agent_name, agent_model, recipient, recipient_model, tool_name, tool_description, tool_output, prompt, response, raw_response
- [ ] **SDK-03**: SDK supports trace grouping via trace_id and parent_span_id
- [ ] **SDK-04**: SDK includes schema versioning field (xeter.schema.version) for forward compatibility
- [ ] **SDK-05**: SDK authenticates via API key sent with each span batch

### Anomaly Detection (Flagging)

**Architecture:** The flagging pipeline is a registry of independent analyzers. Each analyzer receives a span, runs its detection logic, and returns zero or more flags. Tool-call anomalies are the first analyzer category; the system is designed to support arbitrary future categories (loop detection, hallucination, instruction violation, context overflow, etc.) without modifying the pipeline or existing analyzers.

- [ ] **FLAG-01**: Flagging pipeline implements analyzer registry pattern — analyzers register independently, pipeline dispatches spans to all registered analyzers
- [ ] **FLAG-02**: Each analyzer defines its own flag types, scoring logic, and thresholds via a common interface
- [ ] **FLAG-03**: flag_type field in PostgreSQL is an open string (not enum) to support future analyzer categories without schema changes
- [ ] **FLAG-04**: Tool-call analyzer: vector similarity between prompt and tool_name to detect wrong tool usage
- [ ] **FLAG-05**: Tool-call analyzer: vector similarity between prompt and tool_description to detect semantic mismatch
- [ ] **FLAG-06**: Tool-call analyzer: vector similarity between prompt and response to detect response anomalies
- [ ] **FLAG-07**: Tool-call analyzer: embedding of model_name + prompt to detect parsing error patterns
- [ ] **FLAG-08**: Tool-call analyzer classifies anomalies into flag types: wrong_tool, no_tool, excessive_tool, parsing_error
- [ ] **FLAG-09**: Similarity thresholds are configurable per analyzer, not hardcoded
- [ ] **FLAG-10**: All similarity scores are logged for every span (flagged or not) to enable future threshold calibration

### Storage

- [ ] **STOR-01**: Spans are stored as immutable rows in ClickHouse with ORDER BY (tenant_id, trace_id, time_begin)
- [ ] **STOR-02**: Large text payloads (prompt, response, raw_response) are stored in S3 with reference keys in ClickHouse
- [ ] **STOR-03**: Flags are stored as append-only rows in PostgreSQL with span_id, flag_type, score, and detail
- [ ] **STOR-04**: ClickHouse writes are batched via Redis queue — no single-row inserts
- [ ] **STOR-05**: Redis queue decouples span ingestion from embedding worker processing

### Dashboard

- [ ] **DASH-01**: Developer can view a list of spans with flag indicators showing anomaly status
- [ ] **DASH-02**: Developer can filter spans by flag type, agent name, and time range
- [ ] **DASH-03**: Developer can view span detail showing flag details and similarity scores
- [ ] **DASH-04**: Developer can view prompt, response, and raw_response content lazy-loaded from S3
- [ ] **DASH-05**: Span list rows show similarity scores directly (flag score overlay)

### Auth & Multi-tenancy

- [ ] **AUTH-01**: Each tenant has an API key for SDK ingestion; key hash stored in PostgreSQL
- [ ] **AUTH-02**: Developer can log into the dashboard with email and password
- [ ] **AUTH-03**: All database queries are scoped by tenant_id in application code
- [ ] **AUTH-04**: PostgreSQL has Row-Level Security policies as defense-in-depth against cross-tenant data leaks
- [ ] **AUTH-05**: Developer can create an account (tenant registration)

### Infrastructure

- [ ] **INFR-01**: Docker Compose provides local dev environment with ClickHouse, PostgreSQL, Redis, MinIO (S3), backend, and frontend services
- [ ] **INFR-02**: Diagnosticer service is scaffolded — wired to Presenter, accepts requests, returns placeholder response — ready for LLM integration in milestone 2

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Diagnostics (LLM Layer)

- **DIAG-01**: Developer can trigger LLM-powered diagnostic analysis on a trace from the dashboard
- **DIAG-02**: Diagnosticer reads full trace context + flags and sends to configured LLM
- **DIAG-03**: Diagnostic result explains root cause as model, architecture, or prompt failure with reasoning
- **DIAG-04**: LLM backend is configurable per tenant (external API or local model)

### Dashboard Enhancements

- **DASH-06**: Visual trace tree showing parent/child span relationships with flag overlay
- **DASH-07**: SSE push events for real-time flag updates and diagnostic completion
- **DASH-08**: Session grouping (session_id field for grouping related traces)

### SDK Expansion

- **SDK-06**: TypeScript SDK (lags Python by one release cycle per AD-18)

### Auth Expansion

- **AUTH-06**: Clerk migration for multi-member tenants, SSO/SAML for enterprise

### Future Analyzer Categories

- **ANLZ-01**: Loop detection analyzer — detects agents stuck in repetitive tool-call loops
- **ANLZ-02**: Instruction violation analyzer — detects when agent actions contradict explicit prompt instructions (e.g., "don't use X" but X was used)
- **ANLZ-03**: Hallucination analyzer — detects when agent references non-existent tools or fabricates tool outputs
- **ANLZ-04**: Context overflow analyzer — detects when context window limits cause truncated or degraded responses

### Alerting

- **ALRT-01**: Configurable alerts when flag thresholds are breached

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Prompt management / versioning | Competes with Langfuse/LangSmith on their home turf; not our moat |
| LLM cost attribution / billing analytics | General observability breadth — not diagnosis |
| Multi-model A/B comparison | Established players own this; our moat is root-cause diagnosis |
| LLM-as-a-judge eval pipelines | HoneyHive and LangSmith have mature offerings; we differentiate on automated flagging |
| On-premise distribution | SaaS only per architecture constraints |
| Cloud deployment | Deferred; local-first for v1 |
| Real-time alerting | No competitor has shipped it yet (Langfuse's most requested feature); safe to defer |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SDK-01 | — | Pending |
| SDK-02 | — | Pending |
| SDK-03 | — | Pending |
| SDK-04 | — | Pending |
| SDK-05 | — | Pending |
| FLAG-01 | — | Pending |
| FLAG-02 | — | Pending |
| FLAG-03 | — | Pending |
| FLAG-04 | — | Pending |
| FLAG-05 | — | Pending |
| FLAG-06 | — | Pending |
| FLAG-07 | — | Pending |
| FLAG-08 | — | Pending |
| FLAG-09 | — | Pending |
| FLAG-10 | — | Pending |
| STOR-01 | — | Pending |
| STOR-02 | — | Pending |
| STOR-03 | — | Pending |
| STOR-04 | — | Pending |
| STOR-05 | — | Pending |
| DASH-01 | — | Pending |
| DASH-02 | — | Pending |
| DASH-03 | — | Pending |
| DASH-04 | — | Pending |
| DASH-05 | — | Pending |
| AUTH-01 | — | Pending |
| AUTH-02 | — | Pending |
| AUTH-03 | — | Pending |
| AUTH-04 | — | Pending |
| AUTH-05 | — | Pending |
| INFR-01 | — | Pending |
| INFR-02 | — | Pending |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 0
- Unmapped: 32

---
*Requirements defined: 2026-03-27*
*Last updated: 2026-03-27 after initial definition*

# Xeter

## What This Is

Xeter is a B2B SaaS observability platform that debugs AI agent tool-calling failures. It ingests OpenTelemetry spans from instrumented agent code via a Python SDK, applies heuristic analysis (vector similarity between prompt and tool fields) to flag anomalous tool calls, and exposes a dashboard where developers can see what went wrong and why. Unlike existing tools that show traces, Xeter isolates root cause — model, architecture, or prompt.

## Core Value

When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

- [ ] Python SDK that instruments agent code and emits OTel spans to the Analyser
- [ ] Analyser receives spans, stores them in ClickHouse, and enqueues for async heuristic analysis
- [ ] Heuristic flagging: vector similarity comparing prompt vs tool_name, tool_description, response; model+prompt for parsing errors
- [ ] Flag types: wrong_tool, no_tool, excessive_tool, parsing_error
- [ ] Flags stored as append-only rows in PostgreSQL with score and detail
- [ ] Large text payloads (prompt, response, raw_response) stored in S3 with reference keys in ClickHouse
- [ ] Redis queue decoupling ingestion from embedding workers
- [ ] Dashboard: span list view with flag indicators and filtering
- [ ] Dashboard: span detail view showing flag details and S3 payload content (lazy-loaded)
- [ ] Auth: API key per tenant for SDK ingestion (key hash in PostgreSQL)
- [ ] Auth: email/password login for dashboard (Path A — self-hosted)
- [ ] Multi-tenancy: tenant_id on all tables, row-level isolation
- [ ] Diagnosticer service scaffolded (wired to Presenter, accepts requests, returns placeholder — ready for LLM integration in next milestone)
- [ ] Docker Compose for local development (ClickHouse, PostgreSQL, Redis, MinIO for S3, backend, frontend)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- LLM-powered diagnostics (Diagnosticer active) — deferred to milestone 2; service is scaffolded but not functional
- TypeScript SDK — Python first; TS lags by one release cycle per AD-18
- Cloud deployment — local-first; cloud is a later phase
- Clerk auth migration (Path B) — future; schema supports it but not implemented
- Trace tree visualization — v1 is span list + flags; tree view is a later enhancement
- SSE push events — v1 uses polling or manual refresh; SSE deferred
- On-premise distribution — SaaS only per constraints

## Context

- Architecture fully documented in arc42 format (documentation/xeter-arc42.md)
- Foundation sprint completed: competitor analysis, hypothesis, positioning, approach evaluation done
- Hybrid Layered Debugger (A4) is the chosen approach — A3 (schema validation + vector matching) ships first as this milestone
- Main adversary is Langfuse — open-source, self-hostable, framework-agnostic, but doesn't diagnose root cause
- Differentiators: explains the why behind failures (not just traces), integrates into any stack with minimal friction
- Solo developer building this; Python is primary language for backend and SDK
- Storage architecture: ClickHouse (immutable spans) + PostgreSQL (flags, diagnostics, auth, tenants) + S3 (large payloads) + Redis (ingestion queue)
- Data model, runtime flows, and quality scenarios defined in arc42 doc

## Constraints

- **Tech stack**: Python backend + Python SDK primary; ClickHouse + PostgreSQL + S3 + Redis for storage
- **Solo developer**: Single maintainer — scope must stay tight; progressive building is essential
- **SaaS only**: No on-premise distribution in v1
- **Correctness over speed**: False positive flags erode trust — embedding threshold calibration is critical (R-03)
- **View has no logic**: All business logic in backend services per AD-04

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| A4 approach (A3 first) | Best global pattern across all evaluation matrices; A3 is natural first milestone | — Pending |
| ClickHouse for spans | OLAP, append-only, proven at scale by competitors (Langfuse, LangSmith) | — Pending |
| PostgreSQL for flags/diagnostics/auth | Low volume, mutable, relational; append-only pattern | — Pending |
| S3 for large payloads | Prevents row bloat in ClickHouse; lazy retrieval preferred | — Pending |
| Redis for ingestion queue | Decouples ingestion from embedding; standard worker pattern | — Pending |
| Async flagging | Span ingestion must not be blocked by embedding computation (AD-01) | — Pending |
| Diagnosticer as separate service | LLM calls are slow and on-demand; isolation allows independent scaling (AD-02) | — Pending |
| REST + SSE for Presenter | REST for queries/actions; SSE for push events (AD-13) | — Pending |
| Email/password auth first, Clerk later | Zero external dependency for early development; schema supports migration (AD-14) | — Pending |
| Scaffold Diagnosticer in v1 | Wired but inactive — enables progressive building without rearchitecting later | — Pending |

---
*Last updated: 2026-03-27 after initialization*

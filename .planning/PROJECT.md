# Xeter

## What This Is

Xeter is a B2B SaaS observability platform that debugs AI agent tool-calling failures. It ingests OpenTelemetry spans from instrumented agent code via a Python SDK, applies heuristic analysis (vector similarity between prompt and tool fields) to flag anomalous tool calls, and exposes a dashboard where developers can see what went wrong and why. Unlike existing tools that show traces, Xeter isolates root cause — model, architecture, or prompt.

v1.0 shipped: full pipeline from SDK to dashboard running locally via Docker Compose.

## Core Value

When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Python SDK that instruments agent code and emits OTel spans to the Analyser — v1.0
- ✓ Analyser receives spans, stores them in ClickHouse (batched), S3 (large payloads), and enqueues for async embedding analysis — v1.0
- ✓ Heuristic flagging: vector similarity across 5 dimensions (prompt vs tool_name, tool_description, response, available_tools ranking, tool_arguments); flag types: wrong_tool, wrong_tool_args, no_tool, excessive_tool, parsing_error — v1.0
- ✓ Flags stored as append-only rows in PostgreSQL with score and detail; flag_type is open string (no enum) — v1.0
- ✓ Large text payloads stored in S3 with reference keys in ClickHouse; tool_arguments inline as JSON — v1.0
- ✓ Redis queue decoupling ingestion from embedding workers — v1.0
- ✓ Dashboard: span list with flag indicators, filtering by flag_type/agent_name/time range — v1.0
- ✓ Dashboard: span detail with flag details, similarity scores, and lazy-loaded S3 payload content — v1.0
- ✓ Auth: API key per tenant for SDK ingestion; email/password login for dashboard — v1.0
- ✓ Multi-tenancy: tenant_id on all tables, RLS in PostgreSQL, tenant guard in DAL — v1.0
- ✓ Diagnosticer service scaffolded (501 placeholder, wired to Presenter) — v1.0
- ✓ Docker Compose for local development (ClickHouse, PostgreSQL, Redis, MinIO, backend, frontend) — v1.0

### Active

<!-- v1.1 scope — Analyser Accuracy -->

- [ ] Redesign `_check_wrong_tool` with correct conceptual signal
- [ ] Redesign `_check_wrong_args` with correct conceptual signal
- [ ] Split `_check_no_tool` into two methods: capability gap (tool needed, none called) + tool-use violation (prompt forbids tools, tool called anyway)
- [ ] Redesign `_check_excessive_tool` with span-local multi-signal approach (prompt vs each called tool, per-span)

## Current Milestone: v1.1 Analyser Accuracy

**Goal:** Replace the four conceptually-wrong heuristic check methods in ToolCallAnalyzer with research-backed, correctly-reasoned implementations — one method at a time, user-piloted.

**Target features:**
- Redesigned `_check_wrong_tool`
- Redesigned `_check_wrong_args`
- Split `_check_no_tool` → `_check_no_tool` + `_check_tool_use_violation`
- Redesigned `_check_excessive_tool` (span-local signals only)

### Out of Scope

<!-- Explicit boundaries. -->

- Prompt management / versioning — competes with Langfuse on their home turf; not our moat
- LLM cost attribution / billing analytics — general observability breadth, not diagnosis
- Multi-model A/B comparison — established players own this
- LLM-as-a-judge eval pipelines — HoneyHive and LangSmith have mature offerings
- On-premise distribution — SaaS only per constraints
- Clerk auth migration — future; schema supports it, deferred to when multi-member tenants are needed

## Context

- v1.0 shipped 2026-04-04: full pipeline operational locally via Docker Compose
- ~12,660 LOC (10,400 Python + 2,255 TypeScript), 219 files
- Tech stack: Python 3.12, FastAPI, ClickHouse, PostgreSQL (RLS), Redis, MinIO (S3), Next.js 15, sentence-transformers (all-MiniLM-L6-v2)
- Architecture: Analyser (ingestion) → Redis queue → Worker (embedding) → Presenter (read/auth) → View (Next.js); Diagnosticer scaffolded
- Calibration: precision target 80%; wrong_tool_args excluded from P/R (low-confidence by design)
- Main adversary: Langfuse — open-source, self-hostable, but doesn't diagnose root cause
- Solo developer; Python primary language

## Constraints

- **Tech stack**: Python backend + Python SDK primary; ClickHouse + PostgreSQL + S3 + Redis for storage
- **Solo developer**: Single maintainer — scope must stay tight; progressive building is essential
- **SaaS only**: No on-premise distribution
- **Correctness over speed**: False positive flags erode trust — threshold calibration is critical
- **View has no logic**: All business logic in backend services per AD-04

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| A4 approach (A3 first) | Best global pattern across all evaluation matrices; A3 is natural first milestone | ✓ Good — shipped cleanly as v1.0 |
| ClickHouse for spans | OLAP, append-only, proven at scale by competitors (Langfuse, LangSmith) | ✓ Good — no issues at dev scale |
| PostgreSQL for flags/diagnostics/auth | Low volume, mutable, relational; append-only pattern | ✓ Good — RLS works as designed |
| S3 for large payloads | Prevents row bloat in ClickHouse; lazy retrieval preferred | ✓ Good — lazy-load UX works well |
| Redis for ingestion queue | Decouples ingestion from embedding; standard worker pattern | ✓ Good — BRPOP FIFO ordering solid |
| Async flagging | Span ingestion must not be blocked by embedding computation (AD-01) | ✓ Good — ~37s E2E is acceptable |
| Diagnosticer as separate service | LLM calls are slow and on-demand; isolation allows independent scaling (AD-02) | ✓ Good — scaffold in v1 painless |
| REST for Presenter | REST for queries/actions; SSE deferred to v1.1 | ✓ Good — sufficient for v1 |
| Email/password auth first, Clerk later | Zero external dependency for early development; schema supports migration (AD-14) | ✓ Good — JWT works cleanly |
| Scaffold Diagnosticer in v1 | Wired but inactive — enables progressive building without rearchitecting later | ✓ Good — POST /diagnose proxy ready |
| flag_type as open string (not enum) | New analyzer categories must not require schema migrations (FLAG-03) | ✓ Good — validated during Phase 3 |
| ClickHouse ORDER BY (tenant_id, trace_id, time_begin) | One-way door — set before any data flows | ✓ Good — query performance confirmed |
| bcrypt directly instead of passlib | passlib 1.7.4 incompatible with Python 3.14 + current bcrypt | ✓ Good — works cleanly |
| Worker Dockerfile pre-bakes sentence-transformers model | Avoids 80MB runtime download on first span | ✓ Good — image startup fast |
| wrong_tool_args excluded from P/R calibration | Low-confidence by design; terse JSON produces unreliable cosine similarity | ✓ Good — calibration more meaningful |
| BRPOP with 5s retry backoff in worker | Race: Redis delivers span_id before ClickHouse batcher flush (5s interval) | ✓ Good — fixed silent "span not found" |

---
*Last updated: 2026-04-06 after v1.1 milestone start*

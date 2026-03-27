# Project Research Summary

**Project:** Xeter
**Domain:** AI agent observability and debugging SaaS platform
**Researched:** 2026-03-27
**Confidence:** HIGH (stack verified against PyPI; architecture validated against Langfuse, ClickHouse, and OTel official sources)

## Executive Summary

Xeter is an AI agent observability SaaS that fills a specific gap no existing tool addresses: automated, scored classification of *why* a tool call failed, not merely *that* it failed. The market (Langfuse, LangSmith, Arize Phoenix, HoneyHive) shows that observability infrastructure — span ingestion, trace display, multi-tenancy — is table stakes and well-understood. The differentiated wedge is the heuristic flag pipeline (wrong_tool, no_tool, excessive_tool, parsing_error) backed by cosine similarity between OTel span fields, and the future LLM-powered root-cause Diagnosticer. All competitors show trace data; none name the failure class automatically with a confidence score. That is Xeter's moat.

The recommended architecture is a five-service Python system: Python SDK emitting OTLP spans to an Analyser, which writes to ClickHouse (spans) and S3 (large payloads) synchronously and enqueues span IDs to Redis for async processing by an Embedding Worker that computes flags and writes to PostgreSQL. A Presenter service merges the two stores and serves the React/Vite dashboard. A Diagnosticer service is scaffolded in Milestone 1 but activated only in Milestone 2. This polyglot-persistence, ingest-first-analyze-async pattern is directly validated by Langfuse's own v3 infrastructure evolution. Every major architectural decision has industry precedent; there is no experimental architecture here.

The highest-severity risks are correctness and trust risks, not infrastructure risks. A hardcoded embedding threshold that produces noisy flags will erode user trust before the product can prove its value. A wrong ClickHouse ORDER BY will require a full table rebuild to fix. A missing tenant_id filter is a catastrophic cross-tenant data leak. All three must be addressed in the foundation and ingestion phases, not retrofitted. The solo developer scope warning is also critical: five services and four storage technologies demand strict phase discipline — one shippable vertical slice per phase, no parallel half-finished components.

---

## Key Findings

### Recommended Stack

The backend is Python 3.12 throughout. FastAPI 0.135 (async-first, Pydantic v2 native) is the API framework for Analyser, Presenter, and Diagnosticer. arq 0.27 (asyncio-native, Redis-backed) replaces Celery for the embedding worker queue — Celery is not asyncio-native and adds unjustified complexity for this pattern. The embedding model is BAAI/bge-base-en-v1.5 via sentence-transformers 5.3, chosen over all-MiniLM-L6-v2 (56% top-5 accuracy — too low for a trust-critical flagging product) and over OpenAI's API (network dependency, cost, blocks dev environments). Storage is ClickHouse (spans, clickhouse-connect 0.15), PostgreSQL (flags, diagnostics, auth — SQLAlchemy 2.0 + asyncpg 0.31 + Alembic 1.18), and S3/MinIO (large payloads, aioboto3 15.5). The frontend is React 19 + Vite 6 + TypeScript 5 + Tailwind 4 + shadcn/ui + TanStack Query v5 — a pure SPA with no SSR requirement, making Next.js wrong for this use case.

**Core technologies:**
- Python 3.12: runtime for all backend services and SDK — library compatibility sweet spot (sentence-transformers 5.x requires >=3.10; 3.13 JIT is experimental)
- FastAPI 0.135 + Pydantic 2.12: async API framework — native SSE, Rust-backed validation, de-facto standard for Python async APIs in 2026
- arq 0.27 + Redis 7: asyncio-native task queue for embedding workers — avoids Celery's multiprocessing overhead
- BAAI/bge-base-en-v1.5 via sentence-transformers 5.3: embedding model — 70%+ top-5 accuracy vs 56% for MiniLM; runs locally (no API dependency)
- ClickHouse 25.x + clickhouse-connect 0.15: OLAP span storage — append-only, columnar, fast analytical scans; official ClickHouse Inc. driver
- SQLAlchemy 2.0 + asyncpg 0.31 + Alembic 1.18: async PostgreSQL ORM/driver/migrations — first-class async, production standard for FastAPI
- aioboto3 15.5: async S3 client — avoids blocking the asyncio event loop on large payload reads
- React 19 + Vite 6 + Tailwind 4 + shadcn/ui + TanStack Query v5: SPA dashboard — no SSR needed, fastest iteration cycle for authenticated B2B tool

### Expected Features

**Must have (table stakes):**
- Python SDK emitting OTel OTLP spans — without this there is no product
- Span ingestion with API key auth and multi-tenancy (row-level tenant_id isolation)
- ClickHouse span storage + S3 lazy-load for large payloads
- Redis queue + async embedding worker (decouples ingestion from flag computation)
- Heuristic flag types: wrong_tool, no_tool, excessive_tool, parsing_error with cosine similarity scores — the core differentiator
- Span list view with flag indicators and filtering (by time, status, flag type, tenant)
- Span detail view with flag detail (which fields triggered, score, threshold) and lazy-loaded S3 payloads
- Dashboard login (email/password)
- Diagnosticer scaffolded but inactive (wired now, functional in Milestone 2)

**Should have (competitive, v1.x after validation):**
- Session/conversation grouping (capture session_id in v1 spans, render in v1.x)
- Trace tree visualization (capture parent_span_id in v1, render in v1.x)
- TypeScript SDK (Python SDK must be stable first per AD-18)
- Alerting / Slack notifications (deferred until users shift from debugging to monitoring)
- Flag threshold calibration UI (deferred until false positive rate is a reported pain point)

**Defer (v2+ / Milestone 2):**
- LLM-powered Diagnosticer active (root-cause attribution: model/architecture/prompt) — highest strategic value, depends on stable Milestone 1 flag data
- LLM-as-a-judge evaluation pipeline — requires dataset infrastructure; not the diagnosis differentiator
- LLM cost attribution — high maintenance, not Xeter's moat
- Prompt playground / management — Langfuse and LangSmith own this; do not compete
- Multi-model A-B experiment comparison — separate product surface

Notably, no competitor provides automated flag classification or per-flag confidence scores. The gap is real and confirmed across Langfuse, LangSmith, Arize Phoenix, and HoneyHive.

### Architecture Approach

The system uses a polyglot-persistence, ingest-first-analyze-async pattern validated directly by Langfuse's v3 architecture and ClickHouse/Dash0 production experience. Four architectural patterns govern the design: (1) Ingest-First, Analyze-Async — Analyser writes span to ClickHouse and S3 synchronously in the request path, pushes span_id to Redis, returns 200; embedding worker consumes asynchronously. (2) Multi-Store Application-Level Merge — Presenter parallelises ClickHouse and PostgreSQL queries via asyncio.gather, merges in application code; no cross-database JOINs. (3) S3 as Large-Payload Offload — prompt/response/raw_response never stored inline in ClickHouse; fetched lazily by Presenter on detail view only. (4) Isolated On-Demand Service — Diagnosticer is a separate process called only on explicit user request, isolating slow LLM calls from ingestion and flagging paths.

**Major components:**
1. Python SDK — wraps OTel, emits OTLP spans to Analyser; zero overhead on agent code; ships as pip package
2. Analyser (FastAPI) — accepts OTLP spans, writes to ClickHouse + S3 synchronously, enqueues span_id to Redis
3. Embedding Worker (arq) — consumes Redis queue, computes cosine similarities via sentence-transformers, writes flag rows to PostgreSQL
4. ClickHouse — immutable OLAP span store; ORDER BY (tenant_id, trace_id, time_begin); append-only
5. PostgreSQL — mutable relational store for flags, diagnostics, tenants, users, api_keys; Alembic migrations
6. S3 / MinIO — large text payload store; keys referenced in ClickHouse; fetched lazily
7. Redis — decouples ingestion from analysis; BRPOP queue; no durability requirement (span already in ClickHouse)
8. Presenter (FastAPI) — REST + SSE API; merges ClickHouse + PostgreSQL per request; lazy S3 fetch
9. Diagnosticer (FastAPI) — on-demand LLM analysis; scaffolded in Milestone 1, functional in Milestone 2
10. View (React SPA) — pure display layer; consumes Presenter REST + SSE; no business logic

Build order follows strict dependency tiers: Foundation (schemas, shared models, DB clients) → Ingestion path (SDK + Analyser) → Analysis path (Embedding Worker) → Read path (Presenter) → Presentation (View) → Diagnostic path (Diagnosticer, Milestone 2).

### Critical Pitfalls

1. **Embedding threshold hardcoded without domain calibration** — Optimal cosine similarity thresholds vary from 0.334 to 0.867 across domains; a hardcoded 0.7 will produce either all noise or silence on real agent spans. Prevention: make threshold a first-class config parameter from day one; log every similarity score including non-flagged spans to accumulate a calibration dataset; do not claim flagging reliability until calibrated against 200+ labelled spans.

2. **ClickHouse ORDER BY locked in wrong order** — ClickHouse primary keys are sparse ordered indexes, not point-lookup indexes. A wrong ORDER BY (e.g., span_id or time_begin alone) forces full table scans on every tenant/trace query, and cannot be changed without a full table rebuild. Prevention: establish ORDER BY as (tenant_id, trace_id, time_begin) in the first schema migration; verify with EXPLAIN before any data is loaded.

3. **High-frequency single-row ClickHouse inserts causing "Too Many Parts" failure** — One INSERT per span creates one data part; when inserts outpace background merges, ClickHouse rejects all writes above 300 parts/partition. Prevention: buffer in Redis queue and INSERT in batches of 1,000+ rows; alternatively enable ClickHouse async inserts server-side. The Redis queue exists specifically to enable this.

4. **Cross-tenant data leak via missing tenant_id filter** — A single query omitting WHERE tenant_id = $tenant_id exposes all tenants' data to any authenticated user. Prevention: build a data access layer (DAL) that is the only code writing SQL; inject tenant_id in the DAL, not at call sites; enable PostgreSQL RLS as defense-in-depth; write integration tests that authenticate as Tenant A and verify zero Tenant B data returned.

5. **OTel GenAI semantic conventions churn breaking the SDK** — GenAI conventions are experimental and had breaking changes in 1.37.0; convention updates without an adapter layer force a full SDK release cycle and break customer instrumentation silently. Prevention: define Xeter's own stable span schema independently; map OTel attribute names in a single adapter file; add xeter.schema.version to every emitted span.

---

## Implications for Roadmap

Based on the architecture's dependency tiers and the pitfall phase mapping, a six-phase structure is recommended, corresponding to the build order tiers:

### Phase 1: Foundation — Schemas, Shared Models, and Infrastructure
**Rationale:** All downstream phases depend on correct storage schemas and shared data contracts. The ClickHouse ORDER BY decision and threshold config pattern must be locked here; they cannot be changed cheaply later. The PostgreSQL RLS and DAL must be established before any data is stored.
**Delivers:** Running ClickHouse, PostgreSQL, Redis, MinIO (Docker Compose); all schema migrations applied; shared Pydantic models; DB client wrappers; DAL with tenant_id enforcement; PostgreSQL RLS configured; ClickHouse ORDER BY (tenant_id, trace_id, time_begin) verified.
**Addresses:** OTel span ingestion (schema), multi-tenancy, API key auth (schema), retention/persistence
**Avoids:** Wrong ClickHouse ORDER BY (Pitfall 2), cross-tenant data leak (Pitfall 7), nullable ClickHouse columns

### Phase 2: Ingestion Path — Python SDK and Analyser
**Rationale:** No downstream analysis or display is possible without spans flowing in. The SDK is the product's interface to the outside world and must have schema versioning from the start. The Analyser must batch writes (not single-row insert) and enqueue for async analysis — the ingestion pattern locks in here.
**Delivers:** Installable Python SDK (XeterTracer wrapping OTel, OTLP exporter, xeter.schema.version on every span); Analyser FastAPI service receiving OTLP spans, uploading payloads to S3, inserting batched spans to ClickHouse, pushing span_ids to Redis; API key validation.
**Uses:** opentelemetry-sdk 1.40, opentelemetry-exporter-otlp-proto-http 1.40, FastAPI 0.135, clickhouse-connect 0.15, aioboto3 15.5, arq/Redis for enqueue
**Avoids:** Blocking ingestion on embedding (Pitfall — async pattern), span loss on ClickHouse failure (Pitfall 4), "Too Many Parts" (Pitfall 3), OTel convention churn (Pitfall 6), unauthenticated OTLP endpoint (Security)

### Phase 3: Analysis Path — Embedding Worker and Flag Pipeline
**Rationale:** The core differentiator. Depends on ingested spans existing in ClickHouse. The threshold-as-config pattern, score logging, and worker idempotency must all be designed here — retrofitting them is the most trust-eroding mistake identified in research.
**Delivers:** arq Embedding Worker consuming Redis queue; sentence-transformers bge-base-en-v1.5 encoding; cosine similarity computation; flag classification (wrong_tool, no_tool, excessive_tool, parsing_error); confidence score and detail JSON persisted to PostgreSQL flags table; pending/analysed/flagged status tracking; worker idempotency verified.
**Uses:** arq 0.27, sentence-transformers 5.3, BAAI/bge-base-en-v1.5, SQLAlchemy 2.0 + asyncpg 0.31
**Avoids:** Hardcoded embedding threshold (Pitfall 1), cross-store inconsistency (Pitfall 5), worker acking before processing completes

### Phase 4: Read Path — Presenter API
**Rationale:** Depends on both Analyser (spans in ClickHouse) and Embedding Worker (flags in PostgreSQL). The application-level merge pattern and lazy S3 fetch are implemented here. Diagnosticer is scaffolded (wired but returning 501) so Milestone 2 requires no rearchitecting.
**Delivers:** Presenter FastAPI service; GET /spans (list with flag indicators, no S3 fetches); GET /spans/{id} (detail with parallel ClickHouse + PostgreSQL queries + lazy S3 fetch); POST /diagnose (proxied to Diagnosticer scaffold returning 501); Diagnosticer service scaffold; auth middleware; SSE emitter stub.
**Uses:** FastAPI 0.135, asyncpg 0.31, clickhouse-connect 0.15, aioboto3 15.5, httpx
**Avoids:** Eager S3 fetch on list view (Pitfall — performance), sequential rather than parallel store queries, cross-database JOINs (Architecture Anti-Pattern 4), running Diagnosticer in ingestion path (Anti-Pattern 5)

### Phase 5: Presentation — View Dashboard
**Rationale:** Depends on a running Presenter API. Built against the live backend. Pure display layer — no business logic in the frontend. The UI must surface flag detail (which fields, score, threshold) and pending/analysed/flagged status per PITFALLS.md UX guidance.
**Delivers:** React 19 + Vite 6 SPA; dashboard login (email/password, JWT); span list page with flag badges, filtering (time, status, flag type); span detail page with flag detail panel and lazy-loaded S3 payloads; pending/analysed/flagged status visible on every span; Diagnosticer "request diagnostic" button (calls /diagnose, shows placeholder).
**Uses:** React 19, Vite 6, TypeScript 5, Tailwind 4, shadcn/ui, TanStack Query v5, python-jose + passlib on backend for auth
**Avoids:** Loading all S3 payload content on list view, displaying flags without explaining which field triggered them, confusing "clean span" with "analysis not yet run"

### Phase 6: Validation and Threshold Calibration
**Rationale:** After v1 is shippable (Phases 1–5), the embedding threshold must be calibrated against real labelled spans before the product is trusted. This phase also performs the load tests and integration tests identified in PITFALLS.md's "Looks Done But Isn't" checklist.
**Delivers:** Calibration harness run against labelled spans (200+); threshold config tuned per calibration output; load test confirming no "Too Many Parts" at 500 spans/second sustained; cross-tenant isolation integration test passing; ingestion latency confirmed under 100ms with worker running; score logging confirmed active; xeter.schema.version verified on all emitted spans.
**Avoids:** Shipping uncalibrated thresholds that erode user trust (Pitfall 1 — the most trust-critical risk), missing any item on the PITFALLS.md checklist

### Phase Ordering Rationale

- Phases 1–3 follow strict architectural dependency order: schemas before ingestion, ingestion before analysis. No phase can be started until the prior phase is complete.
- Phase 4 (Presenter) intentionally scaffolds the Diagnosticer inactive — wired now so Milestone 2 activates it without rearchitecting. This is confirmed by FEATURES.md (Diagnosticer is P1 scaffold, P2 activation).
- Phase 5 (View) is last in the backend build order because it is a pure consumer of the Presenter API; it cannot be tested meaningfully until the read path exists.
- Phase 6 is explicitly separated from Phase 5 because threshold calibration requires real span data flowing through the live system — it cannot be done during construction.
- The Diagnosticer LLM activation (Milestone 2) is not in these phases. It follows after Phase 6 validation proves the heuristic flag layer is trusted.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Embedding Worker):** Threshold calibration methodology and initial default value need domain-specific research against real agent tool-call patterns. The PITFALLS.md documents the risk but the initial threshold value is unknown without empirical data from real agent spans.
- **Phase 6 (Calibration):** Labelled dataset sourcing and precision/recall evaluation methodology are not fully specified in research. This phase may need a dedicated research spike before execution.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** ClickHouse schema patterns, PostgreSQL RLS, Docker Compose infrastructure — all well-documented with direct official source validation.
- **Phase 2 (Ingestion):** OTLP ingestion, FastAPI + S3 + Redis patterns — extensively documented; Langfuse v3 is an exact reference implementation.
- **Phase 4 (Presenter):** Application-level merge, asyncio.gather parallelisation, lazy S3 fetch — all validated patterns with code examples in ARCHITECTURE.md.
- **Phase 5 (View):** React + Vite + shadcn/ui SPA — standard 2026 SaaS dashboard stack; official installation docs are sufficient.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI March 2026; official docs consulted for all major choices; alternatives explicitly benchmarked (arq vs Celery, bge-base vs MiniLM) |
| Features | MEDIUM-HIGH | Competitor feature tables verified against official docs (Langfuse, Arize Phoenix); differentiator claims cross-referenced; alerting status verified via GitHub discussions |
| Architecture | HIGH | Every major pattern validated against production post-mortems (Langfuse v3 evolution, Dash0, ClickHouse official blog); no experimental architectural choices |
| Pitfalls | MEDIUM-HIGH | Critical infrastructure pitfalls (ClickHouse ORDER BY, Too Many Parts) verified via official ClickHouse docs and practitioner post-mortems; embedding threshold pitfalls MEDIUM — domain-specific calibration data scarce |

**Overall confidence:** HIGH

### Gaps to Address

- **Embedding threshold initial default:** No published benchmarks exist for cosine similarity thresholds specific to agent tool-call spans (prompt-to-tool_name, prompt-to-tool_description comparisons). The initial value must be treated as a hypothesis and calibrated empirically in Phase 6. Log all scores from day one to enable this.
- **Batch size tuning for ClickHouse inserts:** ARCHITECTURE.md documents that 1,000–100,000 rows per INSERT is the target range, but optimal batch size for Xeter's span schema and ClickHouse 25.x configuration requires empirical testing during Phase 1/2 development.
- **S3 presigned URL vs direct Presenter proxy for payload delivery:** PITFALLS.md recommends 15-minute presigned URL expiry; whether the Presenter should proxy S3 content directly (simpler, no URL leakage) vs generate presigned URLs (cheaper at scale) is an implementation decision not resolved in research. Default to Presenter proxy in v1; revisit at scale.
- **Diagnosticer LLM prompt structure:** The result schema for diagnostics.result (root_cause, evidence, recommendation) is identified in PITFALLS.md UX section, but the full prompt template for the Diagnosticer is not designed. This is intentionally deferred to Milestone 2 but should be stubbed in the Diagnosticer scaffold during Phase 4.

---

## Sources

### Primary (HIGH confidence)
- [PyPI verified packages — March 2026](https://pypi.org) — all stack version numbers
- [OpenTelemetry Python official docs](https://opentelemetry.io/docs/languages/python/) — SDK and exporter patterns
- [OTLP Specification 1.10.0](https://opentelemetry.io/docs/specs/otlp/) — transport protocol, ports
- [OTel GenAI Semantic Conventions (experimental)](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — convention status, breaking change history
- [shadcn/ui Vite installation docs](https://ui.shadcn.com/docs/installation/vite) — frontend stack
- [shadcn/ui Tailwind v4 docs](https://ui.shadcn.com/docs/tailwind-v4) — frontend stack
- [ClickHouse: Too Many Parts (official docs)](https://clickhouse.com/docs/tips-and-tricks/too-many-parts) — Pitfall 3
- [ClickHouse: Common Getting Started Mistakes (official blog)](https://clickhouse.com/blog/common-getting-started-issues-with-clickhouse) — Pitfall 2
- [Langfuse Architecture Handbook](https://langfuse.com/handbook/product-engineering/architecture) — polyglot persistence validation
- [Langfuse V3 Infrastructure Evolution](https://langfuse.com/blog/2024-12-langfuse-v3-infrastructure-evolution) — Redis queue, async worker, S3 pattern validation
- [Langfuse and ClickHouse data stack](https://clickhouse.com/blog/langfuse-and-clickhouse-a-new-data-stack-for-modern-llm-applications) — ClickHouse migration rationale
- [sentence-transformers semantic similarity docs (sbert.net)](https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html) — similarity computation
- [Arize Phoenix GitHub](https://github.com/Arize-ai/phoenix) — competitor feature comparison
- [Langfuse official docs](https://langfuse.com/docs/observability/overview) — competitor feature comparison

### Secondary (MEDIUM confidence)
- [BentoML: Best open-source embedding models 2026](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models) — model selection rationale
- [supermemory: embedding model benchmarks](https://supermemory.ai/blog/best-open-source-embedding-models-benchmarked-and-ranked/) — MiniLM vs bge accuracy data
- [Leapcell: Celery vs ARQ](https://leapcell.io/blog/celery-versus-arq-choosing-the-right-task-queue-for-python-applications) — queue selection
- [Leapcell: FastAPI + SQLAlchemy 2.0 + asyncpg](https://leapcell.io/blog/building-high-performance-async-apis-with-fastapi-sqlalchemy-2-0-and-asyncpg) — backend patterns
- [ClickHouse/PostgreSQL for Agentic AI Scale](https://thenewstack.io/postgres-clickhouse-the-oss-stack-to-handle-agentic-ai-scale/) — dual-store pattern
- [Six Months with ClickHouse at CloudQuery](https://www.cloudquery.io/blog/six-months-with-clickhouse-at-cloudquery) — practitioner ClickHouse experience
- [OTel AI Agent Observability Blog 2025](https://opentelemetry.io/blog/2025/ai-agent-observability/) — GenAI convention status
- [AITUDE: Top 5 Sentence Transformer Mistakes](https://www.aitude.com/top-5-sentence-transformer-embedding-mistakes-and-their-easy-fixes-for-better-nlp-results/) — embedding pitfalls
- [LangSmith agent debugging blog](https://blog.langchain.com/debugging-deep-agents-with-langsmith/) — competitor features

### Tertiary (LOW confidence)
- [Maxim AI top 5 platforms 2026](https://www.getmaxim.ai/articles/top-5-ai-agent-observability-platforms-in-2026/) — vendor aggregator, cross-referenced only
- [Medium: Multi-Tenant RLS failures](https://medium.com/@instatunnel/multi-tenant-leakage-when-row-level-security-fails-in-saas-da25f40c788c) — single source, security pattern only

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*

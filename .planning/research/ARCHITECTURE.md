# Architecture Research

**Domain:** AI agent observability and debugging platform
**Researched:** 2026-03-27
**Confidence:** HIGH (project architecture fully specified in arc42; research validates and expands patterns)

---

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INGESTION LAYER                              │
│  ┌──────────────┐   OTLP/HTTP or gRPC   ┌───────────────────────┐  │
│  │  Python SDK  │ ─────────────────────► │  Analyser (FastAPI)   │  │
│  │  (OTel wrap) │                        │  - auth check         │  │
│  └──────────────┘                        │  - protobuf decode    │  │
│                                          │  - ClickHouse INSERT  │  │
│                                          │  - Redis LPUSH        │  │
│                                          └───────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                         Redis queue (span_id refs)
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ANALYSIS LAYER                               │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Embedding Worker (Python process, polling Redis queue)        │  │
│  │  - BRPOP span_id from queue                                   │  │
│  │  - fetch span fields from ClickHouse                          │  │
│  │  - embed: prompt, tool_name, tool_description, response       │  │
│  │  - embed prompt vs each tool in available_tools (from S3)     │  │
│  │  - embed prompt vs tool_arguments values (inline JSON)        │  │
│  │  - cosine similarity comparisons                              │  │
│  │  - classify: wrong_tool / wrong_tool_args / no_tool /         │  │
│  │              excessive_tool / parsing_error                   │  │
│  │  - INSERT flag rows into PostgreSQL                           │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                    flags written to PostgreSQL
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         STORAGE LAYER                                │
│  ┌──────────────┐   ┌──────────────────────┐   ┌────────────────┐  │
│  │  ClickHouse  │   │     PostgreSQL         │   │    S3 / MinIO  │  │
│  │  spans table │   │  flags, diagnostics    │   │  prompt,       │  │
│  │  (immutable) │   │  tenants, users,       │   │  response,     │  │
│  │  OLAP, fast  │   │  api_keys (mutable)    │   │  raw_response  │  │
│  │  scan        │   │                        │   │  (large text)  │  │
│  └──────────────┘   └──────────────────────┘   └────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                    Presenter queries both stores
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         API LAYER                                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Presenter (FastAPI)                                           │  │
│  │  - REST: span list, span detail, trace tree                   │  │
│  │  - merges ClickHouse spans + PostgreSQL flags/diagnostics     │  │
│  │  - lazy-fetches S3 payload refs on detail view                │  │
│  │  - SSE: flag-update events, diagnostic-completion events      │  │
│  │  - routes /diagnose → Diagnosticer                            │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                         ┌───────┴──────────┐
                         │                  │
                         ▼                  ▼
┌───────────────────┐         ┌─────────────────────────────────────┐
│  View (SvelteKit  │         │  Diagnosticer (separate service)     │
│  or React SPA)    │         │  - called on user request only       │
│  no business      │◄────────│  - reads full trace from storage     │
│  logic            │         │  - calls LLM (configurable backend)  │
└───────────────────┘         │  - INSERT INTO diagnostics           │
                              └─────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Key Constraint |
|-----------|----------------|----------------|
| SDK | Wrap OTel, emit OTLP spans to Analyser | Zero overhead on agent code; Python primary |
| Analyser | Accept spans, store immediately, enqueue for async flagging | Must not block on embedding; ingestion latency is SLA |
| Embedding Worker | Consume queue, compute similarities, write flag rows | Async from ingestion; failure leaves span unflagged (not lost) |
| ClickHouse | Store all spans, immutable, OLAP scan for list/filter queries | Append-only; no mutations; `tenant_id` partition key |
| PostgreSQL | Store flags, diagnostics, auth, tenants — all mutable relational data | Append-only rows for flags/diagnostics; FK to ClickHouse span_id |
| S3 / MinIO | Store large text payloads (prompt, response, raw_response, available_tools) | Referenced by key in ClickHouse; fetched lazily by Presenter; tool_arguments stored inline in ClickHouse (small) |
| Redis | Decouple ingestion from embedding worker via queue; optional: event cache | BRPOP queue; no durability requirement (span already in ClickHouse) |
| Presenter | Backend API; merge ClickHouse + PostgreSQL results per request | REST + SSE; parallelises two store queries; lazy S3 fetch |
| Diagnosticer | On-demand LLM diagnostic service; called by Presenter | Separate process; slow calls isolated; configurable LLM backend |
| View | Frontend dashboard | No logic; pure display; consumes Presenter REST + SSE |

---

## Recommended Project Structure

```
xeter/
├── sdk/                        # Python SDK (shipped as package)
│   ├── xeter/
│   │   ├── __init__.py
│   │   ├── tracer.py           # OTel span wrapping
│   │   ├── exporter.py         # OTLP exporter config to Analyser
│   │   └── models.py           # Span field definitions (shared with Analyser)
│   └── pyproject.toml
│
├── services/
│   ├── analyser/               # Span ingestion + Redis enqueue
│   │   ├── main.py             # FastAPI app, OTLP /v1/traces endpoint
│   │   ├── otlp.py             # Protobuf decode, field extraction
│   │   ├── storage/
│   │   │   ├── clickhouse.py   # Span INSERT
│   │   │   └── s3.py           # Payload upload, key generation
│   │   └── queue.py            # Redis LPUSH
│   │
│   ├── worker/                 # Embedding + flag computation
│   │   ├── main.py             # Poll Redis, process spans
│   │   ├── embedder.py         # sentence-transformers encode()
│   │   ├── similarity.py       # Cosine similarity, threshold logic
│   │   ├── classifier.py       # wrong_tool / no_tool / etc.
│   │   └── storage/
│   │       └── postgres.py     # INSERT INTO flags
│   │
│   ├── presenter/              # REST API + SSE
│   │   ├── main.py             # FastAPI app
│   │   ├── routers/
│   │   │   ├── spans.py        # GET /spans, GET /spans/{id}
│   │   │   ├── traces.py       # GET /traces/{trace_id}
│   │   │   └── diagnostics.py  # POST /diagnose, GET /diagnostics/{id}
│   │   ├── merging.py          # Combine ClickHouse + PostgreSQL results
│   │   ├── storage/
│   │   │   ├── clickhouse.py   # Span queries
│   │   │   ├── postgres.py     # Flags/diagnostics queries
│   │   │   └── s3.py           # Lazy payload fetch
│   │   └── sse.py              # Server-Sent Events emitter
│   │
│   └── diagnosticer/           # On-demand LLM analysis
│       ├── main.py             # FastAPI app (or simple HTTP service)
│       ├── llm.py              # Configurable LLM client (OpenAI-compatible)
│       ├── prompt_builder.py   # Build trace context prompt
│       └── storage/
│           └── postgres.py     # INSERT INTO diagnostics
│
├── shared/                     # Shared Python code
│   ├── models.py               # Pydantic models for span fields, flags, etc.
│   ├── db/
│   │   ├── clickhouse.py       # ClickHouse client setup
│   │   ├── postgres.py         # asyncpg / SQLAlchemy setup
│   │   ├── redis.py            # Redis client setup
│   │   └── s3.py               # boto3 / aiobotocore setup
│   └── auth.py                 # API key validation, JWT helpers
│
├── view/                       # Frontend (SvelteKit or React)
│   ├── src/
│   │   ├── routes/             # Pages: span list, span detail, trace view
│   │   ├── components/         # SpanRow, FlagBadge, DiagnosticPanel
│   │   └── api.ts              # Typed Presenter API client
│   └── package.json
│
├── migrations/                 # PostgreSQL schema (alembic or raw SQL)
│   └── 001_initial.sql         # tenants, users, api_keys, flags, diagnostics
│
├── deploy/
│   └── docker-compose.yml      # ClickHouse, PostgreSQL, Redis, MinIO, all services
│
└── tests/
    ├── sdk/                    # SDK unit tests
    ├── analyser/               # Ingestion endpoint tests
    ├── worker/                 # Flagging logic unit tests
    └── e2e/                    # Span in → flag out integration tests
```

### Structure Rationale

- **services/ split by process boundary:** Each service maps to one deployable unit. Worker and Analyser are separate processes even if initially on the same host — this is the right separation for independent scaling later.
- **shared/ for cross-service models:** Pydantic span models are authoritative. All services import from `shared.models` — never duplicate field definitions.
- **storage/ per service:** Each service gets its own storage wrappers. Do not share DB connection objects across services.
- **migrations/ at root:** Schema lives outside services. Avoids the question of "which service owns the schema?"

---

## Architectural Patterns

### Pattern 1: Ingest-First, Analyze-Async

**What:** The Analyser writes the span to ClickHouse synchronously in the HTTP request path, then pushes the span_id to a Redis list. A separate worker process (BRPOP loop) handles all embedding computation and flag writes asynchronously after the HTTP response has returned.

**When to use:** Any time downstream computation (embedding, LLM calls, scoring) is expensive relative to storage write latency. This is the standard pattern for high-throughput observability pipelines — confirmed by Langfuse's v3 architecture (Redis + async worker) and the OpenTelemetry Collector's batch processing model.

**Trade-offs:**
- Pro: Ingestion latency is bounded by ClickHouse INSERT only (~low ms)
- Pro: Embedding worker failure never loses a span
- Con: Flag appears with a small lag after span write (~seconds under normal load)
- Con: If Redis goes down between span write and flag computation, span exists but may never be flagged (acceptable — span is not lost)

**Example:**
```python
# analyser/main.py — synchronous path
@app.post("/v1/traces")
async def ingest_traces(request: Request):
    body = await request.body()
    spans = decode_otlp_protobuf(body)           # parse protobuf
    await clickhouse.insert_spans(spans)          # sync: store immediately
    await s3.upload_payloads(spans)               # sync: upload large fields
    for span in spans:
        await redis.lpush("flagging_queue", span.span_id)  # enqueue for async
    return Response(status_code=200)

# worker/main.py — async analysis loop
async def run():
    while True:
        span_id = await redis.brpop("flagging_queue", timeout=5)
        if span_id:
            span = await clickhouse.fetch_span(span_id)
            flags = await compute_flags(span)
            if flags:
                await postgres.insert_flags(flags)
```

### Pattern 2: Multi-Store Application-Level Merge

**What:** The Presenter issues two parallel queries — one to ClickHouse for span data, one to PostgreSQL for flags and diagnostics — and merges the results in application code before sending the response to View.

**When to use:** When the spans store (ClickHouse) and the relational store (PostgreSQL) have different access patterns and you want to avoid coupling them with cross-database joins or CDC replication. This is explicitly validated by Langfuse, Dash0, and the ClickHouse/PostgreSQL integration blog ("PostgreSQL as transactional source of truth; ClickHouse for analytical queries").

**Trade-offs:**
- Pro: Each store is optimised for its access pattern
- Pro: No foreign-key coupling across DB engines
- Con: Two round-trips per span detail view (mitigated by async parallel queries)
- Con: Presenter must handle the case where flags/diagnostics arrive before span is queryable (rare but possible)

**Example:**
```python
# presenter/merging.py
async def get_span_detail(span_id: str, tenant_id: str):
    span_task = clickhouse.fetch_span(span_id, tenant_id)
    flags_task = postgres.fetch_flags(span_id, tenant_id)
    diagnostics_task = postgres.fetch_diagnostics(span_id, tenant_id)

    span, flags, diagnostics = await asyncio.gather(
        span_task, flags_task, diagnostics_task
    )

    # Lazy S3 fetch — only on detail view, never on list view
    if span.prompt_ref:
        span.prompt = await s3.fetch(span.prompt_ref)

    return merge(span, flags, diagnostics)
```

### Pattern 3: Isolated On-Demand Service for Expensive Operations

**What:** The Diagnosticer runs as a separate process. It is not invoked on every span. The Presenter calls it only when the user explicitly requests a diagnostic. It calls an external or local LLM, writes one row to PostgreSQL, and returns.

**When to use:** When an operation (LLM call) is too slow (~1–30 seconds) to run in the ingestion path or even the background worker, and is only needed when a human explicitly asks for it. This pattern appears in Langfuse (evaluation workers are separate), Braintrust (data plane isolation), and LangWatch (async processing that doesn't block requests).

**Trade-offs:**
- Pro: Slow LLM calls don't affect ingestion or flag computation
- Pro: Diagnosticer can be scaled independently or disabled entirely
- Pro: Configurable LLM backend (external API or local model) is isolated to one service
- Con: Adds a service boundary; requires HTTP call from Presenter to Diagnosticer

### Pattern 4: S3 as Large-Payload Offload

**What:** Large text fields (prompt, response, raw_response, available_tools) are uploaded to S3 at ingestion time. ClickHouse stores only the S3 object key (`prompt_ref`, `response_ref`, `raw_response_ref`, `available_tools_ref`). `tool_arguments` is small enough to store inline as JSON in ClickHouse. The Presenter fetches S3 content lazily — only when a user opens a span detail view, never during list queries.

**When to use:** Always in LLM observability platforms. Prompt and response fields regularly exceed 10KB–100KB. Storing them inline in ClickHouse causes row bloat, degrades scan performance, and inflates storage costs. This pattern is confirmed by Langfuse v3 ("raw ingestion events stored in S3") and the ClickHouse tiered storage playbook.

**Trade-offs:**
- Pro: ClickHouse rows stay small; analytical queries remain fast
- Pro: S3 is cheap; large payloads don't inflate OLAP storage costs
- Con: Detail view latency includes an S3 GET call (~20–100ms)
- Con: S3 objects must be co-deleted when spans are pruned

---

## Data Flow

### Flow 1: Span Ingestion and Flagging

```
Agent code (instrumented with SDK)
    │
    │  OTLP/HTTP POST /v1/traces (protobuf encoded)
    ▼
Analyser
    ├── [sync] decode protobuf → extract span fields
    ├── [sync] upload large fields to S3 → store ref keys
    ├── [sync] INSERT span row into ClickHouse (with _ref keys, no raw text)
    │         → HTTP 200 returned to SDK here
    │
    └── [async] LPUSH span_id to Redis queue
                    │
                    ▼ (BRPOP, worker process)
              Embedding Worker
                    ├── fetch span from ClickHouse
                    ├── fetch prompt from S3 (needed for embedding)
                    ├── fetch available_tools from S3 (via available_tools_ref)
                    ├── sentence-transformers encode():
                    │     embed(prompt) → p_vec
                    │     embed(tool_name) → tn_vec
                    │     embed(tool_description) → td_vec
                    │     embed(response) → r_vec
                    │     embed(model_name + prompt) → mp_vec
                    │     embed(each tool in available_tools) → at_vecs[]
                    │     embed(each tool_arguments value) → ta_vecs[]
                    ├── cosine_similarity(p_vec, tn_vec) → score_1
                    ├── cosine_similarity(p_vec, td_vec) → score_2
                    ├── cosine_similarity(p_vec, r_vec)  → score_3
                    ├── rank at_vecs[] by similarity to p_vec → ranked_tools
                    ├── cosine_similarity(p_vec, each ta_vec) → arg_scores[]
                    ├── classify based on scores + thresholds
                    │     wrong_tool:      called tool not top-ranked in ranked_tools (A1)
                    │                      or score_1 < threshold_A (coarse signal)
                    │     wrong_tool_args: min(arg_scores) < threshold_B (low-confidence, A7)
                    │     no_tool:         tool_name is null + p_vec suggests tool expected
                    │     excessive_tool:  count of tool spans in trace > expected
                    │     parsing_error:   mp_vec pattern match
                    └── INSERT flag rows into PostgreSQL (one row per detected flag)
```

### Flow 2: Span List View

```
View → GET /spans?tenant_id=&limit=&offset=&flagged=true
    ▼
Presenter
    ├── ClickHouse: SELECT span_id, trace_id, agent_name, time_begin, time_end, tool_name
    │              WHERE tenant_id = ? ORDER BY time_begin DESC LIMIT ? OFFSET ?
    │
    └── PostgreSQL: SELECT span_id, flag_type, score
                   WHERE tenant_id = ? AND span_id IN (list from ClickHouse result)

Merge: attach flag indicators to span rows
Return: paginated span list with flag badges (no S3 fetches)
```

### Flow 3: Span Detail View (with Lazy S3 Fetch)

```
View → GET /spans/{span_id}
    ▼
Presenter
    ├── [parallel] ClickHouse: SELECT * FROM spans WHERE span_id = ? AND tenant_id = ?
    ├── [parallel] PostgreSQL: SELECT * FROM flags WHERE span_id = ? AND tenant_id = ?
    └── [parallel] PostgreSQL: SELECT * FROM diagnostics WHERE span_id = ? AND tenant_id = ?

    ├── [then] S3: GET prompt at span.prompt_ref
    ├── [then] S3: GET response at span.response_ref
    └── [then] S3: GET raw_response at span.raw_response_ref

Merge: span + flags + diagnostics + payload text
Return: full span detail
```

### Flow 4: User-Triggered Diagnostics

```
View → POST /diagnose { span_id, tenant_id }
    ▼
Presenter
    ├── ClickHouse: fetch all spans for trace_id (tree context)
    ├── PostgreSQL: fetch all flags for trace_id
    │
    └── HTTP POST → Diagnosticer { trace_spans, flags }
                        ▼
                  Diagnosticer
                        ├── build LLM prompt: trace context + flags + instructions
                        ├── HTTP POST → LLM Backend (OpenAI-compatible)
                        │             (configurable: external API or local model)
                        ├── receive LLM response
                        └── PostgreSQL: INSERT INTO diagnostics (span_id, result, llm_backend)

Presenter → return diagnostic_id to View
View → SSE subscription receives diagnostic-completion event
View → re-fetch span detail to display new diagnostic
```

---

## Build Order (Component Dependencies)

The architecture has clear dependency tiers. Build in this order:

**Tier 1 — Foundation (no dependencies)**
- PostgreSQL schema migrations (`tenants`, `users`, `api_keys`, `flags`, `diagnostics`)
- ClickHouse schema (`spans` table)
- S3 bucket setup (MinIO for local dev)
- Redis setup
- Shared models and DB client wrappers

**Tier 2 — Ingestion path (depends on Tier 1)**
- SDK: OTel wrapping, OTLP exporter config
- Analyser: OTLP endpoint, protobuf decode, ClickHouse INSERT, S3 upload, Redis enqueue
- These two components can be built and tested together end-to-end (SDK → Analyser)

**Tier 3 — Analysis path (depends on Tier 2: spans must exist to flag)**
- Embedding Worker: Redis consumer, sentence-transformers, cosine similarity, flag classifier, PostgreSQL INSERT
- Unit-testable independently with mock span data; integration test requires Tier 2

**Tier 4 — Read path (depends on Tiers 1–3: data must exist to read)**
- Presenter: span list, span detail, trace tree endpoints; merge logic; lazy S3 fetch; auth middleware
- These routes can be built incrementally (span list before detail before diagnostics)

**Tier 5 — Presentation (depends on Tier 4)**
- View: dashboard, span list page, span detail page, flag indicators
- Consumes Presenter REST API; built against a running backend

**Tier 6 — Diagnostic path (depends on Tiers 4–5: scaffolded in Milestone 1, functional in Milestone 2)**
- Diagnosticer: scaffolded in v1 (wired but returns placeholder); LLM integration deferred
- SSE emitter in Presenter for flag-update and diagnostic-completion events

---

## Scaling Considerations

| Concern | At 100 spans/day | At 100K spans/day | At 10M spans/day |
|---------|-----------------|-------------------|-----------------|
| Ingestion throughput | Single Analyser process sufficient | Add async insert batching in ClickHouse; tune Redis queue | Multiple Analyser replicas; consider OTel Collector as front-door buffer |
| Embedding worker | Single worker; no batching needed | Batch embeddings per `model.encode(batch)` call; tune batch_size | Multiple worker replicas consuming same Redis queue |
| ClickHouse storage | Default MergeTree sufficient | Enable ClickHouse async inserts; tune `async_insert_busy_timeout_ms` | ClickHouse Cloud or sharded self-hosted; tiered storage (hot SSD → S3) |
| PostgreSQL (flags) | No concern | No concern (flags are sparse vs spans) | Partition `flags` table by `created_at`; archive old rows |
| S3 cost | Negligible | Implement retention policy | Lifecycle rules to Glacier for old traces |
| Presenter | Single FastAPI instance | Enable async parallel store queries (already pattern) | Add read replicas for ClickHouse; cache hot spans in Redis |

### First Bottleneck

The embedding worker is the first component to saturate. `sentence-transformers` CPU inference at ~50ms per span limits a single worker to ~1,200 spans/minute. Mitigation: batch multiple spans from the Redis queue into one `model.encode()` call. Effective batch_size of 32 reduces per-span time to ~5ms on CPU, ~0.5ms on GPU.

### Second Bottleneck

ClickHouse INSERT rate under single-row inserts. Mitigation: Analyser should batch spans within a request (multiple spans per OTLP export call) and use ClickHouse async inserts if single-span inserts become a concern. Langfuse found this to be the primary ClickHouse scaling concern and introduced explicit batching before flushing.

---

## Anti-Patterns

### Anti-Pattern 1: Blocking Ingestion on Embedding

**What people do:** Compute embeddings and write flags synchronously inside the OTLP endpoint handler before returning HTTP 200 to the SDK.

**Why it's wrong:** sentence-transformers inference takes 50–500ms depending on model and hardware. At 100 spans/second, this creates a queue of blocked HTTP connections. The SDK's agent code waits, adding latency to the agent being observed. If the embedding model loads slowly (cold start), the first request times out.

**Do this instead:** Write span to ClickHouse, push span_id to Redis, return 200. Worker picks it up independently.

### Anti-Pattern 2: Storing Large Payloads in ClickHouse Rows

**What people do:** Store `prompt`, `response`, and `raw_response` as ClickHouse String columns directly in the spans table.

**Why it's wrong:** A prompt to GPT-4 may be 8KB; a long conversation context may be 50KB+. ClickHouse scans full column data for list queries. Storing large strings inline degrades scan performance, inflates compressed block sizes, and makes ClickHouse storage expensive. Langfuse v3 migration explicitly moved large payloads to S3 for this reason.

**Do this instead:** Upload payloads to S3 at ingestion time; store only the object key in ClickHouse. Fetch S3 content lazily in the Presenter on detail view only.

### Anti-Pattern 3: Eager S3 Fetch on List View

**What people do:** Fetch S3 payload content for every span returned in a list query (e.g., page of 50 spans).

**Why it's wrong:** Each S3 GET adds ~20–100ms network latency. For a 50-span page, that is 1–5 seconds of serial S3 requests, or ~200–500ms parallelised. The list view only needs span metadata and flag indicators — it doesn't need prompt/response text.

**Do this instead:** Fetch S3 content only when the user opens a single span's detail view. Referenced in the arc42 as "lazy strongly preferred" for this reason (R-06).

### Anti-Pattern 4: Cross-Database JOINs via Foreign Data Wrappers

**What people do:** Install `pg_clickhouse` or similar FDW to JOIN PostgreSQL flags rows with ClickHouse spans rows in a single SQL query.

**Why it's wrong:** FDW-based cross-engine joins stream data from ClickHouse into PostgreSQL's memory for the duration of the query. This removes ClickHouse's columnar scan advantage, creates unpredictable memory pressure on PostgreSQL, and couples the two databases operationally.

**Do this instead:** Run two parallel queries from the Presenter and merge in application code. The latency cost is one extra round-trip (~1–5ms); the operational simplicity gain is significant.

### Anti-Pattern 5: Running Diagnosticer in the Ingestion Path

**What people do:** Auto-trigger LLM diagnostic analysis for every flagged span immediately after the flag is written.

**Why it's wrong:** LLM API calls take 2–30 seconds. Even asynchronously, running one per flagged span creates a secondary queue that grows unboundedly under high ingestion rates. LLM API costs at scale are significant.

**Do this instead:** Diagnosticer is on-demand only, triggered by explicit user action. Flags (heuristic) are cheap and always run. Diagnostics (LLM) are expensive and optional.

---

## Integration Points

### External Services

| Service | Integration Pattern | Protocol | Notes |
|---------|---------------------|----------|-------|
| LLM Backend | HTTP POST, OpenAI-compatible `/v1/chat/completions` | REST/HTTPS | Configurable per tenant; supports external API (OpenAI, Anthropic) or local model (Ollama, vLLM) |
| S3 / MinIO | PUT on ingestion, GET on detail view | AWS SDK (boto3 / aiobotocore) | MinIO in local Docker Compose; real S3 in production |
| ClickHouse | INSERT on ingestion, SELECT on read | `clickhouse-driver` or `clickhouse-connect` Python client | Use connection pooling; async client preferred in FastAPI |
| PostgreSQL | INSERT flags/diagnostics, SELECT for reads, auth queries | `asyncpg` (FastAPI async) or `psycopg3` | Use asyncpg for non-blocking queries in Presenter |
| Redis | LPUSH on ingestion, BRPOP in worker | `redis-py` (async) | Simple list queue; no BullMQ equivalent needed in Python at this scale |

### Internal Boundaries

| Boundary | Communication | Direction | Notes |
|----------|---------------|-----------|-------|
| SDK → Analyser | OTLP/HTTP protobuf POST to `/v1/traces` | Outbound from SDK | Port 4318 (standard OTLP HTTP). Consider gRPC for higher throughput later |
| Analyser → Redis | LPUSH span_id | Write | Fire-and-forget after span is stored |
| Worker → Redis | BRPOP (blocking read) | Read | Worker blocks until work arrives; single queue, multiple workers possible |
| Worker → PostgreSQL | INSERT flag rows | Write | After embedding computation succeeds |
| Worker → ClickHouse | SELECT span fields | Read | Worker re-reads span to get fields for embedding (avoids passing large data through Redis) |
| Worker → S3 | GET prompt payload | Read | Worker needs prompt text to embed it |
| Presenter → ClickHouse | SELECT spans | Read | List and detail queries |
| Presenter → PostgreSQL | SELECT flags, diagnostics; auth validation | Read | Parallel with ClickHouse query |
| Presenter → S3 | GET payload content | Read | Lazy; only on detail view |
| Presenter → Diagnosticer | HTTP POST with trace context | Outbound | Synchronous from Presenter's perspective; Diagnosticer may respond async via SSE |
| Diagnosticer → PostgreSQL | INSERT diagnostic row | Write | After LLM response received |

---

## Architecture Validation Against Confirmed Decisions

The Xeter arc42 architecture decisions are well-aligned with industry-validated patterns:

| Decision | Industry Validation | Confidence |
|----------|---------------------|------------|
| ClickHouse for spans | Langfuse, LangSmith, Dash0, ClickStack all use ClickHouse for trace/span storage. Langfuse migrated from PostgreSQL to ClickHouse specifically because PostgreSQL couldn't handle high-throughput ingestion + analytical reads. | HIGH |
| Redis queue (not Kafka) | Langfuse explicitly chose Redis over Kafka: "easily self-hostable and can scale to meet our requirements." Kafka adds operational complexity not justified at this scale. | HIGH |
| S3 for large payloads | Langfuse v3 stores raw ingestion events in S3. Confirmed pattern for observability platforms with LLM prompts/responses. | HIGH |
| Async embedding worker | Universal pattern in observability pipelines. OTel Collector uses batch processors. Langfuse uses dedicated worker container. LangWatch documents "async processing that doesn't block requests." | HIGH |
| Separate Diagnosticer service | Braintrust data plane isolation, LangWatch async isolation. LLM calls are slow and on-demand — always isolated from ingestion path. | HIGH |
| Application-level merge (ClickHouse + PostgreSQL) | Confirmed by ClickHouse/PostgreSQL integration documentation: PostgreSQL as transactional source of truth, ClickHouse for analytical reads, merged at application layer. | HIGH |
| OTLP HTTP/protobuf transport | Standard. OTel spec mandates port 4318 for HTTP, 4317 for gRPC. HTTP is preferred for compatibility; gRPC for throughput-critical scenarios. | HIGH |

---

## Sources

- [Langfuse Architecture Handbook](https://langfuse.com/handbook/product-engineering/architecture) — polyglot persistence: PostgreSQL + ClickHouse + Redis + S3 pattern
- [Langfuse V3 Infrastructure Evolution](https://langfuse.com/blog/2024-12-langfuse-v3-infrastructure-evolution) — Redis queue, async worker, S3 event storage, ClickHouse write pattern
- [Langfuse and ClickHouse: A new data stack](https://clickhouse.com/blog/langfuse-and-clickhouse-a-new-data-stack-for-modern-llm-applications) — migration rationale from PostgreSQL to ClickHouse for trace data
- [ClickStack: AI Agent Observability Architecture](https://clickhouse.com/blog/tracing-openai-agents-clickstack) — ClickHouse for agent span storage
- [OpenTelemetry Collector Architecture](https://opentelemetry.io/docs/collector/architecture/) — receiver/processor/exporter pipeline model
- [OTLP Specification 1.10.0](https://opentelemetry.io/docs/specs/otlp/) — gRPC port 4317, HTTP port 4318, protobuf encoding
- [Building Observability with ClickHouse at Dash0](https://clickhouse.com/blog/building-an-observability-solution-with-clickhouse-at-dash0) — ClickHouse + PostgreSQL split: ClickHouse for OTel data, PostgreSQL for customer settings
- [PostgreSQL + ClickHouse for Agentic AI Scale](https://thenewstack.io/postgres-clickhouse-the-oss-stack-to-handle-agentic-ai-scale/) — validated ClickHouse + PostgreSQL dual-store pattern
- [Redis for AI/ML Pipelines](https://redis.io/blog/how-to-build-a-language-processing-pipeline-using-ai-with-redis/) — Redis queue for embedding pipeline
- [Sentence Transformers Batch Processing](https://milvus.io/ai-quick-reference/how-can-you-do-batch-processing-of-sentences-for-embedding-to-improve-throughput-when-using-sentence-transformers) — batch_size tuning for embedding throughput
- [Braintrust Data Plane Isolation](https://www.braintrust.dev/articles/best-ai-observability-platforms-2025) — on-demand diagnostic service isolation pattern
- [ClickHouse Cost Optimization Playbook 2026](https://clickhouse.com/resources/engineering/observability-cost-optimization-playbook) — async inserts, tiered S3 storage for hot/cold data

---
*Architecture research for: AI agent observability and debugging platform (Xeter)*
*Researched: 2026-03-27*

# Xeter — Architecture Documentation
arc42 Template | Version 1.0 — Post-implementation
Audience: Developers

> **Changelog v1.0** — Updated after v1.0 MVP shipment. All TBDs from v0.5 resolved. Deployment view documented. Worker service separated from Analyser. Auth, embedding model, and threshold strategy confirmed against real implementation. New architecture decisions added (AD21–AD25).
>
> **Changelog v0.5** — Added `available_tools_ref` and `tool_arguments` span fields to support wrong-tool and wrong-argument detection (A1, A7). Updated Analyser heuristics, embedding strategy, solution strategy, and architecture decisions accordingly.

---

## Table of Contents

1. Introduction and Goals
2. Architecture Constraints
3. System Scope and Context
4. Solution Strategy
5. Building Block View
6. Runtime View
7. Deployment View
8. Cross-cutting Concepts
9. Architecture Decisions
10. Quality Requirements
11. Risks and Technical Debt
12. Glossary

---

## 1. Introduction and Goals

### 1.1 Requirements Overview

Xeter is a B2B SaaS observability platform for AI agents. It ingests spans emitted by instrumented agent code via a Python SDK, applies heuristic analysis at runtime to flag anomalous tool calls, and exposes a dashboard from which developers can inspect flags, similarity scores, and S3 payloads. An LLM-powered Diagnosticer is scaffolded in v1 and will be activated in v2.

The primary focus of v1 is detection of tool-call anomalies: wrong tool invoked relative to the prompt, wrong arguments passed, no tool invoked when expected, excessive tool calls, and parsing errors.

### 1.2 Quality Goals

| Priority | Quality Goal | Motivation |
|----------|-------------|------------|
| 1 | Correctness of flagging | False positives erode trust and will be ignored |
| 2 | Low-latency ingestion | Agents run continuously; the pipeline must not become a bottleneck |
| 3 | Async analysis | Flagging must not block span storage |
| 4 | Configurability | LLM backend for diagnostics must be swappable (external or local) |
| 5 | Multi-tenancy | B2B SaaS requires strict tenant isolation |

### 1.3 Stakeholders

| Role | Expectation |
|------|-------------|
| B2B customer (developer) | Integrate SDK, view flagged spans, inspect similarity scores and payloads |
| Xeter operator | Deploy and operate the SaaS platform |

---

## 2. Architecture Constraints

| Constraint | Rationale |
|-----------|-----------|
| SaaS deployment only | No on-premise distribution in scope |
| Split storage: ClickHouse + PostgreSQL + S3 + Redis | Replaces earlier "single database TBD"; each store chosen for its workload |
| LLM for diagnostics is configurable | Customers may require local models for data sovereignty |
| SDK primary language: Python | Python covers ~80% of agent implementations |
| SDK secondary language: TypeScript | Deferred to v1.1 (lags Python by one release cycle) |
| View has no business logic | All logic lives in backend services |
| Multi-tenant | Each B2B customer is an isolated tenant |
| Auth: API key (SDK) + email/password + JWT (dashboard) | API key for machine ingestion; email/password for developer login; no external auth dependency in v1 |

---

## 3. System Scope and Context

### 3.1 Business Context

```
+-------------------+  SDK (HTTP/JSON)  +-------------------+
| Customer Agent    |------------------>| Xeter Platform    |
| (B2B Tenant)      |                   |                   |
|                   |<-- Dashboard (HTTP) ----------------  |
+-------------------+                   +-------------------+
                                                 |
                                         LLM Provider (ext/local)
                                         [scaffolded in v1, active v2]
```

External interfaces:

| Interface | Direction | Description |
|-----------|-----------|-------------|
| SDK | Inbound | Customer instruments agent code; spans sent via HTTP/JSON POST to Analyser |
| Dashboard (View) | Bidirectional | Developer browses spans, applies filters, drills into detail |
| LLM Provider | Outbound | Diagnosticer calls external or local LLM (inactive in v1) |

### 3.2 Technical Context

| Channel | Protocol | Notes |
|---------|----------|-------|
| SDK → Analyser | HTTP/JSON | POST /v1/spans with `x-api-key` header; custom JSON schema (not standard OTLP wire format) |
| Analyser → ClickHouse | Native HTTP | Batched INSERT via clickhouse-connect; no single-row inserts |
| Analyser → S3 | HTTP (boto3/aioboto3) | Sequential per-field uploads for large payloads |
| Analyser → Redis | Redis protocol | LPUSH span_id to `analysis_queue` |
| Worker → Redis | Redis protocol | BRPOP from `analysis_queue` with 2s timeout |
| Worker → ClickHouse | Native HTTP | SELECT to fetch span fields for embedding |
| Worker → S3 | HTTP (boto3) | GET to fetch `available_tools` JSON |
| Worker → PostgreSQL | asyncpg / psycopg2 | INSERT scores and flag rows |
| Presenter → ClickHouse | Native HTTP | SELECT spans with tenant_id filter |
| Presenter → PostgreSQL | asyncpg | SELECT flags, scores; JOIN in application code |
| Presenter → S3 | aioboto3 | Lazy GET of prompt/response/raw_response on span detail only |
| Presenter → Diagnosticer | HTTP (httpx) | Proxied POST /diagnose; Diagnosticer returns 501 in v1 |
| Presenter → View | REST (HTTP/JSON) | All v1 interactions are request/response; SSE deferred to v1.1 |

---

## 4. Solution Strategy

| Problem | Decision | Rationale |
|---------|----------|-----------|
| Anomaly detection without blocking ingestion | Async worker via Redis queue | Span is stored immediately; Worker runs after via BRPOP |
| Tool-call anomaly detection | Vector embedding similarity | Compare prompt↔tool fields using all-MiniLM-L6-v2 |
| Wrong tool detection | Embed prompt against all available tools | `available_tools_ref` captures full tool list in S3; Worker ranks by cosine similarity, flags if called tool is not top match |
| Wrong argument detection | Embed prompt against tool_arguments | Low-confidence signal; excluded from P/R calibration |
| Parsing error detection | Embedding of model_name + prompt | Detects prompt/model mismatch patterns |
| Deep diagnosis | On-demand LLM call from dashboard | Expensive; only run when explicitly requested; inactive in v1 |
| High-volume immutable span storage | ClickHouse | OLAP, append-only, proven at scale by competitors |
| Mutable relational data (flags, scores, tenants, auth) | PostgreSQL with RLS | Low volume, relational, row-level security for tenant isolation |
| Large text payloads | S3 | Prevent row bloat in ClickHouse; store reference key in span row |
| Ingestion queue for async flagging | Redis BRPOP | Standard worker pattern; decouples ingestion from embedding |
| Tenant isolation | PostgreSQL RLS + DAL tenant guard | RLS as defence-in-depth; Python raises MissingTenantError before any DB call |
| Cross-store span view assembly | Presenter merges two queries | ClickHouse span + PostgreSQL flags/scores joined in application code |
| S3 payload retrieval | Lazy loading in Presenter | Only fetched on GET /spans/{id}, never on list view |

---

## 5. Building Block View

### 5.1 Level 1 — System Decomposition

```
+-------+    +---------+    +-------+    +----------+    +----------+    +------+
|  SDK  |--->| Analyser|--->| Redis |--->|  Worker  |--->| PostgreSQL|    | View |
+-------+    +---------+    +-------+    +----------+    +----------+    +------+
                  |                           |                ^             |
                  v                           v                |             v
            +---------+                +----------+      +----------+  +---------+
            |ClickHouse|               |ClickHouse|      |  Scores  |  |Presenter|
            +---------+                +----------+      +----------+  +---------+
                  |                                                          |
                  v                                                          v
            +--------+                                               +-------------+
            |  S3    |<----------------------------------------------| Diagnosticer|
            +--------+                                               +-------------+
```

### 5.2 Component Descriptions

**SDK** (`sdk/xeter_sdk/`)
- `@xeter.trace` decorator captures all span fields at decoration time
- Sends spans fire-and-forget from a background daemon thread (zero added latency)
- `XETER_ENDPOINT` and `XETER_API_KEY` configured via environment variables
- `response` and `raw_response` sent as null (not available at decoration time)
- Language: Python 3.12+

**Analyser** (`xeter/services/analyser/`)
- FastAPI app; single endpoint: POST /v1/spans
- Ingestion path (locked sequence): authenticate API key → upload large fields to S3 → batch span row into ClickHouse → LPUSH span_id to Redis
- Manages long-lived singletons via FastAPI lifespan: SpanBatcher, Redis client, S3Client
- SpanBatcher flushes every 5 seconds or when batch reaches threshold (prevents ClickHouse "Too Many Parts")

**Worker** (`xeter/services/worker/`)
- Standalone BRPOP consumer; runs as a separate Docker service
- Loop: BRPOP span_id from Redis → fetch span from ClickHouse → fetch `available_tools` from S3 → run all registered analyzers → write scores + flags to PostgreSQL
- Analyzer registry: `ANALYZERS = [ToolCallAnalyzer(...)]` — extensible by appending; zero modification to existing analyzers
- ToolCallAnalyzer: 5 embedding comparisons (prompt↔tool_name, prompt↔tool_description, prompt↔response, model_name+prompt, prompt↔each available tool)
- Embedding model: all-MiniLM-L6-v2 (sentence-transformers), pre-baked into Docker image
- SIGTERM handled via `running` flag + BRPOP timeout=2s (clean shutdown within ~2s)
- Retry logic: up to 3 attempts with 5s/10s backoff for "span not found" race (ClickHouse batch flush interval)

**Presenter** (`xeter/services/presenter/`)
- FastAPI app; REST API consumed by View
- GET /spans — paginated span list with flag indicators, similarity score overlays, filters (flag_type, agent_name, from_time, to_time)
- GET /spans/{id} — span detail with parallel ClickHouse + PostgreSQL queries; lazy S3 payload fetch (prompt, response, raw_response) with asyncio.wait_for timeout
- POST /login — email/password auth, returns JWT
- POST /register — tenant creation, returns one-time API key
- POST /diagnose — proxied to Diagnosticer via httpx.AsyncClient (returns 501 in v1)
- All endpoints: 401 for missing/invalid JWT; cross-tenant isolation via tenant_id WHERE clause

**Diagnosticer** (`xeter/services/diagnosticer/`)
- Separate FastAPI service on port 8001
- GET /healthz — 200 OK
- POST /diagnose — 501 Not Implemented (scaffold; active in v2)
- Wired to Presenter via httpx.AsyncClient in lifespan; enables v2 activation without rearchitecting

**View** (`services/view/`)
- Next.js 15 app; no business logic
- Auth store: JWT token in memory, hydrated via useHydrateAuth hook (SSR-safe)
- Span list: paginated table with StatusDot (flagged/clean/pending), FilterBar with URL state via nuqs
- Span detail: slide-in Sheet with FlagSection, similarity scores, PayloadTabs (Prompt/Response/Raw Response)
- Diagnostic button: enabled only for flagged spans; calls POST /diagnose and displays response

**Storage:**
- **ClickHouse** — spans (immutable, append-only), `ORDER BY (tenant_id, trace_id, time_begin)`
- **PostgreSQL** — flags, span_scores, tenants, users, api_keys; RLS on all tables except span_scores (explicit WHERE tenant_id)
- **S3 (MinIO)** — prompt, response, raw_response, available_tools; bucket: `xeter-payloads`; auto-created by `minio-init` service on startup

---

## 6. Runtime View

### 6.1 Data Flow — Span Ingestion

```
Agent Code
    |
    | POST /v1/spans  (HTTP/JSON, x-api-key header)
    v
Analyser
    |-- verify API key (bcrypt hash lookup in PostgreSQL)
    |-- upload prompt, response, raw_response, available_tools → S3
    |-- SpanBatcher.add(row)  [batched, flushed every 5s → ClickHouse]
    |-- LPUSH span_id → Redis analysis_queue
    └── return 200 OK
```

### 6.2 Data Flow — Embedding and Flagging

```
Worker (BRPOP loop)
    |
    | BRPOP span_id from Redis (timeout=2s)
    |
    |-- fetch span row from ClickHouse (retry up to 3x, 5s/10s backoff)
    |-- fetch available_tools JSON from S3 (via available_tools_ref)
    |
    | for each analyzer in ANALYZERS:
    |   ToolCallAnalyzer:
    |     embed prompt, tool_name, tool_description, response, model_name
    |     embed prompt vs each tool in available_tools → rank → wrong_tool?
    |     embed prompt vs tool_arguments values → wrong_tool_args?
    |     compute 5+ similarity scores
    |     classify: wrong_tool / wrong_tool_args / no_tool / excessive_tool / parsing_error
    |
    |-- INSERT rows into span_scores (PostgreSQL) — one row per comparison, always
    └-- INSERT rows into flags (PostgreSQL) — only if score exceeds threshold
```

### 6.3 Data Flow — Read Path

```
View
    |-- GET /spans?flag_type=wrong_tool&agent_name=...&from_time=...
    |       Presenter: SELECT spans FROM ClickHouse + LEFT JOIN flags FROM PostgreSQL
    |       Returns: paginated list with status (flagged/clean/pending) + score overlay
    |
    |-- GET /spans/{id}
    |       Presenter: parallel queries:
    |         - ClickHouse: SELECT span WHERE tenant_id AND span_id
    |         - PostgreSQL: SELECT flags, scores WHERE span_id
    |       Then: asyncio.gather → fetch prompt/response/raw_response from S3
    |       Returns: full span detail with lazy-loaded payloads
    |
    └-- POST /diagnose  →  Presenter  →  Diagnosticer (501 in v1)
```

### 6.4 Diagnostic Flow (v2)

```
View
    |-- POST /diagnose  →  Presenter  →  Diagnosticer
    |                            |
    |                            v
    |                     fetch full trace from ClickHouse + flags from PostgreSQL
    |                     call configured LLM with trace context
    |                     INSERT diagnostic row into PostgreSQL
    |
    └── return diagnostic result to View
```

---

## 7. Deployment View

### 7.1 Docker Compose Services

All services are orchestrated via `deploy/docker-compose.yml`. Services start in dependency order enforced by `depends_on` with `condition: service_healthy`.

```
┌─────────────────────────────────────────────────────────┐
│  docker-compose.yml                                     │
│                                                         │
│  Infrastructure:                                        │
│    clickhouse  (port 8123)  ─────────────┐              │
│    postgres    (port 5432)  ─────────────┤              │
│    redis       (port 6379)  ─────────────┤              │
│    minio       (port 9100, 9101)  ────── ┤              │
│    minio-init  (one-shot bucket creator) ┤              │
│                                          │              │
│  Application:                            │              │
│    analyser    (port 4318)  ◀────────────┤ all infra    │
│    worker      (no port)    ◀────────────┤ all infra    │
│    presenter   (port 8000)  ◀────────────┤ all infra    │
│    diagnosticer(port 8001)  ◀────────────┤ postgres     │
│    view        (port 3000)  ◀── presenter, analyser     │
└─────────────────────────────────────────────────────────┘
```

### 7.2 Service Configuration

| Service | Image | Key Environment Variables |
|---------|-------|--------------------------|
| analyser | python:3.12-slim (xeter package) | DATABASE_URL, CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD, REDIS_URL, S3_* |
| worker | custom (pre-bakes all-MiniLM-L6-v2) | DATABASE_URL, CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD, REDIS_URL, S3_*, THRESHOLD_* |
| presenter | python:3.12-slim (xeter package) | DATABASE_URL, CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD, JWT_SECRET, S3_*, DIAGNOSTICER_URL |
| diagnosticer | python:3.12-slim (xeter package) | DATABASE_URL |
| view | node:20-alpine | NEXT_PUBLIC_API_URL |
| clickhouse | clickhouse/clickhouse-server:25.3 | CLICKHOUSE_PASSWORD |
| postgres | postgres:16 | POSTGRES_* |
| redis | redis:7 | — |
| minio | minio/minio | MINIO_ROOT_USER, MINIO_ROOT_PASSWORD |
| minio-init | minio/mc (one-shot) | creates `xeter-payloads` bucket |

### 7.3 Ports

| Service | Port |
|---------|------|
| Presenter (API) | 8000 |
| Analyser (ingestion) | 4318 |
| Diagnosticer | 8001 |
| View (dashboard) | 3000 |
| PostgreSQL | 5432 |
| ClickHouse (HTTP) | 8123 |
| Redis | 6379 |
| MinIO (API) | 9100 |
| MinIO (Console) | 9101 |

---

## 8. Cross-cutting Concepts

### 8.1 Multi-tenancy

All tables carry `tenant_id`. PostgreSQL tables use Row Level Security: every session runs `SET LOCAL app.current_tenant_id = :tenant_id` inside `tenant_session()`, and RLS policies filter rows automatically. The DAL raises `MissingTenantError` at the Python level before any DB call.

Exception: `span_scores` table has no RLS policy (Worker connects as BYPASSRLS role). Tenant isolation there is enforced via explicit `WHERE tenant_id = :tenant_id` in all Presenter queries. This is documented with a CRITICAL comment in the codebase.

### 8.2 Authentication and Authorization

**SDK ingestion (Analyser):**
- API key per tenant; key has `xtr_` prefix for identification
- Analyser stores bcrypt hash; plaintext key returned once at registration
- Header: `x-api-key: <key>`

**Dashboard (Presenter):**
- Email/password login; bcrypt hash stored in PostgreSQL
- POST /login returns a JWT signed with `JWT_SECRET`
- Header: `Authorization: Bearer <token>` on all subsequent requests
- 401 returned for missing or invalid token

**Future (v2):** Clerk migration for multi-member tenants / SSO. Schema supports migration without structural changes.

### 8.3 Data Model

Three stores. Spans are immutable once written. Flags and scores are separate append-only tables in PostgreSQL, referenced by `span_id`. The Presenter merges results from both stores at read time.

**ClickHouse — spans table**

`ORDER BY (tenant_id, trace_id, time_begin)` — partition key is the first component.

| Field | Type | Notes |
|-------|------|-------|
| tenant_id | String | Required for tenant isolation; first ORDER BY component |
| trace_id | String | Groups spans into one session |
| span_id | String | Unique per row |
| parent_span_id | String / null | Null if root span |
| time_begin | DateTime64 | |
| time_end | DateTime64 | |
| agent_name | String | |
| agent_model | String | |
| recipient | String | "user" or agent name |
| recipient_model | String / null | Null if recipient is user |
| tool_name | String / null | Null if no tool call |
| tool_description | String / null | Null if no tool call |
| tool_arguments | String / null | JSON object stored inline; small payload |
| tool_output | String / null | Null if no tool call |
| available_tools_ref | String / null | S3 key for full tool list JSON array |
| prompt_ref | String | S3 key for prompt |
| response_ref | String | S3 key for agent-processed response |
| raw_response_ref | String | S3 key for original LLM output |
| schema_version | String | `xeter.schema.version` — always "1.0" in v1 |

**PostgreSQL — flags table**

Append-only. One row per flag per span. A span with no anomalies has no rows here.

| Field | Type | Notes |
|-------|------|-------|
| flag_id | UUID | Primary key |
| tenant_id | String | RLS policy filters on this |
| span_id | String | References ClickHouse span |
| trace_id | String | Denormalised for trace-level queries |
| flag_type | VARCHAR | Open string — `wrong_tool`, `wrong_tool_args`, `no_tool`, `excessive_tool`, `parsing_error`. Not an enum; new types never require schema migrations |
| score | Float | Similarity score from embedding comparison |
| detail | JSONB | Context: compared fields, candidate tool rankings, etc. |
| created_at | Timestamp | |

**PostgreSQL — span_scores table**

Append-only. One row per embedding comparison per span, regardless of whether a flag was written. This is the calibration dataset.

| Field | Type | Notes |
|-------|------|-------|
| score_id | UUID | Primary key |
| tenant_id | String | No RLS; explicit WHERE tenant_id in queries |
| span_id | String | References ClickHouse span |
| comparison | VARCHAR | e.g. `prompt_tool_name`, `prompt_tool_description` |
| score | Float | Cosine similarity |
| created_at | Timestamp | |

**PostgreSQL — diagnostics table**

Append-only. One row per diagnostic run. Inactive in v1; schema exists for v2 activation.

| Field | Type | Notes |
|-------|------|-------|
| diagnostic_id | UUID | Primary key |
| tenant_id | String | RLS policy filters on this |
| span_id | String | References ClickHouse span |
| trace_id | String | Denormalised |
| llm_backend | String | Model name or endpoint used |
| result | JSONB | Diagnostic output; structure TBD |
| created_at | Timestamp | |

### 8.4 Embedding Strategy

Embedding model: **all-MiniLM-L6-v2** (sentence-transformers). Pre-baked into Worker Docker image to avoid runtime download.

| Comparison | Flag type | Confidence |
|-----------|-----------|------------|
| prompt ↔ tool_name | wrong_tool | Medium |
| prompt ↔ tool_description | wrong_tool | High |
| prompt ↔ response | (response anomaly) | Medium |
| model_name + prompt | parsing_error | Medium |
| prompt ↔ each tool in available_tools (ranking) | wrong_tool | High — primary signal |
| prompt ↔ tool_arguments values | wrong_tool_args | Low |

**Threshold calibration:** Calibration harness (`xeter/scripts/calibrate.py`) generates a precision/recall curve from labelled spans. Precision target: ≥80% (optimise for precision to minimise false alarms). `wrong_tool_args` is excluded from P/R calibration — it is low-confidence by design and its threshold is set independently.

**All scores are always logged** in `span_scores` regardless of whether a flag is written. This provides a growing calibration dataset from production traffic.

### 8.5 Error Handling

- **Embedding fails:** span already stored in ClickHouse; no flag/score rows written; failure logged.
- **S3 fetch of available_tools_ref fails:** wrong-tool heuristic skipped for that span; other comparisons proceed; failure logged.
- **Worker "span not found":** ClickHouse batcher may not have flushed yet; Worker retries up to 3 times with 5s/10s backoff before giving up.
- **Diagnosticer unreachable:** Presenter catches `httpx.HTTPError` and returns 502; existing data unaffected.
- **S3 payload fetch times out (Presenter):** `asyncio.wait_for` wraps the fetch; `asyncio.TimeoutError` → 504, other errors → 502.
- **ClickHouse span insert fails:** span lost (SDK is fire-and-forget, no retry); SpanBatcher logs but does not re-raise.
- **PostgreSQL flag insert fails:** span exists but unflagged; Worker does not currently retry flag writes (acceptable for v1).

### 8.6 Observability of Xeter Itself

Structured logging via `structlog` across all services. No self-monitoring dashboard in v1.

---

## 9. Architecture Decisions

| ID | Decision | Status | Rationale |
|----|----------|--------|-----------|
| AD01 | Async flagging | Decided | Span ingestion must not be blocked by embedding computation |
| AD02 | Diagnosticer as separate service | Decided | LLM calls are slow and on-demand; isolation allows independent scaling |
| AD03 | Split storage (ClickHouse + PostgreSQL + S3 + Redis) | Decided | Each store chosen for its workload; replaces earlier "single database TBD" |
| AD04 | View has no logic | Decided | All logic centralised in backend services |
| AD05 | LLM backend configurable | Decided | Data sovereignty requirements in B2B |
| AD06 | Multi-tenant architecture | Decided | B2B SaaS requirement; tenant_id on all tables |
| AD07 | Span storage: ClickHouse | Decided | High-volume, append-only, immutable rows; OLAP queries; proven by Langfuse and LangSmith at identical workload |
| AD08 | Flags and scores storage: PostgreSQL | Decided | Low-volume, mutable, relational; append-only rows referencing span_id |
| AD09 | Large payload storage: S3 | Decided | prompt, response, raw_response, available_tools stored in S3; ClickHouse holds reference key only |
| AD10 | Spans are immutable; flags/scores are separate tables | Decided | Eliminates ClickHouse mutation cost; append-only pattern on both stores |
| AD11 | Presenter merges ClickHouse + PostgreSQL at read time | Decided | Two parallel queries per span view; small latency accepted |
| AD12 | Ingestion queue: Redis BRPOP | Decided | Decouples ingestion from embedding worker; FIFO ordering via LPUSH/BRPOP |
| AD13 | Presenter protocol: REST only (v1) | Decided | SSE deferred to v1.1; v1 uses request/response for all interactions |
| AD14 | Auth: API key + bcrypt (SDK); email/password + bcrypt + JWT (dashboard) | Decided | Zero external auth dependency in v1; schema supports Clerk migration later |
| AD15 | SDK primary language: Python | Decided | Python powers ~80% of AI agent implementations |
| AD16 | SDK secondary language: TypeScript | Decided | Deferred to v1.1; lags Python by one release cycle (AD18) |
| AD17 | Backend services language: Python | Decided | Analyser and Worker require embedding libraries that are Python-native |
| AD18 | TypeScript SDK will lag Python SDK by one release cycle | Decided | Single maintainer; schema changes hit Python first |
| AD19 | `available_tools` stored in S3, reference key in ClickHouse | Decided | Tool lists can be large (many tools with full JSON schemas); consistent with prompt/response treatment |
| AD20 | `tool_arguments` stored inline as JSON in ClickHouse | Decided | Arguments are typically small key-value objects; inline avoids S3 round-trip on every span |
| AD21 | Embedding model: all-MiniLM-L6-v2 | Decided | Lightweight (80MB), fast CPU inference, sufficient cosine similarity quality for tool-name vs prompt comparison; pre-baked into Worker Docker image |
| AD22 | bcrypt used directly (not passlib) | Decided | passlib 1.7.4 is incompatible with Python 3.14 + current bcrypt; direct bcrypt.hashpw/checkpw is stable |
| AD23 | `wrong_tool_args` excluded from P/R calibration | Decided | Low-confidence signal by design — terse JSON argument values produce unreliable cosine similarity; threshold set independently; flag shown with low-confidence indicator in View |
| AD24 | Worker BRPOP retry with backoff | Decided | ClickHouse SpanBatcher flushes every 5s; Redis delivers span_id before flush completes; Worker retries up to 3× with 5s/10s backoff |
| AD25 | `span_scores` has no PostgreSQL RLS | Decided | Worker connects as BYPASSRLS role for performance; tenant isolation enforced via explicit `WHERE tenant_id` in all Presenter queries; documented with CRITICAL comment |

---

## 10. Quality Requirements

### 10.1 Quality Scenarios

| ID | Quality Scenario | Expected Response |
|----|-----------------|-------------------|
| QS01 | Correctness | Analyser flags a span where prompt is "schedule a meeting" and tool_name is "get_weather" | Flag is written with wrong_tool type and high anomaly score |
| QS02 | Correctness | Analyser does not flag a span where tool use matches prompt semantically | No flag written; similarity scores logged in span_scores |
| QS03 | Performance | High volume of spans ingested continuously | Spans stored without delay (POST /v1/spans returns immediately after S3 + batch enqueue); flagging completes asynchronously via Worker |
| QS04 | Availability | LLM provider is unreachable | Diagnosticer returns 502 to Presenter; View shows error; existing span/flag data unaffected |
| QS05 | Isolation | Tenant A queries spans | Tenant B's data is never returned; enforced by RLS + explicit WHERE tenant_id |
| QS06 | Correctness | Span where tool_arguments recipient is inconsistent with prompt | wrong_tool_args flag written with low-confidence score and detail JSON |
| QS07 | Correctness | Span where called tool is not the top-ranked match in available_tools | wrong_tool flag written with ranked candidate list in detail JSON |

---

## 11. Risks and Technical Debt

| ID | Risk | Impact | Status | Mitigation |
|----|------|--------|--------|------------|
| R01 | ClickHouse operational complexity | Medium | Open | Use managed ClickHouse (ClickHouse Cloud) for SaaS deployment |
| R02 | Cross-store query latency | Low-Medium | Accepted | Presenter parallelises the two queries; latency measured at ~37s E2E including worker processing |
| R03 | Embedding threshold calibration | High | Mitigated | Calibration harness built (`calibrate.py`); P/R curve produced; precision target ≥80% set; `span_scores` provides growing production calibration dataset |
| R04 | Auth security | Low | Resolved | API key + bcrypt (SDK); email/password + bcrypt + JWT (dashboard); implemented in v1 |
| R05 | agent_model / recipient_model inference | Low | Open | SDK passes these as explicit parameters; no inference needed in v1 |
| R06 | S3 payload retrieval strategy | Medium | Resolved | Lazy loading: S3 payloads fetched only on GET /spans/{id}, never on list view; `asyncio.wait_for` with timeout |
| R07 | diagnostics.result JSON structure | Low | Open | Diagnosticer inactive in v1; structure will be defined when LLM integration is designed for v2 |
| R08 | Dual SDK maintenance (Python + TypeScript) | Medium | Deferred | TypeScript SDK deferred to v1.1; when implemented, version-lock both SDKs and run integration tests against both |
| R09 | available_tools not captured by SDK | High | Resolved | SDK captures `available_tools` via `tools_arg` parameter; stored in S3; validated in integration tests |
| R10 | wrong_tool_args false-positive rate | Medium | Accepted | Treated as low-confidence by design; excluded from P/R calibration; score shown prominently in View |
| R11 | span_scores has no RLS | Medium | Accepted | Documented with CRITICAL comment; explicit WHERE tenant_id in all Presenter queries; monitored risk for future RLS addition |

---

## 12. Glossary

| Term | Definition |
|------|------------|
| Span | A single recorded unit of agent execution, one immutable row in ClickHouse |
| Trace | A group of spans sharing the same trace_id, representing one agent session |
| Root span | A span with parent_span_id = null; a trace may have multiple roots |
| Flag | A row in the PostgreSQL flags table written by the Worker, indicating a detected anomaly |
| Score | A row in the PostgreSQL span_scores table; logged for every span regardless of flagging; used for calibration |
| Diagnostic | A row in the PostgreSQL diagnostics table written by the Diagnosticer via LLM analysis, on user request (inactive v1) |
| Analyser | Service responsible for receiving spans, storing them (S3 + ClickHouse), and enqueuing span_ids to Redis |
| Worker | BRPOP consumer service; performs embedding computation, similarity scoring, and flag writing |
| Diagnosticer | Separate service called on demand to run LLM-based trace analysis (scaffolded in v1, active in v2) |
| Presenter | Backend API layer that merges ClickHouse + PostgreSQL + S3 data before serving View |
| View | Next.js 15 frontend dashboard; no business logic |
| SpanBatcher | In-process buffer in Analyser that accumulates rows and flushes to ClickHouse in batches |
| BRPOP | Redis blocking right-pop; used by Worker to consume span_ids from `analysis_queue` |
| OTel | OpenTelemetry — the observability framework whose span model Xeter's SDK is inspired by |
| Heuristic | In this context: vector embedding cosine similarity comparison between span fields |
| raw_response | The original LLM output before any agent-side modification; stored in S3 |
| response | The agent-processed version of raw_response, as actually used; stored in S3 |
| payload_ref | An S3 object key stored in the ClickHouse span row pointing to a large text field |
| available_tools | The full JSON array of tools passed to the LLM in a given span; stored in S3, referenced by available_tools_ref |
| tool_arguments | The arguments passed to the called tool, stored as inline JSON in the span row |
| MissingTenantError | Python exception raised by the DAL before any DB call when tenant_id is absent |
| tenant_session() | PostgreSQL session context that sets `app.current_tenant_id` for RLS policy enforcement |

---

Document status: v1.0 — post-implementation. All v1 architecture decisions resolved. Open items: diagnostics.result structure (v2), TypeScript SDK (v1.1), cloud deployment (v1.1).

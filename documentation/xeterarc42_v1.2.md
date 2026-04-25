# Xeter — Architecture Documentation
arc42 Template | Version 1.2 — Post-implementation
Audience: Developers

> **Changelog v1.2** — Updated after v1.2 Diagnosticer shipment (2026-04-25). The scaffolded Diagnosticer service is now fully active: LLM provider factory (Anthropic / OpenAI / Ollama), context assembly from ClickHouse + PostgreSQL + S3, PostgreSQL `diagnoses` table with RLS, real POST /diagnose endpoint with fail-clean pipeline, DiagnosisService layer in Presenter with tenant guard and error classification, GET /diagnose/{span_id} polling endpoint, and SpanDetailPanel DiagnosisCard with auto-load. New architecture decisions: AD35–AD43.
>
> **Changelog v1.1** — Updated after v1.1 Analyser Accuracy shipment (2026-04-18). The four originally-wrong heuristic check methods in ToolCallAnalyzer have been replaced with research-backed implementations. `_check_wrong_tool` split into three distinct checks. `_check_wrong_args` rewritten with output-error-priority and hybrid scoring. `_check_parsing_error` replaced by a model-format registry. `_check_response_anomaly` added. Embedder extracted as a separate HTTP microservice. spaCy integrated for NLP-based containment guards and social-prompt detection. Calibration infra upgraded to support per-method runs and binary flag types. New architecture decisions: AD26–AD34.
>
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

Xeter is a B2B SaaS observability platform for AI agents. It ingests spans emitted by instrumented agent code via a Python SDK, applies heuristic analysis at runtime to flag anomalous tool calls, and exposes a dashboard from which developers can inspect flags, similarity scores, and S3 payloads. As of v1.2, the LLM-powered Diagnosticer is fully active: clicking "Diagnose" on any span triggers an on-demand root-cause analysis that returns a structured verdict (model / architecture / prompt), severity, affected field, and recommended fix.

The v1.2 milestone activated the Diagnosticer service and wired it end-to-end: Presenter triggers and retrieves diagnoses, the frontend renders structured results, and all LLM provider config is driven by environment variables (Anthropic, OpenAI, or Ollama).

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
| B2B customer (developer) | Integrate SDK, view flagged spans, inspect similarity scores, trigger LLM diagnosis |
| Xeter operator | Deploy and operate the SaaS platform |

---

## 2. Architecture Constraints

| Constraint | Rationale |
|-----------|-----------|
| SaaS deployment only | No on-premise distribution in scope |
| Split storage: ClickHouse + PostgreSQL + S3 + Redis | Replaces earlier "single database TBD"; each store chosen for its workload |
| LLM for diagnostics is configurable | Customers may require local models for data sovereignty |
| SDK primary language: Python | Python covers ~80% of agent implementations |
| SDK secondary language: TypeScript | Deferred to v1.3+ |
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
                                         [active in v1.2]
```

External interfaces:

| Interface | Direction | Description |
|-----------|-----------|-------------|
| SDK | Inbound | Customer instruments agent code; spans sent via HTTP/JSON POST to Analyser |
| Dashboard (View) | Bidirectional | Developer browses spans, applies filters, drills into detail, triggers diagnosis |
| LLM Provider | Outbound | Diagnosticer calls Anthropic / OpenAI / Ollama for root-cause analysis |

### 3.2 Technical Context

| Channel | Protocol | Notes |
|---------|----------|-------|
| SDK → Analyser | HTTP/JSON | POST /v1/spans with `x-api-key` header; custom JSON schema |
| Analyser → ClickHouse | Native HTTP | Batched INSERT via clickhouse-connect; no single-row inserts |
| Analyser → S3 | HTTP (boto3/aioboto3) | Sequential per-field uploads for large payloads |
| Analyser → Redis | Redis protocol | LPUSH span_id to `analysis_queue` |
| Worker → Redis | Redis protocol | BRPOP from `analysis_queue` with 2s timeout |
| Worker → Embedder | HTTP/JSON | POST /encode and /similarity to embedder microservice |
| Worker → ClickHouse | Native HTTP | SELECT to fetch span fields for embedding |
| Worker → S3 | HTTP (boto3) | GET to fetch `available_tools` JSON |
| Worker → PostgreSQL | asyncpg / psycopg2 | INSERT scores and flag rows |
| Presenter → ClickHouse | Native HTTP | SELECT spans with tenant_id filter |
| Presenter → PostgreSQL | asyncpg | SELECT flags, scores, diagnoses; JOIN in application code |
| Presenter → S3 | aioboto3 | Lazy GET of prompt/response/raw_response on span detail only |
| Presenter → Diagnosticer | HTTP (httpx) | POST /diagnose with bearer token forwarding; real endpoint in v1.2 |
| Diagnosticer → PostgreSQL | asyncpg | INSERT/SELECT diagnoses table via DiagnosisRepository |
| Diagnosticer → ClickHouse | Native HTTP | SELECT span fields for context assembly |
| Diagnosticer → S3 | aioboto3 | GET prompt/response payloads for context assembly (5s timeout) |
| Diagnosticer → LLM provider | HTTP | Anthropic / OpenAI / Ollama — async clients, structured output only |
| Presenter → View | REST (HTTP/JSON) | All v1 interactions are request/response; SSE deferred |

---

## 4. Solution Strategy

| Problem | Decision | Rationale |
|---------|----------|-----------|
| Anomaly detection without blocking ingestion | Async worker via Redis queue | Span is stored immediately; Worker runs after via BRPOP |
| Tool called but not offered to agent | Deterministic binary check against available_tools list | No embedding needed; 100% precision |
| Better tool existed for the prompt | spaCy lemma containment guard → embedding ranking | Containment guard short-circuits before embedding; rank > 1 → flag |
| Tool invoked on social/phatic prompt | 4-gate filter: token length, NER, action verbs, centroid similarity | Conservative: all four gates must pass; social centroid pre-computed |
| Wrong arguments passed | Output-error-priority path first; fallback to hybrid (50/50 cosine + BOW) scoring | Error patterns in tool_output are high-confidence; embedding for grounding check |
| Tool-call format parsing error | Model-format registry (TOOL_CALL_REGISTRY) with per-model detect patterns | Eliminates false positives from embedding-based format detection |
| No tool called when expected | Embed prompt against "call a function tool" reference | Lightweight single-embedding check; calibrated threshold |
| Response semantically unrelated to prompt | Embed prompt and response; flag if cosine similarity < threshold | Catches hallucination / topic drift at response level |
| Embedding computation decoupled from Worker | Separate embedder HTTP microservice | Worker Dockerfile no longer pre-bakes the model; embedder scales independently |
| Calibration per flag type | `calibrate.py --flag-type` + BINARY_FLAG_TYPES set | Each check method calibrated in isolation; binary flags skip numeric threshold sweep |
| Deep diagnosis | On-demand LLM call from dashboard — active in v1.2 | Expensive; only run when explicitly requested |
| LLM provider flexibility | Provider abstraction with lazy imports; env-var-driven selection | Only the selected provider SDK is imported at runtime; swap without code changes |
| Structured LLM output | Vendor tool/function calling enforced (no free-text parsing) | Anthropic tool_choice force, OpenAI strict=True, Ollama format= schema |
| Diagnosis fail-clean | assemble → diagnose → persist strictly in sequence | No DB row written unless LLM parse succeeds |
| Presenter ↔ Diagnosticer auth | Presenter forwards user bearer token to Diagnosticer | Shared SECRET_KEY validates JWT; no separate service auth mechanism |
| High-volume immutable span storage | ClickHouse | OLAP, append-only, proven at scale by competitors |
| Mutable relational data (flags, scores, diagnoses, tenants, auth) | PostgreSQL with RLS | Low volume, relational, row-level security for tenant isolation |
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
                  |                           |    |           ^             |
                  v                           |    v           |             v
            +---------+                       |  +----------+  |       +---------+
            |ClickHouse|                      |  | Embedder |  |       |Presenter|
            +---------+                       |  +----------+  |       +---------+
                  |                           v                |             |
                  v                     +----------+     +----------+        v
            +--------+                  |ClickHouse|     |  Scores  |  +-------------+
            |  S3    |<-----------------+----------+     +----------+  | Diagnosticer|---> LLM
            +--------+                                                 +-------------+
```

### 5.2 Component Descriptions

**SDK** (`sdk/xeter_sdk/`)
- `@xeter.trace` decorator captures all span fields at decoration time
- Sends spans fire-and-forget from a background daemon thread (zero added latency)
- `XETER_ENDPOINT` and `XETER_API_KEY` configured via environment variables
- Language: Python 3.12+

**Analyser** (`xeter/services/analyser/`)
- FastAPI app; single endpoint: POST /v1/spans
- Ingestion path (locked sequence): authenticate API key → upload large fields to S3 → batch span row into ClickHouse → LPUSH span_id to Redis
- Manages long-lived singletons via FastAPI lifespan: SpanBatcher, Redis client, S3Client
- SpanBatcher flushes every 5 seconds or when batch reaches threshold

**Embedder** (`services/embedder/`)
- Standalone HTTP microservice; exposes POST /encode and POST /similarity
- Hosts all-MiniLM-L6-v2 (sentence-transformers) — pre-baked into its own Docker image
- Extracted from Worker in v1.1: Worker Dockerfile no longer contains the model
- Worker calls EmbedderClient (httpx-based HTTP client) for all embedding operations

**Worker** (`xeter/services/worker/`)
- Standalone BRPOP consumer; runs as a separate Docker service
- Loop: BRPOP span_id → fetch span from ClickHouse → fetch `available_tools` from S3 → run all registered analyzers → write scores + flags to PostgreSQL
- ToolCallAnalyzer runs 7 checks in sequence; all scores logged before threshold comparison
- SIGTERM handled via `running` flag + BRPOP timeout=2s

**ToolCallAnalyzer** — 7 check methods (v1.1):

| Check | Flag type | Detection strategy |
|-------|-----------|-------------------|
| `_check_tool_not_available` | `tool_not_available` | Deterministic: tool called but no list (WTOOL-03) or tool absent from list |
| `_check_wrong_tool_choice` | `wrong_tool_called` | spaCy lemma containment guard → embedding ranking; flags if rank > 1 and top tool is coherent |
| `_check_unnecessary_tool_call` | `unnecessary_tool_call` | 4-gate filter: token length ≤ 20, no NER entities, no action verbs, social centroid similarity ≥ threshold |
| `_check_wrong_args` | `wrong_tool_args` | Output-error-priority path first; then hybrid (50/50 cosine + BOW) scoring per argument value |
| `_check_no_tool` | `no_tool_used` | Embed prompt vs "call a function tool" reference; flag if similarity > threshold |
| `_check_parsing_error` | `parsing_error` | Model-format registry (TOOL_CALL_REGISTRY): per-model detect patterns for api_structured and raw_text transports |
| `_check_response_anomaly` | `response_anomaly` | Cosine similarity between prompt and response embeddings; flag if below threshold |

**Presenter** (`xeter/services/presenter/`)
- FastAPI app; REST API consumed by View
- GET /spans — paginated span list with flag indicators and filters
- GET /spans/{id} — span detail with parallel ClickHouse + PostgreSQL queries; lazy S3 payload fetch
- POST /login / POST /register
- POST /diagnose — triggers diagnosis via DiagnosisService; forwards bearer token to Diagnosticer
- GET /diagnose/{span_id} — returns latest diagnosis for a span from PostgreSQL

**DiagnosisService** (`xeter/services/presenter/diagnosis_service.py`)
- Service layer instantiated per request inside the diagnose router
- `trigger()`: ClickHouse span ownership guard → httpx POST to Diagnosticer with auth header forwarding → re-read result from PostgreSQL (never parses HTTP response body)
- Error classification: `TimeoutException` → 504, `ConnectError/HTTPError` → 503, non-2xx → 502 (sanitised detail, 120-char cap)
- Re-diagnosis always overwrites — no idempotency; `diagnoses` table is append-only so history is preserved

**Diagnosticer** (`xeter/services/diagnosticer/`)
- Separate FastAPI service on port 8001
- POST /diagnose — real endpoint (replaces 501 scaffold from v1.0)
- Fail-clean pipeline: `assemble_context()` → `provider.diagnose()` → `DiagnosisRepository.create()` — DB row written only on LLM success
- Error mapping: `ValueError` (span not found) → 404, `LLMError` (provider failure) → 502, `ParseError` (bad structured output) → 422

**LLM Provider Factory** (`xeter/services/diagnosticer/providers/`)
- `get_llm_client()` — lazy imports; only selected provider SDK loaded at runtime
- `AnthropicProvider` — AsyncAnthropic + forced tool_choice; iterates all content blocks
- `OpenAIProvider` — AsyncOpenAI + function calling strict=True
- `OllamaProvider` — ollama.AsyncClient + Pydantic-generated format= schema
- All providers return typed `DiagnosisResult(verdict, severity, affected_field, fix)` — no free-text parsing

**Context Assembly** (`xeter/services/diagnosticer/context_assembly.py`)
- `assemble_context(span_id, tenant_id)` → `(context_string, trace_id)`
- Parallel fetch: ClickHouse span (via `asyncio.to_thread`) + PostgreSQL flags (via `tenant_session()`) + S3 prompt/response (via `asyncio.gather` with 5s timeout)
- S3 timeout substitutes `[S3 fetch timed out]` — LLM can still diagnose from tool metadata and flag data

**View** (`services/view/`)
- Next.js 15 app; no business logic
- Auth store: JWT token in memory
- Span list, FilterBar, span detail Sheet with FlagSection, PayloadTabs, and DiagnosisCard
- FlagSection: auto-loads prior diagnosis via GET /diagnose/{span_id} on mount (404 suppressed); Diagnose button always enabled; `key={spanId}` forces remount on span change

**Storage:**
- **ClickHouse** — spans (immutable, append-only)
- **PostgreSQL** — flags, span_scores, diagnoses, tenants, users, api_keys
- **S3 (MinIO)** — prompt, response, raw_response, available_tools

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
    | ToolCallAnalyzer (7 checks in sequence):
    |
    |   _check_tool_not_available:
    |     if no available_tools → flag tool_not_available (binary, score=1.0)
    |     if tool not in list   → flag tool_not_available (binary, score=1.0)
    |
    |   _check_wrong_tool_choice:
    |     spaCy lemma containment guard (short-circuit if match)
    |     embed prompt → EmbedderClient.encode()
    |     embed each tool (name + description) → rank by cosine similarity
    |     if rank > 1 AND top score ≥ tool_coherence_threshold → flag wrong_tool_called
    |
    |   _check_unnecessary_tool_call:
    |     gate 1: token count ≤ 20  (spaCy)
    |     gate 2: no NER entities   (spaCy)
    |     gate 3: no action verbs   (spaCy + ACTION_VERBS set)
    |     gate 4: centroid similarity ≥ unnecessary_tool_call threshold
    |     → flag unnecessary_tool_call
    |
    |   _check_wrong_args:
    |     if tool_output contains error pattern → flag immediately (output-error path)
    |     else: for each argument value:
    |       skip numeric / boolean / SQL / multiline values
    |       check substring containment in prompt (stripped)
    |       compute hybrid_score(cosine, bow) → flag if < wrong_tool_args threshold
    |
    |   _check_no_tool:
    |     embed prompt vs "call a function tool"
    |     if score > no_tool_used threshold → flag no_tool_used
    |
    |   _check_parsing_error:
    |     look up agent_model in TOOL_CALL_REGISTRY
    |     api_structured: parse JSON, run detect patterns, validate argument field type
    |     raw_text: run detect regex patterns against raw_response
    |     → flag parsing_error if format mismatch
    |
    |   _check_response_anomaly:
    |     embed prompt and response independently
    |     if cosine similarity < response_anomaly threshold → flag response_anomaly
    |
    |-- INSERT rows into span_scores — one row per comparison, always
    └-- INSERT rows into flags — only for spans where at least one Flag returned
```

### 6.3 Data Flow — Read Path

```
View
    |-- GET /spans?flag_type=wrong_tool_called&agent_name=...&from_time=...
    |       Presenter: SELECT spans FROM ClickHouse + LEFT JOIN flags FROM PostgreSQL
    |       Returns: paginated list with status + score overlay
    |
    |-- GET /spans/{id}
    |       Presenter: parallel queries ClickHouse + PostgreSQL
    |       Then: asyncio.gather → fetch prompt/response/raw_response from S3
    |       Returns: full span detail with lazy-loaded payloads
    |
    |-- GET /diagnose/{span_id}
    |       Presenter → DiagnosisRepository.get_latest_for_span()
    |       Returns: DiagnosisResponse or 404 if no prior diagnosis
    |
    └-- POST /diagnose
            Presenter → DiagnosisService.trigger()
              → ClickHouse ownership guard (tenant validation)
              → httpx POST /diagnose to Diagnosticer (bearer token forwarded)
              → DiagnosisRepository.get_latest_for_span() (re-read from DB)
            Returns: DiagnosisResponse
```

### 6.4 Diagnostic Flow (v1.2 — active)

```
View
    |-- POST /diagnose  →  Presenter (DiagnosisService.trigger())
    |       |
    |       |-- verify span belongs to tenant (ClickHouse lookup)
    |       |-- httpx POST /diagnose → Diagnosticer (with Authorization header)
    |       |
    |       Diagnosticer (POST /diagnose):
    |         |-- verify JWT (shared SECRET_KEY)
    |         |-- assemble_context(span_id, tenant_id):
    |         |     parallel: ClickHouse span + PostgreSQL flags + S3 prompt/response
    |         |-- provider.diagnose(context_string)  [Anthropic/OpenAI/Ollama]
    |         |-- DiagnosisRepository.create() — INSERT diagnoses row
    |         └── return 200 {verdict, severity, affected_field, fix}
    |
    |       Presenter:
    |         |-- DiagnosisRepository.get_latest_for_span() (re-read from DB)
    |         └── return DiagnosisResponse to View
    |
    └── View renders DiagnosisCard (verdict badge, severity badge, field, fix, timestamp)
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
│    embedder    (port 8002)  ◀────────────┘ (standalone) │
│    analyser    (port 4318)  ◀────────────┤ all infra    │
│    worker      (no port)    ◀────────────┤ all infra    │
│                             ◀── embedder               │
│    presenter   (port 8000)  ◀────────────┤ all infra    │
│    diagnosticer(port 8001)  ◀────────────┤ postgres     │
│    view        (port 3000)  ◀── presenter, analyser     │
└─────────────────────────────────────────────────────────┘
```

### 7.2 Service Configuration

| Service | Image | Key Environment Variables |
|---------|-------|--------------------------|
| embedder | custom (pre-bakes all-MiniLM-L6-v2) | (standalone; no external deps) |
| analyser | python:3.12-slim (xeter package) | DATABASE_URL, CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD, REDIS_URL, S3_* |
| worker | python:3.12-slim (xeter package) | DATABASE_URL, CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD, REDIS_URL, S3_*, EMBEDDER_URL, WORKER_THRESHOLD_* |
| presenter | python:3.12-slim (xeter package) | DATABASE_URL, CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD, JWT_SECRET, S3_*, DIAGNOSTICER_URL |
| diagnosticer | python:3.12-slim (xeter package) | DATABASE_URL, CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD, SECRET_KEY, S3_*, DIAGNOSTICER_PROVIDER, DIAGNOSTICER_MODEL, ANTHROPIC_API_KEY, OPENAI_API_KEY |
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
| Embedder | 8002 |
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

The `diagnoses` table follows the same RLS pattern as `flags`: `tenant_isolation` policy on `tenant_id`, enforced via `tenant_session()`.

Exception: `span_scores` table has no RLS policy (Worker connects as BYPASSRLS role). Tenant isolation there is enforced via explicit `WHERE tenant_id = :tenant_id` in all Presenter queries. This is documented with a CRITICAL comment in the codebase.

### 8.2 Authentication and Authorization

**SDK ingestion (Analyser):**
- API key per tenant; key has `xtr_` prefix for identification
- Analyser stores bcrypt hash; plaintext key returned once at registration

**Dashboard (Presenter):**
- Email/password login; bcrypt hash stored in PostgreSQL
- POST /login returns a JWT signed with `JWT_SECRET`

**Diagnosticer service auth:**
- Presenter forwards the user's `Authorization: Bearer <token>` header to Diagnosticer
- Diagnosticer validates the JWT using the shared `SECRET_KEY` environment variable (same as Presenter's `JWT_SECRET`)
- No separate service-to-service auth mechanism — bearer token forwarding is sufficient for v1.2

**Future (v2+):** Clerk migration for multi-member tenants / SSO.

### 8.3 Data Model

Three stores. Spans are immutable once written. Flags, scores, and diagnoses are separate append-only tables in PostgreSQL, referenced by `span_id`.

**ClickHouse — spans table** (unchanged from v1.0)

`ORDER BY (tenant_id, trace_id, time_begin)`

| Field | Type | Notes |
|-------|------|-------|
| tenant_id | String | Required for tenant isolation |
| trace_id | String | Groups spans into one session |
| span_id | String | Unique per row |
| parent_span_id | String / null | |
| time_begin | DateTime64 | |
| time_end | DateTime64 | |
| agent_name | String | |
| agent_model | String | |
| recipient | String | |
| recipient_model | String / null | |
| tool_name | String / null | |
| tool_description | String / null | |
| tool_arguments | String / null | Inline JSON |
| tool_output | String / null | |
| available_tools_ref | String / null | S3 key |
| prompt_ref | String | S3 key |
| response_ref | String | S3 key |
| raw_response_ref | String | S3 key |
| schema_version | String | Always "1.0" |

**PostgreSQL — flags table**

`flag_type` values in v1.1+: `tool_not_available`, `wrong_tool_called`, `unnecessary_tool_call`, `wrong_tool_args`, `no_tool_used`, `parsing_error`, `response_anomaly`.

| Field | Type | Notes |
|-------|------|-------|
| flag_id | UUID | Primary key |
| tenant_id | String | RLS policy |
| span_id | String | |
| trace_id | String | Denormalised |
| flag_type | VARCHAR | Open string; not an enum |
| score | Float | |
| detail | JSONB | Always includes "metric" key |
| created_at | Timestamp | |

**PostgreSQL — span_scores table** (unchanged from v1.0)

One row per embedding comparison per span, regardless of whether a flag was written.

| Field | Type | Notes |
|-------|------|-------|
| score_id | UUID | |
| tenant_id | String | No RLS; explicit WHERE |
| span_id | String | |
| comparison | VARCHAR | metric name |
| score | Float | |
| created_at | Timestamp | |

**PostgreSQL — diagnoses table** (new in v1.2, migration 003)

One row per diagnosis call. Append-only — re-diagnosis writes a new row; `get_latest_for_span()` orders by `created_at DESC` to return the most recent.

| Field | Type | Notes |
|-------|------|-------|
| diagnosis_id | UUID | Primary key |
| tenant_id | String | RLS policy (tenant_isolation) |
| span_id | String | References spans in ClickHouse |
| trace_id | String | Denormalised from ClickHouse |
| verdict | VARCHAR | String, not enum — `model`, `architecture`, `prompt`, or `unknown` |
| severity | VARCHAR | String, not enum — `low`, `medium`, `high` |
| affected_field | TEXT | e.g. `tool_description`, `prompt`, `tool_arguments` |
| fix | TEXT | Recommended fix from LLM |
| provider | VARCHAR | `anthropic`, `openai`, `ollama` |
| model | VARCHAR | Model name used for this diagnosis |
| created_at | Timestamp | |
| updated_at | Timestamp | |

### 8.4 Embedding and Detection Strategy

Embedding model: **all-MiniLM-L6-v2**, hosted by the **Embedder microservice** (HTTP). Worker delegates all encode/similarity calls to EmbedderClient.

**NLP:** spaCy `en_core_web_md` — used for dependency parsing (clause extraction), NER (entity detection), and lemmatization (containment guard). Lazy-loaded on first use.

| Check | Strategy | Signal type | Calibrated P/R |
|-------|----------|-------------|----------------|
| `tool_not_available` | Deterministic list lookup | Binary | P=1.0, R=1.0 |
| `wrong_tool_called` | spaCy containment guard + embedding rank | Rank-based | P=1.0, R=0.5 |
| `unnecessary_tool_call` | 4-gate filter + social centroid similarity | Threshold (0.25) | P=1.0, R=0.667 |
| `wrong_tool_args` | Output-error path OR hybrid (50/50 cosine+BOW) | Threshold (0.10) | P=0.882, R=0.484 |
| `no_tool_used` | Prompt vs reference embedding | Threshold (0.15) | P=1.0, R=0.333 |
| `parsing_error` | Model-format registry (regex detect patterns) | Binary | P=1.0, R=0.8 |
| `response_anomaly` | Prompt vs response cosine similarity | Threshold (0.10) | P=0.818, R=0.8 |

**Threshold calibration:** `calibrate.py --flag-type <type>` generates a P/R curve per flag type. Results stored in `fixtures/calibrated_thresholds.json`. All scores logged to `span_scores` before threshold comparison (calibration-first invariant).

**Social centroid:** Pre-computed centroid embedding of social/phatic prompts, stored in `fixtures/social_centroid.npy`. Loaded once at Worker startup. Falls back to gate-1/2/3 only if file is absent.

**Hybrid scoring** (`base.py`): `bow_score()` = Jaccard token overlap; `hybrid_score(cosine, bow, weight=0.5)` = 50/50 blend. Used by `_check_wrong_args` to combine embedding grounding with lexical overlap.

### 8.5 Error Handling

- **Embedding fails:** span already stored; no flag/score rows written; failure logged.
- **S3 fetch of available_tools_ref fails:** wrong-tool checks skipped; other comparisons proceed.
- **Worker "span not found":** retries up to 3 times with 5s/10s backoff.
- **Embedder unreachable:** Worker logs error; span processed without flags/scores.
- **Unknown agent_model in TOOL_CALL_REGISTRY:** parsing_error flag written with score=0.0 and "Unknown model" detail.
- **Diagnosticer unreachable:** Presenter DiagnosisService catches `httpx.ConnectError` → 503; `httpx.TimeoutException` → 504; non-2xx response → 502 (sanitised Diagnosticer error detail, 120-char cap).
- **Diagnosticer span not found:** `assemble_context()` raises `ValueError` → 404.
- **LLM provider failure:** `LLMError` → 502.
- **LLM bad structured output:** `ParseError` → 422.
- **S3 payload fetch times out (Diagnosticer context assembly):** `asyncio.wait_for` (5s) → substitutes `[S3 fetch timed out]`; LLM can still diagnose from tool metadata and flag data.
- **S3 payload fetch times out (Presenter span detail):** `asyncio.wait_for` → 504 to View.

### 8.6 Observability of Xeter Itself

Structured logging via `structlog` across all services. No self-monitoring dashboard in v1.

---

## 9. Architecture Decisions

| ID | Decision | Status | Rationale |
|----|----------|--------|-----------|
| AD01 | Async flagging | Decided | Span ingestion must not be blocked by embedding computation |
| AD02 | Diagnosticer as separate service | Decided | LLM calls are slow and on-demand; isolation allows independent scaling |
| AD03 | Split storage (ClickHouse + PostgreSQL + S3 + Redis) | Decided | Each store chosen for its workload |
| AD04 | View has no logic | Decided | All logic centralised in backend services |
| AD05 | LLM backend configurable | Decided | Data sovereignty requirements in B2B |
| AD06 | Multi-tenant architecture | Decided | B2B SaaS requirement |
| AD07 | Span storage: ClickHouse | Decided | High-volume, append-only, immutable rows |
| AD08 | Flags and scores storage: PostgreSQL | Decided | Low-volume, mutable, relational |
| AD09 | Large payload storage: S3 | Decided | prompt, response, raw_response, available_tools stored in S3 |
| AD10 | Spans are immutable; flags/scores are separate tables | Decided | Eliminates ClickHouse mutation cost |
| AD11 | Presenter merges ClickHouse + PostgreSQL at read time | Decided | Two parallel queries per span view |
| AD12 | Ingestion queue: Redis BRPOP | Decided | Decouples ingestion from embedding worker |
| AD13 | Presenter protocol: REST only (v1) | Decided | SSE deferred |
| AD14 | Auth: API key + bcrypt (SDK); email/password + bcrypt + JWT (dashboard) | Decided | Zero external auth dependency in v1 |
| AD15 | SDK primary language: Python | Decided | Python powers ~80% of AI agent implementations |
| AD16 | SDK secondary language: TypeScript | Decided | Deferred to v1.3+ |
| AD17 | Backend services language: Python | Decided | Analyser and Worker require embedding libraries that are Python-native |
| AD18 | TypeScript SDK will lag Python SDK by one release cycle | Decided | Single maintainer |
| AD19 | `available_tools` stored in S3, reference key in ClickHouse | Decided | Tool lists can be large |
| AD20 | `tool_arguments` stored inline as JSON in ClickHouse | Decided | Arguments are typically small key-value objects |
| AD21 | Embedding model: all-MiniLM-L6-v2 | Decided | Lightweight (80MB), fast CPU inference |
| AD22 | bcrypt used directly (not passlib) | Decided | passlib 1.7.4 incompatible with Python 3.14 + current bcrypt |
| AD23 | `wrong_tool_args` excluded from single P/R sweep | Decided | Uses hybrid scoring with output-error priority path; calibrated independently |
| AD24 | Worker BRPOP retry with backoff | Decided | ClickHouse SpanBatcher flushes every 5s; race condition possible |
| AD25 | `span_scores` has no PostgreSQL RLS | Decided | Worker connects as BYPASSRLS role; explicit WHERE tenant_id in Presenter |
| AD26 | Embedder extracted as a separate HTTP microservice | Decided | Worker Dockerfile no longer pre-bakes the model; embedder scales independently; clean separation of ML serving from business logic |
| AD27 | spaCy `en_core_web_md` integrated into Worker | Decided | Dependency parsing for clause extraction, NER for entity-aware containment guard, lemmatization for stemmed overlap — richer signal than pure embedding for short prompts |
| AD28 | `_check_wrong_tool` split into three distinct checks | Decided | Original single check conflated three structurally different cases: (1) tool absent from list, (2) wrong choice among available tools, (3) no tool should have been called. Each case has different evidence and precision target |
| AD29 | `tool_not_available` is a deterministic binary check | Decided | No embedding needed; either the tool is in the list or it isn't; P=1.0, R=1.0 by construction |
| AD30 | `_check_wrong_tool_choice` uses spaCy lemma containment guard before embedding | Decided | Prevents false positives when the prompt explicitly names the called tool; containment match is a high-confidence signal that the tool choice is correct |
| AD31 | `_check_unnecessary_tool_call` uses 4-gate filter + social centroid | Decided | Conservative stacking prevents false positives; social centroid pre-computed from `social_prompts.txt` to avoid per-span reference embedding |
| AD32 | `_check_wrong_args` uses output-error-priority path before embedding | Decided | Error patterns in tool_output are high-confidence (explicit API rejection); embedding grounding is a weaker secondary signal — more reliable to prioritise the explicit evidence |
| AD33 | Hybrid scoring (50/50 cosine + BOW) for `_check_wrong_args` | Decided | Pure cosine is unreliable for short argument values; BOW (Jaccard) adds lexical anchoring; blend improves recall without sacrificing precision |
| AD34 | `_check_parsing_error` replaced by model-format registry | Decided | Original embedding of `model_name + prompt` vs response was a category error — parsing errors are structural, not semantic. Registry with per-model detect patterns gives deterministic detection at zero embedding cost |
| AD35 | String (not PG enum) for `verdict` and `severity` in diagnoses table | Decided | Avoids migration pain when adding new verdict/severity values; consistent with FLAG-03 rationale applied to flag_type |
| AD36 | `diagnoses` table distinct from legacy `diagnostics` placeholder | Decided | Both tables coexist; neither modifies the other. New diagnoses table has full 12-column output schema; placeholder left untouched |
| AD37 | Lazy imports in `get_llm_client()` provider factory | Decided | Only the selected provider SDK is imported at runtime — avoids ImportError when a provider SDK is not installed in the environment |
| AD38 | Structured LLM output via vendor tool/function calling | Decided | Anthropic: forced tool_choice; OpenAI: strict=True function calling; Ollama: Pydantic-generated format= schema. No free-text parsing eliminates a failure mode |
| AD39 | Fail-clean pipeline in Diagnosticer | Decided | `assemble_context` → `provider.diagnose` → `DiagnosisRepository.create` strictly in order; no DB row written unless LLM parse succeeds. Prevents phantom diagnosis rows from failed calls |
| AD40 | Presenter re-reads from DB after Diagnosticer write | Decided | DiagnosisService does not parse the Diagnosticer HTTP response body — it re-reads the row from PostgreSQL after a successful call. Presenter owns the response schema; Diagnosticer owns the DB write |
| AD41 | Auth token forwarding from Presenter to Diagnosticer | Decided | Presenter forwards the user's bearer token to Diagnosticer; both services share SECRET_KEY. No separate service-to-service auth in v1.2 — simple and sufficient for single-tenant deployment |
| AD42 | getDiagnosis 404 suppressed silently in frontend | Decided | A span with no prior diagnosis is the normal initial state, not an error. Surfacing a 404 to the user would be confusing |
| AD43 | Re-diagnosis always overwrites — no idempotency in POST /diagnose | Decided | Presenter removed the idempotency cache-hit check. Every Diagnose button click triggers a fresh LLM call. The `diagnoses` table is append-only so prior diagnoses are preserved as history |

---

## 10. Quality Requirements

### 10.1 Quality Scenarios

| ID | Quality Scenario | Expected Response |
|----|-----------------|-------------------|
| QS01 | Correctness | Span where prompt is "schedule a meeting" and `tool_name` is "get_weather" | `wrong_tool_called` flag; rank and top_candidate in detail |
| QS02 | Correctness | Span where tool use matches prompt semantically | No flag; similarity scores logged in span_scores |
| QS03 | Performance | High volume of spans ingested continuously | Spans stored without delay; flagging completes asynchronously |
| QS04 | Availability | LLM provider unreachable | Diagnosticer returns 502; existing flag/span data unaffected |
| QS05 | Isolation | Tenant A queries spans | Tenant B's data never returned; enforced by RLS + explicit WHERE |
| QS06 | Correctness | Span where tool_output contains "invalid argument" | `wrong_tool_args` flag via output-error path; no embedding computed |
| QS07 | Correctness | Span where called tool is not the top-ranked match in available_tools (and lemma containment fails) | `wrong_tool_called` flag with ranked candidate list in detail |
| QS08 | Correctness | Span where prompt is "thanks!" and any tool is called | `unnecessary_tool_call` flag after all four gates pass |
| QS09 | Correctness | Span where `available_tools` is None and a tool is called | `tool_not_available` flag, score=1.0, no embedding computed |
| QS10 | Correctness | Span where raw_response format does not match the model's registered format | `parsing_error` flag with format mismatch detail |
| QS11 | Correctness | Span where prompt and response are semantically unrelated | `response_anomaly` flag with cosine score |
| QS12 | Correctness | Developer clicks Diagnose on a flagged span | DiagnosisCard renders verdict, severity, affected field, and fix within LLM response time |
| QS13 | Configurability | Operator sets DIAGNOSTICER_PROVIDER=ollama in docker-compose | Diagnosticer uses Ollama without code change; only selected provider SDK imported |

---

## 11. Risks and Technical Debt

| ID | Risk | Impact | Status | Mitigation |
|----|------|--------|--------|------------|
| R01 | ClickHouse operational complexity | Medium | Open | Use managed ClickHouse Cloud for SaaS deployment |
| R02 | Cross-store query latency | Low-Medium | Accepted | Presenter parallelises the two queries |
| R03 | Embedding threshold calibration | High | Mitigated | Per-method calibration via `calibrate.py --flag-type`; `calibrated_thresholds.json` tracks P/R per flag type |
| R04 | Auth security | Low | Resolved | API key + bcrypt (SDK); email/password + bcrypt + JWT (dashboard) |
| R05 | agent_model / recipient_model inference | Low | Open | SDK passes these as explicit parameters; no inference in v1 |
| R06 | S3 payload retrieval strategy | Medium | Resolved | Lazy loading; `asyncio.wait_for` with timeout in both Presenter and Diagnosticer |
| R07 | LLM provider cost and rate limits | Medium | Open | On-demand only (not automatic); Ollama option for local inference; no rate-limit handling in v1.2 |
| R08 | Dual SDK maintenance (Python + TypeScript) | Medium | Deferred | TypeScript SDK deferred to v1.3+ |
| R09 | available_tools not captured by SDK | High | Resolved | SDK captures `available_tools` via `tools_arg` parameter |
| R10 | wrong_tool_args false-positive rate | Medium | Mitigated | Output-error path is high-precision; hybrid scoring for grounding path; P=0.882 at calibrated threshold |
| R11 | span_scores has no RLS | Medium | Accepted | Documented with CRITICAL comment; explicit WHERE tenant_id in Presenter |
| R12 | Embedder microservice is a single point of failure for all embedding-based checks | Medium | Accepted | Worker logs error and skips flag/score writes when embedder is unreachable; span data is preserved; embedder can be restarted independently |
| R13 | spaCy model download at Worker startup | Low | Resolved | `en_core_web_md` pre-baked into Worker Dockerfile; lazy-loaded at first use |
| R14 | Social centroid must be rebuilt if social_prompts.txt changes | Low | Open | Centroid rebuild is a one-off script run; current file is stable; fallback to gates 1–3 if file absent |
| R15 | `wrong_tool_called` recall is low (R=0.5) | Medium | Accepted | Conservative by design — precision target ≥ 80%; LLM-based diagnosis (now active) can surface root cause for missed heuristic cases |
| R16 | Diagnosticer auth uses shared SECRET_KEY | Low | Accepted | Single-tenant deployment; shared key is practical. Multi-tenant SaaS will require service-to-service auth (e.g. HMAC or mTLS) before cloud deployment |
| R17 | LLM context assembly latency | Medium | Accepted | Parallel S3 + flag fetches with 5s timeout mitigate P99; end-to-end diagnosis time depends on LLM provider response time |

---

## 12. Glossary

| Term | Definition |
|------|------------|
| Span | A single recorded unit of agent execution, one immutable row in ClickHouse |
| Trace | A group of spans sharing the same trace_id, representing one agent session |
| Root span | A span with parent_span_id = null |
| Flag | A row in the PostgreSQL flags table written by the Worker, indicating a detected anomaly |
| Score | A row in the PostgreSQL span_scores table; logged for every span regardless of flagging |
| Diagnosis | A row in the PostgreSQL diagnoses table written by the Diagnosticer; stores LLM root-cause result |
| DiagnosisResult | Typed dataclass returned by all LLM providers: verdict, severity, affected_field, fix |
| DiagnosisCard | React sub-component in SpanDetailPanel rendering verdict/severity badges, field, fix, and relative timestamp |
| Analyser | Service responsible for receiving spans, storing them, and enqueuing span_ids to Redis |
| Embedder | Standalone HTTP microservice hosting all-MiniLM-L6-v2; exposes /encode and /similarity |
| EmbedderClient | httpx-based HTTP client in the Worker that delegates all encoding/comparison to the Embedder service |
| Worker | BRPOP consumer; fetches spans, runs ToolCallAnalyzer, writes scores and flags to PostgreSQL |
| ToolCallAnalyzer | Concrete analyzer with 7 check methods, each targeting a distinct tool-call failure mode |
| Diagnosticer | Separate service for LLM-based trace analysis; fully active in v1.2 |
| DiagnosisService | Presenter service layer that triggers Diagnosticer, classifies HTTP errors, and re-reads result from DB |
| Presenter | Backend API layer that merges ClickHouse + PostgreSQL + S3 data before serving View |
| View | Next.js 15 frontend dashboard; no business logic |
| SpanBatcher | In-process buffer in Analyser that accumulates rows and flushes to ClickHouse in batches |
| BRPOP | Redis blocking right-pop; used by Worker to consume span_ids from `analysis_queue` |
| social centroid | Pre-computed mean embedding of social/phatic prompts; used as similarity reference in `_check_unnecessary_tool_call` |
| containment guard | spaCy lemma-set overlap check that short-circuits `_check_wrong_tool_choice` when the prompt names the called tool |
| hybrid_score | 50/50 weighted blend of cosine similarity and BOW (Jaccard) token overlap; used in `_check_wrong_args` |
| bow_score | Jaccard token overlap between two strings; BOW component of hybrid_score |
| calibration-first invariant | All similarity scores must be logged via log_score() before any threshold comparison, ensuring non-flagged spans contribute to the calibration dataset |
| TOOL_CALL_REGISTRY | Per-model registry mapping agent_model strings to tool-call format metadata and detect patterns |
| output-error path | Branch of `_check_wrong_args` that flags immediately when tool_output contains an error pattern, before any embedding computation |
| fail-clean pipeline | Diagnosticer pipeline pattern: context assembly → LLM call → DB persist, strictly in order; DB row only written on LLM success |
| assemble_context | Diagnosticer function that fetches span + flags + S3 payloads in parallel and formats them into a single LLM prompt string |
| get_llm_client | Provider factory with lazy imports; returns the configured LLM provider based on DIAGNOSTICER_PROVIDER env var |
| tool_not_available | Flag type: called tool was absent from available_tools or no list was provided |
| wrong_tool_called | Flag type: a better tool existed among available tools (rank > 1, coherent top match) |
| unnecessary_tool_call | Flag type: tool invoked on a social/phatic prompt that warranted no tool use |
| wrong_tool_args | Flag type: tool arguments are semantically unrelated to the prompt or contain error-evidenced violations |
| no_tool_used | Flag type: prompt implies tool use but no tool was called |
| parsing_error | Flag type: raw_response format does not match the model's registered tool-call format |
| response_anomaly | Flag type: prompt and response are semantically unrelated by cosine similarity |
| MissingTenantError | Python exception raised by the DAL before any DB call when tenant_id is absent |
| tenant_session() | PostgreSQL session context that sets `app.current_tenant_id` for RLS policy enforcement |

---

Document status: v1.2 — post-implementation. Diagnosticer milestone complete. Open items: TypeScript SDK (v1.3+), cloud deployment, wrong_tool_called recall improvement, LLM rate-limit handling, service-to-service auth for multi-tenant SaaS.

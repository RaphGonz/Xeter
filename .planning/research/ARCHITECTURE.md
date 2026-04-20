# Architecture Research

**Domain:** LLM Diagnosticer integration into Xeter observability platform
**Researched:** 2026-04-20
**Confidence:** HIGH — based on direct codebase inspection, no external sources required

---

## System Overview

### Current Architecture (v1.1)

```
SDK (Python)
    |
    | POST /ingest (OTel spans)
    v
┌─────────────────────────────────────────────────────────────┐
│                      Analyser  :4318                         │
│  batch.py (5s flush to ClickHouse)                           │
│  s3.py    (large payloads → MinIO)                           │
│  queue.py (enqueue span_id → Redis)                          │
└────────────────────────┬────────────────────────────────────┘
                         |
                   Redis LPUSH/BRPOP
                         |
                         v
┌─────────────────────────────────────────────────────────────┐
│                  Worker (Python daemon)                       │
│  span_fetcher.py  (ClickHouse + S3 resolution)               │
│  tool_call_analyzer.py (5 heuristic checks)                  │
│  flag_writer.py   (INSERT INTO flags)                        │
│  score_writer.py  (INSERT INTO span_scores)                  │
└─────────────────────────────────────────────────────────────┘

                  ┌──────────────┐
                  │  PostgreSQL  │  flags, span_scores,
                  │              │  diagnostics, tenants,
                  │   (RLS on)   │  users, api_keys
                  └──────────────┘

                  ┌──────────────┐
                  │  ClickHouse  │  spans (OLAP, append-only)
                  └──────────────┘

                  ┌──────────────┐
                  │    MinIO     │  large payloads (prompt,
                  │    (S3)      │  response, available_tools)
                  └──────────────┘

Browser (Next.js 15 View :3000)
    |
    | /api/* (Next.js route handlers proxy)
    v
┌─────────────────────────────────────────────────────────────┐
│                    Presenter  :8000                           │
│  GET  /spans            (ClickHouse + PG + S3)               │
│  GET  /spans/{span_id}  (ClickHouse + PG + S3)               │
│  POST /diagnose         (PROXY → Diagnosticer :8001)         │
│  POST /login            (JWT session)                        │
└─────────────────────────┬────────────────────────────────────┘
                          |
                    HTTP proxy (httpx.AsyncClient,
                    30s timeout, base_url=DIAGNOSTICER_URL)
                          |
                          v
┌─────────────────────────────────────────────────────────────┐
│               Diagnosticer  :8001  (scaffold → v1.2)         │
│  POST /diagnose  — currently returns 501                     │
│  has: DATABASE_URL, CLICKHOUSE_HOST, S3_ENDPOINT_URL         │
└─────────────────────────────────────────────────────────────┘
```

### Target Architecture (v1.2)

```
Browser
    |
    | POST /api/diagnose        GET /api/diagnose/{span_id}
    v
┌──────────────── Presenter :8000 ──────────────────────────┐
│  POST /diagnose  → proxy to Diagnosticer (unchanged)       │
│  GET  /diagnose/{span_id} → NEW: reads from PG diagnostics │
└────────────────────────────────────────────────────────────┘
                    |
            HTTP POST /diagnose
                    |
                    v
┌──────────────── Diagnosticer :8001 ───────────────────────┐
│  1. Validate request (span_id + tenant_id from JWT)        │
│  2. Fetch span from ClickHouse (reuse span_fetcher logic)  │
│  3. Fetch flags from PostgreSQL (RLS-scoped)               │
│  4. S3 payloads already resolved in step 2                 │
│  5. Assemble LLM context                                   │
│  6. Call LLM provider (anthropic / openai / configurable)  │
│  7. Parse structured response                              │
│  8. INSERT INTO diagnostics (PostgreSQL, RLS-scoped)       │
│  9. Return diagnosis to Presenter                          │
└────────────────────────────────────────────────────────────┘
         |              |              |
    ClickHouse      PostgreSQL       MinIO
    (span data)     (flags +        (payloads)
                    diagnostics)
```

---

## Component Responsibilities

| Component | Responsibility | Status |
|-----------|----------------|--------|
| Diagnosticer | Accept POST /diagnose, fetch all context, call LLM, store result, return structured diagnosis | MODIFY (from 501 scaffold to real implementation) |
| Presenter /diagnose router | Proxy POST /diagnose to Diagnosticer; add GET /diagnose/{span_id} to retrieve stored results | MODIFY (add GET endpoint) |
| diagnostics table (PostgreSQL) | Store structured LLM diagnosis per span per tenant with RLS | ALREADY EXISTS (migration 001 created it; no schema migration needed) |
| DiagnosticRepository (DAL) | CRUD for diagnostics table, following existing DAL pattern | NEW |
| LLM provider abstraction | Provider-agnostic calling layer (Anthropic/OpenAI/stub); configured via DIAGNOSTICER_LLM_PROVIDER + DIAGNOSTICER_LLM_MODEL env vars | NEW |
| SpanDetailPanel (View) | Render stored diagnosis after "Request Diagnostic" button; replace raw status/message display | MODIFY |
| View /api/diagnose/[span_id] route handler | Proxy GET to Presenter for stored diagnosis retrieval | NEW |

---

## Data Flow Decision: Where Should PostgreSQL Write Happen?

### Option A — Diagnosticer writes directly to PostgreSQL (RECOMMENDED)

```
View → Presenter (proxy) → Diagnosticer → [LLM] → PostgreSQL (diagnostics)
                                        ↓
                               returns diagnosis in response body
Presenter returns response to View (diagnosis already stored)
```

**Rationale:**
- Diagnosticer already has DATABASE_URL, CLICKHOUSE_HOST, S3_ENDPOINT_URL in docker-compose.yml — the infra wiring was done in v1.0 anticipating exactly this
- The `diagnostics` table has RLS with `tenant_isolation` policy; Diagnosticer writing directly means the RLS guarantee lives in one place
- Consistent with Worker pattern: Worker also writes directly to PostgreSQL (flags, span_scores) without routing through Presenter
- Keeps Presenter as a pure read/auth/proxy layer (AD-02: Diagnosticer isolation for independent scaling)
- Simpler failure modes: if the LLM call fails, nothing is written; if the write fails, the response to Presenter fails cleanly

**Tradeoff:** Diagnosticer needs its own PostgreSQL async session wiring. This is low cost — `get_session` and `tenant_session` are already in `xeter/shared/db/` and importable.

### Option B — Diagnosticer returns result; Presenter stores it

```
View → Presenter (proxy) → Diagnosticer → [LLM]
                         ← returns diagnosis JSON
Presenter → PostgreSQL (diagnostics INSERT)
Presenter → View
```

**Why not:** Presenter becomes stateful and acquires business logic, violating AD-04. The Presenter router would need to know the DiagnosticRepository interface. Adds a second failure point (LLM call succeeds but PG write in Presenter fails). Presenter's httpx proxy is already a pass-through — adding write logic after pass-through creates an asymmetry with every other Presenter route.

**Decision: Option A.** Diagnosticer writes directly to PostgreSQL.

---

## New Components Required

### 1. DiagnosticRepository (DAL)

Location: `xeter/shared/dal/diagnostics.py`

Follows the existing DAL pattern exactly (see `api_keys.py`, `tenants.py`):
- `require_tenant(tenant_id)` guard as first line of every method
- `AsyncSession` dependency injection
- Methods needed: `create(tenant_id, span_id, trace_id, llm_backend, result)` → Diagnostic, `get_by_span(span_id, tenant_id)` → Diagnostic | None

The `Diagnostic` ORM model already exists in `xeter/shared/models.py`. No new model class needed.

### 2. LLM Provider Abstraction

Location: `xeter/services/diagnosticer/llm.py`

**Design: thin adapter protocol, not a framework.**

```python
class LLMProvider(Protocol):
    async def complete(self, system: str, user: str) -> str: ...

class AnthropicProvider:
    """Uses anthropic Python SDK. Model configurable via LLM_MODEL env var."""

class OpenAIProvider:
    """Uses openai Python SDK. Model configurable via LLM_MODEL env var."""

class StubProvider:
    """Returns a canned diagnosis. Used in tests and when LLM_PROVIDER=stub."""

def get_provider() -> LLMProvider:
    """Factory: reads DIAGNOSTICER_LLM_PROVIDER env var (anthropic|openai|stub)."""
```

Why a Protocol instead of ABC: Python Protocols are structurally typed — stub/test providers don't need to import from `llm.py`. Keeps test setup clean.

Environment variables (added to docker-compose.yml diagnosticer service):
- `DIAGNOSTICER_LLM_PROVIDER` — `anthropic` | `openai` | `stub`
- `DIAGNOSTICER_LLM_MODEL` — model string (e.g. `claude-3-5-haiku-20241022`, `gpt-4o-mini`)
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` — provider credential

### 3. Context Assembler

Location: `xeter/services/diagnosticer/context.py`

Builds the structured LLM prompt from a SpanData + list of Flag records. Returns `(system_prompt: str, user_prompt: str)`.

The context assembler is pure Python (no I/O) — easy to unit-test in isolation. The system prompt encodes the diagnosis schema: verdict (model_error | architecture_error | prompt_error), severity (low | medium | high), affected_field, recommended_fix.

### 4. Diagnosis Schema (Pydantic)

Location: `xeter/services/diagnosticer/schemas.py`

```python
class DiagnosisResult(BaseModel):
    verdict: Literal["model_error", "architecture_error", "prompt_error"]
    severity: Literal["low", "medium", "high"]
    affected_field: str
    recommended_fix: str
    raw_llm_response: str  # stored for debugging; not shown in UI
```

The LLM response is parsed from JSON. The structured output is stored as `result` JSON in the `diagnostics` table.

### 5. Revised DiagnoseRequest Schema

The current scaffold `DiagnoseRequest` takes `span_id: str, flags: list`. This needs revision:

```python
class DiagnoseRequest(BaseModel):
    span_id: str
    tenant_id: str  # injected from JWT by Presenter before proxying
```

The Presenter's existing proxy router in `routers/diagnose.py` currently passes `body.model_dump()` verbatim to the Diagnosticer. Two options:

**Option A — Presenter injects tenant_id before proxying (RECOMMENDED):**
```python
# In Presenter diagnose router:
payload = {"span_id": body.span_id, "tenant_id": tenant_id}
resp = await http_client.post("/diagnose", json=payload)
```
This keeps tenant_id verified by JWT in Presenter (where the JWT verification lives) and avoids Diagnosticer needing its own auth layer.

**Option B — Diagnosticer re-verifies JWT:**
Requires Diagnosticer to share SECRET_KEY and JWT verification logic. Adds coupling and a second source of truth for auth. Do not do this.

**Decision: Option A.** Presenter injects tenant_id from the verified JWT before proxying.

### 6. New Presenter GET Endpoint

Location: `xeter/services/presenter/routers/diagnose.py` (extend existing file)

```
GET /diagnose/{span_id}
```

Queries `diagnostics` table via DiagnosticRepository, returns stored result or 404. View calls this after a diagnosis is stored to display the structured result persistently (page reload survives).

---

## Reuse Opportunities (Not New)

| Existing Component | Reused By Diagnosticer How |
|--------------------|-----------------------------|
| `xeter/services/worker/span_fetcher.py` — `fetch_span()` | Import directly. Diagnosticer uses the same ClickHouse + S3 fetch pattern. `fetch_span()` returns `SpanData` — the same contract Diagnosticer needs. The function is sync (boto3); wrap in `asyncio.to_thread` inside the async Diagnosticer handler. |
| `xeter/shared/db/session.py` — `get_session`, `tenant_session` | Import directly. Same pattern as Presenter and Worker for PostgreSQL session management with RLS. |
| `xeter/shared/models.py` — `Diagnostic` ORM model | Already defined. No schema migration needed; table exists from migration 001. |
| `xeter/shared/dal/base.py` — `require_tenant` | Import in DiagnosticRepository, same guard pattern. |

**Important:** `fetch_span()` in `span_fetcher.py` currently imports from `xeter.services.analyser.batch` (for `get_clickhouse_client`). This creates an indirect dependency on the analyser service for the diagnosticer. The cleaner option is to import `get_clickhouse_client` from `xeter/shared/db/clickhouse.py` directly — both modules expose the same function. The shared version should be used instead of the analyser module to avoid cross-service coupling.

---

## Data Flow: Diagnosis Request End-to-End

```
1. User clicks "Request Diagnostic" in SpanDetailPanel
   |
2. View calls POST /api/diagnose with {span_id, flags}
   (Next.js route handler proxies to Presenter)
   |
3. Presenter POST /diagnose:
   - verify_session_token → tenant_id
   - build payload: {span_id, tenant_id}  (flags dropped; Diagnosticer fetches its own)
   - httpx.post(DIAGNOSTICER_URL + "/diagnose", json=payload, timeout=30s)
   |
4. Diagnosticer POST /diagnose:
   a. Validate request body (span_id, tenant_id non-empty)
   b. fetch_span(span_id) → SpanData  [ClickHouse + S3, sync via asyncio.to_thread]
   c. tenant_session(session, tenant_id) → query flags WHERE tenant_id + span_id
   d. context.assemble(span_data, flags) → (system_prompt, user_prompt)
   e. provider.complete(system_prompt, user_prompt) → raw_llm_text  [LLM API call]
   f. parse DiagnosisResult from raw_llm_text (JSON extraction)
   g. repo.create(tenant_id, span_id, trace_id, llm_backend, result)  [PG INSERT]
   h. return DiagnosisResponse (verdict, severity, affected_field, recommended_fix)
   |
5. Presenter returns Diagnosticer response body verbatim (existing proxy logic unchanged)
   |
6. View renders DiagnosisResult in SpanDetailPanel
   - replace raw "status: message" display with structured verdict/severity/fix fields
   |
7. On subsequent panel opens: View calls GET /api/diagnose/{span_id}
   → Presenter GET /diagnose/{span_id}
   → DiagnosticRepository.get_by_span()
   → returns stored result (or 404 if not yet diagnosed)
```

---

## Recommended Project Structure Changes

```
xeter/
├── shared/
│   └── dal/
│       └── diagnostics.py          NEW — DiagnosticRepository
├── services/
│   └── diagnosticer/
│       ├── main.py                 MODIFY — wire real handler; remove 501
│       ├── schemas.py              NEW — DiagnoseRequest, DiagnosisResponse, DiagnosisResult
│       ├── llm.py                  NEW — LLMProvider Protocol + AnthropicProvider + OpenAIProvider + StubProvider + get_provider()
│       └── context.py              NEW — assemble_context(span_data, flags) → (system, user)
│   └── presenter/
│       └── routers/
│           └── diagnose.py         MODIFY — inject tenant_id into proxy; add GET /diagnose/{span_id}
└── tests/
    └── diagnosticer/               NEW directory
        ├── test_context.py         unit tests for context assembler (pure Python, no I/O)
        ├── test_llm.py             unit tests for StubProvider; integration tests for real providers
        └── test_diagnose.py        integration test for full POST /diagnose flow
```

`deploy/docker-compose.yml` — add `DIAGNOSTICER_LLM_PROVIDER`, `DIAGNOSTICER_LLM_MODEL`, and provider API key env vars to `diagnosticer` service.

---

## Architectural Patterns

### Pattern 1: Proxy-then-Store (existing, maintained)

**What:** Presenter passes requests to Diagnosticer; Diagnosticer owns both the LLM call and the PostgreSQL write. Presenter is stateless — it neither knows nor cares what the Diagnosticer does internally.

**When to use:** When the downstream service has sufficient context to make the decision (tenant_id is now injected by Presenter, giving Diagnosticer everything it needs).

**Trade-offs:**
- Pro: Clean separation; Diagnosticer can be scaled independently
- Pro: No second failure mode (Presenter write-after-proxy)
- Con: If Diagnosticer crashes mid-write, the client (Presenter) sees a 5xx and does not retry — acceptable for on-demand, non-critical diagnosis

### Pattern 2: Shared SpanData Contract (reuse)

**What:** `SpanData` dataclass defined in `worker/base.py` is the contract between span_fetcher and all analyzers. Diagnosticer should reuse this same contract rather than defining its own span representation.

**When to use:** Always — don't define two representations of the same data.

**Trade-offs:**
- Pro: Consistent field names across worker and diagnosticer; S3 resolution already handled
- Con: Diagnosticer imports from `worker/` package — minor cross-service coupling. Acceptable because `SpanData` is stable and the worker module is a peer within the same `xeter` package. If this becomes a problem later, move `SpanData` to `xeter/shared/`.

### Pattern 3: Protocol-based Provider Abstraction

**What:** `LLMProvider` is a Python Protocol (structural typing). `StubProvider` is the default in tests — it returns a canned valid `DiagnosisResult` without any HTTP calls. Real providers (`AnthropicProvider`, `OpenAIProvider`) are selected by the `get_provider()` factory at startup based on `DIAGNOSTICER_LLM_PROVIDER` env var.

**When to use:** When the provider set is known but small, and you don't want test code importing from the real provider modules.

**Trade-offs:**
- Pro: Tests run without LLM API credentials; no mock patching needed
- Pro: Adding a new provider (e.g. `ollama`) is one new class + one branch in `get_provider()`
- Con: Protocol structural typing means mypy won't catch incomplete implementations at import time — mitigated by StubProvider serving as a reference implementation

### Pattern 4: Tenant Injection at Proxy Boundary

**What:** JWT verification lives in Presenter. Presenter verifies the JWT, extracts tenant_id, and injects it into the payload before proxying to Diagnosticer. Diagnosticer trusts the tenant_id in the request body without re-verifying the JWT.

**When to use:** When downstream services are internal-only (not externally reachable) and the gateway (Presenter) is the trust boundary.

**Trade-offs:**
- Pro: Single source of truth for auth logic (Presenter's `verify_session_token`)
- Pro: Diagnosticer has no SECRET_KEY dependency
- Con: Diagnosticer trusts Presenter unconditionally — acceptable because Diagnosticer is not exposed outside the Docker network. If Diagnosticer becomes publicly reachable in future, this must be revisited.

---

## Anti-Patterns

### Anti-Pattern 1: Diagnosticer Returning Raw LLM Text

**What people do:** Have the LLM return free-text and pass it straight through to the UI.

**Why it's wrong:** View has no logic (AD-04). Parsing, error handling, and field extraction must happen in the backend. Unstructured text can't be rendered as verdict/severity/fix fields.

**Do this instead:** Prompt the LLM to return a JSON object matching `DiagnosisResult`. If JSON parsing fails, return a structured error response — not raw text.

### Anti-Pattern 2: Diagnosticer Importing from Analyser Service Module

**What people do:** `span_fetcher.py` imports `get_clickhouse_client` from `xeter.services.analyser.batch`. Following this import chain means the Diagnosticer depends on the Analyser's internal module.

**Why it's wrong:** Creates cross-service coupling — the Analyser's batch module is not a shared contract. If the Analyser is refactored, the Diagnosticer breaks unexpectedly.

**Do this instead:** Import `get_clickhouse_client` from `xeter/shared/db/clickhouse.py` directly. The same function is available there. The span_fetcher.py itself should be considered a reusable utility but should ideally be moved to `xeter/shared/` in a future cleanup.

### Anti-Pattern 3: Storing the Full LLM Conversation in the `result` JSON

**What people do:** Store everything (system prompt, user prompt, full completion text, parsed fields) in the `result` JSON column.

**Why it's wrong:** The `result` column will grow to KB per row. PostgreSQL JSONB handles this fine, but it creates unintended surface area in future queries and makes the column semantically ambiguous.

**Do this instead:** Store only `DiagnosisResult` fields (verdict, severity, affected_field, recommended_fix) plus `raw_llm_response` as a debugging field. Keep `llm_backend` in its own column (already designed this way in the schema). If detailed prompt logging becomes valuable later, add a separate `diagnosis_prompts` table.

### Anti-Pattern 4: Blocking the Presenter on LLM Latency with a Short Timeout

**What people do:** Shorten the Presenter → Diagnosticer httpx client timeout, not realising LLM calls are slow.

**Why it's wrong:** LLM API calls routinely take 5-20 seconds. The existing 30-second timeout in `presenter/main.py` (`httpx.AsyncClient(timeout=30.0)`) is correct. Shortening it causes spurious 502s from the Presenter even when the Diagnosticer succeeds.

**Do this instead:** Keep 30s timeout. The View already shows a loading state via `diagLoading` in SpanDetailPanel. If LLM calls consistently exceed 30s, switch to async fire-and-poll (POST → 202 Accepted → GET /diagnose/{span_id} polls for result). For v1.2 synchronous is fine.

---

## Build Order (Phase Dependencies)

The dependency graph is:

```
[DiagnosticRepository (DAL)] ─────────────────────────────────────┐
                                                                   ↓
[LLM provider abstraction]  ──────────────────────────────────┐   │
                                                              ↓   ↓
[Context assembler + DiagnosisResult schema]  ────────────► [Diagnosticer main.py wired]
                                                              ↓
                                                   [Presenter GET /diagnose/{span_id}]
                                                              ↓
                                                   [View SpanDetailPanel updated]
```

**Recommended phase order:**

1. **DAL + Schema** — Add `DiagnosticRepository` and `DiagnosisResult`/`DiagnoseRequest` Pydantic models. No external dependencies. Verifiable immediately with unit tests. The `diagnostics` table already exists so no migration is needed.

2. **LLM Provider Abstraction** — `llm.py` with `StubProvider` first, then `AnthropicProvider`/`OpenAIProvider`. StubProvider enables all downstream tests to run without credentials.

3. **Context Assembler** — `context.py` is pure Python. Unit-testable in isolation with mocked `SpanData` and `Flag` objects. Pin the prompt template here.

4. **Diagnosticer main.py wired** — Wire together: span_fetcher + context assembler + LLM provider + DiagnosticRepository. Replace 501 with real handler. Integration test with StubProvider against real ClickHouse/PG/MinIO (Docker Compose).

5. **Presenter modifications** — Inject `tenant_id` into proxy payload; add `GET /diagnose/{span_id}`. Presenter tests already exist in `tests/presenter/`; extend them.

6. **View SpanDetailPanel** — Replace `diagResult: string | null` state with `diagResult: DiagnosisResult | null`; render verdict/severity/affected_field/recommended_fix. Add GET fetch on panel open if diagnosis already exists.

Each step is independently deployable. Steps 1-3 add no new service endpoints and carry zero risk to the existing pipeline.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Anthropic API | `anthropic` Python SDK; async via `AsyncAnthropic`; model via env var | Install `anthropic>=0.25.0`; key via `ANTHROPIC_API_KEY` env var |
| OpenAI API | `openai` Python SDK; async via `AsyncOpenAI`; model via env var | Install `openai>=1.0.0`; key via `OPENAI_API_KEY` env var |
| Stub/Test provider | No external call; returns canned `DiagnosisResult` | Default when `DIAGNOSTICER_LLM_PROVIDER=stub` |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| View → Presenter | Next.js route handlers proxy to Presenter over HTTP; existing `/api/diagnose` route handler already exists | Add `/api/diagnose/[span_id]` route handler for GET |
| Presenter → Diagnosticer | httpx.AsyncClient POST /diagnose; Presenter injects tenant_id from JWT into body | Timeout already 30s in presenter/main.py lifespan |
| Diagnosticer → ClickHouse | Synchronous `clickhouse_connect` client via `get_clickhouse_client()` from shared/db; wrap in `asyncio.to_thread` | Same client used by Presenter and Worker |
| Diagnosticer → PostgreSQL | Async SQLAlchemy via `get_session` + `tenant_session` from shared/db/session.py | RLS enforced by `SET LOCAL app.current_tenant_id` inside transaction |
| Diagnosticer → MinIO (S3) | boto3 sync client via `get_s3_client()` from span_fetcher.py; called inside `asyncio.to_thread` | Same MinIO instance used by Analyser and Worker |
| Diagnosticer → LLM API | HTTP via provider-specific SDK (anthropic/openai); async | Keys from env vars; never committed |

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-100 tenants | Current synchronous diagnosis (POST → wait → response) is fine. LLM latency is the bottleneck, not infrastructure. |
| 100-1k tenants | Diagnosis requests may queue behind each other in a single Diagnosticer process. Add a second Diagnosticer replica in docker-compose (stateless service). |
| 1k+ tenants | Switch POST /diagnose to async job pattern: 202 Accepted + job_id, poll GET /diagnose/{span_id}. Add a Redis-backed job queue. This is explicitly out of scope for v1.2 but the synchronous design does not block it — adding async is additive, not a rewrite. |

---

## Sources

- Direct inspection of `xeter/services/diagnosticer/main.py` (scaffold state)
- Direct inspection of `xeter/services/presenter/routers/diagnose.py` (proxy implementation)
- Direct inspection of `xeter/shared/models.py` (Diagnostic ORM model, table schema)
- Direct inspection of `xeter/migrations/versions/001_initial.py` (confirmed `diagnostics` table + RLS already migrated)
- Direct inspection of `deploy/docker-compose.yml` (confirmed Diagnosticer has DATABASE_URL, CLICKHOUSE_HOST, S3 env vars)
- Direct inspection of `xeter/services/worker/span_fetcher.py` (SpanData resolution pattern to reuse)
- Direct inspection of `services/view/src/components/SpanDetailPanel.tsx` (existing "Request Diagnostic" UI state)
- Direct inspection of `services/view/src/lib/api.ts` (DiagnoseResponse interface, existing diagnose() function)

---
*Architecture research for: Xeter v1.2 — LLM Diagnosticer integration*
*Researched: 2026-04-20*

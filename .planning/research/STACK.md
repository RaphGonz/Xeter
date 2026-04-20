# Stack Research

**Domain:** AI agent observability and debugging SaaS platform
**Researched:** 2026-03-27 (base platform); 2026-04-20 (v1.2 Diagnosticer additions)
**Confidence:** HIGH (all versions verified against PyPI and official docs)

---

## v1.2 Diagnosticer Additions

This section covers only the new libraries needed for the LLM-powered Diagnosticer service.
All other stack decisions are unchanged — see the base platform sections below.

### What Already Exists (Do Not Re-add)

The following are already in `xeter/pyproject.toml` and cover the Diagnosticer's data-access needs:

- `fastapi==0.135.2` — HTTP framework, Diagnosticer is already a FastAPI app
- `pydantic==2.12.5` — Used for structured output schemas
- `asyncpg==0.31.0` + `sqlalchemy==2.0.48` — PostgreSQL reads/writes; `Diagnostic` model already in `shared/models.py`
- `aioboto3==15.5.0` — S3 payload retrieval (large prompts/responses)
- `clickhouse-connect==0.15.0` — Span field reads
- `httpx` — Already present; no additional async HTTP client needed for LLM SDKs (both Anthropic and OpenAI SDKs use `httpx` internally)
- `python-dotenv` — Env var loading already covered

### New Dependencies Required

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `anthropic` | `>=0.96.0` | Anthropic Claude API client | Official SDK; async via `AsyncAnthropic`; `client.messages.parse()` for structured output with Pydantic; uses `httpx` internally (no new transitive dep) |
| `openai` | `>=2.32.0` | OpenAI GPT API client | Official SDK; async via `AsyncOpenAI`; `client.beta.chat.completions.parse()` for structured output with Pydantic; same `httpx` backend |

Both libraries are all that's needed. No additional abstraction library, no LiteLLM.

---

### Core Technology: LLM Client Libraries

#### Anthropic SDK (`anthropic>=0.96.0`)

The official Python client for Claude models. **HIGH confidence** — verified on PyPI 2026-04-20 at version 0.96.0.

Async pattern for FastAPI:

```python
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

response = await client.messages.create(
    model=settings.LLM_MODEL,          # e.g. "claude-sonnet-4-5-20250929"
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}],
)
```

Structured output (current pattern — no beta header required as of v1.2 timeframe):

```python
from pydantic import BaseModel

class DiagnosisResult(BaseModel):
    verdict: str          # "model" | "architecture" | "prompt"
    severity: str         # "low" | "medium" | "high"
    affected_field: str
    recommended_fix: str

response = await client.messages.parse(
    model=settings.LLM_MODEL,
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}],
    output_format=DiagnosisResult,
)
result: DiagnosisResult = response.parsed_output
```

`client.messages.parse()` handles schema transformation, constrained decoding, and validation.
Returns a typed `DiagnosisResult` instance directly — no manual JSON parsing.

#### OpenAI SDK (`openai>=2.32.0`)

The official Python client for GPT models. **HIGH confidence** — verified on PyPI 2026-04-20 at version 2.32.0.

Async pattern for FastAPI:

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
```

Structured output:

```python
completion = await client.beta.chat.completions.parse(
    model=settings.LLM_MODEL,          # e.g. "gpt-4o-2024-08-06"
    messages=[{"role": "user", "content": prompt}],
    response_format=DiagnosisResult,   # same Pydantic model as above
)
result: DiagnosisResult = completion.choices[0].message.parsed
```

Note: `client.beta.chat.completions.parse()` with Pydantic requires GPT-4o (gpt-4o-2024-08-06 or later).
Older models (gpt-3.5-turbo, gpt-4-turbo) only support JSON mode, which does not guarantee schema conformance.

---

### Provider-Agnostic Adapter Pattern

**Recommendation:** Hand-roll a minimal adapter (Protocol + two concrete classes). Do NOT use LiteLLM.

**Why not LiteLLM:** ~200MB memory footprint, 1.2s import time, 300+ transitive dependencies. For a solo-dev service with two providers and a single operation (diagnose), this is an unacceptable weight. The abstraction cost of LiteLLM exceeds the abstraction benefit when the interface is one `diagnose()` call.

**Why not `instructor`:** The `instructor` library (v1.15.1 on PyPI 2026-04-20) wraps both SDKs behind a unified retry+validation interface and is legitimate for teams using 5+ providers. For Xeter at v1.2, both native SDKs already provide `parse()` methods with Pydantic schemas — `instructor` adds a dependency without adding capability beyond what the SDKs already ship.

**Recommended pattern — Protocol + factory:**

```python
# xeter/services/diagnosticer/llm/base.py
from typing import Protocol
from xeter.services.diagnosticer.schemas import DiagnosisResult

class LLMProvider(Protocol):
    async def diagnose(self, prompt: str) -> DiagnosisResult: ...

# xeter/services/diagnosticer/llm/anthropic_provider.py
class AnthropicProvider:
    def __init__(self, api_key: str, model: str): ...
    async def diagnose(self, prompt: str) -> DiagnosisResult: ...

# xeter/services/diagnosticer/llm/openai_provider.py
class OpenAIProvider:
    def __init__(self, api_key: str, model: str): ...
    async def diagnose(self, prompt: str) -> DiagnosisResult: ...

# xeter/services/diagnosticer/llm/factory.py
def get_provider(settings: DiagnosticerSettings) -> LLMProvider:
    if settings.LLM_PROVIDER == "anthropic":
        return AnthropicProvider(settings.ANTHROPIC_API_KEY, settings.LLM_MODEL)
    elif settings.LLM_PROVIDER == "openai":
        return OpenAIProvider(settings.OPENAI_API_KEY, settings.LLM_MODEL)
    raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")
```

This gives full provider-agnosticism in ~80 lines with zero new dependencies beyond the two SDKs.

---

### Environment Configuration

Use Pydantic `BaseSettings` (already available via `pydantic-settings`, installed transitively with FastAPI):

```python
from pydantic_settings import BaseSettings

class DiagnosticerSettings(BaseSettings):
    LLM_PROVIDER: str = "anthropic"           # "anthropic" | "openai"
    LLM_MODEL: str = "claude-sonnet-4-5-20250929"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MAX_TOKENS: int = 1024
    LLM_TIMEOUT_SECONDS: float = 30.0

    class Config:
        env_file = ".env"
```

**Why pydantic-settings and not raw `os.getenv`:** Type coercion, defaults, and `.env` file support in one place. Already available — `pydantic-settings` is installed alongside `pydantic>=2.0`.

---

### Structured Output Schema

The `Diagnostic` SQLAlchemy model (`shared/models.py`) already has:
- `llm_backend: str` — store `f"{provider}/{model}"` (e.g. `"anthropic/claude-sonnet-4-5-20250929"`)
- `result: dict` (JSON column) — store the serialized `DiagnosisResult`

The Pydantic `DiagnosisResult` model lives in `xeter/services/diagnosticer/schemas.py` (new file) and is shared between the LLM provider and the DAL write path. No new PostgreSQL columns needed.

---

### What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `litellm` | 200MB / 300+ deps for a 2-provider service; import time ~1.2s | Direct `anthropic` + `openai` SDKs with hand-rolled adapter |
| `instructor` | Adds dependency whose value (retry+parse) is already provided by native SDK `.parse()` methods | `client.messages.parse()` (Anthropic) / `client.beta.chat.completions.parse()` (OpenAI) |
| `langchain` | 500MB+ ecosystem; brings its own abstractions that conflict with Xeter's minimal service pattern | Direct SDK calls |
| `aiohttp` separately | `httpx` is already in pyproject.toml; both Anthropic and OpenAI SDKs use `httpx` internally | Nothing extra needed |
| `tenacity` for retry | Both SDKs have built-in retry with exponential backoff (`max_retries` param on client construction) | `AsyncAnthropic(max_retries=3)` / `AsyncOpenAI(max_retries=3)` |

---

### Installation Delta (pyproject.toml additions only)

```toml
# Add to [project] dependencies in xeter/pyproject.toml:
"anthropic>=0.96.0",
"openai>=2.32.0",
```

No other changes to pyproject.toml needed.

---

### Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `anthropic>=0.96.0` | Python 3.9–3.14; `httpx>=0.25` | `httpx` already in pyproject.toml; no conflict |
| `openai>=2.32.0` | Python 3.9–3.14; `httpx>=0.25` | Same `httpx` dep; no conflict |
| `anthropic>=0.96.0` | `pydantic>=2.0` | `.parse()` requires Pydantic v2 BaseModel |
| `openai>=2.32.0` | `pydantic>=2.0` | `.parse()` requires Pydantic v2 BaseModel; already at 2.12.5 |
| Both SDKs | `fastapi==0.135.2` | No conflict; both are pure HTTP client libs |

---

### Sources (v1.2 Additions)

- [PyPI: anthropic 0.96.0](https://pypi.org/project/anthropic/) — version verified 2026-04-20; HIGH confidence
- [PyPI: openai 2.32.0](https://pypi.org/project/openai/) — version verified 2026-04-20; HIGH confidence
- [PyPI: instructor 1.15.1](https://pypi.org/project/instructor/) — version verified 2026-04-20; considered and rejected
- [Anthropic structured outputs docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) — `client.messages.parse()` pattern; HIGH confidence (official docs)
- [Anthropic async client docs](https://github.com/anthropics/anthropic-sdk-python/blob/main/README.md) — `AsyncAnthropic` pattern; HIGH confidence (official GitHub)
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) — `client.beta.chat.completions.parse()` pattern; HIGH confidence (official docs)
- [LiteLLM memory footprint](https://github.com/silvestrid/ullm) — 200MB / 1.2s import benchmarked vs ULLM; MEDIUM confidence (third-party benchmark)

---

## Base Platform Stack (Unchanged from v1.0/v1.1)

---

### Python Runtime

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Runtime for all backend services and SDK | 3.12 is the safe production choice for 2026: all major libraries (sentence-transformers 5.x, FastAPI 0.135, redis 7.4) fully support it; 3.13 JIT is still experimental under real async workloads; 3.11 is the minimum for some deps |

Use Python 3.12. Do not use 3.11 (sentence-transformers 5.x requires >=3.10 but 3.12 is the sweet spot for library compatibility). Do not use 3.13 in production yet — the free-threaded mode and JIT are opt-in and experimental, and the embedding/torch stack has patchy support.

---

### Core Backend Framework

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FastAPI | 0.135.2 | HTTP API framework for Analyser and Presenter | Async-first, built-in Pydantic v2 validation, native SSE support via `StreamingResponse`, 5–10x faster than Flask; the de-facto standard for Python async APIs in 2026 (38% adoption, up from 29% in 2025) |
| Pydantic | 2.12.5 | Data validation and serialisation | Ships with FastAPI; v2 is Rust-backed (5–50x faster than v1); use for all request/response models and internal data contracts |
| Uvicorn | >=0.32 | ASGI server | Production-grade async server; use `uvicorn[standard]` for uvloop and httptools |

**Not Flask, not Django.** Flask is synchronous and requires workarounds for async embedding calls. Django is batteries-included for CRUD apps, not async microservices. FastAPI is the right tool here.

---

### OTel Ingestion (SDK + Analyser)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| opentelemetry-sdk | 1.40.0 | Core OTel SDK — used in the Python SDK to create and emit spans | Official OpenTelemetry Python SDK; stable, production-ready, supports Python 3.9–3.14 |
| opentelemetry-exporter-otlp-proto-http | 1.40.0 | Exports spans from SDK to Analyser over OTLP/HTTP | HTTP transport preferred over gRPC for simplicity (no protobuf compilation, works through proxies); standard port 4318; same release line as sdk |
| opentelemetry-exporter-otlp-proto-grpc | 1.40.0 | Alternative gRPC exporter (include as option) | gRPC transport for lower overhead in high-throughput scenarios; standard port 4317; ship both, let tenant configure |

**Pattern:** The SDK wraps these. The Analyser exposes an OTLP-compatible HTTP endpoint at `/v1/traces` (port 4318) or implements a FastAPI route that accepts OTLP protobuf payloads. The Analyser does NOT need the OTel Collector sidecar — it receives spans directly.

The `opentelemetry-exporter-otlp` convenience meta-package installs both HTTP and gRPC variants. Pin the exact `-proto-http` and `-proto-grpc` packages to avoid surprising transitive installs.

---

### Async Task Queue (Embedding Workers)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| arq | 0.27.0 | Redis-backed async task queue for embedding workers | asyncio-native; pairs perfectly with FastAPI's event loop; significantly faster than RQ for I/O-bound tasks (embedding involves I/O + GPU); minimal API; no broker complexity vs Celery |
| redis (Python client) | 7.4.0 | Redis client with async support | Official client; built-in asyncio support via `redis.asyncio`; required by arq |

**Not Celery.** Celery is not asyncio-native and introduces multiprocessing overhead inappropriate for I/O-bound embedding tasks. Celery's setup complexity (broker + result backend configuration) is not justified for this use case.

**Not RQ.** RQ is synchronous and 4x slower than arq in benchmarks for I/O-bound jobs.

**arq pattern:** Analyser enqueues `compute_embeddings(span_id)` job after persisting the span. One or more arq workers dequeue, load the embedding model, compute similarity scores, write flag rows to PostgreSQL.

---

### Embedding Model and Vector Similarity

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| sentence-transformers | 5.3.0 | Load and run embedding models locally | Standard Python embedding library; 15K+ models on HuggingFace; `model.encode()` + cosine similarity is the standard pattern for intra-span field comparison; Python >=3.10 required |
| BAAI/bge-base-en-v1.5 | — (HuggingFace model) | Embedding model for semantic similarity | Outperforms all-MiniLM-L6-v2 on MTEB (MiniLM scores only 56% top-5 vs bge-base's ~70%+); 109M params, 768-dim vectors; supports up to 512 tokens per field; fast enough for async workers; runs on CPU for dev, GPU for prod |

**Not all-MiniLM-L6-v2.** Benchmarks show it is a 2019-architecture model with 56% top-5 accuracy — unacceptable for a product where false positives destroy trust (R-03 in arc42). Its 512-token context is a hard limit that will be hit by prompt fields.

**Not nomic-embed-text-v1.5.** Higher accuracy (86% top-5) but 137M params and nearly 2x inference latency versus E5/bge models. Context length of 8192 is wasted when comparing field pairs within a single span.

**Not OpenAI text-embedding-3-small.** External API call in the async embedding worker adds latency, cost, and a network dependency that breaks dev environments without internet access. The architecture decision (AD-05) requires configurability; local-first is the right default.

**Similarity computation:** `sentence_transformers.util.cos_sim()` for cosine similarity between field pairs. No vector DB needed — comparisons are within-span (one span at a time), not across a corpus.

---

### ClickHouse Client

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| clickhouse-connect | 0.15.0 | Python client for ClickHouse span storage | Official ClickHouse Inc. driver; HTTP-based (works through firewalls and proxies); automatic connection pooling; SQLAlchemy integration; actively maintained; Python 3.9–3.14 |

**Not clickhouse-driver (native TCP).** clickhouse-driver uses ClickHouse's native TCP binary protocol which provides marginal performance gains, but requires more complex setup and has no official backing. clickhouse-connect is the officially recommended driver from ClickHouse Inc.

**Note:** Python 3.9 support in clickhouse-connect is deprecated and will be removed in 1.0 — pin to Python 3.12 to avoid any future upgrade pain.

---

### PostgreSQL Client and ORM

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| SQLAlchemy | 2.0.48 | ORM and query builder for PostgreSQL (flags, diagnostics, auth, tenants) | SQLAlchemy 2.0 has first-class async support; pairs directly with asyncpg driver; `create_async_engine` + `AsyncSession` is the production pattern; extensive ecosystem |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Lowest-latency async PostgreSQL driver for Python; native asyncio; sub-millisecond queries; required as SQLAlchemy's `postgresql+asyncpg://` backend |
| Alembic | 1.18.4 | Database migration management | Official SQLAlchemy migration tool; supports async engine via `alembic init -t async`; autogenerate from models; essential for managing PostgreSQL schema evolution |

**Pattern:** `SQLAlchemy 2.0 + asyncpg` is the confirmed 2025–2026 standard for async FastAPI applications. Use `postgresql+asyncpg://` connection string. Initialize Alembic with `alembic init -t async` to get the async env.py template.

---

### S3 Storage Client

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| aioboto3 | 15.5.0 | Async S3 client for storing/retrieving large payloads | Async wrapper around boto3; same API surface, async/await semantics; essential in a FastAPI/asyncio context to avoid blocking the event loop on S3 reads (Presenter fetching prompt/response payloads on demand) |

**Not boto3 directly.** Calling boto3 synchronously from an async FastAPI handler blocks the event loop, stalling all concurrent requests. aioboto3 is the async equivalent with the same API.

**Local dev:** Use MinIO in Docker Compose. aioboto3 works with MinIO by setting `endpoint_url="http://minio:9000"` and `use_ssl=False`. MinIO implements the full S3 v4 API. Set `force_path_style=True` for non-AWS endpoints.

---

### Frontend Dashboard

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| React | 19.x | UI component library | Industry standard; largest ecosystem; required by shadcn/ui and TanStack Query |
| Vite | 6.x | Build tool and dev server | Instant HMR; far faster than webpack/CRA for development iteration; official shadcn/ui Vite support; ideal for SPA dashboard (no SSR needed for internal dev tool) |
| TypeScript | 5.x | Type safety for frontend | Standard for any non-trivial React app; shadcn/ui ships TypeScript-first |
| Tailwind CSS | 4.x | Utility-first CSS | Industry standard for SaaS dashboards in 2026; pairs with shadcn/ui v3 |
| shadcn/ui | latest | Component library | Copy-paste component system (not a dependency); full Tailwind v4 support; includes table, filter, badge, dialog components needed for span list and detail views; Vite installation officially supported |
| TanStack Query | 5.x (v5.90+) | Server state management | Powers 80% of new React apps per 2025 State of JS; handles polling, loading states, cache invalidation for span list and detail views; avoids manual fetch-in-useEffect patterns |

**Not Next.js.** The dashboard is a pure SPA — authenticated, served to logged-in B2B users, no SEO requirement, no SSR benefit. Next.js adds build complexity (server components, server actions, routing conventions) with no benefit for this use case. Vite + React Router v6 is the leaner choice.

**Not plain CSS / CSS modules.** Tailwind + shadcn/ui is the standard SaaS component toolkit in 2026 with the most available templates and patterns for exactly this type of dashboard.

---

### Development Infrastructure (Docker Compose)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Docker Compose | v2 (Compose spec 5.0) | Multi-service local dev environment | Industry standard; Compose spec v5.0 (Dec 2025) delegates builds to Docker Bake for better caching; `watch` mode for live reload without rebuilds |
| ClickHouse | 25.x (official image) | Local span storage | Use `clickhouse/clickhouse-server:latest` or pin to `25.3`; minimal config for dev |
| PostgreSQL | 16 | Local flags/diagnostics/auth storage | `postgres:16-alpine`; stable, widely-tested |
| Redis | 7 | Local queue for arq workers | `redis:7-alpine`; lightweight |
| MinIO | latest | Local S3-compatible object storage | `minio/minio:latest`; S3 v4 API compatible; configure with `MINIO_ROOT_USER` + `MINIO_ROOT_PASSWORD` env vars; expose port 9000 (API) and 9001 (console) |

**Compose network pattern:** Define separate `backend` and `frontend` networks. Stateful services (ClickHouse, PostgreSQL, Redis, MinIO) attach to `backend` only. Analyser and Presenter attach to `backend`. Frontend attaches to a separate `frontend` network with Presenter exposed as the API. This limits blast radius and reflects production isolation.

**Volume pattern:** Named volumes for ClickHouse data (`ch_data`), PostgreSQL data (`pg_data`), and MinIO data (`minio_data`). Never use bind-mounts for database data — they cause permission issues on Windows/WSL2.

---

## Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uvicorn[standard] | >=0.32 | ASGI server with uvloop | All FastAPI services |
| python-jose[cryptography] | >=3.3 | JWT token generation/validation | Dashboard auth (Path A email/password) |
| passlib[bcrypt] | >=1.7 | Password hashing | `api_keys.key_hash` and `users.password_hash` |
| httpx | >=0.28 | Async HTTP client | Presenter → Diagnosticer calls; async test client for pytest; also used internally by Anthropic and OpenAI SDKs |
| pytest | >=8.3 | Test runner | All services |
| pytest-asyncio | 1.3.0 | Async test support | Required for testing FastAPI async endpoints |
| anyio | >=4.7 | Async test backend | Used by pytest-asyncio; pin to same version FastAPI depends on |
| python-dotenv | >=1.0 | Environment variable loading | Load `.env` in development |
| structlog | >=25.0 | Structured logging | JSON-formatted logs for all services; pairs well with observability tooling |

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastAPI | Django REST Framework | Only if you need admin panels, heavy ORM magic, or a team already expert in Django |
| FastAPI | Flask | Never for this project — Flask is synchronous and lacks async embedding worker integration |
| arq | Celery | Only if you need scheduled tasks (Celery Beat), complex workflow DAGs, or multi-broker support |
| arq | RQ | Only for pure simplicity at the cost of 4x slower job throughput |
| sentence-transformers + bge-base-en-v1.5 | OpenAI text-embedding-3-small | Only after GA when cost and latency of API calls are acceptable; requires feature flag toggle |
| clickhouse-connect | clickhouse-driver | Only if benchmarks prove the native TCP protocol is a bottleneck in production |
| aioboto3 | boto3 | Only in synchronous scripts (migrations, CLI tools) — never in async FastAPI handlers |
| Vite + React | Next.js | Only if the dashboard needs public-facing pages, SSR for SEO, or server-side data fetching |
| asyncpg + SQLAlchemy 2.0 | psycopg3 | Either works; asyncpg has a larger production track record in the FastAPI ecosystem |
| Direct SDK adapter pattern | litellm | Only if adding 5+ providers and needing cost tracking, rate limiting, and observability built-in |
| Direct SDK adapter pattern | instructor | Only if validation retry logic becomes complex across many providers |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Flask | Synchronous; embedding calls block the process; no native ASGI | FastAPI |
| Celery | Not asyncio-native; heavyweight for simple embedding worker pattern; config overhead | arq |
| all-MiniLM-L6-v2 | 2019 architecture; 56% top-5 accuracy is too low for a trust-critical flagging product | BAAI/bge-base-en-v1.5 |
| nomic-embed-text-v1.5 | 137M params, 2x inference latency vs bge-base; 8192 context wasted on field-pair comparisons | BAAI/bge-base-en-v1.5 |
| boto3 (sync) in FastAPI handlers | Blocks the asyncio event loop on every S3 read/write | aioboto3 |
| clickhouse-driver | Community-maintained, native TCP complexity, no official backing | clickhouse-connect |
| SQLAlchemy 1.x | Async support is bolted on; 2.0 rewrote it properly | SQLAlchemy 2.0.x |
| Next.js for the dashboard | SSR overhead with zero benefit for an authenticated SPA; couples frontend deployment to Node.js server | Vite + React |
| Python 3.9 or 3.10 | clickhouse-connect deprecates 3.9; sentence-transformers 5.x requires >=3.10 but 3.12 avoids edge cases | Python 3.12 |
| Python 3.13 in production | JIT is experimental; torch/embedding stack has patchy 3.13 support as of Q1 2026 | Python 3.12 |
| litellm | 200MB memory footprint, 300+ transitive deps, 1.2s import — massive overhead for 2-provider service | Direct `anthropic` + `openai` SDKs |
| langchain | 500MB+ ecosystem; own abstractions that conflict with Xeter's minimal DAL/service pattern | Direct SDK calls |
| instructor | Duplicate of native SDK `.parse()` methods; adds dependency without capability | `client.messages.parse()` / `client.beta.chat.completions.parse()` |

---

## Installation

```bash
# Backend services (Analyser, Presenter, Diagnosticer)
pip install \
  fastapi==0.135.2 \
  "uvicorn[standard]>=0.32" \
  pydantic==2.12.5 \
  opentelemetry-sdk==1.40.0 \
  opentelemetry-exporter-otlp-proto-http==1.40.0 \
  opentelemetry-exporter-otlp-proto-grpc==1.40.0 \
  arq==0.27.0 \
  redis==7.4.0 \
  sentence-transformers==5.3.0 \
  clickhouse-connect==0.15.0 \
  sqlalchemy==2.0.48 \
  asyncpg==0.31.0 \
  alembic==1.18.4 \
  aioboto3==15.5.0 \
  httpx \
  python-jose[cryptography] \
  passlib[bcrypt] \
  python-dotenv \
  structlog \
  "anthropic>=0.96.0" \
  "openai>=2.32.0"

# Dev / test dependencies
pip install \
  pytest \
  pytest-asyncio==1.3.0 \
  anyio \
  httpx

# SDK (subset — lighter footprint)
pip install \
  opentelemetry-sdk==1.40.0 \
  opentelemetry-exporter-otlp-proto-http==1.40.0

# Frontend (from frontend/ directory)
npm create vite@latest . -- --template react-ts
npm install
npx shadcn@latest init
npm install @tanstack/react-query tailwindcss
```

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| fastapi==0.135.2 | pydantic==2.12.5 | FastAPI 0.100+ requires Pydantic v2; do not mix Pydantic v1 |
| sentence-transformers==5.3.0 | Python >=3.10 | Do not run on Python 3.9; use Python 3.12 |
| clickhouse-connect==0.15.0 | Python >=3.9 (3.9 deprecated) | Use Python 3.12; 3.9 support removed in 1.0 |
| arq==0.27.0 | redis==7.4.0 | arq uses redis-py asyncio client internally; pin compatible versions |
| sqlalchemy==2.0.48 | asyncpg==0.31.0 | Use `postgresql+asyncpg://` URL; SQLAlchemy 2.1.x (pre-release) is not stable yet |
| alembic==1.18.4 | sqlalchemy==2.0.48 | Alembic follows SQLAlchemy major version; both on 2.x is correct |
| opentelemetry-sdk==1.40.0 | opentelemetry-exporter-otlp-proto-http==1.40.0 | Always pin sdk and exporter to the same release; mixed versions cause serialization errors |
| Tailwind CSS v4 | shadcn/ui (latest) | shadcn/ui now supports Tailwind v4 natively; do not use Tailwind v3 with the latest shadcn install |
| anthropic>=0.96.0 | pydantic==2.12.5, httpx | No conflict; uses httpx already in deps; `.parse()` requires Pydantic v2 |
| openai>=2.32.0 | pydantic==2.12.5, httpx | No conflict; `.parse()` requires Pydantic v2; GPT-4o model required for structured outputs |

---

## Stack Patterns by Service

**Analyser service:**
- FastAPI endpoint receives OTLP spans (HTTP POST, protobuf or JSON)
- Synchronous path: validate → write to ClickHouse via clickhouse-connect → enqueue to Redis via arq
- Async path (arq worker): dequeue span_id → load bge-base-en-v1.5 model → compute cosine similarities → write flag rows to PostgreSQL via SQLAlchemy async

**Presenter service:**
- FastAPI with async SQLAlchemy sessions
- Span list: query ClickHouse + LEFT JOIN flag counts from PostgreSQL in parallel (asyncio.gather)
- Span detail: query ClickHouse span row + PostgreSQL flags + lazy-fetch S3 payloads via aioboto3
- SSE endpoint: `StreamingResponse` with `text/event-stream` content type for flag-update and diagnostic-complete push events

**Diagnosticer service (v1.2 — LLM-powered):**
- FastAPI service; `POST /diagnose` receives `span_id` + `tenant_id`
- Context assembly: async-parallel fetch of span fields (ClickHouse), flags (PostgreSQL), S3 payloads (aioboto3)
- LLM call: provider resolved from `LLM_PROVIDER` env var; `AsyncAnthropic` or `AsyncOpenAI` with structured output
- Result persistence: write to `diagnostics` table (existing model) via SQLAlchemy async; `llm_backend = f"{provider}/{model}"`
- Response: return `DiagnosisResult` JSON immediately (synchronous request-response; no background task needed given Diagnosticer is already isolated)

**Python SDK:**
- opentelemetry-sdk + opentelemetry-exporter-otlp-proto-http
- Thin wrapper that creates spans with Xeter-specific attributes
- `XeterTracer` class configures OTLP exporter pointing at Analyser endpoint
- No heavy dependencies; importable in any Python agent framework

---

## Sources

- [PyPI: anthropic 0.96.0](https://pypi.org/project/anthropic/) — version verified 2026-04-20; HIGH confidence
- [PyPI: openai 2.32.0](https://pypi.org/project/openai/) — version verified 2026-04-20; HIGH confidence
- [PyPI: instructor 1.15.1](https://pypi.org/project/instructor/) — version verified 2026-04-20; considered and rejected
- [Anthropic structured outputs docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) — `client.messages.parse()` pattern; HIGH confidence (official docs, no beta header required)
- [Anthropic async client (GitHub README)](https://github.com/anthropics/anthropic-sdk-python/blob/main/README.md) — `AsyncAnthropic` pattern; HIGH confidence
- [OpenAI structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) — `client.beta.chat.completions.parse()` with Pydantic; HIGH confidence (official docs)
- [LiteLLM memory vs ULLM benchmark](https://github.com/silvestrid/ullm) — 200MB / 1.2s import; MEDIUM confidence (third-party benchmark, consistent with community reports)
- [PyPI: opentelemetry-sdk 1.40.0](https://pypi.org/project/opentelemetry-sdk/) — version verified March 2026
- [PyPI: FastAPI 0.135.2](https://pypi.org/project/fastapi/) — verified March 2026
- [PyPI: Pydantic 2.12.5](https://pypi.org/project/pydantic/) — verified
- [PyPI: clickhouse-connect 0.15.0](https://pypi.org/project/clickhouse-connect/) — verified March 2026; deprecation notice on Python 3.9
- [PyPI: sentence-transformers 5.3.0](https://pypi.org/project/sentence-transformers/) — verified March 2026; requires Python >=3.10
- [PyPI: arq 0.27.0](https://pypi.org/project/arq/) — verified February 2026
- [PyPI: SQLAlchemy 2.0.48](https://pypi.org/project/sqlalchemy/) — verified March 2026
- [PyPI: asyncpg 0.31.0](https://pypi.org/project/asyncpg/) — verified November 2025
- [PyPI: Alembic 1.18.4](https://pypi.org/project/alembic/) — verified February 2026
- [PyPI: aioboto3 15.5.0](https://pypi.org/project/aioboto3/) — verified October 2025
- [shadcn/ui Vite installation](https://ui.shadcn.com/docs/installation/vite) — HIGH confidence (official docs)
- [shadcn/ui Tailwind v4](https://ui.shadcn.com/docs/tailwind-v4) — HIGH confidence (official docs)
- [OpenTelemetry Python docs](https://opentelemetry.io/docs/languages/python/) — HIGH confidence (official docs)

---
*Stack research for: Xeter — AI agent observability SaaS*
*Base stack researched: 2026-03-27*
*v1.2 Diagnosticer additions researched: 2026-04-20*

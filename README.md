# Xeter

**AI Agent Tool-Call Debugger**

When your agent fails to call a tool, you shouldn't have to spend hours discovering it was a parser format mismatch, a model capability ceiling, or a bad tool description. Xeter tells you immediately which layer broke and why.

Drop-in Python SDK. Works with any local model. No framework lock-in.

## What It Does

Xeter is a B2B SaaS observability platform that debugs AI agent tool-calling failures. It ingests OpenTelemetry spans from instrumented agent code, applies heuristic analysis (vector similarity between prompt and tool fields) to flag anomalous tool calls, and exposes a dashboard where developers can see what went wrong and why.

### Flag Types

- **wrong_tool_called** — agent picked the wrong tool for the prompt
- **wrong_tool_args** — right tool, wrong arguments
- **no_tool_used** — agent should have called a tool but didn't
- **unnecessary_tool_call** — tool called on a social/phatic prompt that needed none
- **tool_not_available** — agent called a tool not in the available tools list
- **parsing_error** — model output couldn't be parsed into a tool call
- **response_anomaly** — response is semantically unrelated to the prompt

### Two-Layer Analysis

**Layer 1 (heuristic)** catches obvious mechanical failures fast and cheap — format mismatches, wrong-tool ranking via vector similarity, argument validation.

**Layer 2 (LLM diagnosis)** explains root cause on-demand — click "Diagnose" on any span to get a structured verdict (model / architecture / prompt), severity, affected field, and recommended fix. Configurable provider: Anthropic, OpenAI, or Ollama.

## Architecture

```
Customer Agent  ──SDK──▶  Analyser (ingestion)
                               │
                               ├──▶ S3 (large payloads)
                               ├──▶ ClickHouse (spans)
                               └──▶ Redis (queue)
                                        │
                                        ▼
                                   Worker (embedding + flagging)
                                        │
                                        ▼
                                   PostgreSQL (flags, scores, auth, tenants)
                                        │
                               Presenter (API) ◀── View (dashboard)
                                        │
                                        ▼
                               Diagnosticer (LLM, on-demand)
```

**Services:**
- **Analyser** — receives spans via POST /v1/spans, stores large payloads in S3, batches rows into ClickHouse, enqueues span_id to Redis
- **Worker** — BRPOP consumer; fetches span from ClickHouse, runs embedding similarity across 5 dimensions, writes flag rows and similarity scores to PostgreSQL
- **Presenter** — REST API for the dashboard; merges ClickHouse spans + PostgreSQL flags at read time, lazy-loads S3 payloads on span detail
- **View** — Next.js 15 dashboard (span list, filters, span detail panel with flag scores and S3 payload tabs)
- **Diagnosticer** — LLM-powered root cause analysis; on-demand POST /diagnose assembles span + flag + S3 context and calls the configured LLM provider (Anthropic / OpenAI / Ollama) to return a structured verdict, severity, affected field, and recommended fix

**Storage:**
- **ClickHouse** — span storage with MergeTree `ORDER BY (tenant_id, trace_id, time_begin)`
- **PostgreSQL** — flags, similarity scores, auth (API keys, users, tenants) with Row Level Security
- **MinIO/S3** — large text payloads (prompt, response, raw_response, available_tools) referenced by key
- **Redis** — decouples ingestion from embedding workers via BRPOP queue

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.12+

### Setup

```bash
# Clone and enter the repo
git clone <repo-url> && cd Xeter

# Copy environment defaults
cp .env.example .env

# Start all services (PostgreSQL, ClickHouse, Redis, MinIO, Analyser, Worker, Presenter, View)
docker compose -f deploy/docker-compose.yml up --build

# In a new terminal — run database migrations
python -m alembic -c xeter/migrations/alembic.ini upgrade head

# Seed dev data (creates tenant + user + API key: dev-api-key-local)
python -m xeter.scripts.seed
```

### Verify It Works

```bash
# Health check
curl http://localhost:8000/healthz

# Register a new tenant (returns a one-time API key starting with xtr_)
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"tenant_name": "acme", "email": "test@acme.com", "password": "password123"}'
```

### Instrument Your Agent

```python
import xeter_sdk as xeter

@xeter.trace(
    agent_name="my-agent",
    agent_model="gpt-4o",
    tool_name="search_web",
    tool_description="Search the web for a query",
    prompt_arg="prompt",
    tools_arg="available_tools",
)
def call_search(prompt: str, available_tools: list) -> str:
    ...
```

Set `XETER_ENDPOINT=http://localhost:4318` and `XETER_API_KEY=<your-key>` in your environment. Spans are sent fire-and-forget in a background thread — zero added latency to your agent.

### Dev Commands

All commands run from the repo root:

| Command | What it does |
|---------|-------------|
| `docker compose -f deploy/docker-compose.yml up --build` | Start the full stack |
| `docker compose -f deploy/docker-compose.yml down` | Stop all services |
| `docker compose -f deploy/docker-compose.yml down -v` | Stop and remove all data volumes |
| `python -m alembic -c xeter/migrations/alembic.ini upgrade head` | Run PostgreSQL migrations |
| `python -m xeter.scripts.seed` | Seed dev tenant + API key |
| `python -m xeter.scripts.reset` | Drop all schemas, re-migrate, re-seed |
| `cd xeter && python -m pytest tests/ -v` | Run test suite |
| `python xeter/scripts/validate.py` | Run E2E smoke test (register → ingest → analyze → retrieve) |

For frontend development, run the Next.js dev server separately instead of using the dockerized View — it hot-reloads on file changes:

```bash
cd services/view
npm run dev
# open http://localhost:3000
```

The Docker stack must be running for API calls to work.

### Ports

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

## Multi-Tenancy

All tables enforce tenant isolation via PostgreSQL Row Level Security. Every query runs inside a `tenant_session()` that sets `SET LOCAL app.current_tenant_id` — the RLS policy filters rows automatically. The DAL layer raises `MissingTenantError` at the Python level before any database call if `tenant_id` is missing.

## Auth

- **SDK ingestion**: API key per tenant (bcrypt hash stored, plaintext returned once at registration). Keys use the `xtr_` prefix.
- **Dashboard login**: email/password (bcrypt hashed), JWT session token returned and sent as `Authorization: Bearer <token>` on subsequent requests

## Project Status

**v1.0 shipped** (2026-04-04) — full pipeline operational: SDK → Analyser → Redis → Worker → Presenter → Next.js dashboard. E2E smoke test passes (~37s register → ingest → analyze → retrieve).

**v1.1 shipped** (2026-04-18) — Analyser accuracy milestone: all four heuristic check methods rewritten with research-backed implementations, spaCy NLP integrated, Embedder extracted as a standalone microservice, calibration infra upgraded.

**v1.2 shipped** (2026-04-25) — Diagnosticer milestone: LLM root-cause analysis active end-to-end. Click "Diagnose" on any span to get verdict, severity, affected field, and recommended fix. Configurable provider (Anthropic / OpenAI / Ollama). 112 tests passing.

**Next:** v1.3 — TypeScript SDK, cloud deployment.

## Documentation

- `documentation/xeterarc42_v1.2.md` — full arc42 architecture documentation (current, post-v1.2)
- `documentation/xeterarc42_v1.1.md` — arc42 snapshot post-v1.1 (Analyser Accuracy milestone)
- `documentation/silent_failures_ai_agents.md` — problem space research
- `documentation/foundation_sprint/` — competitor analysis, positioning, hypothesis validation

# Xeter

**AI Agent Tool-Call Debugger**

When your agent fails to call a tool, you shouldn't have to spend hours discovering it was a parser format mismatch, a model capability ceiling, or a bad tool description. Xeter tells you immediately which layer broke and why.

Drop-in Python SDK. Works with any local model. No framework lock-in.

## What It Does

Xeter is a B2B SaaS observability platform that debugs AI agent tool-calling failures. It ingests OpenTelemetry spans from instrumented agent code, applies heuristic analysis (vector similarity between prompt and tool fields) to flag anomalous tool calls, and exposes a dashboard where developers can see what went wrong and why.

### Flag Types

- **wrong_tool** — agent picked the wrong tool for the prompt
- **wrong_tool_args** — right tool, wrong arguments
- **no_tool** — agent should have called a tool but didn't
- **excessive_tool** — too many tool calls for the task
- **parsing_error** — model output couldn't be parsed into a tool call

### Two-Layer Analysis

**Layer 1 (heuristic)** catches obvious mechanical failures fast and cheap — format mismatches, wrong-tool ranking via vector similarity, argument validation.

**Layer 2 (LLM supervisor)** explains ambiguous reasoning failures on-demand — why the agent chose that tool, what the prompt implied, what went wrong in the chain of thought. *(Scaffolded in v1, active in v2.)*

## Architecture

```
Customer Agent  ──SDK + OTel──▶  Analyser (ingestion + heuristics)
                                      │
                                      ▼
                              ┌───────────────┐
                              │  ClickHouse    │  spans (immutable, append-only)
                              │  PostgreSQL    │  flags, diagnostics, auth, tenants
                              │  MinIO (S3)    │  large payloads (prompt, response)
                              │  Redis         │  ingestion queue
                              └───────────────┘
                                      │
                                      ▼
                              Presenter (API) ◀── View (dashboard)
                                      │
                                      ▼
                              Diagnosticer (LLM, on-demand)
```

**Services:**
- **Analyser** — receives OTel spans, stores in ClickHouse, enqueues for async heuristic analysis
- **Presenter** — REST API for the dashboard and tenant management
- **View** — frontend dashboard (span list, flag indicators, detail views)
- **Diagnosticer** — LLM-powered root cause analysis (scaffolded, wired but inactive in v1)

**Storage:**
- **ClickHouse** — span storage with MergeTree `ORDER BY (tenant_id, trace_id, time_begin)`
- **PostgreSQL** — flags, diagnostics, auth (API keys, users, tenants) with Row Level Security
- **MinIO/S3** — large text payloads (prompt, response, available_tools) referenced by key
- **Redis** — decouples ingestion from embedding workers

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

# Start all services (PostgreSQL, ClickHouse, Redis, MinIO, Analyser, Presenter, View)
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

### Ports

| Service | Port |
|---------|------|
| Presenter (API) | 8000 |
| Analyser (ingestion) | 4318 |
| View (dashboard) | 3000 |
| PostgreSQL | 5432 |
| ClickHouse (HTTP) | 8123 |
| Redis | 6379 |
| MinIO (API) | 9100 |
| MinIO (Console) | 9101 |

## Multi-Tenancy

All tables enforce tenant isolation via PostgreSQL Row Level Security. Every query runs inside a `tenant_session()` that sets `SET LOCAL app.current_tenant_id` — the RLS policy filters rows automatically. The DAL layer raises `MissingTenantError` at the Python level before any database call if `tenant_id` is missing.

## Auth

- **SDK ingestion**: API key per tenant (bcrypt hash stored, plaintext returned once at registration)
- **Dashboard login**: email/password (bcrypt hashed)
- API keys use the `xtr_` prefix for identification

## Project Status

**Current:** Phase 1 (Foundation) complete — local dev environment, database schemas, DAL with tenant isolation, registration endpoint, dev bootstrap tooling.

**Next:** Span ingestion pipeline, heuristic flagging, dashboard.

## Documentation

- `documentation/xeterarc42_v0.5.md` — full arc42 architecture documentation
- `documentation/silent_failures_ai_agents.md` — problem space research
- `documentation/foundation_sprint/` — competitor analysis, positioning, hypothesis validation

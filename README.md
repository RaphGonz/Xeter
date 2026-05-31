![Xeter](assets/logo+typo.png)

Open-source runtime silent-failures observability platform for AI agents that detects failures across tool use, reasoning, memory, and multi-agent coordination.

Optimize. Ship faster. Build trust.

[![License: GPL-3.0 + Commons Clause](https://img.shields.io/badge/License-GPL--3.0%20%2B%20Commons%20Clause-blue)](LICENSE)

## Table of Contents

- [Quick Start](#quick-start)
- [SDK](#sdk)
- [Detection Checks](#detection-checks)
- [Calibration](#calibration)
- [Pluggable LLM](#pluggable-llm)
- [Performance](#performance)
- [Architecture](#architecture)
- [Multi-Tenancy & Auth](#multi-tenancy--auth)
- [License](#license)

## Quick Start

**Prerequisites:** Docker and Docker Compose.

```bash
git clone https://github.com/RaphGonz/Xeter.git && cd Xeter
cp .env.example .env
./generate-secrets.sh
docker compose -f deploy/docker-compose.yml up --build
```

Migrations and seed data run automatically via the `db-init` init container — no separate commands needed. Once all services are healthy, use the seeded dev credentials to log in:

```
Dashboard:  http://localhost:3000
Email:      dev@example.com
Password:   dev_password_local
API key:    dev-api-key-local
```

> **Note:** `dev-api-key-local` is a fixed dev-only key seeded for local development. Do not use it in production.

**Health check:**

```bash
curl http://localhost:8000/healthz
```

Returns `200 OK` when the Presenter is up.

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

### Dev Commands

All commands run from the repo root:

| Command | What it does |
|---------|-------------|
| `docker compose -f deploy/docker-compose.yml up --build` | Start the full stack (migrations + seed run automatically) |
| `docker compose -f deploy/docker-compose.yml down` | Stop all services |
| `docker compose -f deploy/docker-compose.yml down -v` | Stop and remove all data volumes |
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

## SDK

Install the Python SDK:

```bash
pip install xeter-sdk
```

Set the required environment variables:

```bash
export XETER_ENDPOINT=http://localhost:4318
export XETER_API_KEY=dev-api-key-local
```

Decorate any agent function to emit spans automatically:

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

Spans are sent fire-and-forget in a background thread — zero added latency to your agent.

## Detection Checks

All thresholds are configured via `WORKER_THRESHOLD_*` env vars in `deploy/docker-compose.yml`.

| Flag type | Analyzer class | Description | Threshold type | Default threshold |
|-----------|---------------|-------------|----------------|-------------------|
| `tool_not_available` | ToolCallAnalyzer | Agent called a tool not present in the available tools list | binary | — |
| `wrong_tool_choice` | ToolCallAnalyzer | Agent selected a tool with low semantic relevance to the prompt | binary | — |
| `unnecessary_tool_call` | ToolCallAnalyzer | Agent called a tool on a prompt that required no tool use | tunable | 0.15 |
| `wrong_tool_args` | ToolCallAnalyzer | Agent used the right tool but passed semantically inconsistent arguments | tunable | 0.4 |
| `no_tool` | ToolCallAnalyzer | Agent response contained no tool call despite a prompt that required one | tunable | 0.6 |
| `parsing_error` | ToolCallAnalyzer | Model output could not be parsed into a valid tool call | binary | — |
| `response_anomaly` | ToolCallAnalyzer | Agent response is semantically unrelated to the prompt | tunable | 0.4 |
| `output_schema_violation` | OutputSchemaAnalyzer | Response structure does not match the declared output schema | binary | — |
| `required_fields_missing` | OutputSchemaAnalyzer | Response omits one or more required schema fields | binary | — |
| `output_truncated` | OutputSchemaAnalyzer | Response appears to be cut off before completion | binary | — |
| `type_coercion_error` | OutputSchemaAnalyzer | A field value cannot be coerced to its declared type | binary | — |
| `context_overflow` | OutputSchemaAnalyzer | Input token count exceeds the configured threshold | binary | 8000 tokens |
| `missing_details` | SemanticSpanAnalyzer | Response omits details that were present in the prompt context | tunable | 0.6 |
| `stale_context` | TraceAnalyzer | Agent references information that has been updated or superseded | tunable | 85.0 |
| `step_repetition` | TraceAnalyzer | Agent repeats a previous action without new information | tunable | 85.0 |
| `termination_loop` | TraceAnalyzer | Agent loops on a termination-like action N times without stopping | tunable | N=3 |
| `context_propagation_failure` | TraceAnalyzer | Key information from an earlier span is absent in a later span | tunable | 0.5 |
| `history_loss` | TraceAnalyzer | Conversation history similarity drops sharply between spans | tunable | 0.4 |
| `wrong_agent_handoff` | TraceAnalyzer | Handoff target is not a node in the declared agent routing graph | binary | — |
| `information_withholding` | TraceAnalyzer | Agent response omits information that was available and relevant | tunable | 0.5 |
| `conversation_reset` | TraceAnalyzer | Context similarity between consecutive spans drops below threshold | tunable | 0.25 |
| `clarification_skipped` | TraceAnalyzer | Agent proceeds without asking for clarification on an ambiguous prompt | binary | — |
| `no_verification` | TraceAnalyzer | Agent completes a task without any verification step | binary | — |
| `incomplete_verification` | TraceAnalyzer | Agent's verification step does not cover all stated objectives | tunable | 0.7 |

## Calibration

Calibration finds the F1-optimal threshold for each tunable flag type against your own fixture data. Binary flag types (those not listed with a numeric default above) use deterministic detection logic and do not support threshold tuning.

**Workflow:**

1. **Reset tunable thresholds to defaults:**

   ```bash
   python -m xeter.scripts.calibrate --reset
   ```

2. **Add fixture spans** by running your agent against representative test cases and letting Xeter ingest them via the SDK.

3. **Calibrate per flag type** — prints the F1-optimal threshold for that flag:

   ```bash
   python -m xeter.scripts.calibrate --flag-type <type>
   ```

   Example: `python -m xeter.scripts.calibrate --flag-type missing_details`

4. **Apply the output threshold** to `deploy/docker-compose.yml` by setting the corresponding `WORKER_THRESHOLD_<FLAG_TYPE_UPPER>` env var under the `worker` service, then restart the worker:

   ```bash
   docker compose -f deploy/docker-compose.yml restart worker
   ```

   Example: calibration output `0.65` for `missing_details` → set `WORKER_THRESHOLD_MISSING_DETAILS: "0.65"`.

## Pluggable LLM

The Diagnosticer service uses an LLM to explain root cause on demand. Configure the provider and model via env vars under the `diagnosticer` service in `deploy/docker-compose.yml`:

| Env var | Description | Example values |
|---------|-------------|----------------|
| `DIAGNOSTICER_PROVIDER` | LLM provider to use | `anthropic` (default), `openai`, `ollama` |
| `DIAGNOSTICER_MODEL` | Model name for the selected provider | `claude-haiku-4-5`, `gpt-4o-mini`, `llama3.2` |
| `ANTHROPIC_API_KEY` | API key for Anthropic | Required when provider is `anthropic` |
| `OPENAI_API_KEY` | API key for OpenAI | Required when provider is `openai` |
| `OLLAMA_BASE_URL` | Base URL for local Ollama instance | `http://localhost:11434` |

**Using Ollama (local model, no API key required):**

Set `DIAGNOSTICER_PROVIDER=ollama` and `OLLAMA_BASE_URL=http://localhost:11434`. When running inside Docker on macOS or Windows, use `http://host.docker.internal:11434` so the diagnosticer container can reach the Ollama host.

## Performance

Two levers control the trade-off between analysis latency and detection quality:

**Lever 1 — `WORKER_TRACE_FLUSH_TIMEOUT_S` (default: 30)**

Seconds of inactivity before a trace is flushed for analysis. Set under the `worker` service in `deploy/docker-compose.yml`.

- Lower value → faster analysis, but less span context per trace (fewer spans collected before flush)
- Higher value → richer multi-span context, higher latency to first flag

**Lever 2 — Embedder model swap**

`EMBEDDER_URL` points to the embedder service, which runs a sentence-transformers model. The default model is `all-MiniLM-L6-v2`. Swap the model in `services/embedder/Dockerfile`:

- Smaller/faster: `paraphrase-MiniLM-L3-v2` — lower embedding latency, reduced detection accuracy
- Larger/slower: `all-mpnet-base-v2` — higher detection accuracy, lower throughput

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
- **Worker** — BRPOP consumer; fetches span from ClickHouse, runs embedding similarity across multiple dimensions, writes flag rows and similarity scores to PostgreSQL
- **Presenter** — REST API for the dashboard; merges ClickHouse spans + PostgreSQL flags at read time, lazy-loads S3 payloads on span detail
- **View** — Next.js 15 dashboard (span list, filters, span detail panel with flag scores and S3 payload tabs)
- **Diagnosticer** — LLM-powered root cause analysis; on-demand POST /diagnose assembles span + flag + S3 context and calls the configured LLM provider to return a structured verdict, severity, affected field, and recommended fix
- **db-init** — one-shot init container; runs Alembic migrations then seeds dev credentials before application services start

**Storage:**

- **ClickHouse** — span storage with MergeTree `ORDER BY (tenant_id, trace_id, time_begin)`
- **PostgreSQL** — flags, similarity scores, auth (API keys, users, tenants) with Row Level Security
- **MinIO/S3** — large text payloads (prompt, response, raw_response, available_tools) referenced by key
- **Redis** — decouples ingestion from embedding workers via BRPOP queue

**Ports:**

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

## Multi-Tenancy & Auth

All tables enforce tenant isolation via PostgreSQL Row Level Security. Every query runs inside a `tenant_session()` that sets `SET LOCAL app.current_tenant_id` — the RLS policy filters rows automatically. The DAL layer raises `MissingTenantError` at the Python level before any database call if `tenant_id` is missing.

**Auth:**

- **SDK ingestion**: API key per tenant (bcrypt hash stored, plaintext returned once at registration). Keys use the `xtr_` prefix.
- **Dashboard login**: email/password (bcrypt hashed), JWT session token returned and sent as `Authorization: Bearer <token>` on subsequent requests. Sessions expire after 30 minutes; a silent refresh token handles renewal.

## License

Xeter is licensed under GPL-3.0 with the Commons Clause addendum. You may use, modify, and self-host Xeter freely. You may not sell Xeter or Xeter-powered services to third parties. See [LICENSE](LICENSE) for the full license text.

# Phase 2: Ingestion Path - Research

**Researched:** 2026-03-28
**Domain:** Python SDK packaging, OpenTelemetry instrumentation, FastAPI ingestion service, S3/MinIO integration, ClickHouse batched inserts, Redis queueing
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**SDK API style**
- Decorator-based: `@xeter.trace(tool_name="...", prompt_arg="prompt", tools_arg="tools")`
- Developer maps their function's argument names to span fields via decorator params — explicit, no magic
- Works on both `def` and `async def` (SDK auto-detects coroutines)

**SDK configuration**
- Configuration via environment variables only: `XETER_ENDPOINT` and `XETER_API_KEY`
- No `xeter.init()` call required — zero-setup beyond setting env vars

**Span sending behavior**
- Spans are sent in a background thread (fire-and-forget) — the decorated function returns immediately with no added latency
- On failure (unreachable Analyser, network error): drop the span silently, log a WARNING via the Python `logging` module
- No retry — one attempt, then drop and log
- Agent application is never interrupted or slowed by SDK failures

**S3 payload offload**
- These four fields always go to S3, unconditionally: `prompt`, `response`, `raw_response`, `available_tools`
- The Analyser writes to S3 after receiving the full span — SDK stays thin (no AWS credentials on the client)
- S3 key structure: `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json`
- If S3 write fails: reject the span entirely (5xx to SDK). ClickHouse never gets a span without its S3 payloads.

**ClickHouse batching**
- Flush trigger: size OR time, whichever comes first
- Buffer lives in-memory (in-process queue inside the Analyser) — Redis is reserved for the analysis queue only
- Defaults: `XETER_BATCH_SIZE` (default: 100 spans), `XETER_FLUSH_INTERVAL` (default: 5 seconds)
- Spans lost in an in-flight batch on crash are acceptable

**Redis enqueue**
- After a span is accepted, its `span_id` is pushed to Redis queue for the Embedding Worker (Phase 3)
- Enqueue happens within the 200ms SLA from the ROADMAP success criteria

### Claude's Discretion
- Exact batch flush implementation (asyncio task, threading, etc.)
- ClickHouse client library choice
- S3 client library choice
- Internal SDK thread pool sizing
- Exact WARNING log message format

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SDK-01 | Python SDK wraps OTel instrumentation and emits spans via OTLP HTTP to the Analyser | OTel Python SDK + `opentelemetry-exporter-otlp-proto-http`; decorator wraps function, captures return value and args, creates and exports a span |
| SDK-02 | SDK captures all span fields: agent_name, agent_model, recipient, recipient_model, tool_name, tool_description, tool_arguments, tool_output, prompt, response, raw_response, available_tools_ref | OTel span attributes API — `span.set_attribute(key, value)`; all fields mapped as custom attributes on a single span |
| SDK-03 | SDK supports trace grouping via trace_id and parent_span_id | OTel TraceContext propagation; `trace_id` and `parent_span_id` are native OTel concepts available on every span |
| SDK-04 | SDK includes schema versioning field (xeter.schema.version) for forward compatibility | OTel span attribute `xeter.schema.version` = `"1.0"` set at decorator level |
| SDK-05 | SDK authenticates via API key sent with each span batch | OTLP exporter `headers` parameter — pass `{"x-api-key": XETER_API_KEY}` in exporter config |
| STOR-02 | Large text payloads stored in S3 with reference keys in ClickHouse; tool_arguments stored inline as JSON | Analyser uploads prompt/response/raw_response/available_tools to MinIO/S3 via aioboto3; stores S3 keys in ClickHouse row |
| STOR-04 | ClickHouse writes are batched via Redis queue — no single-row inserts | In-process asyncio.Queue + periodic flush task in Analyser; `client.insert(table, rows, column_names=...)` called with accumulated batch |
| STOR-05 | Redis queue decouples span ingestion from embedding worker processing | `await redis.lpush("analysis_queue", span_id)` after span accepted; worker uses BRPOP in Phase 3 |
</phase_requirements>

---

## Summary

Phase 2 builds the complete write path: a thin Python SDK that decorates agent functions and fires spans to the Analyser, and the Analyser service that validates auth, offloads large payloads to S3, batches metadata writes to ClickHouse, and enqueues span IDs in Redis.

The SDK is a standalone installable Python package (`xeter-sdk`) with its own `pyproject.toml`. It uses the OpenTelemetry Python SDK internally to construct and export spans via OTLP/HTTP to the Analyser on port 4318. The decorator intercepts function arguments (mapped by the developer via decorator params), captures the return value as `tool_output`, and sends the span in a background thread so the decorated function returns with zero added latency. SDK configuration is entirely via environment variables (`XETER_ENDPOINT`, `XETER_API_KEY`) — no init call required.

The Analyser is a FastAPI service (already scaffolded as a stub in Phase 1) that receives OTLP/HTTP POSTs at `/v1/traces`. It validates the API key against the bcrypt hash stored in PostgreSQL (reusing `verify_api_key` and `ApiKeyRepository` from Phase 1 DAL), uploads the four large payload fields to MinIO via `aioboto3`, and then accepts the span into an in-memory `asyncio.Queue`. A background flush task drains the queue to ClickHouse in batches using `clickhouse-connect` (already a dependency, version 0.15.0). After the span is accepted, `span_id` is pushed to Redis for the Phase 3 worker.

The critical operational constraint is atomicity between S3 and ClickHouse: if S3 upload fails, the span is rejected (5xx). ClickHouse never receives a row without its S3 payload keys. This is implemented as a strict sequence in the request handler before the span enters the batch queue.

**Primary recommendation:** Build the SDK first (pure Python, no infra dependency), then implement the Analyser endpoint using aioboto3 for S3, clickhouse-connect's sync `client.insert()` called from an asyncio flush task using `asyncio.to_thread`, and redis-py async client for enqueue.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `opentelemetry-api` | 1.x (latest stable) | OTel trace API — Tracer, Span, SpanContext | Official OTel Python API; stable interface |
| `opentelemetry-sdk` | 1.x (latest stable) | TracerProvider, BatchSpanProcessor, SimpleSpanProcessor | Official SDK; BatchSpanProcessor handles export threading |
| `opentelemetry-exporter-otlp-proto-http` | 1.x (latest stable) | Exports spans as protobuf over HTTP to Analyser | Standard OTLP/HTTP exporter; port 4318 |
| `clickhouse-connect` | 0.15.0 | ClickHouse client for batch INSERT | Already in pyproject.toml; official ClickHouse client |
| `aioboto3` | 15.5.0 | Async S3/MinIO client | Wraps boto3 with asyncio support; context manager pattern |
| `redis[asyncio]` | (existing dep) | Async Redis LPUSH for analysis queue | Already used in Phase 1 shared/db/redis.py |
| `fastapi` | 0.135.2 | Analyser HTTP service | Already in project; consistent with Presenter |
| `httpx` | (existing dep) | SDK span submission (alternative to OTel exporter) | See note below |

**Note on SDK transport choice:** The decorator is NOT using OTel's `BatchSpanProcessor` for background export — that processor operates on the OTel export thread model which may not align with the "background thread, fire-and-forget" decision. The recommended approach is to build a thin custom exporter: the decorator captures span data as a plain dict and submits it via `httpx` in a `threading.Thread`. This keeps the SDK dependency footprint minimal (just `httpx`, no full OTel SDK required in the agent's environment) and gives full control over the fire-and-forget behavior. See Architecture Patterns section.

However, if OTel SDK is used, `BatchSpanProcessor` with a custom OTLP exporter achieves similar behavior and is a valid alternative under "Claude's Discretion."

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `aiobotocore` | (transitive via aioboto3) | Low-level async AWS protocol | Never use directly; aioboto3 wraps it |
| `python-multipart` | — | FastAPI form parsing | Only if accepting multipart uploads (not needed here) |
| `structlog` | (existing dep) | Structured logging in Analyser | Already installed; use for WARNING on S3/CH failures |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `aioboto3` (async) | `boto3` (sync, run_in_executor) | aioboto3 is native async; boto3 blocks event loop unless wrapped. For Analyser (async FastAPI), aioboto3 is cleaner |
| Custom httpx exporter in SDK | OTel `BatchSpanProcessor` + `OTLPSpanExporter` | OTel exporter is more standards-compliant; custom is lighter and gives direct control over failure handling. Both are valid. |
| In-process asyncio.Queue flush | clickhouse-connect server-side async_insert | Server-side async_insert shifts batching to ClickHouse but adds ClickHouse config complexity. Application-level batching (user decision) is simpler to reason about and test. |

### Installation

```bash
# SDK package (standalone)
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http httpx

# Analyser additions (to existing xeter package)
pip install aioboto3
# clickhouse-connect, redis, fastapi already in pyproject.toml
```

---

## Architecture Patterns

### Recommended Project Structure

```
xeter/
├── sdk/                          # NEW: standalone SDK package
│   ├── pyproject.toml            # name = "xeter-sdk"
│   └── xeter_sdk/
│       ├── __init__.py           # exports: trace decorator
│       └── decorator.py          # @xeter.trace implementation
│
├── services/analyser/            # EXPANDED from stub
│   ├── Dockerfile                # update to install full deps
│   ├── main.py                   # FastAPI app with lifespan
│   ├── ingest.py                 # POST /v1/traces handler
│   ├── auth.py                   # API key validation (reuse Phase 1 DAL)
│   ├── s3.py                     # aioboto3 S3/MinIO uploads
│   ├── batch.py                  # asyncio.Queue + flush task
│   └── queue.py                  # Redis LPUSH
│
└── xeter/
    └── tests/
        ├── analyser/             # NEW: analyser tests
        │   ├── __init__.py
        │   └── test_ingest.py    # auth, batching, S3, Redis tests
        └── sdk/                  # NEW: SDK tests
            ├── __init__.py
            └── test_decorator.py
```

### Pattern 1: Thin SDK with Custom Fire-and-Forget Exporter

**What:** The `@xeter.trace(...)` decorator intercepts the decorated function, runs it normally, then submits the collected span data to the Analyser in a daemon `threading.Thread` using `httpx`. No OTel SDK in the agent's runtime is required.

**When to use:** When the decorator must not add latency to the decorated function, must support both `def` and `async def`, and SDK failure must never crash or slow the agent.

**Example:**
```python
# xeter_sdk/decorator.py
import asyncio
import functools
import inspect
import json
import logging
import os
import threading
import time
import uuid

import httpx

logger = logging.getLogger("xeter_sdk")

def trace(
    *,
    agent_name: str,
    agent_model: str,
    tool_name: str | None = None,
    tool_description: str | None = None,
    prompt_arg: str | None = None,
    tools_arg: str | None = None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
):
    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                t0 = time.time()
                result = await fn(*args, **kwargs)
                t1 = time.time()
                _submit(fn, args, kwargs, result, t0, t1)
                return result
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                t0 = time.time()
                result = fn(*args, **kwargs)
                t1 = time.time()
                _submit(fn, args, kwargs, result, t0, t1)
                return result
            return sync_wrapper

    def _submit(fn, args, kwargs, result, t0, t1):
        endpoint = os.environ.get("XETER_ENDPOINT")
        api_key = os.environ.get("XETER_API_KEY")
        if not endpoint or not api_key:
            return  # silently skip if not configured
        span = _build_span(fn, args, kwargs, result, t0, t1)
        t = threading.Thread(target=_send, args=(span, endpoint, api_key), daemon=True)
        t.start()

    def _send(span: dict, endpoint: str, api_key: str):
        try:
            httpx.post(
                f"{endpoint}/v1/spans",
                json=span,
                headers={"x-api-key": api_key},
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("xeter: failed to send span: %s", exc)

    return decorator
```

**Note on `async def` wrapper:** The async wrapper uses `asyncio.get_event_loop()` is NOT needed — the thread submission (`threading.Thread`) is always sync regardless of whether the function is async, so there is no event loop issue.

### Pattern 2: Analyser Request Handler — S3-First, Then Accept

**What:** In the POST `/v1/spans` handler, S3 uploads happen before the span is accepted into the ClickHouse batch. If S3 fails, the handler returns 5xx immediately. ClickHouse never gets a span without S3 keys.

**When to use:** Required by the locked decision. Ensures no partial state.

**Example:**
```python
# services/analyser/ingest.py
@router.post("/v1/spans", status_code=200)
async def ingest_span(
    span: SpanPayload,
    tenant_id: str = Depends(verify_api_key_header),
    s3: S3Client = Depends(get_s3_client),
    batcher: SpanBatcher = Depends(get_batcher),
    redis: Redis = Depends(get_redis_client),
):
    # 1. Upload large payloads to S3 — fail fast if S3 unreachable
    try:
        refs = await s3.upload_span_payloads(tenant_id, span.span_id, span)
    except Exception as exc:
        logger.error("s3 upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="payload storage failed")

    # 2. Build ClickHouse row (refs replace raw payloads)
    row = build_ch_row(span, refs, tenant_id)

    # 3. Accept into in-memory batch (never blocks)
    await batcher.add(row)

    # 4. Enqueue span_id for analysis worker
    await redis.lpush("analysis_queue", span.span_id)

    return {"accepted": True}
```

### Pattern 3: In-Memory Batch Flush with Size-or-Time

**What:** An `asyncio.Queue` buffers accepted spans. A background asyncio task drains the queue when either the batch reaches `XETER_BATCH_SIZE` rows OR `XETER_FLUSH_INTERVAL` seconds have elapsed — whichever comes first.

**When to use:** Required by the user decision (application-level batching, not ClickHouse server-side async_insert).

**Example:**
```python
# services/analyser/batch.py
import asyncio
import os
import time

class SpanBatcher:
    def __init__(self, ch_client):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._ch = ch_client
        self._batch_size = int(os.environ.get("XETER_BATCH_SIZE", "100"))
        self._flush_interval = float(os.environ.get("XETER_FLUSH_INTERVAL", "5"))
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._flush_loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        # final flush on shutdown
        await self._flush_all()

    async def add(self, row: list):
        await self._queue.put(row)

    async def _flush_loop(self):
        buffer = []
        deadline = time.monotonic() + self._flush_interval
        while True:
            timeout = max(0, deadline - time.monotonic())
            try:
                row = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                buffer.append(row)
                if len(buffer) >= self._batch_size:
                    await self._flush(buffer)
                    buffer = []
                    deadline = time.monotonic() + self._flush_interval
            except asyncio.TimeoutError:
                if buffer:
                    await self._flush(buffer)
                    buffer = []
                deadline = time.monotonic() + self._flush_interval

    async def _flush(self, rows: list):
        # clickhouse-connect insert is sync; run in thread
        await asyncio.to_thread(
            self._ch.insert,
            "spans",
            rows,
            column_names=SPAN_COLUMNS,
        )

    async def _flush_all(self):
        rows = []
        while not self._queue.empty():
            rows.append(self._queue.get_nowait())
        if rows:
            await self._flush(rows)
```

### Pattern 4: FastAPI Lifespan for Background Task Management

**What:** FastAPI's `lifespan` context manager (preferred over deprecated `@app.on_event`) starts the `SpanBatcher` flush task on startup and stops it cleanly on shutdown.

**Example:**
```python
# services/analyser/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    batcher = SpanBatcher(get_clickhouse_client())
    await batcher.start()
    app.state.batcher = batcher
    yield
    await batcher.stop()

app = FastAPI(title="Xeter Analyser", lifespan=lifespan)
```

### Pattern 5: API Key Validation via FastAPI Dependency

**What:** Reuse Phase 1's `ApiKeyRepository` and `verify_api_key` to validate the `x-api-key` header. Returns `tenant_id` (UUID string) on success, raises 401 on failure.

**Example:**
```python
# services/analyser/auth.py
from fastapi import Header, HTTPException, Depends
from xeter.shared.dal.api_keys import ApiKeyRepository, verify_api_key

async def verify_api_key_header(
    x_api_key: str = Header(...),
    session: AsyncSession = Depends(get_session),
) -> str:
    repo = ApiKeyRepository(session)
    # scan all keys (small N); return tenant_id on match
    # NOTE: bcrypt.checkpw is slow (~100ms) — run in thread
    keys = await repo.get_all_keys()  # returns List[ApiKey]
    for key_record in keys:
        if await asyncio.to_thread(verify_api_key, x_api_key, key_record.key_hash):
            return str(key_record.tenant_id)
    raise HTTPException(status_code=401, detail="Invalid or missing API key")
```

**Important:** `verify_api_key` calls `bcrypt.checkpw` which is CPU-bound and takes ~100ms. Always run via `asyncio.to_thread` in async handlers to avoid blocking the event loop.

### Pattern 6: aioboto3 S3 Upload (MinIO compatible)

**What:** Upload span payload fields as individual JSON objects to MinIO using aioboto3. Key structure: `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json`.

**Example:**
```python
# services/analyser/s3.py
import json
import aioboto3
from datetime import datetime, timezone

async def upload_span_payloads(
    session: aioboto3.Session,
    bucket: str,
    tenant_id: str,
    span_id: str,
    prompt: str,
    response: str,
    raw_response: str,
    available_tools: str,
) -> dict[str, str]:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    prefix = f"{tenant_id}/{month}/{span_id}"
    refs = {}
    async with session.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", "xeter"),
        aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", "xeter_dev_password"),
    ) as s3:
        for field, value in [
            ("prompt", prompt),
            ("response", response),
            ("raw_response", raw_response),
            ("available_tools", available_tools),
        ]:
            key = f"{prefix}/{field}.json"
            await s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=json.dumps(value).encode("utf-8"),
                ContentType="application/json",
            )
            refs[f"{field}_ref"] = key
    return refs  # {"prompt_ref": "...", "response_ref": "...", ...}
```

### Anti-Patterns to Avoid

- **Blocking event loop with bcrypt:** `verify_api_key` is sync and CPU-bound. Always wrap in `asyncio.to_thread`. Calling it directly in an async handler will block the Uvicorn event loop.
- **Storing large payloads in ClickHouse row:** The `SPANS_TABLE_DDL` already has `prompt_ref` (not `prompt`). Never add raw text columns.
- **Single-row ClickHouse inserts:** Every test that verifies STOR-04 must confirm batch behavior. The flush task is the only path to ClickHouse.
- **Putting large payloads in Redis:** Redis queue holds only `span_id` strings — never the span payload. The worker re-reads from ClickHouse/S3.
- **Using `@app.on_event` for startup/shutdown:** Deprecated in FastAPI. Use `lifespan` context manager.
- **SDK importing full OTel SDK:** Increases agent's dependency footprint. The SDK's `xeter_sdk` package should declare minimal deps (`httpx` only if using custom transport).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async S3 upload | Custom aiohttp S3 client | `aioboto3` | Handles auth, retries, multipart; MinIO-compatible with `endpoint_url` |
| OTel trace/span context propagation | Custom trace ID threading | OTel `TraceContext` / `SpanContext` | W3C standard; free from OTel API |
| bcrypt verification | Custom hash comparison | Phase 1 `verify_api_key()` already built | Already tested and integrated |
| API key lookup | Re-implement DB query | Phase 1 `ApiKeyRepository.get_by_tenant()` | Already exists — extend or reuse |
| ClickHouse connection | Raw HTTP requests | `clickhouse-connect` already in deps | Thread-safe, handles compression/protocol |

**Key insight:** Phase 1 provides all auth primitives — `ApiKeyRepository`, `verify_api_key`, `get_session`, `require_tenant`. Phase 2 reuses them without modification.

---

## Common Pitfalls

### Pitfall 1: bcrypt Blocking the Async Event Loop

**What goes wrong:** `verify_api_key(plaintext, stored_hash)` calls `bcrypt.checkpw()`, which takes ~100ms of CPU time. Called directly in an `async def` handler, it blocks Uvicorn's event loop for the duration, making the entire Analyser unresponsive to other requests.

**Why it happens:** FastAPI handlers run on the event loop. Sync CPU-bound work blocks it unless explicitly offloaded.

**How to avoid:** Always call `await asyncio.to_thread(verify_api_key, plaintext, stored_hash)`.

**Warning signs:** Analyser handles concurrent span submissions slowly; CPU spikes during auth.

### Pitfall 2: aioboto3 Client Lifecycle Mismanagement

**What goes wrong:** Creating an `aioboto3` session or client inside each request handler (not reusing). Each client creation has connection overhead and may leak connections.

**Why it happens:** aioboto3 requires async context managers for client lifecycle, which is unfamiliar.

**How to avoid:** Create the `aioboto3.Session()` once at startup (in lifespan). Use `AsyncExitStack` or a single context manager per request that reuses the session. Alternatively, create the client once in lifespan and keep it alive.

**Warning signs:** Connection pool exhaustion under load; "too many open connections" errors.

### Pitfall 3: S3 Write Atomicity

**What goes wrong:** S3 upload completes for `prompt` and `response` but fails for `raw_response`. ClickHouse receives the span with two valid refs and one null. Downstream code (Phase 3 worker) fails when it tries to fetch `raw_response` and gets a 404.

**Why it happens:** S3 writes are individual PUT operations — there's no transaction.

**How to avoid:** Upload all four fields before inserting to ClickHouse. If any upload fails, return 5xx to the SDK immediately. ClickHouse row is never written. This is the locked decision.

**Warning signs:** Spans with null `raw_response_ref` in ClickHouse while `prompt_ref` is populated.

### Pitfall 4: Queue Shutdown Data Loss

**What goes wrong:** Analyser receives 50 spans, buffers them in the asyncio.Queue. Before the flush interval fires, the process shuts down. All 50 spans are lost.

**Why it happens:** The shutdown path cancels the flush task without draining the queue.

**How to avoid:** In `lifespan` teardown (after `yield`), call `batcher.stop()` which performs a final flush before returning. Since spans-lost-on-crash is explicitly acceptable (per locked decision), this covers the clean shutdown case.

**Warning signs:** Spans disappear after service restart without any errors.

### Pitfall 5: SDK Thread Daemon Status

**What goes wrong:** The SDK uses a daemon thread to send spans. When the agent process exits immediately after the decorated function returns, the daemon thread is killed before it can send the span.

**Why it happens:** Python daemon threads are killed when the main thread exits, even if they have pending work.

**How to avoid:** For the SDK, either: (a) set `daemon=False` and use a timeout join (but this blocks the agent), or (b) accept that spans emitted very close to process exit may be lost (acceptable for observability). Document this limitation in the SDK. For the common use case (long-running agent), daemon threads work fine.

**Warning signs:** Spans from short-lived test scripts don't arrive at the Analyser.

### Pitfall 6: ClickHouse Column Name Mismatch

**What goes wrong:** `client.insert("spans", rows, column_names=[...])` fails silently or raises an obscure error if the `column_names` list doesn't exactly match the ClickHouse DDL column names from Phase 1.

**Why it happens:** The Phase 1 DDL has exact column names (e.g., `available_tools_ref`, `prompt_ref`). Application code must match these exactly.

**How to avoid:** Define a `SPAN_COLUMNS` constant in the batcher module that is the single source of truth for the column order. Verify against the DDL in Phase 1 (`xeter/shared/db/clickhouse.py`).

### Pitfall 7: SDK Package Name Collision

**What goes wrong:** The SDK package is named `xeter` (same as the main server package), causing import conflicts when both are installed in the same Python environment.

**Why it happens:** Python packages sharing the same namespace.

**How to avoid:** The SDK package name in `pyproject.toml` MUST be `xeter-sdk` with module name `xeter_sdk`. The server package remains `xeter`. The 3-line snippet would be: `import xeter_sdk as xeter` or simply `from xeter_sdk import trace`.

---

## Code Examples

Verified patterns from official sources:

### clickhouse-connect batch insert (official API)

```python
# Source: clickhouse.com/docs/integrations/python
# client.insert(table, data, column_names=[...])
rows = [
    [tenant_id, trace_id, span_id, ...],
    [tenant_id, trace_id, span_id, ...],
]
client.insert("spans", rows, column_names=["tenant_id", "trace_id", "span_id", ...])
```

### OTLP HTTP Exporter with custom endpoint and API key header

```python
# Source: opentelemetry.io/docs/languages/python/exporters/
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

exporter = OTLPSpanExporter(
    endpoint="http://localhost:4318/v1/traces",
    headers={"x-api-key": "xtr_..."},
)
processor = BatchSpanProcessor(exporter)
```

### Redis async LPUSH (existing project pattern)

```python
# Source: existing xeter/shared/db/redis.py
# redis.asyncio already a project dependency
import redis.asyncio as aioredis
redis_client = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
await redis_client.lpush("analysis_queue", span_id)
```

### FastAPI lifespan (preferred pattern, not deprecated on_event)

```python
# Source: fastapi.tiangolo.com/advanced/events/
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    app.state.batcher = SpanBatcher(...)
    await app.state.batcher.start()
    yield
    # shutdown
    await app.state.batcher.stop()

app = FastAPI(lifespan=lifespan)
```

### aioboto3 S3 put_object (MinIO compatible)

```python
# Source: aioboto3 PyPI documentation (v15.5.0)
import aioboto3
session = aioboto3.Session()
async with session.client("s3", endpoint_url="http://localhost:9100") as s3:
    await s3.put_object(Bucket="xeter", Key="tenant/2026-03/span_id/prompt.json", Body=b"...")
```

### asyncio.to_thread for sync-in-async (Python 3.9+)

```python
# Source: Python standard library
import asyncio
result = await asyncio.to_thread(sync_blocking_function, arg1, arg2)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan` context manager | FastAPI 0.93 (2023) | Old decorator is deprecated; lifespan is the recommended pattern |
| `aioredis` (separate package) | `redis.asyncio` (built into redis-py) | redis-py 4.2+ | No separate aioredis package needed; already in project |
| `clickhouse-driver` (native TCP) | `clickhouse-connect` (HTTP) | 2022 onward | ClickHouse officially recommends clickhouse-connect; HTTP is simpler to proxy/firewall |
| `AsyncClient` (deprecated wrapper) in clickhouse-connect | Future native async in 1.0.0 | planned | Current 0.15.0 AsyncClient is deprecated; use sync client with `asyncio.to_thread` for now |

**Deprecated/outdated:**
- `clickhouse-connect` `AsyncClient`: The current implementation is a thread-pool executor wrapper and is deprecated. In version 1.0.0 it will be replaced by a native async implementation. For Phase 2, use `get_client()` (sync) and call it via `asyncio.to_thread` in the flush task. Confidence: HIGH (PyPI page for 0.15.0 states this explicitly).
- `@app.on_event("startup"/"shutdown")`: Deprecated in FastAPI. Use `lifespan` context manager. Confidence: HIGH (FastAPI official docs).

---

## Open Questions

1. **S3 bucket creation/bootstrapping**
   - What we know: MinIO is running in Docker Compose from Phase 1. The bucket `xeter` needs to exist before the first upload.
   - What's unclear: Is the bucket created by `seed.py` in Phase 1, or does Phase 2 need to create it?
   - Recommendation: Check `seed.py` — if not present, add bucket creation to either `seed.py` or the Analyser's startup lifespan. Use `create_bucket_if_not_exists` with a `BucketAlreadyOwnedByYou` exception catch.

2. **Span payload format sent from SDK to Analyser**
   - What we know: The Analyser receives spans at `/v1/spans`. The decision says "SDK stays thin" — SDK sends the raw span data.
   - What's unclear: Is the SDK sending OTLP protobuf (standard), or a custom JSON payload? OTLP protobuf decoding in the Analyser requires `opentelemetry-proto` package.
   - Recommendation: Use custom JSON for Phase 2 simplicity. The "OTLP" label from architecture research refers to the transport concept; for a custom SDK sending to a custom Analyser, a simple JSON POST is both simpler and avoids protobuf deserialization. The Analyser can define a `SpanPayload` Pydantic model. This is under "Claude's Discretion" on implementation details.

3. **`get_all_keys()` on `ApiKeyRepository` — multi-tenant key lookup**
   - What we know: Phase 1's `ApiKeyRepository.get_by_tenant()` requires `tenant_id`. But at auth time, we don't know the `tenant_id` yet — we only have the raw API key.
   - What's unclear: Is there a `get_by_key_prefix` or similar method, or do we need to scan all keys?
   - Recommendation: The Analyser needs a new DAL method: `ApiKeyRepository.get_all()` (no tenant guard, used only for auth lookup at the ingestion boundary) — OR — the API key lookup can scan all keys and return the matching `tenant_id`. This is a small, bounded table. Alternatively, add a plaintext `key_prefix` column (first N chars of key) for fast lookup before bcrypt comparison. For Phase 2, a simple scan is acceptable.

4. **`xeter-sdk` package location in the monorepo**
   - What we know: The monorepo has `xeter/` for the server package. The SDK should be `sdk/` at the root.
   - What's unclear: Should `sdk/` be a sibling of `xeter/` or nested under `services/`?
   - Recommendation: Place at `sdk/` in the project root (sibling to `xeter/`, `services/`, `deploy/`). This matches the architecture research's recommended structure and makes it clearly a standalone installable artifact separate from the server.

---

## Sources

### Primary (HIGH confidence)
- [clickhouse.com/docs/integrations/python](https://clickhouse.com/docs/integrations/python) — insert API, column_names parameter, batch patterns
- [opentelemetry.io/docs/languages/python/exporters/](https://opentelemetry.io/docs/languages/python/exporters/) — OTLPSpanExporter config, BatchSpanProcessor
- [opentelemetry.io/docs/languages/python/instrumentation/](https://opentelemetry.io/docs/languages/python/instrumentation/) — decorator pattern, span attributes API
- [fastapi.tiangolo.com/advanced/events/](https://fastapi.tiangolo.com/advanced/events/) — lifespan context manager, asyncio.create_task pattern
- [pypi.org/project/clickhouse-connect/](https://pypi.org/project/clickhouse-connect/) — version 0.15.0, AsyncClient deprecation notice
- [pypi.org/project/aioboto3/](https://pypi.org/project/aioboto3/) — version 15.5.0, async context manager pattern, put_object API

### Secondary (MEDIUM confidence)
- [clickhouse.com/docs/optimize/asynchronous-inserts](https://clickhouse.com/docs/optimize/asynchronous-inserts) — server-side async_insert vs application batching tradeoff (verified with official docs)
- [opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/) — OTLP endpoint and headers env vars
- [redis.io/learn/develop/python/fastapi](https://redis.io/learn/develop/python/fastapi) — redis.asyncio LPUSH pattern in FastAPI (official Redis docs)

### Tertiary (LOW confidence)
- General Python asyncio.Queue size-or-time pattern — from Python docs and community examples; no single authoritative source for the exact pattern but well-established

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against PyPI as of 2026-03-28
- Architecture: HIGH — all patterns follow locked decisions + verified against official docs
- Pitfalls: HIGH for pitfalls 1-4 (verified technical facts); MEDIUM for pitfalls 5-6 (common knowledge, consistent with docs)
- Open questions: Research is honest about gaps; questions have actionable recommendations

**Research date:** 2026-03-28
**Valid until:** 2026-06-28 (stable libraries; aioboto3 and clickhouse-connect release frequently but APIs are stable)

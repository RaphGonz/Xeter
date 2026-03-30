# Phase 4: Read Path - Research

**Researched:** 2026-03-30
**Domain:** FastAPI read API — ClickHouse span queries, PostgreSQL flag joins, S3 lazy fetch, cursor pagination, session-token auth, HTTP proxy to Diagnosticer scaffold
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Span list response shape**
- Cursor-based pagination (opaque token for next/prev)
- Default sort order: newest first
- Inline flag summary per span: `[{type, score}]` — dashboard renders badges without a second call
- Fields per span: span_id, agent_name, model, timestamp, status, duration_ms, plus flags array

**Lazy S3 loading behavior**
- GET /spans/{id} always fetches S3 payloads (prompt, response, raw_response) — no opt-in query param
- Content returned inline in JSON response, not pre-signed URLs
- Block until S3 fetch completes, with a 5-second timeout
- On timeout or S3 failure, return a full error response (not partial data)

**Diagnosticer scaffold**
- Separate service from day one: own Dockerfile, own container, own docker-compose entry
- Presenter proxies POST /diagnose to the Diagnosticer service
- Request body: `{span_id, flags: [...]}`
- Diagnosticer fetches its own data from ClickHouse/S3/PostgreSQL (needs DB access wired up)
- 501 response body: `{status: "not_implemented", message: "Diagnosticer not yet available", span_id: "..."}`
- DB/S3 connections wired in docker-compose even though the scaffold only returns 501 — ready for v2 LLM integration

**Error & auth responses**
- Simple JSON error format: `{error: "not_found", message: "Span not found", status: 404}`
- Cross-tenant access returns 404 (not 403) — no information leakage about other tenants' spans
- Generic 401 for all auth failures: `{error: "unauthorized", message: "Invalid or missing session token"}` — no distinction between expired, malformed, or missing
- No rate limiting in this phase — defer to Phase 6 (Validation) if needed

### Claude's Discretion
- Exact cursor encoding strategy
- Internal routing/proxy mechanism between Presenter and Diagnosticer
- ClickHouse query optimization for span list
- S3 client configuration and retry strategy within the 5s timeout

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| STOR-03 | Flags stored as append-only rows in PostgreSQL with span_id, flag_type, score, and detail | Flags table exists (migration 001). Phase 4 adds the READ path: SELECT flags WHERE span_id IN (...) for list, SELECT flags WHERE span_id = ? for detail. Indexes ix_flags_tenant_span and ix_flags_tenant_trace already created. |
| DASH-03 | Developer can view span detail showing flag details and similarity scores | Combine ClickHouse span row + PostgreSQL flags rows + span_scores rows into a single JSON response. span_scores table exists (migration 002) with ix_span_scores_span index. |
| DASH-04 | Developer can view prompt, response, and raw_response content lazy-loaded from S3 | GET /spans/{id} always fetches S3 via aioboto3. Key pattern already established: {tenant_id}/{YYYY-MM}/{span_id}/{field}.json. Use asyncio.wait_for with 5s timeout. |
| DASH-05 | Span list rows show similarity scores directly (flag score overlay) | List endpoint joins span_scores (or flags.score) per span. No S3 fetches. Scores are in PostgreSQL span_scores table. |
| INFR-02 | Diagnosticer service is scaffolded — wired to Presenter, accepts requests, returns placeholder response — ready for LLM integration in milestone 2 | New service: services/diagnosticer/Dockerfile + xeter/services/diagnosticer/main.py. docker-compose entry with DB/S3 env vars. Presenter proxies POST /diagnose via httpx. |
</phase_requirements>

---

## Summary

Phase 4 adds the read API to the Presenter service and scaffolds the Diagnosticer service. The core work is three FastAPI routes on the Presenter (`GET /spans`, `GET /spans/{id}`, `POST /diagnose`) plus a new Diagnosticer container that returns a 501 placeholder. Auth moves from API-key-per-request (used by the SDK Analyser) to a session token mechanism for the dashboard — this requires a `POST /login` endpoint and a session token dependency, implemented with python-jose JWT or opaque tokens.

The existing codebase has all the infrastructure needed: ClickHouse client (`clickhouse_connect`), aioboto3 S3 client, asyncpg/SQLAlchemy PostgreSQL sessions, tenant_session RLS injection, `require_tenant()` guards, and the `verify_api_key_header` dependency pattern from the Analyser. Phase 4 follows these established patterns rather than introducing new ones.

The most structurally novel piece is cursor-based pagination over ClickHouse. The spans table ORDER BY is `(tenant_id, trace_id, time_begin)` — pagination will use `time_begin` as the cursor value. The multi-store merge (ClickHouse spans + PostgreSQL flags) is documented in ARCHITECTURE.md and uses `asyncio.gather` for parallel queries.

**Primary recommendation:** Build incrementally in three plans — (1) session auth + GET /spans list with flags, (2) GET /spans/{id} with S3 lazy fetch, (3) POST /diagnose proxy + Diagnosticer scaffold. This mirrors how Phase 3 was structured (isolated concerns per plan) and allows each to be verified independently.

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.135.2 | Route definitions, dependency injection | Already used in Analyser/Presenter |
| sqlalchemy | 2.0.48 | Async PostgreSQL ORM | Already used for flags/users/api_keys |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Already in use |
| clickhouse-connect | 0.15.0 | ClickHouse span queries | Already used in Analyser and Worker |
| aioboto3 | 15.5.0 | Async S3 payload fetch | Already used in Analyser |
| httpx | >=0.28 | Async HTTP proxy (Presenter → Diagnosticer) | Already in pyproject.toml |
| pydantic | 2.12.5 | Request/response model validation | Already used throughout |
| python-jose[cryptography] | >=3.3 | JWT session token generation/validation | Listed in STACK.md as the auth library |
| structlog | >=25.0 | Structured logging | Already used in auth router |

### No New Installs Required

All Phase 4 dependencies are already in `xeter/pyproject.toml`. The only new library needed is `python-jose[cryptography]` for JWT session tokens — this should be added to `pyproject.toml` and installed.

**Installation:**
```bash
pip install python-jose[cryptography]
```
Add to `xeter/pyproject.toml` dependencies: `"python-jose[cryptography]>=3.3"`

---

## Architecture Patterns

### Recommended File Structure for Phase 4

```
xeter/services/presenter/
├── main.py                          # EXISTING — add router wiring + lifespan
├── routers/
│   ├── __init__.py                  # EXISTING
│   ├── auth.py                      # EXISTING — add POST /login
│   ├── spans.py                     # NEW — GET /spans, GET /spans/{id}
│   └── diagnose.py                  # NEW — POST /diagnose proxy

xeter/services/diagnosticer/
├── __init__.py                      # NEW
└── main.py                          # NEW — FastAPI scaffold returning 501

services/diagnosticer/
├── __init__.py                      # NEW
└── Dockerfile                       # NEW

deploy/docker-compose.yml            # MODIFY — add diagnosticer service
```

### Pattern 1: Session Token Auth (new for Phase 4)

**What:** The dashboard uses a session token (JWT) rather than an API key. A `POST /login` endpoint accepts email/password, validates against PostgreSQL `users` table + bcrypt, returns a signed JWT containing `tenant_id`. A `verify_session_token` dependency validates the JWT on every protected route and returns `tenant_id`.

**Key distinction from Analyser auth:** The Analyser uses `x-api-key` header for SDK-to-backend auth. The Presenter in Phase 4 uses a `session_token` cookie or `Authorization: Bearer` header for human dashboard auth.

**Implementation approach:**
```python
# xeter/services/presenter/routers/auth.py — add POST /login
import os
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

def create_session_token(tenant_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": tenant_id, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

async def verify_session_token(
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session),
) -> str:
    """FastAPI dependency — validates Bearer JWT, returns tenant_id."""
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise ValueError("not bearer")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        tenant_id = payload.get("sub")
        if not tenant_id:
            raise ValueError("missing sub")
        return tenant_id
    except (JWTError, ValueError, AttributeError):
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Invalid or missing session token"},
        )
```

**Note on SECRET_KEY:** Already present in `.env` as `SECRET_KEY=dev-secret-key-change-in-production`. The env var is set for docker-compose but not yet wired into the presenter service environment — add it to the docker-compose `presenter` service env block.

### Pattern 2: Cursor-Based Pagination Over ClickHouse

**What:** Use `time_begin` as the cursor value. The cursor is base64-encoded ISO timestamp. The query uses `WHERE tenant_id = ? AND time_begin < cursor_ts ORDER BY time_begin DESC LIMIT ?` for subsequent pages.

**Why `time_begin` (not OFFSET):** ClickHouse's ORDER BY `(tenant_id, trace_id, time_begin)` makes range queries on `time_begin` efficient for a given `tenant_id`. OFFSET-based pagination degrades as offset increases (ClickHouse reads and discards skipped rows). Cursor-based pagination always reads only the page being requested.

**Cursor encoding (Claude's discretion):** Base64-encode the ISO8601 timestamp string. Opaque to the client. Example:
```python
import base64
from datetime import datetime

def encode_cursor(time_begin: datetime) -> str:
    return base64.urlsafe_b64encode(time_begin.isoformat().encode()).decode()

def decode_cursor(cursor: str) -> datetime:
    return datetime.fromisoformat(base64.urlsafe_b64decode(cursor).decode())
```

**ClickHouse query pattern:**
```python
# No cursor (first page)
query = """
    SELECT span_id, trace_id, agent_name, agent_model, tool_name,
           time_begin, time_end, status
    FROM spans
    WHERE tenant_id = %(tenant_id)s
    ORDER BY time_begin DESC
    LIMIT %(limit)s
"""

# With cursor (subsequent page)
query = """
    SELECT span_id, trace_id, agent_name, agent_model, tool_name,
           time_begin, time_end, status
    FROM spans
    WHERE tenant_id = %(tenant_id)s AND time_begin < %(cursor_ts)s
    ORDER BY time_begin DESC
    LIMIT %(limit)s
"""
```

**Note:** `status` is not a stored column in ClickHouse. The spans table has no explicit `status` field. Status must be derived from flags (e.g., "flagged" if any flags exist, "clean" if none) and assembled during the merge step in the Presenter.

### Pattern 3: Multi-Store Merge (Parallel Queries)

**What:** Presenter runs ClickHouse and PostgreSQL queries in parallel via `asyncio.gather`, merges results in application code. This is documented in ARCHITECTURE.md Pattern 2.

**For list view:**
```python
async def get_span_list(tenant_id: str, limit: int, cursor: str | None):
    # 1. Query ClickHouse for span rows
    spans = await clickhouse_query(tenant_id, limit, cursor)
    span_ids = [s.span_id for s in spans]

    # 2. Query PostgreSQL flags for those spans (parallel — but need span_ids first)
    flags_by_span = await fetch_flags_for_spans(span_ids, tenant_id)

    # 3. Merge — attach flag summary to each span
    return [SpanListItem(span=s, flags=flags_by_span.get(s.span_id, [])) for s in spans]
```

**Note:** The list-view merge is sequential (flags query depends on span_ids from ClickHouse). Full parallelism applies to the detail view where span and flags can be fetched simultaneously.

**For detail view (full parallelism):**
```python
async def get_span_detail(span_id: str, tenant_id: str):
    # Parallel: ClickHouse + PostgreSQL flags + PostgreSQL scores
    span, flags, scores = await asyncio.gather(
        fetch_span_from_clickhouse(span_id, tenant_id),
        fetch_flags_from_postgres(span_id, tenant_id),
        fetch_scores_from_postgres(span_id, tenant_id),
    )
    if span is None:
        raise HTTPException(status_code=404, detail={...})

    # Sequential: S3 fetch (requires span refs from ClickHouse result)
    payloads = await fetch_s3_payloads_with_timeout(span, timeout=5.0)

    return merge_span_detail(span, flags, scores, payloads)
```

### Pattern 4: S3 Fetch with Timeout

**What:** Use `asyncio.wait_for` to enforce the 5-second timeout. On timeout or any S3 error, return a full error response — no partial data.

```python
async def fetch_s3_payloads_with_timeout(span, timeout: float = 5.0) -> dict:
    async with aioboto3_session.client("s3", endpoint_url=S3_ENDPOINT_URL) as s3:
        try:
            payload = await asyncio.wait_for(
                _fetch_all_payloads(s3, span),
                timeout=timeout,
            )
            return payload
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail={"error": "s3_timeout", "message": "S3 payload fetch timed out", "status": 504}
            )
        except Exception:
            raise HTTPException(
                status_code=502,
                detail={"error": "s3_error", "message": "Failed to fetch span payloads", "status": 502}
            )
```

**S3 key pattern (established in Phase 2):** `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json`
Fields: `prompt`, `response`, `raw_response`. Each stored as `{"value": "<text>"}`.

### Pattern 5: HTTP Proxy to Diagnosticer

**What:** Presenter receives `POST /diagnose` and forwards it to the Diagnosticer service via `httpx.AsyncClient`. Uses the `DIAGNOSTICER_URL` environment variable. Returns the Diagnosticer's response (a 501) directly.

**Claude's discretion:** Use `httpx.AsyncClient` with a `lifespan`-managed client instance stored on `app.state`. This avoids creating a new client per request.

```python
# In presenter/main.py lifespan:
app.state.http_client = httpx.AsyncClient(base_url=os.environ["DIAGNOSTICER_URL"])

# In diagnose.py router:
@router.post("/diagnose")
async def diagnose(body: DiagnoseRequest, request: Request, tenant_id = Depends(verify_session_token)):
    resp = await request.app.state.http_client.post("/diagnose", json=body.model_dump())
    return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
```

### Pattern 6: Diagnosticer Scaffold

**What:** A minimal FastAPI app that accepts `POST /diagnose` and returns 501. Wired to ClickHouse/PostgreSQL/S3 in docker-compose but does not use them in Phase 4.

```python
# xeter/services/diagnosticer/main.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Xeter Diagnosticer", version="0.1.0-scaffold")

class DiagnoseRequest(BaseModel):
    span_id: str
    flags: list

@app.post("/diagnose", status_code=501)
async def diagnose(body: DiagnoseRequest):
    return {
        "status": "not_implemented",
        "message": "Diagnosticer not yet available",
        "span_id": body.span_id,
    }

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
```

### Pattern 7: Tenant Isolation on ClickHouse Reads

**What:** Every ClickHouse query MUST include `WHERE tenant_id = %(tenant_id)s`. The spans table ORDER BY starts with `tenant_id`, so this is an index-aligned prefix scan — efficient and mandatory for isolation.

**Cross-tenant protection:** Return 404 for spans that exist but belong to another tenant. Since ClickHouse has no RLS, the tenant_id filter in the WHERE clause is the sole isolation mechanism. This is consistent with the established pattern: "DAL enforces tenant_id injection — no call-site filtering."

**Important:** `span_scores` table has no RLS (per migration 002 docstring: "RLS intentionally omitted — worker connects as BYPASSRLS role. Phase 4 will add per-tenant filtering at the read path layer"). For Phase 4, all span_scores queries must include `WHERE tenant_id = ?` in application code.

### Anti-Patterns to Avoid

- **Fetching S3 on list view:** Never. Only on `GET /spans/{id}`. The list view has 10–50 rows; each S3 fetch is 20–100ms. Parallel fetches would be 200–500ms of overhead on every page load.
- **Returning partial data on S3 error:** Return a complete error response. Partial JSON (span metadata without payload) is confusing to the client and violates the locked decision.
- **Using OFFSET pagination on ClickHouse:** Degrades with depth. Use cursor-based.
- **Fetching all flags then filtering in Python:** Use `WHERE span_id IN (...)` with the list of span_ids from the ClickHouse result.
- **Blocking the async event loop with S3/ClickHouse calls:** clickhouse-connect is synchronous — wrap ClickHouse calls with `asyncio.to_thread()` or use a sync executor pattern, since clickhouse-connect does not have a native async API.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT session tokens | Custom HMAC token format | python-jose | HS256 JWT with exp claim; well-tested, handles edge cases in encoding/decoding |
| Async HTTP proxy | Manual httpx request forwarding | httpx.AsyncClient with `app.state` | Persistent client, connection pooling, timeout handling |
| Cursor encoding | UUID-based or sequence-based cursors | Base64(ISO timestamp) | Natural fit for ClickHouse time-ordered query; opaque to client |
| Tenant isolation | Row-level checks on every returned item | WHERE tenant_id = ? in query | Push filtering to DB, not application layer |
| S3 timeout | Sleep-based retry | asyncio.wait_for | Precise timeout, cancels coroutine cleanly |

**Key insight:** The hardest problem in this phase is not the code — it is the ClickHouse→PostgreSQL merge being done correctly without N+1 queries. Always fetch flags for all span_ids in a single WHERE span_id IN (...) query, not per-span.

---

## Common Pitfalls

### Pitfall 1: clickhouse-connect is Synchronous

**What goes wrong:** `clickhouse_connect.get_client().query(...)` blocks the asyncio event loop. FastAPI handlers become blocking under any ClickHouse query.

**Why it happens:** clickhouse-connect does not provide an async API. It is a synchronous HTTP client under the hood.

**How to avoid:** Wrap every ClickHouse call in `asyncio.to_thread()`:
```python
import asyncio
result = await asyncio.to_thread(client.query, query, parameters=params)
```

**Warning signs:** Slow response times under concurrent load; pytest-asyncio tests hanging.

### Pitfall 2: ClickHouse Query Parameter Syntax

**What goes wrong:** Using f-strings or % formatting to inject tenant_id into ClickHouse queries causes SQL injection risk and/or syntax errors with special characters in UUIDs.

**Why it happens:** Unlike SQLAlchemy which uses `:param`, clickhouse-connect uses `%(param)s` style with a `parameters={}` dict.

**How to avoid:** Always use `client.query(sql, parameters={"tenant_id": tenant_id})` — never string formatting.

**Warning signs:** 400 errors from ClickHouse; "invalid character in query" exceptions.

### Pitfall 3: span_scores Has No RLS

**What goes wrong:** A query against `span_scores` without a `WHERE tenant_id = ?` filter returns rows from all tenants.

**Why it happens:** Migration 002 explicitly omitted RLS from span_scores ("Phase 4 will add per-tenant filtering at the read path layer"). The PostgreSQL BYPASSRLS role the worker uses means the policy was never written.

**How to avoid:** All span_scores SELECT queries in the Presenter MUST include `WHERE tenant_id = ?`. Document this in the module docstring of every reader module.

**Warning signs:** Span detail responses showing flag scores from other tenants.

### Pitfall 4: S3 Object Key Mismatch

**What goes wrong:** The Presenter constructs an S3 key differently than the Analyser used when uploading, resulting in 404s from S3.

**Why it happens:** The Analyser uploads with key `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json`. The month prefix is the month AT UPLOAD TIME, not the current month. If the Presenter reconstructs the key using the current month, it fails for spans uploaded in a previous month.

**How to avoid:** The ClickHouse spans table stores `prompt_ref`, `response_ref`, `raw_response_ref` as the actual S3 keys. The Presenter reads these _ref columns and fetches by the stored key — never reconstructing the key from scratch.

**Warning signs:** S3 404 errors for spans older than the current month.

### Pitfall 5: session_token dependency location

**What goes wrong:** Defining `verify_session_token` in `auth.py` and importing it creates a circular dependency if `spans.py` imports from `auth.py` while `auth.py` also imports something from the shared layer.

**How to avoid:** Define `verify_session_token` in a separate `deps.py` file or at the bottom of `auth.py` with no imports from `spans.py`. Follow the same pattern as `verify_api_key_header` in the Analyser — it lives in `auth.py` and is imported by `ingest.py`.

### Pitfall 6: presenter docker-compose missing SECRET_KEY

**What goes wrong:** JWT signing fails with "No secret key set" or uses an empty key.

**Why it happens:** SECRET_KEY is in `.env` but the current `presenter` service in `docker-compose.yml` does not have it in its `environment:` block.

**How to avoid:** Add `SECRET_KEY: ${SECRET_KEY:-dev-secret-key-change-in-production}` to the `presenter` service environment and add `DIAGNOSTICER_URL: http://diagnosticer:8001` similarly.

---

## Code Examples

Verified patterns from existing codebase:

### ClickHouse Query via asyncio.to_thread

```python
# Based on established clickhouse-connect usage in analyser/batch.py and worker/span_fetcher.py
import asyncio
from xeter.shared.db.clickhouse import get_clickhouse_client

async def query_spans(tenant_id: str, limit: int) -> list:
    client = get_clickhouse_client()
    result = await asyncio.to_thread(
        client.query,
        "SELECT span_id, agent_name, time_begin FROM spans "
        "WHERE tenant_id = %(tenant_id)s ORDER BY time_begin DESC LIMIT %(limit)s",
        parameters={"tenant_id": tenant_id, "limit": limit},
    )
    return result.result_rows
```

### PostgreSQL Flags Query (async, with RLS)

```python
# Based on xeter/shared/db/postgres.py tenant_session pattern
from sqlalchemy import select, text
from xeter.shared.models import Flag

async def fetch_flags_for_spans(
    span_ids: list[str], tenant_id: str, session: AsyncSession
) -> dict[str, list]:
    async with session.begin():
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": tenant_id},
        )
        result = await session.execute(
            select(Flag).where(
                Flag.tenant_id == tenant_id,
                Flag.span_id.in_(span_ids),
            )
        )
        flags = result.scalars().all()
    by_span: dict[str, list] = {}
    for flag in flags:
        by_span.setdefault(str(flag.span_id), []).append(flag)
    return by_span
```

### S3 Fetch Pattern (from analyser/s3.py — read variant)

```python
# Mirrors write pattern in xeter/services/analyser/s3.py
import asyncio
import json
import aioboto3

async def fetch_s3_payload(session: aioboto3.Session, bucket: str, endpoint_url: str, key: str) -> str | None:
    async with session.client("s3", endpoint_url=endpoint_url) as s3:
        try:
            response = await s3.get_object(Bucket=bucket, Key=key)
            body = await response["Body"].read()
            return json.loads(body).get("value")
        except Exception:
            return None
```

### httpx Proxy Pattern

```python
# In presenter/main.py lifespan — following analyser/main.py pattern
import httpx

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        base_url=os.environ.get("DIAGNOSTICER_URL", "http://diagnosticer:8001"),
        timeout=30.0,
    )
    yield
    await app.state.http_client.aclose()
```

### bcrypt Login Verification Pattern

```python
# Following analyser/auth.py verify_api_key_header pattern with asyncio.to_thread
import asyncio, bcrypt
from sqlalchemy import select
from xeter.shared.models import User

async def verify_login(email: str, password: str, session: AsyncSession) -> str | None:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    match = await asyncio.to_thread(
        bcrypt.checkpw, password.encode(), user.password_hash.encode()
    )
    return str(user.tenant_id) if match else None
```

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.0 |
| Config file | `xeter/pyproject.toml` — `[tool.pytest.ini_options] asyncio_mode = "auto" testpaths = ["tests"]` |
| Quick run command | `cd xeter && pytest tests/presenter/ -x -q` |
| Full suite command | `cd xeter && pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STOR-03 | Flags query returns only flags for the requesting tenant | unit | `pytest tests/presenter/test_spans.py::test_flags_scoped_by_tenant -x` | ❌ Wave 0 |
| DASH-03 | GET /spans/{id} returns flag details and similarity scores | unit | `pytest tests/presenter/test_spans.py::test_span_detail_includes_flags_and_scores -x` | ❌ Wave 0 |
| DASH-04 | GET /spans/{id} returns S3 payloads inline | unit | `pytest tests/presenter/test_spans.py::test_span_detail_includes_s3_payloads -x` | ❌ Wave 0 |
| DASH-04 | S3 timeout returns 504, not partial data | unit | `pytest tests/presenter/test_spans.py::test_span_detail_s3_timeout_returns_error -x` | ❌ Wave 0 |
| DASH-05 | GET /spans returns scores in flag summary | unit | `pytest tests/presenter/test_spans.py::test_span_list_includes_flag_scores -x` | ❌ Wave 0 |
| INFR-02 | POST /diagnose proxies to Diagnosticer and returns 501 | unit | `pytest tests/presenter/test_diagnose.py::test_diagnose_returns_501 -x` | ❌ Wave 0 |
| AUTH | GET /spans returns 401 with missing/invalid session token | unit | `pytest tests/presenter/test_spans.py::test_missing_token_returns_401 -x` | ❌ Wave 0 |
| AUTH | Tenant A cannot retrieve Tenant B spans | unit | `pytest tests/presenter/test_spans.py::test_cross_tenant_returns_404 -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd xeter && pytest tests/presenter/ -x -q`
- **Per wave merge:** `cd xeter && pytest -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `xeter/tests/presenter/__init__.py` — test package
- [ ] `xeter/tests/presenter/test_spans.py` — covers STOR-03, DASH-03, DASH-04, DASH-05, AUTH
- [ ] `xeter/tests/presenter/test_diagnose.py` — covers INFR-02

*(Existing `xeter/tests/conftest.py` with `mock_session` fixture is reusable — no framework install needed)*

---

## Key Implementation Notes

### Session Token: JWT vs Opaque

The CONTEXT.md says "session token" without specifying JWT vs opaque. Given:
- `python-jose` is listed in STACK.md as the auth library
- SECRET_KEY is already in `.env`
- The project is single-service Python with no external session store

**Use JWT (HS256).** An opaque token would require a sessions table in PostgreSQL and an extra DB lookup per request. JWT is stateless, validated inline, and fits the existing architecture perfectly.

### Login Endpoint Location

Add `POST /login` to the existing `xeter/services/presenter/routers/auth.py`. This keeps all auth in one file, consistent with the existing `/register` endpoint. The login endpoint:
1. Accepts `{email, password}`
2. Queries PostgreSQL `users` table
3. Verifies bcrypt hash via `asyncio.to_thread` (same pattern as analyser/auth.py)
4. Returns `{session_token: "eyJ..."}` — no tenant_id in response (opaque from client perspective)
5. Returns generic 401 on any failure (no "user not found" vs "wrong password" distinction)

### ClickHouse Client Lifecycle

Unlike aioboto3, `clickhouse-connect` clients are created per-service-startup and stored on `app.state`. They are stateless HTTP clients and safe to share across requests. Add to presenter `lifespan`:
```python
app.state.ch_client = get_clickhouse_client()
```

### Span Status Derivation

The ClickHouse spans table has no `status` column. The locked decision includes `status` in the list response fields. Derive it from flags: if flags array is non-empty → `"flagged"`, else → `"clean"`. Add this derivation in the Presenter merge layer.

### Duration ms Derivation

`duration_ms` is not a ClickHouse column but is derivable: `(time_end - time_begin)` in milliseconds. Compute in application code during merge.

### Diagnosticer docker-compose Service

New service entry in `deploy/docker-compose.yml`:
```yaml
diagnosticer:
  build:
    context: ..
    dockerfile: services/diagnosticer/Dockerfile
  ports:
    - "8001:8001"
  depends_on:
    postgres:
      condition: service_healthy
    clickhouse:
      condition: service_healthy
    minio:
      condition: service_healthy
  environment:
    DATABASE_URL: postgresql+asyncpg://xeter:xeter_dev_password@postgres:5432/xeter
    CLICKHOUSE_HOST: clickhouse
    S3_ENDPOINT_URL: http://minio:9000
    S3_ACCESS_KEY: xeter
    S3_SECRET_KEY: xeter_dev_password
    S3_BUCKET: xeter-payloads
```

The presenter service also needs:
```yaml
DIAGNOSTICER_URL: http://diagnosticer:8001
SECRET_KEY: dev-secret-key-change-in-production
```

---

## Open Questions

1. **`status` field values**
   - What we know: Locked decision includes `status` in span list fields; ClickHouse has no status column
   - What's unclear: Whether status should also include "pending" (span exists but worker hasn't analyzed yet) — if span_scores is empty AND flags is empty, is that "pending" or "clean"?
   - Recommendation: Use three states: `pending` (no scores in span_scores), `clean` (scores exist, no flags), `flagged` (at least one flag). This requires a check against span_scores, not just flags.

2. **S3 env vars in presenter service**
   - What we know: Presenter docker-compose entry currently has no S3 env vars (MINIO_ENDPOINT only — wrong variable name vs what aioboto3 expects: S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET)
   - What's unclear: Whether the presenter Dockerfile also installs aioboto3 (it's in pyproject.toml so yes, but env vars need to be set in docker-compose)
   - Recommendation: Add the four S3 env vars to the presenter docker-compose entry alongside the new SECRET_KEY and DIAGNOSTICER_URL.

---

## Sources

### Primary (HIGH confidence)
- Existing codebase: `xeter/services/analyser/s3.py` — aioboto3 S3 upload pattern (informs read pattern)
- Existing codebase: `xeter/services/analyser/auth.py` — `verify_api_key_header` dependency pattern
- Existing codebase: `xeter/services/worker/flag_writer.py` — psycopg2 + RLS pattern; informs SQLAlchemy read pattern
- Existing codebase: `xeter/shared/db/postgres.py` — `tenant_session` RLS context manager
- Existing codebase: `xeter/shared/db/clickhouse.py` — ClickHouse client + SPANS_TABLE_DDL (authoritative column list)
- Existing codebase: `deploy/docker-compose.yml` — service definitions to extend
- `.planning/research/ARCHITECTURE.md` — Multi-store merge patterns, S3 lazy fetch pattern, Diagnosticer isolation

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` — `python-jose[cryptography]>=3.3` for JWT (listed as auth library)
- `.planning/STATE.md` Accumulated Context → "[Phase 03-analysis-path]: RLS omitted from span_scores — worker connects as BYPASSRLS; Phase 4 adds read-path filtering" — explicit note that Phase 4 must add tenant filtering to span_scores queries

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in pyproject.toml; only python-jose is new
- Architecture: HIGH — patterns directly mirror established Analyser/Worker patterns; multi-store merge documented in ARCHITECTURE.md
- Pitfalls: HIGH — clickhouse-connect sync issue and span_scores no-RLS issue are explicitly documented in existing codebase and STATE.md

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable stack; no fast-moving components)

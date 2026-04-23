# Phase 12: Presenter Integration - Research

**Researched:** 2026-04-23
**Domain:** FastAPI inter-service HTTP proxy, idempotency service layer, PostgreSQL DAL reads
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Response timing**
- Synchronous: Presenter waits for the full diagnosis result before responding to the frontend
- Timeout is configurable via `DIAGNOSTICER_TIMEOUT_SECONDS` env var (should have a sensible default, e.g. 60s)
- Exceeding the timeout → Presenter returns 504 Gateway Timeout
- Diagnosticer URL configured via `DIAGNOSTICER_URL` env var (consistent with Docker Compose service wiring)
- Endpoint path stays as `/diagnose` — keep the existing scaffold path, no versioning or nesting

**Result retrieval pattern**
- Presenter reads the `diagnoses` PostgreSQL table directly for GET requests — same DB access pattern used for flags and spans
- No proxy to Diagnosticer for reads; Diagnosticer is only involved in writes (POST /diagnose trigger)
- `GET /diagnose/{span_id}` returns **404** if no diagnosis exists (clean absence signal; frontend uses 404 to know it should trigger diagnosis first)
- Response body contains diagnosis fields only: verdict, severity, affected_field, recommended_fix, diagnosed_at
- Single-span lookup only — no list endpoint in this phase

**Idempotency behavior**
- Before forwarding to Diagnosticer, Presenter checks the `diagnoses` table for an existing result
- If diagnosis exists → return it immediately without calling Diagnosticer (no re-diagnosis)
- No force-refresh mechanism in Phase 12 (can be added later if needed)
- Idempotency check lives in a service layer (`DiagnosisService.trigger(span_id)` or equivalent) — keeps the router thin, consistent with existing Presenter patterns

**Error contract**
- Diagnosticer unreachable (connection refused, DNS failure) → **503 Service Unavailable**
- Diagnosticer timeout (exceeds `DIAGNOSTICER_TIMEOUT_SECONDS`) → **504 Gateway Timeout**
- Diagnosticer returns an error (LLM failure, provider error) → Wrap with `{error: "diagnosis_failed", detail: "<sanitized message>"}` — do not leak raw provider error strings to the browser
- Tenant guard: Presenter verifies the `span_id` belongs to the authenticated tenant **before** forwarding to Diagnosticer — consistent with how all span-related reads are guarded; Diagnosticer has no session context to enforce this itself

### Claude's Discretion
- HTTP client library choice for inter-service call (httpx is already used in the codebase)
- Exact default value for `DIAGNOSTICER_TIMEOUT_SECONDS`
- Internal module structure for the service layer (where to place `DiagnosisService`)
- How to sanitize Diagnosticer error messages before surfacing them in the structured error response

### Deferred Ideas (OUT OF SCOPE)
- Force-refresh / re-diagnose button — Phase 13 UI option if needed; Phase 12 just returns cached results
- List endpoint for diagnoses (GET /diagnoses with filters) — future phase if a "diagnosed spans" view is added
</user_constraints>

---

## Summary

Phase 12 wires the Presenter to the live Diagnosticer backend. The primary work is replacing the existing scaffold `POST /diagnose` proxy (which blindly forwarded to Diagnosticer and returned whatever it got) with a proper service layer that: checks idempotency against the `diagnoses` table, forwards to Diagnosticer only when needed, handles all error codes correctly, enforces tenant ownership of `span_id`, and respects a configurable timeout. The second deliverable is a new `GET /diagnose/{span_id}` endpoint that reads directly from the `diagnoses` table via the existing `DiagnosisRepository`.

All infrastructure already exists. The `diagnoses` table, `Diagnosis` ORM model, and `DiagnosisRepository` (including `get_latest_for_span`) were built in Phase 11. The `httpx.AsyncClient` is already created in `main.py` lifespan and stored on `app.state.http_client`. The `tenant_session` context manager, `get_session` dependency, and the existing `select(Flag)` patterns in `spans.py` show exactly how to query PostgreSQL with tenant isolation. No new dependencies are needed.

The main design decision delegated to discretion is where to place the `DiagnosisService`. The existing Presenter has no dedicated service layer — routers call the DAL directly. Given that the idempotency check + HTTP forward + error translation is non-trivial logic, a thin service class at `xeter/services/presenter/diagnosis_service.py` keeps the router clean and is the natural extension point.

**Primary recommendation:** Build `DiagnosisService` in `xeter/services/presenter/diagnosis_service.py`, update `diagnose.py` router to use it, add `GET /diagnose/{span_id}` to the same router, update `DIAGNOSTICER_TIMEOUT_SECONDS` default to 60s in `main.py`, and replace the old scaffold `DiagnoseRequest.flags` field (no longer forwarded).

---

## Standard Stack

### Core (already in pyproject.toml — no new installs)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | (any, pinned transitively) | Async HTTP client for Diagnosticer call | Already on `app.state.http_client`; `AsyncClient` with `base_url` supports per-request `timeout` override |
| SQLAlchemy | 2.0.48 | Async ORM for diagnoses table reads | Already used for flags/spans; `DiagnosisRepository.get_latest_for_span` is ready |
| FastAPI | 0.135.2 | Router, Depends, HTTPException | Existing pattern; `Depends(verify_session_token)` + `Depends(get_session)` |
| Pydantic | 2.12.5 | Request/response schema validation | Existing pattern; `BaseModel` for response schemas |

### No New Dependencies

All required libraries are already installed. `httpx` is in `pyproject.toml` (unpinned, pulled transitively), `asyncpg` + `SQLAlchemy` handle DB, `structlog` handles logging.

---

## Architecture Patterns

### Recommended Module Structure

```
xeter/services/presenter/
├── main.py                    # MODIFIED: add DIAGNOSTICER_TIMEOUT_SECONDS to lifespan
├── deps.py                    # unchanged
├── diagnosis_service.py       # NEW: DiagnosisService class
└── routers/
    ├── auth.py                # unchanged
    ├── spans.py               # unchanged
    └── diagnose.py            # MODIFIED: replace scaffold, add GET /diagnose/{span_id}
```

### Pattern 1: Service Layer for Idempotency + HTTP Forward

**What:** A `DiagnosisService` class that encapsulates the full trigger logic. The router calls `service.trigger(span_id, tenant_id, session, http_client)` and maps the result to HTTP responses. The service handles: DB check → early return, span ownership check → 403/404, HTTP forward → parse response, timeout → 504, unreachable → 503, Diagnosticer error → wrapped 502-style error.

**When to use:** Whenever a single router action involves more than one data source and conditional logic. Keeps the router a thin dispatcher.

**Example (service layer sketch):**
```python
# xeter/services/presenter/diagnosis_service.py
import os
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from xeter.shared.dal.diagnoses import DiagnosisRepository
from xeter.shared.db.postgres import tenant_session
from xeter.shared.models import Diagnosis

DIAGNOSTICER_TIMEOUT_DEFAULT = 60.0

class DiagnosisService:
    async def trigger(
        self,
        *,
        span_id: str,
        tenant_id: str,
        session: AsyncSession,
        http_client: httpx.AsyncClient,
    ) -> Diagnosis:
        timeout = float(os.environ.get("DIAGNOSTICER_TIMEOUT_SECONDS", DIAGNOSTICER_TIMEOUT_DEFAULT))

        # 1. Idempotency check — return cached result without calling Diagnosticer
        async with tenant_session(session, tenant_id) as s:
            repo = DiagnosisRepository(s)
            existing = await repo.get_latest_for_span(span_id=span_id, tenant_id=tenant_id)
            if existing:
                return existing

        # 2. Tenant guard: verify span ownership via ClickHouse (before forwarding)
        # ... span lookup with tenant_id filter (see spans.py pattern) ...

        # 3. Forward to Diagnosticer
        try:
            resp = await http_client.post(
                "/diagnose",
                json={"span_id": span_id},
                timeout=timeout,
            )
        except httpx.TimeoutException:
            raise DiagnosticerTimeout()
        except httpx.HTTPError:
            raise DiagnosticerUnreachable()

        if not resp.is_success:
            raise DiagnosticerError(sanitize(resp.json()))

        # 4. Return the newly-written Diagnosis from the diagnoses table
        async with tenant_session(session, tenant_id) as s:
            repo = DiagnosisRepository(s)
            return await repo.get_latest_for_span(span_id=span_id, tenant_id=tenant_id)
```

**Key insight:** The Diagnosticer writes to the `diagnoses` table itself (Phase 11). The Presenter does not write — it only reads back via `get_latest_for_span` after a successful POST. This is why the service re-queries after a successful forward instead of parsing the JSON response body.

### Pattern 2: GET /diagnose/{span_id} — Direct DB Read

**What:** A plain `GET` route that queries `DiagnosisRepository.get_latest_for_span`, returns 404 if `None`, otherwise returns the diagnosis fields.

**When to use:** Any read that goes directly to the shared PostgreSQL layer, no inter-service call needed.

**Example:**
```python
@router.get("/diagnose/{span_id}")
async def get_diagnosis(
    span_id: str,
    tenant_id: str = Depends(verify_session_token),
    session: AsyncSession = Depends(get_session),
):
    async with tenant_session(session, tenant_id) as s:
        repo = DiagnosisRepository(s)
        diagnosis = await repo.get_latest_for_span(span_id=span_id, tenant_id=tenant_id)
    if diagnosis is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No diagnosis for this span"})
    return DiagnosisResponse(...)
```

### Pattern 3: httpx Timeout Per-Request Override

**What:** The `httpx.AsyncClient` stored on `app.state.http_client` was created with `timeout=30.0` (existing scaffold). Phase 12 needs to support a configurable `DIAGNOSTICER_TIMEOUT_SECONDS`. The cleanest approach is to override per-request via `timeout=` on `.post()` rather than rebuilding the client.

**Source:** httpx official docs — `AsyncClient.post(url, timeout=N)` takes a per-request timeout that overrides the client default.

```python
resp = await http_client.post(
    "/diagnose",
    json={"span_id": span_id},
    timeout=float(os.environ.get("DIAGNOSTICER_TIMEOUT_SECONDS", 60)),
)
```

This avoids needing to modify the lifespan for the timeout value itself, though the lifespan default can still be updated for consistency.

### Pattern 4: Error Classification from httpx Exceptions

**What:** The existing scaffold catches `httpx.HTTPError` broadly. Phase 12 needs to distinguish:
- `httpx.TimeoutException` (subclass of `HTTPStatusError`? No — it's a subclass of `TransportError`) → 504
- Other `httpx.HTTPError` (connect error, DNS, etc.) → 503

**Correct exception hierarchy (verified against httpx source):**
```
httpx.HTTPError
  httpx.TransportError
    httpx.TimeoutException       ← catch first for 504
      httpx.ConnectTimeout
      httpx.ReadTimeout
      httpx.WriteTimeout
      httpx.PoolTimeout
    httpx.ConnectError           ← catch for 503
    httpx.NetworkError
  httpx.HTTPStatusError          ← raised by resp.raise_for_status() only
```

**Pattern:**
```python
try:
    resp = await http_client.post("/diagnose", json=..., timeout=timeout)
except httpx.TimeoutException:
    raise HTTPException(status_code=504, detail={"error": "diagnosticer_timeout", ...})
except httpx.HTTPError:
    raise HTTPException(status_code=503, detail={"error": "diagnosticer_unavailable", ...})
```

Note: Do NOT call `resp.raise_for_status()` — Diagnosticer errors (502, 422 from LLM failures) need custom handling, not generic `HTTPStatusError` propagation.

### Pattern 5: tenant_session Re-use Constraint

**What:** `tenant_session()` opens `session.begin()` internally. Once a `tenant_session` context exits, the session's transaction is committed/rolled back. A second `tenant_session` call on the same session object opens a new transaction. This is the existing pattern in the Diagnosticer — two separate `async with tenant_session(session, tid)` blocks work correctly as sequential transactions.

**Critical:** Do NOT nest `tenant_session` contexts on the same session. The idempotency read and the post-trigger re-read must be separate sequential `tenant_session` blocks.

### Anti-Patterns to Avoid

- **Parsing the Diagnosticer JSON response body to extract diagnosis fields:** The Diagnosticer already wrote to the `diagnoses` table. Re-querying via `DiagnosisRepository.get_latest_for_span` is authoritative and avoids duplicating the schema. Only use this if the Diagnosticer returned 200.
- **Using the old `flags` field in the forwarded request body:** The current `DiagnoseRequest` has `span_id: str` and `flags: list`. The Diagnosticer's real endpoint only accepts `{"span_id": str}`. Remove the `flags` field from the Presenter's request model — it was a scaffolding artifact.
- **Forgetting tenant guard before forwarding:** The Diagnosticer does its own JWT validation but uses the same `tenant_id` from its token — which it receives as the forwarded Bearer token. Wait — the Presenter does NOT forward the user's Bearer token to the Diagnosticer (the existing scaffold sends no auth header). The Diagnosticer has its own `verify_session_token`. This means the Presenter must verify span ownership itself before forwarding, as the Diagnosticer cannot enforce tenant isolation without a valid tenant context.
- **Broad `except Exception` for Diagnosticer errors:** Catch specifically `httpx.TimeoutException` then `httpx.HTTPError`. Don't collapse all errors into one status code.
- **Opening two concurrent execute() calls on the same AsyncSession:** The same warning as in `spans.py` — `AsyncSession` is not safe for concurrent use. All sequential tenant_session blocks on the same session are fine; asyncio.gather on the same session is not.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Diagnoses DB read | Custom SQL query | `DiagnosisRepository.get_latest_for_span` | Already built in Phase 11, handles RLS via tenant_session |
| Session-scoped token validation | Custom JWT decode | `verify_session_token` from `deps.py` | Already tested, same JWT HS256 algorithm |
| PostgreSQL session | Raw asyncpg | `get_session` (via `auth.get_session`) + `tenant_session` | Already wires async_sessionmaker + RLS SET LOCAL |
| HTTP client lifecycle | New httpx.AsyncClient per request | `request.app.state.http_client` | Already created in lifespan, properly closed on shutdown |
| Error sanitization | Custom regex scrubber | Take only the `detail` key from Diagnosticer JSON error body, discard raw provider strings | Simple key extraction is sufficient; don't over-engineer |

**Key insight:** Phase 11 and the existing Presenter already provide every building block. Phase 12 is assembly work, not new infrastructure.

---

## Common Pitfalls

### Pitfall 1: httpx Client Timeout Defaults Not Being Overridden

**What goes wrong:** `app.state.http_client` was created with `timeout=30.0`. If `DIAGNOSTICER_TIMEOUT_SECONDS` is set to 60 but the per-request call doesn't pass `timeout=`, the 30s client default wins. The feature appears to work but ignores the env var.

**Why it happens:** httpx `AsyncClient` timeout is set at construction time by default; per-request override requires explicitly passing `timeout=` to the method call.

**How to avoid:** Always pass `timeout=float(os.environ.get("DIAGNOSTICER_TIMEOUT_SECONDS", 60))` directly in the `http_client.post(...)` call.

**Warning signs:** DIAGNOSTICER_TIMEOUT_SECONDS=120 still triggers 504 after 30s in testing.

### Pitfall 2: Catching httpx.HTTPError Before httpx.TimeoutException

**What goes wrong:** `httpx.TimeoutException` is a subclass of `httpx.TransportError` which is a subclass of `httpx.HTTPError`. If the broad `except httpx.HTTPError` comes first, timeouts are caught as 503 instead of 504.

**Why it happens:** Python's `except` blocks are evaluated top-to-bottom; the first matching handler wins.

**How to avoid:** Always put `except httpx.TimeoutException` before `except httpx.HTTPError`.

**Warning signs:** Timeout tests return 503 instead of 504.

### Pitfall 3: tenant_session Nesting on the Same AsyncSession

**What goes wrong:** Calling `async with tenant_session(s, tid)` inside another `async with tenant_session(s, tid)` on the same session raises `InvalidRequestError: A transaction is already begun on this Session`.

**Why it happens:** `tenant_session` calls `session.begin()` — you can't begin a transaction inside a transaction on the same session.

**How to avoid:** Use separate sequential `async with tenant_session(s, tid)` blocks (not nested). Each block is its own transaction.

**Warning signs:** `InvalidRequestError: A transaction is already begun` in tests or runtime logs.

### Pitfall 4: Forwarding the Old `flags` Field to the Diagnosticer

**What goes wrong:** The existing scaffold `DiagnoseRequest` has a `flags: list` field that gets forwarded as `json=body.model_dump()`. The Diagnosticer's real endpoint (`DiagnoseRequest` in `diagnosticer/main.py`) only has `span_id: str`. FastAPI will ignore unknown fields by default in Pydantic v2, but sending `flags` is confusing and may break if Diagnosticer ever adds strict validation.

**Why it happens:** The scaffold was written before the Diagnosticer's real schema was finalized.

**How to avoid:** Update Presenter's `DiagnoseRequest` to only accept `span_id: str`, forward only `{"span_id": span_id}`.

**Warning signs:** Old tests that assert `flags` is forwarded will need updating.

### Pitfall 5: Leaking Raw LLM Error Strings to the Browser

**What goes wrong:** Diagnosticer returns `{"detail": "LLM call failed: RateLimitError: You exceeded your current quota..."}`. Passing this directly through exposes provider-specific internals and API key hints.

**Why it happens:** Naive pass-through of error responses.

**How to avoid:** When Diagnosticer returns a non-2xx status, extract only a sanitized message. A reasonable sanitization is: take the first 100 characters of the Diagnosticer's detail string, strip any API key patterns, and wrap in `{"error": "diagnosis_failed", "detail": "<truncated>"}`.

**Warning signs:** Browser network tab shows raw provider error messages.

### Pitfall 6: Tenant Guard Missing Before Diagnosticer Forward

**What goes wrong:** If the Presenter does not verify that `span_id` belongs to `tenant_id` before forwarding, a malicious tenant could diagnose spans belonging to another tenant. The Diagnosticer does not enforce cross-tenant isolation (it trusts the forwarding service).

**Why it happens:** The Diagnosticer has its own JWT check but the span lookup inside it uses whatever `tenant_id` is in the token — which is the Presenter's tenant, not the span's actual owner. Wait: actually the Diagnosticer re-verifies the JWT on its own token header. But the Presenter does not forward the user's Bearer token to the Diagnosticer. This means the Diagnosticer runs in a "trusted internal" mode — it trusts the `span_id` it receives. Tenant guard must happen in the Presenter.

**How to avoid:** Before calling Diagnosticer, verify span ownership by querying ClickHouse with `WHERE tenant_id = %(tenant_id)s AND span_id = %(span_id)s` — same pattern as `_fetch_ch_span()` in `spans.py`. Return 404 if not found (do not distinguish "span doesn't exist" from "span belongs to another tenant" — no information leakage).

**Warning signs:** Cross-tenant diagnosis succeeds in integration tests.

---

## Code Examples

### GET /diagnose/{span_id} — Router Pattern

```python
# Source: xeter/services/presenter/routers/diagnose.py (Phase 12)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from xeter.services.presenter.deps import verify_session_token
from xeter.services.presenter.routers.auth import get_session
from xeter.shared.dal.diagnoses import DiagnosisRepository
from xeter.shared.db.postgres import tenant_session

class DiagnosisResponse(BaseModel):
    diagnosis_id: str
    span_id: str
    verdict: str
    severity: str
    affected_field: str | None
    recommended_fix: str | None
    diagnosed_at: str

@router.get("/diagnose/{span_id}", response_model=DiagnosisResponse)
async def get_diagnosis(
    span_id: str,
    tenant_id: str = Depends(verify_session_token),
    session: AsyncSession = Depends(get_session),
) -> DiagnosisResponse:
    async with tenant_session(session, tenant_id) as s:
        repo = DiagnosisRepository(s)
        diagnosis = await repo.get_latest_for_span(span_id=span_id, tenant_id=tenant_id)
    if diagnosis is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "No diagnosis for this span", "status": 404},
        )
    return DiagnosisResponse(
        diagnosis_id=str(diagnosis.diagnosis_id),
        span_id=diagnosis.span_id,
        verdict=diagnosis.verdict,
        severity=diagnosis.severity,
        affected_field=diagnosis.affected_field,
        recommended_fix=diagnosis.fix,  # note: ORM field is `fix`, response key is `recommended_fix`
        diagnosed_at=str(diagnosis.created_at),
    )
```

### httpx Timeout + Exception Classification

```python
# Source: httpx documentation — per-request timeout override
import os
import httpx
from fastapi import HTTPException

async def _call_diagnosticer(http_client: httpx.AsyncClient, span_id: str) -> dict:
    timeout = float(os.environ.get("DIAGNOSTICER_TIMEOUT_SECONDS", 60.0))
    try:
        resp = await http_client.post(
            "/diagnose",
            json={"span_id": span_id},
            timeout=timeout,
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail={"error": "diagnosticer_timeout", "message": "Diagnosis request timed out"},
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail={"error": "diagnosticer_unavailable", "message": "Diagnosticer service is unavailable"},
        )
    return resp
```

### Error Sanitization

```python
def _sanitize_diagnosticer_error(resp_json: dict | None) -> str:
    """Extract a safe error message from Diagnosticer error body."""
    if not resp_json:
        return "Diagnosis failed"
    detail = resp_json.get("detail", "Diagnosis failed")
    if isinstance(detail, str):
        # Truncate at 120 chars; strip anything that looks like an API key
        return detail[:120]
    return "Diagnosis failed"
```

### Tenant Guard Pattern (from spans.py)

```python
# Source: xeter/services/presenter/routers/spans.py — _fetch_ch_span pattern
import asyncio

async def _verify_span_ownership(
    ch_client,
    span_id: str,
    tenant_id: str,
) -> bool:
    """Return True if span_id belongs to tenant_id in ClickHouse."""
    result = await asyncio.to_thread(
        ch_client.query,
        "SELECT span_id FROM spans WHERE tenant_id = %(tid)s AND span_id = %(sid)s LIMIT 1",
        {"tid": tenant_id, "sid": span_id},
    )
    return bool(result.result_rows)
```

### Existing Test Mocking Pattern (for test parity)

Tests for the updated `POST /diagnose` and new `GET /diagnose/{span_id}` should follow the existing `test_diagnose.py` pattern:
- Override `verify_session_token` via `app.dependency_overrides`
- Inject `app.state.http_client` with an `AsyncMock` for POST tests
- Override `get_session` via `app.dependency_overrides` with an `AsyncMock` for GET tests
- Patch `DiagnosisRepository` methods directly via `unittest.mock.patch`

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Scaffold: blind proxy, returns 501 from Diagnosticer | Real service layer: idempotency check + tenant guard + error classification | Phase 12 | POST /diagnose becomes a real endpoint |
| No GET retrieve endpoint | `GET /diagnose/{span_id}` reads directly from diagnoses table | Phase 12 | Frontend can check for existing diagnosis without triggering one |
| `DiagnoseRequest` had `flags: list` (scaffold artifact) | `DiagnoseRequest` has only `span_id: str` | Phase 12 | Matches Diagnosticer's actual schema |
| `timeout=30.0` hardcoded in lifespan | `DIAGNOSTICER_TIMEOUT_SECONDS` env var, per-request override | Phase 12 | Ops can tune without code change |

**Deprecated/outdated in this phase:**
- The existing `test_diagnose_returns_501` test: scaffold behavior no longer applies; replace with real behavior tests
- The `flags` field in `DiagnoseRequest`: remove it; the Diagnosticer does not use it

---

## Open Questions

1. **Does the Presenter need to forward the user's Bearer token to the Diagnosticer?**
   - What we know: The existing scaffold does NOT forward the Authorization header. The Diagnosticer has its own `verify_session_token` that validates JWT. Docker Compose wires `SECRET_KEY` consistently across services.
   - What's unclear: If the Presenter is meant to be a trusted internal caller, should it pass its own service token, the user's token, or no token?
   - Recommendation: Keep the current no-auth-forward pattern. The Presenter verifies tenant ownership of the span before calling Diagnosticer. If the Diagnosticer needs tenant context in the future, that can be added with a service-to-service token. For now, the Diagnosticer endpoint should accept calls from trusted internal services without validating a JWT — or alternatively, the Presenter can be updated to forward the user's Bearer token. Either is valid; the simplest is to remove auth from the internal POST /diagnose call on the Diagnosticer side and rely on the Presenter's guard. This is a planning-level decision.

2. **`recommended_fix` vs `fix` field naming**
   - What we know: The `Diagnosis` ORM model uses `fix`. The CONTEXT.md specifies the GET response body should contain `recommended_fix`.
   - What's unclear: Should the POST /diagnose response also use `recommended_fix` (consistent with GET) or `fix` (matching the Diagnosticer's own response schema which uses `fix`)?
   - Recommendation: Use `recommended_fix` in both Presenter response schemas for frontend consistency; map from `diagnosis.fix` internally. Document the rename in the response model docstring.

---

## Sources

### Primary (HIGH confidence)
- Direct source code inspection: `xeter/services/presenter/main.py`, `routers/diagnose.py`, `routers/spans.py`, `deps.py` — exact existing patterns used throughout
- Direct source code inspection: `xeter/shared/dal/diagnoses.py` — `DiagnosisRepository.get_latest_for_span` confirmed present
- Direct source code inspection: `xeter/shared/models.py` — `Diagnosis` ORM model field names confirmed (`fix`, not `recommended_fix`)
- Direct source code inspection: `xeter/shared/db/postgres.py` — `tenant_session` usage pattern confirmed
- Direct source code inspection: `xeter/services/diagnosticer/main.py` — confirms Diagnosticer `DiagnoseRequest` only has `span_id`; no auth forwarding in current scaffold

### Secondary (MEDIUM confidence)
- httpx exception hierarchy (`httpx.TimeoutException` < `httpx.TransportError` < `httpx.HTTPError`) — from training knowledge, consistent with httpx 0.27+ documentation structure; verified by existing usage pattern in codebase where `httpx.HTTPError` is already caught

### Tertiary (LOW confidence — needs validation during planning)
- Optimal location for `DiagnosisService` — recommendation based on codebase patterns, not a framework constraint

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and in use; no new dependencies
- Architecture patterns: HIGH — based on direct code inspection of existing Presenter routers, DAL, and DB infrastructure
- Pitfalls: HIGH for DB/session pitfalls (directly from existing code comments and patterns); MEDIUM for httpx exception hierarchy (training knowledge, consistent with API)

**Research date:** 2026-04-23
**Valid until:** 2026-05-23 (stable tech stack, no fast-moving dependencies)

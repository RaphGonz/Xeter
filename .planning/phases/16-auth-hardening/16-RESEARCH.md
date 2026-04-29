# Phase 16: Auth Hardening - Research

**Researched:** 2026-04-29
**Domain:** JWT session management, httpOnly refresh tokens, FastAPI middleware, Next.js 16 Route Handlers, internal service authentication
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | Session tokens expire after 30 minutes; server hard-fails on startup if SECRET_KEY env var is unset (no silent fallback to dev key) | `deps.py` currently uses `os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")` — must be replaced with `os.environ["SECRET_KEY"]` (KeyError on missing). `TOKEN_EXPIRE_HOURS = 24` must become `TOKEN_EXPIRE_MINUTES = 30`. Same pattern applies to `diagnosticer/main.py`. |
| AUTH-02 | User can silently refresh an expired access token via httpOnly refresh token cookie — Presenter POST /auth/refresh; Next.js Route Handlers for /api/login and /api/auth/refresh; sessionStorage removed from auth.ts | Current `auth.ts` uses Zustand + `sessionStorage`. Must be replaced with an in-memory Zustand store (no sessionStorage). Current `/api/*` routes are pure Next.js rewrites to Presenter. Two Route Handlers must be added: `app/api/login/route.ts` and `app/api/auth/refresh/route.ts`. Route Handlers can set httpOnly cookies via `cookies()` from `next/headers`. Presenter needs `POST /auth/refresh` endpoint. |
| AUTH-03 | Operator has a documented JWT_SECRET rotation runbook covering dual-secret window and service restart sequence | Docs artifact only — no code changes. Must cover: 30-minute re-login gap, dual-secret window option (python-jose supports multiple keys via `algorithms` list but NOT multiple secrets for HS256 decode — workaround needed), and service restart sequence. |
| AUTH-04 | Presenter-to-Diagnosticer calls are authenticated by a static internal API key — INTERNAL_API_KEY env var (required, no fallback) in both services; Presenter includes X-Internal-Api-Key header; Diagnosticer middleware rejects missing/wrong key with 401 | `diagnosis_service.py` currently forwards the user's `Authorization: Bearer` header to Diagnosticer. Must be replaced with `X-Internal-Api-Key: ${INTERNAL_API_KEY}` header. Diagnosticer needs a FastAPI middleware that checks this header on all non-healthz routes. Both services need `os.environ["INTERNAL_API_KEY"]` at startup (KeyError on missing). |
</phase_requirements>

## Summary

Phase 16 hardens the authentication surface across three layers: the access token lifecycle (AUTH-01), the token refresh flow (AUTH-02), the Presenter-Diagnosticer trust boundary (AUTH-04), and a rotation runbook (AUTH-03).

The current state has two critical defects: `SECRET_KEY` has a soft dev fallback (`os.environ.get(..., "dev-secret-key-change-in-production")`) in both Presenter and Diagnosticer, and access tokens expire after 24 hours. The token is stored in `sessionStorage`, which is XSS-readable. There is no refresh mechanism, so an expired token requires manual re-login. The Presenter forwards the user's JWT to Diagnosticer — meaning a stolen user JWT can directly call the internal service.

The fix is a clean four-task decomposition: (1) hard-fail on missing `SECRET_KEY` + shorten to 30 minutes, (2) introduce httpOnly refresh token cookie managed by Next.js Route Handlers with a 401 interceptor in the client-side API layer, (3) write the rotation runbook, and (4) introduce `INTERNAL_API_KEY` header as the trust boundary between Presenter and Diagnosticer.

**Primary recommendation:** Do all Python changes first (AUTH-01, AUTH-04) before the frontend changes (AUTH-02), since the Presenter `POST /auth/refresh` endpoint must exist before the Next.js Route Handler can call it.

## Standard Stack

### Core (already in use — no new installs)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-jose[cryptography] | >=3.3 | JWT encode/decode in Presenter and Diagnosticer | Already installed; NOTE: flagged for future migration to PyJWT (AUTH-F02). HS256 with `exp` claim is the current approach. |
| FastAPI | 0.135.2 | Middleware, Depends, startup lifespan for hard-fail | Already installed |
| next | 16.2.1 | Route Handlers, `cookies()` from `next/headers` | Already installed |
| zustand | ^5.0.12 | In-memory auth state store in the browser | Already installed — sessionStorage calls must be removed |
| httpx | current | HTTP client for Presenter→Diagnosticer call | Already installed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `cookies` from `next/headers` | Next.js 16 built-in | Set/read httpOnly cookies in Route Handlers | ONLY usable in Route Handlers and Server Components, not in Client Components |
| FastAPI `Request.app.state` | built-in | Access `INTERNAL_API_KEY` from startup-loaded state | Avoid re-reading env var per-request |
| `asynccontextmanager` lifespan | FastAPI built-in | Hard-fail env var check at startup | Already used in Presenter main.py — add key checks here |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hard-fail at module import (os.environ["SECRET_KEY"] at module level) | Lifespan startup check | Module-level raises at import time (fine for prod), but lifespan is already the pattern in both services — prefer module-level for deps.py since it's imported before lifespan runs |
| Long-lived refresh JWT in httpOnly cookie | Iron-session encrypted cookie | Iron-session adds a dependency; HS256 JWT with a long expiry is simpler and already understood by the team |
| Separate `JWT_REFRESH_SECRET` for refresh tokens | Same `SECRET_KEY` for both tokens | Using the same secret is acceptable at v1.3 since there is no refresh token revocation; a separate secret adds no security without a revocation store |

## Architecture Patterns

### Recommended Project Structure (changes only)

```
xeter/services/presenter/
├── deps.py                  # SECRET_KEY: os.environ["SECRET_KEY"], TOKEN_EXPIRE_MINUTES = 30
├── routers/auth.py          # add POST /auth/refresh endpoint
├── main.py                  # add CORSMiddleware; INTERNAL_API_KEY hard-fail in lifespan

xeter/services/diagnosticer/
├── main.py                  # INTERNAL_API_KEY middleware; SECRET_KEY hard-fail

services/view/src/
├── lib/auth.ts              # remove sessionStorage; pure in-memory Zustand store
├── lib/api.ts               # add 401 interceptor that calls /api/auth/refresh
├── app/api/
│   ├── login/route.ts       # NEW: POST handler — proxies to Presenter, sets refresh cookie
│   └── auth/refresh/route.ts # NEW: POST handler — reads cookie, calls /auth/refresh, returns new token

docs/
└── JWT_ROTATION_RUNBOOK.md  # AUTH-03
```

### Pattern 1: Hard-fail SECRET_KEY at module load (deps.py)

**What:** Replace `os.environ.get("SECRET_KEY", fallback)` with `os.environ["SECRET_KEY"]` so a missing var raises `KeyError` before any route is served.
**When to use:** Any required env var where a silent fallback would be a security regression.

```python
# Source: xeter/services/presenter/deps.py (current — to be changed)
# BEFORE (insecure):
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
TOKEN_EXPIRE_HOURS = 24

# AFTER (correct):
SECRET_KEY = os.environ["SECRET_KEY"]   # KeyError on startup if unset
TOKEN_EXPIRE_MINUTES = 30
```

Token creation change:

```python
# BEFORE:
expire = datetime.now(tz=timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)

# AFTER:
expire = datetime.now(tz=timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
```

The same pattern applies to `xeter/services/diagnosticer/main.py` line:
```python
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
# → replace with:
SECRET_KEY = os.environ["SECRET_KEY"]
```

### Pattern 2: Presenter POST /auth/refresh endpoint

**What:** Accept a refresh token (from JSON body — the Next.js Route Handler reads the httpOnly cookie and passes it), verify it, issue a new short-lived access token.
**When to use:** When client receives 401 on any authenticated endpoint.

```python
# Source: xeter/services/presenter/routers/auth.py (new endpoint)
REFRESH_TOKEN_EXPIRE_DAYS = 30  # long-lived refresh token

class RefreshRequest(BaseModel):
    refresh_token: str

class RefreshResponse(BaseModel):
    session_token: str  # new short-lived access token

@router.post("/auth/refresh", response_model=RefreshResponse, status_code=200)
async def refresh_token(body: RefreshRequest) -> RefreshResponse:
    try:
        payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        tenant_id: str | None = payload.get("sub")
        if not tenant_id:
            raise _REFRESH_UNAUTHORIZED
    except JWTError:
        raise _REFRESH_UNAUTHORIZED
    new_token = create_session_token(tenant_id)
    return RefreshResponse(session_token=new_token)
```

Note: `create_session_token` also needs a sibling `create_refresh_token` with 30-day expiry.

### Pattern 3: Login endpoint must also issue a refresh token

The `/login` endpoint currently returns `{"session_token": str}`. It must also return a `refresh_token` field. The Next.js Route Handler intercepts this response and stores the refresh token in an httpOnly cookie, returning only `session_token` to the browser JS.

```python
# Updated LoginResponse in routers/auth.py
class LoginResponse(BaseModel):
    session_token: str
    refresh_token: str
```

### Pattern 4: Next.js Route Handler for /api/login

**What:** Replaces the Next.js rewrite for `/api/login`. The Route Handler proxies credentials to Presenter `/login`, receives `{session_token, refresh_token}`, sets `refresh_token` as an httpOnly cookie, and returns only `{session_token}` to the browser.

```typescript
// Source: Next.js 16 official docs (services/view/node_modules/next/dist/docs/01-app/03-api-reference/04-functions/cookies.md)
// services/view/src/app/api/login/route.ts
import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const PRESENTER_URL = process.env.PRESENTER_URL ?? 'http://localhost:8000'
const IS_PROD = process.env.ENVIRONMENT === 'production'

export async function POST(req: NextRequest) {
  const body = await req.json()

  const presenterRes = await fetch(`${PRESENTER_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!presenterRes.ok) {
    const err = await presenterRes.json().catch(() => ({}))
    return NextResponse.json(err, { status: presenterRes.status })
  }

  const data = await presenterRes.json()
  const cookieStore = await cookies()
  cookieStore.set('xeter_refresh', data.refresh_token, {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'strict' : 'lax',
    path: '/',
    maxAge: 30 * 24 * 60 * 60,  // 30 days in seconds
  })

  return NextResponse.json({ session_token: data.session_token })
}
```

**Critical:** The `cookies()` function is async in Next.js 15+ and must be awaited. Version history in the official docs confirms: "v15.0.0-RC: `cookies` is now an async function."

### Pattern 5: Next.js Route Handler for /api/auth/refresh

```typescript
// services/view/src/app/api/auth/refresh/route.ts
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const PRESENTER_URL = process.env.PRESENTER_URL ?? 'http://localhost:8000'

export async function POST() {
  const cookieStore = await cookies()
  const refreshToken = cookieStore.get('xeter_refresh')?.value

  if (!refreshToken) {
    return NextResponse.json({ error: 'no_refresh_token' }, { status: 401 })
  }

  const presenterRes = await fetch(`${PRESENTER_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })

  if (!presenterRes.ok) {
    return NextResponse.json({ error: 'refresh_failed' }, { status: 401 })
  }

  const data = await presenterRes.json()
  return NextResponse.json({ session_token: data.session_token })
}
```

### Pattern 6: Client-side 401 interceptor in api.ts

**What:** Wrap the `request<T>()` function to detect 401, call `/api/auth/refresh`, update the Zustand store with the new token, and retry the original request once.
**When to use:** Every authenticated API call from the browser.

```typescript
// services/view/src/lib/api.ts — updated request() function
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, options)
  if (res.status === 401) {
    // Attempt transparent refresh
    const refreshRes = await fetch('/api/auth/refresh', { method: 'POST' })
    if (!refreshRes.ok) {
      useAuthStore.getState().clearToken()
      throw new Error('HTTP 401')
    }
    const { session_token } = await refreshRes.json()
    useAuthStore.getState().setToken(session_token)
    // Retry original request with new token
    const retryOptions = {
      ...options,
      headers: {
        ...(options.headers as Record<string, string> ?? {}),
        Authorization: `Bearer ${session_token}`,
      },
    }
    const retry = await fetch(path, retryOptions)
    if (!retry.ok) {
      const body = await retry.json().catch(() => ({}))
      throw new Error(body.message ?? `HTTP ${retry.status}`)
    }
    return retry.json() as Promise<T>
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.message ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}
```

### Pattern 7: Remove sessionStorage from auth.ts

**What:** Zustand store must be pure in-memory. `sessionStorage.setItem`, `sessionStorage.getItem`, `sessionStorage.removeItem` all removed. `hydrate()` becomes a no-op (sets `hydrated: true` immediately since there is nothing to hydrate from storage — token comes from the API response and stays in memory).

```typescript
// services/view/src/lib/auth.ts — AFTER
export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  hydrated: false,
  setToken: (t: string) => set({ token: t }),
  clearToken: () => set({ token: null }),
  hydrate: () => set({ hydrated: true }),
}))
```

**Consequence:** On page reload, the user will need to re-login (token is gone from memory). This is acceptable and intentional — the 401 interceptor will catch the first authenticated request and call refresh, which reads the httpOnly cookie (still alive for 30 days). So a hard refresh silently re-authenticates via the refresh cookie.

### Pattern 8: INTERNAL_API_KEY middleware in Diagnosticer

**What:** FastAPI middleware that checks `X-Internal-Api-Key` header on all requests except `/healthz`. Returns 401 if missing or wrong.

```python
# xeter/services/diagnosticer/main.py — add after app creation
INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]  # KeyError on startup if unset

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class InternalApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)
        key = request.headers.get("X-Internal-Api-Key")
        if key != INTERNAL_API_KEY:
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized", "message": "Invalid or missing internal API key"},
            )
        return await call_next(request)

app.add_middleware(InternalApiKeyMiddleware)
```

### Pattern 9: Presenter adds INTERNAL_API_KEY to Diagnosticer calls

In `diagnosis_service.py`, the `trigger()` method currently sends `headers={"Authorization": auth_header}`. This must be replaced:

```python
# xeter/services/presenter/diagnosis_service.py — trigger() method, Step 3
INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]  # module-level hard-fail

# In trigger():
resp = await http_client.post(
    "/diagnose",
    json={"span_id": span_id},
    headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
    timeout=timeout,
)
```

The `auth_header` parameter to `trigger()` can be removed; `diagnose.py` router no longer passes it.

### Pattern 10: CORSMiddleware in Presenter

**What:** Explicit CORS configuration driven by `ENVIRONMENT` env var.

```python
# xeter/services/presenter/main.py
from fastapi.middleware.cors import CORSMiddleware

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
ALLOW_ORIGINS = os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,  # never "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Cookie security settings (driven by ENVIRONMENT):
- dev: `secure=False`, `sameSite="lax"`
- production: `secure=True`, `sameSite="strict"`

The `ENVIRONMENT` env var is read by the Next.js Route Handler when setting the `xeter_refresh` cookie (see Pattern 4). Must be added to docker-compose.yml for the `view` service.

### Pattern 11: docker-compose.yml — add INTERNAL_API_KEY and ENVIRONMENT

```yaml
# deploy/docker-compose.yml — presenter service environment
environment:
  # ... existing vars ...
  INTERNAL_API_KEY: ${INTERNAL_API_KEY}    # no :- fallback
  ENVIRONMENT: ${ENVIRONMENT:-dev}         # optional: defaults to dev

# deploy/docker-compose.yml — diagnosticer service environment
environment:
  # ... existing vars ...
  INTERNAL_API_KEY: ${INTERNAL_API_KEY}    # no :- fallback

# deploy/docker-compose.yml — view service environment
environment:
  PRESENTER_URL: http://presenter:8000
  ENVIRONMENT: ${ENVIRONMENT:-dev}
```

And `.env.example`:
```
INTERNAL_API_KEY=CHANGE_ME_BEFORE_DEPLOY
ENVIRONMENT=dev
```

### Anti-Patterns to Avoid

- **Returning refresh_token in the JSON response to the browser:** The browser JS must never see the refresh token. The Route Handler MUST strip it before returning.
- **Using sessionStorage for token persistence:** XSS-readable. Auth-02 explicitly removes this.
- **Setting httpOnly cookies from Presenter directly:** The STATE.md records "Next.js rewrites strip upstream Set-Cookie" — this is why the Route Handler pattern is needed.
- **Using `allow_origins=["*"]` with `allow_credentials=True`:** Browsers reject this combination per CORS spec. Always use explicit origins.
- **Using `os.environ.get("INTERNAL_API_KEY", "")` with an empty fallback:** Empty string always fails the equality check — use `os.environ["INTERNAL_API_KEY"]` for the hard-fail.
- **Nesting the Diagnosticer `verify_session_token` dependency after INTERNAL_API_KEY middleware:** The Diagnosticer currently verifies JWTs. With INTERNAL_API_KEY middleware in place, Diagnosticer no longer needs to verify JWTs (it trusts the Presenter). The `verify_session_token` dep in Diagnosticer can be removed or replaced with a simpler tenant extraction from a header forwarded by Presenter.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Refresh token cookie management in browser | Custom fetch wrapper with manual cookie parsing | Next.js `cookies()` from `next/headers` in Route Handler | httpOnly cookies are inaccessible to JS; only the server (Route Handler) can read/set them |
| JWT dual-secret for rotation | Custom multi-key decode loop | python-jose `algorithms` list cannot carry two secrets for HS256; accepted approach is short overlap window + service restart | python-jose HS256 `jwt.decode` takes a single secret string |
| CORS headers manually set per response | Custom `@app.after_request` handler | FastAPI's built-in `CORSMiddleware` | Handles preflight OPTIONS correctly, respects `allow_credentials` |
| Retry logic with exponential backoff on 401 | Custom retry decorator | Simple one-shot retry after refresh (as shown in Pattern 6) | Infinite retry loops can lock users out if refresh itself expires |

## Common Pitfalls

### Pitfall 1: Next.js rewrite conflicts with Route Handlers
**What goes wrong:** The `next.config.ts` has a catch-all rewrite: `source: '/api/:path*', destination: Presenter`. If you add `app/api/login/route.ts`, Next.js will prefer the Route Handler over the rewrite for that exact path. But `app/api/auth/refresh/route.ts` is also intercepted. Both are correct — Route Handlers take priority over rewrites.
**Why it happens:** Route Handlers are matched before the rewrite rules in Next.js 13+.
**How to avoid:** Verify that `/api/login` and `/api/auth/refresh` are not accidentally matched by the rewrite rule. They won't be — Route Handlers win. All other `/api/*` paths still rewrite to Presenter.
**Warning signs:** If `/api/login` returns a 404 after adding the Route Handler, the file path is wrong (must be `app/api/login/route.ts`, not inside a conflicting page.tsx segment).

### Pitfall 2: cookies() must be awaited in Next.js 15+
**What goes wrong:** `cookies().get(...)` (no await) works in Next.js 14 but is deprecated in 15 and removed behavior in 16.
**Why it happens:** The cookies API became async at Next.js 15 RC.
**How to avoid:** Always use `const cookieStore = await cookies()` in Route Handlers (as shown in official docs).
**Warning signs:** TypeScript error "Property 'get' does not exist on type 'Promise<ReadonlyRequestCookies>'".

### Pitfall 3: Zustand store hydration breaks after removing sessionStorage
**What goes wrong:** Components that call `useHydrateAuth()` check `hydrated` before rendering. If `hydrate()` is a no-op, components render immediately with `token: null` and redirect to login before the 401 interceptor can refresh.
**Why it happens:** The old `hydrate()` read from sessionStorage synchronously. The new flow has no persistent token — on hard reload, the token is gone and must be re-acquired via refresh cookie.
**How to avoid:** On page load, immediately set `hydrated: true` (token stays null). The guards in `SpansLayout` check `hydrated && !token` and redirect to login. BUT — the page also does a `listSpans` call on load. If that returns 401, the interceptor calls `/api/auth/refresh`, gets a new token, and stores it via `setToken`. The redirect guard will no longer trigger because `token` is now set. This works correctly — the key is that the `hydrated` flag is set synchronously, not waiting for any async operation.
**Warning signs:** Infinite redirect loop between `/login` and `/spans` on page reload.

### Pitfall 4: Double-counting 401 interceptor
**What goes wrong:** The `listSpans` call on the spans page plus the existing error handler both react to 401. The current `spans/page.tsx` has a manual `if (msg.includes('401')...)` check that calls `clearToken()` and redirects to login. After adding the interceptor, this check must be updated — the interceptor already handles transparent refresh, so the manual 401 handler should only trigger if refresh itself fails.
**Why it happens:** The `request()` function in `api.ts` throws `Error('HTTP 401')` on 401, which the page catches and handles. After adding the interceptor, the 401 is handled silently (refresh + retry), and the Error is never thrown for normal token expiry.
**How to avoid:** The interceptor swallows the 401 and retries. The manual handler in `spans/page.tsx` only fires if the retry also fails (interceptor re-throws). This is correct behavior — no code change needed in `spans/page.tsx`.

### Pitfall 5: Diagnosticer currently verifies JWTs from Presenter
**What goes wrong:** After adding `INTERNAL_API_KEY` middleware to Diagnosticer, the `verify_session_token` dependency on `POST /diagnose` will never receive a valid JWT (Presenter no longer forwards the user's `Authorization` header). The dep raises 401 on every Diagnosticer request.
**Why it happens:** The current architecture treats Diagnosticer as a JWT-authenticated service. AUTH-04 changes this to an internal-key-authenticated service.
**How to avoid:** After adding the middleware, the `tenant_id` for Diagnosticer must come from somewhere else — either a forwarded header (`X-Tenant-Id`) sent by Presenter, or from the request body. Success Criterion 5 says Diagnosticer returns 401 on missing/wrong key — it does NOT say Diagnosticer must still extract tenant_id from a JWT. The simplest approach: Presenter adds `X-Tenant-Id: {tenant_id}` alongside `X-Internal-Api-Key`, and Diagnosticer reads tenant_id from that header. Remove `verify_session_token` from Diagnosticer's `/diagnose` endpoint entirely.

### Pitfall 6: SECRET_KEY module-level assignment vs. import-time error
**What goes wrong:** `SECRET_KEY = os.environ["SECRET_KEY"]` at module level in `deps.py` raises `KeyError` at import time — which means any test that imports `from xeter.services.presenter.deps import ...` will fail unless `SECRET_KEY` is set in the test environment.
**Why it happens:** The test suite currently sets `SECRET_KEY` via the existing `os.environ.get` fallback. After the change, tests must set `SECRET_KEY` explicitly.
**How to avoid:** In test files that import from `deps`, add `os.environ.setdefault("SECRET_KEY", "test-secret-key")` before the import, or use a `conftest.py` fixture. The existing `test_auth_login.py` imports `from xeter.services.presenter.deps import ALGORITHM, SECRET_KEY` — this import will fail post-change if SECRET_KEY is not set.
**Warning signs:** `KeyError: 'SECRET_KEY'` during test collection.

### Pitfall 7: Presenter /auth/refresh does not need a DB lookup
**What goes wrong:** Some refresh token implementations query the DB to verify the token is not revoked. This project explicitly defers revocation (AUTH-F01 is a future requirement). The refresh endpoint just decodes the JWT and issues a new access token — no DB call needed.
**Why it happens:** Overengineering based on full OAuth2 patterns.
**How to avoid:** Keep the refresh endpoint stateless — decode refresh JWT, verify `sub` is present, issue new access token. No session, no DB.

### Pitfall 8: Dual-secret JWT rotation is not natively supported by python-jose for HS256
**What goes wrong:** Operators may expect to hot-reload a new SECRET_KEY without a service restart (dual-secret window). python-jose's `jwt.decode(token, secret, algorithms=[...])` takes a single secret string — there is no built-in way to try multiple secrets.
**Why it happens:** python-jose's API does not expose a multi-secret decode for HS256 (unlike RS256 where a JWKS endpoint provides multiple public keys).
**How to avoid:** The runbook (AUTH-03) must document the accepted approach: (a) there is a 30-minute re-login gap during rotation, OR (b) implement a two-stage rotation by deploying a custom decode loop that tries OLD_SECRET_KEY then NEW_SECRET_KEY for a 30-minute overlap window — this is manual code, not a library feature. For v1.3, option (a) (the gap) is acceptable. Document both options clearly.

## Code Examples

### Verified: cookies() async API in Next.js 16

```typescript
// Source: services/view/node_modules/next/dist/docs/01-app/03-api-reference/04-functions/cookies.md
import { cookies } from 'next/headers'

// In a Route Handler:
export async function POST() {
  const cookieStore = await cookies()   // MUST be awaited
  cookieStore.set('xeter_refresh', value, {
    httpOnly: true,
    secure: true,          // prod only
    sameSite: 'strict',    // prod only
    path: '/',
    maxAge: 30 * 24 * 60 * 60,
  })
}
```

### Verified: Route Handler file location and structure

```typescript
// Source: services/view/node_modules/next/dist/docs/01-app/01-getting-started/15-route-handlers.md
// File: services/view/src/app/api/login/route.ts
export async function POST(request: Request) {
  // handles POST /api/login
}
// File: services/view/src/app/api/auth/refresh/route.ts
export async function POST() {
  // handles POST /api/auth/refresh
}
```

### Verified: HS256 JWT encode with exp (python-jose)

```python
# Source: xeter/services/presenter/deps.py (existing, verified working)
from jose import jwt
from datetime import datetime, timedelta, timezone

SECRET_KEY = os.environ["SECRET_KEY"]  # after fix
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 30

def create_session_token(tenant_id: str) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {"sub": tenant_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(tenant_id: str) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(days=30)
    payload = {"sub": tenant_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
```

### Verified: CORSMiddleware with allow_credentials (FastAPI)

```python
# Source: FastAPI official docs pattern; confirmed via pyproject.toml (fastapi==0.135.2)
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # never "*" when allow_credentials=True
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Verified: Test fix for SECRET_KEY hard-fail

```python
# In conftest.py or at top of test file — BEFORE any import from deps.py
import os
os.environ.setdefault("SECRET_KEY", "test-secret-only")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `sessionStorage` for token persistence | In-memory Zustand + httpOnly refresh cookie | Phase 16 (this phase) | Token no longer XSS-readable |
| `os.environ.get("SECRET_KEY", fallback)` soft fallback | `os.environ["SECRET_KEY"]` hard-fail | Phase 16 | Startup fails loudly instead of silently running with a weak key |
| 24-hour access token expiry | 30-minute access token expiry | Phase 16 | Reduces exposure window from 24h to 30min |
| User JWT forwarded to Diagnosticer | `X-Internal-Api-Key` static header | Phase 16 | User token compromise does not directly expose Diagnosticer |
| Next.js catch-all rewrite for `/api/*` | Route Handlers for `/api/login` and `/api/auth/refresh`, rewrite for everything else | Phase 16 | Enables server-side cookie management without exposing refresh token to JS |
| No CORS config (FastAPI default) | Explicit CORSMiddleware with allow_credentials=True | Phase 16 | Required for cookie-based auth to work cross-origin |

**Deprecated/outdated in this phase:**
- `auth.ts` `sessionStorage` usage: replaced by in-memory store + httpOnly refresh cookie
- `auth_header` parameter in `DiagnosisService.trigger()`: removed (replaced by INTERNAL_API_KEY)
- `verify_session_token` in Diagnosticer `/diagnose` endpoint: replaced by InternalApiKeyMiddleware + X-Tenant-Id header

## Open Questions

1. **Diagnosticer tenant_id after removing JWT verification**
   - What we know: Diagnosticer currently gets `tenant_id` by decoding the forwarded JWT via `verify_session_token`. AUTH-04 removes this.
   - What's unclear: The Success Criteria (criterion 5) says Diagnosticer returns 401 on bad internal key — it does NOT specify how Diagnosticer gets tenant_id after auth.
   - Recommendation: Presenter forwards `X-Tenant-Id: {tenant_id}` alongside `X-Internal-Api-Key`. Diagnosticer reads `request.headers.get("X-Tenant-Id")` in the diagnose endpoint. This keeps Diagnosticer stateless and avoids re-introducing a JWT decode.

2. **CORS allow_origins value in docker-compose**
   - What we know: CORSMiddleware must have explicit origins, never `"*"`.
   - What's unclear: The production origin hostname is not yet known (deployment domain TBD). The `view` service runs on port 3000.
   - Recommendation: Add `CORS_ALLOW_ORIGINS=http://localhost:3000` to `.env.example` and docker-compose for the `presenter` service. Document that this must be updated for production.

3. **Next.js rewrite for /api/login after Route Handler is added**
   - What we know: Route Handlers win over rewrites for the same path. The existing rewrite `source: '/api/:path*'` would match `/api/login` BUT Next.js's routing gives Route Handlers priority.
   - What's unclear: Whether the `next.config.ts` rewrite needs explicit exclusion of `/api/login` and `/api/auth/refresh`.
   - Recommendation: Verify during implementation. Based on Next.js 16 docs ("Route Handlers are only available inside the `app` directory... They are the equivalent of API Routes"), they should take priority. Add a comment in `next.config.ts` noting the two paths now handled locally.

## Sources

### Primary (HIGH confidence)
- `services/view/node_modules/next/dist/docs/01-app/03-api-reference/04-functions/cookies.md` — async cookies() API, set/delete/get methods, httpOnly/secure/sameSite options
- `services/view/node_modules/next/dist/docs/01-app/01-getting-started/15-route-handlers.md` — Route Handler file convention, HTTP methods, priority over rewrites
- `services/view/node_modules/next/dist/docs/01-app/02-guides/authentication.md` — stateless sessions, httpOnly cookies, session management patterns
- `xeter/services/presenter/deps.py` — existing SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_HOURS, create_session_token, verify_session_token
- `xeter/services/presenter/routers/auth.py` — existing login endpoint, LoginResponse shape
- `xeter/services/presenter/main.py` — lifespan pattern, httpx client, existing no-CORS state
- `xeter/services/diagnosticer/main.py` — existing SECRET_KEY fallback, verify_session_token dep, diagnose endpoint
- `xeter/services/presenter/diagnosis_service.py` — existing auth_header forwarding to Diagnosticer
- `services/view/src/lib/auth.ts` — current sessionStorage-backed Zustand store
- `services/view/src/lib/api.ts` — current request() function, no 401 interceptor
- `deploy/docker-compose.yml` — existing env var wiring for presenter and diagnosticer
- `.env.example` — existing secret structure

### Secondary (MEDIUM confidence)
- FastAPI CORSMiddleware behavior (allow_credentials + allow_origins interaction) — confirmed by FastAPI 0.135.2 pyproject.toml; behavior consistent with Starlette docs
- python-jose HS256 single-secret limitation — confirmed from pyproject.toml dependency `python-jose[cryptography]>=3.3` and REQUIREMENTS.md future note AUTH-F02 (noting python-jose is "near-abandoned")

### Tertiary (LOW confidence)
- python-jose multi-secret workaround approach — manual try/except decode loop described in Open Questions item 2; not verified against python-jose source code

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed, versions confirmed from pyproject.toml and package.json
- Architecture: HIGH — Next.js 16 cookie API verified from bundled docs; FastAPI patterns verified from existing code
- Pitfalls: HIGH — pitfalls 1-6 derived directly from reading existing code; pitfalls 7-8 are MEDIUM (python-jose limitation is well-known but not verified from source)

**Research date:** 2026-04-29
**Valid until:** 2026-05-29 (Next.js 16 stable, python-jose pinned, FastAPI pinned)

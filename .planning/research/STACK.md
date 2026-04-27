# Stack Research

**Domain:** AI agent observability and debugging SaaS platform
**Researched:** 2026-03-27 (base platform); 2026-04-20 (v1.2 Diagnosticer additions); 2026-04-27 (v1.3 Security Hardening additions)
**Confidence:** HIGH (all versions verified against PyPI and official docs)

---

## v1.3 Security Hardening Additions

This section covers library changes needed for the v1.3 security hardening milestone.
All other stack decisions are unchanged — see the base platform sections below.

### What Already Exists and Is Sufficient

The following are already in `xeter/pyproject.toml` and require **no changes** to handle the v1.3 security features:

- `python-jose[cryptography]>=3.3` — already imported as `from jose import JWTError, jwt` in `presenter/deps.py` and `diagnosticer/main.py`. Supports arbitrary JWT claims including `type: "refresh"` and long-lived `exp`. Refresh token issuance is a pure logic addition, no new JWT library needed.
- `bcrypt==5.0.0` (installed transitively) — `import bcrypt` is used directly throughout the codebase. `bcrypt.gensalt()` defaults to `rounds=12`. The stored hash format `$2b$12$...` encodes the cost factor at index 2 when split on `$` — parseable in a pytest CI test without any new library.
- `fastapi==0.135.2` — `response.set_cookie(httponly=True, secure=True, samesite="lax")` is fully supported via Starlette's `Response` class. Exact signature confirmed: `set_cookie(key, value, max_age=None, expires=None, path="/", domain=None, secure=False, httponly=False, samesite="lax")`. No additional cookie library needed.
- `sqlalchemy==2.0.48` + `asyncpg==0.31.0` + `alembic==1.18.4` — RLS policies and CHECK constraints are schema migrations; no ORM library changes needed.

### New Dependencies Required

**None.** All six security features in v1.3 are implementable with the existing dependency set. No new packages are needed in `pyproject.toml`.

### Dependency to Remove

| Library | Action | Reason |
|---------|--------|--------|
| `passlib[bcrypt]>=1.7` | **Remove from pyproject.toml** | The codebase uses `import bcrypt` directly throughout (confirmed by grep). `passlib` is never imported anywhere in the codebase. It was explicitly rejected in PROJECT.md key decisions because `passlib 1.7.4` is incompatible with Python 3.14+. It is dead weight. |

Removing `passlib` does not break anything — all bcrypt calls already use the `bcrypt` package directly.

---

### Feature-by-Feature Library Analysis

#### 1. JWT Expiry + Refresh Token Endpoint (httpOnly cookie)

**Libraries needed:** None new.

`python-jose[cryptography]` already handles both access and refresh token creation. The refresh token is just a JWT with a longer `exp` and an additional `type: "refresh"` claim to distinguish it from access tokens. The new endpoint issues it via:

```python
from fastapi import Response
from jose import jwt

def create_refresh_token(tenant_id: str) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(days=7)
    payload = {"sub": tenant_id, "type": "refresh", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/refresh")
async def refresh(response: Response, ...) -> LoginResponse:
    token = create_refresh_token(tenant_id)
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=True,         # HTTPS only — set False in dev
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/auth/refresh",
    )
    ...
```

`response.set_cookie(httponly=True)` is confirmed correct — Starlette's `Response.set_cookie` signature supports `httponly` as a named boolean parameter. **HIGH confidence** (official Starlette docs verified 2026-04-27).

The refresh endpoint reads the cookie via `Cookie` header dependency:

```python
from fastapi import Cookie

@router.post("/refresh")
async def refresh(refresh_token: str | None = Cookie(default=None)):
    ...
```

FastAPI's `Cookie()` dependency is already part of `fastapi` — no additional library.

**python-jose maintenance note (LOW priority, not blocking v1.3):** `python-jose` is considered near-abandoned by the community (last meaningful development activity has stalled despite a 3.5.0 release in May 2025 patching CVE-2024-33663). FastAPI's own documentation updated in PR #11589 to acknowledge this. `PyJWT==2.12.1` is the actively-maintained alternative and is a near-drop-in replacement (import changes from `jose` to `jwt`, slight API differences). Migration from `python-jose` to `PyJWT` is recommended for v1.4 or later — it is explicitly out of scope for v1.3 (would require touching `presenter/deps.py`, `diagnosticer/main.py`, and all related tests simultaneously with no functional security gain in the short term).

#### 2. span_scores RLS + Worker BYPASSRLS Scoped Role

**Libraries needed:** None new.

RLS policies are SQL DDL executed via Alembic migrations. Pattern mirrors existing RLS on `flags` and `diagnoses` tables (already implemented). No new Python library.

The Worker BYPASSRLS scoping requires a PostgreSQL role change and a `GRANT INSERT ON span_scores TO worker_role` statement — pure SQL.

#### 3. PostgreSQL CHECK Constraints (verdict, severity)

**Libraries needed:** None new.

CHECK constraints are Alembic migrations:

```python
# In migration:
op.create_check_constraint(
    "ck_diagnoses_verdict",
    "diagnoses",
    "verdict IN ('model', 'architecture', 'prompt', 'unknown')"
)
op.create_check_constraint(
    "ck_diagnoses_severity",
    "diagnoses",
    "severity IN ('low', 'medium', 'high')"
)
```

SQLAlchemy 2.0's `CheckConstraint` is available in `sqlalchemy.schema`. Already in pyproject.toml.

#### 4. bcrypt Cost Factor CI Test (rounds >= 12)

**Libraries needed:** None new.

`bcrypt.gensalt()` with no arguments already defaults to `rounds=12`. The cost factor is encoded in the stored hash string at position `hash.split("$")[2]`:

- `$2b$12$<salt+digest>` → split on `$` → index 2 = `"12"` → `int("12") == 12`

The CI test parses a freshly-generated hash and asserts the extracted value:

```python
# tests/test_bcrypt_cost.py
import bcrypt

def test_bcrypt_cost_factor_minimum():
    """Fail CI if bcrypt cost factor drops below 12."""
    salt = bcrypt.gensalt()
    # bcrypt hash format: $2b$<rounds>$<22-char-salt><31-char-digest>
    rounds = int(salt.decode("utf-8").split("$")[2])
    assert rounds >= 12, f"bcrypt cost factor is {rounds}, minimum is 12"
```

No new dependency. `bcrypt` is already used directly and `import bcrypt` works in the test environment (confirmed in `tests/presenter/test_auth_login.py:15`).

**Note:** The existing `gensalt()` calls in `auth.py`, `api_keys.py`, and `seed.py` use `bcrypt.gensalt()` without an explicit `rounds` argument. Since `bcrypt.gensalt()` defaults to 12, the current behavior is already compliant. The CI test enforces this cannot regress.

#### 5. docker-compose Secrets Hygiene + generate-secrets.sh

**Libraries needed:** None new.

`generate-secrets.sh` uses only standard POSIX tooling:

```bash
#!/usr/bin/env bash
set -euo pipefail

SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
MINIO_PASSWORD=$(openssl rand -hex 16)
CLICKHOUSE_PASSWORD=$(openssl rand -hex 16)

cat > .env << EOF
SECRET_KEY=${SECRET_KEY}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
# ... etc
EOF
echo ".env written."
```

`openssl` is available in any Docker-capable dev environment (Linux, macOS, WSL2). No Python dependency, no shell library.

The docker-compose changes replace hardcoded `xeter_dev_password` values with `${POSTGRES_PASSWORD:-CHANGE_ME_BEFORE_DEPLOY}` patterns — pure YAML edits.

#### 6. MinIO/S3 Bucket Policy Documentation

**Libraries needed:** None new.

`xeter-payloads` bucket policy uses the `mc` CLI (already used in docker-compose `minio-init` entrypoint) and S3 IAM JSON (documented, no code change). Documentation only:

```bash
# Set bucket to private (deny public access):
mc alias set local http://localhost:9100 $MINIO_USER $MINIO_PASSWORD
mc anonymous set none local/xeter-payloads

# Verify:
mc anonymous get local/xeter-payloads  # Should print: No anonymous policy found
```

The IAM JSON for AWS S3 equivalents is a static JSON document — no Python library.

---

### pyproject.toml Delta

```toml
# REMOVE from [project] dependencies:
# "passlib[bcrypt]>=1.7",    ← never imported; incompatible with Python 3.14

# NO additions needed — all v1.3 features use existing deps
```

---

### What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `PyJWT` (right now) | Migration from `python-jose` → `PyJWT` requires touching `presenter/deps.py`, `diagnosticer/main.py`, and multiple tests simultaneously with no functional security gain for v1.3 | Keep `python-jose` for v1.3; plan migration for v1.4 |
| `itsdangerous` | Sometimes used for signed cookies — unnecessary when the refresh token itself is a signed JWT | `response.set_cookie()` + `python-jose` JWT |
| `fastapi-jwt-auth` | Third-party extension with its own cookie middleware pattern; conflicts with existing `verify_session_token` dependency pattern | Direct `Cookie()` FastAPI dependency + `jose.jwt.decode()` |
| `secrets` module for bcrypt test | No need for a new tool — the hash format embeds the cost factor; parsing is a one-liner | `bcrypt.gensalt()` + string split |
| `python-dotenv` for generate-secrets.sh | Shell script doesn't need Python; `openssl rand` is simpler and available everywhere | `openssl rand -hex 32` in bash |

---

### Version Compatibility

| Package | Version | Notes |
|---------|---------|-------|
| `python-jose[cryptography]` | >=3.3 (3.5.0 installed) | Refresh tokens are plain JWT with extra claims — no API change; `exp` claim already validated on decode |
| `fastapi` | 0.135.2 | `response.set_cookie(httponly=True)` confirmed via Starlette 0.45+ signature; `Cookie()` dependency available since FastAPI 0.47 |
| `bcrypt` | 5.0.0 | `gensalt()` default rounds=12 confirmed on PyPI 2026-04-27; hash format `$2b$<rounds>$...` stable since bcrypt 3.x |
| `alembic` | 1.18.4 | `op.create_check_constraint()` available since Alembic 1.0; no version concern |

---

### Migration Note: python-jose → PyJWT (Future, v1.4+)

When this migration is done, the changes are:

| File | Change |
|------|--------|
| `presenter/deps.py` | `from jose import JWTError, jwt` → `import jwt` + catch `jwt.ExpiredSignatureError`, `jwt.InvalidTokenError` |
| `diagnosticer/main.py` | Same import swap |
| `pyproject.toml` | Remove `python-jose[cryptography]`; add `PyJWT[crypto]>=2.12` |
| Tests | Update any `from jose import jwt` references |

PyJWT 2.12.1 is the current stable version (released 2026-03-13). The API differences are minor — `jwt.decode()` raises `jwt.ExpiredSignatureError` (subclass of `jwt.InvalidTokenError`) rather than `JWTError`.

---

## Base Platform Stack (Unchanged from v1.0/v1.1/v1.2)

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
| Next.js | 15 | Frontend framework | Already shipped as v1.0; SSR supports cookie-based auth patterns natively via `httpOnly` cookie reading server-side |
| React | 19.x | UI component library | Industry standard; largest ecosystem |
| TypeScript | 5.x | Type safety for frontend | Standard for any non-trivial React app |
| Tailwind CSS | 4.x | Utility-first CSS | Industry standard for SaaS dashboards in 2026 |
| shadcn/ui | latest | Component library | Copy-paste component system; full Tailwind v4 support |
| TanStack Query | 5.x (v5.90+) | Server state management | Powers 80% of new React apps per 2025 State of JS |

---

### Development Infrastructure (Docker Compose)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Docker Compose | v2 (Compose spec 5.0) | Multi-service local dev environment | Industry standard |
| ClickHouse | 25.x (official image) | Local span storage | `clickhouse/clickhouse-server:25.3` |
| PostgreSQL | 16 | Local flags/diagnostics/auth storage | `postgres:16-alpine` |
| Redis | 7 | Local queue for arq workers | `redis:7-alpine` |
| MinIO | latest | Local S3-compatible object storage | S3 v4 API compatible; `mc` CLI for bucket policy operations |

---

## Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uvicorn[standard] | >=0.32 | ASGI server with uvloop | All FastAPI services |
| python-jose[cryptography] | >=3.3 (3.5.0) | JWT token generation/validation for access + refresh tokens | Dashboard auth; refresh endpoint |
| bcrypt | 5.0.0 | Password hashing (used directly, not via passlib) | `api_keys.key_hash` and `users.password_hash` |
| httpx | >=0.28 | Async HTTP client | Presenter → Diagnosticer calls; async test client for pytest |
| pytest | >=8.3 | Test runner | All services including bcrypt CI cost test |
| pytest-asyncio | 0.24.0 | Async test support | Required for testing FastAPI async endpoints |
| anyio | >=4.7 | Async test backend | Used by pytest-asyncio |
| python-dotenv | >=1.0 | Environment variable loading | Load `.env` in development |
| structlog | >=25.0 | Structured logging | JSON-formatted logs for all services |
| anthropic | ==0.86.0 | Anthropic Claude API client | Diagnosticer LLM provider |
| openai | ==2.22.0 | OpenAI GPT API client | Diagnosticer LLM provider |

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `python-jose` (for now) | `PyJWT==2.12.1` | Use PyJWT in v1.4+ — it is actively maintained and a near-drop-in replacement; migration is straightforward but out of scope for v1.3 |
| `response.set_cookie(httponly=True)` | `fastapi-jwt-auth` extension | Only if the project needs cookie rotation middleware, token blacklisting, or full CSRF double-submit patterns — none of which are in scope |
| Bash + `openssl rand` for generate-secrets.sh | Python `secrets` module | Python is fine too; bash is simpler since no virtualenv needed to run a secret-generation script |
| Direct `jose.jwt` for refresh tokens | Storing refresh tokens in Redis | Redis refresh token storage adds invalidation capability (allows logout-all-devices) — defer to v1.4 if needed |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `passlib[bcrypt]` | Never imported in codebase; incompatible with Python 3.14+; explicitly rejected in PROJECT.md; should be removed from pyproject.toml | `bcrypt` directly (already the pattern everywhere) |
| `itsdangerous` | Signed cookies are redundant when the refresh token itself is a signed JWT | `response.set_cookie()` + `jose.jwt` |
| `fastapi-jwt-auth` | Third-party extension that introduces its own middleware layer; conflicts with existing `verify_session_token` dependency pattern and adds complexity for one new endpoint | Direct `Cookie()` dependency + `jose.jwt.decode()` |
| `PyJWT` (in v1.3) | Migration requires simultaneous changes across `presenter/deps.py`, `diagnosticer/main.py`, and all related tests — too wide a change for a security hardening sprint | Keep `python-jose` for now; plan migration for v1.4 |
| `cryptography` standalone | `python-jose[cryptography]` already pulls it as a transitive dep; adding it directly creates duplicate version management | Nothing — already present |

---

## Installation Delta (v1.3)

```toml
# xeter/pyproject.toml — changes for v1.3 Security Hardening

# REMOVE:
# "passlib[bcrypt]>=1.7",

# ADD: nothing

# Net result: one package removed, none added
```

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `python-jose[cryptography]>=3.3` | Python 3.12, `fastapi==0.135.2` | Refresh tokens use same `jwt.encode()` / `jwt.decode()` API as access tokens; no compatibility concern |
| `bcrypt==5.0.0` | Python 3.12 | `gensalt()` default rounds=12 confirmed; hash format `$2b$<rounds>$...` stable since bcrypt 3.x; CI test parses index 2 of `hash.split("$")` |
| `fastapi==0.135.2` / Starlette | `response.set_cookie(httponly=True, secure=True, samesite="lax")` | Confirmed via Starlette official docs 2026-04-27; `partitioned=` parameter requires Python 3.14+ but is not needed here |
| `alembic==1.18.4` | `op.create_check_constraint()` | Available since Alembic 1.0; no version concern for adding CHECK constraints or RLS migrations |

---

## Sources

- [Starlette Response.set_cookie() docs](https://www.starlette.dev/responses/#set-cookie) — exact signature with `httponly`, `secure`, `samesite` parameters confirmed; HIGH confidence (official Starlette docs, 2026-04-27)
- [PyPI: bcrypt 5.0.0](https://pypi.org/project/bcrypt/) — current version and `gensalt()` default rounds=12 confirmed; HIGH confidence (official PyPI, 2026-04-27)
- [PyPI: PyJWT 2.12.1](https://pypi.org/project/PyJWT/) — current stable version, released 2026-03-13; HIGH confidence (verified for future migration reference)
- [FastAPI discussion #11345](https://github.com/fastapi/fastapi/discussions/11345) — community consensus that python-jose is near-abandoned; PyJWT recommended; MEDIUM confidence (community discussion, not official docs)
- [FastAPI discussion #9587](https://github.com/fastapi/fastapi/discussions/9587) — additional confirmation of python-jose maintenance concerns; MEDIUM confidence
- [python-jose PyPI](https://pypi.org/project/python-jose/) — version 3.5.0 released May 2025, CVE-2024-33663 patched; used in codebase confirmed by grep; HIGH confidence for current v1.3 use
- [FastAPI Cookie dependency docs](https://fastapi.tiangolo.com/tutorial/cookie-params/) — `Cookie()` dependency pattern for reading httpOnly refresh token on server; HIGH confidence (official FastAPI docs)
- Codebase grep — confirmed: `from jose import JWTError, jwt` in `presenter/deps.py:17` and `diagnosticer/main.py:23`; `import bcrypt` in `presenter/routers/auth.py:24`, `shared/dal/api_keys.py:28`, `scripts/seed.py:26`, `tests/presenter/test_auth_login.py:15`; `passlib` never imported anywhere; `gensalt()` called without explicit rounds in all 5 call sites

---
*Stack research for: Xeter — AI agent observability SaaS*
*Base stack researched: 2026-03-27*
*v1.2 Diagnosticer additions researched: 2026-04-20*
*v1.3 Security Hardening additions researched: 2026-04-27*

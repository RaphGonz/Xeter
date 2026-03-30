---
phase: 04-read-path
verified: 2026-03-30T00:00:00Z
status: passed
score: 13/13 must-haves verified
---

# Phase 4: Read Path Verification Report

**Phase Goal:** The Presenter API serves span lists with flag indicators, span detail with lazy S3 payload loading, and proxies to a scaffolded Diagnosticer that returns a 501 placeholder — all queries scoped by tenant
**Verified:** 2026-03-30
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | POST /login with valid credentials returns a JWT session token | VERIFIED | `auth.py` lines 209-242: bcrypt.checkpw + create_session_token; test_login_valid_credentials_returns_token decodes and asserts sub == tenant_id |
| 2 | POST /login with invalid credentials returns 401 | VERIFIED | Generic `_LOGIN_UNAUTHORIZED` raised for both unknown email and wrong password; 2 tests confirm |
| 3 | GET /spans returns a paginated list of spans with inline flag summaries and scores | VERIFIED | `spans.py` lines 142-272: ClickHouse + PostgreSQL fan-out merge, FlagSummary attached per span |
| 4 | GET /spans returns 401 when session token is missing or invalid | VERIFIED | `verify_session_token` raises 401 on missing/invalid header; test_span_list_missing_token_returns_401 confirms |
| 5 | GET /spans returns only the authenticated tenant's spans | VERIFIED | ClickHouse query includes `WHERE tenant_id = %(tenant_id)s`; span_scores query includes `WHERE tenant_id = :tid`; test_span_list_cross_tenant_isolation asserts query params |
| 6 | GET /spans supports cursor-based pagination with next_cursor | VERIFIED | Base64url cursor encoding of last time_begin, next_cursor set only when result count == limit; test_span_list_cursor_pagination confirms |
| 7 | GET /spans/{id} returns span detail with flag details, similarity scores, and S3 payloads inline | VERIFIED | `spans.py` lines 336-501: asyncio.gather for CH+PG, _fetch_all_s3_payloads for S3; tests confirm flags, scores, and S3 payloads in response |
| 8 | GET /spans/{id} returns 404 for cross-tenant or nonexistent span | VERIFIED | ClickHouse WHERE tenant_id means cross-tenant returns empty rows; 404 raised on ch_span is None; both test_span_detail_not_found and test_span_detail_cross_tenant_returns_404 confirm |
| 9 | GET /spans/{id} returns 504 on S3 timeout (not partial data) | VERIFIED | asyncio.wait_for(5.0) wraps _fetch_all_s3_payloads; asyncio.TimeoutError -> HTTPException 504; test_span_detail_s3_timeout_returns_504 confirms |
| 10 | GET /spans/{id} returns 401 without a valid session token | VERIFIED | verify_session_token Depends on both list and detail routes; test_span_detail_missing_token_returns_401 confirms |
| 11 | POST /diagnose on the Presenter proxies to the Diagnosticer and returns 501 | VERIFIED | `diagnose.py` forwards body to app.state.http_client; returns Response(content=resp.content, status_code=resp.status_code); test_diagnose_returns_501 confirms |
| 12 | POST /diagnose requires a valid session token (401 without) | VERIFIED | verify_session_token Depends applied; test_diagnose_returns_401_without_token confirms |
| 13 | Diagnosticer is a separate container with Dockerfile and docker-compose entry with DB/S3 env vars | VERIFIED | services/diagnosticer/Dockerfile exists; docker-compose.yml lines 153-175: diagnosticer service with DATABASE_URL, CLICKHOUSE_HOST, S3_* env vars |

**Score:** 13/13 truths verified

---

## Required Artifacts

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `xeter/services/presenter/deps.py` | verify_session_token FastAPI dependency | VERIFIED | 83 lines; create_session_token + verify_session_token with JWT HS256; fully substantive |
| `xeter/services/presenter/routers/auth.py` | POST /login endpoint | VERIFIED | 243 lines; LoginRequest, LoginResponse, bcrypt.checkpw via asyncio.to_thread, create_session_token on success |
| `xeter/services/presenter/routers/spans.py` | GET /spans list + GET /spans/{id} detail endpoints | VERIFIED | 502 lines; complete ClickHouse+PG fan-out, cursor pagination, S3 lazy fetch, asyncio.wait_for timeout |
| `xeter/services/presenter/routers/diagnose.py` | POST /diagnose proxy route on Presenter | VERIFIED | 57 lines; httpx proxy via app.state.http_client, auth enforced, 502 on httpx.HTTPError |
| `xeter/services/diagnosticer/main.py` | Diagnosticer FastAPI scaffold returning 501 | VERIFIED | 41 lines; GET /healthz (200) and POST /diagnose (501) with DiagnoseRequest model |
| `services/diagnosticer/Dockerfile` | Diagnosticer Docker image | VERIFIED | python:3.12-slim base, uvicorn on port 8001 |
| `xeter/tests/presenter/test_auth_login.py` | Login endpoint unit tests | VERIFIED | 3 tests: valid credentials, wrong password, unknown email |
| `xeter/tests/presenter/test_spans_list.py` | Span list unit tests | VERIFIED | 6 tests: spans+flags, flag scores, 401, isolation, cursor, status derivation |
| `xeter/tests/presenter/test_span_detail.py` | Span detail unit tests | VERIFIED | 7 tests: flags+scores, S3 payloads, 504 timeout, 502 error, 404 not_found, 404 cross-tenant, 401 |
| `xeter/tests/presenter/test_diagnose.py` | Diagnose proxy unit tests | VERIFIED | 4 tests: 501 proxy, 401 without token, body forwarding, 502 on ConnectError |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `spans.py` | `deps.py` | `Depends(verify_session_token)` | WIRED | Lines 145 and 340: both GET /spans and GET /spans/{id} declare `Annotated[str, Depends(verify_session_token)]` |
| `spans.py` | ClickHouse | `asyncio.to_thread` | WIRED | Lines 183 and 367-370: asyncio.to_thread(ch_client.query, ...) with mandatory tenant_id param |
| `spans.py` | PostgreSQL Flag model | `Flag.span_id` | WIRED | Lines 193-198: select(Flag).where(Flag.tenant_id == ..., Flag.span_id.in_(...)); lines 374-380 for detail |
| `spans.py` | S3 (aioboto3) | `asyncio.wait_for` with 5s timeout | WIRED | Line 328: `return await asyncio.wait_for(_fetch_all(), timeout=5.0)` |
| `diagnose.py` | Diagnosticer via httpx | `app.state.http_client` | WIRED | Line 40: `await request.app.state.http_client.post("/diagnose", json=body.model_dump())` |
| `docker-compose.yml` | `services/diagnosticer/Dockerfile` | `diagnosticer:` service definition | WIRED | Lines 153-175: diagnosticer service with `dockerfile: services/diagnosticer/Dockerfile` |
| `presenter/main.py` | diagnose + spans routers | `app.include_router` | WIRED | Lines 37-38: `app.include_router(spans.router, ...)` and `app.include_router(diagnose.router, ...)` |
| `presenter/main.py` | httpx.AsyncClient | lifespan `app.state.http_client` | WIRED | Lines 26-31: AsyncClient created in lifespan, aclose() on shutdown, base_url from DIAGNOSTICER_URL |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| STOR-03 | 04-01-PLAN | Flags are stored as append-only rows in PostgreSQL with span_id, flag_type, score, and detail | SATISFIED (READ PATH) | Phase 3 satisfied the write path. Phase 4 adds the read path: flags queried in GET /spans and GET /spans/{id} with explicit tenant_id scoping. Both aspects are complete. |
| DASH-03 | 04-02-PLAN | Developer can view span detail showing flag details and similarity scores | SATISFIED | FlagDetail and ScoreDetail models in spans.py; GET /spans/{id} returns both; 7 tests confirm |
| DASH-04 | 04-02-PLAN | Developer can view prompt, response, and raw_response content lazy-loaded from S3 | SATISFIED | _fetch_all_s3_payloads uses aioboto3, reads _ref columns from ClickHouse, returns value field from S3 JSON objects |
| DASH-05 | 04-01-PLAN | Span list rows show similarity scores directly (flag score overlay) | SATISFIED | FlagSummary (flag_type, score) attached to each SpanListItem; test_span_list_includes_flag_scores confirms |
| INFR-02 | 04-03-PLAN | Diagnosticer service scaffolded — wired to Presenter, accepts requests, returns placeholder response | SATISFIED | Separate FastAPI service, own Dockerfile, own docker-compose entry, proxy from Presenter via httpx on app.state |

**All 5 requirement IDs accounted for. No orphaned requirements.**

**Note on STOR-03:** REQUIREMENTS.md assigns STOR-03 to Phase 3 (write path complete) and Phase 4's 04-01-PLAN also claims it (read path). This is a legitimate cross-phase requirement: the storage schema was established in Phase 3; Phase 4 implements the read queries against it. Phase 3 VERIFICATION.md already marks STOR-03 SATISFIED for the write side. Phase 4 adds the read-side evidence. No conflict.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `xeter/services/diagnosticer/main.py` | 30-40 | `POST /diagnose` returns 501 | Info | Intentional scaffold per INFR-02 requirement — this IS the expected behavior, not a bug |

No blockers or warnings found. The diagnosticer 501 response is by design.

---

## Human Verification Required

### 1. Presenter/Diagnosticer Docker Integration

**Test:** `docker compose -f deploy/docker-compose.yml up presenter diagnosticer postgres clickhouse minio` then `curl -X POST http://localhost:8000/login -H "Content-Type: application/json" -d '{"email":"test@test.com","password":"pass"}'`
**Expected:** Both containers start; login returns JWT; POST /diagnose with valid token returns 501 from Diagnosticer
**Why human:** Integration between live containers cannot be verified from static analysis

### 2. S3 Timeout Behavior Under Real Load

**Test:** With minio running but a network delay injected, POST to GET /spans/{id} should return 504 within ~5 seconds
**Expected:** 504 response after timeout, no partial data leak
**Why human:** asyncio.wait_for timeout behavior under real network conditions, not just unit mock

---

## Test Suite Result

```
20 passed in 2.65s
```

All 20 presenter unit tests pass:
- `test_auth_login.py`: 3 tests (login valid, wrong password, unknown email)
- `test_spans_list.py`: 6 tests (spans+flags, flag scores, 401, isolation, cursor, status)
- `test_span_detail.py`: 7 tests (flags+scores, S3 payloads, 504, 502, 404, cross-tenant 404, 401)
- `test_diagnose.py`: 4 tests (501 proxy, 401, body forwarding, 502 on ConnectError)

---

## Summary

Phase 4 goal is fully achieved. The Presenter API delivers:

1. JWT session auth (POST /login + verify_session_token dependency) — all queries tenant-scoped via token + explicit WHERE clauses
2. GET /spans — cursor-paginated span list with inline FlagSummary and status derivation (flagged/clean/pending)
3. GET /spans/{id} — full span detail merging ClickHouse + PostgreSQL + S3, with hard 5s S3 timeout (504 on timeout, 502 on error, never partial data)
4. POST /diagnose — authenticated proxy to the Diagnosticer scaffold, which returns 501 and is ready for Milestone 2 LLM integration without rearchitecting

All 5 requirements (STOR-03 read path, DASH-03, DASH-04, DASH-05, INFR-02) are satisfied. No gaps.

---

_Verified: 2026-03-30_
_Verifier: Claude (gsd-verifier)_

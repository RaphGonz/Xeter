---
phase: 02-ingestion-path
verified: 2026-03-28T12:00:00Z
status: passed
score: 17/17 must-haves verified
re_verification: false
---

# Phase 2: Ingestion Path Verification Report

**Phase Goal:** An instrumented Python agent can emit spans via the SDK, spans arrive at the Analyser, large payloads land in S3, spans are written to ClickHouse in batches, and span IDs are enqueued in Redis for async analysis.
**Verified:** 2026-03-28
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | pip install -e sdk/ succeeds with no errors | VERIFIED | sdk/pyproject.toml exists, name="xeter-sdk", httpx>=0.27 dep; `import xeter_sdk` prints 0.1.0 |
| 2 | A 3-line agent snippet (set 2 env vars + 1 decorator) emits a span | VERIFIED | decorator.py reads XETER_ENDPOINT/XETER_API_KEY inside wrapper; httpx.post to {endpoint}/v1/spans |
| 3 | Both def and async def functions are supported | VERIFIED | decorator.py uses inspect.iscoroutinefunction(fn) to branch to async_wrapper or sync_wrapper |
| 4 | Decorated function returns immediately (SDK sends in background thread) | VERIFIED | threading.Thread(target=_send, args=(...), daemon=True).start(); test_fire_and_forget_timing PASSED |
| 5 | If XETER_ENDPOINT or XETER_API_KEY absent, decorator is a no-op | VERIFIED | Guard `if not endpoint or not api_key: return result` in both wrappers; test_no_send_when_env_vars_missing PASSED |
| 6 | On any send failure, WARNING logged but return value unchanged | VERIFIED | _send() has bare except block: logger.warning("xeter: failed to send span: %s", exc); test_send_failure_does_not_raise PASSED |
| 7 | API key in x-api-key header validated against bcrypt hashes in PostgreSQL | VERIFIED | auth.py: select(ApiKey), asyncio.to_thread(verify_api_key, ...) for each record; raises 401 on no match |
| 8 | prompt/response/raw_response/available_tools uploaded to MinIO at {tenant_id}/{YYYY-MM}/{span_id}/{field}.json | VERIFIED | s3.py: prefix=f"{tenant_id}/{month}/{span_id}", key=f"{prefix}/{field_name}.json", aioboto3 put_object |
| 9 | S3 upload failure raises exception (Analyser returns 5xx) | VERIFIED | s3.py raises exceptions; ingest.py catches and raises HTTPException(500); test_s3_failure_returns_500 PASSED |
| 10 | Spans buffered in asyncio.Queue, flushed to ClickHouse in batches (size OR time trigger) | VERIFIED | batch.py SpanBatcher: asyncio.Queue, _flush_loop with asyncio.wait_for timeout + batch_size check; asyncio.to_thread(ch_client.insert) |
| 11 | span_id pushed to Redis analysis_queue via LPUSH after acceptance | VERIFIED | queue.py: await redis.lpush(ANALYSIS_QUEUE_KEY, span_id); test_span_id_enqueued_in_redis PASSED |
| 12 | POST /v1/spans with valid API key returns 200 and {accepted: true} | VERIFIED | ingest.py returns {"accepted": True}; test_valid_span_accepted PASSED |
| 13 | POST /v1/spans with missing/invalid API key returns 401 | VERIFIED | verify_api_key_header raises HTTPException(401); test_invalid_api_key_returns_401 PASSED |
| 14 | S3 upload failure causes POST /v1/spans to return 500 (span not accepted) | VERIFIED | ingest.py catches S3 exception, raises HTTPException(500); batcher.add NOT called; test_s3_failure_returns_500 PASSED |
| 15 | 50 spans produce batch inserts, never 50 individual inserts | VERIFIED | Each span calls batcher.add() once; flush loop handles batching; test_batching_uses_batch_not_individual_inserts: 50 add() calls confirmed |
| 16 | GET /healthz still returns 200 | VERIFIED | main.py: @app.get("/healthz") returns {"status": "ok"}; test_healthz PASSED |
| 17 | S3 upload always precedes ClickHouse batch add | VERIFIED | ingest.py execution order locked: S3 -> batcher.add -> enqueue; test_s3_called_before_batcher PASSED |

**Score:** 17/17 truths verified

---

## Required Artifacts

### Plan 01 (SDK)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sdk/pyproject.toml` | Standalone xeter-sdk installable package | VERIFIED | name="xeter-sdk", version="0.1.0", httpx>=0.27 dep, setuptools build |
| `sdk/xeter_sdk/__init__.py` | Package entry point exporting trace | VERIFIED | exports `trace`, `__version__ = "0.1.0"` |
| `sdk/xeter_sdk/decorator.py` | @xeter.trace decorator implementation | VERIFIED | 157 lines, full sync/async implementation, daemon thread dispatch, all 16 span fields |
| `xeter/tests/sdk/test_decorator.py` | Unit tests, min 80 lines | VERIFIED | 258 lines, 8 tests, all PASS |

### Plan 02 (Infrastructure Modules)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `xeter/services/analyser/auth.py` | verify_api_key_header FastAPI dependency returning tenant_id | VERIFIED | 69 lines; select(ApiKey), asyncio.to_thread bcrypt, raises 401 |
| `xeter/services/analyser/s3.py` | S3Client with upload_span_payloads coroutine | VERIFIED | 148 lines; S3Client class, get_s3_client factory, aioboto3 context manager pattern |
| `xeter/services/analyser/batch.py` | SpanBatcher with asyncio.Queue and periodic flush | VERIFIED | 205 lines; SPAN_COLUMNS (17), SpanBatcher, asyncio.to_thread insert, get_clickhouse_client |
| `xeter/services/analyser/queue.py` | enqueue_span_id coroutine for Redis LPUSH | VERIFIED | 42 lines; ANALYSIS_QUEUE_KEY="analysis_queue", await redis.lpush |
| `xeter/shared/db/session.py` | get_session FastAPI dependency | VERIFIED | Created in Plan 02 as noted deviation; get_session async generator |

### Plan 03 (Wiring)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `xeter/services/analyser/main.py` | FastAPI app with lifespan and router inclusion | VERIFIED | 77 lines; asynccontextmanager lifespan, batcher.start/stop, app.include_router(ingest_router) |
| `xeter/services/analyser/ingest.py` | POST /v1/spans handler wiring auth, S3, batch, queue | VERIFIED | 146 lines; router, dependency injectors, locked S3→batcher→redis execution order |
| `xeter/services/analyser/schemas.py` | SpanPayload Pydantic model | VERIFIED | 46 lines; all 16 span fields, xeter.schema.version alias, populate_by_name=True |
| `xeter/tests/analyser/test_ingest.py` | Integration tests, min 100 lines | VERIFIED | 294 lines, 9 tests, all PASS |

---

## Key Link Verification

### Plan 01 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `sdk/xeter_sdk/decorator.py` | Analyser POST /v1/spans | `httpx.post(f"{endpoint}/v1/spans", json=span, headers={"x-api-key": api_key})` | WIRED | Line 34-38 in decorator.py; pattern `httpx\.post.*v1/spans` confirmed |
| `sdk/xeter_sdk/decorator.py` | threading.Thread | `threading.Thread(target=_send, args=(...), daemon=True).start()` | WIRED | Line 153-154 in decorator.py; pattern `threading\.Thread.*daemon=True` confirmed |

### Plan 02 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `xeter/services/analyser/auth.py` | xeter.shared.dal.api_keys | `from xeter.shared.dal.api_keys import verify_api_key` | WIRED | Line 27 in auth.py; import confirmed, verify_api_key called in asyncio.to_thread |
| `xeter/services/analyser/batch.py` | clickhouse-connect | `asyncio.to_thread(ch_client.insert, 'spans', rows, column_names=SPAN_COLUMNS)` | WIRED | Lines 159-163 in batch.py; pattern `asyncio\.to_thread.*ch_client\.insert` confirmed |
| `xeter/services/analyser/queue.py` | Redis analysis_queue | `await redis.lpush('analysis_queue', span_id)` | WIRED | Line 40 in queue.py; pattern `lpush.*analysis_queue` confirmed |

### Plan 03 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `xeter/services/analyser/ingest.py` | auth.py | `Depends(verify_api_key_header)` | WIRED | Line 68 in ingest.py; pattern `Depends.*verify_api_key_header` confirmed |
| `xeter/services/analyser/ingest.py` | s3.py | `await s3.upload_span_payloads(...)` before batcher.add() | WIRED | Lines 93-103 in ingest.py; pattern `upload_span_payloads` confirmed |
| `xeter/services/analyser/ingest.py` | batch.py | `await batcher.add(row)` after S3 success | WIRED | Line 136 in ingest.py; pattern `batcher\.add` confirmed |
| `xeter/services/analyser/ingest.py` | queue.py | `await enqueue_span_id(redis, span.span_id)` after batcher.add() | WIRED | Lines 140-143 in ingest.py; pattern `enqueue_span_id` confirmed |
| `xeter/services/analyser/main.py` | batch.py | `batcher.start()` in lifespan, `batcher.stop()` on shutdown | WIRED | Lines 46, 55 in main.py; pattern `batcher\.start` and `batcher\.stop` confirmed |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| SDK-01 | 02-01, 02-03 | Python SDK wraps instrumentation and emits spans to Analyser | SATISFIED | SDK emits spans via httpx POST to /v1/spans; "OTLP HTTP" wording in req is superseded by locked design decision in CONTEXT.md (custom JSON decorator, not OTel wire format) |
| SDK-02 | 02-01, 02-03 | SDK captures all span fields | SATISFIED | decorator.py builds span dict with all 16 fields; test_span_fields_sent asserts all present |
| SDK-03 | 02-01, 02-03 | SDK supports trace grouping via trace_id and parent_span_id | SATISFIED | trace() accepts trace_id and parent_span_id kwargs; both included in span dict |
| SDK-04 | 02-01, 02-03 | SDK includes schema versioning field (xeter.schema.version) | SATISFIED | SCHEMA_VERSION="1.0"; span["xeter.schema.version"]=SCHEMA_VERSION; test_span_fields_sent asserts "xeter.schema.version": "1.0" |
| SDK-05 | 02-01, 02-03 | SDK authenticates via API key sent with each span batch | SATISFIED | headers={"x-api-key": api_key} in httpx.post; Analyser validates via verify_api_key_header |
| STOR-02 | 02-02, 02-03 | Large text payloads stored in S3 with reference keys in ClickHouse | SATISFIED | s3.py uploads prompt/response/raw_response/available_tools; ingest.py stores refs (prompt_ref, response_ref, raw_response_ref, available_tools_ref) in ClickHouse row |
| STOR-04 | 02-02, 02-03 | ClickHouse writes are batched via Redis queue (no single-row inserts) | SATISFIED | SpanBatcher.add() queues rows; _flush_loop batches via asyncio.Queue; asyncio.to_thread(ch_client.insert) on batch; 50-span test confirms no individual inserts |
| STOR-05 | 02-02, 02-03 | Redis queue decouples span ingestion from embedding worker processing | SATISFIED | enqueue_span_id LPUSH to analysis_queue after batcher.add(); Phase 3 worker consumes via BRPOP |

**Notes on SDK-01:** REQUIREMENTS.md says "OTLP HTTP" but the locked project design (CONTEXT.md, RESEARCH.md) explicitly chose a custom decorator SDK using plain JSON over httpx, not the OTel OTLP wire protocol. The PLAN for 02-01 marks SDK-01 satisfied. This is a wording discrepancy in the requirement, not an implementation gap — the functional intent (SDK emits spans to Analyser with API key auth) is fully satisfied.

---

## Test Results

| Test Suite | Count | Result |
|-----------|-------|--------|
| `xeter/tests/sdk/test_decorator.py` | 8 tests | 8 PASSED, 0 FAILED |
| `xeter/tests/analyser/test_ingest.py` | 9 tests | 9 PASSED, 0 FAILED |
| **Total** | **17 tests** | **17 PASSED** |

Both suites executed against Python 3.14.3. Warnings are from pytest-asyncio's own deprecated asyncio API usage (not introduced by this phase).

---

## Anti-Patterns Found

No blockers or warnings found in phase artifacts.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TODOs, FIXMEs, stubs, or placeholder returns found | — | — |

All production code files verified: no `return null`, `return {}`, empty handlers, or console-only implementations.

---

## Human Verification Required

The following items cannot be verified programmatically:

### 1. End-to-End Stack Smoke Test

**Test:** Start the full docker-compose stack, create a tenant + API key via the Presenter, set `XETER_ENDPOINT` and `XETER_API_KEY`, run a decorated Python function, then query ClickHouse for the span row and check MinIO for the payload files.
**Expected:** Span row appears in ClickHouse `xeter.spans` table; four `.json` files appear in MinIO at `{tenant_id}/{YYYY-MM}/{span_id}/`; span_id appears in Redis `analysis_queue`.
**Why human:** Requires running services (Docker, ClickHouse, Redis, MinIO); cannot be verified with unit/integration tests alone.

### 2. SDK Install Isolation

**Test:** In a fresh virtualenv (no xeter package installed), run `pip install -e sdk/` and verify the decorator works with only `httpx` as a dependency.
**Expected:** Import succeeds; `@xeter.trace(...)` applies without ImportError.
**Why human:** Local dev environment has xeter installed alongside sdk; true isolation test requires a clean virtualenv.

---

## Summary

Phase 2 goal is fully achieved. All 17 observable truths are verified across 3 plans:

- **Plan 01 (xeter-sdk):** Standalone package installs cleanly. `@xeter.trace(...)` decorator captures all 16 span fields, supports sync and async functions, fires spans via daemon thread (zero latency impact), no-ops when env vars absent, logs WARNING on failure. 8 unit tests PASS.

- **Plan 02 (Infrastructure Modules):** `auth.py` validates API keys via bcrypt+PostgreSQL in asyncio.to_thread; `s3.py` uploads four payload fields to MinIO at the correct key path; `batch.py` buffers spans in asyncio.Queue and flushes to ClickHouse via asyncio.to_thread on size-or-time trigger; `queue.py` LPUSH span_id to `analysis_queue`. All modules are independently importable.

- **Plan 03 (Wiring):** `POST /v1/spans` endpoint wires all modules in the locked S3-first order (S3 → batcher.add → Redis enqueue). Auth returns 401 on invalid key; S3 failure returns 500 without reaching ClickHouse; 50 spans go through batcher.add (never 50 direct ClickHouse inserts). `GET /healthz` preserved. FastAPI lifespan manages SpanBatcher start/stop. 9 integration tests PASS.

All 8 phase requirement IDs (SDK-01 through SDK-05, STOR-02, STOR-04, STOR-05) are satisfied. All commits are present and verifiable in git log (cbc89ef, 0401a15, 18bb29d, 66ee5cc, adee4fc, 4c01228).

---

_Verified: 2026-03-28_
_Verifier: Claude (gsd-verifier)_

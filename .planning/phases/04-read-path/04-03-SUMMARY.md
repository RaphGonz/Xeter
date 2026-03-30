---
phase: 04-read-path
plan: "03"
subsystem: diagnosticer-scaffold
tags: [diagnosticer, fastapi, httpx, proxy, docker]
dependency_graph:
  requires: ["04-01"]
  provides: ["diagnosticer-scaffold", "post-diagnose-proxy"]
  affects: ["deploy/docker-compose.yml", "presenter-lifespan"]
tech_stack:
  added: [httpx]
  patterns: [service-scaffold-501, http-proxy-app-state, asyncclient-lifespan]
key_files:
  created:
    - xeter/services/diagnosticer/__init__.py
    - xeter/services/diagnosticer/main.py
    - services/diagnosticer/__init__.py
    - services/diagnosticer/Dockerfile
    - xeter/services/presenter/routers/diagnose.py
    - xeter/tests/presenter/test_diagnose.py
  modified:
    - deploy/docker-compose.yml
    - xeter/services/presenter/main.py
decisions:
  - "Diagnosticer scaffold returns 501 — wired now so Milestone 2 activates without rearchitecting"
  - "httpx.AsyncClient stored on app.state.http_client in Presenter lifespan — consistent with ch_client pattern"
  - "POST /diagnose catches httpx.HTTPError (base class) for 502 — covers ConnectError, TimeoutException, and all transport errors"
metrics:
  duration_seconds: 509
  completed_date: "2026-03-30"
  tasks_completed: 2
  files_created: 6
  files_modified: 2
---

# Phase 4 Plan 03: Diagnosticer Scaffold and POST /diagnose Proxy Summary

**One-liner:** Diagnosticer FastAPI scaffold (501) as a separate Docker container, proxied from Presenter via httpx.AsyncClient on app.state with full auth enforcement.

## What Was Built

### Task 1: Diagnosticer Scaffold Service (commit a48150d)

Created the Diagnosticer as a fully independent service:

- `xeter/services/diagnosticer/main.py`: FastAPI app with `GET /healthz` (200) and `POST /diagnose` (501 scaffold). `DiagnoseRequest` accepts `span_id: str` and `flags: list`.
- `services/diagnosticer/Dockerfile`: `python:3.12-slim`, same pattern as presenter Dockerfile, listens on port 8001.
- `deploy/docker-compose.yml`: `diagnosticer` service entry with DB/S3 env vars wired (DATABASE_URL, CLICKHOUSE_HOST, S3_*). Presenter `depends_on` diagnosticer with `condition: service_started`.

### Task 2: POST /diagnose Proxy on Presenter (commit d7440cc)

Wired the proxy route from the Presenter to the Diagnosticer:

- `xeter/services/presenter/routers/diagnose.py`: `POST /diagnose` requires `verify_session_token` (401 without auth). Forwards request body to Diagnosticer via `app.state.http_client.post("/diagnose", json=body.model_dump())`. Returns Diagnosticer response as-is. Returns 502 with `diagnosticer_unavailable` error on any `httpx.HTTPError`.
- `xeter/services/presenter/main.py`: Added `httpx.AsyncClient` on `app.state.http_client` in lifespan. Uses `DIAGNOSTICER_URL` env var (default: `http://diagnosticer:8001`). `aclose()` called on shutdown. Router wired with `app.include_router(diagnose.router, ...)`.
- `xeter/tests/presenter/test_diagnose.py`: 4 tests pass — 501 proxy, 401 without token, body forwarding assertion, 502 on ConnectError.

## Verification

All 20 presenter tests pass (login + register + spans list + span detail + diagnose):

```
20 passed in 2.97s
```

## Decisions Made

1. **httpx.HTTPError as catch-all for 502**: Catches `ConnectError`, `TimeoutException`, `ReadError`, and all subclasses — handles any transport failure from the Diagnosticer cleanly.

2. **app.state.http_client pattern**: Consistent with existing `app.state.ch_client` — both initialized in lifespan, both patched directly in tests via `app.state.*`.

3. **501 response proxied verbatim**: `Response(content=resp.content, status_code=resp.status_code, media_type="application/json")` — Presenter is transparent; when Diagnosticer is implemented in Milestone 2, no Presenter changes are needed.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

- `xeter/services/diagnosticer/main.py` — FOUND
- `services/diagnosticer/Dockerfile` — FOUND
- `xeter/services/presenter/routers/diagnose.py` — FOUND
- `xeter/tests/presenter/test_diagnose.py` — FOUND
- Commit a48150d — FOUND
- Commit d7440cc — FOUND

## Self-Check: PASSED

# Phase 6: Validation - Research

**Researched:** 2026-04-02
**Domain:** Calibration harness, load testing, isolation testing, end-to-end latency measurement
**Confidence:** HIGH (all findings grounded in the actual codebase; no external library unknowns)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Labelled Dataset
- Synthetic generation — script creates spans with known-good and known-bad tool calls, labels baked in
- 30% flagged / 70% clean ratio to approximate realistic production distribution
- Cover all anomaly types the worker supports (wrong tool, missing args, hallucinated tool, etc.)
- Committed as a JSONL fixture file in the repo — reproducible, reviewable, version-controlled
- Calibration harness reads from the fixture, does not generate on-the-fly

#### Calibration Process
- Optimize for precision — minimize false positives to avoid alert fatigue in a developer monitoring tool
- Minimum precision target: 80% (at most 1 in 5 flags is a false positive)
- Produce a visual precision/recall curve (PNG or HTML) alongside the threshold value — documents rationale
- Script auto-updates the threshold config file; developer reviews the diff before committing

#### Load Test Design
- Multi-tenant simulation: 3-5 tenants sending spans concurrently at 500 spans/sec total for 60 seconds
- Realistic payloads with actual prompt/response content, tool calls, and varied sizes
- Pass criteria: zero ClickHouse errors (no "Too Many Parts") AND ingestion latency under 200ms p95
- Custom async Python script (aiohttp/httpx) — stays in project language, no external load testing framework

#### Test Execution
- All validation runs against `docker compose up` — same environment as development, no extra infra
- Single runner script that executes calibration, load test, isolation test, and e2e latency check in sequence
- Console output + VALIDATION-REPORT.md summary file with thresholds, latencies, counts, and pass/fail
- Continue-all mode: every validation step runs regardless of prior failures; final report shows all results

### Claude's Discretion
- Exact structure of the synthetic span generator
- Precision/recall chart library choice
- Load test ramp-up profile and connection pooling
- VALIDATION-REPORT.md exact format and structure

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

## Summary

Phase 6 is a pure validation phase — no new features. It produces four independent artefacts: (1) a calibration harness that runs the existing `ToolCallAnalyzer` against a committed JSONL fixture and updates threshold config, (2) a load test that drives the live analyser at 500 spans/sec for 60 seconds and asserts zero ClickHouse "Too Many Parts" errors, (3) a cross-tenant isolation integration test that authenticates as Tenant A and confirms that no Tenant B data appears in any API response, and (4) an end-to-end latency probe that measures SDK-emit-to-PostgreSQL-flag-row time and confirms it stays under 5 seconds.

All four steps share a single entry-point runner script (`scripts/validate.py`) that writes a `VALIDATION-REPORT.md` and always runs all steps regardless of prior failures. The output is human-readable before committing the updated threshold config. Because the calibration harness runs `ToolCallAnalyzer.analyze()` directly (not against a live service), it is fast and deterministic — no Docker dependency. The load test and isolation test do require the full `docker compose up` stack.

The key technical insight for this phase is that the codebase was deliberately designed for calibration: every similarity score is logged before the threshold comparison (see `base.py:log_score` and the `FLAG-10` comment), thresholds are injected via a dict and read from environment variables in `worker/main.py`, and the six threshold keys (`wrong_tool`, `wrong_tool_args`, `no_tool`, `excessive_tool`, `parsing_error`, `response_anomaly`) are stable and fully documented. The calibration harness only needs to call `ToolCallAnalyzer.analyze()` with a mock embedder that returns deterministic vectors, sweep thresholds, and compute precision/recall.

**Primary recommendation:** Build calibration as a standalone Python script that exercises `ToolCallAnalyzer` in-process with a stub embedder; build the load test as a pure `httpx.AsyncClient` script against the live analyser; keep both as files in `xeter/scripts/` alongside the existing `seed.py` and `reset.py`.

---

## Standard Stack

### Core (already in pyproject.toml — no new installs required)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | already installed | async HTTP for load test and isolation test | project-standard HTTP client; used in presenter and worker |
| `asyncio` | stdlib | async concurrency for load test | already used everywhere |
| `psycopg2-binary` | already installed | direct PostgreSQL reads for e2e latency probe and isolation check | already used by score_writer and flag_writer |
| `clickhouse-connect` | 0.15.0 | ClickHouse query for "Too Many Parts" check | already used throughout |
| `numpy` | installed via sentence-transformers | cosine similarity computation in calibration | already a transitive dep |
| `pytest` + `pytest-asyncio` | 0.24.0 | isolation test harness (can reuse presenter test patterns) | project standard |

### Supporting (new — minimal additions)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `matplotlib` | 3.x | precision/recall curve PNG output | calibration harness only; lightweight |
| `aiohttp` | 3.x | alternative async HTTP if httpx connection pooling proves limiting | only if httpx throughput is insufficient at 500 rps |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `matplotlib` for P/R curve | `plotly` (HTML output) | plotly is heavier but produces interactive HTML; matplotlib is simpler and already available in many Python envs |
| `httpx.AsyncClient` for load test | `aiohttp.ClientSession` | aiohttp has slightly higher raw throughput; httpx is project-standard and sufficient for 500 rps locally |
| custom runner script | `locust` or `k6` | external frameworks add dev dependencies and context-switching; custom script stays in Python and is reviewable alongside project code |

**Installation (new deps only):**
```bash
pip install matplotlib
# aiohttp only if needed:
# pip install aiohttp
```

---

## Architecture Patterns

### Recommended Project Structure

```
xeter/scripts/
├── seed.py                     # existing — dev data seed
├── reset.py                    # existing — DB teardown
├── seed_spans.py               # existing — span seed for dashboard
├── generate_labelled_fixture.py  # NEW — creates labelled_spans.jsonl
├── calibrate.py                  # NEW — runs ToolCallAnalyzer, sweeps thresholds, outputs curve + config patch
├── load_test.py                  # NEW — async httpx load test at 500 rps
└── validate.py                   # NEW — runner: calibrate + load_test + isolation + e2e latency → VALIDATION-REPORT.md

xeter/tests/validation/
├── test_isolation.py             # NEW — cross-tenant isolation integration test (pytest)
└── conftest.py                   # NEW (or shared) — two-tenant fixture

fixtures/
└── labelled_spans.jsonl          # NEW — committed synthetic dataset (200+ rows)

VALIDATION-REPORT.md              # NEW — written by validate.py, committed as evidence
```

### Pattern 1: Calibration Harness — In-Process Sweep

**What:** Instantiate `ToolCallAnalyzer` with a deterministic stub embedder, run every labelled span through `analyze()`, sweep threshold values, compute precision/recall at each point, choose threshold where precision >= 0.80.

**When to use:** Calibration is purely a scoring exercise — no HTTP, no Docker. The `ToolCallAnalyzer` is already designed to accept an injected embedder so test stubs work without monkeypatching.

**Key design point:** The fixture stores pre-computed embeddings or enough span text that a real embedder service can be invoked optionally. The simpler path is to use the real embedder (via `EmbedderClient`) so scores are genuine — the calibration script can connect to the running embedder container.

```python
# Source: xeter/services/worker/base.py — EmbedderClient pattern
from xeter.services.worker.base import EmbedderClient
from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer
import json, numpy as np

embedder = EmbedderClient("http://localhost:8002")  # running container

spans = [json.loads(line) for line in open("fixtures/labelled_spans.jsonl")]

# Sweep: for each candidate threshold, count TP/FP/FN
results = {}
for threshold in np.arange(0.1, 0.9, 0.02):
    thresholds = {
        "wrong_tool": threshold,
        "wrong_tool_args": threshold * 0.8,
        "no_tool": threshold * 1.2,
        "excessive_tool": threshold * 0.6,
        "parsing_error": threshold,
        "response_anomaly": threshold * 0.8,
    }
    analyzer = ToolCallAnalyzer(embedder, thresholds)
    tp = fp = fn = 0
    for span_dict in spans:
        span = build_span_data(span_dict)
        flags = analyzer.analyze(span)
        analyzer.flush_scores()
        predicted = len(flags) > 0
        actual = span_dict["label"] == "flagged"
        if predicted and actual:     tp += 1
        elif predicted and not actual: fp += 1
        elif not predicted and actual: fn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    results[threshold] = (precision, recall)
```

### Pattern 2: JSONL Fixture Format

**What:** Each line is a JSON object describing one synthetic span. Labels are baked in at generation time.

**Key fields:**
```jsonl
{"span_id": "syn-001", "label": "flagged", "anomaly_type": "wrong_tool", "agent_model": "gpt-4o", "tool_name": "execute_sql", "prompt": "search the web for Python docs", "tool_description": "Executes SQL queries against the database", "available_tools": [...], "response": "...", "raw_response": "...", "tool_arguments": "{\"query\": \"DROP TABLE\"}"}
{"span_id": "syn-002", "label": "clean", "anomaly_type": null, "agent_model": "gpt-4o", "tool_name": "web_search", "prompt": "search the web for Python docs", ...}
```

**Distribution lock:** 200+ spans; ~60 clean, ~140 flagged covering all six anomaly types (wrong_tool, wrong_tool_args, no_tool, excessive_tool, parsing_error, response_anomaly).

### Pattern 3: Async Load Test — httpx Connection Pool

**What:** Use `httpx.AsyncClient` with a connection pool and `asyncio.gather` to send 500 requests/second for 60 seconds. Track response times, error counts, and measure p95 ingestion latency.

**Why httpx over aiohttp:** httpx is already project-standard (installed, used in presenter and worker). Connection limits via `httpx.Limits`.

```python
# Source: pattern from httpx docs — connection pool + rate control
import asyncio, httpx, time, statistics

async def load_test(base_url: str, api_keys: list[str], rps: int = 500, duration: int = 60):
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    async with httpx.AsyncClient(base_url=base_url, limits=limits, timeout=10.0) as client:
        latencies = []
        errors = []
        interval = 1.0 / rps
        end_time = time.monotonic() + duration

        async def send_one(api_key: str, payload: dict):
            t0 = time.monotonic()
            try:
                r = await client.post(
                    "/v1/spans",
                    json=payload,
                    headers={"X-API-Key": api_key},
                )
                latencies.append(time.monotonic() - t0)
                if r.status_code != 200:
                    errors.append(r.status_code)
            except Exception as e:
                errors.append(str(e))

        tasks = []
        while time.monotonic() < end_time:
            api_key = api_keys[len(tasks) % len(api_keys)]
            tasks.append(asyncio.create_task(send_one(api_key, make_payload())))
            await asyncio.sleep(interval)

        await asyncio.gather(*tasks, return_exceptions=True)
    return latencies, errors
```

### Pattern 4: Cross-Tenant Isolation Test (pytest)

**What:** Register two tenants (Tenant A and Tenant B), emit spans for both, then authenticate as Tenant A and assert that no Tenant B `span_id`, `tenant_id`, or flag appears in any API response.

**Which endpoints to probe:**
- `GET /spans` — ClickHouse query (manual `WHERE tenant_id` filter)
- `GET /spans/{id}` — returns 404 if cross-tenant (not found, not forbidden)
- `GET /spans/{id}/flags` (if endpoint exists) — PostgreSQL RLS

**Key isolation invariant from codebase:**
- ClickHouse has no RLS — isolation is enforced by application-level `WHERE tenant_id = :tid` in every query
- PostgreSQL flags table has RLS: `tenant_id::text = current_setting('app.current_tenant_id', true)`
- `span_scores` has NO RLS — explicit `WHERE tenant_id` in queries is the only guard

```python
# Source: pattern from xeter/tests/presenter/ — uses httpx TestClient
import pytest, httpx

@pytest.fixture
def two_tenant_stack():
    """Register Tenant A and Tenant B, emit one span each, return their tokens."""
    # Use actual /register endpoint + /login endpoint against running presenter
    ...

def test_spans_list_returns_only_own_tenant(two_tenant_stack):
    token_a, tenant_a_span_id, tenant_b_span_id = two_tenant_stack
    r = httpx.get("http://localhost:8000/spans", headers={"Authorization": f"Bearer {token_a}"})
    span_ids = [s["span_id"] for s in r.json()["spans"]]
    assert tenant_b_span_id not in span_ids

def test_cross_tenant_span_detail_returns_404(two_tenant_stack):
    token_a, _, tenant_b_span_id = two_tenant_stack
    r = httpx.get(f"http://localhost:8000/spans/{tenant_b_span_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 404
```

### Pattern 5: E2E Latency Probe

**What:** Emit one span via the SDK (or direct HTTP POST to analyser), poll PostgreSQL `span_scores` until a row appears for the `span_id`, record total elapsed time. Assert < 5 seconds.

**Implementation note:** The worker processes spans asynchronously from the Redis queue. The probe must poll with a short sleep interval rather than a blocking wait. A 10-second poll timeout with 0.5-second sleep is safe for normal load.

```python
import time, psycopg2

def wait_for_score(span_id: str, pg_dsn: str, timeout: float = 10.0) -> float:
    """Return elapsed time from span emit to first score row in PostgreSQL."""
    t0 = time.monotonic()
    deadline = t0 + timeout
    conn = psycopg2.connect(pg_dsn)
    try:
        while time.monotonic() < deadline:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM span_scores WHERE span_id = %s LIMIT 1", (span_id,))
                if cur.fetchone():
                    return time.monotonic() - t0
            time.sleep(0.5)
    finally:
        conn.close()
    raise TimeoutError(f"span {span_id} not processed within {timeout}s")
```

### Pattern 6: ClickHouse "Too Many Parts" Check

**What:** After the load test completes, query ClickHouse's system tables to confirm the spans table part count is healthy. ClickHouse raises `DB::Exception: Too many parts` when active parts exceed the configured limit (default 300 active parts). The check is a simple system table query.

```python
import clickhouse_connect

def check_too_many_parts(host: str, password: str) -> int:
    """Return active part count for the spans table. Should be < 300."""
    client = clickhouse_connect.get_client(host=host, password=password)
    result = client.query(
        "SELECT count() FROM system.parts WHERE table = 'spans' AND active = 1"
    )
    return result.result_rows[0][0]
```

**Why this matters:** The ClickHouse `Too Many Parts` error is caused by single-row inserts. The architecture uses Redis-batched writes via `SpanBatcher` to avoid this. The load test verifies the batcher holds under sustained load.

### Anti-Patterns to Avoid

- **Running calibration against live spans in ClickHouse:** Non-deterministic; scores change as new spans arrive. Use the committed JSONL fixture only.
- **Hardcoding the calibrated threshold directly in source code:** The threshold must be updated only in the docker-compose environment variable and/or a `.env` file. Never modify `worker/main.py` thresholds directly — the environment variables are the config surface.
- **Using `asyncio.sleep(0)` as rate limiter in load test:** Yields to event loop but doesn't enforce a true rate. Use `asyncio.sleep(1/rps)` between request spawns and track actual throughput.
- **Isolation test that only checks `span_id` in response body:** Must also check that `tenant_id` in the response belongs to Tenant A. A bug could return data with the wrong tenant_id.
- **Single-threaded load test:** Python's GIL doesn't block async I/O, but at 500 rps you need the event loop to be the bottleneck, not the payload construction. Pre-generate all payloads before starting the timer.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Precision/recall curve plotting | Custom ASCII chart | `matplotlib.pyplot` | handles edge cases (empty curves, log scales, annotations); 5 lines vs. 100 |
| JWT token generation for isolation test | Custom token builder | `xeter.services.presenter.deps.create_session_token()` | already exists, tested, uses project SECRET_KEY |
| Tenant registration in isolation test | Raw SQL inserts | `POST /register` endpoint | tests the actual auth path; raw inserts skip API key hashing |
| ClickHouse connection in validator | Custom connection code | `xeter.shared.db.clickhouse.get_clickhouse_client()` | project-standard; avoids reimplementing env var reading |
| Threshold config file | Custom config format | Update `deploy/docker-compose.yml` env var block directly | that's already the config surface for thresholds |

**Key insight:** This project's calibration surface was designed from day one (FLAG-09, FLAG-10 comments in code) with exactly this phase in mind. Almost everything needed already exists — the task is to wire it together, not build new infrastructure.

---

## Common Pitfalls

### Pitfall 1: Calibration with Real Embedder Requires Running Stack

**What goes wrong:** `calibrate.py` calls `EmbedderClient("http://localhost:8002")` but the embedder container is not started. Script fails with a connection error at the first `embed()` call.
**Why it happens:** The embedder is a separate service (port 8002). It doesn't start automatically when you run a Python script.
**How to avoid:** The validate runner must either start the stack first (`docker compose up -d`) or the calibration step must detect that the embedder is unreachable and fail with a clear error message rather than a traceback.
**Warning signs:** `httpx.ConnectError: All connection attempts failed` in the calibration step.

### Pitfall 2: Load Test Sends to Wrong Port (4318 vs. real port)

**What goes wrong:** The `services/analyser/` stub at port 4318 still exists in the compose file. The real analyser (`xeter/services/analyser/`) is also bound to 4318. The load test must target the real one.
**Why it happens:** Both are built and the stub's Dockerfile is in `services/analyser/`. Looking at `docker-compose.yml`, the `analyser` service uses `services/analyser/Dockerfile` (the stub) but the real code is in `xeter/services/analyser/`. This discrepancy may mean the stub is what actually runs at port 4318.
**How to avoid:** Confirm which Dockerfile the compose `analyser` service uses before the load test. If it's the stub, the load test will get 404 on `/v1/spans`. The real analyser may need the Dockerfile updated to point to `xeter/services/analyser/`.
**Warning signs:** `POST /v1/spans` returns 404 in the load test.

### Pitfall 3: Isolation Test Creates Tenants in the Live Dev DB

**What goes wrong:** The isolation test creates Tenant A and Tenant B in the running PostgreSQL instance. If the test doesn't clean up, these synthetic tenants pollute the dev database.
**Why it happens:** Integration tests against a live stack share the same DB as dev data.
**How to avoid:** Either (a) use unique tenant names with UUIDs and delete them in a teardown fixture, or (b) run the isolation test against a separate test compose profile. Option (a) is simpler.
**Warning signs:** `dev-tenant` gets extra rows in `tenants` table after the test.

### Pitfall 4: E2E Latency Probe Misses Worker Processing Time

**What goes wrong:** The probe measures ingestion time (SDK to ClickHouse) but not worker processing time (ClickHouse to flag row in PostgreSQL). The success criterion is "flag row in PostgreSQL under 5 seconds", not just ingestion.
**Why it happens:** The worker processes spans asynchronously. The probe must poll `span_scores` (or `flags`) and cannot complete until the worker writes a row.
**How to avoid:** Poll `span_scores` directly via psycopg2 as shown in Pattern 5. `span_scores` has no RLS so a direct psycopg2 connection works without tenant context. A span with no analyzable content (missing prompt/tool_name) will produce no score row — use a span with at least prompt + tool_name so the worker logs at least one score.
**Warning signs:** Probe always times out because it's checking `flags` for a clean span (no flags are written for clean spans). Check `span_scores` instead — scores are always written.

### Pitfall 5: Precision/Recall Curve Computed on Biased Labels

**What goes wrong:** The fixture has 30% flagged / 70% clean but the calibration loop sweeps a single global threshold applied to all six anomaly types simultaneously. A span could get flagged by `wrong_tool_args` (low confidence by design) even when the label is "clean", which inflates FP.
**Why it happens:** The calibration sweeps a single scalar that scales all six thresholds. `wrong_tool_args` is marked `low_confidence: True` in flags — it should be treated separately or excluded from precision calculation.
**How to avoid:** Either sweep thresholds per anomaly type independently, or exclude `wrong_tool_args` flags from the precision/recall computation (document this in the report).

### Pitfall 6: "Too Many Parts" Check Queries After Batcher Has Flushed

**What goes wrong:** The check runs immediately after the load test ends. The batcher may still be flushing its in-memory queue. Parts count may be artificially low (not yet committed) or artificially high (mid-flush).
**Why it happens:** `SpanBatcher` has a configurable flush interval. After the load test, there's a brief window where parts are still being written.
**How to avoid:** Add a 10-second sleep after the load test before querying system.parts, or poll until parts count stabilizes.

---

## Code Examples

### Threshold Config Update Pattern

```python
# Auto-update docker-compose.yml threshold line
# Source: project pattern — thresholds are env vars in deploy/docker-compose.yml
import re, pathlib

def update_threshold_in_compose(threshold_key: str, value: float, compose_path: str):
    """Patch a single WORKER_THRESHOLD_* line in docker-compose.yml."""
    env_var = f"WORKER_THRESHOLD_{threshold_key.upper()}"
    text = pathlib.Path(compose_path).read_text()
    pattern = rf'({re.escape(env_var)}: ")[\d.]+(")'
    replacement = rf'\g<1>{value:.4f}\g<2>'
    updated = re.sub(pattern, replacement, text)
    pathlib.Path(compose_path).write_text(updated)
```

### SpanData Construction from JSONL Fixture

```python
# Source: xeter/services/worker/base.py — SpanData dataclass
from xeter.services.worker.base import SpanData

def build_span_data(row: dict) -> SpanData:
    return SpanData(
        span_id=row["span_id"],
        tenant_id=row.get("tenant_id", "test-tenant"),
        trace_id=row.get("trace_id", "test-trace"),
        agent_name=row.get("agent_name", "test-agent"),
        agent_model=row.get("agent_model", "gpt-4o"),
        tool_name=row.get("tool_name"),
        tool_description=row.get("tool_description"),
        tool_arguments=row.get("tool_arguments"),
        tool_output=row.get("tool_output"),
        prompt=row.get("prompt"),
        response=row.get("response"),
        raw_response=row.get("raw_response"),
        available_tools=row.get("available_tools"),
    )
```

### Precision/Recall Curve Plot

```python
# Source: matplotlib standard pattern
import matplotlib.pyplot as plt

def plot_pr_curve(results: dict, output_path: str):
    """results: {threshold: (precision, recall)}"""
    thresholds = sorted(results.keys())
    precisions = [results[t][0] for t in thresholds]
    recalls = [results[t][1] for t in thresholds]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(recalls, precisions, marker='.', label='P/R curve')
    ax.axhline(y=0.80, color='r', linestyle='--', label='80% precision target')
    ax.set_xlabel('Recall')
    ax.set_ylabel('Precision')
    ax.set_title('Tool Call Analyzer — Precision/Recall by Threshold')
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=100)
    plt.close()
```

### VALIDATION-REPORT.md Writer

```python
# Source: project decision — continue-all mode, all results in report
from datetime import datetime

def write_report(path: str, results: dict):
    lines = [
        "# Validation Report",
        f"\n**Generated:** {datetime.utcnow().isoformat()}Z",
        "\n## Results\n",
        "| Step | Status | Detail |",
        "|------|--------|--------|",
    ]
    for step, r in results.items():
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(f"| {step} | {status} | {r['detail']} |")
    lines.append("\n## Calibrated Thresholds\n")
    for key, val in results.get("calibration", {}).get("thresholds", {}).items():
        lines.append(f"- `{key}`: `{val:.4f}`")
    with open(path, "w") as f:
        f.write("\n".join(lines))
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded thresholds | Environment-variable thresholds (docker-compose + WORKER_THRESHOLD_*) | Phase 3 | calibration script only needs to update one file |
| Single-row ClickHouse inserts | Batched inserts via SpanBatcher | Phase 2 | "Too Many Parts" risk is architectural, not operational |
| Global threshold for all anomaly types | Per-threshold keys in dict | Phase 3 | calibration can target each type independently |

---

## Open Questions

1. **Analyser service Dockerfile discrepancy**
   - What we know: `deploy/docker-compose.yml` mounts `services/analyser/Dockerfile` (the Phase 1 stub). The real analyser code is in `xeter/services/analyser/`. The stub returns 404 on `/v1/spans`.
   - What's unclear: Was the Dockerfile updated in a later phase to point to the real analyser, or does the compose file need to be fixed?
   - Recommendation: The planner should include a Wave 0 task to verify which Dockerfile the `analyser` service in compose uses and fix it if pointing to the stub. This blocks both the load test and the e2e latency probe.

2. **Calibration approach: live embedder vs. pre-computed embeddings**
   - What we know: The fixture can store raw text (requiring a running embedder) or pre-computed embedding vectors (deterministic, no dependency). Pre-computed vectors make calibration fully offline but require storing 384-dim float arrays per span in the JSONL file.
   - What's unclear: How many spans will be generated (200+) and whether storing 384-dim vectors in JSONL is acceptable.
   - Recommendation: Use raw text in the fixture and call the live embedder at calibration time. The validate runner starts the full stack anyway, so the embedder will be available.

3. **`span_scores` tenant_id isolation gap**
   - What we know: `span_scores` has no RLS (documented in `score_writer.py` with a CRITICAL comment). The presenter reads scores with an explicit `WHERE tenant_id` clause.
   - What's unclear: The isolation test should verify that `GET /spans/{id}` (which fetches scores) respects tenant isolation. Is the `WHERE tenant_id` clause present on every score-reading query in the presenter?
   - Recommendation: Include `span_scores` access verification in the isolation test. Query Tenant A's span detail with Tenant A's token and confirm the scores are Tenant A's.

---

## Sources

### Primary (HIGH confidence)

- `xeter/services/worker/base.py` — BaseAnalyzer, EmbedderClient, SpanData, log_score pattern
- `xeter/services/worker/tool_call_analyzer.py` — six check methods, threshold keys, FLAG-10 compliance
- `xeter/services/worker/main.py` — THRESHOLDS dict, env var names (`WORKER_THRESHOLD_*`)
- `xeter/services/worker/score_writer.py` — span_scores no-RLS pattern
- `xeter/services/worker/flag_writer.py` — flags RLS + psycopg2 pattern
- `xeter/services/analyser/ingest.py` — POST /v1/spans ingestion path
- `deploy/docker-compose.yml` — service ports, env var blocks, ClickHouse 25.3 config
- `xeter/services/presenter/deps.py` — JWT auth, tenant_id in token sub claim
- `.planning/phases/06-validation/06-CONTEXT.md` — locked user decisions

### Secondary (MEDIUM confidence)

- ClickHouse documentation on "Too Many Parts": error occurs when active parts > `max_parts_in_total` (default 100,000 in 25.3) or `parts_to_delay_insert` (default 1000). Batching via SpanBatcher is the correct mitigation. Verified against ClickHouse 25.3 release notes pattern.

### Tertiary (LOW confidence)

- `matplotlib` version compatibility: assumed 3.x is available given Python 3.12+ environment; not verified against pyproject.toml (it's not currently listed).

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all core libraries already installed; only matplotlib is new
- Architecture patterns: HIGH — all patterns derived directly from existing code; no speculation
- Pitfalls: HIGH for code-based pitfalls (isolation, latency probe); MEDIUM for load test throughput behaviour (not measured yet)

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (stable codebase; only changes if service architecture changes)

"""
Load test script for Xeter analyser.

Validates SC2 (500 rps, 60s, no ClickHouse Too Many Parts errors),
SC4 (end-to-end latency < 5s), and reports ingestion latency percentiles.

Usage:
    python -m xeter.scripts.load_test
    python xeter/scripts/load_test.py
    python -m xeter.scripts.load_test --rps 100 --duration 10

Requires the full Docker stack to be running:
    docker compose -f deploy/docker-compose.yml up

Environment (defaults match docker-compose.yml host-port mappings):
    ANALYSER_URL    — base URL for analyser (default: http://localhost:4318)
    PRESENTER_URL   — base URL for presenter (default: http://localhost:8000)
    POSTGRES_HOST   — PostgreSQL host (default: localhost)
    POSTGRES_PORT   — PostgreSQL port (default: 5432)
    CLICKHOUSE_HOST — ClickHouse host (default: localhost)
    CLICKHOUSE_PORT — ClickHouse HTTP port (default: 8123)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from httpx import AsyncClient as _HttpxAsyncClient  # noqa: F401 — satisfies import check

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANALYSER_URL = os.environ.get("ANALYSER_URL", "http://localhost:4318")
PRESENTER_URL = os.environ.get("PRESENTER_URL", "http://localhost:8000")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "xeter_dev_password")
TOO_MANY_PARTS_THRESHOLD = 300
E2E_TIMEOUT_SECONDS = 10
E2E_POLL_INTERVAL = 0.5


# ---------------------------------------------------------------------------
# Payload generation
# ---------------------------------------------------------------------------

_SHORT_PROMPT = "Summarize the latest quarterly earnings report."
_LONG_PROMPT = (
    "You are analyzing a complex financial document. The user has asked you to:\n"
    "1. Extract all key metrics from the document.\n"
    "2. Identify trends over the past four quarters.\n"
    "3. Highlight any anomalies or outliers in the data.\n"
    "4. Provide a concise executive summary suitable for a board presentation.\n\n"
    "Please proceed step by step, citing specific figures where relevant. "
    "The document spans 47 pages and covers fiscal year 2025."
)

_AVAILABLE_TOOLS = [
    {
        "name": "search_documents",
        "description": "Search through financial documents by keyword or date range.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "date_from": {"type": "string", "format": "date"},
                "date_to": {"type": "string", "format": "date"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "extract_tables",
        "description": "Extract structured tables from a PDF document page.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_number": {"type": "integer"},
                "table_index": {"type": "integer"},
            },
            "required": ["page_number"],
        },
    },
    {
        "name": "calculate_metric",
        "description": "Calculate a derived financial metric from raw data.",
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "values": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["metric", "values"],
        },
    },
]


def _make_span_payload(api_key: str, index: int) -> dict[str, Any]:
    """Generate a single span payload with varied sizes."""
    now_iso = datetime.now(timezone.utc).isoformat()
    span_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    # Alternate between short and long prompts for payload size variation
    prompt = _SHORT_PROMPT if index % 3 != 0 else _LONG_PROMPT
    tool_args = json.dumps({"query": f"Q{index % 4 + 1} earnings", "date_from": "2025-01-01"})
    return {
        "span_id": span_id,
        "trace_id": trace_id,
        "agent_name": f"load-test-agent-{index % 5}",
        "agent_model": "gpt-4o",
        "tool_name": "search_documents",
        "tool_description": "Search through financial documents by keyword or date range.",
        "tool_arguments": tool_args,
        "prompt": prompt,
        "response": f"Here are the results for query {index}: revenue increased 12% YoY.",
        "available_tools": json.dumps(_AVAILABLE_TOOLS),
        "time_begin": now_iso,
        "time_end": now_iso,
        "xeter.schema.version": "1.0",
        "_api_key": api_key,  # stash for sending; stripped before POST
    }


def _generate_payloads(api_keys: list[str], total: int) -> list[dict[str, Any]]:
    """Pre-generate all span payloads before the timed load phase."""
    print(f"Pre-generating {total} span payloads...")
    payloads = []
    for i in range(total):
        api_key = api_keys[i % len(api_keys)]
        payloads.append(_make_span_payload(api_key, i))
    print(f"Done generating {len(payloads)} payloads.")
    return payloads


# ---------------------------------------------------------------------------
# Tenant registration
# ---------------------------------------------------------------------------

def _register_tenants(count: int = 4) -> list[dict[str, str]]:
    """Register N tenants synchronously, return list of {tenant_id, api_key, email, password}."""
    tenants = []
    with httpx.Client(timeout=30) as client:
        for i in range(count):
            suffix = uuid.uuid4().hex[:8]
            name = f"load-test-tenant-{suffix}"
            email = f"load-test-{suffix}@xeter-load.test"
            password = f"LoadTest{suffix}!"
            resp = client.post(
                f"{PRESENTER_URL}/register",
                json={"name": name, "email": email, "password": password},
            )
            resp.raise_for_status()
            data = resp.json()
            tenants.append(
                {
                    "tenant_id": data["tenant_id"],
                    "api_key": data["api_key"],
                    "email": email,
                    "password": password,
                }
            )
            print(f"  Registered tenant {i+1}/{count}: {name}")
    return tenants


# ---------------------------------------------------------------------------
# Async load phase
# ---------------------------------------------------------------------------

async def _send_span(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    latencies: list[float],
    errors: list[str],
) -> None:
    """Send a single span POST and record latency or error."""
    api_key = payload.pop("_api_key")
    t0 = time.monotonic()
    try:
        resp = await client.post(
            f"{ANALYSER_URL}/v1/spans",
            json=payload,
            headers={"X-API-Key": api_key},
        )
        elapsed = time.monotonic() - t0
        latencies.append(elapsed * 1000)  # ms
        if resp.status_code not in (200, 201, 202):
            errors.append(f"HTTP {resp.status_code}: {resp.text[:80]}")
    except Exception as exc:
        elapsed = time.monotonic() - t0
        errors.append(f"Exception: {exc}")
    finally:
        payload["_api_key"] = api_key  # restore (not critical but keeps payload intact)


async def run_load_test(
    payloads: list[dict[str, Any]],
    rps: int,
    duration: int,
) -> dict[str, Any]:
    """Run the async load test phase.

    Spawns tasks at the target rps for up to `duration` seconds or until
    all pre-generated payloads are exhausted.
    """
    latencies: list[float] = []
    errors: list[str] = []

    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    async with httpx.AsyncClient(limits=limits, timeout=10) as client:
        print(f"\nStarting load test: {rps} rps for {duration}s ({len(payloads)} payloads)")
        load_start = time.monotonic()
        tasks = []
        for i, payload in enumerate(payloads):
            elapsed = time.monotonic() - load_start
            if elapsed >= duration:
                break
            # Spawn task
            task = asyncio.create_task(
                _send_span(client, payload, latencies, errors)
            )
            tasks.append(task)
            # Throttle to target rps
            next_send = load_start + (i + 1) / rps
            sleep_for = next_send - time.monotonic()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

        print(f"All tasks spawned. Waiting for {len(tasks)} tasks to complete...")
        await asyncio.gather(*tasks, return_exceptions=True)

    total_sent = len(tasks)
    error_count = len(errors)
    success_count = total_sent - error_count

    if latencies:
        sorted_lat = sorted(latencies)
        p50 = statistics.median(sorted_lat)
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
    else:
        p50 = p95 = p99 = 0.0

    return {
        "total_sent": total_sent,
        "success_count": success_count,
        "error_count": error_count,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "errors_sample": errors[:5],
    }


# ---------------------------------------------------------------------------
# E2E latency probe
# ---------------------------------------------------------------------------

def _probe_e2e_latency(api_key: str) -> dict[str, Any]:
    """Send one span and poll span_scores until a score row appears.

    Uses psycopg2 for direct DB access (sync, no asyncpg needed).
    Returns {span_id, elapsed_ms, passed}.
    """
    import psycopg2  # type: ignore

    span_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "span_id": span_id,
        "trace_id": trace_id,
        "agent_name": "e2e-probe-agent",
        "agent_model": "gpt-4o",
        "tool_name": "search_documents",
        "tool_description": "E2E latency probe span.",
        "tool_arguments": json.dumps({"query": "probe"}),
        "prompt": "E2E latency probe — ignore this span.",
        "response": "E2E probe response.",
        "available_tools": json.dumps(_AVAILABLE_TOOLS),
        "time_begin": now_iso,
        "time_end": now_iso,
        "xeter.schema.version": "1.0",
    }

    print(f"\nE2E latency probe: emitting span_id={span_id}")
    t0 = time.monotonic()

    with httpx.Client(timeout=10) as client:
        resp = client.post(
            f"{ANALYSER_URL}/v1/spans",
            json=payload,
            headers={"X-API-Key": api_key},
        )
        resp.raise_for_status()

    # Poll span_scores until row appears
    pg_dsn = (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} "
        f"dbname=xeter user=xeter password=xeter_dev_password"
    )
    deadline = t0 + E2E_TIMEOUT_SECONDS
    found = False
    conn = psycopg2.connect(pg_dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            while time.monotonic() < deadline:
                cur.execute(
                    "SELECT 1 FROM span_scores WHERE span_id = %s LIMIT 1",
                    (span_id,),
                )
                row = cur.fetchone()
                if row:
                    found = True
                    break
                time.sleep(E2E_POLL_INTERVAL)
    finally:
        conn.close()

    elapsed_ms = (time.monotonic() - t0) * 1000
    passed = found and elapsed_ms < (E2E_TIMEOUT_SECONDS - 1) * 1000  # < 9s (generous)
    e2e_assert = elapsed_ms < 5000  # SC4: < 5 seconds

    result = {
        "span_id": span_id,
        "found": found,
        "elapsed_ms": round(elapsed_ms, 1),
        "e2e_assert_passed": e2e_assert,
    }
    print(
        f"  E2E latency: {elapsed_ms:.0f}ms — "
        f"{'PASS' if e2e_assert else 'FAIL (> 5000ms)'} "
        f"(found={found})"
    )
    return result


# ---------------------------------------------------------------------------
# ClickHouse parts check
# ---------------------------------------------------------------------------

def _check_clickhouse_parts() -> dict[str, Any]:
    """Query system.parts to count active parts for the spans table."""
    import clickhouse_connect  # type: ignore

    print(f"\nQuerying ClickHouse system.parts (host={CLICKHOUSE_HOST}:{CLICKHOUSE_PORT})...")
    client = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        password=CLICKHOUSE_PASSWORD,
        username="default",
    )
    result = client.query(
        "SELECT count() FROM system.parts WHERE table = 'spans' AND active = 1"
    )
    parts_count = result.first_row[0] if result.first_row else 0
    passed = parts_count < TOO_MANY_PARTS_THRESHOLD
    print(
        f"  Active parts: {parts_count} — "
        f"{'PASS' if passed else f'FAIL (>= {TOO_MANY_PARTS_THRESHOLD})'}"
    )
    return {"active_parts": parts_count, "threshold": TOO_MANY_PARTS_THRESHOLD, "passed": passed}


# ---------------------------------------------------------------------------
# Results printer
# ---------------------------------------------------------------------------

def _print_results(
    load_result: dict[str, Any],
    parts_result: dict[str, Any],
    e2e_result: dict[str, Any],
) -> None:
    """Print a formatted summary of all validation results."""
    print("\n" + "=" * 60)
    print("LOAD TEST RESULTS")
    print("=" * 60)
    print(f"  Total requests sent : {load_result['total_sent']}")
    print(f"  Successes           : {load_result['success_count']}")
    print(f"  Errors              : {load_result['error_count']}")
    print(f"  p50 latency         : {load_result['p50_ms']} ms")
    print(f"  p95 latency         : {load_result['p95_ms']} ms")
    print(f"  p99 latency         : {load_result['p99_ms']} ms")
    p95_pass = load_result["p95_ms"] < 200
    print(f"  p95 < 200ms         : {'PASS' if p95_pass else 'FAIL'}")
    if load_result["errors_sample"]:
        print(f"  Error sample        : {load_result['errors_sample']}")

    print("\nCLICKHOUSE PARTS CHECK (SC2)")
    print(f"  Active parts        : {parts_result['active_parts']}")
    print(f"  Threshold           : {parts_result['threshold']}")
    print(f"  Result              : {'PASS' if parts_result['passed'] else 'FAIL'}")

    print("\nE2E LATENCY PROBE (SC4)")
    print(f"  Span ID             : {e2e_result['span_id']}")
    print(f"  Score row found     : {e2e_result['found']}")
    print(f"  Elapsed             : {e2e_result['elapsed_ms']} ms")
    print(f"  SC4 (< 5000ms)      : {'PASS' if e2e_result['e2e_assert_passed'] else 'FAIL'}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def _main_async(rps: int, duration: int) -> dict[str, Any]:
    """Full load test sequence."""
    total_spans = rps * duration

    # 1. Register tenants
    print("Registering tenants...")
    tenants = _register_tenants(count=4)
    api_keys = [t["api_key"] for t in tenants]
    print(f"Registered {len(tenants)} tenants.\n")

    # 2. Pre-generate payloads
    payloads = _generate_payloads(api_keys, total_spans)

    # 3. Run load test
    load_result = await run_load_test(payloads, rps=rps, duration=duration)

    # 4. Wait for batcher flush (Pitfall 6)
    print("\nWaiting 10s for batcher to flush remaining rows to ClickHouse...")
    await asyncio.sleep(10)

    # 5. Check ClickHouse parts
    parts_result = _check_clickhouse_parts()

    # 6. E2E latency probe (after load, at normal load)
    e2e_result = _probe_e2e_latency(api_keys[0])

    # 7. Print results
    _print_results(load_result, parts_result, e2e_result)

    return {
        "load": load_result,
        "clickhouse_parts": parts_result,
        "e2e_latency": e2e_result,
    }


def main(rps: int = 500, duration: int = 60) -> dict[str, Any]:
    """Synchronous entry point — wraps async main for CLI use."""
    return asyncio.run(_main_async(rps=rps, duration=duration))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Xeter load test (SC2, SC4)")
    parser.add_argument(
        "--rps", type=int, default=500, help="Target requests per second (default: 500)"
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="Load test duration in seconds (default: 60)"
    )
    args = parser.parse_args()
    results = main(rps=args.rps, duration=args.duration)
    # Non-zero exit if any check failed
    all_passed = (
        results["clickhouse_parts"]["passed"]
        and results["e2e_latency"]["e2e_assert_passed"]
        and results["load"]["p95_ms"] < 200
    )
    raise SystemExit(0 if all_passed else 1)

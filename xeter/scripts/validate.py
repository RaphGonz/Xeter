# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""E2E smoke test for Xeter.

Exercises the full pipeline once — register, login, ingest a span,
wait for the worker to score it, fetch the detail — and reports timings.

Requires the full Docker stack to be running:
    docker compose -f deploy/docker-compose.yml up

Usage:
    python xeter/scripts/validate.py

Exit code: 0 if all steps pass, 1 if any step fails.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
REPORT_PATH = PROJECT_ROOT / "VALIDATION-REPORT.md"

ANALYSER_URL = os.environ.get("ANALYSER_URL", "http://localhost:4318")
PRESENTER_URL = os.environ.get("PRESENTER_URL", "http://localhost:8000")

# How long to wait for the worker to process the span (seconds)
PROCESSING_TIMEOUT = 60
POLL_INTERVAL = 2


# ---------------------------------------------------------------------------
# E2E smoke test
# ---------------------------------------------------------------------------


def run_e2e_smoke() -> dict[str, Any]:
    """Run the full E2E pipeline and return step results with timings."""
    steps: list[dict[str, Any]] = []
    client = httpx.Client(timeout=30)
    overall_t0 = time.monotonic()

    try:
        # --- Step 1: Register tenant ---
        suffix = uuid.uuid4().hex[:8]
        tenant_name = f"e2e-smoke-{suffix}"
        email = f"e2e-smoke-{suffix}@xeter-validate.test"
        password = f"SmokeTest{suffix}!"

        t0 = time.monotonic()
        try:
            reg_resp = client.post(
                f"{PRESENTER_URL}/register",
                json={"tenant_name": tenant_name, "email": email, "password": password},
            )
            reg_ms = (time.monotonic() - t0) * 1000
            reg_resp.raise_for_status()
            reg_data = reg_resp.json()
            api_key = reg_data["api_key"]
            tenant_id = reg_data["tenant_id"]
            steps.append({"name": "Register tenant", "passed": True, "ms": reg_ms})
            print(f"  Register tenant: PASS ({reg_ms:.0f}ms)")
        except Exception as exc:
            reg_ms = (time.monotonic() - t0) * 1000
            steps.append({"name": "Register tenant", "passed": False, "ms": reg_ms, "error": str(exc)})
            print(f"  Register tenant: FAIL ({reg_ms:.0f}ms) — {exc}")
            return {"steps": steps, "total_ms": (time.monotonic() - overall_t0) * 1000}

        # --- Step 2: Login ---
        t0 = time.monotonic()
        try:
            login_resp = client.post(
                f"{PRESENTER_URL}/login",
                json={"email": email, "password": password},
            )
            login_ms = (time.monotonic() - t0) * 1000
            login_resp.raise_for_status()
            token = login_resp.json()["session_token"]
            steps.append({"name": "Login", "passed": True, "ms": login_ms})
            print(f"  Login: PASS ({login_ms:.0f}ms)")
        except Exception as exc:
            login_ms = (time.monotonic() - t0) * 1000
            steps.append({"name": "Login", "passed": False, "ms": login_ms, "error": str(exc)})
            print(f"  Login: FAIL ({login_ms:.0f}ms) — {exc}")
            return {"steps": steps, "total_ms": (time.monotonic() - overall_t0) * 1000}

        # --- Step 3: Ingest span ---
        span_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "span_id": span_id,
            "trace_id": trace_id,
            "agent_name": "e2e-smoke-agent",
            "agent_model": "gpt-4o",
            "tool_name": "search_documents",
            "tool_description": "Search through financial documents by keyword or date range.",
            "tool_arguments": json.dumps({"query": "Q1 earnings", "date_from": "2025-01-01"}),
            "tool_output": "Revenue increased 12% year-over-year in Q1 2025.",
            "prompt": "Summarize the latest quarterly earnings report for the board presentation.",
            "response": "Based on the Q1 2025 report, revenue grew 12% YoY driven by enterprise expansion.",
            "available_tools": json.dumps([
                {"name": "search_documents", "description": "Search through financial documents by keyword or date range."},
                {"name": "extract_tables", "description": "Extract structured tables from a PDF document page."},
            ]),
            "time_begin": now_iso,
            "time_end": now_iso,
            "xeter.schema.version": "1.0",
        }

        t0 = time.monotonic()
        try:
            ingest_resp = client.post(
                f"{ANALYSER_URL}/v1/spans",
                json=payload,
                headers={"X-API-Key": api_key},
            )
            ingest_ms = (time.monotonic() - t0) * 1000
            ingest_resp.raise_for_status()
            steps.append({"name": "Ingest span", "passed": True, "ms": ingest_ms})
            print(f"  Ingest span: PASS ({ingest_ms:.0f}ms)")
        except Exception as exc:
            ingest_ms = (time.monotonic() - t0) * 1000
            steps.append({"name": "Ingest span", "passed": False, "ms": ingest_ms, "error": str(exc)})
            print(f"  Ingest span: FAIL ({ingest_ms:.0f}ms) — {exc}")
            return {"steps": steps, "total_ms": (time.monotonic() - overall_t0) * 1000}

        # --- Step 4: Wait for worker processing ---
        auth_headers = {"Authorization": f"Bearer {token}"}
        t0 = time.monotonic()
        status = "pending"
        scores_count = 0
        deadline = time.monotonic() + PROCESSING_TIMEOUT

        print(f"  Waiting for worker to process span {span_id[:8]}...", end="", flush=True)
        while time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL)
            try:
                list_resp = client.get(f"{PRESENTER_URL}/spans", headers=auth_headers)
                if list_resp.status_code == 200:
                    spans = list_resp.json().get("spans", [])
                    match = next((s for s in spans if s["span_id"] == span_id), None)
                    if match and match.get("status") != "pending":
                        status = match["status"]
                        break
            except Exception:
                pass
            print(".", end="", flush=True)

        process_ms = (time.monotonic() - t0) * 1000
        processed = status != "pending"
        print()

        if processed:
            steps.append({"name": "Worker processing", "passed": True, "ms": process_ms, "status": status})
            print(f"  Worker processing: PASS ({process_ms:.0f}ms) — status={status}")
        else:
            steps.append({"name": "Worker processing", "passed": False, "ms": process_ms, "error": "Timed out waiting for worker"})
            print(f"  Worker processing: FAIL ({process_ms:.0f}ms) — still pending after {PROCESSING_TIMEOUT}s")
            return {"steps": steps, "total_ms": (time.monotonic() - overall_t0) * 1000}

        # --- Step 5: Fetch span detail ---
        t0 = time.monotonic()
        try:
            detail_resp = client.get(f"{PRESENTER_URL}/spans/{span_id}", headers=auth_headers)
            detail_ms = (time.monotonic() - t0) * 1000
            detail_resp.raise_for_status()
            detail = detail_resp.json()

            scores = detail.get("scores", [])
            scores_count = len(scores)
            has_scores = scores_count > 0
            has_prompt = detail.get("prompt") is not None
            has_response = detail.get("response") is not None

            passed = has_scores and has_prompt and has_response
            issues = []
            if not has_scores:
                issues.append("no scores")
            if not has_prompt:
                issues.append("no prompt from S3")
            if not has_response:
                issues.append("no response from S3")

            extra = {
                "scores_count": scores_count,
                "has_prompt": has_prompt,
                "has_response": has_response,
                "status": detail.get("status"),
                "flags_count": len(detail.get("flags", [])),
            }

            if passed:
                steps.append({"name": "Span detail + S3", "passed": True, "ms": detail_ms, **extra})
                print(f"  Span detail + S3: PASS ({detail_ms:.0f}ms) — {scores_count} scores, prompt+response OK")
            else:
                steps.append({"name": "Span detail + S3", "passed": False, "ms": detail_ms, "error": ", ".join(issues), **extra})
                print(f"  Span detail + S3: FAIL ({detail_ms:.0f}ms) — {', '.join(issues)}")

        except Exception as exc:
            detail_ms = (time.monotonic() - t0) * 1000
            steps.append({"name": "Span detail + S3", "passed": False, "ms": detail_ms, "error": str(exc)})
            print(f"  Span detail + S3: FAIL ({detail_ms:.0f}ms) — {exc}")

    finally:
        client.close()

    total_ms = (time.monotonic() - overall_t0) * 1000
    return {"steps": steps, "total_ms": total_ms}


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def write_report(result: dict[str, Any], generated_at: str) -> None:
    """Write VALIDATION-REPORT.md to project root."""
    steps = result["steps"]
    total_ms = result["total_ms"]
    all_passed = all(s["passed"] for s in steps)
    overall = "PASS" if all_passed else "FAIL"

    lines = [
        "# Validation Report",
        "",
        f"Generated: {generated_at}",
        f"Overall result: **{overall}**",
        "",
        "## E2E Smoke Test",
        "",
        "| Step | Status | Duration |",
        "|------|--------|----------|",
    ]

    for s in steps:
        status = "PASS" if s["passed"] else "FAIL"
        ms = s["ms"]
        detail = f"{ms:.0f}ms"
        if not s["passed"] and "error" in s:
            detail += f" ({s['error']})"
        lines.append(f"| {s['name']} | {status} | {detail} |")

    lines.append("")
    lines.append(f"**Total E2E: {total_ms:.0f}ms**")
    lines.append("")

    # Verification summary from detail step
    detail_step = next((s for s in steps if s["name"] == "Span detail + S3"), None)
    lines.append("## Verification")
    lines.append("")
    if detail_step and detail_step["passed"]:
        lines.append(f"- Span appears in list: YES")
        lines.append(f"- Scores present: YES ({detail_step.get('scores_count', '?')} metrics)")
        lines.append(f"- S3 payloads returned: YES (prompt, response)")
        lines.append(f"- Status: {detail_step.get('status', '?')}")
        lines.append(f"- Flags: {detail_step.get('flags_count', 0)}")
    elif detail_step:
        lines.append(f"- Span detail check: FAILED — {detail_step.get('error', 'unknown')}")
    else:
        lines.append("- Span detail check: DID NOT RUN (earlier step failed)")
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print("=" * 60)
    print("XETER E2E SMOKE TEST")
    print(f"Started: {generated_at}")
    print("=" * 60)
    print()

    result = run_e2e_smoke()
    write_report(result, generated_at)

    steps = result["steps"]
    all_passed = all(s["passed"] for s in steps)

    print()
    print("=" * 60)
    overall = "PASS" if all_passed else "FAIL"
    print(f"Overall: {overall} — total {result['total_ms']:.0f}ms")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()

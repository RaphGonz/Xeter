"""Unified validation runner for Xeter.

Orchestrates all four validation steps in continue-all mode:
  1. Calibration          — threshold sweep + P/R curve (requires live embedder)
  2. Load Test            — 500 rps / 60 s (requires full Docker stack)
  3. Cross-Tenant Isolation — pytest tests with VALIDATION_STACK=1
  4. E2E Latency          — extracted from step 2 (or standalone probe)

Every step runs regardless of prior failures.
Produces VALIDATION-REPORT.md at project root.

Usage:
    python xeter/scripts/validate.py
    python xeter/scripts/validate.py --skip-calibration
    python xeter/scripts/validate.py --skip-load-test
    python xeter/scripts/validate.py --skip-calibration --skip-load-test

Exit code: 0 if all steps pass, 1 if any step fails.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
REPORT_PATH = PROJECT_ROOT / "VALIDATION-REPORT.md"
ISOLATION_TEST_PATH = (
    PROJECT_ROOT / "xeter" / "tests" / "validation" / "test_isolation.py"
)

# ---------------------------------------------------------------------------
# Step result container
# ---------------------------------------------------------------------------


class StepResult:
    def __init__(
        self,
        name: str,
        passed: Optional[bool],
        detail: str,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.passed = passed  # None means "skipped"
        self.detail = detail
        self.extra = extra or {}

    @property
    def status_str(self) -> str:
        if self.passed is None:
            return "SKIP"
        return "PASS" if self.passed else "FAIL"


# ---------------------------------------------------------------------------
# Step 1: Calibration
# ---------------------------------------------------------------------------


def run_calibration() -> StepResult:
    """Import and run calibrate.main(); capture threshold, precision, recall."""
    print("\n" + "=" * 60)
    print("STEP 1: CALIBRATION")
    print("=" * 60)

    try:
        # Import lazily to avoid triggering embedder at import time
        sys.path.insert(0, str(PROJECT_ROOT))
        from xeter.scripts.calibrate import (  # type: ignore
            build_thresholds,
            compute_pr_curve,
            load_fixture,
            patch_docker_compose,
            plot_pr_curve,
            select_threshold,
        )
        import httpx
        import numpy as np
        from xeter.services.worker.base import EmbedderClient  # type: ignore

        embedder_url = "http://localhost:8002"
        print(f"Connecting to embedder at {embedder_url} ...")
        try:
            resp = httpx.get(f"{embedder_url}/health", timeout=5.0)
            resp.raise_for_status()
            print("Embedder reachable.")
        except Exception as exc:
            return StepResult(
                name="Calibration",
                passed=False,
                detail=f"Embedder not reachable: {exc}",
            )

        embedder = EmbedderClient(base_url=embedder_url)
        spans = load_fixture()

        threshold_bases = list(np.arange(0.10, 0.95, 0.02))
        pr_results = compute_pr_curve(spans, embedder, threshold_bases)

        selected = select_threshold(pr_results)
        calibrated = build_thresholds(selected["base"])

        precision = selected["precision"]
        recall = selected["recall"]
        base = selected["base"]
        met_target = selected.get("met_target", False)

        plot_pr_curve(pr_results, selected)
        patch_docker_compose(calibrated)

        passed = precision >= 0.80
        detail = (
            f"base={base:.4f}, precision={precision:.4f}, recall={recall:.4f}"
        )
        if not met_target:
            detail += " [WARNING: 80% precision target not met]"

        print(f"\nCalibration result: {'PASS' if passed else 'FAIL'} — {detail}")

        return StepResult(
            name="Calibration",
            passed=passed,
            detail=detail,
            extra={
                "threshold": base,
                "precision": precision,
                "recall": recall,
                "calibrated_thresholds": calibrated,
                "met_target": met_target,
            },
        )

    except Exception as exc:
        print(f"ERROR in calibration step: {exc}")
        return StepResult(
            name="Calibration",
            passed=False,
            detail=f"Exception: {exc}",
        )


# ---------------------------------------------------------------------------
# Step 2: Load Test
# ---------------------------------------------------------------------------


def run_load_test() -> StepResult:
    """Import and run load_test.main(); capture latency stats."""
    print("\n" + "=" * 60)
    print("STEP 2: LOAD TEST (500 rps / 60 s)")
    print("=" * 60)

    try:
        from xeter.scripts.load_test import main as load_test_main  # type: ignore

        results = load_test_main(rps=500, duration=60)

        load = results["load"]
        parts = results["clickhouse_parts"]
        e2e = results["e2e_latency"]

        total_sent = load["total_sent"]
        success_count = load["success_count"]
        error_count = load["error_count"]
        p50_ms = load["p50_ms"]
        p95_ms = load["p95_ms"]
        p99_ms = load["p99_ms"]
        active_parts = parts["active_parts"]
        e2e_elapsed_ms = e2e["elapsed_ms"]
        e2e_passed = e2e["e2e_assert_passed"]

        passed = (
            error_count == 0
            and p95_ms < 200
            and active_parts < 300
        )

        detail_parts = [
            f"sent={total_sent}",
            f"ok={success_count}",
            f"err={error_count}",
            f"p50={p50_ms}ms",
            f"p95={p95_ms}ms",
            f"p99={p99_ms}ms",
            f"parts={active_parts}",
        ]
        detail = ", ".join(detail_parts)
        if not passed:
            reasons = []
            if error_count > 0:
                reasons.append(f"{error_count} errors")
            if p95_ms >= 200:
                reasons.append(f"p95={p95_ms}ms >= 200ms")
            if active_parts >= 300:
                reasons.append(f"parts={active_parts} >= 300")
            detail += f" [FAIL: {'; '.join(reasons)}]"

        print(f"\nLoad test result: {'PASS' if passed else 'FAIL'} — {detail}")

        return StepResult(
            name="Load Test",
            passed=passed,
            detail=detail,
            extra={
                "total_sent": total_sent,
                "success_count": success_count,
                "error_count": error_count,
                "p50_ms": p50_ms,
                "p95_ms": p95_ms,
                "p99_ms": p99_ms,
                "active_parts": active_parts,
                "e2e_elapsed_ms": e2e_elapsed_ms,
                "e2e_passed": e2e_passed,
            },
        )

    except Exception as exc:
        print(f"ERROR in load test step: {exc}")
        return StepResult(
            name="Load Test",
            passed=False,
            detail=f"Exception: {exc}",
        )


# ---------------------------------------------------------------------------
# Step 3: Cross-Tenant Isolation
# ---------------------------------------------------------------------------


def run_isolation_tests() -> StepResult:
    """Run pytest validation/test_isolation.py with VALIDATION_STACK=1."""
    print("\n" + "=" * 60)
    print("STEP 3: CROSS-TENANT ISOLATION")
    print("=" * 60)

    env = os.environ.copy()
    env["VALIDATION_STACK"] = "1"

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(ISOLATION_TEST_PATH),
        "-v",
        "--tb=short",
    ]

    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {PROJECT_ROOT}")

    try:
        proc = subprocess.run(
            cmd,
            env=env,
            cwd=str(PROJECT_ROOT),
            capture_output=False,
            timeout=300,
        )
        passed = proc.returncode == 0
        detail = f"pytest exit code {proc.returncode}"
        if passed:
            detail += " (all tests green)"
        else:
            detail += " (one or more tests failed)"

        print(f"\nIsolation result: {'PASS' if passed else 'FAIL'} — {detail}")

        return StepResult(
            name="Cross-Tenant Isolation",
            passed=passed,
            detail=detail,
            extra={"pytest_exit_code": proc.returncode},
        )

    except subprocess.TimeoutExpired:
        return StepResult(
            name="Cross-Tenant Isolation",
            passed=False,
            detail="Exception: pytest timed out after 300s",
        )
    except Exception as exc:
        print(f"ERROR in isolation step: {exc}")
        return StepResult(
            name="Cross-Tenant Isolation",
            passed=False,
            detail=f"Exception: {exc}",
        )


# ---------------------------------------------------------------------------
# Step 4: E2E Latency
# ---------------------------------------------------------------------------


def run_e2e_latency(
    load_test_result: Optional[StepResult],
) -> StepResult:
    """Extract e2e latency from load test result, or run standalone probe."""
    print("\n" + "=" * 60)
    print("STEP 4: E2E LATENCY")
    print("=" * 60)

    # Try to reuse the e2e result already captured in the load test
    if (
        load_test_result is not None
        and load_test_result.passed is not None
        and "e2e_elapsed_ms" in load_test_result.extra
    ):
        e2e_elapsed_ms = load_test_result.extra["e2e_elapsed_ms"]
        e2e_passed = load_test_result.extra["e2e_passed"]
        detail = f"elapsed={e2e_elapsed_ms:.1f}ms (from load test probe)"
        if not e2e_passed:
            detail += " [FAIL: >= 5000ms]"
        print(f"\nE2E latency result: {'PASS' if e2e_passed else 'FAIL'} — {detail}")
        return StepResult(
            name="E2E Latency",
            passed=e2e_passed,
            detail=detail,
            extra={"elapsed_ms": e2e_elapsed_ms, "source": "load_test"},
        )

    # Load test was skipped or failed — run a standalone probe
    print("Load test unavailable — running standalone e2e probe...")

    try:
        import time
        import uuid

        import httpx
        import psycopg2  # type: ignore

        analyser_url = os.environ.get("ANALYSER_URL", "http://localhost:4318")
        presenter_url = os.environ.get("PRESENTER_URL", "http://localhost:8000")
        pg_host = os.environ.get("POSTGRES_HOST", "localhost")
        pg_port = int(os.environ.get("POSTGRES_PORT", "5432"))

        # Register a transient tenant for the probe
        tenant_name = f"e2e-probe-{uuid.uuid4().hex[:8]}"
        reg_resp = httpx.post(
            f"{presenter_url}/register",
            json={"tenant_name": tenant_name, "email": f"{tenant_name}@probe.test", "password": "probepass123"},
            timeout=10,
        )
        reg_resp.raise_for_status()
        api_key = reg_resp.json()["api_key"]

        span_id = str(uuid.uuid4())
        payload = {
            "span_id": span_id,
            "trace_id": str(uuid.uuid4()),
            "agent_name": "e2e-probe",
            "agent_model": "gpt-4o",
            "tool_name": "web_search",
            "tool_description": "Search the web for information",
            "tool_arguments": '{"query": "test query"}',
            "tool_output": "Probe output for e2e latency test.",
            "prompt": "Search for something",
            "response": "I searched for something.",
            "raw_response": None,
            "available_tools": None,
            "time_begin": datetime.now(timezone.utc).isoformat(),
            "time_end": datetime.now(timezone.utc).isoformat(),
        }

        t0 = time.monotonic()
        send_resp = httpx.post(
            f"{analyser_url}/v1/spans",
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=10,
        )
        send_resp.raise_for_status()

        pg_dsn = f"host={pg_host} port={pg_port} dbname=xeter user=xeter password=xeter_dev_password"
        conn = psycopg2.connect(pg_dsn)
        conn.autocommit = True
        found = False
        deadline = t0 + 10.0
        try:
            with conn.cursor() as cur:
                while time.monotonic() < deadline:
                    cur.execute(
                        "SELECT 1 FROM span_scores WHERE span_id = %s LIMIT 1",
                        (span_id,),
                    )
                    if cur.fetchone():
                        found = True
                        break
                    time.sleep(0.5)
        finally:
            conn.close()

        elapsed_ms = (time.monotonic() - t0) * 1000
        e2e_passed = elapsed_ms < 5000
        detail = f"elapsed={elapsed_ms:.1f}ms (standalone probe, found={found})"
        if not e2e_passed:
            detail += " [FAIL: >= 5000ms]"

        print(f"\nE2E latency result: {'PASS' if e2e_passed else 'FAIL'} — {detail}")
        return StepResult(
            name="E2E Latency",
            passed=e2e_passed,
            detail=detail,
            extra={"elapsed_ms": elapsed_ms, "found": found, "source": "standalone"},
        )

    except Exception as exc:
        print(f"ERROR in e2e latency step: {exc}")
        return StepResult(
            name="E2E Latency",
            passed=False,
            detail=f"Exception: {exc}",
        )


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def write_report(
    results: list[StepResult],
    generated_at: str,
) -> None:
    """Write VALIDATION-REPORT.md to project root."""
    overall_passed = all(
        r.passed is True or r.passed is None for r in results
    ) and any(r.passed is True for r in results)
    # Actually: overall PASS only if all non-skipped steps passed
    non_skipped = [r for r in results if r.passed is not None]
    overall_passed = all(r.passed for r in non_skipped) if non_skipped else False

    overall_str = "PASS" if overall_passed else "FAIL"

    lines: list[str] = []

    lines.append("# Validation Report")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append(f"Overall result: **{overall_str}**")
    lines.append("")

    # Results table
    lines.append("## Results Summary")
    lines.append("")
    lines.append("| Step | Status | Detail |")
    lines.append("|------|--------|--------|")
    for r in results:
        lines.append(f"| {r.name} | {r.status_str} | {r.detail} |")
    lines.append("")

    # Calibrated thresholds table
    calibration = next((r for r in results if r.name == "Calibration"), None)
    if calibration and "calibrated_thresholds" in calibration.extra:
        thresholds = calibration.extra["calibrated_thresholds"]
        # Old values are derived from defaults (same ratios with base=0.5)
        old_thresholds = {
            "wrong_tool": 0.5,
            "wrong_tool_args": 0.4,
            "no_tool": 0.6,
            "excessive_tool": 0.3,
            "parsing_error": 0.5,
            "response_anomaly": 0.4,
        }
        lines.append("## Calibrated Thresholds")
        lines.append("")
        lines.append("| Key | Old Value | New Value |")
        lines.append("|-----|-----------|-----------|")
        for key, new_val in thresholds.items():
            old_val = old_thresholds.get(key, "N/A")
            lines.append(f"| {key} | {old_val} | {new_val} |")
        lines.append("")

    # Load test detail
    load_step = next((r for r in results if r.name == "Load Test"), None)
    if load_step and load_step.extra:
        ex = load_step.extra
        lines.append("## Load Test Detail")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total requests sent | {ex.get('total_sent', 'N/A')} |")
        lines.append(f"| Successful | {ex.get('success_count', 'N/A')} |")
        lines.append(f"| Errors | {ex.get('error_count', 'N/A')} |")
        lines.append(f"| p50 latency | {ex.get('p50_ms', 'N/A')} ms |")
        lines.append(f"| p95 latency | {ex.get('p95_ms', 'N/A')} ms |")
        lines.append(f"| p99 latency | {ex.get('p99_ms', 'N/A')} ms |")
        lines.append(f"| ClickHouse active parts | {ex.get('active_parts', 'N/A')} |")
        lines.append(f"| E2E latency (load probe) | {ex.get('e2e_elapsed_ms', 'N/A')} ms |")
        lines.append("")

    # Notes
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- `wrong_tool_args` flags are excluded from precision/recall computation "
        "by design (low_confidence=True — terse JSON argument text produces "
        "unreliable cosine similarity; see Phase 6 Plan 1 decision log)."
    )
    if calibration and not calibration.extra.get("met_target", True):
        lines.append(
            "- WARNING: Calibration did not achieve the 80% precision target. "
            "Review fixture quality or adjust precision threshold."
        )
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nValidation report written to {REPORT_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Xeter unified validation runner — orchestrates all four validation steps."
    )
    parser.add_argument(
        "--skip-calibration",
        action="store_true",
        help="Skip the calibration step (Step 1)",
    )
    parser.add_argument(
        "--skip-load-test",
        action="store_true",
        help="Skip the load test step (Step 2) — also skips e2e latency if standalone probe also fails",
    )
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print("=" * 60)
    print("XETER VALIDATION RUNNER")
    print(f"Started: {generated_at}")
    print("=" * 60)

    results: list[StepResult] = []

    # Step 1: Calibration
    if args.skip_calibration:
        print("\nSKIPPING Step 1: Calibration (--skip-calibration)")
        results.append(StepResult(name="Calibration", passed=None, detail="Skipped via --skip-calibration"))
    else:
        results.append(run_calibration())

    # Step 2: Load Test
    if args.skip_load_test:
        print("\nSKIPPING Step 2: Load Test (--skip-load-test)")
        results.append(StepResult(name="Load Test", passed=None, detail="Skipped via --skip-load-test"))
        load_result = None
    else:
        load_result = run_load_test()
        results.append(load_result)

    # Step 3: Cross-Tenant Isolation (always runs)
    results.append(run_isolation_tests())

    # Step 4: E2E Latency (reuses load test result or standalone probe)
    results.append(run_e2e_latency(load_result if not args.skip_load_test else None))

    # Write report
    write_report(results, generated_at)

    # Final summary
    print("\n" + "=" * 60)
    print("VALIDATION COMPLETE")
    print("=" * 60)
    for r in results:
        print(f"  {r.name:<30s}: {r.status_str}")

    non_skipped = [r for r in results if r.passed is not None]
    all_passed = all(r.passed for r in non_skipped) if non_skipped else False
    overall = "PASS" if all_passed else "FAIL"
    print(f"\n  Overall: {overall}")
    print("=" * 60)
    print(f"\nReport: {REPORT_PATH}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()

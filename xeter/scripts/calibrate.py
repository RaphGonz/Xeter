"""Calibration harness for ToolCallAnalyzer threshold sweep.

Reads fixtures/labelled_spans.jsonl, sweeps thresholds from 0.10 to 0.94
(step 0.02), computes precision/recall at each point, and selects the
threshold that maximises recall while achieving >= 80% precision.

Usage (requires live embedder at http://localhost:8002):
    python xeter/scripts/calibrate.py

Outputs:
    - fixtures/precision_recall_curve.png  — P/R curve with selected point
    - stdout summary with calibrated threshold values
    - Patches deploy/docker-compose.yml WORKER_THRESHOLD_* env vars in-place

Precision target: 80% minimum (optimise for precision to minimise false alarms).

NOTE: wrong_tool_args flags are EXCLUDED from P/R computation.
These flags carry low_confidence=True by design (FLAG-12 / Pitfall 5 in
research) — their argument embeddings are terse JSON that produces
unreliable similarity scores. Including them would inflate FP counts
artificially and skew calibration results.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

from matplotlib import use as _matplotlib_use  # precision/recall curve; pyplot imported in plot_pr_curve
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURE_PATH = PROJECT_ROOT / "fixtures" / "labelled_spans.jsonl"
CURVE_PATH = PROJECT_ROOT / "fixtures" / "precision_recall_curve.png"
DOCKER_COMPOSE_PATH = PROJECT_ROOT / "deploy" / "docker-compose.yml"

EMBEDDER_URL = "http://localhost:8002"

# ---------------------------------------------------------------------------
# Threshold ratios (relative to sweep base value)
# Derived from existing defaults:
#   wrong_tool=0.5, wrong_tool_args=0.4, no_tool=0.6,
#   excessive_tool=0.3, parsing_error=0.5, response_anomaly=0.4
# Ratios relative to base=0.5 (wrong_tool):
#   wrong_tool=1.0x, wrong_tool_args=0.8x, no_tool=1.2x,
#   excessive_tool=0.6x, parsing_error=1.0x, response_anomaly=0.8x
# ---------------------------------------------------------------------------

THRESHOLD_RATIOS = {
    "wrong_tool": 1.0,
    "wrong_tool_args": 0.8,
    "no_tool": 1.2,
    "excessive_tool": 0.6,
    "parsing_error": 1.0,
    "response_anomaly": 0.8,
}

PRECISION_TARGET = 0.80


def build_thresholds(base: float) -> dict[str, float]:
    """Scale all threshold keys from a single base value using THRESHOLD_RATIOS."""
    return {key: round(base * ratio, 4) for key, ratio in THRESHOLD_RATIOS.items()}


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

def load_fixture() -> list[dict]:
    if not FIXTURE_PATH.exists():
        print(f"ERROR: Fixture not found at {FIXTURE_PATH}")
        print("Run: python xeter/scripts/generate_labelled_fixture.py")
        sys.exit(1)
    spans = []
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                spans.append(json.loads(line))
    print(f"Loaded {len(spans)} spans from {FIXTURE_PATH}")
    return spans


# ---------------------------------------------------------------------------
# SpanData builder
# ---------------------------------------------------------------------------

def build_span_data(row: dict):
    """Convert a fixture row dict into a SpanData instance."""
    # Import here to avoid module-level side effects during tests
    from xeter.services.worker.base import SpanData

    return SpanData(
        span_id=row.get("span_id", "calibration-span"),
        tenant_id=row.get("tenant_id", "calibration-tenant"),
        trace_id=row.get("trace_id", "calibration-trace"),
        agent_name=row.get("agent_name", "calibration-agent"),
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


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

EXCLUDED_FLAG_TYPES = frozenset({"wrong_tool_args"})


def evaluate_threshold(
    base: float,
    spans: list[dict],
    embedder,
) -> tuple[float, float]:
    """Run analyzer at given base threshold; return (precision, recall).

    Excludes wrong_tool_args flags from computation (low_confidence by design).

    Returns:
        (precision, recall) — both in [0, 1]; (0, 0) if no positives predicted.
    """
    from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer

    thresholds = build_thresholds(base)
    analyzer = ToolCallAnalyzer(embedder, thresholds)

    tp = fp = fn = 0

    for row in spans:
        actual_flagged = row["label"] == "flagged"
        # parsing_error spans have label-driven anomaly; all others use embedding checks
        span = build_span_data(row)
        flags = analyzer.analyze(span)
        _ = analyzer.flush_scores()  # SC5: flush scores (ensures every score is present)

        # Filter out excluded flag types before deciding predicted label
        significant_flags = [f for f in flags if f.flag_type not in EXCLUDED_FLAG_TYPES]
        predicted_flagged = len(significant_flags) > 0

        if predicted_flagged and actual_flagged:
            tp += 1
        elif predicted_flagged and not actual_flagged:
            fp += 1
        elif not predicted_flagged and actual_flagged:
            fn += 1
        # TN: not predicted, not actual — no contribution to P/R

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return precision, recall


# ---------------------------------------------------------------------------
# Precision/recall curve
# ---------------------------------------------------------------------------

def compute_pr_curve(
    spans: list[dict],
    embedder,
    thresholds: list[float],
) -> list[dict]:
    """Compute P/R at each threshold value.

    Returns list of dicts: {base, precision, recall}
    """
    results = []
    total = len(thresholds)
    for i, base in enumerate(thresholds, 1):
        precision, recall = evaluate_threshold(base, spans, embedder)
        results.append({"base": base, "precision": precision, "recall": recall})
        print(
            f"  [{i:3d}/{total}] base={base:.2f}  precision={precision:.3f}  recall={recall:.3f}",
            flush=True,
        )
    return results


# ---------------------------------------------------------------------------
# Threshold selection
# ---------------------------------------------------------------------------

def select_threshold(pr_results: list[dict]) -> dict:
    """Select threshold with precision >= PRECISION_TARGET and max recall.

    Falls back to highest-precision point if no threshold achieves target.
    """
    qualifying = [r for r in pr_results if r["precision"] >= PRECISION_TARGET]
    if qualifying:
        best = max(qualifying, key=lambda r: r["recall"])
        best["met_target"] = True
    else:
        best = max(pr_results, key=lambda r: r["precision"])
        best["met_target"] = False
    return best


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_pr_curve(pr_results: list[dict], selected: dict) -> None:
    """Save P/R curve PNG to CURVE_PATH."""
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend for headless environments
    import matplotlib.pyplot as plt

    precisions = [r["precision"] for r in pr_results]
    recalls = [r["recall"] for r in pr_results]
    bases = [r["base"] for r in pr_results]

    fig, ax = plt.subplots(figsize=(8, 6))

    # P/R curve coloured by threshold base value
    scatter = ax.scatter(recalls, precisions, c=bases, cmap="viridis", s=40, zorder=3)
    ax.plot(recalls, precisions, color="steelblue", linewidth=1, alpha=0.6, zorder=2)

    # 80% precision target line
    ax.axhline(
        y=PRECISION_TARGET,
        color="red",
        linestyle="--",
        linewidth=1.5,
        label=f"{PRECISION_TARGET:.0%} precision target",
        zorder=4,
    )

    # Selected point
    sel_p = selected["precision"]
    sel_r = selected["recall"]
    sel_b = selected["base"]
    ax.scatter(
        [sel_r], [sel_p],
        color="red", s=120, zorder=5, marker="*",
        label=f"Selected (base={sel_b:.2f}, P={sel_p:.3f}, R={sel_r:.3f})",
    )
    ax.annotate(
        f"  base={sel_b:.2f}\n  P={sel_p:.3f}, R={sel_r:.3f}",
        xy=(sel_r, sel_p),
        fontsize=9,
        color="darkred",
    )

    fig.colorbar(scatter, ax=ax, label="Threshold base value")

    ax.set_xlabel("Recall", fontsize=12)
    ax.set_ylabel("Precision", fontsize=12)
    ax.set_title("Precision/Recall Curve — ToolCallAnalyzer Threshold Sweep", fontsize=13)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    CURVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(CURVE_PATH, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nPrecision/recall curve saved to {CURVE_PATH}")


# ---------------------------------------------------------------------------
# docker-compose.yml patcher
# ---------------------------------------------------------------------------

def patch_docker_compose(calibrated: dict[str, float]) -> None:
    """Regex-patch WORKER_THRESHOLD_* lines in docker-compose.yml."""
    if not DOCKER_COMPOSE_PATH.exists():
        print(f"WARNING: {DOCKER_COMPOSE_PATH} not found — skipping docker-compose patch")
        return

    content = DOCKER_COMPOSE_PATH.read_text(encoding="utf-8")

    # Mapping from threshold key → env var name
    key_to_env = {
        "wrong_tool": "WORKER_THRESHOLD_WRONG_TOOL",
        "wrong_tool_args": "WORKER_THRESHOLD_WRONG_ARGS",
        "no_tool": "WORKER_THRESHOLD_NO_TOOL",
        "excessive_tool": "WORKER_THRESHOLD_EXCESSIVE_TOOL",
        "parsing_error": "WORKER_THRESHOLD_PARSING_ERROR",
        "response_anomaly": "WORKER_THRESHOLD_RESPONSE_ANOMALY",
    }

    patched = content
    for key, env_var in key_to_env.items():
        value = calibrated[key]
        # Pattern: WORKER_THRESHOLD_XYZ: "any_value"
        pattern = rf'({re.escape(env_var)}:\s*)"[^"]*"'
        replacement = rf'\g<1>"{value}"'
        new_content, n_subs = re.subn(pattern, replacement, patched)
        if n_subs == 0:
            print(f"  WARNING: {env_var} not found in {DOCKER_COMPOSE_PATH}")
        else:
            print(f"  Patched {env_var}: {value}")
        patched = new_content

    DOCKER_COMPOSE_PATH.write_text(patched, encoding="utf-8")
    print(f"docker-compose.yml updated: {DOCKER_COMPOSE_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Check embedder reachability ---
    import httpx
    from xeter.services.worker.base import EmbedderClient

    print(f"Connecting to embedder at {EMBEDDER_URL} ...")
    try:
        resp = httpx.get(f"{EMBEDDER_URL}/health", timeout=5.0)
        resp.raise_for_status()
        print("Embedder reachable.")
    except httpx.ConnectError:
        print(
            f"ERROR: Embedder not reachable at {EMBEDDER_URL} -- "
            "run 'docker compose up embedder' first"
        )
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Embedder health check failed: {exc}")
        sys.exit(1)

    embedder = EmbedderClient(base_url=EMBEDDER_URL)

    # --- Load fixture ---
    spans = load_fixture()
    n_flagged = sum(1 for s in spans if s["label"] == "flagged")
    n_clean = len(spans) - n_flagged
    print(f"  Flagged: {n_flagged}, Clean: {n_clean}")
    print()

    # --- NOTE on exclusions ---
    print(
        "NOTE: wrong_tool_args flags are excluded from P/R computation.\n"
        "      These flags carry low_confidence=True by design (argument embeddings\n"
        "      are terse JSON with unreliable cosine similarity — Pitfall 5 in research).\n"
    )

    # --- Threshold sweep ---
    threshold_bases = list(np.arange(0.10, 0.95, 0.02))
    print(f"Sweeping {len(threshold_bases)} threshold points from 0.10 to 0.94 ...")
    pr_results = compute_pr_curve(spans, embedder, threshold_bases)

    # --- Select best threshold ---
    selected = select_threshold(pr_results)

    if not selected["met_target"]:
        print(
            f"\nWARNING: No threshold achieves {PRECISION_TARGET:.0%} precision target.\n"
            f"Best available precision: {selected['precision']:.3f} at base={selected['base']:.2f}.\n"
            "Consider improving fixture quality or adjusting the precision target."
        )
    else:
        print(f"\nSelected threshold: base={selected['base']:.2f} (precision >= {PRECISION_TARGET:.0%} with max recall)")

    calibrated = build_thresholds(selected["base"])

    # --- Print summary ---
    print("\n" + "=" * 60)
    print("CALIBRATION RESULT")
    print("=" * 60)
    print(f"  Selected base threshold : {selected['base']:.4f}")
    print(f"  Precision               : {selected['precision']:.4f}")
    print(f"  Recall                  : {selected['recall']:.4f}")
    print(f"  Met {PRECISION_TARGET:.0%} target          : {selected['met_target']}")
    print()
    print("  Calibrated threshold values:")
    for key, value in calibrated.items():
        print(f"    {key:<30s}: {value:.4f}")
    print("=" * 60)

    # --- Plot ---
    plot_pr_curve(pr_results, selected)

    # --- Patch docker-compose ---
    print("\nPatching deploy/docker-compose.yml ...")
    patch_docker_compose(calibrated)

    print("\nCalibration complete.")


if __name__ == "__main__":
    main()

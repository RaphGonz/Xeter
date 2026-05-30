"""Calibration harness for ToolCallAnalyzer — per-flag-type hill climbing.

For each flag type, starts at threshold=0.1 and raises by STEP until precision
stops improving. Typically converges in ~6 steps instead of sweeping all 43 points.

Usage (requires live embedder at http://localhost:8002):
    python xeter/scripts/calibrate.py
    python xeter/scripts/calibrate.py --flag-type wrong_tool_args

Outputs:
    - fixtures/precision_recall_curve.png  — per-flag-type P/R plot
    - stdout summary with calibrated threshold values
    - Patches deploy/docker-compose.yml WORKER_THRESHOLD_* env vars in-place
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer
from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer
from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer
from xeter.services.worker.trace_analyzer import TraceAnalyzer
from xeter.services.worker.base import BaseTraceAnalyzer

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

# Ensure project root is on sys.path so `xeter` package is importable
# when running as `python xeter/scripts/calibrate.py`
_PROJECT_ROOT_EARLY = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT_EARLY) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_EARLY))

PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURE_PATH = PROJECT_ROOT / "fixtures" / "labelled_spans.jsonl"
CURVE_PATH = PROJECT_ROOT / "fixtures" / "precision_recall_curve.png"
THRESHOLDS_PATH = PROJECT_ROOT / "fixtures" / "calibrated_thresholds.json"
DOCKER_COMPOSE_PATH = PROJECT_ROOT / "deploy" / "docker-compose.yml"

EMBEDDER_URL = "http://localhost:8002"

# Flag types to calibrate independently via hill climbing
FLAG_TYPES = [
    "tool_not_available",
    "wrong_tool_choice",
    "unnecessary_tool_call",
    "wrong_tool_args",
    "no_tool",
    "parsing_error",
    "response_anomaly",
    # Phase 24 — OutputSchemaAnalyzer
    "output_schema_violation",
    "required_fields_missing",
    "output_truncated",
    "type_coercion_error",
    "context_overflow",
    # Phase 25 — SemanticSpanAnalyzer
    "missing_details",
    # Phase 25 — TraceAnalyzer
    "stale_context",
    "step_repetition",
    "termination_loop",
    "context_propagation_failure",
    "history_loss",
    # Phase 26 — TraceAnalyzer (best-effort proxy checks)
    "wrong_agent_handoff",
    "information_withholding",
    "conversation_reset",
    "clarification_skipped",
    "no_verification",
    "incomplete_verification",
]

# Maps threshold key → actual emitted flag_type (and fixture anomaly_type).
# Needed when threshold key differs from the emitted flag type (e.g. after a
# threshold-key rename that preserved the public flag_type string).
FLAG_TYPE_ALIAS: dict[str, str] = {}

# Maps each flag_type to the analyzer class responsible for evaluating it.
# Phases 24-27 will add new entries when new analyzer classes are introduced.
# evaluate_flag_type() uses this registry for instantiation — no hardcoded class.
FLAG_TYPE_TO_ANALYZER_CLASS: dict[str, type] = {
    "tool_not_available":   ToolCallAnalyzer,
    "wrong_tool_choice":    ToolCallAnalyzer,
    "unnecessary_tool_call": ToolCallAnalyzer,
    "wrong_tool_args":      ToolCallAnalyzer,
    "no_tool":              ToolCallAnalyzer,
    "parsing_error":        ToolCallAnalyzer,
    "response_anomaly":     ToolCallAnalyzer,
    # Phase 24 — OutputSchemaAnalyzer routing
    "output_schema_violation": OutputSchemaAnalyzer,
    "required_fields_missing": OutputSchemaAnalyzer,
    "output_truncated":        OutputSchemaAnalyzer,
    "type_coercion_error":     OutputSchemaAnalyzer,
    "context_overflow":        OutputSchemaAnalyzer,
    # Phase 25 — SemanticSpanAnalyzer
    "missing_details":               SemanticSpanAnalyzer,
    # Phase 25 — TraceAnalyzer
    "stale_context":                 TraceAnalyzer,
    "step_repetition":               TraceAnalyzer,
    "termination_loop":              TraceAnalyzer,
    "context_propagation_failure":   TraceAnalyzer,
    "history_loss":                  TraceAnalyzer,
    # Phase 26 — TraceAnalyzer (best-effort proxy checks)
    "wrong_agent_handoff":           TraceAnalyzer,
    "information_withholding":       TraceAnalyzer,
    "conversation_reset":            TraceAnalyzer,
    "clarification_skipped":         TraceAnalyzer,
    "no_verification":               TraceAnalyzer,
    "incomplete_verification":       TraceAnalyzer,
}

# Binary detectors — no threshold sweep; detected by rank/logic, not cosine threshold.
# P/R is still measured via a single evaluation pass.
BINARY_FLAG_TYPES: set[str] = {
    "tool_not_available",
    "wrong_tool_choice",
    "parsing_error",
    "output_schema_violation",
    "required_fields_missing",
    "output_truncated",
    "type_coercion_error",
    "context_overflow",   # token-scale threshold incompatible with cosine hill_climb range
    # Phase 26 binary classifications (Plan 27-02):
    "wrong_agent_handoff",      # topological graph membership — produces only 0.0 or 1.0
    "clarification_skipped",    # syntactic rule (disjunctive marker + no ?) — binary
    "no_verification",          # keyword scan — fires or not; no continuous score
}

# Default starting thresholds (used as baseline when calibrating other flags)
DEFAULT_THRESHOLDS: dict[str, float] = {
    "tool_coherence_threshold": 0.15,
    "unnecessary_tool_call": 0.15,
    "wrong_tool_args": 0.4,
    "no_tool": 0.6,
    "response_anomaly": 0.4,
    "context_overflow": 8000,
    # Phase 25
    "missing_details": 0.6,
    "stale_context": 85.0,
    "context_propagation_failure": 0.5,
    "history_loss": 0.4,
    "step_repetition": 85.0,
    "termination_loop_n": 3,
    # Phase 26
    "conversation_reset": 0.25,
    "information_withholding": 0.5,
    "wrong_agent_handoff": 1.0,
    "clarification_skipped": 1.0,
    "no_verification": 1.0,
    "incomplete_verification": 0.7,
}

HILL_CLIMB_START = 0.10
HILL_CLIMB_STEP = 0.05
HILL_CLIMB_MAX = 0.95

# Integer grid for termination_loop — hill_climb's [0.10, 0.95] range produces int(x)=0 always
TERMINATION_LOOP_N_VALUES = [2, 3, 4, 5]

# Flag types that require multi-span grouped trace evaluation.
# These checks rely on comparing spans within a trace, so the evaluator must
# feed the full group (all rows sharing a trace_id) to analyzer.analyze().
# Note: "clarification_skipped" is NOT here — it is a syntactic single-span check.
# Note: "missing_details" is NOT here — it is a SemanticSpanAnalyzer (span-level) check.
TRACE_LEVEL_TYPES: frozenset[str] = frozenset({
    "stale_context",
    "step_repetition",
    "termination_loop",
    "context_propagation_failure",
    "history_loss",
    "wrong_agent_handoff",
    "information_withholding",
    "conversation_reset",
    "no_verification",
    "incomplete_verification",
})

# Hardcoded routing graph for calibration runs of wrong_agent_handoff.
# Matches the routing topology embedded in the fixture rows produced by
# make_wrong_agent_handoff_spans(): orchestrator → search_agent / data_agent,
# billing_agent → payment_agent, search_agent → data_agent.
# This is a calibration-only constant — not a production secret (T-27-01-02).
CALIBRATION_ROUTING_GRAPH: dict[str, list[str]] = {
    "orchestrator": ["search_agent", "data_agent"],
    "billing_agent": ["payment_agent"],
    "search_agent": ["data_agent"],
}


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
        expected_output_schema=row.get("expected_output_schema"),
        parent_span_id=row.get("parent_span_id"),
    )


# ---------------------------------------------------------------------------
# Trace grouping helper
# ---------------------------------------------------------------------------

def group_spans_by_trace(spans: list[dict]) -> list[list[dict]]:
    """Group fixture rows by trace_id, preserving insertion order within each group.

    Returns a list of groups (each group is a list of rows sharing a trace_id).
    Single-span rows with unique trace_ids form single-element groups.
    All rows are preserved — no filtering occurs.

    Within each group rows are in insertion (list) order, which corresponds to
    the order they were appended in generate_new_type_spans() (natural ordering
    = ascending span_id when the builder sets span_id suffixes 0, 1, 2…).
    """
    seen: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in spans:
        tid = row.get("trace_id") or ""
        if tid not in seen:
            seen[tid] = []
            order.append(tid)
        seen[tid].append(row)
    return [seen[tid] for tid in order]


# ---------------------------------------------------------------------------
# Per-flag-type evaluation
# ---------------------------------------------------------------------------

def evaluate_flag_type(
    flag_type: str,
    threshold: float,
    spans: list[dict],
    embedder,
    current_thresholds: dict[str, float],
    verbose: bool = False,
) -> tuple[float, float]:
    """Precision and recall for one flag_type at the given threshold.

    Varies only flag_type's threshold; all others stay at current_thresholds.
    Counts only spans whose anomaly_type matches flag_type as actual positives.

    FLAG_TYPE_ALIAS is applied so that threshold keys that differ from the
    emitted flag_type (via FLAG_TYPE_ALIAS if the key differs) are resolved
    correctly when matching fixture labels and analyzer outputs.

    If verbose=True, prints each false positive and false negative with span
    details to help diagnose algorithm failures.
    """
    # Resolve the actual emitted flag_type string used in fixture + analyzer
    emitted_flag_type = FLAG_TYPE_ALIAS.get(flag_type, flag_type)

    thresholds = dict(current_thresholds)
    thresholds[flag_type] = threshold
    analyzer_cls = FLAG_TYPE_TO_ANALYZER_CLASS[flag_type]

    # wrong_agent_handoff requires CALIBRATION_ROUTING_GRAPH injected at instantiation
    if flag_type == "wrong_agent_handoff":
        analyzer = analyzer_cls(embedder, thresholds, routing_graph=CALIBRATION_ROUTING_GRAPH)
    else:
        analyzer = analyzer_cls(embedder, thresholds)

    tp = fp = fn = 0
    false_positives: list[dict] = []
    false_negatives: list[dict] = []

    if emitted_flag_type in TRACE_LEVEL_TYPES:
        # -----------------------------------------------------------------
        # Grouped trace evaluation path — for checks that require N>=2 spans
        # -----------------------------------------------------------------
        groups = group_spans_by_trace(spans)
        for group in groups:
            # ANY row in the group may carry the authoritative label.
            # Fixture traces sometimes store the labeled span first (e.g. span_id suffix=1
            # appears before suffix=0 in JSONL order), so checking only the last row misses
            # many true positives. Use ANY-row convention to handle both orderings.
            last_row = group[-1]
            actual = any(
                emitted_flag_type in (row.get("anomaly_types") or [row.get("anomaly_type") or ""])
                for row in group
            )

            span_list = [build_span_data(row) for row in group]
            flags = analyzer.analyze(span_list)
            scores = analyzer.flush_scores()

            predicted = any(f.flag_type == emitted_flag_type for f in flags)
            matched_flags = [f for f in flags if f.flag_type == emitted_flag_type]

            if predicted and actual:
                tp += 1
            elif predicted and not actual:
                fp += 1
                if verbose:
                    false_positives.append({
                        "span_id": last_row.get("span_id"),
                        "prompt": (last_row.get("prompt") or "")[:120],
                        "tool_name": last_row.get("tool_name"),
                        "available_tools": [t.get("name") for t in (last_row.get("available_tools") or [])],
                        "flag_detail": matched_flags[0].detail if matched_flags else {},
                        "scores": [(m, round(s, 3)) for _, m, s in scores],
                    })
            elif not predicted and actual:
                fn += 1
                if verbose:
                    false_negatives.append({
                        "span_id": last_row.get("span_id"),
                        "prompt": (last_row.get("prompt") or "")[:120],
                        "tool_name": last_row.get("tool_name"),
                        "available_tools": [t.get("name") for t in (last_row.get("available_tools") or [])],
                        "scores": [(m, round(s, 3)) for _, m, s in scores],
                    })
    else:
        # -----------------------------------------------------------------
        # Per-row evaluation path (original behaviour — unchanged)
        # -----------------------------------------------------------------
        for row in spans:
            labels = row.get("anomaly_types") or [row.get("anomaly_type")]
            actual = emitted_flag_type in labels
            span = build_span_data(row)
            if isinstance(analyzer, BaseTraceAnalyzer):
                flags = analyzer.analyze([span])
            else:
                flags = analyzer.analyze(span)
            scores = analyzer.flush_scores()

            predicted = any(f.flag_type == emitted_flag_type for f in flags)
            matched_flags = [f for f in flags if f.flag_type == emitted_flag_type]

            if predicted and actual:
                tp += 1
            elif predicted and not actual:
                fp += 1
                if verbose:
                    false_positives.append({
                        "span_id": row.get("span_id"),
                        "prompt": (row.get("prompt") or "")[:120],
                        "tool_name": row.get("tool_name"),
                        "available_tools": [t.get("name") for t in (row.get("available_tools") or [])],
                        "flag_detail": matched_flags[0].detail if matched_flags else {},
                        "scores": [(m, round(s, 3)) for _, m, s in scores],
                    })
            elif not predicted and actual:
                fn += 1
                if verbose:
                    false_negatives.append({
                        "span_id": row.get("span_id"),
                        "prompt": (row.get("prompt") or "")[:120],
                        "tool_name": row.get("tool_name"),
                        "available_tools": [t.get("name") for t in (row.get("available_tools") or [])],
                        "scores": [(m, round(s, 3)) for _, m, s in scores],
                    })

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    if verbose:
        _print_failures(flag_type, false_positives, false_negatives)

    return precision, recall


def _print_failures(
    flag_type: str,
    false_positives: list[dict],
    false_negatives: list[dict],
) -> None:
    """Print FP and FN details for diagnosis."""
    sep = "-" * 60

    if false_positives:
        print(f"\n  FALSE POSITIVES ({len(false_positives)}) — clean spans incorrectly flagged:")
        for i, fp in enumerate(false_positives, 1):
            tools_str = ", ".join(fp["available_tools"])
            detail = fp["flag_detail"]
            rank = detail.get("rank", "?")
            top = detail.get("top_candidate", "?")
            scores_str = "  ".join(f"{m}={s}" for m, s in fp["scores"] if "tool" in m or "containment" in m or "embedding" in m or "coherence" in m or "missing" in m or "recall" in m)
            print(f"    [{i}] {fp['span_id']}")
            print(f"        prompt:  {fp['prompt']}")
            print(f"        called:  {fp['tool_name']}  |  available: [{tools_str}]")
            print(f"        rank={rank}  top={top}  {scores_str}")

    if false_negatives:
        print(f"\n  FALSE NEGATIVES ({len(false_negatives)}) — {flag_type} spans missed:")
        for i, fn in enumerate(false_negatives, 1):
            tools_str = ", ".join(fn["available_tools"])
            scores_str = "  ".join(f"{m}={s}" for m, s in fn["scores"] if "tool" in m or "containment" in m or "embedding" in m or "coherence" in m or "missing" in m or "recall" in m)
            print(f"    [{i}] {fn['span_id']}")
            print(f"        prompt:  {fn['prompt']}")
            print(f"        called:  {fn['tool_name']}  |  available: [{tools_str}]")
            print(f"        {scores_str or '(no relevant scores)'}")


# ---------------------------------------------------------------------------
# Hill climbing
# ---------------------------------------------------------------------------

def hill_climb(
    flag_type: str,
    spans: list[dict],
    embedder,
    current_thresholds: dict[str, float],
) -> tuple[float, float, float, list[dict]]:
    """Raise threshold until precision stops improving.

    Returns (best_threshold, best_precision, best_recall, history).
    history is a list of {threshold, precision, recall} for plotting.
    """
    threshold = HILL_CLIMB_START
    best_precision = -1.0
    best_threshold = HILL_CLIMB_START
    best_recall = 0.0
    history = []
    step = 0

    print(f"\n  [{flag_type}] hill climbing from {HILL_CLIMB_START:.2f} step={HILL_CLIMB_STEP:.2f}")

    while threshold <= HILL_CLIMB_MAX:
        precision, recall = evaluate_flag_type(
            flag_type, threshold, spans, embedder, current_thresholds
        )
        history.append({"threshold": round(threshold, 4), "precision": precision, "recall": recall})
        step += 1
        print(
            f"    step {step:2d}: threshold={threshold:.2f}  "
            f"precision={precision:.3f}  recall={recall:.3f}"
        )

        if precision < best_precision:
            print(f"    Precision dropped — stopping at threshold={best_threshold:.2f}")
            break

        best_precision = precision
        best_threshold = threshold
        best_recall = recall
        threshold = round(threshold + HILL_CLIMB_STEP, 4)
    else:
        print(f"    Reached max threshold={HILL_CLIMB_MAX:.2f}")

    return best_threshold, best_precision, best_recall, history


# ---------------------------------------------------------------------------
# Recall floor guard
# ---------------------------------------------------------------------------

def _check_recall_floor(flag_type: str, best_recall: float) -> None:
    """Exit with a human-readable error if best_recall is below the minimum floor.

    Called after each hill_climb() in main(). A recall below 0.10 indicates
    degenerate P=1.0, R=0.0 convergence — the threshold has been pushed so high
    that the analyzer never fires (perfect precision on nothing). The calibrated
    threshold would be useless in production.
    """
    if best_recall < 0.10:
        print(
            f"RECALL FLOOR ERROR: flag_type={flag_type} converged to "
            f"recall={best_recall:.3f} which is below the minimum floor of 0.10. "
            f"This indicates degenerate P=1.0, R=0.0 convergence. "
            f"Improve the fixture or check the analyzer logic before calibrating."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_pr_curves(results: dict[str, dict]) -> None:
    """One subplot per flag type showing the hill-climb path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Only plot flag types that have history (non-binary results)
    plottable = {ft: res for ft, res in results.items() if res.get("history")}
    n = len(plottable)
    if n == 0:
        print("\nNo numeric results to plot.")
        return

    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4), sharey=True)
    if n == 1:
        axes = [axes]

    for ax, (flag_type, res) in zip(axes, plottable.items()):
        history = res["history"]
        thresholds = [h["threshold"] for h in history]
        precisions = [h["precision"] for h in history]
        recalls = [h["recall"] for h in history]

        ax.plot(thresholds, precisions, "o-", label="Precision", color="steelblue")
        ax.plot(thresholds, recalls, "s--", label="Recall", color="darkorange", alpha=0.7)
        ax.axvline(
            x=res["best_threshold"],
            color="red", linestyle=":", linewidth=1.5,
            label=f"Selected={res['best_threshold']:.2f}",
        )
        ax.set_title(flag_type, fontsize=10)
        ax.set_xlabel("Threshold")
        ax.set_ylim(-0.05, 1.05)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    axes[0].set_ylabel("Score")
    fig.suptitle("Per-flag-type threshold calibration (hill climbing)", fontsize=12)
    fig.tight_layout()

    CURVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(CURVE_PATH, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nCalibration plot saved to {CURVE_PATH}")


# ---------------------------------------------------------------------------
# docker-compose patcher
# ---------------------------------------------------------------------------

def patch_docker_compose(calibrated: dict[str, float]) -> None:
    if not DOCKER_COMPOSE_PATH.exists():
        print(f"WARNING: {DOCKER_COMPOSE_PATH} not found — skipping patch")
        return

    key_to_env = {
        "tool_not_available":           "WORKER_THRESHOLD_TOOL_NOT_AVAILABLE",
        "wrong_tool_choice":            "WORKER_THRESHOLD_WRONG_TOOL_CHOICE",
        "unnecessary_tool_call":        "WORKER_THRESHOLD_UNNECESSARY_TOOL_CALL",
        "wrong_tool_args":              "WORKER_THRESHOLD_WRONG_TOOL_ARGS",
        "no_tool":                      "WORKER_THRESHOLD_NO_TOOL",
        "response_anomaly":             "WORKER_THRESHOLD_RESPONSE_ANOMALY",
        "context_overflow":             "WORKER_THRESHOLD_CONTEXT_OVERFLOW",
        # Phase 25
        "missing_details":              "WORKER_THRESHOLD_MISSING_DETAILS",
        "stale_context":                "WORKER_THRESHOLD_STALE_CONTEXT",
        "context_propagation_failure":  "WORKER_THRESHOLD_CONTEXT_PROPAGATION_FAILURE",
        "history_loss":                 "WORKER_THRESHOLD_HISTORY_LOSS",
        "step_repetition":              "WORKER_THRESHOLD_STEP_REPETITION",
        "termination_loop_n":           "WORKER_THRESHOLD_TERMINATION_LOOP_N",
    }

    content = DOCKER_COMPOSE_PATH.read_text(encoding="utf-8")
    patched = content
    for key, env_var in key_to_env.items():
        value = calibrated.get(key)
        if value is None:
            continue  # binary flag type — no threshold to patch
        pattern = rf'({re.escape(env_var)}:\s*)"[^"]*"'
        replacement = rf'\g<1>"{value}"'
        new_content, n_subs = re.subn(pattern, replacement, patched)
        if n_subs == 0:
            print(f"  WARNING: {env_var} not found in docker-compose.yml")
        else:
            print(f"  Patched {env_var}: {value}")
        patched = new_content

    DOCKER_COMPOSE_PATH.write_text(patched, encoding="utf-8")
    print(f"docker-compose.yml updated.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Calibrate ToolCallAnalyzer thresholds"
    )
    parser.add_argument(
        "--flag-type",
        dest="flag_type",
        default=None,
        help="Calibrate only this flag type in isolation (e.g. wrong_tool_args)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print false positives and false negatives for binary (rank-based) flag types",
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        default=False,
        help="Single-pass P/R evaluation using current thresholds — no hill climbing",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> dict:
    import httpx
    from xeter.services.worker.base import EmbedderClient

    cli_args = parse_args()

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
    spans = load_fixture()
    n_flagged = sum(1 for s in spans if s["label"] == "flagged")
    print(f"  Flagged: {n_flagged}, Clean: {len(spans) - n_flagged}")

    # Determine which flag types to calibrate this run
    if cli_args.flag_type:
        known = set(FLAG_TYPES) | BINARY_FLAG_TYPES
        if cli_args.flag_type not in known:
            print(f"ERROR: Unknown flag type: {cli_args.flag_type!r}. Known: {sorted(known)}")
            sys.exit(1)
        active_flag_types = [cli_args.flag_type] if cli_args.flag_type in FLAG_TYPES else []
        active_binary = ({cli_args.flag_type} if cli_args.flag_type in BINARY_FLAG_TYPES
                         else set())
    else:
        active_flag_types = FLAG_TYPES
        active_binary = BINARY_FLAG_TYPES

    # Calibrate each flag type independently via hill climbing.
    # In single-type mode (--flag-type), seed from the existing JSON so previous
    # per-type results are preserved when merging back. Full-suite runs always
    # start from DEFAULT_THRESHOLDS (fresh baseline).
    if cli_args.flag_type and THRESHOLDS_PATH.exists():
        try:
            existing_data = json.load(THRESHOLDS_PATH.open(encoding="utf-8"))
            # Merge existing thresholds into DEFAULT_THRESHOLDS so new keys (e.g.
            # context_overflow, phase 25/26 keys) are always present even when the
            # existing file was written before those keys were added (Rule 1 fix).
            calibrated = {**DEFAULT_THRESHOLDS, **existing_data.get("thresholds", {})}
        except (json.JSONDecodeError, KeyError, ValueError):
            calibrated = dict(DEFAULT_THRESHOLDS)
    else:
        calibrated = dict(DEFAULT_THRESHOLDS)
    results: dict[str, dict] = {}

    for flag_type in active_flag_types:
        if flag_type in active_binary or cli_args.eval_only:
            label = "binary" if flag_type in active_binary else f"threshold={calibrated.get(flag_type, 'N/A')}"
            print(f"\n  [{flag_type}] {label} — single evaluation pass")
            threshold = calibrated.get(flag_type, 1.0)
            precision, recall = evaluate_flag_type(
                flag_type, threshold, spans, embedder, calibrated,
                verbose=cli_args.verbose,
            )
            results[flag_type] = {
                "best_threshold": None if flag_type in active_binary else threshold,
                "best_precision": precision,
                "best_recall": recall,
                "history": [],
                "steps": 1,
                "binary": flag_type in active_binary,
            }
            print(f"    P={precision:.3f}  R={recall:.3f}")
            continue
        if flag_type == "termination_loop":
            print(f"\n  [{flag_type}] integer grid sweep {TERMINATION_LOOP_N_VALUES}")
            best_p_tl, best_r_tl, best_n_tl = -1.0, 0.0, 3
            for n_val in TERMINATION_LOOP_N_VALUES:
                p, r = evaluate_flag_type(flag_type, float(n_val), spans, embedder, calibrated)
                print(f"    n={n_val}: P={p:.3f}  R={r:.3f}")
                if p > best_p_tl:
                    best_p_tl, best_r_tl, best_n_tl = p, r, n_val
            _check_recall_floor(flag_type, best_r_tl)
            calibrated["termination_loop_n"] = float(best_n_tl)
            results[flag_type] = {
                "best_threshold": float(best_n_tl),
                "best_precision": best_p_tl,
                "best_recall": best_r_tl,
                "history": [],
                "steps": len(TERMINATION_LOOP_N_VALUES),
            }
            continue
        best_threshold, best_precision, best_recall, history = hill_climb(
            flag_type, spans, embedder, calibrated
        )
        _check_recall_floor(flag_type, best_recall)
        calibrated[flag_type] = best_threshold
        results[flag_type] = {
            "best_threshold": best_threshold,
            "best_precision": best_precision,
            "best_recall": best_recall,
            "history": history,
            "steps": len(history),
        }

    # Summary
    print("\n" + "=" * 65)
    print("CALIBRATION RESULT — per-flag-type hill climbing")
    print("=" * 65)
    all_pass = True
    for flag_type, res in results.items():
        if res.get("binary"):
            met = res["best_precision"] >= 0.80
            if not met:
                all_pass = False
            status = "OK" if met else "WARN (<80% precision)"
            print(
                f"  {flag_type:<25s}  rank-based  "
                f"P={res['best_precision']:.3f}  R={res['best_recall']:.3f}  [{status}]"
            )
            continue
        met = res["best_precision"] >= 0.80
        if not met:
            all_pass = False
        status = "OK" if met else "WARN (<80% precision)"
        print(
            f"  {flag_type:<25s}  threshold={res['best_threshold']:.2f}  "
            f"P={res['best_precision']:.3f}  R={res['best_recall']:.3f}  "
            f"steps={res['steps']}  [{status}]"
        )
    print("=" * 65)
    if not all_pass:
        print(
            "WARNING: Some flag types did not reach 80% precision. "
            "Consider improving fixture quality."
        )

    plot_pr_curves(results)

    # Write thresholds to dedicated file.
    # In single-type mode, merge new results into existing per_flag_type so
    # previous per-type calibrations are not erased.
    THRESHOLDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_per_flag_type = {
        ft: {
            "threshold": res["best_threshold"],
            "precision": round(res["best_precision"], 4) if res["best_precision"] is not None else None,
            "recall": round(res["best_recall"], 4) if res["best_recall"] is not None else None,
            "steps": res["steps"],
        }
        for ft, res in results.items()
    }
    if cli_args.flag_type and THRESHOLDS_PATH.exists():
        try:
            existing_data = json.load(THRESHOLDS_PATH.open(encoding="utf-8"))
            merged_per_flag_type = dict(existing_data.get("per_flag_type", {}))
            merged_per_flag_type.update(new_per_flag_type)
        except (json.JSONDecodeError, KeyError, ValueError):
            merged_per_flag_type = new_per_flag_type
    else:
        merged_per_flag_type = new_per_flag_type
    threshold_output = {
        "thresholds": calibrated,
        "per_flag_type": merged_per_flag_type,
    }
    with THRESHOLDS_PATH.open("w", encoding="utf-8") as f:
        json.dump(threshold_output, f, indent=2)
    print(f"\nCalibrated thresholds written to {THRESHOLDS_PATH}")

    print("\nPatching deploy/docker-compose.yml ...")
    patch_docker_compose(calibrated)
    print("\nCalibration complete.")

    return {"calibrated": calibrated, "results": results, "all_pass": all_pass}


if __name__ == "__main__":
    main()

"""TraceAnalyzer for the Embedding Worker.

Concrete implementation of BaseTraceAnalyzer providing 5 trace-level detection
checks introduced in Phase 25 (v1.5):

  _check_stale_context             CTX-02  — span[i].prompt ≈ span[i-1].tool_output
  _check_step_repetition           TRACE-01 — duplicate/near-duplicate tool calls
  _check_termination_loop          TRACE-02 — same tool called N+ times consecutively
  _check_context_propagation_failure  TRACE-03 — prompt missing key info from prior tool_output
  _check_history_loss              TRACE-04 — prompt disconnected from centroid of prior prompts

Invoked by the worker after WORKER_TRACE_FLUSH_TIMEOUT_S elapses with no new
spans for a given trace_id.
"""

from __future__ import annotations

import numpy as np
from rapidfuzz import fuzz

from xeter.services.worker.base import (
    BaseTraceAnalyzer,
    EmbedderClient,
    Flag,
    SpanData,
    bow_score,
    hybrid_score,
)


# ---------------------------------------------------------------------------
# spaCy helpers — lazy-loaded to avoid paying import cost at module level
# ---------------------------------------------------------------------------

_NLP = None


def _get_spacy():
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load("en_core_web_md")
    return _NLP


# ---------------------------------------------------------------------------
# TraceAnalyzer
# ---------------------------------------------------------------------------


class TraceAnalyzer(BaseTraceAnalyzer):
    """Trace-level analyzer implementing 5 detection checks for CTX-02 and TRACE-01–04."""

    def __init__(self, embedder: EmbedderClient, thresholds: dict[str, float]) -> None:
        super().__init__(embedder, thresholds)

    @property
    def name(self) -> str:
        """Stable analyzer name used as analyzer_name in span_scores rows."""
        return "trace_analyzer"

    def analyze(self, spans: list[SpanData]) -> list[Flag]:
        """Analyze all spans in a completed trace and return combined flags.

        Dispatches to 5 _check_*() helpers, each returning list[Flag].
        Results are concatenated in order.

        Args:
            spans: All SpanData objects accumulated for this trace_id.

        Returns:
            Combined list of Flag instances from all 5 checks.
        """
        flags: list[Flag] = []
        flags.extend(self._check_stale_context(spans))
        flags.extend(self._check_step_repetition(spans))
        flags.extend(self._check_termination_loop(spans))
        flags.extend(self._check_context_propagation_failure(spans))
        flags.extend(self._check_history_loss(spans))
        return flags

    # ------------------------------------------------------------------
    # CTX-02: stale_context
    # ------------------------------------------------------------------

    def _check_stale_context(self, spans: list[SpanData]) -> list[Flag]:
        """Detect when span[i].prompt closely copies span[i-1].tool_output.

        Uses rapidfuzz.fuzz.ratio (character-level edit ratio, 0–100 scale).
        Fires when score >= self._thresholds["stale_context"].
        Marks detail["low_confidence"] = True per D-06.
        """
        if len(spans) < 2:
            return []

        flags: list[Flag] = []
        for i in range(1, len(spans)):
            if spans[i - 1].tool_output is None:
                continue
            if spans[i].prompt is None:
                continue

            score = fuzz.ratio(spans[i].prompt, spans[i - 1].tool_output)
            # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
            self.log_score("stale_context", score)
            if score >= self._thresholds["stale_context"]:
                flags.append(Flag(
                    flag_type="stale_context",
                    score=score,
                    detail={
                        "metric": "stale_context",
                        "span_index": i,
                        "low_confidence": True,
                    },
                ))

        return flags

    # ------------------------------------------------------------------
    # TRACE-01: step_repetition
    # ------------------------------------------------------------------

    def _check_step_repetition(self, spans: list[SpanData]) -> list[Flag]:
        """Detect duplicate or near-duplicate tool calls across all span pairs.

        Uses rapidfuzz.fuzz.token_sort_ratio (word-order invariant, 0–100 scale).
        Compares every unique pair (a, b) where a < b.
        Fires when score >= self._thresholds["step_repetition"].
        """
        if len(spans) < 2:
            return []

        flags: list[Flag] = []
        for a in range(len(spans)):
            if spans[a].tool_name is None:
                continue
            key_a = f"{spans[a].tool_name} {spans[a].tool_arguments or ''}".strip()

            for b in range(a + 1, len(spans)):
                if spans[b].tool_name is None:
                    continue
                key_b = f"{spans[b].tool_name} {spans[b].tool_arguments or ''}".strip()

                score = fuzz.token_sort_ratio(key_a, key_b)
                # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
                self.log_score("step_repetition", score)
                if score >= self._thresholds["step_repetition"]:
                    flags.append(Flag(
                        flag_type="step_repetition",
                        score=score,
                        detail={
                            "metric": "step_repetition",
                            "span_index_a": a,
                            "span_index_b": b,
                        },
                    ))

        return flags

    # ------------------------------------------------------------------
    # TRACE-02: termination_loop
    # ------------------------------------------------------------------

    def _check_termination_loop(self, spans: list[SpanData]) -> list[Flag]:
        """Detect same tool called N+ times consecutively without interruption.

        Counts consecutive run length (not total occurrences).
        Fires when run_length >= int(self._thresholds["termination_loop_n"]).
        No log_score — count-based, not similarity-based (no calibration threshold).
        """
        if len(spans) < 2:
            return []

        n = int(self._thresholds["termination_loop_n"])
        flags: list[Flag] = []
        current_tool: str | None = None
        run_length = 0
        flagged_tools: set[str] = set()

        for span in spans:
            if span.tool_name is None:
                # Reset consecutive tracking on None tool_name
                current_tool = None
                run_length = 0
                continue

            if span.tool_name == current_tool:
                run_length += 1
            else:
                current_tool = span.tool_name
                run_length = 1

            if run_length >= n and current_tool not in flagged_tools:
                flags.append(Flag(
                    flag_type="termination_loop",
                    score=float(run_length),
                    detail={
                        "metric": "termination_loop",
                        "tool_name": current_tool,
                        "count": run_length,
                    },
                ))
                flagged_tools.add(current_tool)

        return flags

    # ------------------------------------------------------------------
    # TRACE-03: context_propagation_failure
    # ------------------------------------------------------------------

    def _check_context_propagation_failure(self, spans: list[SpanData]) -> list[Flag]:
        """Detect when span[i].prompt is missing key information from span[i-1].tool_output.

        Uses hybrid cosine+BOW scoring (hybrid_score utility from base.py).
        Fires when score < self._thresholds["context_propagation_failure"].
        """
        if len(spans) < 2:
            return []

        flags: list[Flag] = []
        for i in range(1, len(spans)):
            if spans[i - 1].tool_output is None:
                continue
            if spans[i].prompt is None:
                continue

            cosine = self.compare(
                self.embed(spans[i].prompt),
                self.embed(spans[i - 1].tool_output),
            )
            bow = bow_score(spans[i].prompt, spans[i - 1].tool_output)
            score = hybrid_score(cosine, bow)
            # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
            self.log_score("context_propagation_failure", score)
            if score < self._thresholds["context_propagation_failure"]:
                flags.append(Flag(
                    flag_type="context_propagation_failure",
                    score=score,
                    detail={
                        "metric": "context_propagation_failure",
                        "span_index": i,
                    },
                ))

        return flags

    # ------------------------------------------------------------------
    # TRACE-04: history_loss
    # ------------------------------------------------------------------

    def _check_history_loss(self, spans: list[SpanData]) -> list[Flag]:
        """Detect when span[i].prompt is semantically disconnected from prior prompts.

        Computes centroid of all prior span prompts via np.mean on encode_batch result.
        Guard: skips entirely when len(spans) < 3 (need at least 2 prior prompts for
        a meaningful centroid per D-08).
        Fires when score < self._thresholds["history_loss"].
        """
        if len(spans) < 3:
            return []

        flags: list[Flag] = []
        for i in range(2, len(spans)):
            if spans[i].prompt is None:
                continue

            prior_prompts = [s.prompt for s in spans[:i] if s.prompt is not None]
            if not prior_prompts:
                continue

            prior_vecs = self._embedder.encode_batch(prior_prompts)
            centroid = np.mean(prior_vecs, axis=0)
            current_vec = self.embed(spans[i].prompt)
            score = self.compare(current_vec, centroid)
            # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
            self.log_score("history_loss", score)
            if score < self._thresholds["history_loss"]:
                flags.append(Flag(
                    flag_type="history_loss",
                    score=score,
                    detail={
                        "metric": "history_loss",
                        "span_index": i,
                    },
                ))

        return flags

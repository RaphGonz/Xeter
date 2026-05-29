"""TraceAnalyzer for the Embedding Worker.

Concrete implementation of BaseTraceAnalyzer providing 11 trace-level detection
checks introduced in Phase 25 and Phase 26 (v1.5):

  _check_stale_context             CTX-02  — span[i].prompt ≈ span[i-1].tool_output
  _check_step_repetition           TRACE-01 — duplicate/near-duplicate tool calls
  _check_termination_loop          TRACE-02 — same tool called N+ times consecutively
  _check_context_propagation_failure  TRACE-03 — prompt missing key info from prior tool_output
  _check_history_loss              TRACE-04 — prompt disconnected from centroid of prior prompts
  _check_wrong_agent_handoff       TRACE-05 — unexpected agent-name transition given routing graph
  _check_information_withholding   TRACE-06 — span[i] response NEs not passed to span[i+1] prompt
  _check_conversation_reset        TRACE-07 — abrupt centroid cosine drop mid-trace
  _check_clarification_skipped     TRACE-08 — disjunctive prompt with no question in response
  _check_no_verification           TRACE-09 — no verification keyword in any span tool_name/desc
  _check_incomplete_verification   TRACE-10 — verification span covers < threshold of entities

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

_VERIFICATION_KEYWORDS: frozenset[str] = frozenset({
    "verify", "check", "validate", "assert", "test", "confirm"
})


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
    """Trace-level analyzer implementing 11 detection checks for CTX-02 and TRACE-01–10."""

    def __init__(
        self,
        embedder: EmbedderClient,
        thresholds: dict[str, float],
        routing_graph: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(embedder, thresholds)
        self._routing_graph = routing_graph

    @property
    def name(self) -> str:
        """Stable analyzer name used as analyzer_name in span_scores rows."""
        return "trace_analyzer"

    def analyze(self, spans: list[SpanData]) -> list[Flag]:
        """Analyze all spans in a completed trace and return combined flags.

        Dispatches to 11 _check_*() helpers, each returning list[Flag].
        Results are concatenated in order.

        Args:
            spans: All SpanData objects accumulated for this trace_id.

        Returns:
            Combined list of Flag instances from all 11 checks.
        """
        flags: list[Flag] = []
        flags.extend(self._check_stale_context(spans))
        flags.extend(self._check_step_repetition(spans))
        flags.extend(self._check_termination_loop(spans))
        flags.extend(self._check_context_propagation_failure(spans))
        flags.extend(self._check_history_loss(spans))
        # Phase 26 additions
        flags.extend(self._check_wrong_agent_handoff(spans))
        flags.extend(self._check_information_withholding(spans))
        flags.extend(self._check_conversation_reset(spans))
        flags.extend(self._check_clarification_skipped(spans))
        no_ver_flags = self._check_no_verification(spans)
        flags.extend(no_ver_flags)
        if not no_ver_flags:  # D-12: skip incomplete_verification when no_verification fired
            flags.extend(self._check_incomplete_verification(spans))
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

            score = fuzz.ratio(spans[i].prompt, spans[i - 1].tool_output) / 100
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

                score = fuzz.token_sort_ratio(key_a, key_b) / 100
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
        log_score emitted on every span so calibration harness has a score signal.
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

            # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
            self.log_score("termination_loop", float(run_length))

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
        Fires only when score < threshold for 2+ consecutive span pairs (low_score_streak >= 2).
        This prevents single-pair anomalies from triggering a flag.
        """
        if len(spans) < 2:
            return []

        flags: list[Flag] = []
        low_score_streak = 0
        for i in range(1, len(spans)):
            if spans[i - 1].tool_output is None:
                low_score_streak = 0
                continue
            if spans[i].prompt is None:
                low_score_streak = 0
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
                low_score_streak += 1
            else:
                low_score_streak = 0
            if low_score_streak >= 2:
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
        for i in range(3, len(spans)):
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

    # ------------------------------------------------------------------
    # TRACE-05: wrong_agent_handoff
    # ------------------------------------------------------------------

    def _check_wrong_agent_handoff(self, spans: list[SpanData]) -> list[Flag]:
        """Detect unexpected agent-name transitions given the routing graph.

        No-op (returns []) when routing_graph is None or empty (D-07).
        Fires only when src IS a known agent AND dst is not in routing_graph[src].
        Unknown source agents (None or unregistered) are silently skipped — they
        cannot be evaluated against the graph and would cause spurious false positives.
        Same-agent consecutive spans (src == dst) are skipped — no handoff occurred.
        Marks detail["low_confidence"] = True per TRACE-05 (D-08).
        """
        if not self._routing_graph:
            return []
        if len(spans) < 2:
            return []

        flags: list[Flag] = []
        for i in range(1, len(spans)):
            src = spans[i - 1].agent_name
            dst = spans[i].agent_name
            # Skip pairs with missing agent names — cannot evaluate routing
            if src is None or dst is None:
                continue
            if src == dst:
                # No handoff when same agent stays
                continue
            # Only flag when src IS a known agent but dst is not permitted
            violation = src in self._routing_graph and dst not in self._routing_graph[src]
            score = 1.0 if violation else 0.0
            # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
            self.log_score("wrong_agent_handoff", score)
            if violation:
                flags.append(Flag(
                    flag_type="wrong_agent_handoff",
                    score=score,
                    detail={
                        "metric": "wrong_agent_handoff",
                        "from_agent": src,
                        "to_agent": dst,
                        "low_confidence": True,
                    },
                ))

        return flags

    # ------------------------------------------------------------------
    # TRACE-06: information_withholding
    # ------------------------------------------------------------------

    def _check_information_withholding(self, spans: list[SpanData]) -> list[Flag]:
        """Detect when named entities from span[i-1].response are absent in span[i].prompt.

        Uses spaCy NE extraction (doc.ents). Recall ratio = len(produced ∩ present) / len(produced).
        Preconditions (both required before log_score):
          - produced set must have >= 2 NEs (single-NE responses too noisy)
          - score must be < 0.5 (> 50% entities withheld — hard precondition)
        After preconditions pass, calibrated threshold controls the final flag decision.
        Guard: skips log_score when produced entity set is empty or under-populated.
        """
        if len(spans) < 2:
            return []

        flags: list[Flag] = []
        for i in range(1, len(spans)):
            if spans[i - 1].response is None or spans[i].prompt is None:
                continue

            # Skip when span[i] is a verification span — incomplete_verification covers that
            # relationship; flagging here would double-count the same signal.
            tool_name_i = (spans[i].tool_name or "").lower()
            tool_desc_i = (spans[i].tool_description or "").lower()
            if any(kw in tool_name_i or kw in tool_desc_i for kw in _VERIFICATION_KEYWORDS):
                continue

            nlp = _get_spacy()
            produced = {ent.text.lower() for ent in nlp(spans[i - 1].response).ents}
            if not produced:
                # Guard: no NEs to check — skip log_score (avoid division-by-zero)
                continue
            if len(produced) < 2:
                # Guard: under-populated NE set too noisy — skip log_score
                continue
            present = {ent.text.lower() for ent in nlp(spans[i].prompt).ents}
            score = len(produced & present) / len(produced)
            # Hard precondition: only proceed when > 50% of entities are withheld
            if score >= 0.5:
                # Not significant enough withholding — skip log_score (guard exit)
                continue
            # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
            self.log_score("information_withholding", score)
            if score < self._thresholds.get("information_withholding", 0.5):
                flags.append(Flag(
                    flag_type="information_withholding",
                    score=score,
                    detail={
                        "metric": "information_withholding",
                        "span_index": i,
                    },
                ))

        return flags

    # ------------------------------------------------------------------
    # TRACE-07: conversation_reset
    # ------------------------------------------------------------------

    def _check_conversation_reset(self, spans: list[SpanData]) -> list[Flag]:
        """Detect abrupt centroid cosine drop mid-trace (same mechanism as history_loss).

        Requires at least 4 prior spans (range starts at i=4) so the centroid is stable.
        Fires only when score < threshold AND the drop from the previous step is abrupt
        (prev_score - score >= 0.15), distinguishing sudden resets from gradual drift.
        Marks detail["low_confidence"] = True per TRACE-07 (D-04).
        """
        if len(spans) < 3:
            return []

        flags: list[Flag] = []
        prev_score: float = 1.0
        for i in range(4, len(spans)):
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
            self.log_score("conversation_reset", score)
            if score < self._thresholds.get("conversation_reset", 0.25) and (prev_score - score) >= 0.15:
                flags.append(Flag(
                    flag_type="conversation_reset",
                    score=score,
                    detail={
                        "metric": "conversation_reset",
                        "span_index": i,
                        "low_confidence": True,
                    },
                ))
            prev_score = score

        return flags

    # ------------------------------------------------------------------
    # TRACE-08: clarification_skipped
    # ------------------------------------------------------------------

    def _check_clarification_skipped(self, spans: list[SpanData]) -> list[Flag]:
        """Detect disjunctive prompts where the response contains no clarifying question.

        DISJUNCTIVE_MARKERS = {"or", "either", "which"}.
        Fires when prompt contains a disjunctive marker AND response has no "?".
        Binary score: 1.0 when fired, 0.0 otherwise.
        Marks detail["low_confidence"] = True per TRACE-08.
        """
        if len(spans) < 1:
            return []

        DISJUNCTIVE_MARKERS = {"or", "either", "which"}
        flags: list[Flag] = []
        for idx, span in enumerate(spans):
            if span.prompt is None or span.response is None:
                continue

            prompt_lower = span.prompt.lower()
            response_lower = span.response.lower()
            has_disjunction = any(f" {m} " in f" {prompt_lower} " for m in DISJUNCTIVE_MARKERS)
            has_question = "?" in response_lower
            score = 1.0 if (has_disjunction and not has_question) else 0.0
            # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
            self.log_score("clarification_skipped", score)
            if has_disjunction and not has_question:
                flags.append(Flag(
                    flag_type="clarification_skipped",
                    score=score,
                    detail={
                        "metric": "clarification_skipped",
                        "span_index": idx,
                        "low_confidence": True,
                    },
                ))

        return flags

    # ------------------------------------------------------------------
    # TRACE-09: no_verification
    # ------------------------------------------------------------------

    def _check_no_verification(self, spans: list[SpanData]) -> list[Flag]:
        """Detect traces where no span has a verification keyword in tool_name or tool_description.

        Uses module-level _VERIFICATION_KEYWORDS frozenset (D-13).
        Binary check: returns one Flag when no verification span found.
        Precondition: the trace must contain at least one write/mutate tool call.
        Traces that only read data have no obligation to verify — flagging them is vacuous.
        Mutual-exclusion partner with _check_incomplete_verification (D-12):
        analyze() skips incomplete_verification when this check fires.
        Guard: if len(spans) < 2: return [] — single-span traces skip all trace-level checks.
        Guard exits (no write/mutate found) do NOT call log_score per D-04 invariant.
        """
        if len(spans) < 2:
            return []

        # Guard: only apply when the trace has at least one write/mutate tool call.
        # Read-only traces have nothing to verify — check would fire vacuously.
        # "send" covers send_email/send_message; "execute"/"sql" covers execute_sql;
        # "submit" covers form submissions — all are write/side-effect operations.
        WRITE_MUTATE_KEYWORDS: frozenset[str] = frozenset({
            "write", "create", "update", "delete", "insert", "save",
            "post", "put", "patch", "modify", "set",
            "send", "email", "execute", "sql", "submit", "publish", "deploy",
        })
        has_write_mutate = any(
            kw in (span.tool_name or "").lower() or kw in (span.tool_description or "").lower()
            for span in spans
            for kw in WRITE_MUTATE_KEYWORDS
        )
        if not has_write_mutate:
            # Guard exit: no write/mutate call present — do NOT log_score (D-04)
            return []

        has_verification = False
        for span in spans:
            tool_name_lower = (span.tool_name or "").lower()
            tool_desc_lower = (span.tool_description or "").lower()
            if any(kw in tool_name_lower or kw in tool_desc_lower for kw in _VERIFICATION_KEYWORDS):
                has_verification = True
                break

        score = 0.0 if has_verification else 1.0
        # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
        self.log_score("no_verification", score)
        if not has_verification:
            return [Flag(
                flag_type="no_verification",
                score=score,
                detail={"metric": "no_verification"},
            )]
        return []

    # ------------------------------------------------------------------
    # TRACE-10: incomplete_verification
    # ------------------------------------------------------------------

    def _check_incomplete_verification(self, spans: list[SpanData]) -> list[Flag]:
        """Detect when the verification span's prompt covers too few entities produced earlier.

        Entity scope: spaCy NEs from all prior span responses (before verification span).
        Recall ratio = len(verified_entities ∩ produced_entities) / len(produced_entities).
        Fires when recall < self._thresholds["incomplete_verification"] (default 0.7).
        Guard: skips log_score when produced entity set is empty (D-09, D-10, D-11).
        analyze() gates this check via D-12 (only runs when no_verification did not fire).
        """
        if len(spans) < 2:
            return []

        # Find first verification span
        ver_idx: int | None = None
        for idx, span in enumerate(spans):
            tool_name_lower = (span.tool_name or "").lower()
            tool_desc_lower = (span.tool_description or "").lower()
            if any(kw in tool_name_lower or kw in tool_desc_lower for kw in _VERIFICATION_KEYWORDS):
                ver_idx = idx
                break

        if ver_idx is None:
            # Defensive guard: should not happen when analyze() gates via D-12
            return []
        if ver_idx == 0:
            # No prior spans to compare against
            return []

        # Collect non-None prior responses before loading spaCy (avoid unnecessary import)
        prior_responses = [span.response for span in spans[:ver_idx] if span.response]
        if not prior_responses:
            # Guard: no prior responses to extract NEs from — skip log_score
            return []

        nlp = _get_spacy()
        produced_entities: set[str] = set()
        for response in prior_responses:
            produced_entities.update({ent.text.lower() for ent in nlp(response).ents})

        if not produced_entities:
            # Guard: no NEs in prior responses — skip log_score
            return []

        ver_prompt = spans[ver_idx].prompt or ""
        verified_entities = {ent.text.lower() for ent in nlp(ver_prompt).ents}
        score = len(verified_entities & produced_entities) / len(produced_entities)
        # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
        self.log_score("incomplete_verification", score)
        if score < self._thresholds.get("incomplete_verification", 0.7):
            return [Flag(
                flag_type="incomplete_verification",
                score=score,
                detail={
                    "metric": "incomplete_verification",
                    "coverage_ratio": score,
                },
            )]
        return []

"""SemanticSpanAnalyzer — embedding-based span checks.

Implements _check_missing_details (CTX-04): fires when response does not
semantically cover items explicitly requested in prompt. Detection via
hybrid cosine + bag-of-words scoring with spaCy lemma entity recall as
the BOW component.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from xeter.services.worker.base import BaseAnalyzer, Flag, SpanData, bow_score, hybrid_score


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


def _lemma_set(text: str) -> set[str]:
    """Return the set of lowercase content-word lemmas from text (spaCy).

    Filters out stop words ("a", "the", "in", …) to avoid spurious
    containment matches on function words.
    """
    nlp = _get_spacy()
    return {
        token.lemma_.lower()
        for token in nlp(text)
        if token.is_alpha and not token.is_stop
    }


# ---------------------------------------------------------------------------
# SemanticSpanAnalyzer
# ---------------------------------------------------------------------------


class SemanticSpanAnalyzer(BaseAnalyzer):
    """Embedding-based span-level checks.

    Does not override __init__ — inherits (embedder, thresholds) constructor
    from BaseAnalyzer. Implements CTX-04: _check_missing_details.
    """

    @property
    def name(self) -> str:
        """Stable analyzer name used as analyzer_name in span_scores rows."""
        return "semantic_span"

    def analyze(self, span: SpanData) -> list[Flag]:
        """Analyze a single span and return zero or more Flag instances.

        Dispatches to _check_missing_details. Each check either returns an
        empty list (no flag) or a list with a single Flag instance.
        """
        flags: list[Flag] = []
        flags.extend(self._check_missing_details(span))
        return flags

    # ------------------------------------------------------------------
    # CTX-04: missing_details
    # ------------------------------------------------------------------

    def _check_missing_details(self, span: SpanData) -> list[Flag]:
        """Fire when the response does not semantically cover the prompt's request.

        Uses hybrid cosine + BOW scoring. Guard paths return early without
        calling log_score (D-04 invariant: no log_score on guard exit).
        log_score is called BEFORE the threshold comparison on all non-guard paths.
        """
        if span.prompt is None:
            return []
        if span.response is None:
            return []

        # Compute cosine similarity between prompt and response embeddings
        prompt_vec = self.embed(span.prompt)
        response_vec = self.embed(span.response)
        cosine = self.compare(prompt_vec, response_vec)

        # Compute BOW (Jaccard token overlap)
        bow = bow_score(span.prompt, span.response)

        # 50/50 hybrid blend
        score = hybrid_score(cosine, bow)

        # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
        self.log_score("missing_details", score)

        threshold = self._thresholds["missing_details"]
        if score < threshold:
            return [Flag(
                flag_type="missing_details",
                score=score,
                detail={
                    "metric": "missing_details",
                    "cosine": round(cosine, 4),
                    "bow": round(bow, 4),
                },
            )]
        return []

# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
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
        """Fire when the response ignores specific named people referenced in the prompt.

        Signal: what fraction of PERSON entities in the prompt appear in the response?
        Guard: skip if fewer than 2 PERSON entities (no specific individuals to track).
        Guard paths return early without calling log_score (D-04 invariant).
        log_score is called BEFORE the threshold comparison on all non-guard paths.
        """
        if span.prompt is None or span.response is None:
            return []

        # Entity types that signal "specific named thing the model needs context about".
        # GPE (places) and DATE/CARDINAL excluded — they appear in wrong_tool prompts
        # and don't signal missing knowledge context.
        _CONTEXT_ENTITY_TYPES = {"PERSON", "ORG", "LAW", "WORK_OF_ART", "EVENT"}

        nlp = _get_spacy()
        # Exclude single-token all-lowercase entities — these are typically
        # mistagged technical terms (e.g. "asyncio" tagged as PERSON) rather
        # than real named entities that require provided context.
        prompt_ents = [
            e for e in nlp(span.prompt).ents
            if e.label_ in _CONTEXT_ENTITY_TYPES
            and not (len(e.text.split()) == 1 and e.text == e.text.lower())
        ]

        # Guard: only check prompts that reference 2+ context-bearing named entities.
        if len(prompt_ents) < 2:
            return []

        response_lower = span.response.lower()
        found = sum(1 for e in prompt_ents if e.text.lower() in response_lower)
        ne_recall = found / len(prompt_ents)

        # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
        self.log_score("missing_details", ne_recall)

        threshold = self._thresholds["missing_details"]
        if ne_recall < threshold:
            return [Flag(
                flag_type="missing_details",
                score=ne_recall,
                detail={
                    "metric": "missing_details",
                    "ne_recall": round(ne_recall, 4),
                    "prompt_ents": [e.text for e in prompt_ents],
                },
            )]
        return []

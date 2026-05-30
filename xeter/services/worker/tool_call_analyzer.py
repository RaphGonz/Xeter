"""ToolCallAnalyzer — concrete analyzer for tool-call anomaly detection.

Detects seven categories of tool-call anomaly by computing cosine similarities
between prompt, tool, argument, and response embeddings:

  tool_not_available      — called tool was not offered (absent or no list)
  wrong_tool_choice       — a better tool existed among available ones
  unnecessary_tool_call   — no available tool was appropriate for the prompt
  wrong_tool_args         — tool arguments are semantically unrelated to the prompt
  no_tool                 — prompt implies a tool call that was never made
  parsing_error           — model+prompt vs response shows a structural mismatch
  response_anomaly        — prompt vs response similarity is unusually low

All similarity scores are logged via self.log_score() BEFORE threshold comparison
so that non-flagged spans still contribute to the calibration dataset (Phase 6).

No numeric threshold literal appears in this file — every comparison reads from
self._thresholds[key].
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Optional

import numpy as np

from xeter.services.worker.base import BaseSpanAnalyzer, Flag, SpanData, bow_score, hybrid_score
from xeter.services.worker.tool_call_registry import (
    TOOL_CALL_REGISTRY,
    FORMAT_GROUPS,
    extract_nested,
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


_CLAUSE_DEPS = frozenset({"ROOT", "advcl", "relcl", "xcomp", "ccomp", "conj"})


def _extract_non_negated_clauses(text: str) -> list[str]:
    """Extract all non-negated action clauses from text using spaCy dependency parse.

    Finds all clause-head verbs (ROOT, advcl, relcl, xcomp, ccomp, conj) and skips
    any whose immediate children include a negation token (dep_ == "neg"). Returns
    the full subtree span for each non-negated clause head, deduplicated by span
    boundaries. Falls back to [text] when no verbs are found.

    A prompt can contain multiple independent action intents; returning all
    non-negated clauses lets _check_wrong_tool score each intent separately and
    take the best match per tool.
    """
    nlp = _get_spacy()
    doc = nlp(text)
    seen: set[tuple[int, int]] = set()
    clauses: list[str] = []
    for token in doc:
        if token.pos_ not in ("VERB", "AUX"):
            continue
        if token.dep_ not in _CLAUSE_DEPS:
            continue
        if any(child.dep_ == "neg" for child in token.children):
            continue
        subtree = sorted(token.subtree, key=lambda t: t.i)
        start, end = subtree[0].i, subtree[-1].i + 1
        if (start, end) not in seen:
            seen.add((start, end))
            clauses.append(doc[start:end].text.strip())
    return [c for c in clauses if c] or [text]


_NER_ENTITY_TYPES = frozenset({
    "CARDINAL", "DATE", "TIME", "PERSON", "ORG", "GPE", "LOC",
    "MONEY", "QUANTITY", "ORDINAL", "PRODUCT", "EVENT",
})

_SOCIAL_CENTROID_PATH = Path(__file__).parent.parent.parent.parent / "fixtures" / "social_centroid.npy"
_SOCIAL_CENTROID: np.ndarray | None = (
    np.load(_SOCIAL_CENTROID_PATH) if _SOCIAL_CENTROID_PATH.exists() else None
)

_ACTION_VERBS: frozenset[str] = frozenset({
    "find", "search", "get", "fetch", "query", "calculate", "send", "create",
    "update", "delete", "run", "execute", "show", "list", "compare", "retrieve",
    "lookup", "add", "remove", "set", "check", "generate", "summarize", "analyze",
    "read", "write", "open", "close", "save", "load", "download", "upload",
})






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


_STRIP_PUNCT_RE = re.compile(r'[^a-z0-9]')
_NUMERIC_OR_BOOL_RE = re.compile(r'^[\d\s\+\-\*\/\^\%\.]+$')
_TIME_FORMAT_RE = re.compile(r'^\d{1,2}:\d{2}(:\d{2})?$')
_SQL_KEYWORD_RE = re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE)\b', re.IGNORECASE)
_BOOL_LITERALS = frozenset({"true", "false"})


def _strip_punctuation(token: str) -> str:
    return _STRIP_PUNCT_RE.sub('', token.lower())


class ToolCallAnalyzer(BaseSpanAnalyzer):
    """Analyze SpanData for tool-call anomalies using embedding similarity."""

    def __init__(self, embedder, thresholds: dict[str, float]) -> None:
        super().__init__(embedder, thresholds)
        self._tool_embed_cache: dict[str, list[np.ndarray]] = {}

    # ------------------------------------------------------------------
    # BaseAnalyzer abstract interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "tool_call"

    def analyze(self, span: SpanData) -> list[Flag]:
        """Run all seven check methods and return a flat list of Flag instances."""
        flags: list[Flag] = []
        flags.extend(self._check_tool_not_available(span))
        flags.extend(self._check_wrong_tool_choice(span))
        flags.extend(self._check_unnecessary_tool_call(span))
        flags.extend(self._check_wrong_args(span))
        flags.extend(self._check_no_tool(span))
        flags.extend(self._check_parsing_error(span))
        flags.extend(self._check_response_anomaly(span))
        return flags

    # ------------------------------------------------------------------
    # Tool embedding cache (FLAG-09 / calibration efficiency)
    # ------------------------------------------------------------------

    def _get_tool_embeddings(self, available_tools: list[dict]) -> list[np.ndarray]:
        """Return embeddings for all tools, cached by content hash.

        Cache key is a SHA-256 of the sorted JSON representation so identical
        tool lists (in any order) always hit the cache.
        """
        tools_json = json.dumps(available_tools, sort_keys=True)
        cache_key = hashlib.sha256(tools_json.encode()).hexdigest()
        if cache_key not in self._tool_embed_cache:
            self._tool_embed_cache[cache_key] = [
                self.embed(f"{t.get('name', '')} {t.get('description', '')}")
                for t in available_tools
            ]
        return self._tool_embed_cache[cache_key]

    # ------------------------------------------------------------------
    # Check methods — tool_not_available (deterministic, binary)
    # ------------------------------------------------------------------

    def _check_tool_not_available(self, span: SpanData) -> list[Flag]:
        """Detect when the called tool was not offered to the agent."""
        if span.tool_name is None:
            return []

        # Called tool absent from the offered list (includes empty-list case)
        if not any(t.get("name") == span.tool_name for t in (span.available_tools or [])):
            self.log_score("tool_not_in_list", 1.0)
            return [Flag(
                flag_type="tool_not_available",
                score=1.0,
                detail={
                    "metric": "tool_not_in_list",
                    "actual_tool": span.tool_name,
                    "available_tools": [t.get("name") for t in (span.available_tools or [])],
                },
            )]

        return []

    # ------------------------------------------------------------------
    # Check methods — wrong_tool_choice (Case B: rank > 1, score ≥ floor)
    # ------------------------------------------------------------------

    def _check_wrong_tool_choice(self, span: SpanData) -> list[Flag]:
        """Detect when a better tool existed among the available ones.

        Requires tool IS in the list and score ≥ coherence floor (otherwise
        unnecessary_tool_call handles it). Containment guard via spaCy lemma
        overlap short-circuits before any embedding work.
        """
        if span.tool_name is None or not span.available_tools or span.prompt is None:
            return []

        # Skip if tool not in list — handled by _check_tool_not_available
        candidate = next(
            (t for t in span.available_tools if t.get("name") == span.tool_name),
            None,
        )
        if candidate is None:
            return []

        # Step 1 — Stemmed containment check
        prompt_lemmas = _lemma_set(span.prompt)
        target_text = f"{candidate.get('name', '')} {candidate.get('description', '')}".strip()
        target_lemmas = _lemma_set(target_text)
        if prompt_lemmas & target_lemmas:
            self.log_score("containment_match", 1.0)
            return []

        # Step 2 — Embedding ranking (pure cosine, full prompt)
        prompt_vec = self.embed(span.prompt)
        tool_vecs = self._get_tool_embeddings(span.available_tools)

        tool_scores: list[tuple[str, float]] = []
        for tool, tool_vec in zip(span.available_tools, tool_vecs):
            name = tool.get("name", "")
            sim = self.compare(prompt_vec, tool_vec)
            tool_scores.append((name, sim))

        tool_scores.sort(key=lambda x: x[1], reverse=True)

        rank = next(
            (i + 1 for i, (name, _) in enumerate(tool_scores) if name == span.tool_name),
            None,
        )
        called_score = tool_scores[rank - 1][1]
        self.log_score("embedding_rank", float(rank))
        self.log_score("embedding_score", called_score)

        top_name, top_score = tool_scores[0]

        # Defer to _check_unnecessary_tool_call only when ALL tools are
        # incoherent.  If the best tool is coherent, the called tool simply
        # ranks below it → wrong_tool_choice (handled by the rank > 1 check).
        if top_score < self._thresholds["tool_coherence_threshold"]:
            return []

        if rank == 1:
            return []

        # Require a minimum score gap between the best alternative and the
        # called tool (D-11). A gap < 0.10 means the ranking difference is a
        # near-coin-toss in embedding space and should not be flagged.
        score_gap = top_score - called_score
        self.log_score("score_gap", score_gap)
        if score_gap < 0.10:
            return []

        # Case B: a better tool existed
        return [Flag(
            flag_type="wrong_tool_choice",
            score=called_score,
            detail={
                "metric": "embedding_rank",
                "rank": rank,
                "top_candidate": top_name,
                "top_score": top_score,
                "actual_tool": span.tool_name,
                "all_rankings": [{"name": n, "score": s} for n, s in tool_scores],
            },
        )]

    # ------------------------------------------------------------------
    # Check methods — unnecessary_tool_call (Case C: low coherence)
    # ------------------------------------------------------------------

    def _check_unnecessary_tool_call(self, span: SpanData) -> list[Flag]:
        """Detect tool calls triggered by social/phatic prompts (e.g. 'thanks!').

        Four sequential gates — all must pass to flag:
          1. Token length ≤ 20
          2. No named entities (person, org, location, quantity, date, …)
          3. No action verbs (find, search, get, …)
          4. Centroid similarity ≥ threshold (social prompt embedding proximity)
        """
        if span.tool_name is None or span.prompt is None:
            return []

        nlp = _get_spacy()
        doc = nlp(span.prompt)

        # Gate 1: short prompt only
        if len(doc) > 20:
            return []

        # Gate 2: no named entities
        if any(ent.label_ in _NER_ENTITY_TYPES for ent in doc.ents):
            return []

        # Gate 3: no action verbs
        if any(
            token.pos_ == "VERB" and token.lemma_.lower() in _ACTION_VERBS
            for token in doc
        ):
            return []

        # Gate 4: centroid similarity
        if _SOCIAL_CENTROID is None:
            # Centroid not yet built — skip embedding gate, trust gates 1-3
            centroid_score = 1.0
        else:
            prompt_vec = self.embed(span.prompt)
            centroid_score = float(self.compare(prompt_vec, _SOCIAL_CENTROID))

        self.log_score("social_centroid_score", centroid_score)

        threshold = self._thresholds["unnecessary_tool_call"]
        if centroid_score < threshold:
            return []

        return [Flag(
            flag_type="unnecessary_tool_call",
            score=centroid_score,
            detail={
                "metric": "social_prompt",
                "token_count": len(doc),
                "centroid_score": centroid_score,
                "actual_tool": span.tool_name,
            },
        )]

    # ------------------------------------------------------------------
    # Check methods — FLAG-12
    # ------------------------------------------------------------------

    def _check_wrong_args(self, span: SpanData) -> list[Flag]:
        if span.tool_arguments is None or span.prompt is None:
            return []

        args_stripped = span.tool_arguments.strip()
        if not args_stripped or args_stripped in ("{}", "[]", "null"):
            return []

        try:
            parsed = json.loads(span.tool_arguments)
        except (ValueError, TypeError):
            return []
        if not isinstance(parsed, dict) or not parsed:
            return []

        prompt_stripped = _strip_punctuation(span.prompt)
        prompt_vec = self.embed(span.prompt)

        # Guard: only evaluate args when the called tool is a plausible match for the prompt.
        # If the tool itself is wrong (wrong_tool_choice territory), skip — the args being
        # unrelated is a consequence of the wrong tool, not an independent args problem.
        if span.available_tools and span.tool_name and prompt_vec is not None:
            called_def = next(
                (t for t in span.available_tools if t.get("name") == span.tool_name), None
            )
            if called_def is not None:
                tool_text = called_def.get("description") or span.tool_name
                tool_vec = self.embed(tool_text)
                if tool_vec is not None:
                    tool_fit = float(self.compare(tool_vec, prompt_vec))
                    self.log_score("tool_fit_score", tool_fit)
                    if tool_fit < self._thresholds.get("wrong_tool_args_tool_fit", 0.15):
                        return []

        threshold = self._thresholds["wrong_tool_args"]
        violations: list[dict] = []
        worst_score = 1.0

        for key, value in parsed.items():
            # Check 1 — missing argument
            if value is None or str(value).strip() == "":
                violations.append({"key": key, "value": "", "score": 0.0, "reason": "missing_argument"})
                worst_score = 0.0
                continue

            str_value = str(value)

            # Skip — numeric/boolean/expression literals
            if _NUMERIC_OR_BOOL_RE.match(str_value.strip()) or str_value.strip().lower() in _BOOL_LITERALS:
                continue

            # Skip — clock time values (e.g. "10:00" won't substring-match "10am")
            if _TIME_FORMAT_RE.match(str_value.strip()):
                continue

            # Skip — multi-line or SQL values (model-generated content)
            if "\n" in str_value or _SQL_KEYWORD_RE.search(str_value):
                continue

            # Skip — very short values (e.g. "yes", "no", "all") that embed poorly
            # against any long prompt without being semantically wrong (D-14)
            if len(str_value.strip()) <= 3:
                continue

            # Check 2 — argument in prompt (substring match)
            if _strip_punctuation(str_value) in prompt_stripped:
                continue

            # Check 3 — argument similar to prompt (embedding)
            score = 0.0
            if prompt_vec is not None:
                value_vec = self.embed(str_value)
                if value_vec is not None and isinstance(value_vec, np.ndarray) and isinstance(prompt_vec, np.ndarray):
                    score = self.compare(value_vec, prompt_vec)

            self.log_score("arg_grounding", score)

            if score < threshold:
                violations.append({"key": key, "value": str_value, "score": score, "reason": "not_grounded"})
                worst_score = min(worst_score, score)

        if not violations:
            return []

        return [Flag(
            flag_type="wrong_tool_args",
            score=worst_score,
            detail={"metric": "arg_violations", "violations": violations},
        )]

    # ------------------------------------------------------------------
    # Check methods — FLAG-08 (no_tool)
    # ------------------------------------------------------------------

    def _check_no_tool(self, span: SpanData) -> list[Flag]:
        """Detect when the prompt implies a tool call but no tool was used.

        A generic "call a function tool" reference string is used as the
        comparison target. High similarity → the prompt expected tool use.
        """
        if span.tool_name is not None:
            return []  # tool was called; this check is not applicable
        if span.prompt is None:
            return []

        prompt_vec = self.embed(span.prompt)
        reference_vec = self.embed("call a function tool")
        score = self.compare(prompt_vec, reference_vec)

        self.log_score("prompt_expects_tool", score)

        if score > self._thresholds["no_tool"]:
            return [
                Flag(
                    flag_type="no_tool",
                    score=score,
                    detail={
                        "metric": "prompt_expects_tool",
                        "score": score,
                    },
                )
            ]
        return []

    # ------------------------------------------------------------------
    # Check methods — FLAG-07
    # ------------------------------------------------------------------

    def _check_parsing_error(self, span: SpanData) -> list[Flag]:
        """Detect tool-call format parsing errors using the format registry.

        Different models emit tool calls in different formats (<xml>, {{}},
        bare function calls, etc.). A wrong parser silently drops tool calls
        (A4 failure). This check validates raw_response against the model's
        known format from the registry.

        Reference: https://old.reddit.com/r/LocalLLaMA/comments/1r4ie8z/i_tested_21_small_llms_on_toolcalling_judgment/
        """
        if span.raw_response is None:
            return []

        entry = TOOL_CALL_REGISTRY.get(span.agent_model)
        if entry is None:
            # Unknown model — log score 0 and flag so the user knows
            self.log_score("format_match", 0.0)
            return [
                Flag(
                    flag_type="parsing_error",
                    score=0.0,
                    detail={
                        "metric": "format_match",
                        "error": f"Unknown model: {span.agent_model}. No registry entry.",
                    },
                )
            ]

        if entry["transport"] == "api_structured":
            # API-structured: raw_response should be valid JSON
            try:
                parsed = json.loads(span.raw_response)
            except (json.JSONDecodeError, TypeError) as exc:
                self.log_score("format_match", 0.0)
                return [
                    Flag(
                        flag_type="parsing_error",
                        score=0.0,
                        detail={
                            "metric": "format_match",
                            "error": f"api_structured model but raw_response is not valid JSON: {exc}",
                        },
                    )
                ]

            # Check if any detect pattern matches the raw string
            detected = any(p.search(span.raw_response) for p in entry["detect"])
            if not detected:
                # No tool call detected — not an error, just no tool call in this response
                self.log_score("format_match", 1.0)
                return []

            # Validate argument field type if format expects a JSON string
            errors: list[str] = []
            fmt_group = FORMAT_GROUPS.get(entry["format"])
            if fmt_group and fmt_group["argument_type"] == "json_string" and entry.get("argument_field"):
                args_raw = extract_nested(parsed, entry["argument_field"])
                if args_raw is not None and not isinstance(args_raw, str):
                    errors.append(
                        f"Expected {entry['argument_field']} to be a JSON string, "
                        f"got {type(args_raw).__name__}. Do not double-parse."
                    )

            if errors:
                self.log_score("format_match", 0.0)
                return [
                    Flag(
                        flag_type="parsing_error",
                        score=0.0,
                        detail={"metric": "format_match", "errors": errors},
                    )
                ]

            self.log_score("format_match", 1.0)
            return []

        if entry["transport"] == "raw_text":
            if not entry["detect"]:
                # Non-printable delimiters (e.g. deepseek_v3) — can't regex check
                self.log_score("format_match", 0.5)
                return []

            detected = any(p.search(span.raw_response) for p in entry["detect"])
            self.log_score("format_match", 1.0 if detected else 0.0)

            if not detected:
                return [
                    Flag(
                        flag_type="parsing_error",
                        score=0.0,
                        detail={
                            "metric": "format_match",
                            "error": f"No {entry['format']} pattern found in raw_response for model {span.agent_model}.",
                        },
                    )
                ]
            return []

        # Unknown transport
        self.log_score("format_match", 0.0)
        return [
            Flag(
                flag_type="parsing_error",
                score=0.0,
                detail={"metric": "format_match", "error": f"Unknown transport: {entry['transport']}"},
            )
        ]

    # ------------------------------------------------------------------
    # Check methods — FLAG-06
    # ------------------------------------------------------------------

    def _check_response_anomaly(self, span: SpanData) -> list[Flag]:
        """Detect response anomalies by comparing prompt and response embeddings.

        Embeds prompt and response independently, computes cosine similarity,
        logs it as "prompt_vs_response", and flags if below threshold (FLAG-06).
        """
        if span.prompt is None or span.response is None:
            return []

        # No-tool spans are owned by _check_no_tool; do not double-count here
        if span.tool_name is None:
            return []

        prompt_vec = self.embed(span.prompt)
        response_vec = self.embed(span.response)
        score = self.compare(prompt_vec, response_vec)

        # MUST call log_score BEFORE threshold comparison (FLAG-10 / calibration-first)
        self.log_score("prompt_vs_response", score)

        # Very short prompts produce low cosine similarity with any response; do not flag (D-15)
        if len(span.prompt.split()) < 4:
            return []

        # Defer to wrong_tool_choice when a clearly better tool existed (gap >= 0.10).
        # Reuse prompt_vec already computed above.
        if span.available_tools:
            tool_vecs = self._get_tool_embeddings(span.available_tools)
            tool_sim = {
                t.get("name", ""): self.compare(prompt_vec, tv)
                for t, tv in zip(span.available_tools, tool_vecs)
            }
            called_sim = tool_sim.get(span.tool_name)
            if called_sim is not None:
                best_sim = max(tool_sim.values())
                if best_sim - called_sim >= 0.10:
                    return []

        if score < self._thresholds["response_anomaly"]:
            return [
                Flag(
                    flag_type="response_anomaly",
                    score=score,
                    detail={
                        "metric": "prompt_vs_response",
                        "score": score,
                    },
                )
            ]
        return []

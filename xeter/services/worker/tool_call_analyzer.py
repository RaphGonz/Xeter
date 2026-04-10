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
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional
from urllib.parse import urlparse

import numpy as np

from xeter.services.worker.base import BaseAnalyzer, Flag, SpanData, bow_score, hybrid_score
from xeter.services.worker.tool_call_registry import (
    TOOL_CALL_REGISTRY,
    FORMAT_GROUPS,
    extract_nested,
)


_WRONG_ARGS_ERROR_PATTERNS: list[re.Pattern] = [
    re.compile(r'invalid argument', re.IGNORECASE),
    re.compile(r'invalid param', re.IGNORECASE),
    re.compile(r'missing required', re.IGNORECASE),
    re.compile(r'missing param', re.IGNORECASE),
    re.compile(r'required field', re.IGNORECASE),
    re.compile(r'validation error', re.IGNORECASE),
    re.compile(r'type error', re.IGNORECASE),
    re.compile(r'value error', re.IGNORECASE),
    re.compile(r'parse error', re.IGNORECASE),
    re.compile(r'HTTP [4][0-9][0-9]', re.IGNORECASE),
    re.compile(r'status[ _]?code[: ]*4[0-9][0-9]', re.IGNORECASE),
    re.compile(r'400 bad request', re.IGNORECASE),
    re.compile(r'422 unprocessable', re.IGNORECASE),
]

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


def _extract_context_candidates(prompt: str) -> set[str]:
    """Extract candidate strings from the prompt for argument grounding checks.

    Returns NER entities (dates, names, IDs, quantities, etc.) and proper-noun-headed
    noun chunks, lowercased and deduplicated. Restricting chunks to proper-noun heads
    (PROPN) avoids adding common noun phrases like "compound interest" which provide
    no meaningful grounding signal and cause false positives.
    """
    nlp = _get_spacy()
    doc = nlp(prompt)
    candidates: set[str] = set()
    for ent in doc.ents:
        if ent.label_ in _NER_ENTITY_TYPES:
            candidates.add(ent.text.lower().strip())
    for chunk in doc.noun_chunks:
        if chunk.root.pos_ == "PROPN":
            candidates.add(chunk.text.lower().strip())
    return {c for c in candidates if len(c) > 1}


def _arg_grounding_score(value: str, candidates: set[str]) -> float:
    """Return a grounding score for value against context candidates.

    Two-signal check (takes the max):
    1. Containment: if any candidate appears as a substring of value, score=1.0.
       Handles long arg values (SQL queries, sentences) that embed a NER entity.
    2. SequenceMatcher: character-level ratio of the whole value vs each candidate.
       Handles short values (location names, IDs) that should closely resemble the entity.

    Returns 1.0 when candidates is empty (no NER signal → no evidence of mismatch).
    """
    if not candidates:
        return 1.0
    normalized = value.lower().strip()
    if any(c in normalized for c in candidates):
        return 1.0
    return max(SequenceMatcher(None, normalized, c).ratio() for c in candidates)


# ---------------------------------------------------------------------------
# Schema-free format heuristics (key-name based)
# ---------------------------------------------------------------------------

def _validate_email(value: str) -> str | None:
    if re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', value.strip()):
        return None
    return "invalid_email_format"


def _validate_date(value: str) -> str | None:
    stripped = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            datetime.strptime(stripped, fmt)
            return None
        except ValueError:
            pass
    # Accept natural language date indicators
    if re.search(
        r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4}|'
        r'today|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        stripped, re.IGNORECASE,
    ):
        return None
    return "invalid_date_format"


def _validate_url(value: str) -> str | None:
    try:
        r = urlparse(value.strip())
        if r.scheme in ("http", "https", "ftp", "ftps") and r.netloc:
            return None
    except Exception:
        pass
    return "invalid_url_format"


_FORMAT_KEY_PATTERNS: list[tuple[re.Pattern, object]] = [
    # "email" anywhere in key — avoids \b which treats _ as a word char
    (re.compile(r'email', re.IGNORECASE), _validate_email),
    # Match "date" as standalone or after "_" (avoids matching "update")
    (re.compile(r'(?:^|_)date(?:_|$)|_at$|_on$', re.IGNORECASE), _validate_date),
    (re.compile(r'(?:^|_)url(?:_|$)|(?:^|_)uri(?:_|$)', re.IGNORECASE), _validate_url),
]


def _key_has_format_pattern(key: str) -> bool:
    """Return True if any format pattern applies to this key."""
    return any(p.search(key) for p, _ in _FORMAT_KEY_PATTERNS)


def _check_format_heuristic(key: str, value: str) -> str | None:
    """Return an error reason string if value fails the format implied by key name.

    Matches key against _FORMAT_KEY_PATTERNS in order and runs the corresponding
    validator. Returns None if key matches no known pattern or value passes validation.
    """
    for pattern, validator in _FORMAT_KEY_PATTERNS:
        if pattern.search(key):
            return validator(value)  # type: ignore[operator]
    return None


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


class ToolCallAnalyzer(BaseAnalyzer):
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
        """Detect when the called tool was not offered to the agent.

        Two sub-cases:
          - WTOOL-03: available_tools is None or empty — tool called with no list
          - tool_not_in_list: called tool name is absent from available_tools
        """
        if span.tool_name is None:
            return []

        # WTOOL-03: tool called but none available
        if not span.available_tools:
            self.log_score("no_available_tools", 1.0)
            return [Flag(
                flag_type="tool_not_available",
                score=1.0,
                detail={
                    "metric": "no_available_tools",
                    "actual_tool": span.tool_name,
                },
            )]

        # Called tool absent from the offered list
        if not any(t.get("name") == span.tool_name for t in span.available_tools):
            self.log_score("tool_not_in_list", 1.0)
            return [Flag(
                flag_type="tool_not_available",
                score=1.0,
                detail={
                    "metric": "tool_not_in_list",
                    "actual_tool": span.tool_name,
                    "available_tools": [t.get("name") for t in span.available_tools],
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
        """Detect when no available tool was appropriate for the prompt.

        The called tool's embedding score is below the coherence floor,
        meaning no tool in the list was semantically grounded in the prompt.
        Replaces the old excessive_tool check with a more principled signal.
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

        # Containment guard — if prompt shares lemmas with the called tool,
        # the tool call is textually grounded and not unnecessary
        prompt_lemmas = _lemma_set(span.prompt)
        target_text = f"{candidate.get('name', '')} {candidate.get('description', '')}".strip()
        target_lemmas = _lemma_set(target_text)
        if prompt_lemmas & target_lemmas:
            self.log_score("containment_match", 1.0)
            return []

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
        self.log_score("tool_coherence_score", called_score)

        coherence_floor = self._thresholds["unnecessary_tool_call"]
        top_name, top_score = tool_scores[0]

        # If the best tool IS coherent, the issue is wrong_tool_choice, not
        # unnecessary — a reasonable tool existed, the agent just ignored it.
        if top_score >= coherence_floor:
            return []

        if called_score >= coherence_floor:
            return []
        return [Flag(
            flag_type="unnecessary_tool_call",
            score=called_score,
            detail={
                "metric": "low_tool_coherence",
                "rank": rank,
                "top_candidate": top_name,
                "top_score": top_score,
                "actual_tool": span.tool_name,
                "all_rankings": [{"name": n, "score": s} for n, s in tool_scores],
            },
        )]

    # ------------------------------------------------------------------
    # Check methods — FLAG-12
    # ------------------------------------------------------------------

    def _check_wrong_args(self, span: SpanData) -> list[Flag]:
        """Detect when tool arguments are semantically unrelated to the prompt.

        Three-path detection (ARGS-01 takes priority):

        Path 1 — output-error priority (ARGS-01):
          If tool_output contains an error pattern (regex), flag immediately.
          Score=1.0. No spaCy call.

        Path 2 — per-argument format heuristics (schema-free):
          For arguments whose key name implies a known format (email, date, url),
          validate the value against that format. Format violations score 0.0 and
          skip the grounding check for that argument.

        Path 3 — per-argument grounding check:
          Build context candidates from the prompt (NER entities + noun chunks).
          For each argument value, compute the best SequenceMatcher ratio against
          candidates. If no candidates are found → no signal → no flag.
          Flag if the worst-case score across all args is below threshold.

        low_confidence is NOT included in flag detail (ARGS-05).
        """
        if span.tool_arguments is None or span.prompt is None:
            return []

        # ARGS-01: output-error priority path (no spaCy)
        if span.tool_output and any(
            p.search(span.tool_output) for p in _WRONG_ARGS_ERROR_PATTERNS
        ):
            self.log_score("wrong_args_output_error", 1.0)
            return [Flag(
                flag_type="wrong_tool_args",
                score=1.0,
                detail={"metric": "output_error_pattern", "source": "tool_output"},
            )]

        # Skip empty / null args — nothing to compare
        args_stripped = span.tool_arguments.strip()
        if not args_stripped or args_stripped in ("{}", "[]", "null"):
            return []

        try:
            parsed = json.loads(span.tool_arguments)
        except (ValueError, TypeError):
            return []
        if not isinstance(parsed, dict) or not parsed:
            return []

        # Per-argument checks — format heuristics run unconditionally;
        # grounding checks only when prompt yields candidates.
        violations: list[dict] = []
        all_scores: list[float] = []
        needs_grounding: list[tuple[str, str]] = []  # (key, value) pairs deferred to grounding

        for key, value in parsed.items():
            if value is None or str(value).strip() == "":
                continue
            str_value = str(value)

            # Path 2: schema-free format heuristic
            format_issue = _check_format_heuristic(key, str_value)
            if format_issue is not None:
                # Value is structurally malformed for this key type
                all_scores.append(0.0)
                violations.append({"key": key, "value": str_value, "score": 0.0, "reason": format_issue})
                continue
            if _key_has_format_pattern(key):
                # Value passes format validation — trust it, skip grounding
                # (e.g. ISO date "2025-03-05" won't SequenceMatcher-match "March 5th")
                all_scores.append(1.0)
                continue

            needs_grounding.append((key, str_value))

        # Path 3: grounding check — only when candidates are available
        if needs_grounding:
            candidates = _extract_context_candidates(span.prompt)
            if candidates:
                for key, str_value in needs_grounding:
                    score = _arg_grounding_score(str_value, candidates)
                    all_scores.append(score)
                    if score < self._thresholds["wrong_tool_args"]:
                        violations.append({"key": key, "value": str_value, "score": score, "reason": "not_grounded"})
            else:
                # No NER signal — treat remaining args as grounded
                all_scores.extend(1.0 for _ in needs_grounding)

        if not all_scores:
            return []  # no checkable arguments

        worst_score = min(all_scores)
        self.log_score("arg_grounding", worst_score)  # log BEFORE threshold (ARGS-05)

        if not violations:
            return []

        return [Flag(
            flag_type="wrong_tool_args",
            score=worst_score,
            detail={"metric": "arg_grounding", "violations": violations},
            # ARGS-05: no low_confidence key
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

        prompt_vec = self.embed(span.prompt)
        response_vec = self.embed(span.response)
        score = self.compare(prompt_vec, response_vec)

        # MUST call log_score BEFORE threshold comparison (FLAG-10 / calibration-first)
        self.log_score("prompt_vs_response", score)

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

"""ToolCallAnalyzer — concrete analyzer for tool-call anomaly detection.

Detects five categories of tool-call anomaly by computing cosine similarities
between prompt, tool, argument, and response embeddings:

  wrong_tool        — called tool is not the best semantic match for the prompt
  wrong_tool_args   — tool arguments are semantically unrelated to the prompt
  no_tool           — prompt implies a tool call that was never made
  excessive_tool    — tool was called but the prompt did not warrant it
  parsing_error     — model+prompt vs response shows a structural mismatch
  response_anomaly  — prompt vs response similarity is unusually low

All similarity scores are logged via self.log_score() BEFORE threshold comparison
so that non-flagged spans still contribute to the calibration dataset (Phase 6).

No numeric threshold literal appears in this file — every comparison reads from
self._thresholds[key].
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

import numpy as np

from xeter.services.worker.base import BaseAnalyzer, Flag, SpanData
from xeter.services.worker.tool_call_registry import (
    TOOL_CALL_REGISTRY,
    FORMAT_GROUPS,
    extract_nested,
)


class ToolCallAnalyzer(BaseAnalyzer):
    """Analyze SpanData for tool-call anomalies using embedding similarity."""

    def __init__(self, model, thresholds: dict[str, float]) -> None:
        super().__init__(model, thresholds)
        self._tool_embed_cache: dict[str, list[np.ndarray]] = {}

    # ------------------------------------------------------------------
    # BaseAnalyzer abstract interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "tool_call"

    def analyze(self, span: SpanData) -> list[Flag]:
        """Run all six check methods and return a flat list of Flag instances."""
        flags: list[Flag] = []
        flags.extend(self._check_wrong_tool(span))
        flags.extend(self._check_wrong_args(span))
        flags.extend(self._check_no_tool(span))
        flags.extend(self._check_excessive_tool(span))
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
    # Check methods — FLAG-04, FLAG-05, FLAG-11
    # ------------------------------------------------------------------

    def _check_wrong_tool(self, span: SpanData) -> list[Flag]:
        """Detect when the called tool is not the top semantic match for the prompt.

        Three signals are combined:
          - prompt vs tool_name (FLAG-04)
          - prompt vs tool_description (FLAG-05)
          - available_tools ranking — top-ranked tool by similarity (FLAG-11)

        A wrong_tool flag is raised when available_tools ranking disagrees with
        the called tool AND the top-ranked similarity is below threshold.
        """
        if span.tool_name is None:
            return []
        if span.prompt is None:
            return []

        prompt_vec = self.embed(span.prompt)

        # --- available_tools ranking (FLAG-11) ---
        if span.available_tools is not None and len(span.available_tools) > 0:
            tool_vecs = self._get_tool_embeddings(span.available_tools)
            tool_scores: list[tuple[str, float]] = []
            for tool, tool_vec in zip(span.available_tools, tool_vecs):
                score = self.compare(prompt_vec, tool_vec)
                tool_scores.append((tool.get("name", ""), score))

            # Sort descending — highest similarity first
            tool_scores.sort(key=lambda x: x[1], reverse=True)
            top_tool_name, top_score = tool_scores[0]

            # Log the ranking score
            self.log_score("prompt_vs_tool_rank", top_score)

            # Also log individual signals (FLAG-04 / FLAG-05)
            if span.tool_name is not None:
                tool_name_vec = self.embed(span.tool_name)
                name_score = self.compare(prompt_vec, tool_name_vec)
                self.log_score("prompt_vs_tool_name", name_score)

            if span.tool_description is not None:
                desc_vec = self.embed(span.tool_description)
                desc_score = self.compare(prompt_vec, desc_vec)
                self.log_score("prompt_vs_tool_description", desc_score)

            # Flag if: called tool is not top-ranked AND top similarity below threshold
            if (
                span.tool_name != top_tool_name
                and top_score < self._thresholds["wrong_tool"]
            ):
                ranked_detail = [
                    {"name": name, "score": score} for name, score in tool_scores
                ]
                return [
                    Flag(
                        flag_type="wrong_tool",
                        score=top_score,
                        detail={
                            "metric": "prompt_vs_tool_rank",
                            "expected_tool": top_tool_name,
                            "actual_tool": span.tool_name,
                            "score": top_score,
                            "ranked_tools": ranked_detail,
                        },
                    )
                ]
        else:
            # No available_tools — fall back to prompt vs tool_name (FLAG-04)
            tool_name_vec = self.embed(span.tool_name)
            name_score = self.compare(prompt_vec, tool_name_vec)
            self.log_score("prompt_vs_tool_name", name_score)

            if span.tool_description is not None:
                desc_vec = self.embed(span.tool_description)
                desc_score = self.compare(prompt_vec, desc_vec)
                self.log_score("prompt_vs_tool_description", desc_score)

            if name_score < self._thresholds["wrong_tool"]:
                return [
                    Flag(
                        flag_type="wrong_tool",
                        score=name_score,
                        detail={
                            "metric": "prompt_vs_tool_name",
                            "actual_tool": span.tool_name,
                            "score": name_score,
                        },
                    )
                ]

        return []

    # ------------------------------------------------------------------
    # Check methods — FLAG-12
    # ------------------------------------------------------------------

    def _check_wrong_args(self, span: SpanData) -> list[Flag]:
        """Detect when tool arguments are semantically unrelated to the prompt.

        Always attaches low_confidence: True because argument text is often
        terse JSON keys/values that are hard to compare fairly (FLAG-12).
        """
        if span.tool_arguments is None or span.prompt is None:
            return []

        prompt_vec = self.embed(span.prompt)
        args_vec = self.embed(span.tool_arguments)
        score = self.compare(prompt_vec, args_vec)

        self.log_score("prompt_vs_tool_args", score)

        if score < self._thresholds["wrong_tool_args"]:
            return [
                Flag(
                    flag_type="wrong_tool_args",
                    score=score,
                    detail={
                        "metric": "prompt_vs_tool_args",
                        "score": score,
                        "low_confidence": True,
                    },
                )
            ]
        return []

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
    # Check methods — FLAG-08 (excessive_tool)
    # ------------------------------------------------------------------

    def _check_excessive_tool(self, span: SpanData) -> list[Flag]:
        """Detect when a tool was called but the prompt doesn't warrant it.

        Low similarity between the prompt and the tool name suggests the
        tool call was unnecessary or misdirected.
        """
        if span.tool_name is None:
            return []  # no tool was called; this check is not applicable
        if span.prompt is None:
            return []

        prompt_vec = self.embed(span.prompt)
        tool_name_vec = self.embed(span.tool_name)
        score = self.compare(prompt_vec, tool_name_vec)

        self.log_score("prompt_vs_tool_relevance", score)

        if score < self._thresholds["excessive_tool"]:
            return [
                Flag(
                    flag_type="excessive_tool",
                    score=score,
                    detail={
                        "metric": "prompt_vs_tool_relevance",
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

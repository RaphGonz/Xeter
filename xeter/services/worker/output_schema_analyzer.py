"""OutputSchemaAnalyzer — deterministic span-level schema and context-overflow checks.

Implements 5 checks (output_schema_violation, required_fields_missing, output_truncated,
type_coercion_error, context_overflow) — no embedding calls. All checks log_score() before
flag/clean decisions so every span contributes to span_scores.

Checks implemented:
  output_schema_violation  — expected_output_schema set AND response is not valid JSON (D-01, sub-case A)
  required_fields_missing  — tool_arguments JSON missing required fields per jsonschema Draft7 (SCHEMA-02)
  output_truncated         — finish_reason=length in raw_response OR unclosed JSON delimiter (SCHEMA-03)
  type_coercion_error      — tool_arguments contains type violations per jsonschema Draft7 (SCHEMA-04)
  context_overflow         — prompt token count via tiktoken cl100k_base exceeds threshold (CTX-01)

All checks are deterministic; no embedding calls are made. The analyzer is self-contained:
register it in main.py and calibrate.py (plan 24-03) to activate it in the worker pipeline.
"""

from __future__ import annotations

import json
from typing import Optional

import jsonschema

from xeter.services.worker.base import BaseSpanAnalyzer, Flag, SpanData


# ---------------------------------------------------------------------------
# tiktoken helpers — lazy-loaded to avoid paying import cost at module level
# (Pitfall 6: tiktoken lazy import pattern mirrors tool_call_analyzer._get_spacy)
# ---------------------------------------------------------------------------

_TIKTOKEN_ENCODING = None


def _get_tiktoken():
    global _TIKTOKEN_ENCODING
    if _TIKTOKEN_ENCODING is None:
        import tiktoken as _tiktoken
        _TIKTOKEN_ENCODING = _tiktoken.get_encoding("cl100k_base")
    return _TIKTOKEN_ENCODING


# ---------------------------------------------------------------------------
# OutputSchemaAnalyzer
# ---------------------------------------------------------------------------

class OutputSchemaAnalyzer(BaseSpanAnalyzer):
    """Deterministic span-level schema and context-overflow checks.

    Does not override __init__ — inherits (embedder, thresholds) constructor
    from BaseAnalyzer (D-06). The embedder is accepted for interface consistency
    but never called by any check method in this class.
    """

    @property
    def name(self) -> str:
        """Stable analyzer name used as analyzer_name in span_scores rows."""
        return "output_schema"

    def analyze(self, span: SpanData) -> list[Flag]:
        """Analyze a single span and return zero or more Flag instances.

        Dispatches to the 5 private check methods in order. Each check either
        returns an empty list (no flag) or a list with a single Flag instance.
        """
        flags: list[Flag] = []
        flags.extend(self._check_output_schema_violation(span))
        flags.extend(self._check_required_fields_missing(span))
        flags.extend(self._check_output_truncated(span))
        flags.extend(self._check_type_coercion_error(span))
        flags.extend(self._check_context_overflow(span))
        return flags

    # ------------------------------------------------------------------
    # SCHEMA-01: output_schema_violation (D-01, sub-case A only)
    # ------------------------------------------------------------------

    def _check_output_schema_violation(self, span: SpanData) -> list[Flag]:
        """Fire when expected_output_schema is set AND response is not valid JSON.

        Early guards return [] without log_score (D-04 invariant: early exits
        do not contribute to span_scores because the span did not participate
        in this check's logic).
        """
        if span.expected_output_schema is None:
            return []
        if span.response is None:
            return []
        try:
            json.loads(span.response)
            # Valid JSON — no violation
            self.log_score("output_schema_violation", 0.0)
            return []
        except (json.JSONDecodeError, ValueError):
            self.log_score("output_schema_violation", 1.0)
            return [Flag(
                flag_type="output_schema_violation",
                score=1.0,
                detail={"metric": "output_schema_violation"},
            )]

    # ------------------------------------------------------------------
    # SCHEMA-03: output_truncated — finish_reason=length OR unclosed delimiter
    # ------------------------------------------------------------------

    def _parse_finish_reason(self, raw_response: Optional[str]) -> Optional[str]:
        """Extract finish reason from raw_response JSON. Provider-agnostic.

        Returns "length" if truncation detected, None otherwise or on parse failure.

        Provider formats:
          OpenAI:   {"choices": [{"finish_reason": "length"}]}
          Anthropic: {"stop_reason": "max_tokens"}  → normalized to "length"
        """
        if raw_response is None:
            return None
        try:
            parsed = json.loads(raw_response)
        except (json.JSONDecodeError, ValueError):
            return None
        # OpenAI shape: {"choices": [{"finish_reason": "..."}]}
        choices = parsed.get("choices")
        if isinstance(choices, list) and choices:
            reason = choices[0].get("finish_reason")
            if reason is not None:
                return reason
        # Anthropic shape: {"stop_reason": "max_tokens"} — normalize to "length"
        stop_reason = parsed.get("stop_reason")
        if stop_reason == "max_tokens":
            return "length"
        return stop_reason

    def _has_unclosed_delimiter(self, text: Optional[str]) -> bool:
        """Return True if text fails JSON parse AND ends without a closing delimiter.

        Pitfall 3: A malformed string like '{"key": undefined}' ends with '}' →
        returns False (correctly NOT classified as truncated). The heuristic only
        fires when the string has opening structure but is missing the closing char.
        """
        if not text:
            return False
        text = text.rstrip()
        try:
            json.loads(text)
            return False  # valid JSON — not truncated
        except (json.JSONDecodeError, ValueError):
            pass
        # Heuristic: has opening delimiter but last char is not a closing one
        last = text[-1] if text else ""
        has_open = "{" in text or "[" in text
        return has_open and last not in ("}", "]", '"')

    def _check_output_truncated(self, span: SpanData) -> list[Flag]:
        """Fire when finish_reason=length in raw_response OR unclosed JSON delimiter.

        Early guard: if raw_response, response, and tool_arguments are all None there
        is no signal to examine and no log_score is recorded (D-04 invariant — early
        exits do not contribute to span_scores). When at least one field is present
        the check always logs a score for calibration completeness.
        """
        if span.raw_response is None and span.response is None and span.tool_arguments is None:
            return []
        finish_reason = self._parse_finish_reason(span.raw_response)
        truncated_by_reason = finish_reason == "length"
        truncated_by_delimiter = (
            self._has_unclosed_delimiter(span.response)
            or self._has_unclosed_delimiter(span.tool_arguments)
        )
        if truncated_by_reason or truncated_by_delimiter:
            self.log_score("output_truncated", 1.0)
            return [Flag(
                flag_type="output_truncated",
                score=1.0,
                detail={"metric": "output_truncated"},
            )]
        self.log_score("output_truncated", 0.0)
        return []

    # ------------------------------------------------------------------
    # SCHEMA-02: required_fields_missing
    # ------------------------------------------------------------------

    def _check_required_fields_missing(self, span: SpanData) -> list[Flag]:
        """Fire when tool_arguments JSON is missing required fields per jsonschema Draft7.

        Early guard: return [] when expected_output_schema or tool_arguments is None.
        Both JSON strings are parsed before validation (Pitfall 1: expected_output_schema
        is Optional[str], not a dict). On malformed JSON, return [] — not this check's
        concern (T-24-04 mitigated). SCHEMA-02 and SCHEMA-04 can co-fire independently
        on the same span (Pitfall 2) because they use separate iter_errors() calls.
        """
        if span.expected_output_schema is None or span.tool_arguments is None:
            return []
        try:
            schema = json.loads(span.expected_output_schema)
            instance = json.loads(span.tool_arguments)
        except (json.JSONDecodeError, ValueError):
            return []  # malformed schema or args — not this check's concern
        errors = [
            e for e in jsonschema.Draft7Validator(schema).iter_errors(instance)
            if e.validator == "required"
        ]
        if errors:
            self.log_score("required_fields_missing", 1.0)
            return [Flag(
                flag_type="required_fields_missing",
                score=1.0,
                detail={
                    "metric": "required_fields_missing",
                    "missing_fields": [e.message for e in errors],
                },
            )]
        self.log_score("required_fields_missing", 0.0)
        return []

    # ------------------------------------------------------------------
    # SCHEMA-04: type_coercion_error
    # ------------------------------------------------------------------

    def _check_type_coercion_error(self, span: SpanData) -> list[Flag]:
        """Fire when tool_arguments contains type violations per jsonschema Draft7.

        Identical structure to _check_required_fields_missing but filters by
        e.validator == "type". Flag.detail uses key "type_errors" (not "missing_fields").
        Both SCHEMA-02 and SCHEMA-04 can fire on the same span (Pitfall 2) — they run
        independently in analyze() and filter different e.validator values.
        """
        if span.expected_output_schema is None or span.tool_arguments is None:
            return []
        try:
            schema = json.loads(span.expected_output_schema)
            instance = json.loads(span.tool_arguments)
        except (json.JSONDecodeError, ValueError):
            return []
        errors = [
            e for e in jsonschema.Draft7Validator(schema).iter_errors(instance)
            if e.validator == "type"
        ]
        if errors:
            self.log_score("type_coercion_error", 1.0)
            return [Flag(
                flag_type="type_coercion_error",
                score=1.0,
                detail={
                    "metric": "type_coercion_error",
                    "type_errors": [e.message for e in errors],
                },
            )]
        self.log_score("type_coercion_error", 0.0)
        return []

    # ------------------------------------------------------------------
    # CTX-01: context_overflow
    # ------------------------------------------------------------------

    def _check_context_overflow(self, span: SpanData) -> list[Flag]:
        """Fire when prompt token count via tiktoken cl100k_base exceeds threshold.

        Early guard: return [] when prompt is None (D-04 — no log_score when span
        did not participate). log_score is called with the NUMERIC token_count BEFORE
        threshold comparison (D-04 invariant: the count IS the calibration signal).
        Threshold is always read from self._thresholds["context_overflow"] — no
        numeric literal 8000 here (D-05, D-03). Lazy tiktoken load via _get_tiktoken()
        avoids cold-start penalty (Pitfall 6).
        """
        if span.prompt is None:
            return []
        enc = _get_tiktoken()
        token_count = len(enc.encode(span.prompt))
        # CRITICAL: log BEFORE threshold comparison (D-04 invariant)
        self.log_score("prompt_token_count", float(token_count))
        threshold = self._thresholds["context_overflow"]
        if token_count > threshold:
            return [Flag(
                flag_type="context_overflow",
                score=1.0,
                detail={
                    "metric": "prompt_token_count",
                    "token_count": token_count,
                    "threshold": threshold,
                },
            )]
        return []

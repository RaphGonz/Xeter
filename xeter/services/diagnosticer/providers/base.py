"""
LLM provider base contracts for the Diagnosticer service.

Defines:
  - DiagnosisResult: typed dataclass for parsed LLM output
  - LLMProvider: Protocol that all concrete providers must satisfy
  - LLMError: raised when the LLM call fails (network, rate limit, etc.)
  - ParseError: raised when the LLM response cannot be parsed into DiagnosisResult
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class DiagnosisResult:
    """Parsed output from the LLM diagnosis call."""

    verdict: Literal["model", "architecture", "prompt", "unknown"]
    severity: Literal["low", "medium", "high"]
    affected_field: str
    fix: str


class LLMProvider(Protocol):
    """Async callable interface all providers must implement."""

    async def diagnose(self, context: str) -> tuple[DiagnosisResult, str]:
        """Run root-cause analysis on the assembled context string.

        Args:
            context: Full assembled context string (span fields + flags + payloads).

        Returns:
            Tuple of (parsed DiagnosisResult, raw LLM response string).

        Raises:
            LLMError: On network failure, rate limit, or LLM-side error.
            ParseError: If the response cannot be parsed into DiagnosisResult.
        """
        ...


class LLMError(Exception):
    """LLM call failed (network, authentication, rate limit, etc.)."""


class ParseError(Exception):
    """LLM responded but output could not be parsed into DiagnosisResult."""

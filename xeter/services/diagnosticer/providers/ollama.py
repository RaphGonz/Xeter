# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Ollama provider for Diagnosticer — uses ollama.AsyncClient with format= schema.

NOTE: Structured output via format= is model-dependent. Not all local models
handle JSON schema constraints reliably. Set DIAGNOSTICER_MODEL to a
function-calling-capable model (e.g., llama3.2, qwen2.5).

OLLAMA_HOST env var sets the Ollama server URL (default: http://ollama:11434).
"""

from __future__ import annotations

import os
from typing import Literal

import ollama
from pydantic import BaseModel

from xeter.services.diagnosticer.providers.base import (
    DiagnosisResult,
    LLMError,
    ParseError,
)


class _DiagnosisOutput(BaseModel):
    """Pydantic model used to validate Ollama's structured JSON output."""

    verdict: Literal["model", "architecture", "prompt", "unknown"]
    severity: Literal["low", "medium", "high"]
    affected_field: str
    fix: str


class OllamaProvider:
    """Calls a local Ollama model with format= structured output."""

    def __init__(self, model: str) -> None:
        self._model = model
        host = os.environ.get("OLLAMA_HOST", "http://ollama:11434")  # [safe-default] docker-compose value
        self._client = ollama.AsyncClient(host=host)

    async def diagnose(self, context: str) -> tuple[DiagnosisResult, str]:
        """Run diagnosis using Ollama format= structured output.

        The format parameter passes the JSON schema to the model, constraining
        the response to the DiagnosisOutput shape. Model must support JSON schema
        constrained generation (llama3.2, qwen2.5 are known-good choices).

        Raises:
            LLMError: On connection failure (Ollama not running) or API error.
            ParseError: If the model's JSON output fails Pydantic validation.
        """
        try:
            response = await self._client.chat(
                model=self._model,
                messages=[{"role": "user", "content": context}],
                format=_DiagnosisOutput.model_json_schema(),
            )
        except (ConnectionRefusedError, Exception) as exc:
            # ConnectionRefusedError: Ollama not running
            raise LLMError(f"Ollama call failed (is Ollama running at OLLAMA_HOST?): {exc}") from exc

        raw = str(response)

        try:
            parsed = _DiagnosisOutput.model_validate_json(response.message.content)
        except Exception as exc:
            raise ParseError(f"Ollama response failed Pydantic validation: {exc}") from exc

        return (
            DiagnosisResult(
                verdict=parsed.verdict,
                severity=parsed.severity,
                affected_field=parsed.affected_field,
                fix=parsed.fix,
            ),
            raw,
        )

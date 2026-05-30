# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Anthropic provider for Diagnosticer — uses AsyncAnthropic with forced tool use.

IMPORTANT: Uses anthropic.AsyncAnthropic (async), NOT anthropic.Anthropic (sync).
Calling the sync client from an async FastAPI handler blocks the event loop.

Structured output via tool_choice={"type": "tool", "name": "record_diagnosis"}.
The model is guaranteed to emit a tool_use block (may be preceded by a text block —
iterate content, don't assume content[0] is the tool call).
"""

from __future__ import annotations

import anthropic

from xeter.services.diagnosticer.providers.base import (
    DiagnosisResult,
    LLMError,
    ParseError,
)

_DIAGNOSIS_TOOL = {
    "name": "record_diagnosis",
    "description": (
        "Record the root-cause diagnosis for a failing tool call span. "
        "Choose the verdict that best explains the root cause, estimate severity, "
        "identify the affected field, and provide a specific actionable fix."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["model", "architecture", "prompt", "unknown"],
                "description": (
                    "Root cause: 'model' = LLM capability/knowledge issue, "
                    "'architecture' = system design/tool schema issue, "
                    "'prompt' = instruction clarity/context issue, "
                    "'unknown' = insufficient signal"
                ),
            },
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Impact severity of this failure on the agent's task.",
            },
            "affected_field": {
                "type": "string",
                "description": (
                    "The specific span field most implicated "
                    "(e.g., tool_arguments, tool_name, prompt_text, response_text)."
                ),
            },
            "fix": {
                "type": "string",
                "description": "Concrete recommended action to resolve this issue.",
            },
        },
        "required": ["verdict", "severity", "affected_field", "fix"],
    },
}


class AnthropicProvider:
    """Calls Anthropic API with forced tool use for structured diagnosis output."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env

    async def diagnose(self, context: str) -> tuple[DiagnosisResult, str]:
        """Run diagnosis using Anthropic tool_choice forced tool call.

        Raises:
            LLMError: On API or network failure.
            ParseError: If no tool_use block found in response.
        """
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=[_DIAGNOSIS_TOOL],
                tool_choice={"type": "tool", "name": "record_diagnosis"},
                messages=[{"role": "user", "content": context}],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Anthropic call failed: {exc}") from exc

        raw = response.model_dump_json()

        # Iterate content — text blocks may appear before tool_use block
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_diagnosis":
                data = block.input
                try:
                    return (
                        DiagnosisResult(
                            verdict=data["verdict"],
                            severity=data["severity"],
                            affected_field=data["affected_field"],
                            fix=data["fix"],
                        ),
                        raw,
                    )
                except KeyError as exc:
                    raise ParseError(f"Missing field in Anthropic tool input: {exc}") from exc

        raise ParseError("No record_diagnosis tool_use block found in Anthropic response")

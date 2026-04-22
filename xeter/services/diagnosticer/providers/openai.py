"""
OpenAI provider for Diagnosticer — uses AsyncOpenAI with function calling strict=True.

IMPORTANT: Uses openai.AsyncOpenAI (async), NOT openai.OpenAI (sync).
Use parallel_tool_calls=False (required for strict mode with a single tool).

Structured output via tools + tool_choice with strict=True in function definition.
The legacy `functions` parameter is deprecated — use `tools` array.
"""

from __future__ import annotations

import json

import openai

from xeter.services.diagnosticer.providers.base import (
    DiagnosisResult,
    LLMError,
    ParseError,
)

_OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "record_diagnosis",
        "description": (
            "Record the root-cause diagnosis for a failing tool call span. "
            "Choose the verdict that best explains the root cause, estimate severity, "
            "identify the affected field, and provide a specific actionable fix."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["model", "architecture", "prompt", "undetermined"],
                    "description": (
                        "Root cause: 'model' = LLM capability/knowledge issue, "
                        "'architecture' = system design/tool schema issue, "
                        "'prompt' = instruction clarity/context issue, "
                        "'undetermined' = insufficient signal"
                    ),
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "affected_field": {
                    "type": "string",
                    "description": "The specific span field most implicated.",
                },
                "fix": {
                    "type": "string",
                    "description": "Concrete recommended action to resolve this issue.",
                },
            },
            "required": ["verdict", "severity", "affected_field", "fix"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


class OpenAIProvider:
    """Calls OpenAI API with function calling strict=True for structured output."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._client = openai.AsyncOpenAI()  # reads OPENAI_API_KEY from env

    async def diagnose(self, context: str) -> tuple[DiagnosisResult, str]:
        """Run diagnosis using OpenAI function calling with strict mode.

        Raises:
            LLMError: On API or network failure.
            ParseError: If no tool call found or JSON parse fails.
        """
        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": context}],
                tools=[_OPENAI_TOOL],
                tool_choice={"type": "function", "name": "record_diagnosis"},
                parallel_tool_calls=False,  # required for strict mode
            )
        except openai.APIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"OpenAI call failed: {exc}") from exc

        raw = completion.model_dump_json()
        tool_calls = completion.choices[0].message.tool_calls

        if not tool_calls:
            raise ParseError("No tool_calls in OpenAI response")

        try:
            data = json.loads(tool_calls[0].function.arguments)
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ParseError(f"Failed to parse OpenAI function arguments: {exc}") from exc

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
            raise ParseError(f"Missing field in OpenAI function arguments: {exc}") from exc

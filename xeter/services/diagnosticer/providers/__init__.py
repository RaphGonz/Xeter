# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
LLM provider factory for the Diagnosticer service.

Reads DIAGNOSTICER_PROVIDER and DIAGNOSTICER_MODEL from env vars and returns
the appropriate concrete provider implementation.

Usage:
    from xeter.services.diagnosticer.providers import get_llm_client
    provider = get_llm_client()
    result, raw = await provider.diagnose(context_string)
"""

from __future__ import annotations

import os

from xeter.services.diagnosticer.providers.base import LLMProvider


def get_llm_client() -> LLMProvider:
    """Factory: returns the LLMProvider for the configured DIAGNOSTICER_PROVIDER.

    Reads:
        DIAGNOSTICER_PROVIDER: "anthropic" (default) | "openai" | "ollama"
        DIAGNOSTICER_MODEL: model name string
            Defaults: anthropic -> "claude-haiku-4-5",
                      openai   -> "gpt-4o-mini",
                      ollama   -> "llama3.2"

    Providers are imported lazily — only the selected provider's SDK is imported.
    This avoids import errors when a provider's SDK is not installed.

    Raises:
        ValueError: If DIAGNOSTICER_PROVIDER is set to an unsupported value.
    """
    provider = os.environ.get("DIAGNOSTICER_PROVIDER", "anthropic").lower().strip()  # [safe-default]
    defaults = {
        "anthropic": "claude-haiku-4-5",
        "openai": "gpt-4o-mini",
        "ollama": "llama3.2",
    }
    model = os.environ.get("DIAGNOSTICER_MODEL", defaults.get(provider, ""))  # [safe-default]

    if provider == "anthropic":
        from xeter.services.diagnosticer.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=model)
    elif provider == "openai":
        from xeter.services.diagnosticer.providers.openai import OpenAIProvider
        return OpenAIProvider(model=model)
    elif provider == "ollama":
        from xeter.services.diagnosticer.providers.ollama import OllamaProvider
        return OllamaProvider(model=model)
    else:
        raise ValueError(
            f"Unknown DIAGNOSTICER_PROVIDER: {provider!r}. "
            f"Supported values: anthropic, openai, ollama"
        )

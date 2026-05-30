# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""xeter-sdk decorator — @xeter.trace captures all span fields and fires them to
the Analyser in a background daemon thread (fire-and-forget, zero added latency).

Fields `response` and `raw_response` are NOT captured by the decorator because
they are agent-provided values not available at decoration time. They are sent as
null. Agents needing response capture can post-process spans or extend this
decorator in a subclass / wrapper.
"""

import inspect
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any

import httpx

logger = logging.getLogger("xeter_sdk")

SCHEMA_VERSION = "1.0"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _send(endpoint: str, api_key: str, span: dict) -> None:
    """Send span to Analyser. Called from a daemon thread — never re-raises."""
    try:
        httpx.post(
            f"{endpoint}/v1/spans",
            json=span,
            headers={"x-api-key": api_key},
            timeout=5.0,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("xeter: failed to send span: %s", exc)


def trace(
    *,
    agent_name: str,
    agent_model: str,
    tool_name: str | None = None,
    tool_description: str | None = None,
    prompt_arg: str | None = None,
    tools_arg: str | None = None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    expected_output_schema: dict | None = None,
) -> Any:
    """Decorator factory.  All parameters are keyword-only.

    Usage::

        import xeter_sdk as xeter

        @xeter.trace(
            agent_name="my-agent",
            agent_model="gpt-4o",
            tool_name="search",
            prompt_arg="prompt",
            tools_arg="tools",
        )
        def call_search(prompt: str, tools: list) -> str:
            ...
    """

    def decorator(fn):  # noqa: ANN001
        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                endpoint = os.environ.get("XETER_ENDPOINT")
                api_key = os.environ.get("XETER_API_KEY")

                time_begin = _iso_now()
                result = await fn(*args, **kwargs)
                time_end = _iso_now()

                if not endpoint or not api_key:
                    return result

                _dispatch(endpoint, api_key, kwargs, result, time_begin, time_end)
                return result

            return async_wrapper

        else:

            @wraps(fn)
            def sync_wrapper(*args, **kwargs):
                endpoint = os.environ.get("XETER_ENDPOINT")
                api_key = os.environ.get("XETER_API_KEY")

                time_begin = _iso_now()
                result = fn(*args, **kwargs)
                time_end = _iso_now()

                if not endpoint or not api_key:
                    return result

                _dispatch(endpoint, api_key, kwargs, result, time_begin, time_end)
                return result

            return sync_wrapper

    def _dispatch(
        endpoint: str,
        api_key: str,
        kwargs: dict,
        result: Any,
        time_begin: str,
        time_end: str,
    ) -> None:
        # Extract mapped fields from kwargs
        prompt = kwargs.get(prompt_arg) if prompt_arg else None
        available_tools_ref = kwargs.get(tools_arg) if tools_arg else None

        # tool_arguments = all kwargs except the mapped prompt/tools keys
        excluded = set()
        if prompt_arg:
            excluded.add(prompt_arg)
        if tools_arg:
            excluded.add(tools_arg)
        tool_args_dict = {k: v for k, v in kwargs.items() if k not in excluded}
        tool_arguments = json.dumps(tool_args_dict)

        tool_output = result if isinstance(result, str) else str(result)

        expected_output_schema_str = json.dumps(expected_output_schema) if expected_output_schema is not None else None

        span: dict = {
            "span_id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "parent_span_id": parent_span_id,
            "agent_name": agent_name,
            "agent_model": agent_model,
            "tool_name": tool_name,
            "tool_description": tool_description,
            "tool_arguments": tool_arguments,
            "expected_output_schema": expected_output_schema_str,
            "tool_output": tool_output,
            "prompt": prompt,
            "response": None,
            "raw_response": None,
            "available_tools_ref": available_tools_ref,
            "time_begin": time_begin,
            "time_end": time_end,
            "xeter.schema.version": SCHEMA_VERSION,
        }

        t = threading.Thread(target=_send, args=(endpoint, api_key, span), daemon=True)
        t.start()

    return decorator

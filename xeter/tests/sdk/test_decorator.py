# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Unit tests for xeter_sdk.decorator — 8 test cases covering core behaviour."""

import asyncio
import threading
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

import xeter_sdk as xeter
from xeter_sdk.decorator import _send


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_decorator(**kw):
    """Return a @xeter.trace(...) decorator with sensible defaults."""
    defaults = dict(
        agent_name="test-agent",
        agent_model="gpt-4o-mini",
        tool_name="test-tool",
    )
    defaults.update(kw)
    return xeter.trace(**defaults)


# ---------------------------------------------------------------------------
# Test 1 — sync function returns its value unchanged
# ---------------------------------------------------------------------------

def test_sync_function_returns_normally():
    @_make_decorator()
    def greet(name: str) -> str:
        return f"hello {name}"

    result = greet(name="world")
    assert result == "hello world"


# ---------------------------------------------------------------------------
# Test 2 — async function returns its value unchanged
# ---------------------------------------------------------------------------

def test_async_function_returns_normally():
    @_make_decorator()
    async def greet_async(name: str) -> str:
        return f"async hello {name}"

    result = asyncio.run(greet_async(name="world"))
    assert result == "async hello world"


# ---------------------------------------------------------------------------
# Test 3 — no send when env vars are missing
# ---------------------------------------------------------------------------

def test_no_send_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("XETER_ENDPOINT", raising=False)
    monkeypatch.delenv("XETER_API_KEY", raising=False)

    with patch("threading.Thread") as mock_thread:
        @_make_decorator()
        def fn() -> str:
            return "ok"

        result = fn()

    assert result == "ok"
    mock_thread.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — all required span fields are sent
# ---------------------------------------------------------------------------

def test_span_fields_sent(monkeypatch):
    monkeypatch.setenv("XETER_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("XETER_API_KEY", "test-key-123")

    captured_span = {}

    def fake_thread_init(target, args, daemon):
        # Call target synchronously so we can inspect the span
        endpoint, api_key, span = args
        captured_span.update(span)
        return MagicMock()

    with patch("threading.Thread", side_effect=fake_thread_init) as mock_thread:
        @_make_decorator()
        def fn() -> str:
            return "output-value"

        fn()

    mock_thread.assert_called_once()

    required_fields = [
        "span_id", "trace_id", "parent_span_id",
        "agent_name", "agent_model",
        "tool_name", "tool_description",
        "tool_arguments", "tool_output",
        "prompt", "response", "raw_response",
        "available_tools_ref",
        "time_begin", "time_end",
        "xeter.schema.version",
    ]
    for field in required_fields:
        assert field in captured_span, f"Missing field: {field}"

    assert captured_span["xeter.schema.version"] == "1.0"
    # span_id must be a valid UUID string
    uuid.UUID(captured_span["span_id"])
    # time fields must be non-empty strings
    assert isinstance(captured_span["time_begin"], str) and captured_span["time_begin"]
    assert isinstance(captured_span["time_end"], str) and captured_span["time_end"]


# ---------------------------------------------------------------------------
# Test 5 — send failure does not raise, function still returns normally
# ---------------------------------------------------------------------------

def test_send_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("XETER_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("XETER_API_KEY", "test-key")

    import httpx as _httpx

    def fake_thread_init(target, args, daemon):
        # Run synchronously with a patched httpx.post that raises
        with patch("httpx.post", side_effect=_httpx.ConnectError("refused")):
            target(*args)
        return MagicMock()

    with patch("threading.Thread", side_effect=fake_thread_init):
        @_make_decorator()
        def fn() -> str:
            return "result"

        result = fn()

    assert result == "result"


# ---------------------------------------------------------------------------
# Test 6 — prompt_arg mapping
# ---------------------------------------------------------------------------

def test_prompt_arg_mapping(monkeypatch):
    monkeypatch.setenv("XETER_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("XETER_API_KEY", "key")

    captured = {}

    def fake_thread_init(target, args, daemon):
        _, _, span = args
        captured.update(span)
        return MagicMock()

    with patch("threading.Thread", side_effect=fake_thread_init):
        @xeter.trace(
            agent_name="agent",
            agent_model="model",
            prompt_arg="prompt",
        )
        def fn(prompt: str) -> str:
            return "resp"

        fn(prompt="hello world")

    assert captured.get("prompt") == "hello world"


# ---------------------------------------------------------------------------
# Test 7 — tools_arg mapping
# ---------------------------------------------------------------------------

def test_tools_arg_mapping(monkeypatch):
    monkeypatch.setenv("XETER_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("XETER_API_KEY", "key")

    captured = {}

    def fake_thread_init(target, args, daemon):
        _, _, span = args
        captured.update(span)
        return MagicMock()

    with patch("threading.Thread", side_effect=fake_thread_init):
        @xeter.trace(
            agent_name="agent",
            agent_model="model",
            tools_arg="tools",
        )
        def fn(tools: list) -> str:
            return "resp"

        fn(tools=["tool1", "tool2"])

    assert captured.get("available_tools_ref") == ["tool1", "tool2"]


# ---------------------------------------------------------------------------
# Test 8 — fire-and-forget: function returns before background thread finishes
# ---------------------------------------------------------------------------

def test_fire_and_forget_timing(monkeypatch):
    monkeypatch.setenv("XETER_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("XETER_API_KEY", "key")

    send_started = threading.Event()
    send_may_finish = threading.Event()
    real_threads = []

    # Capture real Thread constructor before the patch replaces it
    RealThread = threading.Thread

    def fake_thread_init(target, args, daemon):
        # Start a real daemon thread that signals when the "send" begins.
        # We wrap target so we can inject delay without touching the SDK source.
        def slow_target(*a):
            send_started.set()
            send_may_finish.wait(timeout=5)

        t = RealThread(target=slow_target, args=args, daemon=True)
        real_threads.append(t)

        # Return a mock whose .start() starts our real thread
        m = MagicMock()
        m.start.side_effect = t.start
        return m

    with patch("threading.Thread", side_effect=fake_thread_init):
        @_make_decorator()
        def fn() -> str:
            return "done"

        t_start = time.monotonic()
        result = fn()
        t_end = time.monotonic()

    # Function must have returned with the correct value
    assert result == "done"

    # Background thread must have started (with brief grace period for scheduling)
    send_started.wait(timeout=1.0)
    assert send_started.is_set(), "Background thread never started"

    # Function must have returned before the send completed (fire-and-forget)
    assert (t_end - t_start) < 1.0, "Function took too long — may be blocking on send"

    # Let the thread finish cleanly
    send_may_finish.set()
    for t in real_threads:
        t.join(timeout=2.0)

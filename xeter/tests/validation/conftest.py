# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Pytest fixtures for validation (integration) tests.

These fixtures require the full Docker stack to be running.
Set VALIDATION_STACK=1 to enable.

Usage:
    VALIDATION_STACK=1 pytest xeter/tests/validation/ -v
"""

from __future__ import annotations

import json
import time
import uuid
from typing import NamedTuple

import httpx
import pytest

ANALYSER_URL = "http://localhost:4318"
PRESENTER_URL = "http://localhost:8000"

_AVAILABLE_TOOLS = [
    {
        "name": "search_documents",
        "description": "Search through financial documents by keyword or date range.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "extract_tables",
        "description": "Extract structured tables from a PDF document page.",
        "parameters": {
            "type": "object",
            "properties": {"page_number": {"type": "integer"}},
            "required": ["page_number"],
        },
    },
]


class TwoTenantStack(NamedTuple):
    """Return value from the two_tenant_stack fixture."""

    token_a: str
    token_b: str
    tenant_id_a: str
    tenant_id_b: str
    span_id_a: str
    span_id_b: str
    api_key_a: str
    api_key_b: str


def _register_and_login(client: httpx.Client, name_prefix: str) -> dict:
    """Register a tenant and log in, returning {tenant_id, api_key, token}."""
    suffix = uuid.uuid4().hex[:8]
    name = f"{name_prefix}-{suffix}"
    email = f"{name_prefix}-{suffix}@xeter-isolation.test"
    password = f"Isolation{suffix}!"

    reg_resp = client.post(
        f"{PRESENTER_URL}/register",
        json={"tenant_name": name, "email": email, "password": password},
    )
    assert reg_resp.status_code == 200, (
        f"Register failed: {reg_resp.status_code} — {reg_resp.text}"
    )
    reg_data = reg_resp.json()
    tenant_id = reg_data["tenant_id"]
    api_key = reg_data["api_key"]

    login_resp = client.post(
        f"{PRESENTER_URL}/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, (
        f"Login failed: {login_resp.status_code} — {login_resp.text}"
    )
    token = login_resp.json()["session_token"]

    return {"tenant_id": tenant_id, "api_key": api_key, "token": token}


def _emit_span(client: httpx.Client, api_key: str, span_id: str) -> None:
    """Emit a single span to the analyser on behalf of the given tenant."""
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "span_id": span_id,
        "trace_id": str(uuid.uuid4()),
        "agent_name": "isolation-test-agent",
        "agent_model": "gpt-4o",
        "tool_name": "search_documents",
        "tool_description": "Search through financial documents by keyword or date range.",
        "tool_arguments": json.dumps({"query": "isolation test"}),
        "prompt": "Isolation test span — please ignore.",
        "response": "Isolation test response.",
        "available_tools": json.dumps(_AVAILABLE_TOOLS),
        "time_begin": now_iso,
        "time_end": now_iso,
        "xeter.schema.version": "1.0",
    }
    resp = client.post(
        f"{ANALYSER_URL}/v1/spans",
        json=payload,
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code in (200, 201, 202), (
        f"Emit span failed: {resp.status_code} — {resp.text}"
    )


@pytest.fixture(scope="module")
def two_tenant_stack() -> TwoTenantStack:
    """Module-scoped fixture that creates two tenants, emits one span each.

    Sets up:
      - Tenant A: registered, logged in, span_id_a emitted
      - Tenant B: registered, logged in, span_id_b emitted
    Waits 3 seconds for ingestion to complete (batcher flush).

    Returns TwoTenantStack with tokens, tenant_ids, span_ids, and api_keys.
    """
    with httpx.Client(timeout=30) as client:
        tenant_a = _register_and_login(client, "isolation-tenant-a")
        tenant_b = _register_and_login(client, "isolation-tenant-b")

        span_id_a = str(uuid.uuid4())
        span_id_b = str(uuid.uuid4())

        _emit_span(client, tenant_a["api_key"], span_id_a)
        _emit_span(client, tenant_b["api_key"], span_id_b)

    # Wait for batcher to flush spans to ClickHouse + worker to enqueue
    time.sleep(3)

    return TwoTenantStack(
        token_a=tenant_a["token"],
        token_b=tenant_b["token"],
        tenant_id_a=tenant_a["tenant_id"],
        tenant_id_b=tenant_b["tenant_id"],
        span_id_a=span_id_a,
        span_id_b=span_id_b,
        api_key_a=tenant_a["api_key"],
        api_key_b=tenant_b["api_key"],
    )

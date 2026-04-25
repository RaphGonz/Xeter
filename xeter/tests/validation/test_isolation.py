"""
Cross-tenant isolation integration tests.

Verifies that Tenant A cannot retrieve Tenant B's data through any
Presenter endpoint, and vice versa. Also verifies that span_scores
(which has no RLS) are inaccessible across tenants because the span
detail endpoint filters by tenant_id before fetching scores.

Requires the full Docker stack (docker compose up):
    VALIDATION_STACK=1 pytest xeter/tests/validation/ -v

All tests use the two_tenant_stack fixture from conftest.py which
registers two tenants, emits one span per tenant, and waits for ingestion.
"""

from __future__ import annotations

import os

import httpx
import pytest

from xeter.tests.validation.conftest import PRESENTER_URL, TwoTenantStack

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not os.environ.get("VALIDATION_STACK"),
    reason="Requires running Docker stack (set VALIDATION_STACK=1)",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_spans(token: str) -> httpx.Response:
    """GET /spans with the given JWT token."""
    with httpx.Client(timeout=60) as client:
        return client.get(
            f"{PRESENTER_URL}/spans",
            headers={"Authorization": f"Bearer {token}"},
        )


def _get_span_detail(token: str, span_id: str) -> httpx.Response:
    """GET /spans/{span_id} with the given JWT token."""
    with httpx.Client(timeout=60) as client:
        return client.get(
            f"{PRESENTER_URL}/spans/{span_id}",
            headers={"Authorization": f"Bearer {token}"},
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_spans_list_returns_only_own_tenant(two_tenant_stack: TwoTenantStack) -> None:
    """GET /spans with token_a must include span_id_a and exclude span_id_b."""
    resp = _get_spans(two_tenant_stack.token_a)
    assert resp.status_code == 200, (
        f"Expected 200 from GET /spans with token_a, got {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    span_ids = {s["span_id"] for s in data.get("spans", [])}

    assert two_tenant_stack.span_id_a in span_ids, (
        f"Tenant A's own span {two_tenant_stack.span_id_a} was not found in GET /spans response. "
        f"Got span_ids: {span_ids}"
    )
    assert two_tenant_stack.span_id_b not in span_ids, (
        f"ISOLATION FAILURE: Tenant B's span {two_tenant_stack.span_id_b} appeared in "
        f"Tenant A's GET /spans response. Cross-tenant data leak detected."
    )


def test_cross_tenant_span_detail_returns_404(two_tenant_stack: TwoTenantStack) -> None:
    """GET /spans/{span_id_b} with token_a must return 404.

    Per design decision [Phase 04-02]: cross-tenant span access returns 404 (not 403)
    because the ClickHouse query filters by tenant_id — the span is simply "not found"
    from Tenant A's perspective. This avoids information leakage about span existence.
    """
    resp = _get_span_detail(two_tenant_stack.token_a, two_tenant_stack.span_id_b)
    assert resp.status_code == 404, (
        f"Expected 404 when Tenant A accesses Tenant B's span {two_tenant_stack.span_id_b}, "
        f"got {resp.status_code}. "
        f"Response: {resp.text[:200]}"
    )


def test_spans_list_tenant_b_sees_only_own(two_tenant_stack: TwoTenantStack) -> None:
    """GET /spans with token_b must include span_id_b and exclude span_id_a."""
    resp = _get_spans(two_tenant_stack.token_b)
    assert resp.status_code == 200, (
        f"Expected 200 from GET /spans with token_b, got {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    span_ids = {s["span_id"] for s in data.get("spans", [])}

    assert two_tenant_stack.span_id_b in span_ids, (
        f"Tenant B's own span {two_tenant_stack.span_id_b} was not found in GET /spans response. "
        f"Got span_ids: {span_ids}"
    )
    assert two_tenant_stack.span_id_a not in span_ids, (
        f"ISOLATION FAILURE: Tenant A's span {two_tenant_stack.span_id_a} appeared in "
        f"Tenant B's GET /spans response. Cross-tenant data leak detected."
    )


def test_span_detail_includes_correct_tenant_id(two_tenant_stack: TwoTenantStack) -> None:
    """GET /spans/{span_id_a} with token_a must include the correct tenant_id.

    Verifies that the returned detail carries Tenant A's tenant_id, not a
    default/null/cross-tenant value. This catches cases where data is returned
    but with the wrong tenant context.
    """
    resp = _get_span_detail(two_tenant_stack.token_a, two_tenant_stack.span_id_a)
    assert resp.status_code == 200, (
        f"Expected 200 from GET /spans/{two_tenant_stack.span_id_a} with token_a, "
        f"got {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    returned_tenant_id = data.get("tenant_id")
    assert returned_tenant_id == two_tenant_stack.tenant_id_a, (
        f"Span detail tenant_id mismatch: expected {two_tenant_stack.tenant_id_a!r}, "
        f"got {returned_tenant_id!r}. Full response: {data}"
    )


def test_span_scores_isolation(two_tenant_stack: TwoTenantStack) -> None:
    """Verify span_scores isolation via the span detail endpoint.

    span_scores has NO row-level security (documented CRITICAL in score_writer.py).
    Isolation is enforced by the span detail endpoint: it first fetches the span
    from ClickHouse filtered by tenant_id, and only fetches scores for spans the
    tenant owns. Cross-tenant span access returns 404, making scores inaccessible.

    Test:
      1. GET /spans/{span_id_a} with token_a — expect 200 (own span, scores may be present)
      2. GET /spans/{span_id_b} with token_a — expect 404 (Tenant B's span, scores blocked)
    """
    # Step 1: Tenant A can access their own span detail (scores accessible via span endpoint)
    resp_own = _get_span_detail(two_tenant_stack.token_a, two_tenant_stack.span_id_a)
    assert resp_own.status_code == 200, (
        f"Expected 200 for Tenant A's own span detail, got {resp_own.status_code}: {resp_own.text}"
    )

    # Step 2: Tenant A cannot access Tenant B's span (and therefore cannot see their scores)
    resp_cross = _get_span_detail(two_tenant_stack.token_a, two_tenant_stack.span_id_b)
    assert resp_cross.status_code == 404, (
        f"ISOLATION FAILURE: Expected 404 when Tenant A accesses Tenant B's span "
        f"{two_tenant_stack.span_id_b} (which would expose span_scores). "
        f"Got {resp_cross.status_code}: {resp_cross.text[:200]}"
    )

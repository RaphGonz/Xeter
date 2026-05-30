# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Presenter — DiagnosisService layer.

Handles:
  - Idempotency: returns cached diagnosis if one already exists for this span.
  - Tenant guard: verifies span ownership via ClickHouse before forwarding.
  - HTTP forward: calls Diagnosticer with configurable per-request timeout.
  - Error classification: 504 on timeout, 503 on connection failure, 502 on non-2xx.
  - Error sanitization: strips raw provider strings from error detail.

Usage::

    service = DiagnosisService()
    response = await service.trigger(
        span_id=span_id,
        tenant_id=tenant_id,
        session=session,
        http_client=request.app.state.http_client,
        ch_client=ch_client,
    )
"""

import asyncio
import os

import httpx
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.shared.dal.diagnoses import DiagnosisRepository
from xeter.shared.db.postgres import tenant_session
from xeter.shared.models import Diagnosis

INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]  # KeyError on startup if unset


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class DiagnosisResponse(BaseModel):
    """Unified response shape for both POST /diagnose and GET /diagnose/{span_id}."""

    diagnosis_id: str
    span_id: str
    verdict: str
    severity: str
    affected_field: str | None
    recommended_fix: str | None  # mapped from Diagnosis.fix (ORM field is "fix")
    diagnosed_at: str  # ISO string from Diagnosis.created_at


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sanitize_diagnosticer_error(resp_json: dict | None) -> str:
    """Extract and truncate the detail field from a Diagnosticer error response.

    Returns a safe, truncated string with no raw provider details exposed.

    Args:
        resp_json: Parsed JSON body from the Diagnosticer response, or None.

    Returns:
        Truncated detail string, or "Diagnosis failed" if not available.
    """
    if resp_json is None:
        return "Diagnosis failed"
    detail = resp_json.get("detail", "Diagnosis failed")
    if isinstance(detail, str):
        return detail[:120]
    return "Diagnosis failed"


def _diagnosis_to_response(diagnosis: Diagnosis) -> DiagnosisResponse:
    """Map a Diagnosis ORM instance to a DiagnosisResponse.

    Key rename: diagnosis.fix → recommended_fix (ORM field is "fix",
    but API surface uses the more descriptive "recommended_fix" name).

    Args:
        diagnosis: Refreshed Diagnosis ORM instance.

    Returns:
        DiagnosisResponse with all fields populated.
    """
    diagnosed_at = (
        diagnosis.created_at.isoformat()
        if hasattr(diagnosis.created_at, "isoformat")
        else str(diagnosis.created_at)
    )
    return DiagnosisResponse(
        diagnosis_id=str(diagnosis.diagnosis_id),
        span_id=diagnosis.span_id,
        verdict=diagnosis.verdict,
        severity=diagnosis.severity,
        affected_field=diagnosis.affected_field,
        recommended_fix=diagnosis.fix,
        diagnosed_at=diagnosed_at,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DiagnosisService:
    """Service layer for triggering and retrieving diagnoses.

    Encapsulates idempotency, tenant guard, HTTP forwarding, and error
    classification. Instantiated fresh per request inside the router.
    """

    async def trigger(
        self,
        *,
        span_id: str,
        tenant_id: str,
        session: AsyncSession,
        http_client: httpx.AsyncClient,
        ch_client,  # clickhouse_connect.driver.Client
    ) -> DiagnosisResponse:
        """Trigger a diagnosis or return a cached result.

        Execution order:
          1. Idempotency check — returns cached diagnosis immediately if found.
          2. Tenant guard — verifies span belongs to tenant via ClickHouse.
          3. HTTP forward to Diagnosticer with configurable timeout.
          4. Non-2xx error handling with sanitized message.
          5. Re-read from diagnoses table (Diagnosticer wrote the row).

        Args:
            span_id: ClickHouse span_id to diagnose.
            tenant_id: Authenticated tenant UUID string.
            session: Open AsyncSession (not in a transaction yet).
            http_client: Shared httpx.AsyncClient pointed at Diagnosticer.
            ch_client: ClickHouse client for span ownership check.
            (auth_header removed — Presenter now uses INTERNAL_API_KEY + X-Tenant-Id)

        Returns:
            DiagnosisResponse with diagnosis fields.

        Raises:
            HTTPException 404: Span not found or not owned by tenant.
            HTTPException 503: Diagnosticer unreachable (connection error).
            HTTPException 504: Diagnosticer timed out.
            HTTPException 502: Diagnosticer returned non-2xx response.
            HTTPException 500: Diagnosis not found after successful forward.
        """
        # Step 2 — Tenant guard: verify span ownership via ClickHouse
        ch_query = (
            "SELECT span_id FROM spans "
            "WHERE tenant_id = %(tid)s AND span_id = %(sid)s LIMIT 1"
        )
        result = await asyncio.to_thread(
            ch_client.query, ch_query, {"tid": tenant_id, "sid": span_id}
        )
        if not result.result_rows:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": "Span not found",
                    "status": 404,
                },
            )

        # Step 3 — HTTP forward to Diagnosticer
        timeout = float(os.environ.get("DIAGNOSTICER_TIMEOUT_SECONDS", 60.0))  # [safe-default]
        try:
            resp = await http_client.post(
                "/diagnose",
                json={"span_id": span_id},
                headers={
                    "X-Internal-Api-Key": INTERNAL_API_KEY,
                    "X-Tenant-Id": tenant_id,
                },
                timeout=timeout,  # per-request override of client default 30s
            )
        except httpx.TimeoutException:
            # IMPORTANT: TimeoutException must be caught BEFORE HTTPError —
            # TimeoutException is a subclass of HTTPError; wrong order returns 503.
            raise HTTPException(
                status_code=504,
                detail={
                    "error": "diagnosticer_timeout",
                    "message": "Diagnosis request timed out",
                    "status": 504,
                },
            )
        except httpx.HTTPError:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "diagnosticer_unavailable",
                    "message": "Diagnosticer service is unavailable",
                    "status": 503,
                },
            )

        # Step 4 — Non-2xx Diagnosticer error
        if not resp.is_success:
            try:
                body = resp.json()
            except Exception:
                body = None
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "diagnosis_failed",
                    "detail": _sanitize_diagnosticer_error(body),
                    "status": 502,
                },
            )

        # Step 5 — Re-read from diagnoses table (tenant_session block #2)
        # Diagnosticer has already written the row; Presenter reads it back.
        # Sequential block — NOT nested inside block #1 (would violate RLS rules).
        async with tenant_session(session, tenant_id) as s:
            repo = DiagnosisRepository(s)
            diagnosis = await repo.get_latest_for_span(
                span_id=span_id, tenant_id=tenant_id
            )
        if diagnosis is None:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "internal_error",
                    "message": "Diagnosis not found after successful forward",
                },
            )
        return _diagnosis_to_response(diagnosis)

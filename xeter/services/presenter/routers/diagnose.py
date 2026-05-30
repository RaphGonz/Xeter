# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Presenter — POST /diagnose and GET /diagnose/{span_id} routes.

POST /diagnose
  Trigger a diagnosis or return a cached one.
  Checks idempotency first — returns cached result if diagnosis already exists.
  Verifies span ownership before forwarding to Diagnosticer.
  Returns 404 if span not found, 503 if Diagnosticer unreachable, 504 on timeout.

GET /diagnose/{span_id}
  Return an existing diagnosis without triggering a new one.
  Returns 404 if no diagnosis exists — frontend polls this and calls POST to trigger.

Error responses:
  401 Unauthorized   — missing or invalid session token
  404 Not Found      — span not found or no diagnosis exists
  502 Bad Gateway    — Diagnosticer returned non-2xx
  503 Unavailable    — Diagnosticer unreachable (connection error)
  504 Timeout        — Diagnosticer did not respond within timeout
  500 Internal Error — unexpected failure after successful Diagnosticer forward
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.services.presenter.deps import get_ch_client, verify_session_token
from xeter.services.presenter.diagnosis_service import (
    DiagnosisResponse,
    DiagnosisService,
    _diagnosis_to_response,
)
from xeter.services.presenter.routers.auth import get_session
from xeter.shared.dal.diagnoses import DiagnosisRepository
from xeter.shared.db.postgres import tenant_session

router = APIRouter()


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class DiagnoseRequest(BaseModel):
    """Request body for POST /diagnose.

    NOTE: flags field removed — Diagnosticer only accepts {"span_id": str}.
    Old test test_diagnose_proxies_request_body asserted flags forwarding;
    that test will be replaced in Plan 02.
    """

    span_id: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/diagnose", response_model=DiagnosisResponse)
async def diagnose(
    body: DiagnoseRequest,
    request: Request,
    tenant_id: str = Depends(verify_session_token),
    session: AsyncSession = Depends(get_session),
    ch_client=Depends(get_ch_client),
) -> DiagnosisResponse:
    """Trigger or return cached diagnosis for a span.

    Checks idempotency first — returns cached result if diagnosis already exists.
    Verifies span ownership before forwarding to Diagnosticer.
    Returns 404 if span not found, 503 if Diagnosticer unreachable, 504 on timeout.
    """
    service = DiagnosisService()
    return await service.trigger(
        span_id=body.span_id,
        tenant_id=tenant_id,
        session=session,
        http_client=request.app.state.http_client,
        ch_client=ch_client,
    )


@router.get("/diagnose/{span_id}", response_model=DiagnosisResponse)
async def get_diagnosis(
    span_id: str,
    tenant_id: str = Depends(verify_session_token),
    session: AsyncSession = Depends(get_session),
) -> DiagnosisResponse:
    """Return an existing diagnosis for a span without triggering a new one.

    Returns 404 if no diagnosis exists — frontend uses this as the signal
    to call POST /diagnose to trigger diagnosis first.
    """
    async with tenant_session(session, tenant_id) as s:
        repo = DiagnosisRepository(s)
        diagnosis = await repo.get_latest_for_span(
            span_id=span_id, tenant_id=tenant_id
        )
    if diagnosis is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": "No diagnosis for this span",
                "status": 404,
            },
        )
    return _diagnosis_to_response(diagnosis)

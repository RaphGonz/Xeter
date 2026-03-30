"""
Presenter — POST /diagnose proxy route.

Proxies diagnose requests to the Diagnosticer service via HTTP.
Requires a valid session token (401 without one).
Returns the Diagnosticer response as-is (currently 501 scaffold).
Returns 502 if the Diagnosticer is unreachable.
"""

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from xeter.services.presenter.deps import verify_session_token

router = APIRouter()


class DiagnoseRequest(BaseModel):
    span_id: str
    flags: list


@router.post("/diagnose")
async def diagnose(
    body: DiagnoseRequest,
    request: Request,
    tenant_id: str = Depends(verify_session_token),
):
    """Proxy POST /diagnose to the Diagnosticer service.

    Requires:
      Authorization: Bearer <session_token>

    Returns the Diagnosticer's response directly (currently 501 scaffold).
    Returns 502 if the Diagnosticer service is unreachable.
    """
    try:
        resp = await request.app.state.http_client.post(
            "/diagnose",
            json=body.model_dump(),
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type="application/json",
        )
    except httpx.HTTPError:
        return JSONResponse(
            status_code=502,
            content={
                "error": "diagnosticer_unavailable",
                "message": "Diagnosticer service is unavailable",
            },
        )

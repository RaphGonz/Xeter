"""
Xeter Diagnosticer service — FastAPI application entry point.

Scaffold: All endpoints return 501 Not Implemented.
Wired now so Milestone 2 activates without rearchitecting.

Routes:
  GET  /healthz    — liveness probe
  POST /diagnose   — diagnose a span (scaffold: returns 501)
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Xeter Diagnosticer", version="0.1.0-scaffold")


class DiagnoseRequest(BaseModel):
    span_id: str
    flags: list


@app.get("/healthz")
async def healthz():
    """Liveness probe — returns ok if the process is alive."""
    return {"status": "ok"}


@app.post("/diagnose", status_code=501)
async def diagnose(body: DiagnoseRequest):
    """Diagnose a span — scaffold returning 501 until v2 LLM integration."""
    return JSONResponse(
        status_code=501,
        content={
            "status": "not_implemented",
            "message": "Diagnosticer not yet available",
            "span_id": body.span_id,
        },
    )

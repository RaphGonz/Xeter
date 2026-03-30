"""
Xeter Presenter service — FastAPI application entry point.

Routes:
  GET  /healthz       — liveness probe
  POST /register      — tenant registration (returns one-time API key)
  POST /login         — session login (returns JWT token)
  GET  /spans         — span list with flag summaries and scores (auth required)
  POST /diagnose      — proxy to Diagnosticer service (auth required)
"""

import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from xeter.services.presenter.routers import auth, diagnose, spans
from xeter.shared.db.clickhouse import get_clickhouse_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create ClickHouse client and httpx client on startup."""
    app.state.ch_client = get_clickhouse_client()
    app.state.http_client = httpx.AsyncClient(
        base_url=os.environ.get("DIAGNOSTICER_URL", "http://diagnosticer:8001"),
        timeout=30.0,
    )
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="Xeter Presenter", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router, prefix="", tags=["auth"])
app.include_router(spans.router, prefix="", tags=["spans"])
app.include_router(diagnose.router, prefix="", tags=["diagnose"])


@app.get("/healthz")
async def healthz():
    """Liveness probe — returns ok if the process is alive."""
    return {"status": "ok"}

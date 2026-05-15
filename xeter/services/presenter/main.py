"""
Xeter Presenter service — FastAPI application entry point.

Routes:
  GET  /healthz       — liveness probe
  POST /register      — tenant registration (returns one-time API key)
  POST /login         — session login (returns JWT token)
  GET  /spans         — span list with flag summaries and scores (auth required)
  POST /diagnose      — proxy to Diagnosticer service (auth required)
  GET  /traces        — trace list with span and flag counts (auth required)
  GET  /traces/{id}   — full trace detail with spans, flags, scores (auth required)
"""

import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from xeter.services.presenter.routers import auth, diagnose, spans, traces


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create httpx client on startup.

    ClickHouse clients are created per-request via the get_ch_client dependency
    to avoid concurrent-session errors when multiple requests arrive at once.
    """
    app.state.http_client = httpx.AsyncClient(
        base_url=os.environ.get("DIAGNOSTICER_URL", "http://diagnosticer:8001"),  # [safe-default] docker-compose value
        timeout=30.0,
    )
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="Xeter Presenter", version="0.1.0", lifespan=lifespan)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")  # [must-set-in-prod] must be 'production' in production
ALLOW_ORIGINS = os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")  # [must-set-in-prod] restrict to actual frontend origin

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,   # never "*" — explicit list always
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="", tags=["auth"])
app.include_router(spans.router, prefix="", tags=["spans"])
app.include_router(diagnose.router, prefix="", tags=["diagnose"])
app.include_router(traces.router, prefix="", tags=["traces"])


@app.get("/healthz")
async def healthz():
    """Liveness probe — returns ok if the process is alive."""
    return {"status": "ok"}

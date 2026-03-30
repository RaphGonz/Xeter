"""
Xeter Presenter service — FastAPI application entry point.

Routes:
  GET  /healthz       — liveness probe
  POST /register      — tenant registration (returns one-time API key)
  POST /login         — session login (returns JWT token)
  GET  /spans         — span list with flag summaries and scores (auth required)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from xeter.services.presenter.routers import auth, spans
from xeter.shared.db.clickhouse import get_clickhouse_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create ClickHouse client on startup."""
    app.state.ch_client = get_clickhouse_client()
    yield
    # No explicit cleanup needed — clickhouse_connect HTTP client is stateless


app = FastAPI(title="Xeter Presenter", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router, prefix="", tags=["auth"])
app.include_router(spans.router, prefix="", tags=["spans"])


@app.get("/healthz")
async def healthz():
    """Liveness probe — returns ok if the process is alive."""
    return {"status": "ok"}

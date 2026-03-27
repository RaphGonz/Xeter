"""
Xeter Presenter service — FastAPI application entry point.

Routes:
  GET  /healthz       — liveness probe
  POST /register      — tenant registration (returns one-time API key)
"""

from fastapi import FastAPI

from xeter.services.presenter.routers import auth

app = FastAPI(title="Xeter Presenter", version="0.1.0")

app.include_router(auth.router, prefix="", tags=["auth"])


@app.get("/healthz")
async def healthz():
    """Liveness probe — returns ok if the process is alive."""
    return {"status": "ok"}

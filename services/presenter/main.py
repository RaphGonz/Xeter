"""Presenter service stub — Phase 1 placeholder.

This is a minimal FastAPI application that satisfies the health check.
Real API endpoints (spans, flags, diagnostics, registration) are implemented in Plans 03 and 04.
"""

from fastapi import FastAPI

app = FastAPI(title="Xeter Presenter", version="0.1.0-stub")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

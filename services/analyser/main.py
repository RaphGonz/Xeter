"""Analyser service stub — Phase 1 placeholder.

This is a minimal FastAPI application that satisfies the health check.
Real ingestion logic is implemented in Phase 2.
"""

from fastapi import FastAPI

app = FastAPI(title="Xeter Analyser", version="0.1.0-stub")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

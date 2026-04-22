"""
Xeter Diagnosticer service — FastAPI application.

POST /diagnose — synchronous LLM root-cause analysis for a span.
  Assembles context from ClickHouse + PostgreSQL + S3,
  calls the configured LLM provider (DIAGNOSTICER_PROVIDER env var),
  stores the result in the diagnoses table, and returns the structured diagnosis.

  Fail-clean: on LLM failure, no DB row is written.

GET  /healthz — liveness probe.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import clickhouse_connect
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xeter.services.diagnosticer.context_assembly import assemble_context
from xeter.services.diagnosticer.providers import get_llm_client
from xeter.services.diagnosticer.providers.base import LLMError, ParseError
from xeter.shared.dal.diagnoses import DiagnosisRepository
from xeter.shared.db.clickhouse import get_clickhouse_client
from xeter.shared.db.postgres import get_async_engine, get_async_session_factory, tenant_session

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create session factory on startup."""
    engine = get_async_engine()
    app.state.session_factory = get_async_session_factory(engine)
    yield
    await engine.dispose()


app = FastAPI(title="Xeter Diagnosticer", version="0.2.0", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def verify_session_token(authorization: str | None = Header(default=None)) -> str:
    """Validate Authorization: Bearer <token> header. Returns tenant_id string."""
    _unauthorized = HTTPException(
        status_code=401,
        detail={"error": "unauthorized", "message": "Invalid or missing session token"},
    )
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        tenant_id: str | None = payload.get("sub")
        if not tenant_id:
            raise _unauthorized
        return tenant_id
    except JWTError:
        raise _unauthorized


def get_ch_client():
    """FastAPI dependency: fresh ClickHouse client per request (not safe for concurrent use)."""
    client = get_clickhouse_client()
    try:
        yield client
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class DiagnoseRequest(BaseModel):
    span_id: str


class DiagnoseResponse(BaseModel):
    diagnosis_id: str
    span_id: str
    trace_id: str
    verdict: str
    severity: str
    affected_field: str | None
    fix: str | None
    model_used: str
    provider_used: str
    created_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz():
    """Liveness probe — returns ok if the process is alive."""
    return {"status": "ok"}


@app.post("/diagnose", response_model=DiagnoseResponse)
async def diagnose(
    body: DiagnoseRequest,
    tenant_id: str = Depends(verify_session_token),
    ch_client: clickhouse_connect.driver.Client = Depends(get_ch_client),
):
    """Diagnose a span synchronously.

    Assembles context (ClickHouse span + PostgreSQL flags + S3 payloads),
    calls the configured LLM provider for structured root-cause analysis,
    stores the result in the diagnoses table, and returns the diagnosis.

    Fail-clean: if the LLM call or parse fails, no DB row is written.
    """
    provider_name = os.environ.get("DIAGNOSTICER_PROVIDER", "anthropic").lower().strip()
    model_name = os.environ.get(
        "DIAGNOSTICER_MODEL",
        {"anthropic": "claude-haiku-4-5", "openai": "gpt-4o-mini", "ollama": "llama3.2"}.get(
            provider_name, ""
        ),
    )

    engine = get_async_engine()
    session_factory: async_sessionmaker[AsyncSession] = get_async_session_factory(engine)

    async with session_factory() as session:
        # 1. Assemble context (span + flags + S3 payloads)
        try:
            context_string, trace_id = await assemble_context(
                span_id=body.span_id,
                tenant_id=tenant_id,
                session=session,
                ch_client=ch_client,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        # 2. Call LLM (fail-clean: no DB write until parse succeeds)
        try:
            llm_provider = get_llm_client()
            diagnosis_result, raw_response = await llm_provider.diagnose(context_string)
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc
        except ParseError as exc:
            raise HTTPException(status_code=422, detail=f"LLM response parse failed: {exc}") from exc

        # 3. Write to DB only after successful parse
        async with tenant_session(session, tenant_id) as s:
            repo = DiagnosisRepository(s)
            diagnosis = await repo.create(
                tenant_id=tenant_id,
                span_id=body.span_id,
                trace_id=trace_id,
                verdict=diagnosis_result.verdict,
                severity=diagnosis_result.severity,
                affected_field=diagnosis_result.affected_field,
                fix=diagnosis_result.fix,
                raw_llm_response=raw_response,
                model_used=model_name,
                provider_used=provider_name,
            )

    return DiagnoseResponse(
        diagnosis_id=str(diagnosis.diagnosis_id),
        span_id=diagnosis.span_id,
        trace_id=diagnosis.trace_id,
        verdict=diagnosis.verdict,
        severity=diagnosis.severity,
        affected_field=diagnosis.affected_field,
        fix=diagnosis.fix,
        model_used=diagnosis.model_used,
        provider_used=diagnosis.provider_used,
        created_at=str(diagnosis.created_at),
    )

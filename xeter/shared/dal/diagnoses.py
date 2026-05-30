# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
DiagnosisRepository — DAL for the `diagnoses` table.

All methods call require_tenant() as first line (MissingTenantError on None/empty).
Wrap all DAL calls in tenant_session() to set RLS app.current_tenant_id.

Usage:
    async with tenant_session(session, tenant_id) as s:
        repo = DiagnosisRepository(s)
        diagnosis = await repo.create(tenant_id=tenant_id, span_id=span_id, ...)
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.shared.dal.base import require_tenant
from xeter.shared.models import Diagnosis


class DiagnosisRepository:
    """Repository for LLM root-cause diagnoses."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: str | None,
        span_id: str,
        trace_id: str,
        verdict: str,
        severity: str,
        affected_field: str | None,
        fix: str | None,
        raw_llm_response: str | None,
        model_used: str,
        provider_used: str,
    ) -> Diagnosis:
        """Insert a new diagnosis row and return the refreshed ORM instance.

        Args:
            tenant_id: UUID string of the owning tenant. Must not be None/empty.
            span_id: ClickHouse span_id this diagnosis is for.
            trace_id: Trace that contains the span.
            verdict: One of model|architecture|prompt|undetermined.
            severity: One of low|medium|high|critical.
            affected_field: Span field most implicated (may be None if undetermined).
            fix: Recommended remediation action (may be None if undetermined).
            raw_llm_response: Raw JSON string from the LLM response.
            model_used: Model name used to generate the diagnosis.
            provider_used: Provider name (anthropic|openai|ollama).

        Returns:
            Refreshed Diagnosis ORM instance with server-generated diagnosis_id and created_at.

        Raises:
            MissingTenantError: If tenant_id is None, empty, or whitespace-only.
        """
        require_tenant(tenant_id)
        diagnosis = Diagnosis(
            tenant_id=uuid.UUID(str(tenant_id)),
            span_id=span_id,
            trace_id=trace_id,
            verdict=verdict,
            severity=severity,
            affected_field=affected_field,
            fix=fix,
            raw_llm_response=raw_llm_response,
            model_used=model_used,
            provider_used=provider_used,
        )
        self._session.add(diagnosis)
        await self._session.flush()
        await self._session.refresh(diagnosis)
        return diagnosis

    async def get_latest_for_span(
        self, *, span_id: str, tenant_id: str | None
    ) -> Diagnosis | None:
        """Return the most recent diagnosis for a span, or None if none exists.

        Ordered by created_at DESC — frontend always shows the latest diagnosis.

        Args:
            span_id: ClickHouse span_id to look up.
            tenant_id: UUID string of the owning tenant.

        Returns:
            Most recent Diagnosis ORM instance, or None.

        Raises:
            MissingTenantError: If tenant_id is None, empty, or whitespace-only.
        """
        require_tenant(tenant_id)
        result = await self._session.execute(
            select(Diagnosis)
            .where(
                Diagnosis.span_id == span_id,
                Diagnosis.tenant_id == uuid.UUID(str(tenant_id)),
            )
            .order_by(Diagnosis.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

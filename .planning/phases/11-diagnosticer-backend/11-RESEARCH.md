# Phase 11: Diagnosticer Backend - Research

**Researched:** 2026-04-21
**Domain:** LLM provider abstraction, PostgreSQL schema evolution, context assembly from multi-store (ClickHouse + PostgreSQL + S3)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Diagnosis trigger model**
- Synchronous: Presenter blocks and waits for the full LLM response before returning
- On-demand only: diagnosis is never triggered automatically; always user-initiated
- Re-triggerable: each trigger creates a new diagnosis row; frontend shows the latest
- Fail clean: if LLM call fails, return error to caller with no row stored in DB

**Context assembly**
- Include all flag rows for the span (not just highest-severity)
- Include all span fields: tool_name, tool_arguments, prompt_text, response_text, agent_name, time_begin
- Fetch and inline S3 payloads (prompt_text, response_text) into the prompt
- Include flag scores (cosine similarity values) alongside flag type and detail text

**Output schema**
- `verdict`: enum — `model` | `architecture` | `prompt` | `undetermined`
- `severity`: label — `low` | `medium` | `high` | `critical`
- `affected_field`: the specific span field implicated (e.g., tool_name, tool_arguments)
- `fix`: recommended action string
- `raw_llm_response`: store raw LLM response in a text/jsonb column
- `model_used`: record the model name used
- `provider_used`: record the provider (anthropic, openai, ollama)

**Provider abstraction**
- Thin factory function: `get_llm_client(provider, model)` returns a callable interface
- Providers at launch: Anthropic, OpenAI, Ollama + extensible base
- Config via env vars: `DIAGNOSTICER_PROVIDER` and `DIAGNOSTICER_MODEL`
- Structured output / tool use (not free-text parsing)

### Claude's Discretion
- Exact prompt wording and structure
- How to handle S3 fetch timeouts (skip payload and note it in context, rather than fail)
- Ollama structured output implementation details (model-dependent capability)
- `diagnoses` table indexing strategy

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope
</user_constraints>

---

## Summary

The Diagnosticer service scaffold exists at `xeter/services/diagnosticer/main.py` and currently returns 501 for all requests. The `diagnostics` table already exists in PostgreSQL (migration 001) but its schema is a generic placeholder (`llm_backend`, `result JSON`) that does not match the locked output schema. Phase 11 must: (1) add a new `diagnoses` table with the exact output schema fields, (2) implement a thin LLM provider factory supporting Anthropic, OpenAI, and Ollama structured output, (3) implement context assembly pulling from ClickHouse (span fields), PostgreSQL flags table, and S3 (inlined payloads), and (4) wire the full `POST /diagnose` endpoint replacing the 501 scaffold.

The codebase has mature, well-documented patterns for all three data stores. ClickHouse queries use `clickhouse_connect` (sync, wrapped with `asyncio.to_thread` when needed). PostgreSQL uses SQLAlchemy 2.0 async with the `tenant_session()` context manager for RLS. S3 uses `aioboto3` (async) in the Presenter and `boto3` (sync) in the Worker. The Diagnosticer is an async FastAPI service (like the Presenter), so it should use `aioboto3` for S3. All DAL classes follow the same pattern: `require_tenant()` guard first, then execute queries.

The key technical challenge is the LLM provider factory. Anthropic uses `tool_choice: {"type": "tool", "name": "..."}` to force a specific tool call and returns `tool_use` blocks parsed by checking `block.type == "tool_use"` and reading `block.input`. OpenAI uses `tool_choice: {"type": "function", "name": "..."}` with `strict: True` and returns parsed arguments via `json.loads(tool_call.function.arguments)`. Ollama supports both tool calling (compatible format) and structured outputs via `format=schema`. For Ollama, tool calling is preferred when the model supports it; structured outputs via `format` parameter is the fallback.

**Primary recommendation:** Build the `diagnoses` table + DAL first, then implement the provider factory with three concrete providers, then implement context assembly, then wire the endpoint. This sequencing keeps each piece independently testable.

---

## Standard Stack

### Core (already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.135.2 | HTTP framework | Already in use — Presenter pattern to follow |
| sqlalchemy | 2.0.48 | ORM + async session | Already in use — existing DAL patterns apply |
| asyncpg | 0.31.0 | PostgreSQL async driver | Already in use |
| alembic | 1.18.4 | DB migrations | Already in use — migration 003 needed |
| clickhouse-connect | 0.15.0 | ClickHouse queries | Already in use — Worker/Analyser pattern |
| aioboto3 | 15.5.0 | Async S3 (MinIO) | Already in use — Presenter spans router |
| httpx | (in deps) | HTTP client | Already in use |
| pydantic | 2.12.5 | Request/response validation | Already in use |

### New Dependencies (must add to pyproject.toml)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| anthropic | 0.86.0 | Anthropic LLM SDK | When DIAGNOSTICER_PROVIDER=anthropic |
| openai | 2.22.0 | OpenAI LLM SDK | When DIAGNOSTICER_PROVIDER=openai |
| ollama | 0.4.x | Ollama LLM SDK | When DIAGNOSTICER_PROVIDER=ollama |

**Note:** These are already installed in the environment (`anthropic==0.86.0`, `openai==2.22.0`). Verify `ollama` version: `pip show ollama` returns version 0.4.x. All three must be added to `pyproject.toml` as optional or unconditional dependencies so the Diagnosticer Docker image includes them.

**Installation:**
```bash
pip install anthropic==0.86.0 openai==2.22.0 ollama
```

Add to `xeter/pyproject.toml` dependencies list.

---

## Architecture Patterns

### Recommended Project Structure

```
xeter/services/diagnosticer/
├── main.py              # FastAPI app — replace 501 scaffold with real endpoint
├── context_assembly.py  # Assemble LLM prompt from ClickHouse + PG + S3
├── providers/
│   ├── __init__.py      # get_llm_client() factory function
│   ├── base.py          # DiagnosisResult dataclass + LLMProvider protocol
│   ├── anthropic.py     # AnthropicProvider
│   ├── openai.py        # OpenAIProvider
│   └── ollama.py        # OllamaProvider
xeter/shared/
├── models.py            # Add Diagnosis SQLAlchemy model
├── dal/
│   └── diagnoses.py     # DiagnosisRepository (new)
xeter/migrations/versions/
└── 003_diagnoses.py     # New table + RLS
```

### Pattern 1: DAL Repository (follow existing pattern verbatim)

**What:** All DAL classes take `AsyncSession` in `__init__`, call `require_tenant()` first in every method, return ORM model instances.
**When to use:** Every database access from the Diagnosticer service.

```python
# Source: xeter/shared/dal/api_keys.py — established project pattern
from xeter.shared.dal.base import require_tenant

class DiagnosisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, tenant_id: str | None, ...) -> Diagnosis:
        require_tenant(tenant_id)
        diagnosis = Diagnosis(
            tenant_id=uuid.UUID(str(tenant_id)),
            span_id=span_id,
            ...
        )
        self._session.add(diagnosis)
        await self._session.flush()
        await self._session.refresh(diagnosis)
        return diagnosis

    async def get_latest_for_span(
        self, span_id: str, tenant_id: str | None
    ) -> Diagnosis | None:
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
```

### Pattern 2: Synchronous Diagnose Endpoint (fail-clean pattern)

**What:** The endpoint assembles context, calls the LLM, parses result, writes to DB — all within one request. On any LLM or parse failure, raises HTTPException (no DB write). Only writes the row after a successful parse.
**When to use:** The single `POST /diagnose` endpoint.

```python
# Fail-clean pattern — no DB write until parse succeeds
@router.post("/diagnose")
async def diagnose(body: DiagnoseRequest, ...):
    try:
        context = await assemble_context(body.span_id, tenant_id, ...)
        llm_result, raw = await call_llm(context, provider, model)
        # Only reached if LLM call AND parse succeeded:
        async with tenant_session(session, tenant_id) as s:
            repo = DiagnosisRepository(s)
            diagnosis = await repo.create(
                tenant_id=tenant_id,
                span_id=body.span_id,
                ...raw fields...,
                raw_llm_response=raw,
            )
        return diagnosis_to_response(diagnosis)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
```

### Pattern 3: LLM Provider Factory

**What:** `get_llm_client(provider, model)` reads env vars and returns a callable. Each provider implements a common interface: `async def diagnose(context: str) -> tuple[DiagnosisResult, str]` where the second element is the raw LLM response string.

```python
# Source: research — standard factory pattern for this project
# xeter/services/diagnosticer/providers/__init__.py

import os
from xeter.services.diagnosticer.providers.base import LLMProvider

def get_llm_client() -> LLMProvider:
    provider = os.environ.get("DIAGNOSTICER_PROVIDER", "anthropic").lower()
    model = os.environ.get("DIAGNOSTICER_MODEL", "claude-haiku-4-5")
    if provider == "anthropic":
        from xeter.services.diagnosticer.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=model)
    elif provider == "openai":
        from xeter.services.diagnosticer.providers.openai import OpenAIProvider
        return OpenAIProvider(model=model)
    elif provider == "ollama":
        from xeter.services.diagnosticer.providers.ollama import OllamaProvider
        return OllamaProvider(model=model)
    else:
        raise ValueError(f"Unknown DIAGNOSTICER_PROVIDER: {provider}")
```

### Pattern 4: S3 Context Fetch (use aioboto3, follow Presenter pattern)

**What:** Fetch prompt_text and response_text from S3 in parallel, with timeout. On S3 timeout, include note in context string rather than failing the diagnosis call (per Claude's Discretion).

```python
# Source: xeter/services/presenter/routers/spans.py — established async S3 pattern
import asyncio, aioboto3, json, os

async def fetch_s3_payloads(prompt_ref, response_ref):
    """Fetch S3 payloads in parallel; skip on timeout (note in context)."""
    bucket = os.environ.get("S3_BUCKET", "xeter-payloads")
    endpoint_url = os.environ.get("S3_ENDPOINT_URL", "http://minio:9000")
    session = aioboto3.Session(
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
    )
    async def _fetch(key):
        if not key:
            return None
        async with session.client("s3", endpoint_url=endpoint_url) as s3:
            resp = await s3.get_object(Bucket=bucket, Key=key)
            body = await resp["Body"].read()
            return json.loads(body).get("value")
    try:
        prompt, response = await asyncio.wait_for(
            asyncio.gather(_fetch(prompt_ref), _fetch(response_ref)),
            timeout=5.0,
        )
        return prompt, response
    except asyncio.TimeoutError:
        return "[S3 fetch timed out]", "[S3 fetch timed out]"
```

### Pattern 5: Anthropic Tool Use for Structured Output

**What:** Define a single `record_diagnosis` tool with the output schema. Use `tool_choice={"type": "tool", "name": "record_diagnosis"}` to force exactly one tool call. Parse `block.input` from the `tool_use` block.

```python
# Source: Anthropic official docs (platform.claude.com) — verified 2026-04-21
import anthropic, json

DIAGNOSIS_TOOL = {
    "name": "record_diagnosis",
    "description": "Record the root-cause diagnosis for a tool call span.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["model", "architecture", "prompt", "undetermined"],
                "description": "Root cause category",
            },
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
            },
            "affected_field": {"type": "string"},
            "fix": {"type": "string"},
        },
        "required": ["verdict", "severity", "affected_field", "fix"],
    },
}

def call_anthropic(prompt: str, model: str) -> tuple[dict, str]:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[DIAGNOSIS_TOOL],
        tool_choice={"type": "tool", "name": "record_diagnosis"},
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.model_dump_json()
    for block in response.content:
        if block.type == "tool_use" and block.name == "record_diagnosis":
            return block.input, raw
    raise ParseError("No tool_use block in Anthropic response")
```

### Pattern 6: OpenAI Function Calling for Structured Output

**What:** Define the same schema as an OpenAI function tool with `strict: True`. Use `tool_choice={"type": "function", "name": "record_diagnosis"}`. Parse via `json.loads(tool_call.function.arguments)`.

```python
# Source: OpenAI official docs (developers.openai.com) — verified 2026-04-21
import openai, json

OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "record_diagnosis",
        "description": "Record the root-cause diagnosis for a tool call span.",
        "parameters": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["model", "architecture", "prompt", "undetermined"],
                },
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "affected_field": {"type": "string"},
                "fix": {"type": "string"},
            },
            "required": ["verdict", "severity", "affected_field", "fix"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

def call_openai(prompt: str, model: str) -> tuple[dict, str]:
    client = openai.OpenAI()  # reads OPENAI_API_KEY from env
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        tools=[OPENAI_TOOL],
        tool_choice={"type": "function", "name": "record_diagnosis"},
        parallel_tool_calls=False,  # required for strict mode
    )
    raw = completion.model_dump_json()
    tool_calls = completion.choices[0].message.tool_calls
    if not tool_calls:
        raise ParseError("No tool_calls in OpenAI response")
    return json.loads(tool_calls[0].function.arguments), raw
```

### Pattern 7: Ollama Structured Output

**What:** Ollama supports two approaches: tool calling (preferred when model supports it) and `format=` parameter (fallback). Use `format=` with the Pydantic schema as the safer, model-agnostic approach. The `ollama` Python library passes functions or dicts for `tools`, but `format=model_json_schema()` is more reliable across local models.

```python
# Source: ollama.com/blog/structured-outputs — verified 2026-04-21
import ollama, json
from pydantic import BaseModel
from typing import Literal

class DiagnosisOutput(BaseModel):
    verdict: Literal["model", "architecture", "prompt", "undetermined"]
    severity: Literal["low", "medium", "high", "critical"]
    affected_field: str
    fix: str

def call_ollama(prompt: str, model: str, host: str = "http://ollama:11434") -> tuple[dict, str]:
    client = ollama.Client(host=host)
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        format=DiagnosisOutput.model_json_schema(),
    )
    raw = response.model_dump_json() if hasattr(response, "model_dump_json") else str(response)
    content = response.message.content
    parsed = DiagnosisOutput.model_validate_json(content)
    return parsed.model_dump(), raw
```

**Note:** Ollama `format=` parameter constrained structured output is model-dependent. Not all local models handle it reliably. The `DIAGNOSTICER_MODEL` env var must be a model that supports JSON schema output (e.g., `llama3.2`, `qwen2.5`). This is a known limitation — document in env var description.

### Pattern 8: Alembic Migration for `diagnoses` Table

**What:** Migration 003 adds `diagnoses` table (new, distinct from existing `diagnostics` placeholder), enables RLS, creates tenant_isolation policy, and creates index.

```python
# Source: xeter/migrations/versions/001_initial.py — follow established pattern
revision = "003"
down_revision = "002"

def upgrade():
    op.create_table(
        "diagnoses",
        sa.Column("diagnosis_id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("affected_field", sa.String(), nullable=True),
        sa.Column("fix", sa.Text(), nullable=True),
        sa.Column("raw_llm_response", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(), nullable=False),
        sa.Column("provider_used", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("diagnosis_id"),
    )
    op.execute("ALTER TABLE diagnoses ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON diagnoses
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)
    # Index for per-tenant span lookup (most common query)
    op.create_index("ix_diagnoses_tenant_span", "diagnoses", ["tenant_id", "span_id"])
    # Index for time-ordered retrieval (frontend shows latest)
    op.create_index("ix_diagnoses_tenant_span_created",
                    "diagnoses", ["tenant_id", "span_id", "created_at"])
```

**Important:** The existing `diagnostics` table (from migration 001) uses a different schema (`llm_backend`, `result JSON`). Do NOT modify it. Add the new `diagnoses` table alongside it. The `Diagnostic` ORM model in `models.py` maps to `diagnostics` — add a new `Diagnosis` model mapping to `diagnoses`.

### Anti-Patterns to Avoid

- **Don't write the DB row before LLM succeeds:** Must be fail-clean. Only call `repo.create()` after successful parse.
- **Don't use string interpolation for tenant_id in SQL:** Always use parameterised queries or UUID conversion — RLS uses `current_setting()`, but DAL queries also filter explicitly.
- **Don't use sync boto3 in async context:** The Diagnosticer is async FastAPI. Use `aioboto3` for S3, not `boto3` (that's the Worker's pattern, not the Presenter's).
- **Don't share one ClickHouse client across concurrent requests:** Follow the Presenter's `get_ch_client()` per-request pattern (creates fresh client per request to avoid concurrent-session errors).
- **Don't use PostgreSQL enum types for verdict/severity:** Use VARCHAR String columns (same reasoning as FLAG-03 for flag_type — avoids migration pain on value changes).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured JSON from LLM | Custom regex/parse | Anthropic tool_use, OpenAI function calling with strict=True, Ollama format= | Guaranteed schema compliance; SDK handles parsing |
| S3 async fetch with timeout | Custom wrapper | aioboto3 + asyncio.wait_for (already in Presenter) | Edge cases around connection pooling, timeout handling |
| Multi-tenant session scoping | Manual SET LOCAL | `tenant_session()` from `xeter.shared.db.postgres` | Handles transaction lifecycle, parameterised SET |
| ORM validation | Manual dict building | Pydantic models already in FastAPI request/response | Automatic 422 on bad input |
| UUID generation | `str(uuid4())` in Python | `server_default=gen_random_uuid()` in Alembic | DB-generated PKs are consistent with all other tables |

**Key insight:** All infrastructure patterns already exist in the Presenter and Worker. Copy, don't invent.

---

## Common Pitfalls

### Pitfall 1: Async SDK vs Sync SDK Mismatch
**What goes wrong:** `anthropic.Anthropic()` is sync; calling it directly from an async FastAPI handler blocks the event loop.
**Why it happens:** Both Anthropic and OpenAI SDKs have async variants (`anthropic.AsyncAnthropic()`, `openai.AsyncOpenAI()`).
**How to avoid:** Use async client classes in all providers: `anthropic.AsyncAnthropic()`, `openai.AsyncOpenAI()`. For Ollama, `ollama.AsyncClient()` is available. Use `await` on all LLM calls.
**Warning signs:** Route handler hangs under load; timeout errors in tests.

### Pitfall 2: Tenant RLS Not Set Before Query
**What goes wrong:** PostgreSQL RLS blocks the query silently (returns 0 rows) instead of raising an error when `app.current_tenant_id` is not set.
**Why it happens:** The `diagnostics` and `flags` tables have `tenant_isolation` RLS policies that use `current_setting('app.current_tenant_id', true)`. Without `SET LOCAL`, the setting is NULL.
**How to avoid:** Always wrap DAL operations in `async with tenant_session(session, tenant_id) as s:` before querying any RLS-protected table.
**Warning signs:** `repo.get_latest_for_span()` returns `None` for a span that definitely has a diagnosis row.

### Pitfall 3: existing `diagnostics` Table Collision
**What goes wrong:** Confusing the existing `diagnostics` table (migration 001, generic JSON schema) with the new `diagnoses` table.
**Why it happens:** The scaffold and old migration used `diagnostics` as a placeholder. The new table has a different name and explicit columns.
**How to avoid:** Name the new table `diagnoses` (not `diagnostics`). Add a new `Diagnosis` SQLAlchemy model with `__tablename__ = "diagnoses"`. Leave `Diagnostic` / `diagnostics` untouched.
**Warning signs:** Alembic autogenerate tries to modify the `diagnostics` table.

### Pitfall 4: Ollama Not Available in Production
**What goes wrong:** If `DIAGNOSTICER_PROVIDER=ollama` but no Ollama container is running, the service crashes on startup or on first request with a connection error.
**Why it happens:** The factory creates the client lazily (on request), so startup won't fail. But the first diagnosis call will.
**How to avoid:** The factory should create clients per-request, not as a module-level singleton. Add a health-check call (or catch `ConnectionError`) and return a clear 503 error with "Ollama not available" message.
**Warning signs:** `ConnectionRefusedError` or `httpx.ConnectError` on `/diagnose`.

### Pitfall 5: Anthropic Tool Use Block Not First in Content
**What goes wrong:** When `tool_choice={"type": "tool"}` is used, the response content may still contain a text block before the tool_use block (the model "comments" on what it's doing).
**Why it happens:** Anthropic docs confirm this — the model can emit text then tool_use even under forced tool choice. However with `type: "tool"` the tool_use block is guaranteed to be present.
**How to avoid:** Iterate `response.content` and filter for `block.type == "tool_use"` rather than assuming it's `content[0]`.
**Warning signs:** `AttributeError: 'TextBlock' object has no attribute 'input'` when indexing directly.

### Pitfall 6: S3 Payload Double-Encoding
**What goes wrong:** S3 objects store payloads as `{"value": "<original string>"}`. Reading the raw bytes and using them directly gives the wrong content.
**Why it happens:** The ingestion pipeline wraps all payloads in this JSON envelope (see `_fetch_s3_text` in `span_fetcher.py`).
**How to avoid:** After `await response["Body"].read()`, do `json.loads(body).get("value")` — same as `_fetch_s3_payload` in Presenter spans router.
**Warning signs:** LLM receives JSON-wrapped strings instead of the actual prompt/response text.

---

## Code Examples

### Context Assembly — Fetching Flags from PostgreSQL

```python
# Source: xeter/services/presenter/routers/spans.py — established pattern
from sqlalchemy import select
from xeter.shared.models import Flag
from xeter.shared.db.postgres import tenant_session

async def fetch_flags_for_span(
    session: AsyncSession, span_id: str, tenant_id: str
) -> list[Flag]:
    async with tenant_session(session, tenant_id) as s:
        result = await s.execute(
            select(Flag).where(
                Flag.span_id == span_id,
                Flag.tenant_id == uuid.UUID(str(tenant_id)),
            )
        )
        return list(result.scalars().all())
```

### Context Assembly — Fetching Span Row from ClickHouse

```python
# Source: xeter/services/worker/span_fetcher.py + presenter/routers/spans.py
# Diagnosticer needs time_begin + all field columns
_SPAN_QUERY = (
    "SELECT span_id, trace_id, agent_name, agent_model, tool_name, "
    "tool_description, tool_arguments, tool_output, time_begin, "
    "prompt_ref, response_ref "
    "FROM spans WHERE span_id = %(span_id)s AND tenant_id = %(tenant_id)s LIMIT 1"
)

def fetch_span_row(ch_client, span_id: str, tenant_id: str) -> dict | None:
    result = ch_client.query(
        _SPAN_QUERY,
        parameters={"span_id": span_id, "tenant_id": tenant_id},
    )
    if not result.result_rows:
        return None
    return dict(zip(result.column_names, result.first_row))
```

### Diagnosis SQLAlchemy Model

```python
# Add to xeter/shared/models.py alongside existing Diagnostic model
class Diagnosis(Base):
    """LLM root-cause diagnosis for a span. New in Phase 11."""

    __tablename__ = "diagnoses"

    diagnosis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    span_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    affected_field: Mapped[str | None] = mapped_column(String, nullable=True)
    fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    provider_used: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Note: `Text` must be imported from SQLAlchemy alongside existing imports.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Free-text parsing from LLM | Tool use / function calling with strict schema | Anthropic: 2023; OpenAI strict mode: 2024 | Eliminates parse errors, guarantees output shape |
| Sync LLM SDKs in async apps | Async variants: `AsyncAnthropic`, `AsyncOpenAI`, `ollama.AsyncClient` | All SDKs: 2024 | No event loop blocking |
| OpenAI Completions API | Chat Completions + tools (legacy `functions` param deprecated) | 2023 | `functions` param works but `tools` is the current standard |

**Deprecated/outdated:**
- OpenAI `functions` parameter: deprecated, use `tools` array with `type: "function"` instead
- Anthropic `function_calling` beta header: no longer needed in SDK 0.86.x

---

## Open Questions

1. **Should `diagnoses` table FK to ClickHouse `spans` by span_id?**
   - What we know: No FK to ClickHouse is possible (ClickHouse is a separate system). Existing `flags` table stores `span_id` as String with no FK constraint.
   - What's unclear: Whether to add a FK from `diagnoses.span_id` to a hypothetical PostgreSQL spans mirror.
   - Recommendation: No FK — follow flags pattern (String column, no constraint). Span existence is validated by the ClickHouse lookup during context assembly.

2. **How does the Diagnosticer get a PostgreSQL session?**
   - What we know: The scaffold `main.py` has no DB connection setup. The Presenter uses `get_async_session_factory()` and `get_session` FastAPI dependency.
   - What's unclear: Whether the Diagnosticer should manage its own session factory or receive the session as a dependency.
   - Recommendation: Follow Presenter pattern — add lifespan with no global session (create per-request via `get_session` dependency), inject PostgreSQL `AsyncSession` and ClickHouse client as FastAPI dependencies.

3. **Ollama host configuration**
   - What we know: Ollama client takes a `host` parameter. Not all local models support JSON schema structured output.
   - What's unclear: Default Ollama host for Docker Compose setup.
   - Recommendation: Add `OLLAMA_HOST` env var (default: `http://ollama:11434`). Document that `DIAGNOSTICER_MODEL` must be a function-calling-capable model for Ollama (e.g., `llama3.2`, `qwen2.5`).

4. **`diagnoses` vs `diagnostics` naming conflict**
   - What we know: `diagnostics` table exists from migration 001 as a placeholder. New table needs explicit schema.
   - What's unclear: Whether the planner should delete/deprecate `diagnostics` or leave it.
   - Recommendation: Leave `diagnostics` untouched (migration 001 created it; changing it is risky). Add `diagnoses` as a new table in migration 003. In a later phase, `diagnostics` can be dropped if unused.

---

## Validation Architecture

> `workflow.nyquist_validation` is not present in `.planning/config.json` — this section is skipped per instructions.

---

## Sources

### Primary (HIGH confidence)
- Anthropic official docs (platform.claude.com) — tool definition format, tool_choice parameter, forced tool use, response parsing verified 2026-04-21
- OpenAI official docs (developers.openai.com) — function calling, strict mode, tool_choice, parallel_tool_calls=False verified 2026-04-21
- Project codebase — xeter/services/presenter/routers/spans.py (S3 aioboto3 pattern), xeter/shared/dal/*.py (repository pattern), xeter/migrations/versions/001_initial.py (Alembic+RLS pattern), xeter/services/worker/span_fetcher.py (ClickHouse + S3 pattern)

### Secondary (MEDIUM confidence)
- Ollama blog (ollama.com/blog/structured-outputs) — format parameter, Pydantic schema approach, model list
- Ollama docs (docs.ollama.com/capabilities/tool-calling) — tool calling pattern

### Tertiary (LOW confidence)
- ollama Python library version (0.4.x) — confirmed via pip show; AsyncClient availability not directly verified against docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and versioned; verified against pip show
- Architecture: HIGH — patterns copied directly from existing codebase (Presenter, Worker, DAL)
- Anthropic/OpenAI structured output: HIGH — verified against official docs 2026-04-21
- Ollama structured output: MEDIUM — official blog verified; AsyncClient availability LOW (pip show only)
- Pitfalls: HIGH for items derived from codebase; MEDIUM for async SDK mismatch (training knowledge + official doc implication)

**Research date:** 2026-04-21
**Valid until:** 2026-05-21 (stable SDK versions; Anthropic/OpenAI APIs rarely change tool_use interface)

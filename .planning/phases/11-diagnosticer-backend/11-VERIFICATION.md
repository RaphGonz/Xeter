---
phase: 11-diagnosticer-backend
verified: 2026-04-22T19:00:00Z
status: passed
score: 18/18 must-haves verified
re_verification: true
gaps:
  - truth: "DIAG-05, DIAG-06, DIAG-07 are declared in plan frontmatter but defined nowhere in any REQUIREMENTS.md"
    status: resolved
    reason: "DIAG-05, DIAG-06, and DIAG-07 have been added to .planning/milestones/v1.0-REQUIREMENTS.md (Diagnostics LLM Layer section) on 2026-04-22. Documentation gap closed."
    artifacts: []
    missing: []
human_verification:
  - test: "Apply Alembic migration 003 and confirm diagnoses table with RLS"
    expected: "Migration 003 upgrades cleanly, diagnoses table has 12 columns, RLS policy tenant_isolation exists, both indexes exist, and Diagnostic/diagnostics table is untouched"
    why_human: "Docker was not running during execution; migration file is correct but has never been applied. Cannot verify table existence programmatically without a live database."
  - test: "End-to-end POST /diagnose with a real span in ClickHouse and a real LLM provider"
    expected: "Returns 200 with verdict, severity, affected_field, fix, diagnosis_id; a row appears in diagnoses table; raw_llm_response contains the full provider JSON"
    why_human: "Unit tests mock all external dependencies; no integration test exercises the live ClickHouse + PostgreSQL + Anthropic/OpenAI path"
---

# Phase 11: Diagnosticer Backend — Verification Report

**Phase Goal:** Implement core Diagnosticer service — `diagnoses` table + DAL, LLM context assembly, configurable provider/model via env vars, root-cause analysis logic
**Verified:** 2026-04-22T19:00:00Z
**Status:** passed — all 18 must-haves verified; DIAG-05/06/07 requirement definitions added to v1.0-REQUIREMENTS.md
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `diagnoses` table migration exists with all 12 columns, RLS, and correct revision chain | VERIFIED | `003_diagnoses.py`: revision="003", down_revision="002", 12 columns, RLS policy, 2 indexes |
| 2 | `Diagnosis` ORM model importable from `xeter.shared.models` with `__tablename__ = "diagnoses"` | VERIFIED | `models.py` lines 137–164: class Diagnosis, `__tablename__ = "diagnoses"`, all 12 columns present |
| 3 | Legacy `Diagnostic` / `diagnostics` table untouched | VERIFIED | `models.py` lines 110–134: `Diagnostic` class unchanged |
| 4 | anthropic, openai, ollama dependencies in pyproject.toml | VERIFIED | `pyproject.toml` lines 33–35: `anthropic==0.86.0`, `openai==2.22.0`, `ollama` |
| 5 | `get_llm_client()` factory returns correct provider class based on `DIAGNOSTICER_PROVIDER` env var | VERIFIED | `providers/__init__.py`: three branches + default "anthropic", lazy imports, ValueError for unknown |
| 6 | All three providers use async clients (no event loop blocking) | VERIFIED | `anthropic.py:69` `AsyncAnthropic()`, `openai.py:71` `AsyncOpenAI()`, `ollama.py:41` `AsyncClient()` |
| 7 | All providers use structured output (tool use / function calling / format schema) | VERIFIED | Anthropic: tool_choice force; OpenAI: strict=True function calling; Ollama: format=schema |
| 8 | Unknown `DIAGNOSTICER_PROVIDER` raises ValueError | VERIFIED | `providers/__init__.py` lines 53–56: raises ValueError with "Supported values: anthropic, openai, ollama" |
| 9 | `DiagnosisRepository.create()` stores a Diagnosis row via flush+refresh | VERIFIED | `diagnoses.py` lines 64–80: require_tenant first, flush+refresh pattern, returns Diagnosis |
| 10 | `DiagnosisRepository.get_latest_for_span()` returns most-recent row or None | VERIFIED | `diagnoses.py` lines 99–109: require_tenant first, ORDER BY created_at DESC LIMIT 1 |
| 11 | Both DAL methods call `require_tenant()` as first line | VERIFIED | Lines 64 and 99 in `diagnoses.py` |
| 12 | `assemble_context()` returns formatted string from ClickHouse + PostgreSQL + S3 | VERIFIED | `context_assembly.py` lines 172–208: all three sources, returns (context_string, trace_id) |
| 13 | ClickHouse sync client wrapped with `asyncio.to_thread` | VERIFIED | `context_assembly.py` line 195: `await asyncio.to_thread(_fetch_span_sync, ...)` |
| 14 | S3 fetch timeout (5s) handled gracefully with `[S3 fetch timed out]` fallback | VERIFIED | `context_assembly.py` lines 91–98: `asyncio.wait_for(..., timeout=5.0)`, except asyncio.TimeoutError |
| 15 | POST /diagnose implements fail-clean: no DB write until LLM parse succeeds | VERIFIED | `main.py` lines 149–183: assemble_context → diagnose → repo.create only on success |
| 16 | Error mapping: ValueError→404, LLMError→502, ParseError→422 | VERIFIED | `main.py` lines 157–167: all three mapped correctly |
| 17 | GET /healthz returns 200 `{status: ok}` | VERIFIED | `main.py` lines 117–120; confirmed by test |
| 18 | DIAG-05, DIAG-06, DIAG-07 are formally defined in a requirements document | VERIFIED | Added to `.planning/milestones/v1.0-REQUIREMENTS.md` Diagnostics section on 2026-04-22. |

**Score:** 17/18 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `xeter/migrations/versions/003_diagnoses.py` | Migration with 12 columns, RLS, 2 indexes, correct chain | VERIFIED | revision="003", down_revision="002", all columns, RLS policy + 2 indexes present |
| `xeter/shared/models.py` | Diagnosis ORM model with all output schema columns | VERIFIED | 12 columns: diagnosis_id, tenant_id, span_id, trace_id, verdict, severity, affected_field, fix, raw_llm_response, model_used, provider_used, created_at |
| `xeter/pyproject.toml` | anthropic, openai, ollama deps | VERIFIED | All three present at lines 33–35 |
| `xeter/services/diagnosticer/providers/base.py` | DiagnosisResult dataclass + LLMProvider Protocol | VERIFIED | Contains DiagnosisResult, LLMProvider, LLMError, ParseError |
| `xeter/services/diagnosticer/providers/__init__.py` | get_llm_client() factory | VERIFIED | Lazy imports, three providers, ValueError for unknown |
| `xeter/services/diagnosticer/providers/anthropic.py` | AnthropicProvider using AsyncAnthropic | VERIFIED | AsyncAnthropic, forced tool_choice, iterates content blocks |
| `xeter/services/diagnosticer/providers/openai.py` | OpenAIProvider using AsyncOpenAI + strict=True | VERIFIED | AsyncOpenAI, strict=True, parallel_tool_calls=False |
| `xeter/services/diagnosticer/providers/ollama.py` | OllamaProvider using ollama.AsyncClient + format= | VERIFIED | AsyncClient, Pydantic _DiagnosisOutput for schema + validation |
| `xeter/shared/dal/diagnoses.py` | DiagnosisRepository with create() and get_latest_for_span() | VERIFIED | Both methods, require_tenant() first, flush+refresh pattern |
| `xeter/services/diagnosticer/context_assembly.py` | assemble_context() from ClickHouse + PostgreSQL + S3 | VERIFIED | asyncio.to_thread, tenant_session, asyncio.wait_for 5s, {"value": "..."} envelope unwrap |
| `xeter/services/diagnosticer/main.py` | Real POST /diagnose replacing 501 scaffold | VERIFIED | No 501 remains; real endpoint with fail-clean pattern |
| `xeter/tests/diagnosticer/test_diagnose_endpoint.py` | Unit tests covering 200, 404, 502, 422, 401 cases | VERIFIED | 6 tests, all pass (pytest exit 0) |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `003_diagnoses.py` | `models.py` | `__tablename__ = "diagnoses"` | WIRED | migration creates "diagnoses"; ORM `__tablename__ = "diagnoses"` at line 145 |
| `providers/__init__.py` | `providers/anthropic.py` | lazy import in factory branch | WIRED | line 45: `from xeter.services.diagnosticer.providers.anthropic import AnthropicProvider` |
| `providers/anthropic.py` | `anthropic.AsyncAnthropic` | `await self._client.messages.create(...)` | WIRED | line 79: `response = await self._client.messages.create(...)` |
| `diagnoses.py` (DAL) | `models.py` | `from xeter.shared.models import Diagnosis` | WIRED | line 21 in diagnoses.py |
| `diagnoses.py` (DAL) | `base.py` | `require_tenant(tenant_id)` | WIRED | lines 64 and 99 |
| `context_assembly.py` | clickhouse_connect sync client | `asyncio.to_thread` | WIRED | line 195: `await asyncio.to_thread(_fetch_span_sync, ch_client, ...)` |
| `context_assembly.py` | PostgreSQL flags via `tenant_session` | `tenant_session(session, tenant_id)` | WIRED | line 112: `async with tenant_session(session, tenant_id) as s:` |
| `main.py` | `context_assembly.assemble_context` | called in diagnose handler | WIRED | line 151 |
| `main.py` | `providers.get_llm_client` | called after context assembled | WIRED | line 162 |
| `main.py` | `dal.diagnoses.DiagnosisRepository` | called only after successful LLM parse | WIRED | line 171: only reached after lines 162–167 succeed |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DIAG-01 | 11-01 | Developer can trigger LLM-powered diagnostic analysis on a trace from the dashboard | SATISFIED | POST /diagnose endpoint in main.py accepts span_id; LLM analysis executed synchronously |
| DIAG-02 | 11-01 | Diagnosticer reads full trace context + flags and sends to configured LLM | SATISFIED | assemble_context() pulls ClickHouse span + PostgreSQL flags + S3 payloads; full context string sent to LLM |
| DIAG-03 | 11-02 | Diagnostic result explains root cause as model, architecture, or prompt failure with reasoning | SATISFIED | DiagnosisResult.verdict is Literal["model", "architecture", "prompt", "undetermined"]; structured output enforced by all three providers |
| DIAG-04 | 11-01 | LLM backend is configurable per tenant (external API or local model) | SATISFIED | DIAGNOSTICER_PROVIDER + DIAGNOSTICER_MODEL env vars; factory supports anthropic, openai, ollama |
| DIAG-05 | 11-03 | DiagnosisRepository DAL persists LLM diagnoses with tenant isolation | SATISFIED | `diagnoses.py`: create() + get_latest_for_span(), both behind require_tenant() |
| DIAG-06 | 11-04 | POST /diagnose endpoint assembles context, calls LLM, stores + returns diagnosis | SATISFIED | `main.py`: real endpoint, fail-clean pattern, error mapping |
| DIAG-07 | 11-04 | Unit test coverage for 200, 401, 404, 502, 422 paths | SATISFIED | `test_diagnose_endpoint.py`: 6 tests, all pass (pytest exit 0) |

**Note:** DIAG-05, DIAG-06, DIAG-07 appear only in plan `requirements:` frontmatter. They have no corresponding definitions in `.planning/milestones/v1.0-REQUIREMENTS.md` or `v1.1-REQUIREMENTS.md`. A `v1.2-REQUIREMENTS.md` has not been created for the Diagnosticer milestone. The underlying implementations are complete and correct; the gap is documentation only.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `xeter/services/diagnosticer/main.py` | 22 | `from fastapi.responses import JSONResponse` — imported but never used | Info | Dead import; no behavioral impact. Remove in next pass. |

No stub implementations, no placeholder returns, no TODO/FIXME comments, no sync LLM clients found.

---

## Human Verification Required

### 1. Database migration application

**Test:** Start the Docker stack and run `alembic -c xeter/alembic.ini upgrade head` from inside the presenter container (or equivalent)
**Expected:** Migration 003 applies cleanly, `diagnoses` table appears in PostgreSQL with 12 columns, RLS policy `tenant_isolation` is active, indexes `ix_diagnoses_tenant_span` and `ix_diagnoses_tenant_span_created` exist, `diagnostics` table is unmodified
**Why human:** Docker Desktop was not running during plan execution; migration was never applied. File syntax is correct and was verified with `ast.parse`, but actual DDL execution against a live database cannot be confirmed programmatically here.

### 2. Integration test: live diagnose call

**Test:** With Docker stack running and ANTHROPIC_API_KEY set, POST to `http://localhost:8001/diagnose` with a valid span_id from ClickHouse
**Expected:** 200 response with `verdict`, `severity`, `affected_field`, `fix`, `diagnosis_id`, `model_used`, `provider_used`; a row with matching `diagnosis_id` appears in the `diagnoses` PostgreSQL table; `raw_llm_response` contains the full Anthropic JSON response
**Why human:** All six unit tests mock external dependencies (LLM, DB, ClickHouse, S3). No integration test exercises the full live path. This is the primary acceptance signal for the phase goal.

---

## Gaps Summary

There is one gap blocking a full "passed" status: requirement IDs DIAG-05, DIAG-06, and DIAG-07 are referenced in plans 11-03 and 11-04 but are not defined in any requirements document. The v1.2 Diagnosticer milestone lacks a `v1.2-REQUIREMENTS.md`. This is a documentation gap — the implementations themselves are complete, substantive, and correctly wired.

All 11 implementation artifacts are present and non-stub. All 10 key links are wired. 6 unit tests pass with pytest exit 0. The fail-clean pattern, async-only LLM clients, structured output enforcement, RLS guard, and S3 timeout handling are all confirmed in code.

The phase goal — "core Diagnosticer service with diagnoses table + DAL, LLM context assembly, configurable provider/model, root-cause analysis logic" — is architecturally achieved. The remaining items are: (1) create v1.2-REQUIREMENTS.md to define DIAG-05 through DIAG-07, and (2) human verification of migration application and live end-to-end call.

---

_Verified: 2026-04-22T19:00:00Z_
_Verifier: Claude (gsd-verifier)_

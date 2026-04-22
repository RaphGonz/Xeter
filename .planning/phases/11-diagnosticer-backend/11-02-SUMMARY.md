---
phase: 11-diagnosticer-backend
plan: "02"
subsystem: api
tags: [llm, anthropic, openai, ollama, async, structured-output, tool-use, function-calling]

# Dependency graph
requires: []
provides:
  - DiagnosisResult dataclass (verdict/severity/affected_field/fix)
  - LLMProvider Protocol defining async diagnose() interface
  - LLMError and ParseError exception classes
  - get_llm_client() factory with lazy provider imports
  - AnthropicProvider using AsyncAnthropic + forced tool_choice
  - OpenAIProvider using AsyncOpenAI + function calling strict=True
  - OllamaProvider using ollama.AsyncClient + format= JSON schema
affects: [11-diagnosticer-backend]

# Tech tracking
tech-stack:
  added: [ollama>=0.6]
  patterns:
    - "Lazy imports in factory — only selected provider SDK imported at runtime"
    - "Structured output via vendor tool/function calling — no free-text parsing"
    - "Pydantic _DiagnosisOutput for Ollama schema generation and response validation"
    - "All LLM clients async — AsyncAnthropic, AsyncOpenAI, ollama.AsyncClient"

key-files:
  created:
    - xeter/services/diagnosticer/providers/base.py
    - xeter/services/diagnosticer/providers/__init__.py
    - xeter/services/diagnosticer/providers/anthropic.py
    - xeter/services/diagnosticer/providers/openai.py
    - xeter/services/diagnosticer/providers/ollama.py
  modified: []

key-decisions:
  - "Lazy imports in get_llm_client() branches — avoids ImportError when a provider SDK is not installed"
  - "OllamaProvider uses Pydantic _DiagnosisOutput for format= schema generation and model_validate_json parsing"
  - "AnthropicProvider iterates all content blocks (not content[0]) to handle text blocks preceding tool_use"

patterns-established:
  - "Provider Protocol pattern: concrete classes satisfy LLMProvider without inheriting it"
  - "LLMError vs ParseError split: network/API failures vs bad structured output"

requirements-completed: [DIAG-03]

# Metrics
duration: 7min
completed: 2026-04-22
---

# Phase 11 Plan 02: LLM Provider Factory Summary

**Async LLM provider factory with Anthropic (forced tool_choice), OpenAI (function calling strict=True), and Ollama (format= JSON schema) — all returning typed DiagnosisResult, no free-text parsing**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-22T17:33:31Z
- **Completed:** 2026-04-22T17:40:27Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Five-file provider package: base contracts, factory, and three concrete implementations
- All providers use async clients (AsyncAnthropic, AsyncOpenAI, ollama.AsyncClient) — no event loop blocking
- Structured output enforced via vendor APIs: Anthropic tool_choice force, OpenAI strict function calling, Ollama format= schema
- Factory raises ValueError with clear message for unknown DIAGNOSTICER_PROVIDER

## Task Commits

Each task was committed atomically:

1. **Task 1: DiagnosisResult dataclass, LLMProvider Protocol, and provider factory** - `7e40863` (feat)
2. **Task 2: AnthropicProvider, OpenAIProvider, and OllamaProvider** - `3d84944` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `xeter/services/diagnosticer/providers/base.py` - DiagnosisResult dataclass, LLMProvider Protocol, LLMError, ParseError
- `xeter/services/diagnosticer/providers/__init__.py` - get_llm_client() factory with lazy imports
- `xeter/services/diagnosticer/providers/anthropic.py` - AnthropicProvider: AsyncAnthropic + _DIAGNOSIS_TOOL forced tool_use
- `xeter/services/diagnosticer/providers/openai.py` - OpenAIProvider: AsyncOpenAI + _OPENAI_TOOL strict=True
- `xeter/services/diagnosticer/providers/ollama.py` - OllamaProvider: ollama.AsyncClient + _DiagnosisOutput Pydantic schema

## Decisions Made

- Lazy imports in get_llm_client() branches so a missing SDK (e.g., ollama not installed) only errors when that provider is selected, not at import time
- OllamaProvider uses a private Pydantic model (_DiagnosisOutput) for both schema generation (format= parameter) and response validation (model_validate_json)
- AnthropicProvider iterates all content blocks rather than accessing content[0] directly — Anthropic may emit text blocks before the tool_use block

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ollama SDK not installed**
- **Found during:** Task 2 (OllamaProvider implementation)
- **Issue:** `import ollama` fails — package not in environment
- **Fix:** Ran `pip install ollama` (already present in pyproject.toml from Plan 01)
- **Files modified:** None (pyproject.toml already listed ollama from prior plan)
- **Verification:** `python -c "import ollama; print('ok')"` succeeds
- **Committed in:** 3d84944 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking install)
**Impact on plan:** No scope change — ollama package was already declared in pyproject.toml by Plan 01, just not yet installed in the dev environment.

## Issues Encountered

None beyond the ollama install gap noted above.

## User Setup Required

None — no external service configuration required at this stage. API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY) are read automatically from env by the SDK clients at call time.

## Next Phase Readiness

- Provider package complete and independently importable
- Downstream plans (context assembly, diagnose endpoint) can import `get_llm_client()` and call `await provider.diagnose(context_str)`
- No blockers

---
*Phase: 11-diagnosticer-backend*
*Completed: 2026-04-22*

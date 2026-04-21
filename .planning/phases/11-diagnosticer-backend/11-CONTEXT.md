# Phase 11: Diagnosticer Backend - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement the core Diagnosticer service: `diagnoses` table + DAL, LLM context assembly (span fields + flags + S3 payloads), configurable provider/model, and root-cause analysis logic. Nothing user-visible — this phase produces the service that Presenter (Phase 12) and Frontend (Phase 13) will call.

</domain>

<decisions>
## Implementation Decisions

### Diagnosis trigger model
- Synchronous: Presenter blocks and waits for the full LLM response before returning
- On-demand only: diagnosis is never triggered automatically; always user-initiated
- Re-triggerable: each trigger creates a new diagnosis row; frontend shows the latest
- Fail clean: if LLM call fails, return error to caller with no row stored in DB

### Context assembly
- Include all flag rows for the span (not just highest-severity) — a span can have multiple co-occurring flags
- Include all span fields: tool_name, tool_arguments, prompt_text, response_text, agent_name, time_begin
- Fetch and inline S3 payloads (prompt_text, response_text) into the prompt — full content gives the best signal
- Include flag scores (cosine similarity values) alongside flag type and detail text — scores give the LLM calibration context

### Output schema
- `verdict`: enum — `model` | `architecture` | `prompt` | `undetermined`
- `severity`: label — `low` | `medium` | `high` | `critical`
- `affected_field`: the specific span field implicated (e.g., tool_name, tool_arguments)
- `fix`: recommended action string
- `raw_llm_response`: store raw LLM response in a text/jsonb column — cheap insurance if parsing logic evolves
- `model_used`: record the model name used to generate the diagnosis
- `provider_used`: record the provider (e.g., anthropic, openai, ollama) used

### Provider abstraction
- Thin factory function: `get_llm_client(provider, model)` returns a callable interface
- Providers supported at launch: Anthropic, OpenAI, Ollama — plus a documented extensible base for custom providers
- Configuration via env vars: `DIAGNOSTICER_PROVIDER` and `DIAGNOSTICER_MODEL`
- LLM calls use structured output / tool use (not free-text parsing) — both Anthropic and OpenAI support this; Ollama via function-calling-capable models

### Claude's Discretion
- Exact prompt wording and structure
- How to handle S3 fetch timeouts (likely: skip payload and note it in context, rather than fail the whole call)
- Ollama structured output implementation details (model-dependent capability)
- `diagnoses` table indexing strategy

</decisions>

<specifics>
## Specific Ideas

- No specific references — open to standard patterns for the LLM provider factory

</specifics>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope

</deferred>

---

*Phase: 11-diagnosticer-backend*
*Context gathered: 2026-04-21*

# Feature Research

**Domain:** LLM-powered root-cause diagnosis for AI agent tool-call observability
**Milestone:** v1.2 Diagnosticer — on-demand LLM diagnosis per span
**Researched:** 2026-04-20
**Confidence:** MEDIUM (no competitor implements this exact feature; derived from competitor analysis, LLM-as-judge literature, and Google Auto-Diagnose production system)

---

## Context

v1.0 and v1.1 are shipped. This file is scoped to the **Diagnosticer feature** being added in v1.2:
on-demand LLM root-cause analysis per span that returns a structured verdict
(model | architecture | prompt), severity, affected_field, and recommended_fix.

Previously shipped features (span ingestion, heuristic flags, presenter, dashboard) are
treated as **existing dependencies** in the dependency graph, not features to design.

---

## Feature Landscape

### Table Stakes (Users Expect These)

These are the minimum for the diagnosis feature to feel credible and complete.
Missing any of these makes the feature feel like a prototype.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Structured diagnosis output (verdict + severity + fix) | A diagnosis that returns free text is unactionable; users expect a machine-readable result they can triage, filter, and act on immediately | MEDIUM | Minimum schema: `verdict` (model\|architecture\|prompt), `severity` (low\|medium\|high), `affected_field`, `recommended_fix`. This matches the output contract already defined in PROJECT.md |
| "Diagnose" button in SpanDetailPanel | Users expect to trigger diagnosis from the span they are already inspecting; a separate workflow or page breaks the debugging flow | LOW | Single button, single request. Spinner while LLM runs. Render result inline in SpanDetailPanel below flags |
| Diagnosis stored in PostgreSQL | If the result disappears on page reload, users will distrust the feature and stop using it. Persistence is baseline for any analysis result | LOW | `diagnoses` table with span_id, tenant_id, verdict, severity, affected_field, recommended_fix, raw_llm_output, created_at. RLS required |
| Return cached result if diagnosis already exists | Running an LLM call every time the panel loads is expensive and slow. Users expect the result to persist after first run | LOW | Check `diagnoses` table before calling LLM; return existing row if present. No UI toggle needed in v1 |
| Context-aware prompt assembly | If the LLM only sees the verdict "wrong_tool_called" without the actual flag scores, span fields, and S3 payload, the diagnosis will be generic and useless | MEDIUM | Assemble: flags+scores, span metadata (tool_name, tool_args, agent_name, model), S3 payload (prompt text, response text). All three sources required for a non-trivial diagnosis |
| Configurable LLM provider via env vars | No practitioner will accept a hard-coded provider dependency. Provider lock-in is a dealbreaker. env-var config is the industry baseline | LOW | `DIAGNOSTICER_PROVIDER` (anthropic\|openai), `DIAGNOSTICER_MODEL`, `DIAGNOSTICER_API_KEY`. Provider-switching must not require code changes |
| Graceful failure handling | LLM calls fail (rate limits, timeouts, provider outages). If the button breaks the UI or returns an unhandled 500, users lose trust in the whole platform | LOW | Return structured error response: `{"status": "diagnosis_failed", "reason": "llm_error\|timeout\|context_too_large"}`. UI renders a dismissible error state, not a broken panel |
| Tenant isolation on diagnoses | Diagnoses contain full span context including prompt text and response text. A tenant data leak here is a critical trust failure | LOW | `tenant_id` on `diagnoses` table + PostgreSQL RLS. Presenter must validate tenant_id from JWT matches span's tenant before calling Diagnosticer |

### Differentiators (Competitive Advantage)

These features make the Xeter Diagnosticer meaningfully better than a generic LLM chat with pasted trace data.
No competitor implements any of these as an integrated product feature.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Three-category verdict (model / architecture / prompt) | The only structured root-cause taxonomy built specifically for tool-call failures. Langfuse, Phoenix, LangSmith — none of them do this. Developers currently guess which to fix first | MEDIUM | This is Xeter's stated core value per PROJECT.md. The taxonomy maps directly to actionable fixes: model → upgrade or swap model; architecture → change tool routing logic; prompt → rewrite instructions. Must be the primary output |
| Flag-informed context assembly | The LLM diagnosis is seeded with Xeter's heuristic flag scores (cosine similarity values per dimension). This gives the LLM signal that a human-annotator would otherwise have to construct manually | MEDIUM | Pass `flag_type`, `score`, `detail` for every flag on the span. The LLM uses these as structured evidence rather than doing unguided pattern-matching on raw text |
| `affected_field` granularity | Naming the specific span field that caused the failure (e.g., `tool_description`, `system_prompt`, `tool_args`) turns a categorical verdict into an actionable edit target | LOW | Enumerate the set: `system_prompt`, `user_prompt`, `tool_name`, `tool_description`, `tool_args`, `model_output`, `agent_logic`. Prompt the LLM to choose one. Store as string for extensibility |
| Hard negative constraint in prompt | Instructing the LLM to return `verdict: "inconclusive"` when evidence is insufficient prevents hallucinated diagnoses that erode trust. Google Auto-Diagnose validated this pattern in production (52k executions) | LOW | Add explicit instruction: "If the flags and span data do not provide sufficient evidence to identify a root cause, return verdict: inconclusive and explain what additional context would be needed." |
| `raw_llm_output` stored alongside structured fields | Storing the full LLM response text lets developers see the LLM's reasoning, not just the structured fields. This builds trust and enables future improvement of the diagnosis prompt | LOW | Single JSONB or TEXT column. Not displayed by default; available for developer inspection. Enables prompt iteration without losing history |
| Low-temperature structured output (JSON mode) | At temperature=0.1 with JSON mode enforced, the LLM reliably returns parseable output rather than prose. Google Auto-Diagnose uses temperature=0.1 validated at scale | LOW | Use provider JSON mode (OpenAI: `response_format={"type": "json_object"}`; Anthropic: explicit JSON instructions in prompt + system prompt). Parse with Pydantic model. Fallback to `inconclusive` on parse failure |

### Anti-Features (Commonly Requested, Often Problematic)

Features that sound like natural extensions of diagnosis but add scope without proportional value in v1.2.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Re-diagnose / force-refresh button | Users may want to re-run diagnosis after editing their prompt or updating tools | Adds UI state, a "stale" indicator, and mutation logic to a table that should be append-only. In v1.2, a span's diagnosis won't change because the span data is immutable. Re-diagnosis is only meaningful when the LLM model or prompt template changes — which is a config change, not a user action | In v1.2: diagnose once, serve cached. If the diagnosis prompt template changes in a future version, introduce `diagnosis_version` column and re-diagnose automatically. Don't build a UI toggle for this now |
| Multiple diagnoses per span (history) | Power users want to compare diagnosis quality across LLM providers | Requires version tracking, diff UI, and provider-comparison logic. This is a future research feature, not a debugging workflow | Store one diagnosis per span per `(span_id, tenant_id)`. If provider changes, the new diagnosis overwrites the old one in v1.2. Add versioning later when there is user evidence of need |
| User feedback on diagnosis (thumbs up/down) | RLHF-style feedback loop would improve diagnosis quality over time | Requires feedback storage, aggregation, and a retraining or prompt-refinement pipeline that doesn't exist. Collecting feedback without acting on it is worse than not collecting it (users feel ignored) | Defer. Build feedback collection only when there is a concrete plan to use it. "Log it for now" feedback stores are graveyard data |
| Batch diagnosis (diagnose all flagged spans) | Users want to run diagnosis across all flags at once | LLM costs scale linearly with span count. At $0.003/call and 10k flagged spans, a single batch run costs $30. Without cost controls, rate limit management, and background job UX, batch diagnosis is a support ticket waiting to happen | On-demand only in v1.2. Document that batch diagnosis is a future feature requiring background job infrastructure |
| Streaming LLM response (SSE) | Makes the diagnosis feel more "alive" while waiting 5-30 seconds | Streaming requires SSE infrastructure end-to-end (LLM provider → Diagnosticer → Presenter → View). The spinner-then-reveal pattern is acceptable for a 10-30s one-time operation. Streaming is a UX polish feature, not a correctness feature | Spinner + full response on completion. Streaming is a v1.3+ polish item |
| Explanation of the explanation (chain-of-thought display) | Some users want to see why the LLM chose a verdict | The LLM's reasoning chain is often inconsistent between runs and may confuse users more than inform them. Storing `raw_llm_output` (differentiator above) is a better middle ground | Store `raw_llm_output` and expose it as a "view reasoning" collapsible for developers who want it. Don't surface it as primary UI |
| LLM cost tracking per diagnosis | Developers want to know how much each diagnosis costs | Requires per-model pricing tables, token counting, and cost storage. High maintenance burden as model pricing changes frequently | Capture `prompt_tokens` and `completion_tokens` in the `diagnoses` table. Let users multiply by provider rates themselves. Don't own the cost math |
| Automatic diagnosis on every flagged span | Zero-click diagnosis sounds like a feature | Runs LLM on every span that gets flagged, including noise flags. At current flag precision ~95%, this is still 5% wasted LLM calls per run. More importantly, it removes developer agency — they can't batch their own review workflow | On-demand only. Developer clicks "Diagnose" when they want it. Auto-diagnosis can be a webhook/trigger feature in v2 for high-value customers |

---

## Feature Dependencies

```
[Diagnoses PostgreSQL table + DAL]
    └──required by──> [Diagnosticer: cache check]
    └──required by──> [Presenter: GET /diagnose result]
    └──required by──> [SpanDetailPanel: diagnosis display]

[LLM context assembly]
    └──requires──> [Flags from PostgreSQL] (already exists)
    └──requires──> [Span metadata from ClickHouse] (already exists)
    └──requires──> [S3 payload retrieval] (already exists)

[Diagnosticer LLM call]
    └──requires──> [LLM context assembly]
    └──requires──> [Configurable provider (env vars)]
    └──requires──> [Structured output parsing (Pydantic)]

[Presenter POST /diagnose — trigger]
    └──requires──> [Diagnoses table cache check]
    └──requires──> [Diagnosticer LLM call (if not cached)]
    └──requires──> [Tenant isolation check] (JWT → tenant_id)

[Presenter GET /diagnose/:span_id — retrieve]
    └──requires──> [Diagnoses table]

[SpanDetailPanel "Diagnose" button]
    └──requires──> [Presenter POST /diagnose endpoint]
    └──requires──> [Span detail already loaded] (already exists)

[SpanDetailPanel diagnosis display]
    └──requires──> [Presenter GET /diagnose/:span_id]
    └──enhances──> [SpanDetailPanel flag display] (already exists)
```

### Dependency Notes

- **Context assembly requires all three data sources:** Flags alone produce shallow diagnoses ("you had a wrong_tool flag"). Span metadata alone produces generic diagnoses. S3 payload alone produces analysis without structure. All three together let the LLM reason with evidence.

- **Cache check must happen in Presenter before proxying:** The Presenter (not the Diagnosticer) should check the `diagnoses` table first and short-circuit the proxy call. This keeps the Diagnosticer stateless (it never reads from PostgreSQL) and matches the existing architecture where Presenter owns PostgreSQL reads.

- **Diagnosticer remains stateless:** Diagnosticer receives assembled context (flags, span fields, payload text), calls the LLM, returns structured JSON. It does not read from ClickHouse or PostgreSQL. Context assembly is the Presenter's responsibility via DAL calls before proxying.

- **SpanDetailPanel display requires a GET endpoint, not just POST:** The POST trigger returns the diagnosis result, but a GET endpoint is needed for re-loading the panel after navigation. Both are required.

---

## MVP Definition

### Launch With (v1.2 — Diagnosticer milestone)

Minimum set for the diagnosis feature to deliver value and be trusted.

- [ ] `diagnoses` PostgreSQL table with RLS — required for persistence and tenant isolation
- [ ] Diagnoses DAL — insert and fetch by (span_id, tenant_id)
- [ ] LLM context assembly in Presenter — fetch flags, span metadata, S3 payload; build structured prompt
- [ ] Configurable LLM provider via env vars — Anthropic and OpenAI at minimum
- [ ] Diagnosticer: receive assembled context, call LLM, parse structured output, return result
- [ ] Hard negative constraint in LLM prompt — return `verdict: inconclusive` when evidence is insufficient
- [ ] Presenter cache check before LLM call — return stored result if diagnosis already exists
- [ ] Presenter POST /diagnose endpoint (full, not scaffold) — triggers or returns cached diagnosis
- [ ] Presenter GET /diagnose/:span_id endpoint — retrieve stored diagnosis
- [ ] SpanDetailPanel "Diagnose" button — triggers POST /diagnose
- [ ] SpanDetailPanel diagnosis display — shows verdict, severity, affected_field, recommended_fix inline
- [ ] Graceful error states in UI — spinner while running, error message on failure, no broken panel states

### Add After Validation (v1.3+)

- [ ] `raw_llm_output` "view reasoning" collapsible — add when users ask why the LLM chose a verdict
- [ ] `prompt_tokens` + `completion_tokens` capture — add when token cost visibility is requested
- [ ] Streaming LLM response (SSE) — add if 10-30s wait is reported as a UX problem in user feedback
- [ ] `diagnosis_version` column for prompt template versioning — add when the diagnosis prompt template is iterated for the first time

### Future Consideration (v2+)

- [ ] User feedback (thumbs up/down) on diagnosis — defer until there is a prompt improvement pipeline to consume it
- [ ] Batch diagnosis via background job — defer until cost controls and job queue infrastructure exist
- [ ] Multiple diagnoses per span (history/comparison) — defer until users demonstrate multi-provider comparison need
- [ ] Auto-diagnosis on flag creation webhook — defer until high-value customers request zero-click workflow

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Structured diagnosis output (verdict/severity/fix) | HIGH | MEDIUM | P1 |
| `diagnoses` PostgreSQL table + RLS | HIGH | LOW | P1 |
| Diagnoses DAL (insert + fetch) | HIGH | LOW | P1 |
| LLM context assembly (flags + span + S3) | HIGH | MEDIUM | P1 |
| Configurable provider via env vars | HIGH | LOW | P1 |
| Diagnosticer LLM call + JSON parsing | HIGH | MEDIUM | P1 |
| Hard negative constraint (inconclusive verdict) | HIGH | LOW | P1 |
| Presenter cache check before LLM call | HIGH | LOW | P1 |
| Presenter POST /diagnose (full) | HIGH | LOW | P1 |
| Presenter GET /diagnose/:span_id | HIGH | LOW | P1 |
| SpanDetailPanel "Diagnose" button + spinner | HIGH | LOW | P1 |
| SpanDetailPanel diagnosis display | HIGH | LOW | P1 |
| Graceful error handling (UI + backend) | HIGH | LOW | P1 |
| Tenant isolation check (JWT → tenant_id) | HIGH | LOW | P1 |
| `raw_llm_output` stored (not displayed) | MEDIUM | LOW | P1 |
| `raw_llm_output` "view reasoning" collapsible | MEDIUM | LOW | P2 |
| `prompt_tokens` + `completion_tokens` capture | LOW | LOW | P2 |
| Streaming LLM response (SSE) | LOW | HIGH | P3 |
| User feedback on diagnosis | LOW | MEDIUM | P3 |
| Batch diagnosis (background job) | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for v1.2 launch
- P2: Should have, add in v1.3 when validated
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

No competitor currently implements on-demand structured root-cause diagnosis for agent tool-call failures.
The closest analogues are summarized below.

| Feature | Langfuse | LangSmith (Polly) | Arize Phoenix | HoneyHive | Google Auto-Diagnose | Xeter Diagnosticer |
|---------|----------|-------------------|---------------|-----------|---------------------|-------------------|
| On-demand LLM root cause per span | No | Partial (Polly AI assistant, not structured) | No | No | Yes (integration tests, not agents) | Yes — v1.2 |
| Structured output (verdict + severity + fix) | No | No | No | No | Partial (Conclusion + Steps + Log Lines) | Yes — model\|arch\|prompt taxonomy |
| Three-category root cause taxonomy | No | No | No | No | No | Yes — unique |
| Seeded with heuristic flag scores | N/A | N/A | N/A | N/A | N/A | Yes — flags as evidence |
| `affected_field` granularity | No | No | No | No | No | Yes |
| Hard negative / inconclusive verdict | No | No | No | No | Yes (validated at 52k executions) | Yes (adopting Google pattern) |
| Cached result (no redundant LLM calls) | N/A | N/A | N/A | N/A | Not documented | Yes |
| Configurable provider | N/A | No (OpenAI) | N/A | N/A | Gemini-only | Yes — env var config |

**Key insight:** No existing tool combines heuristic flag scores with LLM-powered structured diagnosis.
The closest production validation is Google's Auto-Diagnose, which confirms the "hard negative constraint"
and low-temperature JSON output patterns work at scale. Xeter's taxonomy (model\|architecture\|prompt)
is not derived from any competitor — it is the novel differentiator.

---

## Sources

- Google Auto-Diagnose production report (52,635 tests, Gemini 2.5 Flash, temperature=0.1): https://www.marktechpost.com/2026/04/17/google-ai-releases-auto-diagnose-an-large-language-model-llm-based-system-to-diagnose-integration-test-failures-at-scale/ (MEDIUM confidence — secondary report; validates temperature + hard negative pattern)
- Langfuse error analysis guide (2025) — two-phase categorization, custom Score configurations: https://langfuse.com/blog/2025-08-29-error-analysis-to-evaluate-llm-applications (HIGH confidence — official Langfuse blog)
- HoneyHive LLM evaluators — boolean/numeric/string return types, custom passing ranges: https://docs.honeyhive.ai/evaluators/llm (MEDIUM confidence — official docs, no structured diagnosis output)
- LangSmith Polly AI assistant for agent debugging (2025): https://blog.langchain.com/debugging-deep-agents-with-langsmith/ (MEDIUM confidence — official LangChain blog)
- Latitude AI agent failure detection framework — tool selection errors, argument errors, chained corruption: https://latitude.so/blog/ai-agent-failure-detection-guide (MEDIUM confidence — vendor blog, cross-referenced with Arize taxonomy)
- LLM-as-a-Judge structured output patterns — JSON mode, temperature sensitivity: https://wandb.ai/site/articles/exploring-llm-as-a-judge/ (MEDIUM confidence — W&B official article)
- Multi-agent system failure taxonomy (MAST research): https://openreview.net/pdf?id=fAjbYBmonr (HIGH confidence — peer-reviewed; validates that system design failures dominate over model failures)
- LLM Observability complete guide 2026: https://portkey.ai/blog/the-complete-guide-to-llm-observability/ (LOW confidence — vendor aggregator; used only for baseline feature inventory)

---
*Feature research for: LLM-powered root-cause Diagnosticer (Xeter v1.2)*
*Researched: 2026-04-20*

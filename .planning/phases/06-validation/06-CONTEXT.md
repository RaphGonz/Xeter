# Phase 6: Validation - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Embedding thresholds are calibrated against labelled spans, critical infrastructure invariants are confirmed under load, cross-tenant isolation is verified, and the system is ready to trust before being presented to users. No new features — this phase validates all prior work against real runtime behaviour.

</domain>

<decisions>
## Implementation Decisions

### Labelled Dataset
- Synthetic generation — script creates spans with known-good and known-bad tool calls, labels baked in
- 30% flagged / 70% clean ratio to approximate realistic production distribution
- Cover all anomaly types the worker supports (wrong tool, missing args, hallucinated tool, etc.)
- Committed as a JSONL fixture file in the repo — reproducible, reviewable, version-controlled
- Calibration harness reads from the fixture, does not generate on-the-fly

### Calibration Process
- Optimize for precision — minimize false positives to avoid alert fatigue in a developer monitoring tool
- Minimum precision target: 80% (at most 1 in 5 flags is a false positive)
- Produce a visual precision/recall curve (PNG or HTML) alongside the threshold value — documents rationale
- Script auto-updates the threshold config file; developer reviews the diff before committing

### Load Test Design
- Multi-tenant simulation: 3-5 tenants sending spans concurrently at 500 spans/sec total for 60 seconds
- Realistic payloads with actual prompt/response content, tool calls, and varied sizes
- Pass criteria: zero ClickHouse errors (no "Too Many Parts") AND ingestion latency under 200ms p95
- Custom async Python script (aiohttp/httpx) — stays in project language, no external load testing framework

### Test Execution
- All validation runs against `docker compose up` — same environment as development, no extra infra
- Single runner script that executes calibration, load test, isolation test, and e2e latency check in sequence
- Console output + VALIDATION-REPORT.md summary file with thresholds, latencies, counts, and pass/fail
- Continue-all mode: every validation step runs regardless of prior failures; final report shows all results

### Claude's Discretion
- Exact structure of the synthetic span generator
- Precision/recall chart library choice
- Load test ramp-up profile and connection pooling
- VALIDATION-REPORT.md exact format and structure

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-validation*
*Context gathered: 2026-04-02*

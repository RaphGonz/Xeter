# Requirements — v1.6 Release

## Milestone Goal

Ship Xeter publicly: apply a license, clean up dev artifacts, improve the diagnosticer prompt, and produce exhaustive documentation covering installation, deployment, the SDK, all 24 detection checks, calibration, pluggable LLM configuration, and performance optimization hints.

---

## v1.6 Requirements

### Licensing

- [ ] **LICENSE-01**: A `LICENSE` file exists at repo root containing GPL-3.0 full text followed by a Commons Clause 1.0 addendum that explicitly prohibits selling Xeter as a service
- [ ] **LICENSE-02**: SPDX license identifier header (`SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0`) added to all top-level Python source files across analyser, presenter, worker, diagnosticer, and SDK
- [ ] **LICENSE-03**: README displays a license badge linked to the LICENSE file

### Assets & Housekeeping

- [ ] **ASSETS-01**: `assets/` folder created at repo root; `logo+typo.png` moved from root to `assets/logo+typo.png`; `.gitignore` and any path references updated
- [ ] **CLEAN-01**: `check_tier4.py` deleted from repo root (dead calibration dev script, no longer needed)
- [ ] **CLEAN-02**: `VALIDATION-REPORT.md` deleted from repo root (stale dev artifact, not part of public release)

### Diagnosticer Prompt

- [ ] **DIAG-01**: Inline prompt string extracted from `xeter/services/diagnosticer/context_assembly.py:_format_context()` into a dedicated file `xeter/services/diagnosticer/prompt.md`; `_format_context()` reads the file at import time and substitutes span data into it
- [ ] **DIAG-02**: Extracted prompt rewritten with: (a) a system message section that frames the diagnosticer role, (b) a chain-of-thought scaffold that walks through each flag before reaching a verdict, (c) explicit decision criteria for the four verdicts (`model` / `architecture` / `prompt` / `unknown`), and (d) guidance on severity calibration

### Documentation

- [ ] **DOCS-01**: README displays a banner image (`assets/logo+typo.png`) at the top followed by a one-sentence tagline and a license badge
- [ ] **DOCS-02**: README contains a **Quick Start** section covering local install (Python env + Docker Compose) with exact commands: `generate-secrets.sh`, `docker compose up`, health-check verification
- [ ] **DOCS-03**: README contains an **SDK** section showing how to instrument an agent: install, `@xeter_sdk.trace` decorator usage, env vars (`XETER_ENDPOINT`, `XETER_API_KEY`), and a minimal working example
- [ ] **DOCS-04**: README contains a **Detection Checks** section with a table of all 24 flag types: flag type, analyzer class, description, threshold type (binary / tunable), and default threshold value where applicable
- [ ] **DOCS-05**: README contains a **Calibration** section explaining how to reset thresholds, add fixture spans, run `calibrate.py --flag-type <type>` on real data, and apply the output to `docker-compose.yml` via `WORKER_THRESHOLD_*` env vars
- [ ] **DOCS-06**: README contains a **Pluggable LLM** section listing the three supported providers (Anthropic, OpenAI, Ollama), the env vars to configure each (`DIAGNOSTICER_PROVIDER`, `DIAGNOSTICER_MODEL`, `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `OLLAMA_BASE_URL`), and a note on using local models via Ollama
- [ ] **DOCS-07**: README contains a **Performance & Optimization** section covering: embedding model swap guidance (model size vs latency tradeoff), `WORKER_TRACE_FLUSH_TIMEOUT_S` tuning, Redis queue sizing, disabling unused analyzers via env flag, and ClickHouse retention policy

---

## Future Requirements

- TypeScript/Node.js SDK for JS-based agents (SDK-F01) — deferred from v1.5
- Refresh token revocation store (AUTH-F01) — server-side blacklist
- python-jose → PyJWT migration (AUTH-F02)
- Rate limiting on Analyser ingestion (OPS-F01) — per-API-key sliding window, 429 + Retry-After

---

## Out of Scope (v1.6)

- New detection modes — v1.5 shipped 24 flag types; calibration is settled
- Dashboard UI changes — docs-only release
- New LLM provider integrations — three providers are sufficient for release
- Clerk auth migration — deferred per AD-14
- Per-tenant Redis queue keys — deferred per OPS-F02

---

## Traceability

| REQ-ID | Phase | Status | Notes |
|--------|-------|--------|-------|
| LICENSE-01 | 29 | Pending | |
| LICENSE-02 | 29 | Pending | |
| ASSETS-01 | 29 | Pending | |
| CLEAN-01 | 29 | Pending | |
| CLEAN-02 | 29 | Pending | |
| DIAG-01 | 30 | Pending | |
| DIAG-02 | 30 | Pending | |
| LICENSE-03 | 31 | Pending | Part of README |
| DOCS-01 | 31 | Pending | |
| DOCS-02 | 31 | Pending | |
| DOCS-03 | 31 | Pending | |
| DOCS-04 | 31 | Pending | |
| DOCS-05 | 31 | Pending | |
| DOCS-06 | 31 | Pending | |
| DOCS-07 | 31 | Pending | |

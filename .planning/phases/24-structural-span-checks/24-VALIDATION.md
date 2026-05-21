---
phase: 24
slug: structural-span-checks
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-21
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `xeter/pyproject.toml` — `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| **Quick run command** | `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py -x -q` |
| **Full suite command** | `python -m pytest xeter/tests/ -q` |
| **Estimated runtime** | ~10 seconds (unit tests only, no DB) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py -x -q`
- **After every plan wave:** Run `python -m pytest xeter/tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 24-01-01 | 01 | 1 | SCHEMA-01 | — | N/A (test scaffold) | unit | `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 24-01-02 | 01 | 1 | SCHEMA-02, SCHEMA-04, CTX-01 | — | N/A (test scaffold) | unit | `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 24-01-03 | 01 | 1 | SCHEMA-03, D-04, D-06 | — | N/A (test scaffold) | unit | `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 24-02-01 | 02 | 2 | SCHEMA-01, SCHEMA-03 | — | Malformed JSON is caught, not raised | unit | `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py -x -k "schema_violation or output_truncated"` | ❌ W0 | ⬜ pending |
| 24-02-02 | 02 | 2 | SCHEMA-02, SCHEMA-04, CTX-01 | — | Schema validator exceptions are caught; token count never propagates exception | unit | `python -m pytest xeter/tests/worker/test_output_schema_analyzer.py -x` | ❌ W0 | ⬜ pending |
| 24-03-01 | 03 | 3 | CTX-01 | — | OutputSchemaAnalyzer imported without crash | unit | `python -c "import importlib; import xeter.services.worker.main"` | ✅ | ⬜ pending |
| 24-03-02 | 03 | 3 | SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04, CTX-01 | — | calibrate.py registry accepts 5 new keys | unit | `python -c "from xeter.scripts.calibrate import FLAG_TYPE_TO_ANALYZER_CLASS; assert len(FLAG_TYPE_TO_ANALYZER_CLASS) == 12"` | ✅ | ⬜ pending |
| 24-03-03 | 03 | 3 | D-05 | — | N/A (routing test update) | unit | `python -m pytest xeter/tests/test_calibrate_routing.py -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `xeter/tests/worker/test_output_schema_analyzer.py` — covers all SCHEMA-01 through CTX-01 check behaviors (created by plan 24-01)
- [ ] Extend `xeter/tests/test_calibrate_routing.py` — add tests for 5 new `FLAG_TYPE_TO_ANALYZER_CLASS` entries + 4 `BINARY_FLAG_TYPES` entries + `context_overflow` in `DEFAULT_THRESHOLDS` (done by plan 24-03)

*Existing `xeter/tests/test_calibrate_routing.py` covers the existing 7-entry registry. Needs extension but file exists.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

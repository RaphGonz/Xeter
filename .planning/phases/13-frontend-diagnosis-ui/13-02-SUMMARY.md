# Phase 13 Plan 02 — Summary

**Plan:** Visual E2E verification + debugging
**Status:** COMPLETE
**Date:** 2026-04-25

## What Was Done

### Debugging session (seeded spans not visible)
- Confirmed ClickHouse port 8123 exposed in docker-compose — not the issue
- Identified root cause: seed script uploaded payloads to `xeter-spans` bucket; Presenter reads from `xeter-payloads`
- Fixed `seed_spans.py` default from `xeter-spans` → `xeter-payloads`
- Fixed `.env` `MINIO_BUCKET` value and removed leading whitespace on LLM env var lines (docker-compose was silently ignoring them)

### Diagnosticer 503 → fixed
- Removed stale `get_async_engine` import and `engine.dispose()` from `diagnosticer/main.py` lifespan — `get_async_session_factory()` no longer takes an engine argument
- Fixed test fixture patching `get_async_engine` that no longer exists in the module

### Diagnosticer 401 → fixed
- Presenter was forwarding POST /diagnose to Diagnosticer without auth header
- Added `auth_header` parameter to `DiagnosisService.trigger()` and forwarded `request.headers.get("authorization")` to the Diagnosticer HTTP call

### Diagnosticer 500 → fixed
- `anthropic` and `openai` packages missing from Diagnosticer Docker image (built before they were added to pyproject.toml)
- Added `DIAGNOSTICER_PROVIDER`, `DIAGNOSTICER_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `SECRET_KEY` to Diagnosticer service env in docker-compose (previously missing — container had no LLM config)
- Rebuilt Diagnosticer image

### UX improvements
- Removed idempotency check from `DiagnosisService.trigger()` — POST /diagnose always calls Diagnosticer, allowing re-diagnosis/overwrite
- Enabled Diagnose button for clean spans (no flags) — removed disabled state and `FlagSection` gate; `FlagSection` now renders for all spans

### Tests
- Updated `test_diagnose.py`: replaced idempotency test with re-diagnosis test; fixed `get_latest_for_span` side_effect from `[None, diagnosis]` → `return_value=diagnosis`
- Updated `test_diagnose_endpoint.py`: removed `get_async_engine` patch, removed `_make_mock_engine` helper
- Updated 3 stale `test_tool_call_analyzer.py` tests to match current social-centroid implementation:
  - `test_unnecessary_tool_call_flag_score_is_called_tool_score` → rewrote for new centroid_score behavior
  - `test_unnecessary_tool_call_flagged_low_coherence` → updated to social_prompt metric + None centroid patch
  - `test_unnecessary_tool_call_flagged_via_analyze` → patched `_SOCIAL_CENTROID = None`
  - `test_wrong_args_flag_has_no_low_confidence` → replaced None embed mock with orthogonal vector

## Decisions Made

- Diagnose button always enabled (including clean spans) — false negatives are a valid reason to diagnose
- Re-diagnosis always overwrites — no idempotency; `diagnoses` table is append-only so history is preserved
- Auth forwarding: Presenter passes user's bearer token to Diagnosticer (shared SECRET_KEY validates it)

## Test Results

112 passed, 9 skipped, 0 failed

## Phase 13 Status: COMPLETE — v1.2 Diagnosticer milestone done

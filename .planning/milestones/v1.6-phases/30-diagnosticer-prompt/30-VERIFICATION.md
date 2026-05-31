---
phase: 30-diagnosticer-prompt
verified: 2026-05-31T00:00:00Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 30: Diagnosticer Prompt — Verification Report

**Phase Goal:** The diagnosticer prompt is a maintainable, human-readable file with structured reasoning guidance — not a raw string buried in Python source
**Verified:** 2026-05-31
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | prompt.md exists co-located with context_assembly.py and is read at module import time | VERIFIED | `xeter/services/diagnosticer/prompt.md` exists; line 36 of context_assembly.py: `_PROMPT_TEMPLATE: str = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")` |
| 2 | `_format_context()` contains no inline prompt f-string — it substitutes span data into the template read from prompt.md | VERIFIED | No `f"""` block in `_format_context`; line 149: `return _PROMPT_TEMPLATE.format_map({...})` |
| 3 | `_format_context()` preserves its signature `(span, flags, prompt_text, response_text) -> str` | VERIFIED | `inspect.signature` confirms params `['span', 'flags', 'prompt_text', 'response_text']` with return annotation `str`; `assemble_context()` at line 204 calls it unchanged |
| 4 | Importing context_assembly with prompt.md absent raises FileNotFoundError at import time | VERIFIED | `test_missing_prompt_file_raises` passes; patches `pathlib.Path.read_text` to raise and reloads the module — FileNotFoundError confirmed |
| 5 | The existing /diagnose endpoint tests still pass (no regression) | VERIFIED | `test_diagnose_endpoint.py`: 7 passed |
| 6 | prompt.md contains a system message section framing the diagnosticer's role as root-cause analysis | VERIFIED | Line 1–6 of prompt.md: "Your role is root-cause analysis"; "call `record_diagnosis` with the single most likely root cause" |
| 7 | prompt.md contains a chain-of-thought scaffold instructing the model to walk through each flag before reaching a verdict | VERIFIED | Lines 65–75 of prompt.md: "Reasoning Steps" section; "For each flag: what does this flag type indicate"; "each flag above" phrase present |
| 8 | prompt.md contains explicit decision criteria distinguishing all four verdicts: model, architecture, prompt, unknown | VERIFIED | Lines 8–34 of prompt.md: "Verdict Decision Criteria" section with one bulleted paragraph per verdict and distinguishing signals |
| 9 | prompt.md contains severity calibration guidance for high, medium, and low | VERIFIED | Lines 35–39 of prompt.md: "Severity Calibration" section defines all three levels |
| 10 | All nine span placeholders plus prompt_text, response_text, flags_section remain present — format_map substitution succeeds with no KeyError | VERIFIED | Programmatic check: all 12 required `{placeholder}` patterns found in `_PROMPT_TEMPLATE`; smoke render OK |
| 11 | The existing /diagnose endpoint tests and context assembly tests still pass | VERIFIED | Full diagnosticer suite: 16 passed (9 context assembly + 7 endpoint) |

**Score:** 11/11 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `xeter/services/diagnosticer/prompt.md` | Prompt template with `{variable}` placeholders, no SPDX header | VERIFIED | 76 lines; 12 `{placeholder}` references confirmed; first line is not `# SPDX` |
| `xeter/services/diagnosticer/context_assembly.py` | Import-time read + `_PROMPT_TEMPLATE` constant + `format_map` substitution | VERIFIED | Line 36: `_PROMPT_TEMPLATE` defined; line 149: `_PROMPT_TEMPLATE.format_map` call; no inline f-string prompt |
| `xeter/tests/diagnosticer/test_context_assembly.py` | 9 tests covering Plan 01 substitution/flags/FileNotFoundError (5) + Plan 02 content-presence (4) | VERIFIED | 9 `def test_` definitions; all 9 pass; SPDX header present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `context_assembly.py` | `prompt.md` | `Path(__file__).parent / 'prompt.md'` read at module level | WIRED | Line 36 of context_assembly.py; confirmed path-relative read |
| `context_assembly.py:_format_context` | `_PROMPT_TEMPLATE` | `.format_map(...)` substitution | WIRED | Line 149: `return _PROMPT_TEMPLATE.format_map({...})` |
| `prompt.md` | `anthropic.py:_DIAGNOSIS_TOOL` verdict enum | `record_diagnosis` tool name + all four verdict names present in prompt | WIRED | `record_diagnosis` appears 3 times; `model`, `architecture`, `prompt`, `unknown` all present |
| `test_context_assembly.py` | `_format_context` rendered output | string-presence assertions | WIRED | `TestPromptContent._render()` calls `context_assembly._format_context` and asserts on durable substrings |

---

### Data-Flow Trace (Level 4)

Not applicable — prompt.md is a static template file (not a component rendering dynamic DB-sourced data). The data flow from span fields through `format_map` into the rendered string is fully verified by the unit tests.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Smoke render of `_format_context` with stub span and empty flags | `python -c "... assert 's1' in out ... print('OK')"` | OK | PASS |
| Plan 02 render: root framing, record_diagnosis, four verdicts, severity levels all present | Programmatic check against rendered output | All 10 assertions passed | PASS |
| `_format_context` signature unchanged | `inspect.signature` | `['span', 'flags', 'prompt_text', 'response_text']` | PASS |
| Full diagnosticer test suite | `python -m pytest xeter/tests/diagnosticer/ -q` | 16 passed, 0 failed | PASS |

---

### Probe Execution

No probes declared or applicable for this phase (content + wiring change, no migration scripts).

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DIAG-01 | 30-01 | Inline prompt extracted to `prompt.md`; read at import time; span data substituted | SATISFIED | `_PROMPT_TEMPLATE` at module level; `format_map` in `_format_context`; 5 tests pass |
| DIAG-02 | 30-02 | Rewritten prompt: system message + CoT scaffold + four-verdict criteria + severity calibration | SATISFIED | All four required sections verified in prompt.md content; 4 content-presence tests pass |

No orphaned requirements — REQUIREMENTS.md maps only DIAG-01 and DIAG-02 to phase 30, both addressed.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `test_context_assembly.py` | 112 | Comment contains "placeholder" | Info | In-code comment explaining what `{placeholder}` references are; not a stub indicator — the test is substantive |

No TBD, FIXME, or XXX markers. No stub returns. No empty implementations. The "placeholder" match on line 112 is a code comment describing `{variable}` syntax, not a deferred implementation.

---

### Human Verification Required

None. All must-haves are programmatically verifiable and have been verified.

---

### Gaps Summary

No gaps. All 11 must-have truths are verified, all artifacts are substantive and wired, all key links are active, both requirement IDs are satisfied, and the full diagnosticer test suite (16 tests) passes with no regressions.

---

_Verified: 2026-05-31_
_Verifier: Claude (gsd-verifier)_

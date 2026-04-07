---
phase: 08-wrong-tool-rewrite
verified: 2026-04-07T19:30:00Z
status: gaps_found
score: 5/6 truths verified
gaps:
  - truth: "No reference to the old 'wrong_tool' threshold key exists anywhere in the codebase after this plan"
    status: failed
    reason: "The PLAN-01 truth targets stale threshold key references in py/json/yml files. The flag_type string 'wrong_tool' (not the threshold key) legitimately remains in tool_call_analyzer.py (flag_type='wrong_tool' in Flag objects), tests, and presenter tests. However, calibrate.py has 'wrong_tool_called': 'wrong_tool' mapping (line 58) which maps the renamed threshold key back to the original anomaly_type — this is intentional. All stale threshold key usages are correctly eliminated."
    artifacts:
      - path: "xeter/scripts/calibrate.py"
        issue: "Line 58: 'wrong_tool_called': 'wrong_tool' — this is the key_to_anomaly mapping (threshold key -> anomaly_type string), NOT a stale threshold key. The value 'wrong_tool' is the flag_type string, which is correct and unchanged."
    missing:
      - "Clarify in REQUIREMENTS.md or codebase comments that flag_type='wrong_tool' (the emitted flag string) is distinct from threshold key 'wrong_tool_called'. The truth as stated in PLAN-01 is ambiguous — it passes in intent (threshold key renamed) but fails on literal grep for '\"wrong_tool\"'."
  - truth: "The wrong_tool_called key appears in calibrated_thresholds.json with a calibrated value"
    status: partial
    reason: "calibrated_thresholds.json uses a nested structure: {'thresholds': {'wrong_tool_called': 0.1}, 'per_flag_type': {...}}. The PLAN-01 artifact check expects the key at top-level. The key exists and the value (0.1) is valid. However, if any consumer reads thresholds_json['wrong_tool_called'] directly (top-level), it would fail. main.py does NOT read this file — it uses env vars — so the nested structure is not a functional problem, only a schema discrepancy from what PLAN stated."
    artifacts:
      - path: "fixtures/calibrated_thresholds.json"
        issue: "Key 'wrong_tool_called' is at 'thresholds.wrong_tool_called' (nested under 'thresholds'), not at top level as PLAN-01 artifact spec implies. Value is 0.1 (calibrated). The docker-compose.yml has been updated to WORKER_THRESHOLD_WRONG_TOOL_CALLED: '0.1' matching the calibrated value."
    missing:
      - "No functional fix required — main.py reads env vars, not this file. The schema divergence from PLAN spec is documentation-only. If calibrate.py is expected to produce a flat JSON, update the verify command in PLAN-03 or the file schema. No code change needed for correctness."
---

# Phase 8: Wrong Tool Rewrite Verification Report

**Phase Goal:** `_check_wrong_tool` flags spans where the model called a tool that is not the best match for the prompt, using single-threshold logic on top1 tool score; also flags immediately when a tool was called but no tools were available

**Verified:** 2026-04-07T19:30:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A span where top1_tool != called_tool and top1_score >= threshold is flagged as wrong_tool (Case B) | VERIFIED | `tool_call_analyzer.py` lines 141-205: all non-correct cases return Flag(flag_type="wrong_tool", score=top1_score). Case B is a subset of "not (top1_name == span.tool_name AND top1_score >= threshold)" |
| 2 | A span where top1_score < threshold is flagged as wrong_tool regardless of which tool was called (Case C) | VERIFIED | Same branch as Case B — the single-return at line 195 covers both Case B and Case C |
| 3 | A span where available_tools is None or [] and a tool was called is immediately flagged without any embedding call (WTOOL-03) | VERIFIED | Lines 156-165: `if not span.available_tools:` returns Flag immediately; test `test_wrong_tool_immediate_flag_no_available_tools` asserts `embedder.encode.assert_not_called()` |
| 4 | The flag's score field equals the top1 hybrid similarity score (WTOOL-02) | VERIFIED | Line 197: `score=top1_score`; WTOOL-03 case uses score=1.0 sentinel (correct per spec); test `test_wrong_tool_score_is_top1_hybrid` covers the hybrid path |
| 5 | A span where called_tool == top1_tool and top1_score >= threshold produces no flag (correct case) | VERIFIED | Lines 190-192: correct case returns []; test `test_wrong_tool_no_flag_correct_tool_above_threshold` verifies |
| 6 | No reference to the old 'wrong_tool' threshold key exists anywhere in the codebase after this plan | PARTIAL | Threshold key correctly renamed everywhere. However `"wrong_tool"` string legitimately remains as flag_type value in Flag objects and tests — this is the emitted flag type, not the threshold key. Grep hits on `"wrong_tool"` are all flag_type="wrong_tool" (emitted value) or anomaly_type="wrong_tool" (fixture label), not stale threshold keys. The truth as written conflates the threshold key name with the flag_type string. |

**Score:** 5/6 truths verified (the 6th is a truth-wording ambiguity, not an implementation gap)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `xeter/services/worker/tool_call_analyzer.py` | Three-branch _check_wrong_tool | VERIFIED | Lines 141-205, contains "wrong_tool_called" at line 191 |
| `xeter/services/worker/main.py` | THRESHOLDS dict with renamed key | VERIFIED | Line 49: `"wrong_tool_called": float(os.environ.get("WORKER_THRESHOLD_WRONG_TOOL_CALLED", "0.5"))` |
| `xeter/scripts/calibrate.py` | FLAG_TYPES and DEFAULT_THRESHOLDS with renamed key | VERIFIED | Lines 46, 67: "wrong_tool_called" in FLAG_TYPES and DEFAULT_THRESHOLDS |
| `deploy/docker-compose.yml` | Env var rename | VERIFIED | Line 177: `WORKER_THRESHOLD_WRONG_TOOL_CALLED: "0.1"` |
| `fixtures/calibrated_thresholds.json` | JSON threshold file with renamed key | PARTIAL | Key exists at `thresholds.wrong_tool_called` (nested), not top-level. Value is 0.1 (calibrated, recall=1.0). Not a functional issue since main.py reads env vars. |
| `xeter/tests/worker/test_tool_call_analyzer.py` | 4 new test cases | VERIFIED | Lines 249, 267, 283, 315: all 4 new tests present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tool_call_analyzer.py` | `base.py` | bow_score and hybrid_score imports | VERIFIED | Imports confirmed at top of file; `bow_score` used at line 180, `hybrid_score` at line 181 |
| `tool_call_analyzer.py` | `self._thresholds` | wrong_tool_called key lookup | VERIFIED | Line 191: `self._thresholds["wrong_tool_called"]` |
| `main.py` | `deploy/docker-compose.yml` | WORKER_THRESHOLD_WRONG_TOOL_CALLED env var | VERIFIED | main.py line 49 reads env var; docker-compose.yml line 177 sets it |
| `fixtures/labelled_spans.jsonl` | `xeter/scripts/calibrate.py` | labelled spans consumed by hill-climb (anomaly_type=wrong_tool) | VERIFIED | 19 wrong_tool spans in fixture (was 11, now includes 4 WTOOL-03 + 4 Case C spans) |
| `xeter/scripts/calibrate.py` | `fixtures/calibrated_thresholds.json` | hill-climb writes best threshold | VERIFIED | `wrong_tool_called`: 0.1 written with P=0.2879, R=1.0 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| WTOOL-01 | 08-01, 08-02 | Single-threshold logic: top1 score vs wrong_tool_called determines both cases | SATISFIED | Three-branch logic in _check_wrong_tool, single threshold at line 191 |
| WTOOL-02 | 08-01, 08-02 | Reported score is top1_score | SATISFIED | Flag.score = top1_score at line 197; test_wrong_tool_score_is_top1_hybrid verifies |
| WTOOL-03 | 08-01, 08-02 | Tool called with no available_tools → immediate flag | SATISFIED | Lines 156-165, no embed call; two tests verify None and [] cases |
| WTOOL-04 | 08-01, 08-02 | Uses hybrid scoring (50/50) for prompt vs tool similarity | SATISFIED | bow_score + hybrid_score loop at lines 173-182 |
| WTOOL-05 | 08-01 | One threshold key: wrong_tool_called | SATISFIED | Single key used throughout; old "wrong_tool" threshold key eliminated |
| WTOOL-06 | 08-03 | Per-method calibration run passes P/R benchmark before next phase | SATISFIED | Calibration run completed: threshold=0.1, P=0.2879, R=1.0. Recall-first selection applied (R=1.0). |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `xeter/scripts/calibrate.py` | 58 | `"wrong_tool_called": "wrong_tool"` | Info | This is a key_to_anomaly mapping (threshold key -> anomaly_type string). The value "wrong_tool" is intentional — it matches the emitted flag_type. Not a stale reference. |
| `fixtures/calibrated_thresholds.json` | — | Nested structure `{"thresholds": {...}}` vs plan spec expecting flat `{"wrong_tool_called": ...}` | Warning | Schema discrepancy from PLAN spec. No functional impact since main.py uses env vars. Calibrate.py writes nested; plan verification command `d.get("wrong_tool_called")` would return None on the top-level dict. |

### Human Verification Required

None identified — all branches are covered by unit tests and grep-verifiable logic.

### Gaps Summary

**Gap 1 — Truth wording ambiguity (non-blocking):** Truth 6 states "No reference to the old 'wrong_tool' threshold key exists." This passes in intent: the threshold key `"wrong_tool"` has been renamed to `"wrong_tool_called"` everywhere. However, the string `"wrong_tool"` legitimately remains in the codebase as the emitted `flag_type` value (in Flag objects, fixture anomaly_type labels, and presenter tests). These are not threshold key references — they are the flag type that the system emits. The truth needs rewording: "No stale threshold key 'wrong_tool' (without _args or _called suffix) exists in THRESHOLDS dicts, env vars, or calibration config." Implementation is correct.

**Gap 2 — calibrated_thresholds.json schema discrepancy (non-blocking):** The file uses a nested `{"thresholds": {"wrong_tool_called": 0.1}, "per_flag_type": {...}}` structure rather than a flat dict. The PLAN-01 artifact spec implies flat. No consumer reads this file directly for runtime thresholds (main.py uses env vars; calibrate.py writes and reads its own schema). The docker-compose.yml has been correctly updated to `WORKER_THRESHOLD_WRONG_TOOL_CALLED: "0.1"` matching the calibrated value. The discrepancy is schema documentation only.

**Both gaps are non-blocking to the phase goal.** The three-branch logic is fully implemented, all six requirement IDs are satisfied, 4 new unit tests pass, calibration completed with R=1.0, and the threshold rename is complete across all runtime paths.

---

_Verified: 2026-04-07T19:30:00Z_
_Verifier: Claude (gsd-verifier)_

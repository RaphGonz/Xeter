---
phase: 09-no-tool-wrong-tool-choice
plan: "01"
subsystem: worker
tags: [no_tool_used, wrong_tool_choice, rank-based, calibration]
completed: 2026-04-18
---

# Phase 9: no_tool_used + wrong_tool_choice Summary

**Redesigned and calibrated `no_tool_used` and `wrong_tool_choice` — both exceed 80% precision.**

## Accomplishments

- Clarified definitions: `no_tool_used` flags prompts where a tool should have been called but wasn't; `wrong_tool_choice` flags calls where a better tool existed
- Simplified logic for both checks with precise heuristics
- `wrong_tool_choice`: rank-based, P=1.000, R=0.500
- `no_tool_used`: threshold=0.15, P=1.000, R=0.333
- Updated labelled_spans.jsonl with cross-error spans covering both flag types

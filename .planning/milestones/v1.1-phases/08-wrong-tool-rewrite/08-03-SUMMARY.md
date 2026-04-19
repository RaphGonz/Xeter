---
phase: 08-wrong-tool-rewrite
plan: "03"
subsystem: worker
tags: [calibration, wrong_tool_choice, rank-based]
completed: 2026-04-18
---

# Phase 8 Plan 03: Calibration Summary

**`wrong_tool_choice` is rank-based — P=1.000, R=0.500. No threshold sweep needed.**

## Accomplishments

- Confirmed `wrong_tool_choice` operates as a rank-based detector (no cosine threshold)
- Calibration result: P=1.000, R=0.500
- `wrong_tool_called` threshold key removed from calibration sweep; binary flag handling confirmed

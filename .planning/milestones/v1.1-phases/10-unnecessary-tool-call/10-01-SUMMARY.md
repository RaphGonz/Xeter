---
phase: 10-unnecessary-tool-call
plan: "01"
subsystem: worker
tags: [unnecessary_tool_call, social-centroid, calibration]
completed: 2026-04-18
---

# Phase 10: unnecessary_tool_call Summary

**Redesigned `unnecessary_tool_call` using social centroid heuristic — P=1.000, R=0.667 at threshold=0.25.**

## Accomplishments

- Renamed from `excessive_tool` to `unnecessary_tool_call` — flags tool calls made when no tool was needed
- Implemented social centroid signal: compares prompt embedding against centroid of social/phatic prompts
- Wired `social_centroid.npy` fixture; calibrated threshold=0.25
- Final result: P=1.000, R=0.667
- Updated labelled_spans.jsonl with cross-error spans; full suite mean precision ≥ 95%

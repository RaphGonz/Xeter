# Phase 8: wrong_tool Rewrite - Context

**Gathered:** 2026-04-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Rewrite `_check_wrong_tool` in `ToolCallAnalyzer` to use single-threshold logic on the top1 tool score, covering three distinct cases: tool called with no available tools (immediate flag), tool called when a better-ranked tool existed, and tool called when no tool was actually appropriate. The existing `wrong_tool_args` method and calibration infrastructure are not touched.

</domain>

<decisions>
## Implementation Decisions

### Detection logic (replaces two-gate approach)

Three cases, all flag as `wrong_tool`:

1. **No available_tools + tool called** — immediate flag, no threshold check. The agent called a tool when none were available.
2. **available_tools present, top1_tool != called_tool, top1_score >= wrong_tool_called** — a better tool existed and the ranking is trustworthy. Flag.
3. **available_tools present, top1_score < wrong_tool_called** — no tool was appropriate for the prompt; the agent shouldn't have called anything. Flag.

Correct case (no flag): `top1_tool == called_tool AND top1_score >= wrong_tool_called`.

### Threshold key

Single key: `wrong_tool_called`. Replaces the previously planned `wrong_tool_gap`, `wrong_tool_rank_floor`, and `wrong_tool_called` trio — these collapse to one. The old `wrong_tool` key is retired.

### Reported score

`top1_score` (the best available tool's hybrid similarity to the prompt). Not the gap.

### Hybrid scoring (WTOOL-04)

Use `hybrid_score` (50/50 cosine + BOW) for all prompt-vs-tool comparisons, consistent with Phase 7. Tool text = `name + " " + description` for both the cosine embedding (reuses `_get_tool_embeddings` cache) and the BOW computation. No change to cache structure needed.

### Calibration direction

Recall-first: maximize recall (minimize false negatives) as the primary objective. Precision should be as high as achievable given that goal. Rationale: users click flags to investigate — too many false positives erodes trust, but false negatives (missed wrongs) are invisible and more harmful. Both P and R reported after calibration run.

### Plan structure

3 plans:
- 08-01: wrong_tool rewrite
- 08-02: Algorithm review — user reviews implementation before calibration
- 08-03: Calibration run

### Claude's Discretion

- Exact BOW text construction when `description` is absent (fall back to name only)
- How to handle `tool_name` not found in the `available_tools` list (edge case — treat called_tool_score as 0)
- Logging metric names for calibration

</decisions>

<specifics>
## Specific Ideas

- "If a tool is called but none are available, it's an immediate flag" — no threshold, no score needed
- "Score all available tools including the called one, take top1 — if it's a different tool and score is above threshold, flag; if all scores are low, also flag"
- The algorithm review step (08-02) exists so the user can inspect and approve the implementation before calibration runs — this pattern applies to every phase

</specifics>

<deferred>
## Deferred Ideas

- detection_patterns.yml schema review (negation motifs + tool-triggering terms) — belongs in Phase 9 (tool_use_violation), already planned as 09-01

</deferred>

---

*Phase: 08-wrong-tool-rewrite*
*Context gathered: 2026-04-07*

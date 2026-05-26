# Phase 26: Best-Effort Proxy Checks - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-26
**Phase:** 26-best-effort-proxy-checks
**Areas discussed:** conversation_reset vs history_loss, AGENT_ROUTING_GRAPH config, incomplete_verification scope

---

## conversation_reset vs history_loss

| Option | Description | Selected |
|--------|-------------|----------|
| Same mechanism, lower threshold | Both check centroid cosine drop; conversation_reset fires at 0.25 vs 0.4. Two separate log_score() calls and threshold keys. | ✓ |
| Rolling window (local) vs full centroid (global) | conversation_reset uses last 3 prior prompts; history_loss uses all prior prompts. | |
| Collapse — skip conversation_reset | history_loss already covers the detection signal; mark TRACE-07 as covered by TRACE-04. | |

**User's choice:** Same mechanism, lower threshold (0.25 for conversation_reset vs 0.4 for history_loss)
**Notes:** User confirmed 0.25 as the starting threshold. Rationale: conversation_reset represents abrupt hard resets; history_loss is gradual drift. Same minimum span guard (< 3 spans, skip). Phase 27 calibration will tune.

---

## AGENT_ROUTING_GRAPH config

| Option | Description | Selected |
|--------|-------------|----------|
| Inline JSON env var | WORKER_AGENT_ROUTING_GRAPH env var holds JSON string. Parsed at startup in main.py. No-op if absent/empty. | ✓ |
| JSON file path env var | WORKER_AGENT_ROUTING_GRAPH_PATH points to a JSON file. Adds file dependency to Docker container config. | |
| Infer from observed order | No config. Worker builds graph from first-seen agent_name transitions per trace. | |

**User's choice:** Inline JSON env var
**Notes:** Consistent with existing env-var config pattern. Parsed in main.py (alongside THRESHOLDS). Injected into TraceAnalyzer.__init__ as optional `routing_graph=None` param.

| Follow-up: Unknown agent handling | Description | Selected |
|--------|-------------|----------|
| Always flag (whitelist) | Any agent not in graph = violation. Any valid source with invalid destination = violation. | ✓ |
| Skip silently | Only flag when source IS in graph but destination not in allowed list. | |
| You decide | Let planner choose most conservative option. | |

**User's choice:** Always flag — routing graph is a whitelist; any transition not explicitly allowed is a violation.

---

## incomplete_verification scope

| Option: Entities produced | Description | Selected |
|--------|-------------|----------|
| All responses across the trace | NEs from every prior span's response (before verification span). Full trace coverage. | ✓ |
| Immediately prior span's response only | NEs from span[verif_index - 1].response. Simpler but misses earlier outputs. | |
| All tool_outputs in the trace | Use tool_output (not response) as entity source. More precise for tool-calling agents. | |

**User's choice:** All responses across the trace

| Option: Verification scope | Description | Selected |
|--------|-------------|----------|
| Verification span's prompt | NEs in the verifier's prompt = what it was asked to check. | ✓ |
| Verification span's tool_output | NEs in verifier's tool_output = actual verification result. | |
| Both prompt + response of verification span | Union of NEs from prompt AND response. More permissive. | |

**User's choice:** Verification span's prompt

| Option: Threshold | Description | Selected |
|--------|-------------|----------|
| 0.7 (stricter) | Fire when verifier covers < 70% of produced entities. | ✓ |
| 0.5 (permissive) | Fire when verifier covers < 50% of produced entities. | |
| You decide | Let planner pick; Phase 27 calibration will tune. | |

**User's choice:** 0.7 — stricter start; Phase 27 calibration will tune.

---

## Claude's Discretion

- Starting threshold for `information_withholding` NE recall — suggest 0.5 (consistent with context_propagation_failure baseline)
- Starting threshold / binary classification for `wrong_agent_handoff` — topology check is deterministic (0.0/1.0 logged); planner picks
- `clarification_skipped` and `no_verification` implementation details — purely syntactic/keyword checks per REQUIREMENTS.md
- NE extraction method (`doc.ents` vs `doc.noun_chunks`) for `information_withholding` and `incomplete_verification` — planner decides based on signal quality

## Deferred Ideas

- Per-tenant AGENT_ROUTING_GRAPH — would require routing_graph to be keyed by tenant_id; out of scope for v1.5
- BINARY_FLAG_TYPES classification for Phase 26 checks — Phase 27 scope

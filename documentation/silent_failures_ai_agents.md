# Silent Failures in AI Agents — Master List

> Sources: IBM Research (arXiv 2511.04032), Berkeley MAST (NeurIPS 2025, arXiv 2503.13657), Microsoft AI Red Team Whitepaper (2025), Partnership on AI Report (2025), Xeter v1.1 Analyser Accuracy calibration (2026-04-18).

---

## A. Tool Use Failures

| ID | Name | Description |
|----|------|-------------|
| A1 | Wrong tool called | Semantically incorrect tool selected for the task — a better tool existed among the offered ones |
| A2 | No tool called when expected | Model produces a verbal answer instead of invoking a tool |
| A3 | Unnecessary tool call | Tool invoked in response to a social, phatic, or conversational prompt that warranted no tool use (e.g. "thanks!", "got it") |
| A4 | Tool call parsing error | Model generates a tool call in the wrong format for the executor; call is silently dropped or coerced |
| A5 | Tool output ignored | Tool returns a result; model proceeds as if it didn't |
| A6 | Silent tool failure | External API fails, rate-limits, or returns unexpected data; agent does not detect or handle it and continues as if successful |
| A7 | Wrong tool arguments | Correct tool called, but parameters are semantically unrelated to the prompt or contain values that evidence an API-level error |
| A8 | Hallucinated tool invocation | Model calls a tool that was never offered to it — not present in the available_tools list provided in the prompt, or no tool list was provided at all |

---

## B. Output / Schema Failures

| ID | Name | Description |
|----|------|-------------|
| B1 | Output schema not respected | Model returns free text when structured output was required |
| B2 | Required fields missing | Schema structure respected but fields are absent or null |
| B3 | Output truncated | Response cut before schema closes; downstream silently coerces |
| B4 | Type coercion errors | Number as string, boolean as integer; passes validation but is semantically wrong |

---

## C. Reasoning / Planning Failures

| ID | Name | Description |
|----|------|-------------|
| C1 | Task derailment | Agent drifts from the intended objective mid-execution, pursuing a subtask no longer relevant to the original goal |
| C2 | Premature termination | Agent stops before the task is complete and reports success |
| C3 | Step repetition | Agent repeats a step already performed without new information to justify it |
| C4 | Unaware of termination condition | Agent cannot determine when to stop; loops indefinitely or over-produces |
| C5 | Reasoning-action mismatch | The agent's stated reasoning does not match the action it actually takes |

---

## D. Context / Memory Failures

| ID | Name | Description |
|----|------|-------------|
| D1 | Context propagation failure | Failure to pass the correct context to dependent agents or tools |
| D2 | Loss of conversation history | Agent loses access to prior state mid-trace and restarts reasoning from an incomplete base |
| D3 | Context truncation / prompt overflow | Prompt exceeds model context window; older content is silently dropped |
| D4 | Memory poisoning | Malicious or incorrect instructions stored in memory are recalled and executed without detection |
| D5 | Stale context | Agent uses outdated information from a prior turn or tool call without re-querying |

---

## E. Instruction Following Failures

| ID | Name | Description |
|----|------|-------------|
| E1 | Disobey task specification | Agent ignores or partially ignores the declared task objective |
| E2 | Disobey role specification | Agent acts outside its declared role, taking actions that belong to another agent |
| E3 | Prompt injection / hijacking | Agent is subverted mid-task by malicious content in external tool outputs or retrieved data, without user intent |

---

## F. Multi-Agent / Handoff Failures

| ID | Name | Description |
|----|------|-------------|
| F1 | Wrong agent handoff | Agent routes to the wrong downstream agent; drift in the execution graph |
| F2 | Information withholding | An agent fails to pass necessary information to the next agent in the chain |
| F3 | Ignored agent input | A receiving agent ignores the output sent by the upstream agent and proceeds independently |
| F4 | Conversation reset | An agent resets the shared conversation state, losing prior context for all downstream agents |
| F5 | Fail to ask for clarification | Agent proceeds on an ambiguous instruction rather than requesting disambiguation, propagating the ambiguity downstream |
| F6 | Miscoordination / zero-shot failure | Agents sharing a mutual objective fail to align their behaviors, especially when they have no prior interaction history |

---

## G. Verification Failures

| ID | Name | Description |
|----|------|-------------|
| G1 | No verification | Agent produces output without any self-check or cross-check step |
| G2 | Incomplete verification | Agent checks a subset of the output and misses failures in unchecked fields |
| G3 | Incorrect verification | Agent performs a verification step but the verification itself is wrong, and the agent accepts the flawed output |

---

## H. Output Content Failures

| ID | Name | Description |
|----|------|-------------|
| H1 | Hallucination | Model produces factually incorrect content with no signal of uncertainty |
| H2 | Missing details | Agent returns a response without errors but omits information explicitly requested in the input |
| H3 | Confabulated tool output | Model fabricates a plausible tool result instead of calling the tool |
| H4 | Response-prompt semantic mismatch | Agent response is semantically unrelated to the prompt — the model answered a different question or drifted to an unrelated topic, with no explicit error |

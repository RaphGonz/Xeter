# excessive_tool Detection Signals — Research

**Researched:** 2026-04-06
**Confidence:** MEDIUM — primary signals derived from first-principles analysis of the codebase and supported by adjacent research (Self-RAG, Adaptive-RAG, DeepEval tool metrics). No published prior art was found that directly addresses span-local "tool necessity" detection using cosine similarity.

---

## Conceptual Distinction from wrong_tool

The two checks answer fundamentally different questions:

| Check | Question answered | Assumes a tool was... |
|---|---|---|
| `wrong_tool` | Was the right tool selected from the available set? | Necessary — a tool was appropriate, but the wrong one was chosen |
| `excessive_tool` | Was calling any tool at all warranted? | NOT necessary — the prompt could have been answered directly without any external call |

**At the semantic level:**

- `wrong_tool` compares the prompt to the *tool selection space* (available_tools ranking). Its signal is "another tool in the roster would have been a better match."
- `excessive_tool` should compare the prompt to the *concept of requiring external information or action*. Its signal is "this prompt does not need an external tool at all."

These two checks should be **mutually exclusive by design** (see section on double-flagging below).

---

## Current Approach Assessment

The current `_check_excessive_tool` computes:

```
cosine_similarity(embed(prompt), embed(tool_name))
```

And flags if this is below `thresholds["excessive_tool"]`.

**Why this overlaps with wrong_tool:**

Both checks detect "the prompt and the tool name don't match." In the no-available-tools fallback path of `_check_wrong_tool`, the same computation (`prompt vs tool_name`) is performed. Even with available_tools, a very low `prompt vs tool_name` score will often accompany a `wrong_tool` flag. The current `_check_excessive_tool` cannot distinguish between:

1. "You called `send_email` when you should have called `get_weather`" (wrong tool — a tool was needed)
2. "You called `get_weather` when you could have just said 'I don't know tomorrow's weather'" (excessive — no tool was needed)

The current check's score (`prompt vs tool_name`) does not encode the concept of "tool necessity." It encodes "tool name relevance," which is a `wrong_tool` signal.

---

## Recommended Signal

### Primary Signal: prompt vs "direct answer" reference embedding

The conceptually correct signal for excessive_tool is:

> "How much does this prompt look like something that can be answered without any external tool?"

The canonical approach used in Adaptive-RAG and Self-RAG literature is to compare a query against reference strings that represent "self-sufficient" or "tool-requiring" prompt types.

**Recommended implementation:**

Embed two reference strings and compute:

```python
direct_ref   = "answer this question directly from knowledge without calling any external tools"
tool_ref     = "use a tool or external system to complete this task or retrieve this information"
```

Then for the span:

```python
prompt_vec = embed(span.prompt)
direct_score = cosine_similarity(prompt_vec, embed(direct_ref))
tool_score   = cosine_similarity(prompt_vec, embed(tool_ref))
```

The `excessive_tool` signal is: `direct_score > tool_score` by a meaningful margin.

In practice, compute a **difference score**:

```python
necessity_delta = tool_score - direct_score
# Positive = prompt looks tool-requiring
# Negative = prompt looks self-answerable
```

Flag when `necessity_delta < thresholds["excessive_tool_delta"]` (i.e., when the prompt is more "direct answer" than "tool requiring"). This threshold will need calibration — start with `necessity_delta < 0.0` as the raw condition (direct beats tool) and tune from there.

**Why this works:**

all-MiniLM-L6-v2 is trained on semantic similarity and will cluster "What is the capital of France?" near "answer this question directly from knowledge" and away from "use a tool or external system to retrieve information." Action-oriented prompts ("Send a calendar invite for tomorrow at 3pm", "Look up the current price of AAPL") will cluster near the tool_ref string. This encodes tool necessity rather than tool name relevance.

**Score to log:** log `necessity_delta` as `"prompt_tool_necessity_delta"` so it joins the calibration dataset.

### Supporting Signal: prompt vs tool_output (HIGH value when available)

If `span.tool_output` is present, compute:

```python
output_overlap = cosine_similarity(embed(span.prompt), embed(span.tool_output))
```

A **high** `output_overlap` score is a red flag: it means the tool output is essentially paraphrasing the prompt — suggesting the information was already present and no retrieval was needed.

This is an independent signal from a different direction:
- `necessity_delta` looks at the prompt alone (was any tool warranted?)
- `output_overlap` looks at what the tool actually returned (did the tool contribute anything new?)

Both signals pointing in the same direction (prompt looks self-answerable AND tool returned nothing new) is a strong compound indicator of excessive tool use.

**Score to log:** `"prompt_vs_tool_output_overlap"`. Note this is only available when `span.tool_output is not None`.

### Signal priority

Use `necessity_delta` as the **primary gate** (it is always computable). Use `output_overlap` as a **secondary booster** — optionally included in the detail dict when available. Do not require both to fire.

---

## Avoiding Double-Flagging

### The core rule

`wrong_tool` and `excessive_tool` should never fire on the same span for the same underlying issue. They can conceptually co-exist (a span where no tool was needed AND the wrong tool was called anyway), but the signals must be non-overlapping in what they measure.

**How to enforce this structurally:**

Option 1 (recommended): **Mutual exclusion guard** — if `wrong_tool` has already fired on this span, skip `_check_excessive_tool`.

```python
def _check_excessive_tool(self, span: SpanData) -> list[Flag]:
    if span.tool_name is None:
        return []
    if span.prompt is None:
        return []
    # Skip if wrong_tool already flagged this span
    # (wrong_tool implies a tool was at least somewhat warranted)
    wrong_tool_fired = any(f.flag_type == "wrong_tool" for f in self._current_span_flags)
    if wrong_tool_fired:
        return []
    ...
```

This requires `analyze()` to accumulate flags incrementally and pass them, or for `_check_excessive_tool` to run after `_check_wrong_tool` and inspect the already-collected list.

Option 2: **Signal exclusivity** — by design, `wrong_tool` requires `available_tools` ranking disagreement (called tool != top-ranked tool). `excessive_tool` requires `necessity_delta < threshold`. These measure orthogonal things. A span where the correct tool was called but wasn't needed will only fire `excessive_tool`. A span where the wrong tool was chosen may or may not be excessive. In practice, signal exclusivity is weaker insurance than a structural guard.

**Recommendation:** Implement Option 1. It is explicit, testable, and aligns with the conceptual model: if a tool was clearly the wrong pick from the available set, diagnosing it as "excessive" adds noise. The developer should fix the selection first, then re-evaluate necessity.

The existing `analyze()` method runs checks in order:

```python
flags.extend(self._check_wrong_tool(span))   # runs first
...
flags.extend(self._check_excessive_tool(span))  # runs after
```

Pass the accumulating `flags` list (or a snapshot of it) into `_check_excessive_tool`, or have `analyze()` skip the call if `wrong_tool` was already appended.

---

## Structural vs Embedding Approaches

### Structural signals (non-embedding)

Several lexical/structural signals correlate with "direct answer" prompts:

| Pattern | Interpretation | Reliability |
|---|---|---|
| Prompt is a pure WH-question with no imperative verb ("What is...", "Who is...", "When did...") | Factual knowledge question — often self-answerable | MEDIUM — depends on domain |
| Prompt contains no imperative verbs at all (no "search", "fetch", "look up", "get", "send", "create") | Passive, knowledge-only | LOW — imperative verbs vary by domain |
| Prompt length < 15 tokens | Short query — likely direct | LOW — short action prompts exist ("Run the tests") |
| Tool name is a CRUD verb + noun pair ("create_ticket", "search_web", "send_email") | Tool is an action tool, not a knowledge lookup | LOW — doesn't tell you whether the action was warranted |

**Verdict on structural signals:** They are too noisy to use as primary signals. A prompt like "What is the weather in Paris today?" is a WH-question but legitimately needs a weather API tool. Structural signals can serve as cheap **pre-filters** to avoid embedding calls in obvious cases, but should not gate the final flag decision.

The embedding approach with reference strings is strictly better because all-MiniLM-L6-v2 encodes intent, not just surface syntax.

### Why embedding beats structural here

The Self-RAG and Adaptive-RAG literature reaches this same conclusion: binary classifiers (which can be as simple as "embedding vs reference string") outperform heuristic rule sets for retrieval necessity detection. Adaptive-RAG (2024) uses a fine-tuned T5-large classifier to route queries; the simpler embedding-vs-reference-string approach is the lightweight version of the same idea appropriate for Xeter's span-local, threshold-based architecture.

---

## Implementation Notes

### Reference string choices

The reference strings must be chosen carefully. all-MiniLM-L6-v2 is sensitive to phrasing. Recommended defaults:

```python
DIRECT_ANSWER_REF = (
    "answer this question directly from existing knowledge "
    "without calling any external tool or API"
)
TOOL_REQUIRED_REF = (
    "use a tool, API, or external system to perform this action "
    "or retrieve this information"
)
```

These are verbose on purpose: all-MiniLM-L6-v2 produces richer embeddings for longer, context-complete strings. Single-word references ("direct", "tool") produce near-random similarity scores.

### Threshold calibration strategy

`necessity_delta` (= `tool_score - direct_score`) will require calibration like all other thresholds. The existing calibration infrastructure (Phase 6, `calibrate.py`) can handle it. Initial threshold guess: `< -0.05` (direct beats tool by more than 5 percentage points). This should be conservative to avoid false positives.

The `output_overlap` score has a different calibration logic: a **high** score is suspicious (unlike most other checks where **low** is the flag). Log it as-is; the calibration script may need a "high-bad" variant noted in the threshold config.

### Signal naming

| Score | metric_name key | Direction |
|---|---|---|
| `necessity_delta` | `"prompt_tool_necessity_delta"` | Low (negative) = flag |
| `output_overlap` | `"prompt_vs_tool_output_overlap"` | High = suspicious (log only, secondary) |

### Span fields availability

- `span.prompt` — always required (guard at method entry)
- `span.tool_name` — always required (this check only runs when a tool was called)
- `span.tool_output` — optional; include overlap check only when not None
- `span.tool_description` — NOT recommended as a signal here; it encodes what the tool does (useful for wrong_tool), not whether the task needed it

### False positive risk

The main false positive scenario: a prompt like "What is the balance in my bank account?" — a WH-question that appears direct-answer but legitimately needs an API call. The `tool_required_ref` string should capture this because "retrieve this information" is semantically close to "What is my balance." Verify during calibration by reviewing flagged spans manually for this pattern.

### What not to use

- **prompt vs tool_name**: Do not use this in excessive_tool. It is already logged by `_check_wrong_tool` as `prompt_vs_tool_name` and using it here creates the same overlap the current implementation has.
- **prompt vs tool_description**: Same issue — this encodes wrong_tool territory.
- **prompt vs response**: This is `_check_response_anomaly`'s signal. It would create triple overlap.

---

## Sources

Research supporting these findings:

- [Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection](https://arxiv.org/abs/2310.11511) — Reflection tokens determine on-demand whether retrieval is necessary; conceptual basis for "tool necessity" as a query property
- [Understanding Adaptive-RAG](https://medium.com/@tuhinsharma121/understanding-adaptive-rag-smarter-faster-and-more-efficient-retrieval-augmented-generation-38490b6acf88) — T5-based classifier routes queries to "no retrieval / single retrieval / multi-step" based on query complexity; nearest equivalent to span-local tool necessity scoring
- [Adaptive Retrieval without Self-Knowledge?](https://arxiv.org/html/2501.12835) — Discusses limitations of binary retrieval-necessary classifiers; supports keeping the signal continuous (delta score) rather than binary
- [DeepEval Tool Correctness Metric](https://deepeval.com/docs/metrics-tool-correctness) — Deterministic comparison of tools_called vs expected_tools; requires ground truth. Not applicable to Xeter's zero-label design, but confirms the ecosystem frames "unnecessary calls" as a distinct metric from "wrong selection."
- [DeepEval AI Agent Metrics](https://deepeval.com/guides/guides-ai-agent-evaluation-metrics) — StepEfficiencyMetric penalizes redundant tool calls; operates at trace level (requires expected trajectory). Confirms trace-level is the standard — span-local detection is novel.
- [Is Cosine-Similarity of Embeddings Really About Similarity?](https://arxiv.org/abs/2403.05440) — Netflix/2024 research: cosine similarity is not uniformly reliable across all embedding models; confidence in the `necessity_delta` signal should remain MEDIUM until calibrated on real Xeter spans.
- [Observability and Evaluation Strategies for Tool-Calling AI Agents](https://www.getmaxim.ai/articles/observability-and-evaluation-strategies-for-tool-calling-ai-agents-a-complete-guide/) — Confirms span-level tool evaluation is an active area; no specific "necessity" signal documented at span granularity.

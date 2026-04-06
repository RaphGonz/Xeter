# wrong_tool Detection Signals — Research

**Domain:** LLM agent observability — tool-call anomaly detection
**Researched:** 2026-04-06
**Confidence:** MEDIUM (no single canonical source; synthesized from IR literature, embedding model docs, and observability platform patterns)

---

## Current Approach Assessment

The current implementation in `_check_wrong_tool` combines two conditions to fire:

```
span.tool_name != top_tool_name   # called tool lost the ranking
AND top_score < threshold         # top score is low
```

**What is conceptually wrong with this.**

The AND condition breaks the logic in a subtle way. When the top-ranked tool score is *high*, the flag is suppressed even if the called tool lost the ranking badly. This means: "Agent called `search_web` but `get_calendar` was ranked #1 with score 0.9 — no flag." That is the exact case that should be flagged. A high score for the top-ranked tool is evidence that the ranking signal is trustworthy, not a reason to suppress the flag.

The intended guard is against noise: when all tools have low similarity, the ranking becomes meaningless and a rank disagreement should not be flagged. That is a valid guard, but the threshold direction is inverted in the current code. It should be: "do not flag if the top score is so low that ranking cannot be trusted" — i.e., flag only when top_score is *above* some minimum trustworthiness floor, not below.

**Second problem: the signal being logged and scored is `top_score` (similarity of the top-ranked tool), not the similarity of the *called* tool.**

The flag score and detail report `top_score`, which is the score of the tool the model *should* have called. It tells the developer how good the best option looked, but not how bad the choice was. The more informative score for the flag is the similarity of the actually-called tool, plus the gap between them.

**Third problem: symmetric model used for asymmetric task.**

`all-MiniLM-L6-v2` is trained for symmetric sentence similarity (SBERT documentation explicitly distinguishes symmetric from asymmetric search). A prompt is typically a paragraph-length instruction. A tool name is 1-4 words. A tool description is 1-3 sentences. Comparing these directly with cosine similarity will systematically under-score because the vector directions will diverge in proportion to token count and vocabulary breadth differences. Concatenating `name + description` (as `_get_tool_embeddings` already does) partially mitigates this by giving the tool a richer representation, but the asymmetry with the prompt remains.

**Fourth problem: the fallback path (no available_tools) uses tool_name alone.**

Tool names are 1-4 tokens. Cosine similarity between a 200-token prompt and a 2-token name is almost always low regardless of relevance. This path will generate many false positives from the name comparison alone, and many false negatives when a vague name happens to share vocabulary with a common word in the prompt.

**Verdict: the approach is salvageable but needs the condition logic inverted, the scored value changed, and the signal decomposed into two explicit sub-signals.**

---

## Recommended Signals

### Signal 1 — Called-tool similarity (primary)

```
called_tool_score = cosine(prompt_vec, embed(called_tool_name + " " + called_tool_description))
```

This is the direct measure of fit between what the prompt requested and what tool was used. It answers: "did the called tool semantically match the prompt?" If this score is below a threshold, the tool was a poor fit, independent of what else was available.

**This is the foundational signal.** It does not require `available_tools`. It fires on clear misfits. It should be logged as `prompt_vs_called_tool`.

### Signal 2 — Rank position of the called tool (requires available_tools)

```
rank_scores = [(tool.name, cosine(prompt_vec, embed(tool.name + " " + tool.description)))
               for tool in available_tools]
rank_scores.sort(descending)
rank_of_called = position of span.tool_name in this list (0-indexed)
```

This answers: "given all available options, how far from the best was the agent's choice?" A rank of 0 means the agent picked the highest-scoring tool. A rank of 3 means it skipped three better options.

**Log this as `called_tool_rank`.** The flag score reported should be the rank (as a normalized value: `rank / (len(available_tools) - 1)` so it sits in [0, 1], where 0 = best choice).

### Signal 3 — Similarity gap between top-ranked and called tool (requires available_tools)

```
top_score  = rank_scores[0].score
called_score = score for span.tool_name from rank_scores
gap = top_score - called_score
```

This answers: "how much better was the best alternative?" A gap of 0.05 is negligible — models sometimes call near-equally-good tools. A gap of 0.30 means the prompt had a dramatically better match sitting unused.

**Log this as `wrong_tool_gap`.** This is the most informative single number for severity.

### Combining the signals

Use a two-gate approach rather than a single condition:

```python
# Gate 1: ranking is trustworthy (top score above minimum floor)
ranking_trustworthy = top_score > thresholds["wrong_tool_rank_floor"]

# Gate 2: the called tool lost the ranking by a meaningful margin
called_score = <score for span.tool_name in ranked list>
gap = top_score - called_score
significant_gap = gap > thresholds["wrong_tool_gap"]

# Flag if ranking is trustworthy AND the gap is significant
if ranking_trustworthy and significant_gap:
    flag(...)
```

When `available_tools` is absent, fall back to Signal 1 alone:

```python
if called_tool_score < thresholds["wrong_tool_called"]:
    flag(...)
```

**Why this is better than the current approach:**
- Flags when the agent chose a worse tool even if the best tool had a high score (the current approach suppresses this).
- Does not flag when all tools have low similarity (ranking is noise below the floor).
- Reports the gap as the score so the dashboard shows severity.
- The fallback path uses the called tool's full embedding (name + description), not just the name.

---

## Threshold Strategy

### Why fixed absolute thresholds are wrong for this check

Cosine similarity scores from `all-MiniLM-L6-v2` on prompt-vs-tool comparisons are not comparable across different prompt lengths, tool counts, or vocabulary domains. A prompt about "calendar scheduling" will score differently against tool descriptions than a prompt about "file system operations," even for equally correct tool calls. Fixed thresholds tuned on one domain will drift across tenants.

### Recommended: relative margin threshold for the gap signal

The gap between top-ranked and called tool is more stable than absolute scores because it is internal to one span — it compares the model's choice against the alternatives available at the same moment with the same prompt. Domain shifts affect all tools equally, so the gap is domain-invariant.

**Set `wrong_tool_gap` as a fixed value (e.g., 0.15) derived from calibration.** This means: "the called tool must be at least 0.15 below the best available option before we flag." Values below 0.10 produce too many marginal flags on near-equivalent tools. Values above 0.25 miss real misrouting.

### The rank_floor threshold

`wrong_tool_rank_floor` guards against flagging when all tools are semantically unrelated to the prompt (the ranking is unreliable). Set this around 0.20 — below this, the embedding space provides no trustworthy signal for discrimination.

### Calibration note

Both thresholds should be calibrated against real spans (as Xeter's existing calibration infrastructure supports). Log `called_tool_score`, `wrong_tool_gap`, and `called_tool_rank` for every span regardless of flag outcome. Examine the precision/recall curve at different gap values. The existing `calibrate.py` workflow applies directly.

---

## Failure Modes to Avoid

### Failure 1: Flagging on rank disagreement when tools are synonymous

Two tools `search_documents` and `find_files` with similar descriptions will have nearly identical cosine scores against any prompt. The agent calling one instead of the other is not wrong. If the gap check is too sensitive (gap threshold < 0.05), synonymous tools will generate spurious flags constantly.

**Prevention:** The gap threshold is the correct guard here. A gap below 0.10 should never flag. The rank alone is insufficient.

### Failure 2: Comparing tool_name tokens against a full-length prompt

Tool names are 1-4 tokens. `all-MiniLM-L6-v2` compresses 256 tokens into 384 dimensions. A two-word name carries almost no directional signal relative to a paragraph. Cosine similarity between a short name and a long prompt will be low for almost all semantically correct tool calls.

**Prevention:** Always embed `tool_name + " " + tool_description` as a unit. Never compare on name alone unless description is genuinely absent. The current `_get_tool_embeddings` already does this for the ranking path; the fallback path must be updated to match.

### Failure 3: Trusting ranking when the pool has only 2 tools

With two tools, every call is either rank 0 or rank 1. The gap may be large by chance because one description is simply a better string match. Flagging rank-1 calls in a two-tool pool will have a high false positive rate.

**Prevention:** Add a guard: only use the ranking signal when `len(available_tools) >= 3`. With 1 or 2 tools, fall back to Signal 1 (called_tool_score vs threshold) only.

### Failure 4: Called tool name not matching available_tools names exactly

If `span.tool_name` is `"search_web"` but available_tools contains `{"name": "SearchWeb", ...}`, the rank lookup will fail to find the called tool. The current code compares `span.tool_name != top_tool_name` with a direct string comparison.

**Prevention:** Normalize all tool names to lowercase (or another canonical form) before comparison and lookup. Log a warning if the called tool name is not found in the available_tools list — that may itself be a signal worth surfacing.

### Failure 5: The "AND low score" trap (existing bug)

As described in the assessment: `top_score < threshold` suppresses the flag when the top-ranked tool has a high score. This inverts the intended semantics.

**Prevention:** Replace the AND condition with the two-gate logic described in the Recommended Signals section. The `ranking_trustworthy` gate uses a floor check (`top_score > floor`), not a ceiling check.

### Failure 6: Reporting top_score as the flag score

The current flag reports `top_score` — how good the best tool looked. This is not the severity of the wrong call. A developer seeing score=0.85 with `flag_type=wrong_tool` will think "high confidence means I should trust this flag" when actually it means "there was a great tool you should have used."

**Prevention:** Report `gap` as the score (how much worse the called tool was) or `called_tool_score` (how poorly the called tool matched the prompt). Include both in `detail`. Reserve the top-level `score` field for the primary severity signal — the gap is the best choice here because higher gap = more severe wrong choice.

---

## Implementation Notes

### Batch the embeddings

The method already caches tool embeddings via `_get_tool_embeddings`. Extend this to also batch-encode tools in one HTTP call. The EmbedderClient already has `encode_batch`. For a span with 10 available tools, this reduces 10 network calls to 1.

### Structure of the rewritten method

```python
def _check_wrong_tool(self, span: SpanData) -> list[Flag]:
    if span.tool_name is None or span.prompt is None:
        return []

    prompt_vec = self.embed(span.prompt)

    # --- Signal 1: called tool similarity (always computed) ---
    called_tool_text = span.tool_name
    if span.tool_description:
        called_tool_text = f"{span.tool_name} {span.tool_description}"
    called_vec = self.embed(called_tool_text)
    called_score = self.compare(prompt_vec, called_vec)
    self.log_score("prompt_vs_called_tool", called_score)

    # --- Signal 2 + 3: ranking and gap (requires available_tools) ---
    if span.available_tools and len(span.available_tools) >= 3:
        tool_vecs = self._get_tool_embeddings(span.available_tools)
        tool_scores = [
            (t.get("name", ""), self.compare(prompt_vec, v))
            for t, v in zip(span.available_tools, tool_vecs)
        ]
        tool_scores.sort(key=lambda x: x[1], reverse=True)

        top_tool_name, top_score = tool_scores[0]
        # Find called tool score in the ranking
        called_rank_score = next(
            (s for name, s in tool_scores if name.lower() == span.tool_name.lower()),
            called_score  # fallback to Signal 1 if name not found
        )
        gap = top_score - called_rank_score
        rank = next(
            (i for i, (name, _) in enumerate(tool_scores)
             if name.lower() == span.tool_name.lower()),
            -1
        )

        self.log_score("wrong_tool_gap", gap)
        self.log_score("called_tool_rank", float(rank))

        ranking_trustworthy = top_score > self._thresholds["wrong_tool_rank_floor"]
        if ranking_trustworthy and gap > self._thresholds["wrong_tool_gap"]:
            return [Flag(
                flag_type="wrong_tool",
                score=gap,
                detail={
                    "metric": "wrong_tool_gap",
                    "called_tool": span.tool_name,
                    "called_tool_score": called_rank_score,
                    "top_tool": top_tool_name,
                    "top_tool_score": top_score,
                    "gap": gap,
                    "called_rank": rank,
                    "ranked_tools": [{"name": n, "score": s} for n, s in tool_scores],
                },
            )]
    else:
        # Fallback: no ranking available — use called tool similarity alone
        if called_score < self._thresholds["wrong_tool_called"]:
            return [Flag(
                flag_type="wrong_tool",
                score=called_score,
                detail={
                    "metric": "prompt_vs_called_tool",
                    "called_tool": span.tool_name,
                    "called_tool_score": called_score,
                },
            )]

    return []
```

### New threshold keys needed

| Key | Suggested starting value | Meaning |
|-----|--------------------------|---------|
| `wrong_tool_gap` | 0.15 | Minimum gap between top-ranked and called tool to flag |
| `wrong_tool_rank_floor` | 0.20 | Minimum top score for ranking to be considered trustworthy |
| `wrong_tool_called` | 0.25 | Fallback: minimum called_tool_score for no-ranking path |

The existing `wrong_tool` key can be retired or kept as an alias during migration.

### What to log for calibration

Every call to `_check_wrong_tool` should log:
- `prompt_vs_called_tool` — always
- `wrong_tool_gap` — when available_tools present and ranking trustworthy
- `called_tool_rank` — when available_tools present

These three metrics will build the calibration dataset needed to tune thresholds via `calibrate.py`.

---

## Sources

- [Internal Representations as Indicators of Hallucinations in Agent Tool Selection (arXiv 2601.05214)](https://arxiv.org/html/2601.05214) — shows that wrong tool selection is detectable as a signal separate from semantic similarity; function selection errors are a distinct hallucination category
- [Embedding-Based Tool Selection for AI Agents — Zarar's blog](https://zarar.dev/embedding-based-tool-selection-for-ai-agents/) — practical notes on similarity threshold tuning; confirms threshold sensitivity
- [Don't use cosine similarity carelessly — Piotr Migdał (2025)](https://p.migdal.pl/blog/2025/01/dont-use-cosine-similarity/) — key pitfall: symmetric models match questions to questions rather than questions to answers; applies directly to prompt-vs-tool asymmetry
- [Semantic Search — Sentence Transformers documentation](https://sbert.net/examples/sentence_transformer/applications/semantic-search/README.html) — confirms all-MiniLM-L6-v2 is a symmetric model; asymmetric tasks require MS MARCO models; warns that model choice for task type is critical
- [sentence-transformers/all-MiniLM-L6-v2 — Hugging Face](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) — confirms 256 token limit, symmetric design, general (not tool-specific) training
- [Tool Selection Quality — Galileo](https://v2docs.galileo.ai/concepts/metrics/agentic/tool-selection-quality) — production observability platform uses LLM-as-judge (not embedding similarity) for wrong-tool detection; confirms that embedding-only approaches are not the industry standard for high-accuracy evaluation
- [ToolFlood: Beyond Selection (arXiv 2603.13950)](https://arxiv.org/html/2603.13950) — confirms that rank position in a similarity-ordered list is a meaningful signal; lower rank = lower probability of selection by a well-functioning agent
- [When Document and Query Embeddings Don't Match — Microsoft Fabric Blog](https://community.fabric.microsoft.com/t5/Data-Science-Community-Blog/When-Document-and-Query-Embeddings-Don-t-Match-A-Practical-Guide/ba-p/4993140) — retrieval asymmetry is a real failure mode; short text vs long text comparison degrades cosine reliability
- [DeepEval Tool Correctness](https://deepeval.com/docs/metrics-tool-correctness) — when available_tools is provided, uses LLM judge to assess optimality (not embedding ranking); confirms ranking alone is insufficient for production correctness metrics

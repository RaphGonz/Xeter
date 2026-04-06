# Research Summary — v1.1 Analyser Accuracy

**Project:** Xeter v1.1 — Analyser Signal Redesign
**Domain:** LLM agent observability — span-local tool-call anomaly detection
**Researched:** 2026-04-06
**Confidence:** MEDIUM (signal design is well-reasoned and grounded in research; threshold values require calibration on real spans)

---

## What's Wrong (Current State)

- **wrong_tool:** The AND gate is inverted — it suppresses the flag when the top-ranked tool has a *high* score, which is exactly when the ranking signal is most trustworthy and a disagreement most meaningful. The flag score reports `top_score` (the best available tool) instead of the gap or the called tool's own score, so severity is unreadable from the dashboard. The fallback path compares bare tool names (1-4 tokens) against a full prompt, which reliably produces noise regardless of actual relevance.

- **no_tool:** Compares the prompt against the hardcoded string `"call a function tool"` — too generic to catch real capability gaps. Recall is 0.2; 80% of true gaps are missed. The span already contains `available_tools`, which are the semantically correct comparison target and are never consulted.

- **tool_use_violation (buried inside no_tool):** Uses cosine similarity to detect explicit prohibition phrases like "do not use tools." Research confirms all-MiniLM-L6-v2 encodes "do not use tools" and "use tools" as nearly identical vectors (empirically measured at ~0.993 cosine similarity). This check cannot work with this model class — it is not a threshold calibration problem, it is a documented representational limitation of contrastive-trained SBERT models.

- **wrong_args:** Embeds the raw JSON string of `tool_arguments` including structural syntax characters (`{`, `}`, `"`, `:`). Research shows a 19% Recall@10 improvement just from flattening structured data before embedding; the current approach wastes token capacity on non-semantic characters and operates outside the model's training distribution. The check is already marked `low_confidence: True` in production, confirming the team recognises it is unreliable.

- **excessive_tool:** Computes `cosine(prompt, tool_name)` — the same signal as the `wrong_tool` fallback path. It cannot distinguish "called the wrong tool" from "didn't need any tool at all." The concept of tool necessity is not encoded in prompt-vs-tool-name similarity.

---

## Recommended Signals

### wrong_tool

Replace the single AND condition with a two-gate approach. Gate 1: ranking is trustworthy only when `top_score > wrong_tool_rank_floor` (a minimum floor, not a ceiling — the current code has the direction inverted). Gate 2: flag when `gap = top_score - called_tool_score > wrong_tool_gap`. Report `gap` as the flag score (higher gap = more severe misfiling). When `available_tools` is absent or contains fewer than 3 tools, fall back to Signal 1 only: embed `tool_name + " " + tool_description` as a unit and flag when `called_tool_score < wrong_tool_called`. Never compare on tool name alone.

New threshold keys required: `wrong_tool_gap` (suggested start: 0.15), `wrong_tool_rank_floor` (suggested start: 0.20), `wrong_tool_called` (suggested start: 0.25). The existing `wrong_tool` key can be retired after migration.

### no_tool

When `available_tools` is present and non-empty, compute the max cosine similarity between the prompt embedding and each available tool embedding (reusing the existing `_get_tool_embeddings` cache). A high max score means the prompt semantically overlapped with at least one available tool — a tool-less response is therefore a capability gap. Log as `prompt_vs_best_tool`.

When `available_tools` is absent, compare against a centroid of action-oriented reference phrases ("look up information", "retrieve from database", "call an external service", etc.) rather than the single generic string. Log as `prompt_vs_action_reference`. Keep metric names distinct so calibration can track both paths separately. Expect the threshold to shift upward from the current 0.25; a starting value of 0.45 is recommended for the `available_tools` path.

### tool_use_violation (split out from no_tool)

Retire the embedding-based approach entirely — it cannot be fixed by threshold adjustment. Use keyword regex as the primary and sufficient mechanism. Compile patterns once at class init covering three categories: direct prohibition ("do not use tools", "don't call functions"), answer-directly instructions ("respond without calling", "answer from memory"), and format-constrained responses ("plain text only", "do not make API calls"). The flag score is binary (1.0 on any match). Log metric as `prompt_forbids_tool`. An embedding score can optionally be logged as a calibration artefact but must never gate the flag decision.

### wrong_args

Implement three signals in priority order. Priority 1 (output-based, highest ROI): scan `tool_output` for error patterns using compiled regex (`error`, `exception`, `invalid`, `missing required`, HTTP 4xx/5xx). This is deterministic, zero embedding cost, and directly causally linked to bad arguments. Priority 2 (semantic, replaces broken signal): flatten `tool_arguments` JSON to string values only (strip keys and all structural syntax), embed the result against the prompt; skip the embedding entirely if the flattened string is empty or all-numeric. Priority 3 (log-only in v1.1): compute `cosine(embed(arg_key_names), embed(tool_description))` to accumulate calibration data for a future threshold — do not flag on this in v1.1.

The `wrong_tool_args` threshold will need recalibration after raw-JSON embedding is replaced because the score distribution will shift significantly.

### excessive_tool

Replace `cosine(prompt, tool_name)` with a necessity delta signal. Embed two reference strings at class init: `DIRECT_ANSWER_REF` ("answer this question directly from existing knowledge without calling any external tool or API") and `TOOL_REQUIRED_REF` ("use a tool, API, or external system to perform this action or retrieve this information"). For each span: `necessity_delta = cosine(prompt, TOOL_REQUIRED_REF) - cosine(prompt, DIRECT_ANSWER_REF)`. Flag when `necessity_delta < thresholds["excessive_tool_delta"]` (start at -0.05, calibrate). Log secondary signal `prompt_vs_tool_output_overlap` when `tool_output` is available — a high score (output paraphrases the prompt) corroborates the necessity finding.

Add a mutual exclusion guard: if `wrong_tool` has already fired on the span, skip `_check_excessive_tool`. New threshold key: `excessive_tool_delta`.

---

## Cross-Cutting Findings

**Calibration infrastructure must accommodate binary signals.** The existing `calibrate.py` P/R sweep assumes continuous scores. Three new signals are binary (keyword match, output error, JSON validity). These should either be excluded from the numeric threshold sweep or handled with a sentinel value in `calibrated_thresholds.json`. The calibration script likely needs a `"binary": true` marker per flag type so it does not attempt sweep optimisation on them.

**Metric naming discipline is more important in v1.1 than v1.0.** Several checks now produce multiple sub-signals per span. Each sub-signal must be logged under a distinct `metric_name` key (e.g., `prompt_vs_best_tool` vs. `prompt_vs_action_reference`, `wrong_tool_gap` vs. `prompt_vs_called_tool`) so calibration datasets are separable by signal path. Do not aggregate sub-signals into a single score in the log.

**all-MiniLM-L6-v2 has two hard limits affecting multiple methods.** First, it is symmetric — comparing short text (tool names, argument values, 1-4 tokens) against long text (prompts) degrades cosine reliability in proportion to length asymmetry. Consistent mitigation: always embed the richest available representation of the short side (`name + description`, `flattened values`, action phrase centroid). Any new signal that embeds a sub-sentence fragment against a full prompt must be flagged for review. Second, it cannot encode negation polarity — "do not use tools" and "use tools" score ~0.993 cosine similarity. Any check needing to detect prohibitive language must use keyword regex, not cosine similarity.

**Double-flagging between wrong_tool and excessive_tool must be resolved explicitly.** Without a structural guard, the same span can fire both flags representing the same underlying issue. The recommended guard: if `wrong_tool` has already been appended to `flags` in `analyze()`, skip the `_check_excessive_tool` call. This requires `analyze()` to pass the accumulating flag list or check it before the call, but aligns with the natural execution order (wrong_tool runs first).

**The no_tool / tool_use_violation split is architecturally necessary.** The current single `_check_no_tool` conflates two opposite situations: "should have called a tool and didn't" vs. "was told not to call a tool and did anyway." These require different signals, different threshold types (continuous vs. binary), and different developer actions. Keeping them merged prevents independent calibration and makes flag semantics ambiguous.

**New threshold keys needed across all methods:**

| Key | Method | Type | Suggested Start |
|-----|--------|------|----------------|
| `wrong_tool_gap` | wrong_tool | continuous | 0.15 |
| `wrong_tool_rank_floor` | wrong_tool | continuous | 0.20 |
| `wrong_tool_called` | wrong_tool fallback | continuous | 0.25 |
| `tool_use_violation` | tool_use_violation | binary sentinel | 1.0 |
| `excessive_tool_delta` | excessive_tool | continuous (low-bad) | -0.05 |

The existing `wrong_tool`, `no_tool`, and `excessive_tool` keys may be retired or reused depending on migration approach. `wrong_tool_args` is retained but will need recalibration.

---

## Recommended Build Order

**1. wrong_args (first)** — Highest ROI for least risk. The output-based error signal (Priority 1) requires no embedding changes and no new threshold calibration; it is purely additive. It immediately resolves the `low_confidence: True` flag that has been shipping to users. The flattened-values improvement (Priority 2) is a localised change to one method. Start here — it is the clearest win with the most contained blast radius.

**2. wrong_tool (second)** — The logic inversion bug is clearly defined and the fix is surgical: invert one threshold comparison, change what is scored and reported, add the two-tool pool guard. The three new threshold keys are straightforward additions to `calibrated_thresholds.json`. This fix will have immediate impact on flag quality because the current AND-gate bug suppresses valid flags on high-confidence spans — the cases most worth catching.

**3. no_tool + tool_use_violation split (third)** — These two changes are tightly coupled: the method split is the prerequisite for fixing both signals independently. The `tool_use_violation` fix (keyword regex) is trivial to implement once the method is separated. The `no_tool` fix (max cosine against available_tools) reuses `_get_tool_embeddings` already in place from the wrong_tool work.

**4. excessive_tool (last)** — The necessity delta signal is conceptually the most novel and has no prior art for span-local detection specifically. The reference string embeddings need validation against real spans before the threshold is trustworthy. Implement last so calibration data from the first three fixes is available to inform the threshold choice, and so any cross-span double-flagging guards can be designed with full knowledge of what wrong_tool actually produces.

---

## Watch Out For

**1. The symmetric model trap applies to all four methods.** all-MiniLM-L6-v2 degrades when one side of a cosine comparison is much shorter than the other. The pattern that causes this is embedding bare tool names, single argument values, or short generic reference strings against a full prompt. The consistent fix is always to embed the richest available representation of the shorter input. Any v1.1 implementation that introduces a new cosine comparison where one side is a sub-sentence fragment should be treated as a red flag.

**2. Threshold values will not transfer from v1.0 to v1.1.** Score distributions shift when the underlying signal changes. The existing `calibrate.py` infrastructure handles recalibration, but the team must run it after each method rewrite before deploying. Do not reuse v1.0 threshold values for v1.1 signals — they were calibrated against different score distributions and will produce incorrect precision/recall tradeoffs. Budget a calibration run as the acceptance criterion for each method rewrite.

**3. The tool_use_violation embedding approach is not fixable by threshold adjustment.** This is the most important constraint from the research. The limitation is peer-reviewed and multiply confirmed: SBERT-family models assign near-identical embeddings to negated and non-negated forms of the same sentence because the contrastive training objective optimises for content-word similarity, not polarity. If anyone proposes keeping the cosine-similarity approach with a different threshold or reference string, the answer is no. Only keyword regex (or a negation-aware NLI classifier, which is not in scope) can detect explicit prohibition reliably.

---

## Sources

### Primary (HIGH confidence)
- Scientific Reports 2025 (Nature) — peer-reviewed confirmation that SBERT negation pairs score ~0.993 cosine similarity; confirms this is a model-class limitation
- HuggingFace community forum — empirical demonstration with measured score on negated pair
- sentence-transformers/all-MiniLM-L6-v2 model card (HuggingFace) — symmetric design, 256 token limit, contrastive training objective
- Towards Data Science: "Optimizing Vector Search: Why You Should Flatten Structured Data" — 19.1% Recall@10 improvement and 27.2% MRR improvement from JSON flattening before embedding

### Secondary (MEDIUM confidence)
- Arize Phoenix: How to Evaluate Tool-Calling Agents — LLM-as-a-judge for argument correctness; semantic equivalence problem documented
- Self-RAG (arXiv 2310.11511) — retrieval necessity as a query property; conceptual basis for necessity delta signal
- Adaptive-RAG — classifier-based query routing as lightweight equivalent of necessity delta
- ToolFlood (arXiv 2603.13950) — rank position as a meaningful signal for tool selection quality
- Internal Representations as Indicators of Hallucinations (arXiv 2601.05214) — wrong tool selection as a distinct hallucination category; detectable as a separate signal
- Don't use cosine similarity carelessly (Piotr Migdal, 2025) — prompt-vs-tool asymmetry; symmetric model misuse pitfalls
- Galileo tool selection quality docs — production observability platform uses LLM-as-judge, confirms embedding-only is not industry standard for high-accuracy evaluation

### Tertiary (MEDIUM-LOW confidence)
- DeepEval tool correctness metric — "unnecessary calls" as a distinct metric from wrong selection; no span-local necessity signal documented
- Is Cosine-Similarity of Embeddings Really About Similarity? (arXiv 2403.05440) — cosine reliability varies across models; `necessity_delta` confidence remains MEDIUM until calibrated on real Xeter spans
- Adaptive Retrieval without Self-Knowledge? (arXiv 2501.12835) — supports keeping necessity signal continuous (delta) rather than binary

---

*Research completed: 2026-04-06*
*Ready for roadmap: yes*

# no_tool + tool_use_violation Detection Signals — Research

**Researched:** 2026-04-06
**Scope:** Split `_check_no_tool` into two methods — capability gap and explicit violation detection
**Confidence:** HIGH for architecture reasoning; MEDIUM for threshold values (need calibration)

---

## no_tool: Capability Gap Detection

### Current Approach Assessment

The existing implementation compares `span.prompt` against the hardcoded string `"call a function tool"` and flags if similarity exceeds `no_tool` threshold (currently 0.25, precision 1.0 / recall 0.2).

**Why this is wrong:**

The reference string `"call a function tool"` is too generic to be a meaningful signal. It will only fire on prompts that literally describe calling tools in the abstract, not on prompts that _implicitly_ need tool use to fulfill a task. The calibration result confirms this: recall is 0.2, meaning 80% of true capability gaps are missed. The high precision (1.0) only means the few it does catch happen to be right — not that the signal is good. A better approach will trade some precision for substantially higher recall.

The core conceptual error is using a single generic reference string when the span already contains the specific tool descriptions the model had available. The correct signal should ask: "does this prompt look like it was trying to accomplish something that one of the available tools could do?"

### Recommended Signal

**Primary: prompt vs. available_tools max cosine similarity (span-local)**

When `available_tools` is present and non-empty, compute the embedding of each tool as `"{name} {description}"` (reuse `_get_tool_embeddings`), compute cosine similarity between `prompt_vec` and each tool embedding, and take the **maximum** across all tools. A high max score means the prompt is semantically close to at least one available tool — i.e., the task the user asked about overlaps strongly with what a tool was designed to do. When no tool was called despite this overlap, that is a capability gap.

This is strictly better than the generic reference string because:
- It is grounded in the actual tool set the agent had access to
- Different agents have different tools; comparing against available_tools makes the signal contextual rather than generic
- The `_get_tool_embeddings` cache already exists and makes this cheap

**Fallback when available_tools is None or empty:**

Compare prompt against a richer multi-phrase reference that encodes action-seeking intent. Use the centroid (average) of embeddings for a set of action-oriented reference phrases:

```
"look up information"
"search for data"
"retrieve from database"
"fetch the current value"
"find records matching"
"call an external service"
"execute a function"
"get the latest status"
```

Average these vectors at construction time (or hardcode a single representative phrase like `"retrieve information using an available tool"`) to produce a stable reference vector. This is more semantically grounded than `"call a function tool"` because it covers the vocabulary an actual task-oriented prompt would use.

Log the score as `"prompt_vs_best_tool"` when available_tools is used, or `"prompt_vs_action_reference"` for the fallback, so that calibration can track both paths separately.

### Threshold Strategy

The existing threshold of 0.25 is almost certainly too low for the new signal (which will produce higher scores against real tool descriptions than against a generic string). Expect the new signal's distribution to shift upward.

Recommended approach after implementation:
1. Set an initial threshold of **0.45** for `prompt_vs_best_tool` (the available_tools path). This is in the moderate-overlap range for all-MiniLM-L6-v2 on semantically related but not identical text.
2. Recalibrate against labeled spans using the existing calibration pipeline. The threshold is injected via `self._thresholds["no_tool"]` so no code changes are needed to adjust it.
3. For the fallback path, calibrate separately if metric names are distinct.

**Upper bound consideration:** Do not set the threshold above ~0.65 without strong calibration evidence. All-MiniLM-L6-v2 rarely exceeds 0.7 for semantically related but non-identical text, so setting threshold too high will collapse recall back toward zero.

### False Positive Risks

**Risk 1: Conceptual discussion of tools without needing them called.**
Prompts like "explain what the `search_web` tool does" will score high against the search_web tool embedding but do not require a tool call — they want an explanation. Mitigation: if the response is present and is long-form prose rather than structured data, `_check_response_anomaly` may already handle this as a secondary signal. No simple mitigation purely at the `no_tool` check level; accept some FPs and set threshold conservatively (err slightly high to reduce FPs over recall).

**Risk 2: Prompts that mention tool names as examples.**
"Unlike a database query, I want you to reason from first principles" — will score high against a database tool. Hard to mitigate without NLI. Accept as low-frequency FP.

**Risk 3: Empty or trivial available_tools entries.**
Tools with missing names or descriptions will produce near-zero embeddings, pulling max score down artificially. Mitigation: skip tools where `name` and `description` are both empty before embedding.

**Risk 4: available_tools path vs. fallback path calibrated together.**
If the calibration pipeline does not separate the two metric names, threshold will be optimized for whichever path is more common in the dataset. Keep metric names distinct (`prompt_vs_best_tool` vs. `prompt_vs_action_reference`) so calibration data is separable.

---

## tool_use_violation: Explicit Prohibition Detection

### Recommended Signal (embedding vs keyword vs hybrid)

**Recommendation: keyword/regex primary, embedding secondary.**

This is one of the clearest cases in NLP where embedding similarity is the wrong primary tool. The reason is well-established and confirmed by peer-reviewed research (Scientific Reports 2025, HuggingFace community documentation): all-MiniLM-L6-v2 and SBERT-family models trained on contrastive similarity objectives do not reliably encode negation polarity. The sentence pair ("use tools to answer", "do not use tools to answer") will produce a **high** cosine similarity score — often 0.95+ — because the content words are identical and the negation marker `"do not"` carries minimal weight in the embedding space.

This is not a threshold calibration problem. It is a representational limitation of the model class. Attempting to detect tool prohibition via embedding similarity against a reference like `"do not use tools"` will fire on prompts that actively _request_ tool use, because both sides encode similarly.

**Recommended approach: keyword regex pattern match with optional embedding confirmation.**

Step 1 — Keyword scan (sufficient, required):
Check whether `span.prompt` matches any pattern in a curated list. If yes, flag.

Step 2 — Embedding confirmation (optional, defense-in-depth):
If the keyword scan fires, optionally compute similarity between prompt and a "prohibition reference" as a secondary score to log for calibration, but do not make it a gate.

### Reference Phrases / Patterns

Group the patterns by three distinct intent categories:

**Category A — Direct prohibition:**
```
do not (use|call|invoke|run) (tools|functions|any tool|any function)
don't (use|call|invoke|run) (tools|functions|any tool|any function)
without (using|calling|invoking|running) (tools|functions|any tool|any function)
no (tool|function) calls?
refrain from (using|calling) (tools|functions)
avoid (using|calling) (tools|functions)
```

**Category B — Answer-directly instructions:**
```
answer (directly|from memory|without tools|on your own)
respond (directly|without calling|without using)
reply (directly|without tools)
answer this (directly|yourself|without external)
do not call (any|external) (function|tool|api)
```

**Category C — Format-constrained responses (implicit prohibition):**
```
answer in (plain text|prose|natural language) (only|without)
(text.only|prose.only) response
do not make (api|function|external) calls
```

**Implementation note:** Use `re.search` with `re.IGNORECASE` and compile patterns once at class construction. Do not use raw string matching; normalise whitespace before matching.

**Threshold for keyword match:** Binary — either a pattern matches or it does not. No threshold needed. The `score` field in the Flag should be set to `1.0` on a keyword match or to a constant (e.g., `1.0`) since it is not a continuous similarity score.

Log metric name as `"prompt_forbids_tool"`. Log score `1.0` if keyword fires, `0.0` if it does not (for calibration completeness even on non-firing spans).

### Reliability Assessment (can all-MiniLM-L6-v2 handle this?)

**No. all-MiniLM-L6-v2 cannot reliably detect explicit tool prohibition via cosine similarity.**

Evidence:

1. The HuggingFace discussion thread documents empirically that "I like rainy days" and "I don't like rainy days" score 0.993 cosine similarity with SBERT. Negation markers (`do not`, `without`, `don't`) are not meaningfully encoded in the embedding space.

2. Scientific Reports 2025 (Nature) confirms: "SSTs perform effectively on non-negated text, but they exhibit notable limitations in modeling the semantic distortions introduced by negation." The paper specifically documents that "embeddings of sentences with opposite meanings are placed very close to each other in the representation space."

3. The contrastive training objective of all-MiniLM-L6-v2 optimizes for semantic relatedness between content words, not polarity. Tool prohibition prompts ("don't call tools") and tool invitation prompts ("call tools") share the same content words and will land at nearly identical positions in embedding space.

**Confidence of this assessment: HIGH.** Multiple independent sources confirm this as a documented limitation of the model class, not a configuration issue.

An embedding similarity approach for this check would require either a negation-aware model fine-tuned on negation pairs, or an NLI (Natural Language Inference) classifier that can evaluate entailment/contradiction rather than semantic similarity. Neither is available in the current stack without adding a new model.

### False Positive Risks

**Risk 1: Educational or meta discussion about tool prohibition.**
"Explain to me why you should not use tools for simple questions" — will fire on keyword patterns but the context is not a prohibition instruction. Low-frequency in real agent prompts; acceptable FP. Mitigation: none at the heuristic level without NLI.

**Risk 2: Nested quotation or example content.**
"The user said 'do not use tools' but I disagree" — will fire. Again, low-frequency in real spans; accept as known limitation.

**Risk 3: Partial phrase match.**
"Don't use tools that are deprecated" is a partial prohibition (deprecated tools only, not all tools), but the regex patterns above will match it. Mitigation: keep patterns strict by requiring the phrase to end in a broad term (`tools`, `functions`, `any tool`) rather than matching `"tools that"` — the patterns above already avoid `"tools that"` as a suffix.

**Risk 4: Prompt only contains the prohibition but the tool was called by a system component, not the model.**
The violation attribution is at the span level, so a tool call that was pre-wired independently of the model's decision will still appear as a violation. No mitigation at the analyzer level; add a `low_confidence: True` marker in the detail dict analogous to `_check_wrong_args`.

---

## Implementation Notes

**Method split in `analyze()`:**
Replace the single `flags.extend(self._check_no_tool(span))` call with two calls:
```python
flags.extend(self._check_no_tool(span))          # span.tool_name is None
flags.extend(self._check_tool_use_violation(span))  # span.tool_name is not None
```

Each method guards itself on `tool_name` nullity, so there is no overlap:
- `_check_no_tool` returns `[]` immediately if `span.tool_name is not None`
- `_check_tool_use_violation` returns `[]` immediately if `span.tool_name is None`

**`_check_no_tool` threshold key:** Keep `"no_tool"` as the key. The existing threshold injection pattern handles this without schema changes.

**`_check_tool_use_violation` threshold key:** Add `"tool_use_violation"` as a new key. Since the primary detection is keyword-based (binary), the threshold is not used as a numeric gate but should still be registered in the thresholds dict for calibration uniformity. Set the initial default to `0.5` (unused numeric placeholder) or omit the threshold comparison entirely for the keyword path.

**Compile regex patterns once:** Instantiate compiled patterns as a class-level constant or in `__init__`. Do not recompile on every span.

**Logging discipline:** Both methods must call `self.log_score()` before any `return` with a flag — same calibration-first discipline as all other check methods. For `_check_tool_use_violation`, log `1.0` on a match and `0.0` on no match. This gives the calibration dataset signal even from non-flagging spans.

**Handle `available_tools is None` for `_check_no_tool`:**
```python
if span.available_tools is not None and len(span.available_tools) > 0:
    # primary path: max similarity across tool embeddings
else:
    # fallback path: action reference vector
```

**Score field for `tool_use_violation` Flag:** Since it is a binary keyword match, set `score=1.0` and include `"match_type": "keyword"` in the detail dict so the dashboard can display "keyword match" rather than a misleading float similarity score.

**New threshold key in calibrated_thresholds.json:** Add `"tool_use_violation": 1.0` as a sentinel. The calibration script will need to know this flag type is keyword-based so it does not attempt numeric threshold sweep on it (or it can be excluded from the P/R sweep similarly to `wrong_tool_args`).

---

## Sources

- [Scientific Reports 2025: Negation sentence similarity hybrid deep learning](https://www.nature.com/articles/s41598-025-34084-2) — HIGH confidence; peer-reviewed confirmation of SBERT negation limitation
- [HuggingFace Forum: Sentence similarity models not capturing opposite sentences](https://discuss.huggingface.co/t/sentence-similarity-models-not-capturing-opposite-sentences/10388) — HIGH confidence; empirical demonstration with score 0.993 on negated pair
- [Defining and Detecting LLM-based Autonomous Agent Defects (arXiv 2412.18371)](https://arxiv.org/html/2412.18371v1) — MEDIUM confidence; documents IETI defect class relevant to capability gap detection
- [Why Your AI Agent Needs Semantic Tool Discovery — Rocket Connect](https://www.rconnect.tech/blog/semantic-tool-discovery) — MEDIUM confidence; confirms semantic similarity against tool descriptions as the correct matching signal
- [sentence-transformers/all-MiniLM-L6-v2 — HuggingFace Model Card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) — HIGH confidence; official model documentation confirming contrastive training objective

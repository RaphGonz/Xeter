# wrong_args Detection Signals — Research

**Project:** Xeter v1.1 — Analyser Accuracy
**Researched:** 2026-04-06
**Scope:** Rewriting `_check_wrong_args` in `ToolCallAnalyzer`
**Confidence:** HIGH (assessment of core problem); MEDIUM (alternative signal design)

---

## Current Approach Assessment

### What the current implementation does

`_check_wrong_args` embeds the raw `tool_arguments` string (a JSON string such as
`{"query": "Paris population", "limit": 10}`) and computes cosine similarity against
the embedded `prompt`. If the score falls below the `wrong_tool_args` threshold, a flag
is raised with `low_confidence: True` attached.

### Is embedding raw JSON fundamentally broken?

**Yes. This is conceptually broken for three compounding reasons.**

**Reason 1: Tokenizer waste on structural syntax.**
When `sentence-transformers` (or any transformer tokenizer) processes raw JSON, a
significant fraction of tokens are consumed by structural characters: `{`, `}`, `"`, `:`,
`,`. These carry no semantic meaning but dilute the representation of the actual content.
Research on flattening structured data for retrieval shows a 19% improvement in Recall@10
just by converting JSON to natural language before embedding — the magnitude of
degradation is large, not marginal (source: Towards Data Science, "Optimizing Vector
Search: Why You Should Flatten Structured Data").

**Reason 2: all-MiniLM-L6-v2 was trained on sentence pairs, not structured data.**
The model was trained on natural language sentence pairs (SNLI, MSMARCO, etc.). It
produces meaningful similarity scores when comparing natural language to natural language.
When one input is a fragment like `{"q": "capital france"}` and the other is a full
sentence prompt, the model is operating outside its training distribution. The resulting
cosine scores are neither reliable nor calibratable.

**Reason 3: terse argument values do not embed like the concepts they represent.**
A prompt of "What is the capital of France?" and an argument value of `"france"` share
the same underlying concept, but their embedding representations are not close in
all-MiniLM-L6-v2's space because the word `"france"` alone does not activate the same
contextual features as the full natural language sentence. The shorter the value, the
worse the embedding quality.

### Why `low_confidence: True` was the right call but is insufficient

Marking flags as low-confidence signals awareness that the approach is unreliable. But
an unreliable signal that consistently fires has two failure modes: (a) it generates false
positives that erode developer trust, and (b) because it is excluded from precision/recall
calibration, it remains invisible in the calibration dataset. The correct action is not to
keep the signal and mark it low-confidence — it is to replace it with a signal that does
not require a confidence caveat.

---

## The Wrong-Args Problem, Correctly Stated

There are two distinct failure modes being conflated under "wrong args":

**Type A — Semantic mismatch:** The argument *values* passed do not reflect what the
prompt requested. The agent asked for one thing; the arguments encode something else.
Example: prompt says "find hotels in Paris near the Eiffel Tower" but the argument is
`{"location": "London", "stars": 4}`.

**Type B — Structural mismatch:** The argument *structure* does not conform to what the
tool expects. Required parameters are missing, unexpected keys are present, or values
are the wrong type.
Example: a tool expects `{"city": str, "date": str}` but receives `{"location": "Paris"}`.

These require different signals. The current implementation attempts semantic detection
(Type A) using a method that is not reliable for either type.

---

## Alternative Signals

### Signal 1: Argument values flattened to natural language → embed against prompt

**What:** Parse the `tool_arguments` JSON string. Extract the values (not keys) and
concatenate them into a natural-language-like string. Embed this flattened string and
compare to the prompt embedding.

**Why this is better than raw JSON embedding:**
- Keys like `"query"`, `"location"`, `"limit"` are structural — they repeat the tool
  schema, not the intent. The *values* are what the model chose based on the prompt.
- Flattening strips JSON structure tokens that waste tokenizer capacity.
- Research confirms flattened structured data embeds meaningfully; raw JSON does not.

**Example transformation:**
```python
# raw: '{"query": "Paris population", "limit": 10, "year": 2024}'
# flattened: "Paris population 10 2024"
```

**Limitations:**
- Still produces a short string, especially for terse arguments. A single-value arg
  like `{"city": "Paris"}` flattens to just `"Paris"` — still a poor embedding target.
- Numeric values (`10`, `2024`) embed meaninglessly. Filter them out or convert to
  words only.
- If argument values are already natural language (e.g., `{"query": "population of Paris
  in the last decade"}`), this works well. If they are codes, IDs, or enum values, it
  does not.

**Confidence of signal:** MEDIUM. Better than raw JSON; not reliable for terse args.

**Implementation:**
```python
import json

def _flatten_arg_values(args_str: str) -> str | None:
    """Extract string values from a JSON args string, skip numerics and nesting."""
    try:
        parsed = json.loads(args_str)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    values = []
    for v in parsed.values():
        if isinstance(v, str) and v.strip():
            values.append(v.strip())
    return " ".join(values) if values else None
```

Only proceed with embedding if the flattened string is non-empty and contains at least
one substantive string value. Otherwise skip the semantic check entirely.

---

### Signal 2: Argument key names compared to tool description

**What:** Extract the key names from `tool_arguments`, join them into a string, and
compute cosine similarity against the `tool_description`. High similarity means the
argument names look like they belong to this tool; low similarity suggests the arguments
may have been generated for a different tool.

**Why this works conceptually:**
Tool descriptions typically describe what parameters the tool accepts ("Search for flights
between two airports using departure and arrival codes and a travel date"). Key names
like `departure`, `arrival`, `date` embed close to that description. Keys like `city`,
`stars`, `budget` do not.

**Limitations:**
- Only fires when the tool description contains parameter-relevant language.
- Requires a non-trivial tool description. If tool_description is `"Search tool"`, the
  signal collapses.
- Does not detect wrong *values*, only structurally foreign *keys*.

**Confidence of signal:** MEDIUM, conditional on tool description quality.

**Implementation:**
```python
def _arg_keys_string(args_str: str) -> str | None:
    try:
        parsed = json.loads(args_str)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    keys = [k for k in parsed.keys() if k]
    return " ".join(keys) if keys else None
```

Score: `cosine(embed(arg_keys_string), embed(tool_description))`

---

### Signal 3: Tool output as a proxy for argument correctness

**What:** Inspect `tool_output` for error-pattern strings. Common patterns include:
`"error"`, `"exception"`, `"invalid"`, `"not found"`, `"missing"`, `"required"`,
`"ValidationError"`, `"TypeError"`, HTTP 4xx status codes in JSON responses.

**Why this is a strong signal:**
When a tool receives structurally or semantically wrong arguments, tools typically return
errors. This is observable in the span without any embedding computation. It is a direct
causal indicator: bad args → tool error → error in tool_output.

**Why this approach is underused:**
Most evaluation frameworks focus on the pre-execution side (were the right args passed?)
rather than the post-execution side (what happened when those args ran?). But for
span-local detection without ground truth, the output is a high-value signal.

**Limitations:**
- Only fires when a tool actually returns an error. Well-behaved tools with graceful
  degradation may return empty results rather than errors ("no results found" is not
  necessarily a wrong-args error).
- "Not found" can be semantically correct (searching for something that does not exist
  is not a wrong-args error).
- False positives: tool network failures or downstream service errors will also produce
  error output but are not wrong-args failures.

**Confidence of signal:** HIGH for clear error patterns; MEDIUM for ambiguous patterns.

**Implementation approach:**
```python
import re

_ERROR_PATTERNS = [
    re.compile(r'\b(error|exception|traceback|invalid|missing required|'
               r'validation.?error|type.?error|value.?error)\b', re.IGNORECASE),
    re.compile(r'"status"\s*:\s*[45]\d{2}'),          # HTTP 4xx/5xx in JSON
    re.compile(r'"code"\s*:\s*"[A-Z_]+_ERROR"'),       # error code pattern
]

def _output_contains_error(tool_output: str | None) -> bool:
    if not tool_output:
        return False
    return any(p.search(tool_output) for p in _ERROR_PATTERNS)
```

This should be treated as a distinct sub-signal reported separately in the flag `detail`,
not collapsed into a single score, because the cause (bad args vs network failure) is
ambiguous.

---

### Signal 4: JSON parse validity check (structural, no embedding needed)

**What:** Attempt to parse `tool_arguments` as JSON. If it fails, that is an immediate
structural wrong-args signal — the model produced malformed arguments.

**Why:** The `_check_parsing_error` method already handles raw_response format detection,
but `tool_arguments` itself may be malformed (the model generated invalid JSON for the
arguments field). This is separate from the response format check and should be caught
here.

**Confidence of signal:** HIGH. Malformed JSON is unambiguous.

**Note:** This is already implicit in Signal 1 (the flatten attempt catches parse errors),
but it should be surfaced explicitly as a separate condition rather than silently skipped.

---

## What Arize Phoenix Does (Industry Reference)

Arize Phoenix's Tool Invocation Evaluator uses an LLM-as-a-judge approach. It checks:
1. Whether all required parameters are present
2. Whether argument values are hallucinated or inconsistent with user intent
3. Whether argument values match what the user actually said

Arize's explicit conclusion is that "tool call arguments don't lend themselves to exact
matching — values like 'CDG Airport' and 'Charles De Gaulle Airport' are equivalent in
ways that string comparison can't capture." Their solution is LLM-as-a-judge.

**Relevance to Xeter:** LLM-as-a-judge is explicitly out of scope for v1.1 (no LLM in
the worker path; Diagnosticer is separate and on-demand only). The Arize finding does
confirm that raw string or embedding matching is unreliable for semantic correctness — it
validates the pivot to structural and output-based signals for the heuristic layer.

---

## Should wrong_args be split into two flags?

**Yes, and here is the recommended split:**

| Flag type | What it detects | Signal |
|-----------|----------------|--------|
| `wrong_tool_args` | Argument values semantically diverge from prompt | Flattened value embedding vs prompt; arg keys vs tool description |
| `tool_args_error` | Tool returned an error, likely due to bad arguments | Error pattern in tool_output |

The two types have different causes and different developer actions:
- Semantic mismatch → fix the prompt or tool description to guide the model
- Tool error → fix the argument structure or tool's error handling

Collapsing them into one flag obscures which problem occurred. Splitting them also allows
separate threshold calibration once data accumulates.

If the implementation budget allows only one change, prioritize adding the output-based
error signal under the existing `wrong_tool_args` flag type rather than creating a new
flag type — this is additive and does not require schema changes.

---

## Recommended Approach

### Priority 1: Output-based error detection (highest ROI, span-local, no embedding)

Check `tool_output` for error patterns. This is:
- Deterministic (regex, no model)
- High-precision (errors in tool output are real failures)
- Zero embedding cost
- No threshold calibration needed (pattern match = flag)

This should be the primary new signal.

### Priority 2: Flattened value embedding vs prompt (replaces raw JSON embedding)

Replace `embed(span.tool_arguments)` with `embed(flatten_arg_values(args))`. Only run
the embedding if the flattened string is non-empty and contains meaningful string values.
If the flattened string is empty (all-numeric args, or no string values), skip the
semantic check entirely rather than embedding a degenerate string.

Set `low_confidence: True` only when the flattened string is very short (fewer than 3
meaningful tokens). Otherwise remove the low_confidence caveat — flattened natural
language values are a legitimate embedding target.

### Priority 3: Arg keys vs tool description (secondary signal, additive)

If `tool_description` is available and non-trivial (longer than ~30 chars), compute
`cosine(embed(arg_keys), embed(tool_description))`. Log this score as a new metric
(`args_keys_vs_description`) for calibration. Threshold separately.

### What to NOT do

- Do not embed the raw JSON string including structural syntax. This is confirmed broken.
- Do not embed a single word or two-word arg value. Degenerate embedding inputs produce
  noise, not signal.
- Do not collapse output-based error detection and semantic mismatch into the same score.
  They are different problems.
- Do not apply the LLM-as-a-judge approach in the worker. That belongs in the
  Diagnosticer.

---

## What to Abandon

1. **`embed(span.tool_arguments)` as the primary signal.** The raw JSON string is a
   consistently poor embedding input. Retire this immediately.

2. **`low_confidence: True` as a permanent marker.** Low-confidence was a correct
   temporary marker, but it should be resolved by replacing the signal — not kept
   indefinitely. A flag the system knows is unreliable should not be shipped to users.

3. **Single-score reduction.** The current approach collapses all argument quality into
   one cosine score. The rewrite should produce multiple sub-signals (output error check,
   semantic value match, structural key match) reported separately in `detail`.

---

## Implementation Notes

### Recommended method structure

```python
def _check_wrong_args(self, span: SpanData) -> list[Flag]:
    if span.tool_arguments is None:
        return []

    flags: list[Flag]  = []
    detail: dict = {}

    # --- Signal A: structural validity ---
    try:
        parsed_args = json.loads(span.tool_arguments)
    except (json.JSONDecodeError, TypeError):
        self.log_score("args_json_valid", 0.0)
        return [Flag(
            flag_type="wrong_tool_args",
            score=0.0,
            detail={"metric": "args_json_valid", "error": "tool_arguments is not valid JSON"},
        )]
    self.log_score("args_json_valid", 1.0)

    # --- Signal B: output-based error detection ---
    output_has_error = _output_contains_error(span.tool_output)
    if output_has_error:
        self.log_score("tool_output_error", 1.0)
        # Log and flag independently; don't short-circuit other checks
        flags.append(Flag(
            flag_type="wrong_tool_args",
            score=1.0,
            detail={"metric": "tool_output_error",
                    "note": "tool_output contains error pattern — args may be wrong"},
        ))
    else:
        self.log_score("tool_output_error", 0.0)

    # --- Signal C: flattened arg values vs prompt ---
    if span.prompt is not None and isinstance(parsed_args, dict):
        flattened = _flatten_arg_values_from_dict(parsed_args)
        if flattened:  # only embed if we have meaningful string content
            prompt_vec = self.embed(span.prompt)
            flat_vec = self.embed(flattened)
            score = self.compare(prompt_vec, flat_vec)
            self.log_score("prompt_vs_arg_values", score)
            if score < self._thresholds["wrong_tool_args"]:
                flags.append(Flag(
                    flag_type="wrong_tool_args",
                    score=score,
                    detail={"metric": "prompt_vs_arg_values",
                            "score": score,
                            "flattened_args": flattened},
                ))
        # else: skip embedding — degenerate input, log nothing for this signal

    # --- Signal D: arg key names vs tool description ---
    if span.tool_description is not None and len(span.tool_description) > 30:
        if isinstance(parsed_args, dict):
            keys_str = " ".join(parsed_args.keys())
            if keys_str.strip():
                desc_vec = self.embed(span.tool_description)
                keys_vec = self.embed(keys_str)
                keys_score = self.compare(desc_vec, keys_vec)
                self.log_score("args_keys_vs_description", keys_score)
                # Do not flag on this signal alone in v1.1 — accumulate calibration data first

    return flags
```

### Threshold considerations

- Signal B (output error) is binary — no threshold, pattern match directly produces a
  flag. Score is always 1.0 to indicate the signal fired.
- Signal C (flattened values vs prompt) shares the existing `wrong_tool_args` threshold
  key. This key will need recalibration after raw-JSON embedding is replaced, because
  the score distribution will shift.
- Signal D (keys vs description) should not produce flags in v1.1. Log the score only,
  to build a calibration dataset before setting a threshold.

### Existing test coverage

`xeter/tests/worker/test_tool_call_analyzer.py` covers `_check_wrong_args`. The test
suite will need updating to reflect:
- Cases where tool_output contains error patterns → flag expected
- Cases where flattened arg values diverge from prompt → flag expected
- Cases where tool_arguments is invalid JSON → flag expected
- Cases where arg values match prompt but tool_output is clean → no flag expected
- Cases where arg values are all-numeric → semantic check skipped, no flag expected

---

## Confidence Assessment

| Finding | Confidence | Basis |
|---------|------------|-------|
| Raw JSON embedding is fundamentally unreliable | HIGH | Research confirms structural token waste degrades embeddings; model training distribution mismatch; project's own calibration exclusion acknowledges this |
| Flattened string values are a better embedding target | HIGH | Retrieval research (19% Recall@10 gain); logical elimination of structural token waste |
| Output-based error detection is a viable signal | MEDIUM | Observability platform practice; causal relationship is sound; false positive rate from network errors is a real concern |
| Arg keys vs tool description as secondary signal | MEDIUM | Conceptually sound; empirical calibration needed to set threshold |
| Splitting into two flag types (semantic vs structural) | MEDIUM | Conceptually correct; deferred to v1.2 if implementation budget is tight |
| LLM-as-a-judge is the most accurate approach | HIGH | Arize's confirmed finding; excluded from scope by architecture constraints |

---

## Sources

- [Arize Phoenix: How to Evaluate Tool-Calling Agents](https://arize.com/blog/how-to-evaluate-tool-calling-agents/) — Tool Invocation Evaluator; LLM-as-a-judge for argument correctness; semantic equivalence problem with string matching
- [Arize Phoenix: Tool Response Handling](https://arize.com/docs/phoenix/evaluation/pre-built-metrics/tool-response-handling) — post-execution output evaluation; distinction from invocation evaluation
- [Towards Data Science: Optimizing Vector Search — Flatten Structured Data](https://towardsdatascience.com/optimizing-vector-search-why-you-should-flatten-structured-data/) — 19.1% Recall@10 and 27.2% MRR improvement from flattening JSON before embedding
- [Milvus AI Reference: Common Sentence Transformer Mistakes](https://milvus.io/ai-quick-reference/what-are-common-mistakes-that-could-lead-to-poor-results-when-using-sentence-transformer-embeddings-for-semantic-similarity-tasks) — pooling misconfiguration, domain mismatch, threshold calibration pitfalls
- [Agent Observability: Tracing Tool Calls](https://www.braintrust.dev/articles/agent-observability-tracing-tool-calls-memory) — tool call inputs/outputs as primary observability signal
- [Partnership on AI: Real-Time Failure Detection in AI Agents](https://partnershiponai.org/wp-content/uploads/2025/09/agents-real-time-failure-detection.pdf) — tool call failure as fastest reliability signal
- [Quotient AI: Evaluating Tool Calling Capabilities — Literature Review](https://blog.quotientai.co/evaluating-tool-calling-capabilities-in-large-language-models-a-literature-review/) — Hungarian algorithm for best-assignment matching; embedding array per JSON value approach

---
*Research for: Xeter v1.1 — _check_wrong_args rewrite*
*Researched: 2026-04-06*

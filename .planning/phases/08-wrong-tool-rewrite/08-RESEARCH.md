# Phase 8: wrong_tool Rewrite - Research

**Researched:** 2026-04-07
**Domain:** Python, ToolCallAnalyzer heuristic rewrite, hybrid scoring, calibration
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Detection logic (replaces two-gate approach)

Three cases, all flag as `wrong_tool`:

1. **No available_tools + tool called** — immediate flag, no threshold check. The agent called a tool when none were available.
2. **available_tools present, top1_tool != called_tool, top1_score >= wrong_tool_called** — a better tool existed and the ranking is trustworthy. Flag.
3. **available_tools present, top1_score < wrong_tool_called** — no tool was appropriate for the prompt; the agent shouldn't have called anything. Flag.

Correct case (no flag): `top1_tool == called_tool AND top1_score >= wrong_tool_called`.

#### Threshold key

Single key: `wrong_tool_called`. Replaces the previously planned `wrong_tool_gap`, `wrong_tool_rank_floor`, and `wrong_tool_called` trio — these collapse to one. The old `wrong_tool` key is retired.

#### Reported score

`top1_score` (the best available tool's hybrid similarity to the prompt). Not the gap.

#### Hybrid scoring (WTOOL-04)

Use `hybrid_score` (50/50 cosine + BOW) for all prompt-vs-tool comparisons, consistent with Phase 7. Tool text = `name + " " + description` for both the cosine embedding (reuses `_get_tool_embeddings` cache) and the BOW computation. No change to cache structure needed.

#### Calibration direction

Recall-first: maximize recall (minimize false negatives) as the primary objective. Precision should be as high as achievable given that goal. Both P and R reported after calibration run.

#### Plan structure

3 plans:
- 08-01: wrong_tool rewrite
- 08-02: Algorithm review — user reviews implementation before calibration
- 08-03: Calibration run

### Claude's Discretion

- Exact BOW text construction when `description` is absent (fall back to name only)
- How to handle `tool_name` not found in the `available_tools` list (edge case — treat called_tool_score as 0)
- Logging metric names for calibration

### Deferred Ideas (OUT OF SCOPE)

- detection_patterns.yml schema review (negation motifs + tool-triggering terms) — belongs in Phase 9 (tool_use_violation), already planned as 09-01
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WTOOL-01 | Single-threshold logic: score all available tools against the prompt; top1 score vs `wrong_tool_called` determines both "no tool was appropriate" and "better tool existed" cases | New `_check_wrong_tool` implementation below replaces the current AND-gate; all three cases use single threshold |
| WTOOL-02 | Reported score is top1_score (the best available tool's similarity to the prompt) | `hybrid_score` over all available tools; take `max` — this becomes the `score` field on the Flag |
| WTOOL-03 | Tool called with no available_tools → immediate flag (no threshold needed) | Early return with Flag before any embedding or threshold check |
| WTOOL-04 | Uses hybrid scoring (50/50) for prompt vs tool similarity comparisons | `bow_score` + `compare()` already available; `_get_tool_embeddings` cache reused for cosine component; BOW uses same `name + " " + description` text |
| WTOOL-05 | One threshold key: `wrong_tool_called` | Replace all references to old `wrong_tool` key in `tool_call_analyzer.py`, `main.py`, `calibrate.py`, `docker-compose.yml`, and `calibrated_thresholds.json` |
| WTOOL-06 | Per-method calibration run passes P/R benchmark before next phase | `python xeter/scripts/calibrate.py --flag-type wrong_tool` — fixture already has 11 labelled wrong_tool spans; may need augmentation for robustness |
</phase_requirements>

---

## Summary

Phase 8 rewrites `_check_wrong_tool` in `ToolCallAnalyzer` to use a single-threshold, recall-first algorithm. The current implementation has an inverted AND gate: it flags only when the called tool is not top-ranked AND the top-score is below threshold, which means spans where a clearly better tool exists (high top-score, wrong tool called) are silently suppressed. The rewrite corrects this by treating "top tool differs from called tool with trustworthy score" as a flag, "no tool was appropriate" as a flag, and "no available_tools at all" as an immediate flag.

The new algorithm is a surgical replacement of `_check_wrong_tool` only. All supporting infrastructure (`_get_tool_embeddings`, `hybrid_score`, `bow_score`, `BaseAnalyzer`) is unchanged. The only threshold key rename required is `wrong_tool` → `wrong_tool_called`, which touches four files: `tool_call_analyzer.py`, `main.py`, `calibrate.py`, and `docker-compose.yml`.

The calibration run (08-03) requires the live embedder container and runs `calibrate.py --flag-type wrong_tool`. The existing 11 labelled `wrong_tool` spans in `fixtures/labelled_spans.jsonl` are all "called wrong tool with available_tools present" cases; the fixture may need augmentation with "no appropriate tool" and "no available_tools" cases to make calibration meaningful across all three detection branches.

**Primary recommendation:** Rewrite `_check_wrong_tool` with the three-branch logic, rename the threshold key everywhere, verify existing tests still pass (update threshold dict key), add tests for the two new branches (WTOOL-03, the "no appropriate tool" path), then run calibration.

---

## Standard Stack

### Core (all already installed — no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | >=1.26 | Vector math for cosine similarity | Already in `BaseAnalyzer.compare()` |
| Python stdlib | 3.12+ | `hashlib`, `json`, `re` | Already used in `_get_tool_embeddings` cache |

### Existing utilities (in `base.py`)

| Utility | Location | Purpose |
|---------|----------|---------|
| `bow_score(a, b)` | `xeter/services/worker/base.py` | Jaccard token overlap; used for BOW component |
| `hybrid_score(cosine, bow)` | `xeter/services/worker/base.py` | 50/50 blend; used in `_check_wrong_args` |
| `_get_tool_embeddings(tools)` | `ToolCallAnalyzer` | Cache of tool embeddings by SHA-256 of tools JSON |
| `BaseAnalyzer.compare(a, b)` | `base.py` | Cosine similarity via numpy |
| `BaseAnalyzer.log_score(metric, score)` | `base.py` | Calibration dataset logging (must call before threshold) |

**Installation:** No new packages required.

---

## Architecture Patterns

### Current `_check_wrong_tool` (to be replaced)

The current logic (lines 141–230 of `tool_call_analyzer.py`):
1. Returns `[]` if `span.tool_name is None` or `span.prompt is None`
2. If `available_tools` present: score all tools by cosine only, sort descending, take top1
3. Flag if: `called_tool != top_tool AND top_score < threshold["wrong_tool"]`  ← **inverted AND gate bug**
4. If no `available_tools`: fall back to `prompt_vs_tool_name` cosine only

### New `_check_wrong_tool` — Three-branch algorithm

```
Branch 0 (guard): tool_name is None → return []  (method only applies when a tool was called)
Branch 1 (immediate): available_tools is None or empty → flag immediately, no score needed
Branch 2 (threshold): score all available_tools with hybrid_score; top1_score and top1_name
  Case A: top1_tool == called_tool AND top1_score >= threshold → clean, no flag
  Case B: top1_tool != called_tool AND top1_score >= threshold → flag (better tool existed)
  Case C: top1_score < threshold → flag (no tool was appropriate)
```

### Recommended Project Structure

Files touched in this phase:
```
xeter/services/worker/tool_call_analyzer.py   # _check_wrong_tool rewrite
xeter/services/worker/main.py                  # THRESHOLDS key rename
xeter/scripts/calibrate.py                     # FLAG_TYPES + DEFAULT_THRESHOLDS key rename
fixtures/calibrated_thresholds.json            # key rename + calibrated value
deploy/docker-compose.yml                      # env var rename
xeter/tests/worker/test_tool_call_analyzer.py  # update threshold dicts + new test cases
fixtures/labelled_spans.jsonl                  # potential augmentation for calibration
```

### Pattern 1: Hybrid scoring over available_tools list

```python
# Source: base.py bow_score/hybrid_score, tool_call_analyzer.py _get_tool_embeddings
def _check_wrong_tool(self, span: SpanData) -> list[Flag]:
    if span.tool_name is None:
        return []

    # WTOOL-03: immediate flag when no tools available
    if not span.available_tools:
        return [Flag(
            flag_type="wrong_tool",
            score=1.0,
            detail={"metric": "no_available_tools", "actual_tool": span.tool_name},
        )]

    if span.prompt is None:
        return []

    prompt_vec = self.embed(span.prompt)
    tool_vecs = self._get_tool_embeddings(span.available_tools)

    # WTOOL-04: hybrid score for each tool
    tool_scores: list[tuple[str, float]] = []
    for tool, tool_vec in zip(span.available_tools, tool_vecs):
        tool_text = f"{tool.get('name', '')} {tool.get('description', '')}".strip()
        cosine = self.compare(prompt_vec, tool_vec)
        bow = bow_score(span.prompt, tool_text)
        score = hybrid_score(cosine, bow)
        tool_scores.append((tool.get("name", ""), score))

    tool_scores.sort(key=lambda x: x[1], reverse=True)
    top_tool_name, top1_score = tool_scores[0]

    # WTOOL-02: log top1_score before threshold check
    self.log_score("prompt_vs_top1_tool_hybrid", top1_score)

    threshold = self._thresholds["wrong_tool_called"]

    # Case A: called correct tool with trustworthy score → clean
    if top_tool_name == span.tool_name and top1_score >= threshold:
        return []

    # Case B: better tool existed (score trustworthy, wrong tool called)
    # Case C: no tool was appropriate (score below threshold)
    ranked_detail = [{"name": n, "score": s} for n, s in tool_scores]
    return [Flag(
        flag_type="wrong_tool",
        score=top1_score,
        detail={
            "metric": "prompt_vs_top1_tool_hybrid",
            "expected_tool": top_tool_name,
            "actual_tool": span.tool_name,
            "score": top1_score,
            "ranked_tools": ranked_detail,
        },
    )]
```

### Pattern 2: Threshold key rename — all four locations

```python
# main.py — THRESHOLDS dict
"wrong_tool_called": float(os.environ.get("WORKER_THRESHOLD_WRONG_TOOL_CALLED", "0.5")),
# (remove "wrong_tool" entry)

# calibrate.py — FLAG_TYPES list and DEFAULT_THRESHOLDS dict
FLAG_TYPES = ["wrong_tool_called", "wrong_tool_args", ...]
DEFAULT_THRESHOLDS = {"wrong_tool_called": 0.5, "wrong_tool_args": 0.3, ...}

# calibrate.py — patch_docker_compose key_to_env dict
"wrong_tool_called": "WORKER_THRESHOLD_WRONG_TOOL_CALLED",

# docker-compose.yml
WORKER_THRESHOLD_WRONG_TOOL_CALLED: "0.5"
# (rename from WORKER_THRESHOLD_WRONG_TOOL)
```

### Pattern 3: Fixture augmentation for calibration

The current 11 `wrong_tool` spans all exercise Branch 2/Case B (better tool existed). For meaningful calibration covering all three detection branches, add:
- 3–5 spans with `available_tools=[]` or `available_tools=None` (Branch 1 / WTOOL-03)
- 3–5 spans where the prompt doesn't align with any available tool (Branch 2/Case C)

Use `xeter/scripts/add_fixture_spans.py` as the model for adding spans inline.

### Anti-Patterns to Avoid

- **Keeping old cosine-only tool scoring:** The current `_check_wrong_tool` uses `self.compare()` (cosine only). The rewrite must use `hybrid_score(cosine, bow)`. Not doing so leaves WTOOL-04 incomplete.
- **Forgetting BOW uses the same tool text as embeddings:** `_get_tool_embeddings` embeds `f"{name} {description}"`. The BOW component must use the same `name + " " + description` string for consistency.
- **Skipping log_score for Branch 1:** The `no_available_tools` immediate flag (WTOOL-03) produces no embedding score. Log a fixed sentinel (e.g., `self.log_score("no_available_tools", 1.0)`) so the calibration dataset has a record for every span.
- **Forgetting to update test threshold dicts:** Existing tests use `DEFAULT_THRESHOLDS = {"wrong_tool": 0.5, ...}`. After the rename, these must reference `"wrong_tool_called"` or the tests will error with `KeyError`.
- **Assuming calibrate.py hill_climb direction matches new logic:** The current hill_climb raises threshold until precision drops (maximizes precision). For recall-first calibration, the stopping criterion must instead be: continue while recall >= target_recall, then pick threshold with highest precision that still meets recall. Alternatively, pick the lowest threshold that achieves acceptable precision while keeping recall high. The CONTEXT.md is intentionally vague here — the hill_climb as written already provides good starting behavior; the recall-first interpretation is met by choosing the threshold at the "elbow" or reporting both values and letting the user choose.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cosine similarity | Custom dot-product loop | `BaseAnalyzer.compare(a, b)` | Already handles zero-norm edge case |
| BOW scoring | Custom Jaccard | `bow_score(a, b)` from base.py | Handles empty string edge case |
| Hybrid blend | Inline arithmetic | `hybrid_score(cosine, bow)` from base.py | HYBRID-01 contract; consistent weight |
| Tool embedding cache | Dict keyed by tool list | `_get_tool_embeddings(tools)` | SHA-256 hash, already works |

**Key insight:** All required scoring infrastructure already exists in `base.py` from Phase 7. Phase 8 is a logic rewrite, not new infrastructure work.

---

## Common Pitfalls

### Pitfall 1: `description` absent from a tool dict
**What goes wrong:** `tool.get('description', '')` returns empty string; BOW text becomes just the tool name; hybrid score skewed.
**Why it happens:** Some tool schemas omit `description`.
**How to avoid:** Fall back to name only — `tool_text = tool.get('name', '') + (" " + tool.get('description', '')).rstrip()`. This is Claude's discretion per CONTEXT.md.
**Warning signs:** BOW score of 0.0 for all tools on a span where the prompt clearly matches the tool name.

### Pitfall 2: Called tool not found in `available_tools` list
**What goes wrong:** `top1_tool != span.tool_name` is always True (tool not in list), so every span with a mismatch is flagged regardless of intent.
**Why it happens:** The agent called a tool that wasn't in the advertised available_tools list.
**How to avoid:** Per CONTEXT.md, treat `called_tool_score` as 0 in this case. Since we only compare `top1_tool_name != span.tool_name`, this case is handled correctly by the existing logic — if the called tool isn't in the list, it can't be the top-ranked match, so either Case B or C fires naturally.
**Warning signs:** Many false positives on spans where tool_name is a valid tool not listed in available_tools.

### Pitfall 3: Old `wrong_tool` threshold key left in some files
**What goes wrong:** `KeyError: 'wrong_tool_called'` at runtime; or old key silently falling back to default.
**Why it happens:** The rename touches 4+ files; easy to miss one.
**How to avoid:** After the rename, grep the entire codebase for `"wrong_tool"` (the old key) to verify no stale references remain. The test file threshold dicts are the most likely to be missed.
**Warning signs:** Tests pass but calibration crashes with KeyError, or docker-compose still has old env var name.

### Pitfall 4: Hill-climb stopping criterion vs recall-first goal
**What goes wrong:** The hill-climb raises threshold until precision drops — this maximizes precision, not recall. At low thresholds, recall is high but precision is low.
**Why it happens:** The existing calibrate.py is designed to maximize precision. The CONTEXT.md specifies recall-first but doesn't change the hill-climb algorithm.
**How to avoid:** For Phase 8, the hill-climb behavior is acceptable as-is — the recall-first instruction means: accept a lower precision threshold if it achieves higher recall. Report both P and R for every step (already done). The user reviews the table and picks the threshold in 08-02. Calibrate.py does not need algorithm changes — just running it and inspecting output is sufficient.
**Warning signs:** Choosing a threshold that gives R=0.5 when a lower threshold gives R=1.0 at acceptable precision.

### Pitfall 5: Fixture imbalance — all 11 wrong_tool spans are Case B only
**What goes wrong:** The hill-climb calibrates only for "better tool existed" spans. WTOOL-03 (no available_tools) is never exercised in calibration; Case C ("no tool appropriate") is also absent.
**Why it happens:** The original fixture was generated before the three-branch algorithm was designed.
**How to avoid:** Add fixture spans for the two missing branches before running calibration. This is a Wave 0 task in the plan.
**Warning signs:** 100% recall on existing fixture but WTOOL-03 edge case never verified during calibration.

---

## Code Examples

### New `_check_wrong_tool` skeleton (verified against base.py API)

```python
# Source: tool_call_analyzer.py (current) + base.py (bow_score, hybrid_score)

def _check_wrong_tool(self, span: SpanData) -> list[Flag]:
    """Detect when the called tool is not the best semantic match for the prompt.

    Three cases (WTOOL-01):
      1. No available_tools: immediate flag (WTOOL-03)
      2. top1_tool != called_tool AND top1_score >= threshold: better tool existed
      3. top1_score < threshold: no tool was appropriate

    Correct: top1_tool == called_tool AND top1_score >= threshold.
    Reported score: top1_score via hybrid_score (WTOOL-02, WTOOL-04).
    """
    if span.tool_name is None:
        return []

    # WTOOL-03: immediate flag — tool called but none available
    if not span.available_tools:
        self.log_score("no_available_tools", 1.0)
        return [Flag(
            flag_type="wrong_tool",
            score=1.0,
            detail={
                "metric": "no_available_tools",
                "actual_tool": span.tool_name,
            },
        )]

    if span.prompt is None:
        return []

    prompt_vec = self.embed(span.prompt)
    tool_vecs = self._get_tool_embeddings(span.available_tools)

    # WTOOL-04: hybrid score (50/50 cosine + BOW)
    tool_scores: list[tuple[str, float]] = []
    for tool, tool_vec in zip(span.available_tools, tool_vecs):
        name = tool.get("name", "")
        desc = tool.get("description", "")
        tool_text = f"{name} {desc}".strip() if desc else name
        cosine = self.compare(prompt_vec, tool_vec)
        bow = bow_score(span.prompt, tool_text)
        score = hybrid_score(cosine, bow)
        tool_scores.append((name, score))

    tool_scores.sort(key=lambda x: x[1], reverse=True)
    top1_name, top1_score = tool_scores[0]

    # WTOOL-02: log top1_score before threshold check
    self.log_score("prompt_vs_top1_tool_hybrid", top1_score)

    # Correct case: called the best tool with trustworthy score
    if top1_name == span.tool_name and top1_score >= self._thresholds["wrong_tool_called"]:
        return []

    # All other cases: flag
    return [Flag(
        flag_type="wrong_tool",
        score=top1_score,  # WTOOL-02
        detail={
            "metric": "prompt_vs_top1_tool_hybrid",
            "expected_tool": top1_name,
            "actual_tool": span.tool_name,
            "score": top1_score,
            "ranked_tools": [{"name": n, "score": s} for n, s in tool_scores],
        },
    )]
```

### New unit tests (to add to test_tool_call_analyzer.py)

```python
# Tests for new branches in rewritten _check_wrong_tool

def test_wrong_tool_immediate_flag_no_available_tools():
    """WTOOL-03: tool called but available_tools is None → immediate flag."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_called": 0.5})
    span = make_clean_span(tool_name="search_web", available_tools=None)
    flags = analyzer._check_wrong_tool(span)
    assert any(f.flag_type == "wrong_tool" for f in flags)
    flag = next(f for f in flags if f.flag_type == "wrong_tool")
    assert flag.detail.get("metric") == "no_available_tools"
    # No embed() calls should happen
    assert embedder.encode.call_count == 0


def test_wrong_tool_immediate_flag_empty_available_tools():
    """WTOOL-03: tool called but available_tools is [] → immediate flag."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_called": 0.5})
    span = make_clean_span(tool_name="search_web", available_tools=[])
    flags = analyzer._check_wrong_tool(span)
    assert any(f.flag_type == "wrong_tool" for f in flags)


def test_wrong_tool_no_flag_when_top1_correct_and_above_threshold():
    """WTOOL-01 correct case: top1 == called tool, score >= threshold → no flag."""
    embedder = make_mock_embedder(_unit_vec())  # all same → cos=1.0, bow=any → top1 == any tool
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_called": 0.5})
    span = make_clean_span(
        tool_name="search_web",
        available_tools=[{"name": "search_web", "description": "Search the web"}],
    )
    flags = analyzer._check_wrong_tool(span)
    assert not any(f.flag_type == "wrong_tool" for f in flags)


def test_wrong_tool_score_is_top1_hybrid():
    """WTOOL-02: reported score in flag.score is top1 hybrid score."""
    embedder = make_mock_embedder()
    # Make prompt and search_web description similar, calculator dissimilar
    # (reuse test_wrong_tool_uses_available_tools_ranking vector setup)
    # ... flag.score must equal max hybrid score across tools
    ...  # implementation detail for the plan author
```

### Threshold key rename locations

```
xeter/services/worker/tool_call_analyzer.py:
  self._thresholds["wrong_tool"]  →  self._thresholds["wrong_tool_called"]

xeter/services/worker/main.py:
  THRESHOLDS dict: "wrong_tool" key → "wrong_tool_called"
  WORKER_THRESHOLD_WRONG_TOOL env var → WORKER_THRESHOLD_WRONG_TOOL_CALLED

xeter/scripts/calibrate.py:
  FLAG_TYPES list: "wrong_tool" → "wrong_tool_called"
  DEFAULT_THRESHOLDS: "wrong_tool" key → "wrong_tool_called"
  patch_docker_compose key_to_env: "wrong_tool" → "wrong_tool_called"
  key: "WORKER_THRESHOLD_WRONG_TOOL" → "WORKER_THRESHOLD_WRONG_TOOL_CALLED"

deploy/docker-compose.yml:
  WORKER_THRESHOLD_WRONG_TOOL → WORKER_THRESHOLD_WRONG_TOOL_CALLED

fixtures/calibrated_thresholds.json:
  "wrong_tool" key → "wrong_tool_called"

xeter/tests/worker/test_tool_call_analyzer.py:
  DEFAULT_THRESHOLDS dict: "wrong_tool" → "wrong_tool_called"
  All {**DEFAULT_THRESHOLDS, "wrong_tool": 0.5} overrides → "wrong_tool_called"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Cosine-only tool scoring | Hybrid (50/50 cosine+BOW) | Phase 7 (HYBRID-01) | BOW component catches name/keyword exact matches |
| AND gate: wrong tool AND low score | Three-branch: immediate/case-B/case-C | Phase 8 | Fixes inverted gate; high-score wrong-tool spans now correctly flagged |
| `wrong_tool` threshold key | `wrong_tool_called` threshold key | Phase 8 | Semantically accurate name; old key retired |
| Gap score reported | top1_score reported | Phase 8 | Simpler to interpret; consistent with other check methods |

**Retired in Phase 8:**
- `wrong_tool` threshold key: replaced by `wrong_tool_called`
- `WORKER_THRESHOLD_WRONG_TOOL` env var: replaced by `WORKER_THRESHOLD_WRONG_TOOL_CALLED`
- Cosine-only scoring in `_check_wrong_tool`: replaced by hybrid scoring

---

## Open Questions

1. **Does the hill-climb stopping criterion need to change for recall-first?**
   - What we know: current hill_climb raises threshold until precision drops (maximizes precision, not recall). The CONTEXT.md says "maximize recall while keeping precision as high as possible."
   - What's unclear: whether the user expects the algorithm to auto-select recall-maximizing threshold, or just report both P and R and let the user choose.
   - Recommendation: Do not change the hill-climb algorithm. Run calibration, report both P and R per step (already done), and let the user choose the threshold in the 08-02 review step. The three-step plan structure (08-01 implement, 08-02 review, 08-03 calibrate) explicitly includes a review checkpoint.

2. **Should `wrong_tool_called` key appear in `WORKER_THRESHOLD_WRONG_TOOL_CALLED` env var or reuse the old name?**
   - What we know: CONTEXT.md only specifies the Python dict key name. The env var name is a separate concern.
   - What's unclear: whether to use `WORKER_THRESHOLD_WRONG_TOOL_CALLED` or keep the env var as `WORKER_THRESHOLD_WRONG_TOOL` for backward compatibility.
   - Recommendation: Rename to `WORKER_THRESHOLD_WRONG_TOOL_CALLED` for consistency with the key name. There is no backward compatibility concern — this is a development-only change.

3. **Fixture augmentation scope: how many new spans to add?**
   - What we know: 11 wrong_tool spans exist, all Case B. WTOOL-03 (no available_tools) and Case C (no appropriate tool) have zero fixture coverage.
   - What's unclear: whether calibration is meaningful with only 3–5 new spans per case.
   - Recommendation: Add 3–5 spans for WTOOL-03 (no available_tools) and 3–5 spans for Case C. Mark them with the same `"anomaly_type": "wrong_tool"` label. The calibration scoring already counts any wrong_tool flag as TP — all three branches produce the same flag_type.

---

## Validation Architecture

> nyquist_validation not present in .planning/config.json — using standard test commands

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (installed in pyproject.toml) |
| Config file | `xeter/pyproject.toml` — `testpaths = ["tests"]` |
| Quick run command | `python -m pytest xeter/tests/worker/test_tool_call_analyzer.py -x -q` |
| Full suite command | `python -m pytest xeter/tests/worker/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WTOOL-01 | Single-threshold: Case B flags (better tool existed), Case C flags (no tool appropriate) | unit | `python -m pytest xeter/tests/worker/test_tool_call_analyzer.py::test_wrong_tool_flagged_when_below_threshold xeter/tests/worker/test_tool_call_analyzer.py::test_wrong_tool_uses_available_tools_ranking -x` | Partial (tests exist but test old logic) |
| WTOOL-02 | Reported score is top1 hybrid score | unit | `python -m pytest xeter/tests/worker/test_tool_call_analyzer.py -k "wrong_tool" -x` | Partial (new test needed) |
| WTOOL-03 | No available_tools → immediate flag | unit | `python -m pytest xeter/tests/worker/test_tool_call_analyzer.py::test_wrong_tool_immediate_flag_no_available_tools -x` | No — Wave 0 gap |
| WTOOL-04 | Hybrid scoring for tool comparisons | unit | `python -m pytest xeter/tests/worker/test_tool_call_analyzer.py -k "hybrid" -x` | Partial (hybrid_score tests exist; new integration test needed) |
| WTOOL-05 | `wrong_tool_called` key in calibrated_thresholds.json | manual | inspect `fixtures/calibrated_thresholds.json` | No — after calibration run |
| WTOOL-06 | Calibration P/R benchmark | manual (live embedder) | `python xeter/scripts/calibrate.py --flag-type wrong_tool` | No — 08-03 plan |

### Wave 0 Gaps

- [ ] `xeter/tests/worker/test_tool_call_analyzer.py` — add `test_wrong_tool_immediate_flag_no_available_tools` (WTOOL-03)
- [ ] `xeter/tests/worker/test_tool_call_analyzer.py` — add `test_wrong_tool_immediate_flag_empty_available_tools` (WTOOL-03)
- [ ] `xeter/tests/worker/test_tool_call_analyzer.py` — add `test_wrong_tool_score_is_top1_hybrid` (WTOOL-02)
- [ ] `xeter/tests/worker/test_tool_call_analyzer.py` — update `DEFAULT_THRESHOLDS` key from `"wrong_tool"` to `"wrong_tool_called"`
- [ ] `xeter/tests/worker/test_tool_call_analyzer.py` — update all inline threshold overrides using `"wrong_tool"` key
- [ ] `fixtures/labelled_spans.jsonl` — add 3–5 `wrong_tool` spans with `available_tools=None` (WTOOL-03 coverage)
- [ ] `fixtures/labelled_spans.jsonl` — add 3–5 `wrong_tool` spans where no tool matches prompt (Case C coverage)

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection — `xeter/services/worker/tool_call_analyzer.py` (current implementation, lines 141–230)
- Direct codebase inspection — `xeter/services/worker/base.py` (bow_score, hybrid_score, BaseAnalyzer)
- Direct codebase inspection — `xeter/scripts/calibrate.py` (hill-climb, FLAG_TYPES, patch_docker_compose)
- Direct codebase inspection — `fixtures/labelled_spans.jsonl` (11 wrong_tool spans confirmed, all Case B)
- Direct codebase inspection — `fixtures/calibrated_thresholds.json` (current keys and values)
- Direct codebase inspection — `xeter/tests/worker/test_tool_call_analyzer.py` (26 existing tests)
- `.planning/phases/08-wrong-tool-rewrite/08-CONTEXT.md` — locked decisions

### Secondary (MEDIUM confidence)
- Phase 7 calibration result (STATE.md): `wrong_tool_args` threshold=0.30, P=0.40, R=0.90 — establishes calibration baseline and expectations for wrong_tool

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in use; no new dependencies
- Architecture: HIGH — implementation directly derived from existing code + locked CONTEXT.md decisions
- Pitfalls: HIGH — identified by direct code inspection (inverted AND gate visible at line 186–189)
- Calibration expectations: MEDIUM — 11 fixture spans for wrong_tool, limited to Case B only; P/R outcome depends on fixture augmentation

**Research date:** 2026-04-07
**Valid until:** 2026-05-07 (stable domain — pure Python logic rewrite with no external dependencies)

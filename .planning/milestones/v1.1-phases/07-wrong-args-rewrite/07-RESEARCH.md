# Phase 7: wrong_args Rewrite — Research

**Researched:** 2026-04-06
**Domain:** Python heuristic analysis — argument error detection, hybrid similarity scoring, calibration script extension
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| HYBRID-01 | Shared hybrid scoring utility — 50/50 blend of cosine similarity (embedding) and bag-of-words score (token overlap) used by all similarity-based checks | BOW via Jaccard token overlap is available in stdlib (no new dep); function lives in `base.py` or a new `scoring.py` module |
| ARGS-01 | Detects bad arguments via `tool_output` error pattern matching (regex, no embedding, fires first) | Compiled regex list in `_check_wrong_args`; short-circuits before any `embed()` call |
| ARGS-02 | Detects semantic mismatch by embedding flattened argument *values* (not raw JSON string) | `json.loads` + extract `.values()` + join as string; embed the result, not raw JSON |
| ARGS-03 | Uses hybrid scoring (50/50 embed + BOW) for the semantic path | Call the HYBRID-01 utility with (prompt, flattened_values) |
| ARGS-04 | Skips semantic check when flattened values are empty or all-numeric | Guard: `not flat.strip()` or all tokens match `^[\d\.\-\+\*\/\(\)\^\%\s]+$` |
| ARGS-05 | `low_confidence: True` removed from flag detail | Delete the key from the Flag detail dict |
| ARGS-06 | Per-method calibration run passes P/R benchmark before next phase | `wrong_tool_args` added to `FLAG_TYPES` in `calibrate.py` after ARGS-01–05 enable reliable scoring |
| CAL-01 | `calibrate.py` supports `"binary": true` per flag type to exclude from numeric P/R sweep | Add `BINARY_FLAG_TYPES` set; skip hill-climb, report fixed threshold only |
| CAL-02 | `calibrate.py` supports per-method mode — calibrate a single flag_type in isolation | Add `--flag-type` CLI argument via `argparse`; filter `FLAG_TYPES` list before main loop |

</phase_requirements>

---

## Summary

Phase 7 rewrites `_check_wrong_args` from a naive raw-JSON cosine comparison to a two-path detector: an output-error priority path (regex, no embeddings) and a semantic path that embeds flattened argument values using a new shared hybrid (50/50 cosine + BOW) scoring utility. Simultaneously, `calibrate.py` gains two infrastructure upgrades — `--flag-type` for per-method isolation and a binary-flag bypass — that unblock both this phase's calibration run and Phase 9's `tool_use_violation` proximity scorer.

The fixture (`fixtures/labelled_spans.jsonl`) contains 10 labelled `wrong_tool_args` spans. Inspection shows all 10 have `tool_output = "Email delivered"` — none contain output error patterns. This is by design: the fixture currently exercises the semantic mismatch path only. The error-path (ARGS-01) will be verified by unit tests with synthetic spans. The hybrid scoring utility (HYBRID-01) uses stdlib only (no new dependency: token overlap via `set` operations), keeping the worker Docker image unchanged.

The current `_check_wrong_args` embeds the raw JSON string `tool_arguments` and compares it to the prompt. This is why it was excluded from P/R calibration with `low_confidence: True` — JSON keys contaminate the signal. The fix is to extract only the argument *values*, flatten them to a plain string, apply empty/all-numeric guards, and use hybrid scoring. After the rewrite, `wrong_tool_args` moves from excluded back into `FLAG_TYPES` and the per-method calibration run (CAL-02) validates it independently.

**Primary recommendation:** Implement HYBRID-01 first (07-02), then build the `_check_wrong_args` rewrite on top of it (07-03), with calibration infrastructure changes (07-01) done in parallel or first since they are independent of each other.

---

## Standard Stack

### Core (already in project — no new installs)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `re` (stdlib) | Python 3.12+ | Compile error-pattern regexes for ARGS-01 | Zero-dep; `re.compile` with `re.IGNORECASE` is the correct approach |
| `json` (stdlib) | Python 3.12+ | Parse `tool_arguments` string to extract values (ARGS-02) | Already used throughout the codebase |
| `numpy` | >=1.26 | Cosine similarity computation in `BaseAnalyzer.compare()` | Already installed; no change |
| `argparse` (stdlib) | Python 3.12+ | `--flag-type` CLI arg for calibrate.py (CAL-02) | Standard; no new dep |
| `pytest` | installed | Unit test harness | Already in pyproject.toml |

### No New Dependencies Required

The BOW component of HYBRID-01 uses Jaccard token overlap via Python `set` operations — no `sklearn`, `nltk`, `rank_bm25`, or `gensim` needed. All three of those libraries were tested and are not installed in this environment. The stdlib approach is simpler, dependency-free, and sufficient for the token-overlap signal intended by the requirement.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Jaccard token overlap (BOW) | `sklearn` TF-IDF cosine | sklearn available but not installed; TF-IDF adds IDF weighting which is overkill for two short texts |
| Jaccard token overlap (BOW) | `rank_bm25` BM25 | BM25 handles document-length normalization better, but not installed and the two-text case doesn't need it |
| Custom regex list (ARGS-01) | External schema file for error patterns | Schema file is already planned for NOTOOL-04 (Phase 9); reusing it here would couple phases — keep error patterns inline as module-level compiled list in the analyzer |

---

## Architecture Patterns

### Existing File Structure (relevant to this phase)

```
xeter/
├── services/
│   └── worker/
│       ├── base.py                  # BaseAnalyzer, Flag, SpanData, EmbedderClient
│       └── tool_call_analyzer.py    # ToolCallAnalyzer — _check_wrong_args lives here
├── scripts/
│   └── calibrate.py                 # Calibration harness — gets CAL-01, CAL-02
└── tests/
    └── worker/
        └── test_tool_call_analyzer.py  # Existing 16 tests — must stay green
fixtures/
└── labelled_spans.jsonl             # 210 spans: 10 wrong_tool_args, rest as shown
```

### Pattern 1: Two-Path Error Detection (ARGS-01 priority gate)

**What:** Check `tool_output` for error patterns using a module-level compiled regex list before any embedding computation. If a match is found, return the flag immediately.

**When to use:** Whenever a deterministic signal is cheaper and more reliable than a probabilistic one — fire the cheap check first, skip the expensive one.

**Example:**

```python
# In tool_call_analyzer.py — module level
import re

_WRONG_ARGS_ERROR_PATTERNS: list[re.Pattern] = [
    re.compile(r'invalid argument', re.IGNORECASE),
    re.compile(r'invalid param', re.IGNORECASE),
    re.compile(r'missing required', re.IGNORECASE),
    re.compile(r'missing param', re.IGNORECASE),
    re.compile(r'required field', re.IGNORECASE),
    re.compile(r'validation error', re.IGNORECASE),
    re.compile(r'type error', re.IGNORECASE),
    re.compile(r'value error', re.IGNORECASE),
    re.compile(r'parse error', re.IGNORECASE),
    re.compile(r'HTTP [4][0-9][0-9]', re.IGNORECASE),
    re.compile(r'status[ _]?code[: ]*4[0-9][0-9]', re.IGNORECASE),
    re.compile(r'400 bad request', re.IGNORECASE),
    re.compile(r'422 unprocessable', re.IGNORECASE),
]

def _check_wrong_args(self, span: SpanData) -> list[Flag]:
    if span.tool_arguments is None or span.prompt is None:
        return []

    # ARGS-01: output-error priority path (no embedding)
    if span.tool_output and any(p.search(span.tool_output) for p in _WRONG_ARGS_ERROR_PATTERNS):
        self.log_score("wrong_args_output_error", 1.0)
        return [Flag(
            flag_type="wrong_tool_args",
            score=1.0,
            detail={"metric": "output_error_pattern", "source": "tool_output"},
        )]

    # ARGS-02/03/04: semantic path with flattened values + hybrid scoring
    flattened = _flatten_arg_values(span.tool_arguments)
    if _should_skip_embedding(flattened):
        return []

    score = hybrid_score(self, span.prompt, flattened)  # HYBRID-01
    self.log_score("prompt_vs_args_hybrid", score)

    if score < self._thresholds["wrong_tool_args"]:
        return [Flag(
            flag_type="wrong_tool_args",
            score=score,
            detail={"metric": "prompt_vs_args_hybrid", "score": score},
            # ARGS-05: no low_confidence key
        )]
    return []
```

### Pattern 2: Flatten Argument Values (ARGS-02)

**What:** Parse the JSON `tool_arguments` string and join only the leaf values as a plain text string for embedding.

**When to use:** Whenever argument text needs to be embedded — never embed raw JSON.

**Example:**

```python
# Source: derived from json stdlib + manual testing on fixture data
def _flatten_arg_values(args_str: str) -> str:
    """Extract leaf values from tool_arguments JSON and join as plain text."""
    try:
        parsed = json.loads(args_str)
        if not isinstance(parsed, dict):
            return args_str
        return " ".join(str(v) for v in parsed.values() if v is not None)
    except (json.JSONDecodeError, TypeError):
        return args_str  # fallback: embed raw string if not parseable
```

### Pattern 3: Empty / All-Numeric Guard (ARGS-04)

**What:** Skip embedding if flattened values are empty or consist entirely of numeric tokens (operators, digits, decimal points).

**When to use:** Before any `self.embed()` call on argument values.

**Example:**

```python
_NUMERIC_TOKEN_RE = re.compile(r'^[\d\.\-\+\*\/\(\)\^\%\s]+$')

def _should_skip_embedding(flattened: str) -> bool:
    """Return True if flattened values are empty or all-numeric."""
    text = flattened.strip()
    if not text:
        return True
    return bool(_NUMERIC_TOKEN_RE.match(text))
```

Manual test results on representative cases:
- `"10000 * (1 + 0.05) ** 3"` → skip (all-numeric/operator tokens)
- `"42 100"` → skip
- `"sales@competitor.com Partnership Proposal..."` → embed (meaningful text)
- `"users"` → embed (single meaningful word)
- `""` → skip

### Pattern 4: Hybrid Scoring Utility (HYBRID-01)

**What:** A module-level function (or `BaseAnalyzer` method) that returns `0.5 * cosine_sim + 0.5 * bow_score`. The BOW component uses Jaccard token overlap (intersection / union of lowercased token sets).

**When to use:** Whenever a check method needs a semantic similarity score. All subsequent phases (8, 9, 10) will call this utility — placing it in `base.py` makes it available to all analyzers without import gymnastics.

**Placement decision:** Add as a standalone function in `base.py` (not a method of `BaseAnalyzer`), so it can be called with a pre-computed cosine score and an arbitrary string pair. This avoids embedding being coupled into the utility itself.

**Example:**

```python
# In base.py
def bow_score(text_a: str, text_b: str) -> float:
    """Jaccard token overlap between two strings. Returns [0, 1]."""
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def hybrid_score(cosine: float, bow: float, weight: float = 0.5) -> float:
    """50/50 blend of cosine similarity and BOW score."""
    return weight * cosine + (1.0 - weight) * bow
```

And in `ToolCallAnalyzer`:

```python
# Usage in _check_wrong_args semantic path
from xeter.services.worker.base import bow_score, hybrid_score

prompt_vec = self.embed(span.prompt)
args_vec = self.embed(flattened)
cosine = self.compare(prompt_vec, args_vec)
bow = bow_score(span.prompt, flattened)
score = hybrid_score(cosine, bow)
```

### Pattern 5: Calibration — Per-Method Mode (CAL-02)

**What:** Add `--flag-type` argument to `calibrate.py` using `argparse`. When provided, filter `FLAG_TYPES` to only include the specified type before the main hill-climb loop.

**Example:**

```python
# In calibrate.py main()
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Calibrate ToolCallAnalyzer thresholds")
    parser.add_argument(
        "--flag-type",
        dest="flag_type",
        default=None,
        help="Calibrate only this flag type (e.g. wrong_tool_args)",
    )
    return parser.parse_args()

def main() -> dict:
    args = parse_args()
    # ...
    flag_types = FLAG_TYPES
    if args.flag_type:
        if args.flag_type not in FLAG_TYPES and args.flag_type not in BINARY_FLAG_TYPES:
            print(f"ERROR: Unknown flag type: {args.flag_type}")
            sys.exit(1)
        flag_types = [args.flag_type] if args.flag_type in FLAG_TYPES else []
        # Handle binary separately
```

### Pattern 6: Calibration — Binary Flag Support (CAL-01)

**What:** Define a `BINARY_FLAG_TYPES` set. Flag types listed there are NOT included in the numeric hill-climb sweep. Instead, they are reported with a fixed threshold (e.g., `1.0`) and their precision/recall are reported as "N/A — binary detection".

**Why:** `tool_use_violation` (Phase 9) uses windowed proximity scoring that is always > 0 when a match fires — there is no numeric threshold to sweep. Trying to hill-climb it would be meaningless.

**Example:**

```python
# In calibrate.py
BINARY_FLAG_TYPES: set[str] = {
    # "tool_use_violation",  # placeholder — added in Phase 9
}

# In main loop:
for flag_type in flag_types:
    if flag_type in BINARY_FLAG_TYPES:
        print(f"\n  [{flag_type}] binary flag — skipping numeric sweep")
        results[flag_type] = {
            "best_threshold": 1.0,
            "best_precision": None,
            "best_recall": None,
            "history": [],
            "steps": 0,
            "binary": True,
        }
        continue
    # normal hill climb
    best_threshold, best_precision, best_recall, history = hill_climb(...)
```

### Anti-Patterns to Avoid

- **Embedding raw `tool_arguments` JSON string:** JSON keys like `"to"`, `"subject"`, `"body"` add noise that drowns out the actual value content. Always flatten to values only.
- **Global threshold modification during per-method calibration:** When calibrating `wrong_tool_args`, all other thresholds must stay at their current calibrated values. The existing `dict(current_thresholds)` pattern in `evaluate_flag_type` already handles this correctly — preserve it.
- **Logging score after threshold comparison:** The existing codebase enforces `log_score()` BEFORE any `if score < threshold` check. The new code must maintain this invariant — both the error path (log 1.0) and the semantic path (log hybrid score) call `log_score` before returning.
- **Placing the hybrid utility inside `ToolCallAnalyzer`:** It must be available to all analyzers (wrong_tool, no_tool, excessive_tool in later phases). Put it in `base.py` as module-level functions.
- **Making the all-numeric guard too narrow:** The guard must catch `"10000 * (1 + 0.05) ** 3"` — this string is all operators/digits/punctuation. Testing confirms the regex `^[\d\.\-\+\*\/\(\)\^\%\s]+$` handles it correctly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token-overlap similarity | Custom n-gram or edit-distance scorer | Jaccard over lowercased `.split()` tokens | Simple, fast, no deps; verified to produce discriminating scores on fixture data |
| CLI argument parsing | Manual `sys.argv` slicing | `argparse` stdlib | Standard Python pattern; handles `--help`, error messages, type coercion automatically |
| JSON value extraction | Recursive tree walker | `json.loads(s).values()` with `isinstance(parsed, dict)` guard | Tool arguments are always flat dicts in this codebase (confirmed by fixture data); no nesting observed |

**Key insight:** The BOW component of the hybrid score deliberately does not use IDF weighting. For two short texts (prompt ~10–20 tokens, flattened args ~5–15 tokens), IDF does not help — the discriminating power comes purely from shared vocabulary.

---

## Common Pitfalls

### Pitfall 1: Re-embedding Tools During wrong_args Check

**What goes wrong:** `_check_wrong_args` might inadvertently trigger tool re-embedding by calling methods that touch `_tool_embed_cache`.
**Why it happens:** The wrong_args check only involves prompt and arg values — no tool embeddings needed.
**How to avoid:** `_check_wrong_args` must never call `_get_tool_embeddings()` or embed any tool field.
**Warning signs:** Unusually high `encode.call_count` in unit tests for `_check_wrong_args` in isolation.

### Pitfall 2: Test 7 Will Break (Intentionally)

**What goes wrong:** `test_wrong_args_flag_has_low_confidence` asserts `detail.get("low_confidence") is True`. After ARGS-05, this key is removed, so the test will fail.
**Why it happens:** The test was written against the old contract.
**How to avoid:** Update `test_wrong_args_flag_has_low_confidence` as part of 07-03. The new test should assert `"low_confidence" not in detail`.
**Warning signs:** pytest reports `test_wrong_args_flag_has_low_confidence` FAILED after the rewrite.

### Pitfall 3: Fixture Has No Error-Pattern Examples for wrong_tool_args

**What goes wrong:** All 10 `wrong_tool_args` spans in `labelled_spans.jsonl` have `tool_output = "Email delivered"`. The ARGS-01 error-path will never fire against the fixture.
**Why it happens:** The fixture was built before the error-path design.
**How to avoid:** Cover ARGS-01 via unit tests with synthetic spans (e.g., `tool_output = "invalid argument: expected string"`). Do NOT add error-pattern spans to the fixture — doing so would let the zero-cost regex path inflate P/R metrics artificially. The calibration run (07-05) should test the semantic path exclusively.
**Warning signs:** If ARGS-06 calibration shows suspiciously perfect precision/recall on wrong_tool_args, check whether error-pattern spans leaked into the fixture.

### Pitfall 4: `argparse` and `sys.exit(1)` Conflict with Unit Tests

**What goes wrong:** Tests that call `calibrate.main()` directly will hit `sys.exit(1)` if the embedder is unreachable or an unknown flag type is passed.
**Why it happens:** `argparse.parse_args()` reads `sys.argv` — test calls will see test-runner arguments.
**How to avoid:** Keep `parse_args()` as a separate function; in tests, patch `sys.argv` or pass arguments as parameters. Existing calibration tests (if any) are integration tests requiring the embedder container — they are not run in CI.

### Pitfall 5: All-Numeric Guard Must Not Block Numeric-Prefixed Strings

**What goes wrong:** A value like `"10.5 percent growth"` would not be all-numeric, but the regex must not incorrectly classify it as numeric.
**Why it happens:** Partial numeric strings that contain words should be embedded.
**How to avoid:** The regex `^[\d\.\-\+\*\/\(\)\^\%\s]+$` requires the ENTIRE string to match — a single letter character causes it to fail, allowing embedding. Verified correct with test cases above.

### Pitfall 6: `wrong_tool_args` Added to `FLAG_TYPES` but Still Excluded

**What goes wrong:** `calibrate.py` has a hardcoded `NOTE:` print statement saying `wrong_tool_args` is excluded. After the rewrite, this note becomes misleading and wrong.
**Why it happens:** The note was accurate in v1.0. After Phase 7, it must be removed.
**How to avoid:** In 07-01 or 07-03, remove the exclusion comment and add `wrong_tool_args` to `FLAG_TYPES`. The `DEFAULT_THRESHOLDS` dict already has `"wrong_tool_args": 0.4` — just un-exclude it.

---

## Code Examples

### Verified: Current _check_wrong_args (to be replaced)

```python
# Source: xeter/services/worker/tool_call_analyzer.py lines 180–207
def _check_wrong_args(self, span: SpanData) -> list[Flag]:
    if span.tool_arguments is None or span.prompt is None:
        return []

    prompt_vec = self.embed(span.prompt)
    args_vec = self.embed(span.tool_arguments)  # BUG: embeds raw JSON
    score = self.compare(prompt_vec, args_vec)

    self.log_score("prompt_vs_tool_args", score)

    if score < self._thresholds["wrong_tool_args"]:
        return [Flag(
            flag_type="wrong_tool_args",
            score=score,
            detail={
                "metric": "prompt_vs_tool_args",
                "score": score,
                "low_confidence": True,  # REMOVED by ARGS-05
            },
        )]
    return []
```

### Verified: calibrate.py FLAG_TYPES and exclusion comment (to be updated)

```python
# Source: xeter/scripts/calibrate.py lines 46–52
FLAG_TYPES = [
    "wrong_tool",
    "no_tool",
    "excessive_tool",
    "parsing_error",
    "response_anomaly",
    # "wrong_tool_args",  <- ADD THIS after Phase 7 rewrite
]
```

### Verified: Fixture wrong_tool_args distribution

All 10 `wrong_tool_args` spans: `tool_output = "Email delivered"`, `tool_name = "send_email"`. The anomaly is that the prompt specifies one recipient/subject and the actual arguments contain a completely different recipient/subject — a semantic mismatch the hybrid scorer must catch.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Embed raw JSON `tool_arguments` string | Embed flattened argument values only | Phase 7 | Removes JSON-key noise; cosine signal becomes meaningful |
| `low_confidence: True` in flag detail | No `low_confidence` key | Phase 7 | Flag is trustworthy; can be calibrated normally |
| Single cosine similarity for all checks | Hybrid 50/50 cosine + BOW | Phase 7 | BOW catches lexical overlap that cosine misses (shared keywords) |
| `wrong_tool_args` excluded from calibration | `wrong_tool_args` included in calibration | Phase 7 | Per-method P/R tracking now possible |
| Global `calibrate.py` run only | Per-method `--flag-type` mode | Phase 7 | Faster iteration; required for Phase-by-phase v1.1 workflow |

**Deprecated after Phase 7:**
- `low_confidence: True` in wrong_args detail: removed entirely
- The exclusion NOTE comment in `calibrate.py` stdout: replaced by normal calibration output

---

## Open Questions

1. **Should `_flatten_arg_values` handle nested dicts/lists in arguments?**
   - What we know: All 10 fixture wrong_tool_args spans have flat dict arguments (one level deep). No nested structure observed.
   - What's unclear: Production spans may have nested structures (e.g., `{"filters": {"city": "NYC", "age": 30}}`).
   - Recommendation: Implement flat-only for Phase 7 (`.values()` on top-level dict). Add a comment noting the limitation. Recursive flattening can be added in a follow-up without changing the calling code.

2. **Where exactly should `bow_score` and `hybrid_score` live — `base.py` or a new `scoring.py`?**
   - What we know: `base.py` is already imported by all analyzers. Adding two pure functions there has no coupling downside.
   - What's unclear: If `scoring.py` is cleaner as the project grows to 4+ analyzers.
   - Recommendation: Use `base.py` for Phase 7. This is the simplest option; refactor to `scoring.py` only if base.py becomes crowded in a later phase.

3. **Should the `--flag-type` argument accept comma-separated values (e.g., `--flag-type wrong_tool_args,no_tool`)?**
   - What we know: The roadmap shows single-method use only. CAL-02 says "calibrate a single flag_type in isolation."
   - Recommendation: Single value only. Comma-separated is overengineering for a solo-developer calibration tool.

---

## Validation Architecture

> `workflow.nyquist_validation` is not present in `.planning/config.json` — this section is skipped per research instructions.

---

## Sources

### Primary (HIGH confidence)

- Direct source inspection: `xeter/services/worker/tool_call_analyzer.py` — current `_check_wrong_args` implementation (lines 180–207)
- Direct source inspection: `xeter/services/worker/base.py` — `BaseAnalyzer`, `Flag`, `SpanData`, `compare()` (entire file)
- Direct source inspection: `xeter/scripts/calibrate.py` — current hill-climb loop, `FLAG_TYPES`, `DEFAULT_THRESHOLDS` (entire file)
- Direct source inspection: `xeter/tests/worker/test_tool_call_analyzer.py` — existing 16 tests including `test_wrong_args_flag_has_low_confidence` (test 7)
- Direct fixture inspection: `fixtures/labelled_spans.jsonl` — 210 spans; 10 `wrong_tool_args` all with `tool_output = "Email delivered"`
- Direct fixture inspection: `fixtures/calibrated_thresholds.json` — current calibrated values; `wrong_tool_args` at 0.4 default (excluded from sweep)
- Live test run: `pytest xeter/tests/worker/test_tool_call_analyzer.py` — 16 passed as baseline confirmation

### Secondary (MEDIUM confidence)

- Manual execution of `_flatten_arg_values` and `_should_skip_embedding` logic on representative fixture data — confirmed correct behavior on all 10 wrong_tool_args spans and edge cases (all-numeric, empty)
- Manual execution of BOW Jaccard function on fixture prompt/value pairs — confirmed discriminating scores (0.0 for wrong pairs, 0.333 for correct pairs)
- Manual test of error-pattern regex list on representative tool_output strings — confirmed no false positives on "Email delivered" or "Success"

### Tertiary (LOW confidence)

- None. All findings are grounded in direct codebase inspection and executable tests.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all stdlib or already installed
- Architecture patterns: HIGH — derived from direct code reading and manual execution
- Pitfalls: HIGH — Pitfall 2 (test_7) and Pitfall 3 (fixture gap) confirmed by inspection; Pitfall 4 is standard Python argparse behavior
- Fixture analysis: HIGH — all 10 wrong_tool_args spans inspected

**Research date:** 2026-04-06
**Valid until:** 2026-05-06 (stable domain — no external dependencies changing)

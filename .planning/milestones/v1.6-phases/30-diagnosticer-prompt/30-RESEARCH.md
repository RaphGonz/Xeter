# Phase 30: Diagnosticer Prompt — Research

**Researched:** 2026-05-30
**Domain:** LLM prompt engineering, Python file I/O, template substitution
**Confidence:** HIGH

---

## Summary

Phase 30 is a focused refactor with two tightly coupled deliverables: (1) extract the inline prompt string from `context_assembly.py:_format_context()` into a dedicated `prompt.md` file, and (2) rewrite that prompt with a structured system message, chain-of-thought scaffold, explicit four-verdict decision criteria, and severity calibration guidance.

The current prompt is a Python f-string inside `_format_context()`. It serves as the *user message* sent to all three LLM providers (Anthropic, OpenAI, Ollama). None of the providers use a separate `system` parameter — the entire message, including role framing, goes into the user content string. This means the rewritten `prompt.md` must embed the system message section as literal text within the user message, not as a provider-level `system` param (unless providers are updated, which is not scoped here).

The implementation is straightforward: read `prompt.md` once at import time into a module-level constant, then use Python string `.format()` or similar substitution in `_format_context()` to inject span data at call time. The planner needs to decide whether to use `str.format_map()` with `{variable}` placeholders or `str.replace()` calls with sentinel tokens — both are valid, but `format_map()` is idiomatic and requires no extra parsing logic.

**Primary recommendation:** Read `prompt.md` at module import time using `pathlib.Path(__file__).parent / "prompt.md"`. Use `str.format_map()` with named placeholders matching current f-string variables. Add a test verifying the file is read and substitution produces the correct variable expansion.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DIAG-01 | Inline prompt string extracted from `context_assembly.py:_format_context()` into `xeter/services/diagnosticer/prompt.md`; `_format_context()` reads the file at import time and substitutes span data into it | See "Architecture Patterns" — import-time file read with `pathlib`, substitution via `format_map` |
| DIAG-02 | Extracted prompt rewritten with: (a) system message section, (b) CoT scaffold through each flag before verdict, (c) explicit decision criteria for four verdicts, (d) severity calibration guidance | See "Prompt Content Requirements" section — all four sub-requirements mapped |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Prompt file storage | API / Backend (diagnosticer service) | — | `prompt.md` lives adjacent to `context_assembly.py`; it is a service artifact, not a shared resource |
| Import-time file read | API / Backend (context_assembly module) | — | Module-level read runs once at import, not per-request |
| Span data substitution | API / Backend (`_format_context()`) | — | Only this function has access to span, flags, prompt_text, response_text |
| LLM message assembly | API / Backend (providers) | — | Providers receive the assembled string; they do not own the prompt template |
| Prompt content (CoT, verdicts) | Human authorship task | — | Content quality is a writing task, not a code task; it belongs in the plan as a discrete deliverable |

---

## Standard Stack

No new external packages are required. Everything needed is in the Python standard library.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pathlib` (stdlib) | 3.12 | Locate `prompt.md` relative to source file | `Path(__file__).parent` is the canonical cross-platform way to find co-located data files |
| `str.format_map()` (stdlib) | 3.12 | Substitute span variables into template | Cleaner than `%` formatting; safer than `format()` with positional args; handles `{key}` placeholders natively |

### No New Dependencies
This phase installs zero packages. The `pyproject.toml` dependency list is unchanged.

**Installation:** None required.

---

## Package Legitimacy Audit

No packages are installed in this phase. This section is not applicable.

---

## Architecture Patterns

### System Architecture Diagram

```
prompt.md (template file, co-located with context_assembly.py)
       |
       | read once at module import
       v
_PROMPT_TEMPLATE (module-level str constant in context_assembly.py)
       |
       | .format_map({span_fields, flags_section, prompt_text, response_text})
       v
_format_context(span, flags, prompt_text, response_text) -> str
       |
       | returns assembled context string
       v
assemble_context() -> (context_string, trace_id)
       |
       | passes context_string to provider
       v
AnthropicProvider / OpenAIProvider / OllamaProvider
       |
       | messages=[{"role": "user", "content": context_string}]
       v
LLM API  ->  DiagnosisResult (verdict, severity, affected_field, fix)
```

### Recommended Project Structure
```
xeter/services/diagnosticer/
├── prompt.md              # NEW: extracted + rewritten prompt template
├── context_assembly.py    # MODIFIED: reads prompt.md at import, uses format_map
├── main.py                # unchanged
├── providers/
│   ├── base.py            # unchanged
│   ├── anthropic.py       # unchanged
│   ├── openai.py          # unchanged
│   └── ollama.py          # unchanged
```

### Pattern 1: Import-Time File Read
**What:** Read `prompt.md` once when the module is first imported, store as a module constant. Never re-read on each request.
**When to use:** Any static asset co-located with a Python source file that is read frequently but never changes at runtime.

```python
# Source: Python stdlib pathlib docs [CITED: docs.python.org/3/library/pathlib.html]
from pathlib import Path

_PROMPT_TEMPLATE: str = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
```

**Why `Path(__file__).parent`:** This is immune to working-directory changes (e.g., when pytest runs from a different cwd). It always resolves relative to the source file's location. [CITED: Python docs — `__file__` attribute]

**Failure mode:** If `prompt.md` is absent (e.g., after a bad deploy), `read_text()` raises `FileNotFoundError` at import time. This is the correct failure mode — the service refuses to start rather than silently using a missing prompt at request time.

### Pattern 2: Template Substitution with `format_map`
**What:** Replace the f-string body with a template string using `{variable}` placeholders, then call `.format_map()` at call time.
**When to use:** When the template is stored in a file and values are injected at runtime.

```python
# Source: Python stdlib str.format_map docs [CITED: docs.python.org/3/library/stdtypes.html#str.format_map]
def _format_context(
    span: dict[str, Any],
    flags: list[Flag],
    prompt_text: str,
    response_text: str,
) -> str:
    flag_lines = []
    for f in flags:
        detail_str = json.dumps(f.detail) if f.detail else "none"
        flag_lines.append(
            f"  - type={f.flag_type}, score={f.score:.4f}, detail={detail_str}"
        )
    flags_section = "\n".join(flag_lines) if flag_lines else "  (no flags)"

    return _PROMPT_TEMPLATE.format_map({
        "span_id": span.get("span_id", "unknown"),
        "trace_id": span.get("trace_id", "unknown"),
        "agent_name": span.get("agent_name", "unknown"),
        "agent_model": span.get("agent_model", "unknown"),
        "tool_name": span.get("tool_name", "unknown"),
        "tool_description": span.get("tool_description", "unknown"),
        "tool_arguments": span.get("tool_arguments", "unknown"),
        "tool_output": span.get("tool_output", "unknown"),
        "time_begin": span.get("time_begin", "unknown"),
        "prompt_text": prompt_text,
        "response_text": response_text,
        "flags_section": flags_section,
    })
```

**Caution — curly brace escaping:** The prompt template is a Markdown file. Any literal `{` or `}` character in the prompt text (e.g., in JSON examples) must be escaped as `{{` and `}}` in the `.md` file when using `format_map`. This is the primary pitfall for this approach.

**Alternative — sentinel replacement:** Use `prompt.md` with `{{SPAN_ID}}` or `<!-- SPAN_ID -->` style sentinels and replace them with `str.replace()`. This avoids curly-brace escaping entirely. Tradeoff: more verbose substitution code, but the template is cleaner for prose-heavy content that might naturally contain `{}`.

### Anti-Patterns to Avoid
- **Re-reading `prompt.md` on every `_format_context()` call:** Adds unnecessary I/O per LLM request. Read once at module import.
- **Storing prompt in a subdirectory without updating the path:** The file must be at `xeter/services/diagnosticer/prompt.md`, co-located with `context_assembly.py`.
- **Using `format()` with positional args:** The template has many variables; named keys via `format_map` are readable and order-independent.
- **Adding a system message as a provider-level parameter:** The current provider interface passes a single `context` string. Adding a `system` parameter to all three providers is out of scope for this phase. The system message section belongs as literal text inside `prompt.md`, rendered as part of the user message.

---

## Prompt Content Requirements

This section documents what DIAG-02 requires inside `prompt.md`, based on the requirements and the existing system.

### (a) System Message Section
Frame the diagnosticer's role explicitly. The existing prompt says "You are diagnosing a failing AI agent tool call." — this must be expanded into a section that:
- States the task is root-cause analysis (not general Q&A, not summarization)
- Names the four possible verdicts and their meanings (already defined in `_DIAGNOSIS_TOOL` in `anthropic.py`)
- Instructs the model to call `record_diagnosis` with its conclusion

### (b) Chain-of-Thought Scaffold
Walk through each flag before reaching a verdict. The scaffold should instruct the model to:
1. List each flag type and score from the anomaly flags section
2. Interpret what each flag indicates about the failure mode
3. Consider whether the evidence points to model, architecture, prompt, or unknown
4. State its verdict with justification

### (c) Explicit Verdict Decision Criteria (all four verdicts)
The current tool description in `anthropic.py` provides terse one-line descriptions. The prompt template can expand these into decision guidance:
- `model`: LLM capability/knowledge failure — e.g., wrong_args with high score, model selects wrong tool despite clear schema
- `architecture`: System design / tool schema failure — e.g., ambiguous tool_description, tool_arguments schema issues
- `prompt`: Instruction clarity / context failure — e.g., missing context in prompt_text, ambiguous user instruction
- `unknown`: Insufficient signal — no flag has a high-confidence score, or flags are contradictory

### (d) Severity Calibration Guidance
The prompt should guide the model on how to calibrate severity:
- `high`: The failure prevents the agent from completing its task entirely
- `medium`: The failure degrades output quality but the task partially completes
- `low`: A minor issue that may correct itself or has minimal user impact

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Template variable substitution | Custom regex-based template engine | `str.format_map()` or sentinel `str.replace()` | stdlib handles it; custom parsers introduce bugs |
| File loading with caching | Custom caching layer | Module-level constant (import-time read) | Python's import system already caches modules; one read per process lifetime |
| Prompt content versioning | Git-tracked version in filename | Standard git history on `prompt.md` | The file is in source control; git provides history |

---

## Common Pitfalls

### Pitfall 1: Curly Brace Collision in `format_map`
**What goes wrong:** The prompt template is Markdown prose. If it contains any literal `{` or `}` (e.g., `{"type": "object"}`), `str.format_map()` raises `KeyError` or `ValueError` trying to interpret them as placeholders.
**Why it happens:** `str.format_map()` treats every `{...}` as a substitution placeholder, regardless of context.
**How to avoid:** Either (a) escape all literal braces as `{{` and `}}` in the template, or (b) use sentinel-style replacement instead of `format_map`. If the prompt content uses JSON examples, sentinel replacement is cleaner.
**Warning signs:** `KeyError` exception during `_format_context()` calls in tests; the key name in the error will be the content inside an unescaped `{}`.

### Pitfall 2: `FileNotFoundError` at Import in Tests
**What goes wrong:** Tests that import `context_assembly` will fail with `FileNotFoundError` if `prompt.md` doesn't exist yet (e.g., during TDD when writing the reader before the file).
**Why it happens:** Module-level `read_text()` runs at import time, before any test setup runs.
**How to avoid:** Create the `prompt.md` stub in the same plan that adds the import-time read. The file and the reader must be created in the same task (or the file first, then the reader).
**Warning signs:** `FileNotFoundError: [Errno 2] No such file or directory: '.../prompt.md'` during pytest collection.

### Pitfall 3: SPDX Header Missing from `prompt.md`
**What goes wrong:** Phase 29 added SPDX headers to all Python source files. `prompt.md` is a new non-Python file — it does not need an SPDX header, but the plan should not accidentally add one to a Markdown file where it would appear as visible text.
**Why it happens:** Overzealous application of the Phase 29 SPDX convention.
**How to avoid:** SPDX headers go in `.py` files only. `prompt.md` is a template file, not source code — no header needed. `context_assembly.py` already has its SPDX header and should not need a new one added.
**Warning signs:** The rendered prompt starts with `# SPDX-License-Identifier:` — this would be sent to the LLM as part of the user message.

### Pitfall 4: Losing the `_format_context` Function Signature
**What goes wrong:** Refactoring `_format_context()` to change its signature breaks `assemble_context()` which calls it at line 208 of `context_assembly.py`.
**Why it happens:** The function body is replaced but the caller is not updated.
**How to avoid:** Keep the signature `_format_context(span, flags, prompt_text, response_text) -> str` exactly as-is. Only the function body changes.
**Warning signs:** `TypeError` in `assemble_context()`.

### Pitfall 5: Template Variables Don't Cover All Span Fields
**What goes wrong:** The template uses `{tool_output}` but the substitution dict in `_format_context()` doesn't include it — or vice versa.
**Why it happens:** The prompt template and the substitution dict are maintained separately; they can drift.
**How to avoid:** After writing `prompt.md`, verify that every `{variable}` placeholder in the file has a corresponding key in the `format_map` dict. A test that calls `_format_context()` with a stub span will catch `KeyError` immediately.
**Warning signs:** `KeyError: 'tool_output'` (or similar) during `_format_context()`.

---

## Code Examples

### Module-Level Read (the canonical pattern)
```python
# Source: Python stdlib [CITED: docs.python.org/3/library/pathlib.html]
from pathlib import Path

_PROMPT_TEMPLATE: str = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
```

### Substitution in `_format_context()`
```python
# Source: Python stdlib [CITED: docs.python.org/3/library/stdtypes.html#str.format_map]
def _format_context(
    span: dict[str, Any],
    flags: list[Flag],
    prompt_text: str,
    response_text: str,
) -> str:
    flag_lines = []
    for f in flags:
        detail_str = json.dumps(f.detail) if f.detail else "none"
        flag_lines.append(
            f"  - type={f.flag_type}, score={f.score:.4f}, detail={detail_str}"
        )
    flags_section = "\n".join(flag_lines) if flag_lines else "  (no flags)"

    return _PROMPT_TEMPLATE.format_map({
        "span_id": span.get("span_id", "unknown"),
        "trace_id": span.get("trace_id", "unknown"),
        "agent_name": span.get("agent_name", "unknown"),
        "agent_model": span.get("agent_model", "unknown"),
        "tool_name": span.get("tool_name", "unknown"),
        "tool_description": span.get("tool_description", "unknown"),
        "tool_arguments": span.get("tool_arguments", "unknown"),
        "tool_output": span.get("tool_output", "unknown"),
        "time_begin": span.get("time_begin", "unknown"),
        "prompt_text": prompt_text,
        "response_text": response_text,
        "flags_section": flags_section,
    })
```

### Prompt Template Structure (skeleton for `prompt.md`)
```markdown
You are the Xeter Diagnosticer. Your role is root-cause analysis of failing AI agent
tool calls — not general Q&A. You will receive span data, the agent's prompt and
response text, and a list of anomaly flags scored by the Xeter analyser.

Your task: call `record_diagnosis` with the single most likely root cause.

## Verdict Decision Criteria

Choose the verdict that best fits the evidence:

- **model**: The LLM itself failed — wrong tool selected despite a clear schema,
  malformed arguments that a capable model should not produce, or reasoning that
  contradicts the available context. High `wrong_tool`, `wrong_args`, or
  `wrong_tool_called` flag scores are strong signals.

- **architecture**: The system design failed — ambiguous tool description, missing
  required tool, overly complex argument schema, or structural issues in the tool
  definition. High `missing_tool`, `ambiguous_tool_description`, or schema-related
  flags are strong signals.

- **prompt**: The instruction context failed — the agent's system prompt lacked
  necessary context, gave contradictory instructions, or failed to guide the model
  toward the correct tool. High `context_missing`, `instruction_conflict`, or
  `no_tool_used` flags are strong signals.

- **unknown**: Insufficient signal — no flag has a high-confidence score, the flags
  are contradictory, or the failure pattern does not map clearly to any category.
  Use this when you cannot confidently assign blame.

## Severity Calibration

- **high**: The failure prevents the agent from completing its task entirely.
- **medium**: The failure degrades output quality but the task partially completes.
- **low**: A minor issue with minimal user impact.

## Span Information
- span_id: {span_id}
- trace_id: {trace_id}
- agent_name: {agent_name}
- agent_model: {agent_model}
- tool_name: {tool_name}
- tool_description: {tool_description}
- tool_arguments: {tool_arguments}
- tool_output: {tool_output}
- time_begin: {time_begin}

## Prompt Text (full content)
{prompt_text}

## Response Text (full content)
{response_text}

## Anomaly Flags (all flags for this span, with scores)
{flags_section}

## Reasoning Steps

Before calling `record_diagnosis`, work through each flag above:
1. What does this flag type indicate about the failure mode?
2. Is the score high enough to be diagnostic (> 0.7 is typically significant)?
3. Do multiple flags point to the same root cause?
4. Which verdict best explains the combination of evidence?

Then call `record_diagnosis` with your conclusion.
```

**Note on curly brace escaping:** The skeleton above uses `{variable}` style. If the final prompt prose needs literal curly braces (e.g., JSON examples), escape them as `{{` / `}}`, or switch to sentinel-style replacement.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline f-string prompt in Python source | Dedicated `prompt.md` template file | Phase 30 | Prompt is human-editable without touching Python; visible in code review as a semantic diff |
| Minimal role framing ("You are diagnosing...") | Structured system message + CoT scaffold + decision criteria | Phase 30 | LLM has explicit reasoning guidance, reducing ambiguous `unknown` verdicts |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The system message should remain part of the user message string, not moved to a `system` parameter on the provider API calls | Architecture Patterns (anti-patterns) | If the LLM performs significantly better with a native `system` parameter, providers would need updating — but that is a separate concern from the prompt extraction |
| A2 | `str.format_map()` is the right substitution mechanism (vs. sentinel replacement) | Architecture Patterns | If the prompt content requires many literal `{}` characters, sentinel replacement would be less error-prone |

---

## Open Questions (RESOLVED)

1. **Curly brace escaping vs. sentinel replacement**
   - What we know: `format_map` requires `{{`/`}}` escaping for literal braces; sentinel replacement avoids this
   - What's unclear: How much prose with literal braces will the rewritten prompt contain?
   - Recommendation: Use `format_map` — the prompt is primarily instructional prose, not JSON examples. If escaping becomes burdensome, switch to sentinel replacement in the same task.

2. **Number of plans**
   - What we know: Two requirements (DIAG-01 = code change, DIAG-02 = content authorship)
   - What's unclear: Whether to combine both into one plan or keep them separate
   - Recommendation: Two plans. Plan 01: Write `prompt.md` stub + update `context_assembly.py` to read it (DIAG-01 satisfiable independently). Plan 02: Rewrite `prompt.md` content with system message, CoT, verdict criteria, severity guidance (DIAG-02). This ordering means the code change is verified before the content quality is judged.

---

## Environment Availability

Step 2.6: SKIPPED — this phase is a code/config-only change. No external tools, services, databases, or CLIs are required beyond the existing Python environment.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (with pytest-asyncio 0.24.0) |
| Config file | `xeter/pyproject.toml` — `[tool.pytest.ini_options]` |
| Quick run command | `cd xeter && python -m pytest tests/diagnosticer/ -x -q` |
| Full suite command | `cd xeter && python -m pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DIAG-01 | `_format_context()` substitutes span fields from `prompt.md` template | unit | `cd xeter && python -m pytest tests/diagnosticer/test_context_assembly.py -x -q` | No — Wave 0 gap |
| DIAG-01 | `FileNotFoundError` if `prompt.md` is absent | unit | included in same file | No — Wave 0 gap |
| DIAG-02 | `prompt.md` contains required sections (system message, CoT, all four verdicts, severity guidance) | smoke (file content check) | included in same file | No — Wave 0 gap |
| DIAG-01 | Existing `/diagnose` endpoint tests still pass (no regression) | regression | `cd xeter && python -m pytest tests/diagnosticer/test_diagnose_endpoint.py -x -q` | Yes (`test_diagnose_endpoint.py`) |

### Sampling Rate
- **Per task commit:** `cd xeter && python -m pytest tests/diagnosticer/ -x -q`
- **Per wave merge:** `cd xeter && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `xeter/tests/diagnosticer/test_context_assembly.py` — covers DIAG-01 (import-time read, substitution, FileNotFoundError)
- [ ] Content assertions for DIAG-02 can live in the same file as a simple string-presence check against the rendered output

*(Existing `test_diagnose_endpoint.py` already covers the endpoint and mocks `assemble_context` — it does not need changes for DIAG-01/DIAG-02, but must remain green as a regression gate.)*

---

## Security Domain

This phase makes no changes to authentication, session management, access control, cryptography, or external input handling. The prompt file is a read-only template loaded at import time from a trusted source path. No ASVS categories apply.

Security note: The `prompt.md` content is sent verbatim (with span data interpolated) to external LLM APIs. The span data fields (tool_arguments, prompt_text, response_text) can contain arbitrary user-agent content — this is unchanged behavior from the current inline f-string. No new injection surface is introduced by the extraction.

---

## Sources

### Primary (HIGH confidence)
- Python stdlib `pathlib.Path` — `Path(__file__).parent / "file"` pattern for co-located assets [CITED: docs.python.org/3/library/pathlib.html]
- Python stdlib `str.format_map()` — named placeholder substitution [CITED: docs.python.org/3/library/stdtypes.html#str.format_map]
- `xeter/services/diagnosticer/context_assembly.py` — current prompt location and `_format_context()` signature [VERIFIED: codebase]
- `xeter/services/diagnosticer/providers/anthropic.py` — `_DIAGNOSIS_TOOL` verdict definitions [VERIFIED: codebase]
- `xeter/services/diagnosticer/providers/base.py` — `DiagnosisResult` fields and `LLMProvider.diagnose()` contract [VERIFIED: codebase]
- `xeter/tests/diagnosticer/test_diagnose_endpoint.py` — existing test coverage and mock patterns [VERIFIED: codebase]
- `xeter/pyproject.toml` — pytest config and dependency versions [VERIFIED: codebase]
- `.planning/REQUIREMENTS.md` — DIAG-01, DIAG-02 specification [VERIFIED: codebase]

### Secondary (MEDIUM confidence)
- None for this phase — all relevant information comes from primary codebase sources.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib only, no new packages
- Architecture: HIGH — pattern is directly derived from reading current source; `Path(__file__).parent` is well-established Python idiom
- Prompt content requirements: HIGH — verbatim from REQUIREMENTS.md and existing `_DIAGNOSIS_TOOL` definitions
- Pitfalls: HIGH — curly brace collision and import-time FileNotFoundError are well-known consequences of `format_map` + file-read patterns

**Research date:** 2026-05-30
**Valid until:** Stable — stdlib patterns do not change; valid indefinitely

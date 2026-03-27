# SPRINT.md — Foundation Sprint Journal

**Sprint date:** 2026-03-22
**Completed:** yes

---

## Step 1: The Basics

### Target Customer

**Options considered:**
- A) Solo developers and small engineering teams (2-5 people) building agentic AI systems with local or open-source models
- B) Engineers building AI agent workflows who prefer open-source/local models over closed APIs (any team size)
- C) Small engineering teams shipping agentic products, currently underserved by tooling that assumes OpenAI/Anthropic API access

**Chosen:** B) Engineers building AI agent workflows who prefer open-source/local models over closed APIs (any team size)

**Rationale:** User wanted to keep the segment broad across team sizes rather than limiting to solo/small teams, since the problem applies regardless of team size.

### Core Problem / Pain Point

**Options considered:**
- A) When agentic tool-calling fails, developers can't diagnose whether the root cause is the model, the architecture, or the prompt — forcing slow, expensive trial-and-error debugging
- B) Developers building agentic pipelines lack dedicated diagnostic tooling for tool-call failures, leaving them blind to whether they need a better model, a different architecture, or better prompts
- C) Debugging agentic tool-calling is a black box — no existing tooling isolates model capability vs. architecture design vs. prompt quality as the failure source

**Chosen:** A) When agentic tool-calling fails, developers can't diagnose whether the root cause is the model, the architecture, or the prompt — forcing slow, expensive trial-and-error debugging

**Rationale:** Most concrete framing — centers the pain on the diagnostic blindness and its cost (slow, expensive trial-and-error).

**Client-problem fit validation:** Web search confirmed this is a well-documented pain. Multiple 2025-2026 reports cite brittle tool connectors and lack of diagnostic tooling as top reasons agent pilots fail. The Composio AI Agent Report describes integration failures (not LLM failures) as the primary cause of agent pilot failure. Specialized debugging platforms are emerging as a category (5 Best Agent Debugging Platforms in 2026), confirming market recognition of the problem.

### Founder Advantages

**Capacity** (what you can build): Built a multi-tool agent from scratch; deep technical knowledge of AI, RAG, and LLMs; software engineer by trade.

**Insight** (what you've seen before others): Lived through a multi-layer tool-calling debugging spiral — silent model failure where the model couldn't call tools but gave no indication, a supervisor layer that couldn't detect intent even with few-shot prompting, and resolution only by upgrading to a costly larger model. Experienced the exact diagnostic blindness this product would solve.

**Motivation** (why you're doing this): Building a zero-human company running on local infrastructure — needs this tooling personally to track and resolve tool-calling failures at scale.

### Competitors

| Competitor | Type | Main Adversary? | Why Flagged |
|------------|------|-----------------|-------------|
| Langfuse | Direct | Yes | Open-source, self-hostable, framework-agnostic — the default free tool most developers in this segment will reach for first |
| LangSmith | Direct | No | Market leader but closed-source and cloud-dependent — less relevant for local model users |
| Arize Phoenix | Direct | No | Fully open-source and local-first, but general-purpose observability without root-cause diagnosis |
| HoneyHive | Direct | No | Has Tool Use Accuracy evaluator but closed-source with pricing gap |
| Print/Log Debugging | Workaround | No | Status quo — zero dependencies but extremely slow for multi-step agent workflows |

**Research summary:** All five competitors provide some form of trace visibility for agent workflows, but none explicitly diagnose the root cause of tool-calling failures (model vs. architecture vs. prompt). Langfuse and Arize Phoenix are the strongest fits for the open-source/local model segment. HoneyHive comes closest with its Tool Use Accuracy evaluator but it scores correctness, not causality. Print/log debugging remains the dominant practice despite being the slowest approach.

---

## Step 2: Differentiation

### Bipolar Axis Ratings (Dream Company)

| Axis | Our Position | Notes |
|------|-------------|-------|
| Slow <-> Fast | 0 | |
| Hard <-> Easy | +4 | |
| Expensive <-> Free | -1 | Want to have revenue |
| Complex <-> Simple | +4 | |
| Dumb <-> Smart | +2 | |
| Siloed <-> Integrated | +5 | |
| Manual <-> Automatic | -1 | |
| Narrow <-> Broad | -5 | Address this specific problem first |
| Generic traces <-> Root-cause isolation | +5 | Custom axis — no current tool isolates which layer caused a tool-call failure |
| Cloud-API-first <-> Local-model-first | 0 | Custom axis — want it to work for everyone |

### Chosen Differentiating Axes

**Axis 1 (X):** Generic traces <-> Root-cause isolation — No competitor explicitly diagnoses why a tool call failed (model, architecture, or prompt). This is the exact gap the product fills. User noted: none of the competitors explain the root cause, they only show that something happened.

**Axis 2 (Y):** Siloed <-> Integrated — Covers both the API vs. local model divide and the founder's insight about needing tooling that works across any stack. User chose this to reflect that the tool should work everywhere.

### Conflict Check

Initial axis selection (Root-cause isolation + Integrated) produced conflicts: Langfuse, Arize Phoenix, and HoneyHive landed in the top-right. After user challenged the scoring — pointing out that none of these tools actually explain why a tool call failed, they only show traces — scores were corrected downward on the Root-cause axis. Rescored: Langfuse X:-2, LangSmith X:-1, Arize Phoenix X:-1, HoneyHive X:0. No conflicts after rescoring. User's challenge was valid: showing a trace is not the same as diagnosing root cause.

### Mini-Manifesto

**Differentiator 1:** Trying to explain why something happens is better than pointing fingers at a problem.

**Differentiator 2:** Adaptation to user is key.

**Safeguard:** Must be as simple as possible to integrate.

---

## Step 3: Approaches

### Approaches Evaluated

#### Approach 1 — A1: Live SDK with LLM Supervisor (User's Initial Idea)

**Description:** A lightweight SDK that hooks into agent runtime, intercepts tool calls as they happen, and runs a secondary LLM pass to compare the tool call against the prompt context and tool schema. It flags discrepancies in real-time with human-readable suggestions, and logs everything for post-hoc review. Starts with live interception, traces come for free as a byproduct.

#### Approach 2 — A2: Trace Analyzer (AI-Generated)

**Description:** A post-hoc tool that ingests agent traces (from any source — log files, OpenTelemetry, custom formats) and runs diagnostic analysis on tool-call failures. No runtime dependency — developers point it at a trace and get a root-cause report: was it the model, the prompt, or the architecture? Simpler to integrate since it doesn't touch the agent's execution path.

#### Approach 3 — A3: Schema Validator + Vector Matcher (AI-Generated, refined by user)

**Description:** A rule-based SDK that validates tool calls against schemas at runtime (argument types, missing fields, hallucinated function names) AND uses vector similarity to check whether the right tool was called given the prompt context — comparing the user's intent against tool names/descriptions without any LLM inference. Suggests fixes based on common failure patterns. Zero inference cost. User added the vector matching component to check if the correct tool was called based on intent.

#### Approach 4 — A4: Hybrid Layered Debugger (AI-Generated)

**Description:** Combines A3's zero-cost checks as a first pass (schema validation + vector matching) with A1's LLM supervisor as a second pass only when heuristics can't determine the root cause. Developers get instant feedback on obvious failures and deeper diagnostic analysis on ambiguous ones. Cost-efficient — LLM inference only fires when needed.

### 4-Matrix Evaluation

| Matrix | A1 | A2 | A3 | A4 |
|--------|----|----|----|----|
| Customer Vision (ease x solves perfectly) | top-right (easy, solves well) | top-left (friction, thorough) | bottom-right (simplest, partial) | top-right (easy, closest to perfect) |
| Money Vision (recurring revenue x # clients) | bottom-right (recurring, fewer) | bottom-left (one-time risk, few) | top-left (many customers, less recurring) | top-right (many, recurring with upsell) |
| Pragmatic Vision (ease to build x speed to build) | bottom-right (moderate complexity, moderate speed) | top-left (fast but separate from runtime) | top-right (straightforward, fast) | bottom-left (most to build, slowest) |
| Growth Vision (adaptability x acquisition over time) | bottom-right (adaptable via LLM, fewer users) | bottom-left (utility, limited growth) | top-left (many users, ceiling on capability) | top-right (most adaptable, natural expansion) |

**Recommended approach:** A4 (Hybrid Layered Debugger) — strongest global pattern across all 4 matrices, top-right in Customer Vision, Money Vision, and Growth Vision. Only weakness is Pragmatic Vision (hardest/slowest to build), mitigated by shipping A3 first.

**Backup approach:** A3 (Schema Validator + Vector Matcher) — strong in Pragmatic and Growth, weaker in Customer Vision since it can't handle nuanced failures. Notably A3 is the natural first milestone on the way to A4.

**Chosen approach:** A4 (Hybrid Layered Debugger). User's rationale: "It will cover the bug and explain well, above a fixed and predictable algorithmic comparison of what's failed. A3 is the second approach but the first I'll actually build, even though it doesn't solve the problem at all: we need to know the why of the why and not simply why."

---

## Step 4: Final Hypothesis

**Full hypothesis:** If we help engineers building AI agent workflows with open-source/local models (any team size) solve the inability to diagnose whether tool-calling failures come from the model, the architecture, or the prompt with a hybrid layered debugger that catches obvious tool-call breakage through schema validation and vector matching, then uses an LLM supervisor to explain why the AI made the wrong decision, they will choose us over Langfuse because we explain the reasoning behind failures rather than just showing that something broke and we integrate into any stack with minimal friction.

**See HYPOTHESIS.md for the complete testable form.**

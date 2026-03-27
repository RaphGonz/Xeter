# HYPOTHESIS.md

## The Hypothesis

> If we help **engineers building AI agent workflows with open-source/local models (any team size)**
> solve **the inability to diagnose whether tool-calling failures come from the model, the architecture, or the prompt — forcing slow, expensive trial-and-error debugging**
> with **a hybrid layered debugger that catches obvious tool-call breakage through schema validation and vector matching, then uses an LLM supervisor to explain why the AI made the wrong decision**,
> they will choose us over **Langfuse**
> because we **explain the reasoning behind failures rather than just showing that something broke** and **we integrate into any stack with minimal friction**.

### Breakdown

| Variable | Value |
|----------|-------|
| X — Target customer | Engineers building AI agent workflows with open-source/local models (any team size) |
| Y — Problem | When agentic tool-calling fails, developers can't diagnose whether the root cause is the model, the architecture, or the prompt — forcing slow, expensive trial-and-error debugging |
| Z — Approach | Hybrid Layered Debugger — schema validation + vector matching as first pass, LLM supervisor for ambiguous cases to explain why the AI made the wrong decision |
| W — Main adversary | Langfuse |
| U — Differentiator 1 | Explain the reasoning behind failures rather than just showing that something broke |
| V — Differentiator 2 | Integrate into any stack with minimal friction |

## Testable Form

### Success Metric

10 engineers outside your network actively using the SDK in their agent projects within 8 weeks of public release.

### Falsification Condition

If 30+ developers are contacted/shown the tool and fewer than 3 integrate it into a project, the hypothesis is proven wrong.

### Main Risk

That developers find schema validation + vector matching "good enough" and never need the LLM supervisor layer — making the core differentiator (explaining why) unnecessary.

### Fastest Validation Test

Build the A3 layer (schema validation + vector matching), ship it to 5 developers building agents with local models, and ask: "Does this tell you enough, or do you still need to know why the AI made that decision?" If 4/5 say they need the why, the LLM layer is validated.

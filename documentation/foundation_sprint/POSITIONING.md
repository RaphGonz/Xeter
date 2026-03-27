# POSITIONING.md

## Differentiation Axes

**Axis 1 (horizontal):** Generic traces <-> Root-cause isolation — Measures whether a tool shows that something failed (left) or explains why the AI made the wrong decision at the model, architecture, or prompt level (right).

**Axis 2 (vertical):** Siloed <-> Integrated — Measures whether a tool locks you into a specific framework, vendor, or deployment model (bottom) or works across any stack, model provider, and infrastructure setup (top).

**Rationale:** These two axes were chosen because they represent the exact gap in the market: every existing tool shows traces of what happened, but none diagnose root cause. And the target segment (open-source/local model users) needs tooling that works everywhere, not just within one ecosystem. Together, these axes capture the founder's core insight — that developers need to know the why behind the why, and they need it regardless of their stack.

---

## 2x2 Matrix

```
              High Integrated
                        ^
    Langfuse            |      You
                        |  
    Arize Phoenix       |  
    HoneyHive           |
  ──────────────────────+──────────────────► High Root-cause
         LangSmith      |                   isolation
                        |
  Print/Log             |
                        |
              Low Integrated
```

### Competitor Positions

| Competitor | Axis 1 Score | Axis 2 Score | Quadrant | Rationale |
|------------|-------------|-------------|---------|-----------|
| Langfuse | -2 | +3 | top-left | Framework-agnostic and self-hostable (strong integration), but general-purpose traces — profile states "not specialized for diagnosing tool-calling failures specifically" |
| LangSmith | -1 | -1 | bottom-left | Visual trace trees but no diagnostic layer explaining why; siloed to LangChain ecosystem and closed-source cloud by default |
| Arize Phoenix | -1 | +3 | top-left | Agent Graph visualization speeds up inspection but doesn't isolate model vs. prompt vs. architecture; fully open-source and local-first |
| HoneyHive | 0 | +1 | top-left | Tool Use Accuracy evaluator scores whether a call was correct but doesn't explain why it failed; OpenTelemetry-based but closed-source |
| Print/Log Debugging | -4 | -2 | bottom-left | No structured diagnosis whatsoever; works anywhere but connects to nothing — developers manually correlate everything |

---

## Mini-Manifesto

**We explain why:**
Trying to explain why something happens is better than pointing fingers at a problem. When a tool call fails, we don't just show the trace — we tell the developer whether it was the model, the architecture, or the prompt, and why.

**We adapt to you:**
Adaptation to user is key. We work with any model provider, any framework, any deployment setup. Local models, cloud APIs, custom stacks — the debugger meets you where you are.

**We will never sacrifice simplicity of integration:**
Must be as simple as possible to integrate. We will never require complex setup, framework lock-in, or infrastructure changes to get value. If it takes more than a few lines of code to start debugging, we've failed.

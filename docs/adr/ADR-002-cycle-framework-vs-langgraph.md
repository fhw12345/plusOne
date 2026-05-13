# ADR-002: Custom cycle framework vs LangGraph / LangChain

## Status

Accepted (2026-05-13)

## Context

The product depends on a multi-step agent loop (Producer → Joiner → Controller,
looping until convergence). Several mature options exist:

- **LangGraph**: state-machine-based orchestration with checkpointing
- **LangChain Agents**: high-level agent abstractions
- **CrewAI**: role-based multi-agent
- **Pydantic AI**: lightweight LLM call layer (no orchestration)
- **Custom**: build the cycle / skill / multi-agent layer in-house

A senior reviewer specifically pushed back on building custom: "this is the
most dangerous item because it's the most fun … it's invisible to users and
it's the #1 schedule killer." That feedback is acknowledged.

## Decision

**Build a custom cycle / skill / multi-agent framework in-house**, on top of
**Pydantic AI** for LLM call mechanics.

Scope of "custom":
- Cycle main loop with rule-first / LLM-fallback Controller
- File-based Skill system with frontmatter (Anthropic Skills format)
- Tool registry with `is_concurrency_safe` self-reporting
- Multi-agent orchestration (Producer / Joiner / Controller as separate agent roles)
- Demo-mode plumbing (cached LLM provider) integrated at the framework level

Scope explicitly NOT custom:
- LLM call mechanics (Pydantic AI handles request/response/schema)
- HTTP / DB / queue (FastAPI + SQLAlchemy + asyncio)

## Alternatives considered

### LangGraph

- **Pros**: State machine + checkpointer is genuinely useful; community traction; visualization
- **Cons**: Abstractions tuned for LangChain's ecosystem; checkpointer is overkill for 60-90s tasks; ties us to LangChain release cadence; harder to tell "what the agent is actually doing"
- **Why rejected**: For a 60-90s task with in-process queue, checkpointer is overkill; we want full control over the Controller's rule-first decision logic

### LangChain Agents

- **Pros**: Off-the-shelf
- **Cons**: Over-abstracted; debugging tool calls is painful; reputation declining in 2026
- **Why rejected**: Net-negative ergonomics

### CrewAI

- **Pros**: Multi-agent first-class
- **Cons**: Sync-first, doesn't fit async backend
- **Why rejected**: Async incompatibility

### Pure Pydantic AI (no custom orchestration)

- **Pros**: Minimal abstraction
- **Cons**: We'd reinvent the wheel inline anyway for cycle / skill / multi-agent
- **Why rejected**: Skills + multi-agent need a real abstraction layer

## Consequences

### Positive

- Full control over Controller decision logic (rule-first → LLM fallback is critical)
- Skill system can match the team's existing internal `agent-framework-patterns.md` design
- Demo-mode integration is clean (provider-level swap, not framework-level hack)
- Resume / interview signal: shows real framework design, not framework consumption
- Easier to debug when things go wrong (no black box)

### Negative / Trade-offs

- **Real schedule cost**: estimated 2-3 weeks vs reusing LangGraph
- Risk of over-engineering — must keep framework scope tight (cycle + skill + tool only)
- Framework needs ≥10 skills to justify its existence (per reviewer note)
- No community-shared improvements (we own all bugs)

### Follow-ups

- [ ] Define framework scope contract: what's in vs out
- [ ] Implement minimal cycle loop first (~300 lines), then layer skills/tools
- [ ] Write a public technical post on the framework design (Phase γ)
- [ ] Re-evaluate in 3 months: is the framework paying for itself?

## References

- Internal patterns doc: `agent-framework-patterns.md`
- Internal patterns doc: `agent-platform-patterns.md`
- Reviewer feedback: see internal review notes

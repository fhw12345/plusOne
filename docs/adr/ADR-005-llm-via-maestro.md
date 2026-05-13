# ADR-005: LLM access via Agent Maestro gateway

## Status

Accepted (2026-05-13). Supersedes the LLM portion of ADR-001.

## Context

Plus One needs multi-LLM access:

- Some roles (Producer, Joiner) want Claude Opus 4.7 for deep reasoning + long context
- Other roles need cross-vendor diversity (e.g. the **disagreement detector**
  must not be the same model family as Producer / Joiner — otherwise our
  "Chinese sources say X vs English sources say Y" judgment is graded by a
  model that already shares the bias of the models that produced X and Y)
- The eval judge (pairwise comparison of our report vs baseline) must also
  cross-vendor — grading yourself with the same family is circular

Originally (ADR-001) we planned to wire Anthropic and OpenAI SDKs directly.
A sibling project (FinancialAgent) has solved this same need with
**Agent Maestro**: an Anthropic-API-compatible gateway exposing Claude / GPT /
Gemini behind one wire protocol, with token-unlimited internal access.

## Decision

**All LLM traffic in Plus One goes through Agent Maestro**, accessed via
``langchain-anthropic``'s ``ChatAnthropic`` (pointing ``anthropic_api_url`` at
the Maestro endpoint).

Agent code never names a model — it names a **role** (e.g. ``producer_agent``,
``disagreement_detector``, ``eval_judge``). Roles are mapped to concrete
Maestro model ids via env vars in :mod:`plus_one.core.llm.roles`.

### Role catalogue (initial)

| Role | Default model | Why this model |
|------|--------------|----------------|
| `producer_agent` | claude-opus-4.7 | Broad world knowledge + creative recall |
| `joiner_agent` | claude-opus-4.7 | Heavy reasoning + structured output |
| `controller_agent` | claude-haiku-4.5 | Cheap rule-fallback decisions |
| `skill_router` | claude-haiku-4.5 | Cheap, fast routing |
| `disagreement_detector` | gemini-3.1-pro-preview | **Cross-vendor** — avoid self-correlation with Claude-based Producer/Joiner |
| `eval_judge` | gpt-5.5 | **Cross-vendor** — different family from Producer |
| `bullshit_filter` | gpt-5.5 | Strong at structured extraction |
| `conversational` | claude-haiku-4.5 | Fast follow-up chat |
| `summarizer` | gemini-3-flash-preview | Cheap long-context |

Defaults are env-overridable for A/B experiments.

## Alternatives considered

### Direct Anthropic + OpenAI SDKs (original ADR-001 plan)

- **Pros**: No gateway dependency; simpler local dev
- **Cons**: Two SDKs to manage; multiple API keys; no token-unlimited; manual
  failover wiring; need to manage rate-limit budgets ourselves
- **Why rejected**: Maestro removes all of these costs

### Pydantic AI / LangChain agent abstractions

- **Pros**: Higher-level
- **Cons**: We still need our own role mapping + per-role sampling; the
  abstractions don't add value over a thin Maestro wrapper
- **Why rejected**: Net-negative ergonomics; we want full control of the call

### Locally caching LLM responses (demo-mode CachedLLMProvider, original plan)

- **Pros**: Offline / reproducible demos
- **Cons**: Token-unlimited via Maestro removes the cost motivation;
  cache invalidation is its own complexity; tests can stub the provider
  directly without a file-based cache
- **Why rejected**: With Maestro the demo concern goes away — we can always
  hit a real model. Tests stub at the Protocol boundary instead.

## Consequences

### Positive

- One wire protocol, one SDK
- Cross-vendor diversity is a config change, not a code change
- Token-unlimited removes the "is this query worth running?" friction during dev
- Reduces secrets surface (one Maestro token vs N vendor API keys)
- Roles document *intent*, not just *capacity* — code reads "we use the
  disagreement_detector here" which is more revealing than "we use Gemini here"

### Negative / Trade-offs

- Hard dependency on Maestro availability — if the gateway is down, the app is down
- Defaults assume internal Microsoft Maestro is reachable (host.docker.internal)
- Public release will require either: (a) running our own Maestro instance,
  (b) replacing with direct vendor SDKs, or (c) defining a hosted alternative
- Anthropic SDK feature lag — features only on the native Anthropic SDK
  (computer-use, Files API) are not directly available; we'd need Maestro to add them

### Follow-ups

- [ ] Implement structured-output parsing fallback (done: ``parsers.py``)
- [ ] Add a thin wrapper that emits Langfuse traces around every Maestro call
- [ ] Document Maestro setup in CONTRIBUTING.md
- [ ] Before public release: revisit "production deployment without Maestro"
      decision tree

## References

- ADR-001 (tech stack — partially superseded)
- ``backend/src/plus_one/core/llm/roles.py``
- ``backend/src/plus_one/core/llm/maestro_provider.py``
- FinancialAgent (sibling project) ``backend/src/agent/llm_factory.py``

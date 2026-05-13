# ADR-006: Self-hosted local deployment posture

## Status

Accepted (2026-05-13). Supersedes deployment portions of ADR-001.

## Context

After deciding that all LLM traffic goes through Agent Maestro (ADR-005), we
faced a follow-up question: how is Plus One actually *run*? Maestro is a
VS Code extension that borrows the developer's GitHub Copilot quota via the
``vscode.LanguageModelChat`` API. It cannot be deployed headless to Azure
without:

  - Violating GitHub Copilot ToS (running Copilot on a server)
  - Or paying for direct Anthropic / OpenAI / Gemini API access
    (defeating the "token-unlimited" benefit)

So Plus One's deployment story is constrained by Maestro's hosting model.

## Decision

**Plus One runs entirely on the developer's local machine.** Production
deployment to Azure / Fly.io / Vercel is NOT pursued for v1.

Components:

| Component | Where it runs |
|-----------|---------------|
| Backend (FastAPI) | localhost:8000 |
| Frontend (Next.js dev server) | localhost:3000 |
| Redis | localhost:6379 (docker-compose) |
| Agent Maestro | localhost:23333 (VS Code extension) |
| **PostgreSQL** | **Azure Database for PostgreSQL (managed)** |

PostgreSQL is the one component on cloud — Azure managed Postgres gives us
durability (PITR, automated backups, no disk failure risk) without
self-hosting ops. Cost ~$15/month on Burstable B1ms.

CI runs all backend tests with the LLM provider **mocked** — see
``backend/tests/conftest.py`` and ADR following this one when written.
No CI job ever calls Maestro or any real LLM endpoint.

E2E tests run on the developer's machine, hitting real Maestro.

## Alternatives considered

### Deploy backend to Azure / Fly.io with direct vendor API keys

- **Pros**: Real-world deployable, sharable URL, demoable to remote
  interviewers
- **Cons**: Need to pay Anthropic / OpenAI / Gemini directly; rebuilds the
  exact gateway Maestro already gives us; doubles configuration surface
- **Why rejected**: Project is a personal portfolio piece, not a public
  product. The marginal value of cloud deployment doesn't justify the cost
  + complexity. If we ever decide to publish, this ADR is revisited.

### Headless VS Code on Azure with Copilot installed

- **Pros**: Maestro could run on the cloud
- **Cons**: Violates GitHub Copilot ToS; account ban risk; code-server's
  Copilot Chat support is unreliable
- **Why rejected**: ToS violation is a non-starter

### Rewrite Maestro to call vendor APIs directly

- **Pros**: Decouples from VS Code
- **Cons**: Equivalent to writing a new LLM gateway from scratch; still
  requires paying for tokens; ~2-3 weeks of pure plumbing work with zero
  product value
- **Why rejected**: Cost without benefit

## Consequences

### Positive

- **Zero ongoing infrastructure cost** beyond Azure Postgres (~$15/mo) and
  Copilot subscription ($10/mo, already paid)
- **No deployment pipeline to maintain** — fewer moving parts, faster iteration
- **CI is fast + free** — mocked LLM means tests run in seconds with no
  network or cost
- **Demo for interviews works**: laptop running everything locally, presentable
  via screen share

### Negative / Trade-offs

- **Cannot share a URL** with friends / interviewers for them to try
  (mitigation: record demo videos; share screen during live interviews)
- **No telemetry from real users** unless we publish (mitigation: Phase β
  reach-out plan recruits friends to run it locally)
- **Resume signal slightly different**: "self-hosted personal AI agent"
  rather than "SaaS deployed to N users". Honest framing required.
- **Re-deploying later is non-trivial** if we change minds: would need
  to revisit auth (currently magic-link assumes single user), CORS, secrets

### Follow-ups

- [ ] Remove `infra/docker/Dockerfile.web` and `Dockerfile.worker` (done)
- [ ] Remove `infra/fly.toml` (done)
- [ ] Update README to reflect self-hosted posture
- [ ] Add Maestro setup instructions to CONTRIBUTING.md
- [ ] If publishing later: write ADR superseding this, deciding deployment topology

## References

- ADR-001 (tech stack — partially superseded)
- ADR-005 (LLM via Maestro)
- Discussion thread in design log, 2026-05-13

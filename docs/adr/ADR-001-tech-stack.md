# ADR-001: Tech Stack Selection

## Status

Accepted (2026-05-13). Amended by later stack work: the current frontend is
Next.js 16 + React 19, the PWA layer is Serwist, and ADR-006 changed hosting to
self-hosted local app services with managed Postgres.

## Context

Plus One is a solo-developer side project (target: 6-12 months to a polished
product, not a 10-week sprint) building an AI travel planner that:

- Runs multi-agent cycles (60-90s per query)
- Scrapes Xiaohongshu via headless browser
- Maintains user accounts with personalization
- Exposes a streaming UI (live progress + report)
- Targets eventual deployment as a PWA

The developer's background is .NET / C# (Microsoft Sydney AI platform),
moving to Python for this project. Constraints:

- Solo dev — must be maintainable by one person
- Quality > speed — accepting 6-12mo timeline
- Must showcase real engineering depth (resume / interview signal)

## Decision

| Layer | Choice |
|-------|--------|
| Backend language | Python 3.12 |
| Web framework | FastAPI |
| Async runtime | asyncio (native) |
| LLM SDK | `langchain-anthropic` via **Agent Maestro** gateway (see ADR-005) |
| ORM | SQLAlchemy 2.0 (async) + Alembic |
| Auth | FastAPI Users + magic-link email |
| DB | Azure Database for PostgreSQL Flexible Server |
| Cache / pub-sub | Redis |
| Background tasks | asyncio.Queue + BackgroundTask (MVP); Arq later |
| Scraping | Playwright (Python) |
| Observability | Langfuse (LLM) + structlog (app) |
| Frontend | Next.js 16 App Router + React 19 + TypeScript |
| Styling | Tailwind 4 + shadcn/ui |
| State | Zustand + TanStack Query |
| PWA | Serwist |
| Streaming | Server-Sent Events |
| Frontend host | Local dev server for MVP |
| Backend host | Local FastAPI process for MVP |
| DB host | Azure (East Asia) |
| Package mgmt | uv (Python) + pnpm (Node) |

## Alternatives considered

### TypeScript full-stack (Node + Next.js)

- **Pros**: Single language across stack, Vercel AI SDK is best-in-class for streaming, shared types via Zod
- **Cons**: LLM ecosystem maturity less than Python, scraping harder for hostile targets like XHS, dev's Python skills are explicit project goal
- **Why rejected**: Python's ML/LLM/scraping ecosystem maturity is decisive; dev wants to grow Python skills

### .NET 8 + TypeScript frontend

- **Pros**: Dev's strongest language, .NET 8 async is excellent
- **Cons**: LLM ecosystem in .NET is significantly weaker (no equivalents to Pydantic AI / LangGraph), scraping libraries less mature
- **Why rejected**: LLM/scraping ecosystem gap too large; the project's goal includes Python upskilling

### Serverless (Vercel Functions / Cloudflare Workers)

- **Pros**: Zero ops, auto-scale, free tier
- **Cons**: 60-90s agent runs exceed function timeouts; Playwright doesn't fit serverless cost model
- **Why rejected**: Hard timeout constraints incompatible with workload

## Consequences

### Positive

- Best-in-class LLM ecosystem (Pydantic AI, Anthropic SDK, Langfuse all Python-first)
- Playwright Python is mature for scraping
- FastAPI + asyncio handles long-running tasks naturally
- Next.js gives a modern frontend with typed routes and PWA support
- Azure Postgres removes self-hosted DB risk (a reviewer flagged this as critical)

### Negative / Trade-offs

- Two languages (Python + TypeScript) — context switching cost
- Dev learning Python while building — expect 1.5x time on early backend work
- Local-host posture limits external ops, but puts demo reliability on the
  developer machine
- Magic-link adds email-delivery dependency (vs password)

### Follow-ups

- [x] ADR-005: All LLM traffic via Agent Maestro gateway (token-unlimited multi-vendor)
- [x] ADR-002: Why custom agent framework over LangGraph
- [x] ADR-003: Data sources strategy (later amended: Reddit JSON + Foursquare)
- [x] ADR-004: Monorepo structure

## References

- PRD: `docs/prd.md`
- Senior review feedback informing this decision: see internal review notes

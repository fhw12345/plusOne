# Plus One

> AI travel planner — extracts scattered local experience from Reddit / Xiaohongshu
> into structured **"local gems vs tourist traps"** reports, with Chinese / English
> dual-source perspectives and information-disagreement detection.

## Why this exists

Current travel guides suffer from three problems:
1. **Sponsored content drowns real experience** (Xiaohongshu, TripAdvisor)
2. **Single-language sources miss half the picture** (Reddit lacks Chinese local lens; 小红书 lacks Western traveler context)
3. **No tool tells you when sources disagree** (the most informative signal is hidden)

Plus One solves these by running a multi-source agent cycle that:
- Pulls signal from Reddit + Xiaohongshu + Foursquare Places in parallel
- Filters sponsored content via heuristics + LLM judgment
- Cross-validates claims and surfaces disagreements as first-class output
- Personalizes by user / companion preferences (per-card match scoring)

## Status

🚧 **Phase α — Active development**. See [docs/prd.md](docs/prd.md) for the
full product spec and [docs/adr/](docs/adr/) for key architectural decisions.

**Backend is complete; frontend pending.** See
[docs/handoff/REMAINING_WORK.md](docs/handoff/REMAINING_WORK.md) for the
current state, a curl-based demo of the working backend, and the plan
for finishing the frontend + end-to-end smoke.

Plus One is **self-hosted on the developer's machine** (see [ADR-006](docs/adr/ADR-006-local-host-posture.md)).
Only PostgreSQL runs on Azure for durability. LLM traffic goes through a
local Agent Maestro instance running as a VS Code extension (free, borrows
your GitHub Copilot quota — see [ADR-005](docs/adr/ADR-005-llm-via-maestro.md)).

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the system diagram and component
breakdown.

High-level:

```
Next.js dev (localhost:3000) ──HTTPS+SSE──▶  FastAPI (localhost:8000)
                                                  │
                                                  ├──── Azure Postgres
                                                  ├──── Redis (localhost)
                                                  └──── Maestro (localhost:23333)
                                                            │
                                                            └──▶ Claude / GPT / Gemini
                                                                 (via VS Code + Copilot)
```

## Quick start (local dev)

```bash
# Prerequisites:
#   - VS Code with Agent Maestro extension installed and running
#     (provides localhost:23333 LLM gateway, uses your Copilot subscription)
#   - Docker Desktop (for postgres + redis)
#   - uv (Python pkg mgmt), pnpm, just

# 1. Start infra (postgres + redis)
docker compose -f infra/docker-compose.yml up -d

# 2. Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn plus_one.main:app --reload

# 3. Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev

# 4. Open http://localhost:3000
```

## Tech stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic
- **Agent framework**: custom cycle / skill / multi-agent system (see ADR-002)
- **LLM**: All traffic via **Agent Maestro** gateway — multi-vendor (Claude / GPT / Gemini), role-based model selection (see ADR-005)
- **DB**: Azure Database for PostgreSQL Flexible Server
- **Cache / Queue**: Redis
- **Scraping**: Playwright (Reddit via PRAW, Xiaohongshu via headless browser)
- **Observability**: Langfuse (LLM traces + cost), structlog (JSONL logs)
- **Frontend**: Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui, Zustand
- **PWA**: next-pwa
- **Deploy**: Self-hosted local (see ADR-006). Postgres on Azure managed.

## Repo layout

```
plus-one/
├── backend/        # FastAPI + agent framework + workers
├── frontend/       # Next.js PWA
├── infra/          # docker-compose, Dockerfiles, fly.toml, deploy scripts
├── docs/           # PRD, ADRs, design notes
└── .github/        # CI workflows, PR templates
```

## Development

- **Branching**: `main` is protected; all changes via PR from `feature/*` or `fix/*`
- **CI**: lint + typecheck + tests must pass to merge
- **Commits**: conventional commits encouraged (`feat:`, `fix:`, `chore:`, `docs:`)
- **ADRs**: every load-bearing decision gets an ADR in `docs/adr/`

### E2E (Playwright)

~~~bash
just frontend-e2e-install   # one-time: download chromium binary
just frontend-build         # build for production (e2e runs against pnpm start)
just frontend-e2e           # run headless
just frontend-e2e-ui        # interactive UI mode for debugging

# All browsers locally:
cd frontend && PLAYWRIGHT_ALL_BROWSERS=1 pnpm e2e
~~~

See [CONTRIBUTING.md](CONTRIBUTING.md) (TODO) for full dev workflow.

## License

TBD (likely AGPL or proprietary — pending decision)

## Disclaimer

Xiaohongshu data is collected for personal research and demo purposes. The
project does not redistribute scraped content; all displayed claims link back
to original sources. Production / commercial use will require a different
data-sourcing strategy.

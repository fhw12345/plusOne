# Architecture

## High-level diagram

```
┌─────────────────────────┐
│   Next.js dev server    │  localhost:3000
│   - App Router          │
│   - SSE client          │
│   - Zustand state       │
└────────────┬────────────┘
             │ HTTP + SSE
             ▼
┌─────────────────────────────────────────────────────────────┐
│      FastAPI Web (localhost:8000)                           │
│                                                             │
│   /api/auth         register / verify / login + JWT cookie  │
│   /api/profile      user profile CRUD                       │
│   /api/companions   companion CRUD                          │
│   /api/trips        POST → enqueue, GET /:id/stream → SSE   │
│   /api/shared       share-link report view                  │
│   /api/me           export + hard-delete                    │
│                                                             │
│   In-process asyncio.Queue per session                      │
│   (v2: Arq + Redis Pub/Sub when concurrency demands)        │
└────┬─────────────────────────────────────────┬──────────────┘
     │                                         │
     │ async DB                                │ async tools
     ▼                                         ▼
┌──────────────────┐                ┌─────────────────────────┐
│  Azure Postgres  │                │  Agent Cycle (worker)   │
│  Flexible Server │                │                         │
│  (East Asia)     │                │  Producer ─▶ Joiner ─▶  │
│                  │                │  Controller ─▶ (loop)   │
│  Tables:         │                │                         │
│   users          │                │  Skills (file-based,    │
│   profiles       │                │  hot-loaded)            │
│   companions     │                │  Tools:                 │
│   trips          │                │   - reddit_search       │
│   reports        │                │   - xhs_search          │
│   feedback       │                │   - foursquare          │
│   skill_versions │                │   - llm (Maestro)       │
│   prompt_runs    │                └────┬────────────────────┘
│   eval_results   │                     │
└──────────────────┘                     │ external
                                         ▼
                              ┌──────────────────────────────┐
                              │  Agent Maestro               │
                              │  (localhost:23333,           │
                              │   VS Code extension)         │
                              │     ↓                        │
                              │   Claude / GPT / Gemini      │
                              │   via Copilot quota          │
                              │                              │
                              │  Reddit public JSON          │
                              │  Foursquare Places API       │
                              │  Xiaohongshu fallback chain  │
                              │  Langfuse (optional, local)  │
                              └──────────────────────────────┘
```

## Key design choices

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Backend | FastAPI + asyncio | Native async, Pydantic-first, fits LLM-heavy I/O |
| Agent framework | Custom (cycle / skill / multi-agent) | See [ADR-002](docs/adr/ADR-002-cycle-framework-vs-langgraph.md) |
| LLM access | Agent Maestro gateway (multi-vendor) | See [ADR-005](docs/adr/ADR-005-llm-via-maestro.md) |
| Persistence | Postgres (Azure managed) | Reliability > self-hosting; managed backups + PITR |
| Queue (MVP) | In-process asyncio.Queue | <100 users; defer Arq until measured queue depth |
| Streaming | SSE | Simpler than WebSocket; one-way is enough |
| Frontend | Next.js 16 App Router + React 19 + Serwist PWA | Modern, single-language with backend types |

## Three-layer agent architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Producer Agent                                             │
│   Generates candidate items (places, regions) from context  │
│   Skills: ramen_basics, tokyo_geography, ...                │
│   Output: Pydantic-validated Candidate[]                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Joiner Agent                                               │
│   Cross-validates candidates against multi-source data      │
│   Skills: bullshit_filter, source_weighting, ...            │
│   Tools: reddit_search, xhs_search, foursquare              │
│   Output: JoinedItem[] with classification + evidence       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Controller Agent                                           │
│   Decides: continue cycle (with focus) OR converge          │
│   Rule-first (depth, coverage, info-saturation)             │
│   LLM fallback for ambiguous cases                          │
│   Output: ControllerDecision (continue/stop + summary)      │
└─────────────────────────────────────────────────────────────┘
```

## Data flow: user submits a trip query

```
1. POST /api/trips                  ← Next.js
2. Auth check + DB insert (pending) ← FastAPI
3. asyncio.create_task(run_agent)   ← BackgroundTask
4. Return {trip_id}                 ← HTTP 202

5. GET /api/trips/:id/stream        ← Next.js opens SSE
6. SSE handler subscribes to in-mem queue for trip_id

7. Worker (run_agent):
   ├─ producer → emit progress event
   ├─ joiner   → emit progress + partial results
   ├─ controller → emit decision
   ├─ (loop)
   └─ emit final report (streaming)

8. Frontend renders progress (left panel) + report (right panel) live
9. On final → DB update report, close SSE
```

## Observability

| Layer | Tool | What it captures |
|-------|------|------------------|
| LLM calls | Langfuse | Prompts, completions, tokens, cost, traces |
| App logs | structlog (JSONL) | Structured events with trace_id |
| HTTP | FastAPI middleware | Request latency, status codes |
| (Future) Metrics | Prometheus | When traffic justifies it |

## Security & privacy

- **Secrets**: env vars only; `.env` gitignored; `detect-secrets` in pre-commit
- **Auth**: magic-link email (no passwords stored); JWT short-lived (1h)
- **PII**: user data exportable + hard-deletable (GDPR-style)
- **Scraped content**: stored separately from user IDs; joined only at query time
- **CORS**: restricted to known frontend origins

## Scaling assumptions

MVP designed for <100 concurrent users. Scaling triggers:

| Trigger | Action |
|---------|--------|
| Queue depth > 5 sustained | Migrate to Arq + Redis-backed queue |
| Multiple backend instances | Move pub/sub from in-process to Redis |
| LLM cost > $50/mo | Add semantic caching layer |
| DB CPU > 60% sustained | Vertical scale Azure tier |

# Plus One — Remaining work handoff

> Status snapshot: 2026-05-14. Backend complete and tested through PR #7;
> Frontend (Batch 2f) and E2E (Batch 2g) deferred.

This document is the source of truth for picking up Plus One where the
last session stopped. It is intentionally **specific** — file paths,
commands, prompts, gotchas — so the next session (or you yourself in a
fresh window) can hit the ground running without re-deriving design
decisions from PR threads.

---

## Current state at a glance

| Layer | Status | What works |
|-------|--------|------------|
| Harness (lint / mypy / CI / pre-commit) | ✅ Complete | `just check` green; PR-based workflow with auto-reviewer |
| Agent framework (cycle / skill / tool) | ✅ Complete | `tests/unit/agents/framework/` |
| LLM layer (Maestro provider + role map + mock) | ✅ Complete | `tests/unit/test_llm_provider.py` — CI never calls real LLM |
| DB (models / migrations / async session) | ✅ Complete | Postgres-only (JSONB, PGUUID); migration is hand-written |
| Auth (magic-link + JWT + cookie + current_user) | ✅ Complete | `tests/unit/auth/`, `tests/unit/api/test_auth.py` |
| Tools (Reddit / XHS / Google Places — fixture-backed) | ✅ Complete | `tests/unit/tools/` |
| Domain agents (Producer / Joiner / Controller) | ✅ Complete | `tests/unit/agents/test_domain_agents.py` |
| Trips API + SSE + Report persistence | ✅ Complete | `tests/unit/services/test_trip_runner.py` |
| **Frontend (Next.js)** | 🚧 Skeleton only | landing page renders; no auth, no trip flow |
| **End-to-end demo** | ⏳ Not yet wired | Manual smoke pending |

7 PRs merged so far (`git log --oneline main` for the list). Test count
at last green: **123 unit tests passing**, **89% coverage on backend**.

---

## How to demo right now (backend-only, via curl)

The full backend works without the frontend. You can demo it in a
terminal as proof.

### Prereqs

```bash
# 1) Start postgres + redis
docker compose -f infra/docker-compose.yml up -d postgres redis

# 2) Apply DB migrations
cd backend && uv run alembic upgrade head

# 3) Set the email-sender opt-in (so /auth/request-link logs the link)
echo "ALLOW_CONSOLE_EMAIL_SENDER=true" >> .env

# 4) Set Maestro endpoint (your local VS Code Maestro extension)
echo "MAESTRO_BASE_URL=http://localhost:23333/api/anthropic" >> .env
echo "MAESTRO_AUTH_TOKEN=Powered by Agent Maestro" >> .env

# 5) Run the backend (allow real LLM in this process)
PLUS_ONE_ALLOW_REAL_LLM=1 uv run uvicorn plus_one.main:app --reload
```

### Walk-through

```bash
# A) Request a magic link — server logs the URL
curl -X POST http://localhost:8000/api/auth/request-link \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com"}'
# Look in server console for: magic_link_console_only ... link=http://...

# B) Copy the token from that URL and exchange for a JWT
curl -X POST http://localhost:8000/api/auth/exchange \
  -H 'Content-Type: application/json' \
  -d '{"token":"<paste_token_here>"}'
# Returns {"access_token": "<jwt>", "token_type": "bearer", "expires_in_minutes": 60}

# C) Create a trip
TOKEN=<paste_jwt>
curl -X POST http://localhost:8000/api/trips \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"destination":"Tokyo","free_text":"tonkotsu ramen, avoid tourist traps"}'
# Returns {"trip_id":"...", "status":"pending"}

# D) Subscribe to live SSE progress
TRIP=<paste_trip_id>
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/trips/$TRIP/stream
# Streams: event: started ... event: producer ... event: joiner ...
# event: controller ... event: trip_complete

# E) Fetch the persisted report
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/trips/$TRIP
```

If any of these fail, it's a real bug — fix it before starting Batch 2f.

---

## Batch 2f — Frontend

### Goal

Get the **happy path** working end to end in a browser:

1. User visits `http://localhost:3000`, lands on a login page.
2. Enters email → POST `/api/auth/request-link`.
3. Pulls the link from the dev console, opens it.
4. Frontend calls `/api/auth/exchange`, stores the JWT.
5. Redirects to a trip-input form.
6. User fills destination + free text → POST `/api/trips`.
7. Frontend immediately opens SSE stream, renders progress live.
8. On `trip_complete`, frontend fetches `/api/trips/{id}` and renders
   the report cards (Tabs: Local Gems / Tourist Traps / Together / etc).

Out of scope for Batch 2f: profile management, companions, feedback
buttons, multi-trip history, polish. Add them as Batch 2h+.

### Suggested PR structure

Don't try to ship all of this in one PR — the reviewer will (correctly)
push back on size. Split:

#### PR A — Auth pages + API client + Zustand store (~400 LOC)

```
frontend/lib/
  api.ts           # fetch wrapper that reads JWT from a Zustand store
  auth.ts          # requestMagicLink, exchangeToken
  types.ts         # mirror of backend Pydantic schemas (CreateTripBody, etc)
frontend/lib/stores/
  auth.ts          # Zustand: { token, user, setToken, clearToken }
frontend/app/login/
  page.tsx         # Email form -> /api/auth/request-link -> "check your email"
frontend/app/auth/exchange/
  page.tsx         # Reads ?token=, calls /api/auth/exchange,
                   # stores JWT, redirects to /
frontend/components/ui/
  (shadcn/ui scaffolding — Input, Button, Card, Tabs)
```

Tests: `vitest` for `api.ts` mock-fetch round-trips. Auth pages can be
manual-smoke for Batch 2f; serious E2E waits for 2g.

#### PR B — Trip input + SSE consumer + report view (~500 LOC)

```
frontend/app/page.tsx                      # gated: redirect to /login if no JWT
frontend/app/trips/new/page.tsx            # destination + free_text form
frontend/app/trips/[id]/page.tsx           # SSE consumer + report view
frontend/components/trips/
  TripForm.tsx
  ProgressFeed.tsx                         # Renders SSE events as a timeline
  ReportCards.tsx                          # Tabs + per-card detail
  ItemCard.tsx
frontend/lib/sse.ts                        # EventSource wrapper that parses our event format
```

The backend SSE format is:

```
event: <name>
data: {"name":"...","depth":N,"data":{...}}

```

Event `name` values to handle:
- `started` — initial; show "Cycle started"
- `iteration_start` — bump depth indicator
- `producer` — show "Generating candidates"
- `joiner` — show "Cross-validating evidence" + n_in/n_out
- `controller` — show "Deciding next step" + reasoning
- `cycle_aborted` — show error banner with `data.reason`
- `cycle_complete` — show "Done"
- `trip_complete` — terminal; pivot to fetching `GET /api/trips/{id}`

### Frontend gotchas to know in advance

1. **JWT storage**: The backend sets an `httpOnly` cookie AND returns
   the JWT in the body. For the SPA, prefer the cookie path (no XSS
   risk). The fetch wrapper just needs `credentials: 'include'`. The
   body-token storage is for non-browser clients (CLI / mobile).

2. **CORS**: The backend in `main.py` allows `http://localhost:3000`
   only. If you change frontend port, update `allow_origins`.

3. **SSE through Next.js dev server**: `EventSource` from the browser
   directly to `http://localhost:8000/api/trips/{id}/stream` works.
   Don't try to proxy through `next.config.mjs` rewrites — SSE doesn't
   tolerate buffering.

4. **`PLUS_ONE_ALLOW_REAL_LLM=1` reminder**: the backend refuses to
   construct the LLM provider unless this env var is set. Production
   entry points (uvicorn) set it; tests don't. If the frontend hits
   `/api/trips` and gets a 500, this is the first thing to check.

5. **`ALLOW_CONSOLE_EMAIL_SENDER=true` for dev**: without it,
   `/api/auth/request-link` returns 503 (intentional safety). For a
   real demo, set it.

6. **Trip status states**: `pending` → `running` → `complete` |
   `aborted`. Frontend must handle `aborted` gracefully (show the
   `cycle_aborted` event's reason).

### Reviewer cadence

Use mode B (single review per PR). The reviewer agent is well-trained
on this codebase by now — it'll catch real frontend issues (XSS, CSRF,
SSE leaks, race conditions in React-state-with-EventSource).

---

## Batch 2g — End-to-end smoke + bug fix

After Batch 2f's PRs land, the only thing left is **actually running it**.

### Steps

```bash
# 1) Start everything
docker compose -f infra/docker-compose.yml up -d postgres redis
cd backend && uv run alembic upgrade head

# 2) Backend
PLUS_ONE_ALLOW_REAL_LLM=1 \
ALLOW_CONSOLE_EMAIL_SENDER=true \
  uv run uvicorn plus_one.main:app --reload &

# 3) Frontend (separate terminal)
cd frontend && pnpm dev

# 4) Browser
open http://localhost:3000
```

Walk the user flow end to end. Expect to find 3-5 real bugs. Fix each
in its own small PR; they should be `fix/...` branches off `main`.

### Likely bugs (predict, don't ignore)

- **Stream reconnection**: if the SSE connection drops mid-cycle, the
  current frontend has no retry — events are lost. Decide: silently
  retry, or show a "reconnecting" toast? Either is fine; pick one.
- **CORS preflight on SSE**: Some browsers send an OPTIONS preflight
  on `EventSource`. FastAPI's CORS middleware should handle it, but
  double-check.
- **JWT expiration mid-cycle**: 60-min TTL vs 90-second cycle is
  fine, but if the user starts a trip with 3 minutes left and it
  takes 4, the SSE connection dies on the 401. Decide: refresh-token
  flow (out of scope for v1) or just show a banner.
- **Maestro not running**: If the user starts the backend without VS
  Code's Maestro extension active, the cycle will fail on the first
  LLM call. The `cycle_aborted` event will fire — make sure the UI
  surfaces this clearly.
- **Empty Producer**: For some queries the LLM returns no candidates
  → `CycleAbortedError` → `cycle_aborted` SSE → frontend should show
  a "no results" card, not crash.

---

## Known follow-ups (file as separate issues / PRs after E2E works)

These are the deferred items the reviewer agent flagged across the 7
PRs. None block E2E; all are real long-term work.

### From PR #2 (Agent framework)
- N1: `_ResultCarrierError` smuggles partial result via `__cause__`
  — replace with explicit `partial_result` attribute on
  `CycleAbortedError`.
- N2: `Decision` reconstruction in `run_cycle` drops fields if
  `Decision` ever grows; pass the full object via event data.
- N3: At depth-cap with `should_continue=True`, `decision.should_continue`
  is `True` but cycle stopped — stamp `reasoning` with "depth cap".

### From PR #3 (DB)
- F5: `Trip.reports` lazy strategy — paginate at query layer when
  trip regeneration count grows.
- F6: Add `alembic check` step to CI (requires running Postgres in CI).

### From PR #4 (Auth)
- F4: Cleanup cron job for expired magic-link tokens.
- F6: Rate limiting on `/api/auth/request-link` (e.g. slowapi).
- Add `/api/auth/logout` test.

### From PR #5 (Tools)
- Subreddit case-folding (`("Ramen",)` vs `("ramen",)` produce
  different cache keys).
- Live (non-fixture) tool implementations: real PRAW for Reddit,
  Playwright + 3-tier fallback for XHS (per ADR-003), real
  Google Places API.

### From PR #6 (Domain agents)
- Move `_MIN_LOCAL_GEMS` / `_MIN_TOURIST_TRAPS` into a
  `ControllerConfig` dataclass.
- Skill cache reload via `PLUS_ONE_RELOAD_SKILLS=1` env var (dev).
- Drop the `cast(Tool[Any, Any], ...)` workaround by fixing the
  Protocol's ClassVar declaration in `framework/tools.py`.
- Switch `template.format(...)` in prompts.py to `str.Template` so a
  stray `{}` in a prompt doesn't crash.

### From PR #7 (Trips API)
- " | " query join is lossy; pass a structured query object.
- `GET /api/trips/{id}` returns only latest report — add `/reports`
  list for history.
- `asyncio.Queue(maxsize=N)` to bound memory under slow consumers.
- Wider HTTP-level tests (cycle abort, status flips, cross-user 404).

### Profile / Companion endpoints
- Not built yet. PRD §8 specifies them. Frontend can ship without
  them (uses defaults), but full PRD compliance needs:
  - `GET /api/profile` / `PUT /api/profile`
  - `GET/POST/DELETE /api/companions`
  - Pass profile + selected companions into `AgentContext` so
    Producer / Joiner can use them in skill routing.

---

## How to ask the next session to continue

If you start a fresh Claude Code session and want it to pick up:

1. Point it at this file: `docs/handoff/REMAINING_WORK.md`.
2. Tell it: "Continue Plus One from where the last session stopped.
   Read `docs/handoff/REMAINING_WORK.md` for state + plan. Use the
   PR-based workflow with auto-reviewer that previous PRs followed.
   Mode B (single reviewer round per PR). Start with Batch 2f PR A
   (auth pages + API client + Zustand store)."
3. Confirm it understands by asking it to summarize the current state
   in one paragraph before writing any code.

The reviewer agent has access to the full repo and ADRs; it does not
need re-onboarding.

---

## Architecture decisions you must NOT silently change

These are documented in `docs/adr/` and were debated across multiple
PR cycles. Changing any of them requires a new ADR superseding the
prior one.

- **ADR-001**: Tech stack (Python + Next.js)
- **ADR-002**: Custom cycle framework over LangGraph
- **ADR-003**: Reddit + XHS scrape + Google Places (fixture-backed in v1)
- **ADR-004**: Monorepo
- **ADR-005**: All LLM via Maestro gateway
- **ADR-006**: Local-host posture (Postgres on Azure, everything else local)

If a new requirement bumps against one of these, write `ADR-007` first.

---

## Final note

The backend is in a healthy, tested, demoable state. The handoff cost
is real but small: one focused session can finish Batch 2f in ~3-4 PRs
and Batch 2g in 1-2 PRs. The reviewer agent has the muscle memory; the
ADRs have the rationale; the tests have the safety net. Pick it up
when ready.

# Plus One — Current Handoff

> Status snapshot: 2026-05-26. Browser MVP is implemented. The latest local
> admin real-chain re-run completed and the trip-detail value pass is in place,
> but Reddit and XHS remain network/auth-sensitive data-source risks.

This is the first file to read when picking the project back up. The older PRD
batch files under `docs/prd/` and `docs/prds/` are useful historical specs, but
many of them describe pre-merge work that has already landed.

## Current State At A Glance

| Layer | Status | What works |
|-------|--------|------------|
| Backend API | Complete for MVP | Auth, admin logs, profile, companions, trips, sharing, export, hard-delete |
| Agent cycle | Complete for MVP | Producer / joiner / controller, clarifier loop, refinement, itinerary output |
| Data sources | Real mode with fallback | Reddit public JSON, XHS profile/cookie Playwright plus prewarmed DB/jsonl cache and public-index fallback, Foursquare Places, fixture degradation |
| Persistence | Complete for MVP | Postgres models, Alembic migrations, report persistence, DB tool cache |
| Frontend | Complete for MVP | Landing, login/register/verify, trip list, trip form, SSE detail view, profile, companions, share page, admin logs |
| E2E | Real chain verified, degraded-source caveats | Tokyo ramen Playwright flow passed with local Agent Maestro; latest admin re-run completed with Reddit 403 and XHS login-wall degradation; see `docs/status/batch-3a-real-e2e.md` |
| Docs | Mostly current | README and this handoff reflect the current state; older PRDs remain historical |

## Latest Proof

The strongest current signal is [docs/status/batch-3a-real-e2e.md](../status/batch-3a-real-e2e.md).

The verified flow covered:

- auth and trip creation
- optional clarifier skip
- SSE progress streaming
- full agent cycle and report persistence
- itinerary rendering
- language toggle rendering
- backend assertions on generated report content

Result from the recorded run:

```text
pnpm e2e -- e2e/trip-flow.spec.ts --project=chromium
1 passed (1.7m)
```

Latest admin re-run generated trip `37813015-ace8-4230-863b-81c3c014e367` with
10 items, 10 evidence-backed cards, 3 itinerary days, synthesized `tl_dr`, and 2
loaded images. Playwright confirmed the trip detail is no longer stuck on
`pulling your notes`, source notes are collapsed by default, and internal
fallback copy is not visible.

## Local Dev

Prerequisites:

- VS Code with Agent Maestro running at `http://127.0.0.1:23333/api/anthropic`
- Docker Desktop for Postgres / Redis
- `uv`, `pnpm`, and `just`

Typical startup:

```powershell
docker compose -f infra/docker-compose.yml up -d

cd backend
uv sync
uv run alembic upgrade head
$env:MAESTRO_BASE_URL='http://127.0.0.1:23333/api/anthropic'
$env:MAESTRO_AUTH_TOKEN='Powered by Agent Maestro'
$env:PLUS_ONE_ALLOW_REAL_LLM='1'
$env:PLUS_ONE_TOOLS_MODE='real'
uv run uvicorn plus_one.main:app --reload
```

In a second terminal:

```powershell
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:3000`.

## Useful Checks

Fast local confidence:

```powershell
just backend-lint
just backend-typecheck
cd frontend; pnpm typecheck
```

Focused real-chain regression from the latest status note:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit\tools\test_foursquare_places_real.py -q
backend\.venv\Scripts\python.exe -m ruff check backend\src\plus_one\core\tools\foursquare_places.py backend\tests\unit\tools\test_foursquare_places_real.py
```

Full-ish local checks:

```powershell
just check
cd frontend; pnpm test
cd frontend; pnpm e2e -- e2e/trip-flow.spec.ts --project=chromium
```

The real E2E depends on local services, Agent Maestro, and network conditions;
when it fails, check the caveats below before assuming a product regression.

## Current Caveats

- Joiner LLM calls can still exceed the configured timeout. The pipeline logs
  `joiner_llm_timeout` and falls back to evidence-grounded joined items.
- Translation is best effort. Translation timeouts are logged and do not block
  report completion.
- Local Reddit access can return 403 depending on network policy. The trip can
  still complete, but English-community evidence is absent or cached/fixture
  backed in that state.
- XHS full-content scraping requires logged-in browser auth. Local dev now
  prefers `XHS_PROFILE_DIR=.auth/xhs-profile` so Playwright reuses a persistent
  profile; `XHS_STORAGE_STATE` and `XHS_COOKIE` are fallback options. The latest
  re-run still hit `xhs login wall: search results require logged-in browser
  auth`, so the tool degraded to public search-index / fixture evidence.
- XHS prewarm now downloads note images into `MEDIA_DIR` (default `backend/media`)
  and stores `/media/xhs/...` URLs in the cached payload. The original CDN URLs
  remain in `source_images` / `cached_images` for provenance. Successful prewarm
  writes both Postgres `tool_cache` and a local `tmp-xhs-prewarm-cache.jsonl` so
  the data can later be imported into a different Postgres without re-scraping.
- Foursquare photos are not used. Venue images come from Wikimedia Commons,
  Openverse, then local fixtures.
- The in-process SSE queue is still the MVP design. Redis pub/sub or Arq is the
  planned scale-up path if multiple backend instances or sustained queue depth
  become real.

## Remaining Work

These are real follow-ups, not blockers for the current local MVP.

### Stabilization

- Keep `backend/.env` pointed at a logged-in `XHS_PROFILE_DIR` before running
  strict no-fallback XHS E2E. Current latest run shows the profile can still hit
  an XHS login wall, so strict XHS is not yet stable.
- For broader XHS coverage, run the conservative prewarm first and let trip
  creation read `tool_cache` before live XHS. If Postgres changes later, import
  the local jsonl with `uv run python -m plus_one.scripts.xhs_prewarm import-local`.
- Decide how the UI should disclose degraded source coverage, especially when
  Reddit 403 or XHS login wall forced fallback evidence.
- Refresh older PRD / ADR wording that still says Google Places or PRAW where a
  current reader might mistake it for live implementation. ADR-003 keeps some
  historical text intentionally; prefer addenda over rewriting history.
- Add bounded `asyncio.Queue(maxsize=N)` for SSE consumers so slow clients
  cannot grow memory unbounded.
- Add wider HTTP-level tests for cycle aborts, status flips, and cross-user 404
  masking.
- Add `alembic check` or migration drift detection to CI once Postgres is
  available there.

### Product Polish

- Improve empty / degraded evidence states so users understand when real sources
  fell back to fixtures.
- Consider a reconnect banner for SSE stream drops.
- Add report history endpoints if multiple report generations per trip become
  user-facing.
- Decide whether Foursquare Premium fields such as ratings / photos are worth
  the cost, or keep the current free image resolver path.

### Technical Debt

- Replace `_ResultCarrierError` partial-result smuggling with an explicit
  `partial_result` attribute on `CycleAbortedError`.
- Preserve full `Decision` objects through cycle events if `Decision` grows.
- Stamp depth-cap stops clearly when `decision.should_continue` is true but the
  cycle stops because of max depth.
- Move controller thresholds such as `_MIN_LOCAL_GEMS` / `_MIN_TOURIST_TRAPS`
  into a config object.
- Switch prompt rendering away from `template.format(...)` if prompt braces keep
  causing escape hazards.

## Historical Notes

- Batch 2f and 2g are done. The old frontend skeleton and backend-only demo
  plan was accurate on 2026-05-14, but no longer reflects `main`.
- Google Places was replaced by Foursquare Places in ADR-003's 2026-05-23
  addendum.
- Reddit PRAW was replaced by the unauthenticated Reddit JSON endpoint in
  ADR-007.
- `docs/handoff/2026-05-22-real-mode-credentials.md` is historical. Real mode
  no longer requires Reddit credentials, and Google Places credentials are no
  longer part of the current path.

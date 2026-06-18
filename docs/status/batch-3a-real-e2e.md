# Batch 3a Real E2E Status

Date: 2026-05-25
Status: real chain verified with Playwright

## Summary

The Tokyo ramen trip flow now completes end to end with the real local Agent Maestro gateway enabled and `PLUS_ONE_TOOLS_MODE=real`. The latest Playwright run exercised auth, trip creation, optional clarifier skip, SSE progress, agent cycle, report persistence, itinerary rendering, language toggle rendering, and backend report assertions.

The previous blocker was that `places_search` treated missing `FOURSQUARE_API_KEY` as fatal in real mode. That made the trip abort during tool registration before the fallback evidence path could run. The tool now checks cache first, calls Foursquare only when a key is configured, and degrades to fixture evidence when the key is missing or the API fails.

## Data-source decisions

- Google Places Photos is not used because it requires billing setup.
- Foursquare `/photos` is not used because it is a premium endpoint and returned 429 with the current account.
- Venue images use the free `PlaceImageResolver` path: Wikimedia Commons, Openverse, then local fixture fallback.
- XHS full-content scraping requires logged-in browser auth. Local dev now prefers `XHS_PROFILE_DIR=.auth/xhs-profile` so Playwright reuses a persistent profile; `XHS_STORAGE_STATE` and `XHS_COOKIE` remain fallbacks. Logged-out XHS search currently returns a login wall, so real mode skips logged-out Playwright, then tries public search-index URL discovery, then fixture fallback when public providers time out or return no posts.
- XHS prewarm can now cache full note payloads ahead of trip creation. During prewarm, note images are downloaded into `MEDIA_DIR` and cached posts expose `/media/xhs/...` image URLs while retaining original CDN URLs in provenance fields.
- Empty XHS scrape/cache results no longer count as successful evidence.

## E2E proof

Command run from `frontend/`:

```powershell
$env:MAESTRO_BASE_URL='http://127.0.0.1:23333/api/anthropic'
$env:MAESTRO_AUTH_TOKEN='Powered by Agent Maestro'
$env:PLUS_ONE_ALLOW_REAL_LLM='1'
$env:PLUS_ONE_TOOLS_MODE='real'
$env:PLUS_ONE_TRANSLATE_ENABLED='1'
$env:PLUS_ONE_TRANSLATE_TIMEOUT_S='8'
$env:PLUS_ONE_JOINER_LLM_TIMEOUT_S='25'
$env:XHS_TIMEOUT_S='8'
$env:NO_PROXY='*'
$env:LLM_DEFAULT_MAX_TOKENS='16000'
pnpm e2e -- e2e/trip-flow.spec.ts --project=chromium
```

Result:

```text
1 passed (1.7m)
```

Verified trip:

```json
{
  "trip_id": "f103b079-2973-40d6-a8e8-c039ea201fa0",
  "status": "complete",
  "latest_report_id": "a2c59621-9fb9-4ae7-8781-b7c054eb9bd4",
  "reports": 1,
  "items": 10,
  "non_insufficient": 10,
  "with_evidence": 10,
  "with_image": 6,
  "sample_names": [
    "Menya Itto",
    "Tsuta",
    "Nakiryu",
    "Ichiran Shibuya",
    "Afuri Ebisu"
  ]
}
```

## Additional validation

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit\tools\test_foursquare_places_real.py -q
backend\.venv\Scripts\python.exe -m ruff check backend\src\plus_one\core\tools\foursquare_places.py backend\tests\unit\tools\test_foursquare_places_real.py
```

Results:

```text
9 passed
All checks passed!
```

Earlier focused validation for the broader real-chain patch also passed:

```text
56 passed
pnpm typecheck passed
```

## Current caveats

- Joiner LLM can still exceed the configured timeout. The pipeline logs `joiner_llm_timeout` and falls back to evidence-grounded joined items so the trip can complete instead of hanging.
- Translation is best effort in E2E. Timeouts are logged and do not prevent report completion.
- XHS public access is opportunistic. Without a valid `XHS_PROFILE_DIR`, `XHS_STORAGE_STATE`, or `XHS_COOKIE`, the tool can only discover publicly indexed note URLs/titles and may degrade to fixture evidence. Strict "all info" XHS E2E requires a logged-in browser profile or equivalent auth state in `backend/.env`.

## Re-run — 2026-05-25 15:03 SGT

Command run from `frontend/` after rebuilding the production bundle with
`NEXT_PUBLIC_API_URL=http://localhost:8010` because local port `8000` was
occupied by an unrelated `dotnet-script` service:

```powershell
$env:PLUS_ONE_BACKEND_PORT='8010'
$env:NEXT_PUBLIC_API_URL='http://localhost:8010'
$env:PLAYWRIGHT_API_URL='http://localhost:8010'
$env:MAESTRO_BASE_URL='http://127.0.0.1:23333/api/anthropic'
$env:MAESTRO_AUTH_TOKEN='Powered by Agent Maestro'
$env:PLUS_ONE_ALLOW_REAL_LLM='1'
$env:PLUS_ONE_TOOLS_MODE='real'
$env:PLUS_ONE_TRANSLATE_ENABLED='1'
$env:PLUS_ONE_TRANSLATE_TIMEOUT_S='8'
$env:PLUS_ONE_JOINER_LLM_TIMEOUT_S='25'
$env:XHS_TIMEOUT_S='8'
$env:NO_PROXY='*'
$env:LLM_DEFAULT_MAX_TOKENS='16000'
pnpm e2e -- e2e/trip-flow.spec.ts --project=chromium
```

Result:

```text
1 passed (2.0m)
```

Observed during the run:

- Register / verify / create trip / optional clarifier skip / SSE all succeeded.
- Agent Maestro completed producer, itinerary, and translator calls.
- Joiner LLM hit the configured timeout and fell back to evidence-grounded joined items; the trip still completed.
- Reddit public JSON returned 403 in this local network path.
- Foursquare had no API key and degraded through cache / fixture behavior.
- XHS had no logged-in profile/storage/cookie; logged-out Playwright was skipped because the search page is gated, then search-index or fixture fallback supplied evidence.

## XHS fix — 2026-05-25

Backend `.env` is now loaded at startup, so direct `os.getenv(...)` tool reads see values such as `FOURSQUARE_API_KEY`, `XHS_PROFILE_DIR`, and `XHS_COOKIE` when present.

XHS real-mode behavior is now:

- With `XHS_PROFILE_DIR`: run Playwright against XHS search using the persistent browser profile, parse note cards, then best-effort open note detail pages to enrich title/body/images/like/comment fields before caching.
- With `XHS_STORAGE_STATE` or `XHS_COOKIE` but no profile: run the same scrape using a temporary context seeded from that auth state.
- Without browser auth: skip logged-out Playwright because current XHS search returns `登录后查看搜索结果`, then try public search-index discovery. This path can return note URLs/titles only and is not a full-content substitute.
- If cache/search-index/fixtures all miss, return an empty successful tool result so the trip pipeline still completes and logs `xhs_total_failure`.

Focused validation after the fix:

```text
cd backend
.\.venv\Scripts\python.exe -m pytest tests/unit/tools/test_xhs_tiers.py tests/unit/tools/test_tools.py -q
23 passed

.\.venv\Scripts\python.exe -m ruff check src/plus_one/config.py src/plus_one/core/tools/xiaohongshu.py src/plus_one/core/tools/_playwright_session.py tests/unit/tools/test_xhs_tiers.py
All checks passed!
```

At the time of this note, strict no-fallback XHS E2E requires local `backend/.env` to point at a valid logged-in `XHS_PROFILE_DIR` or equivalent auth state.

## XHS persistent profile — 2026-05-26

After logging in through a headed Playwright window backed by `backend/.auth/xhs-profile`, local real mode now uses:

```text
XHS_PROFILE_DIR=.auth/xhs-profile
```

Earlier admin verification completed with `xhs_tier1_scrape_ok ... mode=persistent_profile`; that run generated a Tokyo ramen trip with 10 items and 10 images from XHS `xhscdn.com` URLs. Current prewarm behavior downloads those images locally and stores app-facing `/media/xhs/...` URLs instead of relying on XHS hotlinks.

## XHS prewarm cache and local media — 2026-05-28

XHS collection now supports a cache-first path for trip creation:

- `xhs_search` checks the DB-backed `tool_cache` before live scraping by default (`XHS_PREFER_CACHE=1`).
- `plus_one.scripts.xhs_prewarm run` uses the logged-in Playwright context to collect notes and download content images into `MEDIA_DIR/xhs/...`.
- Cached posts store `images` as `/media/xhs/...` URLs for the frontend, plus `source_images` and `cached_images` with the original XHS CDN URLs and local-file metadata.
- The backend serves local media at `/media/...`; the frontend resolves those URLs through `NEXT_PUBLIC_API_URL`.
- Successful prewarm writes Postgres `tool_cache` and appends a local `tmp-xhs-prewarm-cache.jsonl`. A later Postgres can be populated with `uv run python -m plus_one.scripts.xhs_prewarm import-local`.

Focused validation:

```text
cd backend
uv run ruff check src/plus_one/scripts/xhs_prewarm.py src/plus_one/core/tools/_playwright_session.py src/plus_one/core/tools/xiaohongshu.py tests/unit/tools/test_xhs_tiers.py
All checks passed!

uv run pytest tests/unit/tools/test_xhs_tiers.py -q
26 passed

cd frontend
pnpm test -- lib/media.test.ts components/trips/ItineraryView.test.tsx
5 passed

pnpm typecheck
passed
```

## Product-value optimization re-run — 2026-05-26

After the PM/designer review found trip detail too thin and poorly grounded, the joiner and itinerary surface were tightened:

- Joiner search now includes the destination in Reddit/XHS queries.
- Tool evidence is filtered per candidate before classification and image resolution, dropping wrong-city and wrong-place hits.
- Mixed positive/negative source language now lands as `neutral` instead of a confident `local_gem`.
- When the Joiner LLM omits `tl_dr` or times out, the backend synthesizes a report-level takeaway from the classified items.
- Itinerary cards now show an explicit decision line, confidence, why text, per-language signals, and collapsed source notes.

Focused validation:

```text
cd backend
uv run ruff check src/plus_one/agents/joiner.py tests/unit/agents/test_domain_agents.py
All checks passed!

uv run pytest tests/unit/agents/test_domain_agents.py -q
27 passed, 1 warning

cd frontend
pnpm typecheck
passed

pnpm test -- lib/api/client.test.ts components/trips/ItineraryView.test.tsx
11 passed
```

Admin real-chain re-run used a temporary backend on `127.0.0.1:8001` because local port `8000` was occupied by `token-server-lite`; existing `localhost:3000` was left running. Generated trip:

```json
{
  "trip_id": "37813015-ace8-4230-863b-81c3c014e367",
  "status": "complete",
  "items": 10,
  "with_evidence": 10,
  "with_image": 2,
  "day_plan": 3,
  "tl_dr": true
}
```

Observed caveats in that run:

- Reddit public JSON returned local `403` for every sampled query.
- XHS persistent-profile Playwright hit `xhs login wall: search results require logged-in browser auth`, then degraded to public search-index / fixture evidence.
- Joiner LLM exceeded `PLUS_ONE_JOINER_LLM_TIMEOUT_S=45` and used evidence-grounded fallback items.
- Translation produced timeout warnings but did not block trip completion.

Playwright page smoke on `http://localhost:3000/app/trips/37813015-ace8-4230-863b-81c3c014e367` verified:

```json
{
  "status": "complete",
  "articleCount": 10,
  "imageCount": 2,
  "loadedImages": 2,
  "decisionCount": 10,
  "evidenceDetails": 10,
  "openDetails": 0,
  "hasFallbackCopy": false,
  "hasPullingNotes": false
}
```

Current truth: the trip no longer hangs and the page now explains decisions, but the local real-data path is still degraded when Reddit is blocked and XHS auth is gated. Strict no-fallback XHS remains unresolved until the persistent profile can pass XHS search without the login wall.

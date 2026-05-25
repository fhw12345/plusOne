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
- XHS no longer requires cookies. Real mode attempts logged-out public Playwright scraping, then public search-index discovery, then fixture fallback when public providers time out or return no posts.
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
- XHS public access is opportunistic. When logged-out scraping and public search providers fail, the chain degrades to fixture evidence and records the fallback in logs.

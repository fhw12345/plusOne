# Batch 2k — Real-backed data sources + output language toggle

> Status: PRD v2 (ship-quality, verified against code + ADR-003).
> Depends on: Batch 2g + 2h + 2i merged (UI surfaces the language toggle and report view).
> 3-PR split (locked): PR A = Reddit PRAW, PR B = XHS Playwright scraper, PR C = Google Places + output language.

---

## 1. Context

Plus One's product differentiation per `docs/prd.md` §4 and ADR-003 is "Chinese vs English perspectives + cross-source disagreement detection." This requires three live data sources today behind fixtures:

- `backend/src/plus_one/core/tools/reddit.py:43` — `RedditSearchTool` reads `fixtures/reddit/<slug>.json` via `load_json_fixture` (no PRAW yet).
- `backend/src/plus_one/core/tools/xiaohongshu.py:42` — `XHSSearchTool` reads `fixtures/xhs/<slug>.json` (no Playwright yet; comment at line 2 explicitly notes "deferred").
- `backend/src/plus_one/core/tools/google_places.py:42` — `GooglePlacesSearchTool` reads `fixtures/google_places/<slug>.json` (no `googlemaps` client yet).

Cache today is pure filesystem-of-fixtures (`backend/src/plus_one/core/tools/_cache.py:72`, `load_json_fixture`). There is **no in-memory cache, no DB cache**, and no TTL — `_cache.py` is misleadingly named; it's actually a fixture loader. This batch introduces a real DB-backed cache layer (`tool_cache` table) used by all three real-mode paths.

Joiner-side integration (`backend/src/plus_one/agents/joiner.py:75-89`): a fresh `ToolRegistry` is built per `joiner()` call via `_default_registry()`, which instantiates each tool with default args (just `fixtures_dir`). **The joiner is intentionally mode-unaware** — the mode switch lives inside each tool's `execute()` method. This avoids a cross-cutting "mode" parameter in `AgentContext` and keeps the cycle framework clean.

Naming reconciliation with ADR-003: ADR-003 uses `DEMO_MODE=true` for fixture mode. The team-lead-locked decision uses `PLUS_ONE_TOOLS_MODE=real|fixture`. **This PRD adopts `PLUS_ONE_TOOLS_MODE` as the canonical name**; we will treat `DEMO_MODE=true` as an alias mapping to `PLUS_ONE_TOOLS_MODE=fixture` for backwards compatibility (one-line check in `_mode.py`). ADR-003 will be amended in a separate follow-up doc PR (not in this batch).

Dependencies already in `backend/pyproject.toml:42-44`:
- `playwright>=1.49.0` — present (PR B will not add this, only wire it up + add browser-install step).
- `praw>=7.8.0` — present (PR A will not add it, only wire it up).
- `httpx>=0.28.0` — present (used by `googlemaps`? No — PR C still needs `googlemaps` Python client added).

Existing alembic convention (`backend/alembic/versions/20260513_0001_initial_schema.py:21`): revision id format is `YYYYMMDD_NNNN`. New revisions in this batch follow that convention.

---

## 2. Sequencing & dependencies

```
PR A (Reddit + cache infrastructure) ──> PR B (XHS, uses cache table) ──> PR C (Places + language)
       creates tool_cache table              uses tool_cache table          uses tool_cache table
       creates _mode.py                      consumes _mode.py              consumes _mode.py
       creates _cache_db.py                  consumes _cache_db.py          consumes _cache_db.py
                                                                            adds report content schema migration
```

Hard ordering:
- **PR B depends on PR A merged**: PR A introduces the `tool_cache` table and the `_cache_db.py` helper. PR B's 3-tier fallback uses the cache as tier 2.
- **PR C depends on PR A merged**: same `tool_cache` table for Places caching. PR C also adds an *independent* second migration for the Report content schema.
- **PR B and PR C are independent of each other** — they can be developed in parallel after PR A merges; pick whichever lands first based on bandwidth.

Each PR is independently reviewable, independently mergeable behind feature work, and behind the `PLUS_ONE_TOOLS_MODE` env switch — none of them flip default behavior in CI / e2e / dev.

---

## 3. Cross-PR conventions

### 3.1 Mode switch — `_mode.py`

New file `backend/src/plus_one/core/tools/_mode.py` (introduced in PR A, reused by B + C):

- Reads `PLUS_ONE_TOOLS_MODE` env var; defaults to `"fixture"` if unset.
- Accepts `"real"` or `"fixture"`. Anything else raises at first call (loud).
- Alias: `DEMO_MODE=true` → `"fixture"` (back-compat with ADR-003 wording).
- Exposes `def get_tools_mode() -> Literal["real", "fixture"]`.
- Exposes `def require_env(*names: str, tool: str) -> None` — raises `RuntimeError("Tool {tool} requires env vars: {missing}")` at tool instantiation when mode=real. Each tool calls this in `__init__` so misconfig surfaces at app startup (FastAPI dependency injection eagerly constructs tools — or, if not, the first request fails fast with a clean error rather than a cryptic auth error mid-cycle).

CI / e2e / `PLUS_ONE_ALLOW_REAL_LLM=0` runs leave `PLUS_ONE_TOOLS_MODE` unset → fixture mode → no behavior change.

### 3.2 DB cache table — `tool_cache`

Introduced in PR A migration. Reused by PR B + PR C. Schema:

| Column | Type | Notes |
|---|---|---|
| `source` | `String(50)` PK part | e.g. `"reddit"`, `"xhs"`, `"google_places"` |
| `key_hash` | `CHAR(64)` PK part | SHA-256 hex of `cache_key(...)` output |
| `payload` | `JSONB` | The raw tool response list (one entry = one tool call's full result) |
| `fetched_at` | `timestamptz` | Set at insert |
| `expires_at` | `timestamptz` | Indexed; computed at insert as `fetched_at + ttl(source)` |
| `created_at` / `updated_at` | from `TimestampMixin` | Standard |

- **PK**: composite `(source, key_hash)`.
- **Index**: `ix_tool_cache_expires_at` on `expires_at` for cleanup queries.
- Per-tool TTLs (defined in `_cache_db.py` `_TTL_BY_SOURCE`):
  - Reddit: 24h
  - XHS: 7d (content is less time-sensitive; freshness via re-fetch loop in tier 1)
  - Google Places: 30d (address / hours / rating churn is slow)
- **Lookup**: `get_cached(source, key) -> list[dict] | None` returns `None` when row absent OR `expires_at < now()`.
- **Write**: `put_cached(source, key, payload)` upserts (`INSERT ... ON CONFLICT (source, key_hash) DO UPDATE`).
- All cache operations use their own `session_scope()` (per ADR-006 + trip_runner.py:148 pattern of short-lived sessions).

### 3.3 Tool execute pattern (all three tools)

```
async def execute(self, args):
    if get_tools_mode() == "fixture":
        return self._execute_fixture(args)   # current behavior
    return await self._execute_real(args)    # new — with cache fallback
```

`_execute_real` flow per tool varies (PR A: simple cache-or-fetch; PR B: 3-tier; PR C: simple cache-or-fetch).

### 3.4 Thread model — quota exhaustion mid-cycle

Threat-modeled: if real-mode credentials are valid but quota is exhausted mid-cycle, the tool's `_execute_real` raises → caught by `run_tool_calls` framework wrapper → returns a `ToolResult(ok=False, error=...)`. Joiner's `joiner.py:134` already handles `not r.ok` ("empty/{r.error or 'no data'}"). Controller phase declares insufficient evidence → cycle aborts cleanly via `CycleAbortedError`, trip status → `aborted`, user sees clean abort event. **Acceptable** — no need for special quota handling in v1.

---

## 4. PR A — Reddit PRAW + cache infrastructure

### 4.1 Goals

- Wire PRAW (`praw>=7.8.0` already pinned at `backend/pyproject.toml:43`) behind `PLUS_ONE_TOOLS_MODE=real`.
- Introduce `_mode.py` (shared) and `_cache_db.py` (shared) — both used by PR B + C.
- Add `tool_cache` table.
- Fail-loud at tool init if mode=real and Reddit creds missing.
- Fixture mode remains exact current behavior.

### 4.2 Env vars

- `REDDIT_CLIENT_ID` — required when mode=real.
- `REDDIT_CLIENT_SECRET` — required when mode=real.
- `REDDIT_USER_AGENT` — required when mode=real; format `"plus-one/0.1 by <reddit-username>"`.
- `PLUS_ONE_TOOLS_MODE` — `"real" | "fixture"` (defaults `"fixture"`).

### 4.3 Files to change

**Backend:**
- `backend/pyproject.toml` — add `vcrpy>=6.0.0` to `dev` group (cassette tests).
- `backend/src/plus_one/core/tools/_mode.py` — **new** (mode resolution + `require_env`).
- `backend/src/plus_one/core/tools/_cache_db.py` — **new** (`get_cached`, `put_cached`, `_TTL_BY_SOURCE`).
- `backend/src/plus_one/core/tools/reddit.py` — add `_execute_real` branch; PRAW client lazily constructed in `__init__` (after `require_env`).
- `backend/src/plus_one/core/db/models.py` — add `ToolCache` model.
- `backend/alembic/versions/20260520_0002_tool_cache.py` — **new** migration creating `tool_cache` table + `ix_tool_cache_expires_at`.
- `backend/README.md` — document `PLUS_ONE_TOOLS_MODE` and required env vars.

**Tests:**
- `backend/tests/unit/tools/test_mode.py` — env-var resolution; alias; missing-env raises.
- `backend/tests/unit/tools/test_cache_db.py` — TTL boundary; upsert; expired returns None.
- `backend/tests/unit/tools/test_reddit_real.py` — vcrpy cassette under `backend/tests/unit/tools/cassettes/reddit/`; one cassette per query.
- `backend/tests/unit/tools/test_reddit_fixture.py` — keep existing fixture-mode test untouched.

### 4.4 Rate limiting

Bounded via an `asyncio.Semaphore(3)` held at module level in `reddit.py` plus a `1.0s` min-interval guarded by a monotonic-clock check (sufficient for v1; PRAW's own backoff handles 429s on top). Test: simulate 5 concurrent calls, assert at most 3 enter `_execute_real` body simultaneously, total elapsed >= 4s for 5 calls.

### 4.5 Test plan

- **Unit** (`mode=fixture` — current default in CI):
  - `test_reddit_fixture.py` — unchanged, smoke that fixture path still works.
- **Unit** (`mode=real` via cassette):
  - `test_reddit_real.py` — `monkeypatch.setenv("PLUS_ONE_TOOLS_MODE", "real")` + set fake creds + `vcrpy` cassette. Verify: cache miss → PRAW called (cassette) → cache row written → second call within TTL hits cache (no PRAW call).
- **Unit** cache:
  - `test_cache_db.py` — write, read-fresh, advance clock past TTL, read-expired returns None, re-write upserts.
- **Coverage gate**: 80% on the new files (matches repo standard).

### 4.6 Acceptance criteria

1. `pytest` green; coverage gate held.
2. `ruff` + `mypy` clean (no new ignores).
3. With `PLUS_ONE_TOOLS_MODE` unset, ALL existing tests (incl. integration + e2e) pass unchanged.
4. With `PLUS_ONE_TOOLS_MODE=real` and missing `REDDIT_CLIENT_ID`, app startup (or first tool construction) raises a `RuntimeError` with clear message — verified by `test_mode.py`.
5. Cassette-replay path proves: real-mode → cache write → cache hit → no second network call. Verified by spying on `praw.Reddit().subreddit().search`.
6. `alembic upgrade head` + `alembic downgrade -1` round-trips clean (manual smoke; not in CI yet).

### 4.7 Risks + mitigations

- **PRAW is sync**, joiner is async. Mitigation: wrap PRAW calls in `asyncio.to_thread(...)` — keeps the rest of the event loop unblocked. Documented in the `_execute_real` method.
- **Reddit rate limits** mid-cycle. Mitigation: semaphore + per-call 1s interval; on 429, PRAW retries internally; on persistent 429, exception → empty ToolResult → joiner continues with empty-evidence per §3.4.
- **Cassette stale** if Reddit response shape drifts. Mitigation: cassette refresh is a manual op documented in `backend/tests/unit/tools/cassettes/README.md` (new, one-page).
- **Schema migration race** with parallel PRs. Mitigation: revision id `20260520_0002` (sequence after initial `0001`) and is the only migration in PR A.

### 4.8 Out of scope (defer)

- Subreddit allow/deny lists beyond the existing `JapanTravel`, `ramen` defaults (in joiner).
- Reddit OAuth refresh tokens (using script-app client credentials only).
- Cache invalidation API / admin endpoint.
- Cache-warming background job.
- Multi-process cache lock (single-worker per ADR-006).

---

## 5. PR B — Xiaohongshu Playwright scraper (3-tier per ADR-003)

### 5.1 Goals

- Implement the **ADR-003-mandated 3-tier fallback** inside `XHSSearchTool._execute_real`:
  - **Tier 1**: live Playwright headless scrape with rotating UA + (future) proxy/cookie hooks.
  - **Tier 2**: DB `tool_cache` lookup (TTL 7d).
  - **Tier 3**: fixture file from `fixtures/xhs/<slug>.json` — same code path as fixture mode, but with `WARN` log `xhs_degraded_to_fixture`.
- `playwright` Python is already in deps (`backend/pyproject.toml:42`). Need `playwright install chromium` step documented; **not** added to CI (real-mode XHS never runs in CI per ADR-003 §"Demo-mode override" and PRD §3.1).

### 5.2 ADR-003 reconciliation

ADR-003 defines L1/L2/L3 in terms of anti-bot (L1 = live, L2 = backup account on captcha, L3 = serve from cache with staleness warning). This PRD's "3-tier" is a slightly different decomposition:

| ADR-003 | PRD Batch 2k tier | Behavior |
|---|---|---|
| L1 default — live scrape | Tier 1 — Playwright | Same. Cache every successful fetch. |
| L1 cache-hit (implicit) | Tier 2 — DB cache | TTL 7d. ADR is silent on TTL; this PRD picks 7d. |
| L2 — backup account + cooldown | **Deferred to v2** | Single account in v1; on captcha, fall straight to Tier 2 then Tier 3. |
| L3 — serve from cache with staleness warning | Tier 3 — fixture fallback | ADR-003 says "from cache"; this PRD says "from fixture" because fixture is the curated demo corpus and cache may be empty/cold for a new query. Acceptable per ADR-003 spirit ("never let user see a hard error"). |

Captured here so reviewers don't flag the divergence. v2 follow-up: backup accounts + residential proxies per ADR-003 §Decision.

### 5.3 Env vars

- `PLUS_ONE_TOOLS_MODE` — same as PR A.
- `XHS_COOKIE` — required when mode=real (single-value JSON-encoded cookie blob, opaque to the app).
- `XHS_USER_AGENT` — optional; defaults to a pinned modern Chromium UA string.
- `XHS_TIMEOUT_S` — optional; default `30`.

`require_env("XHS_COOKIE", tool="xhs_search")` raises at init.

### 5.4 Files to change

**Backend:**
- `backend/src/plus_one/core/tools/xiaohongshu.py` — add `_execute_real` with 3-tier; keep `_execute_fixture` for fixture mode + tier-3.
- `backend/src/plus_one/core/tools/_playwright_session.py` — **new**; thin wrapper that lazily creates a single `Browser` per process via `async_playwright()` and yields fresh `Context`s with UA + cookie injection. Cleanup hook registered with FastAPI lifespan (or, for v1 simplicity, lives for app lifetime and is closed via `atexit`).
- `backend/Dockerfile` (if it exists) — add `RUN playwright install --with-deps chromium` BEHIND an arg `INCLUDE_PLAYWRIGHT_BROWSERS=0` default. v1 sets it to 1 only in a separate `Dockerfile.real-tools` (or compose profile). Image bloat ~500MB — quarantined.

**Tests:**
- `backend/tests/unit/tools/test_xhs_tiers.py` — **new**; mocks all 3 paths. Strategy: patch `_playwright_session.fetch` (raises / returns), patch `_cache_db.get_cached` (None / list), patch `load_json_fixture` (list). Assert correct tier reached + correct WARN logged for tier-3.
- `backend/tests/unit/tools/test_xhs_fixture.py` — keep existing fixture-mode test.

**No CI changes**: e2e and CI keep `PLUS_ONE_TOOLS_MODE` unset → fixture mode → no Chromium needed.

### 5.5 Test plan

All tests use **full mocks** — no live Playwright in CI per ADR-003 §"Demo-mode override". Scenarios:

1. Mode=fixture → bypasses real path entirely → existing fixture test green.
2. Mode=real + Playwright succeeds → Tier 1 hits, cache written.
3. Mode=real + Playwright raises (timeout/captcha) + cache hit → Tier 2 returns cached payload, INFO log `xhs_cache_hit`.
4. Mode=real + Playwright raises + cache miss + fixture present → Tier 3 returns fixture, WARN log `xhs_degraded_to_fixture`.
5. Mode=real + all three fail (no fixture) → returns `[]` (matches existing `load_json_fixture` miss behavior), WARN log `xhs_total_failure`. Tool returns `ToolResult(output=[], notes="degraded")` — joiner handles empty per §3.4.
6. Missing `XHS_COOKIE` in mode=real → `RuntimeError` at tool construction.

### 5.6 Acceptance criteria

1. `pytest` green; all 5 tier scenarios covered.
2. `ruff` + `mypy` clean.
3. e2e and CI green unchanged.
4. With mode=real + valid env (manual dev test), one Tokyo ramen query produces ≥1 XHS post end-to-end OR degrades gracefully to fixture without exception.
5. `xhs_degraded_to_fixture` WARN log structurally appears in the trip's structlog output when tier-3 fires (verifiable via captured log fixture in the test).

### 5.7 Risks + mitigations

- **Chromium image size** — quarantined to `Dockerfile.real-tools` (not the default image). v1 default Docker image unchanged.
- **Anti-bot blocking** — Tier 2/3 absorb the failure; user never sees a hard error. ADR-003 §Decision.
- **Cookie staleness** — when `XHS_COOKIE` expires, every fetch raises; cache TTL still saves recent queries, but new queries degrade to fixture. Mitigation: log `xhs_auth_failed` distinctly so dev can refresh cookie.
- **Per-process Playwright Browser singleton** leaking memory across long-running workers. Mitigation: v1 is single-worker per ADR-006; `atexit` cleanup is sufficient. v2 (multi-worker) will need a proper lifespan hook.
- **Cache key collisions across runs of same query at different times** — by design (cache hit is the point). TTL bounds staleness.

### 5.8 Out of scope (defer)

- Backup accounts + cooldown (ADR-003 L2).
- Residential proxy rotation (ADR-003 §Decision).
- Captcha-detection heuristics beyond "scrape raised".
- Real-time scrape in CI/e2e.
- XHS notification on auth-failed (manual log scan for v1).
- Cache-warming background job.

---

## 6. PR C — Google Places + output language toggle

### 6.1 Goals

- Wire `googlemaps` (Python) behind mode=real for `GooglePlacesSearchTool`.
- Cache in `tool_cache` table with TTL 30d.
- Add a **Translator agent** that runs post-cycle (after `_save_report`) to produce translations of the report's `items[].summary` and any other user-facing strings.
- Persist translations into `Report.content` schema; new shape: `content = {"items": [...], "translations": {"en": {...}, "zh": {...}}}`.
- Frontend toggle (zh / en) reads from `content.translations[<lang>]` with fallback to `content.items` (original) if translation is missing or hasn't run yet (back-compat).

### 6.2 Env vars

- `PLUS_ONE_TOOLS_MODE` — same.
- `GOOGLE_PLACES_API_KEY` — required when mode=real.
- `PLUS_ONE_TRANSLATE_ENABLED` — `"1" | "0"`, default `"1"`. Off-switch in case translation explodes.
- `PLUS_ONE_TRANSLATE_LANGS` — comma-separated, default `"en,zh"`. Future expansion.

Translator uses the existing Maestro/Anthropic plumbing (`llm_factory.get_llm_provider("translator_agent")`) — no new env vars for the LLM itself.

### 6.3 Report content schema design — decision matrix

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A**: `Report.content_en` + `Report.content_zh` (2 new JSONB columns) | Cheap to query each language | Schema migration each time supported langs change; awkward for >2 langs | Reject |
| **B**: `Report.content = {"items": [...], "translations": {"en": {...}, "zh": {...}}}` (keep one column) | No migration to add langs; backwards compatible (old reports just lack `translations` key); cleanest | Slightly larger JSON; one column read returns all langs | **Choose** |
| **C**: New `report_translations` row-per-language table | Normalized; per-lang TTL/regen | Extra join on every render; over-engineered for 2 langs | Reject |

**Choose B.** Migration `20260520_0003_report_content_schema.py` is a documentation-only / no-op DDL migration — the column type and nullability don't change; the schema lives in code (`services/` Pydantic models). For correctness we still ship the migration file as a no-op `upgrade()`/`downgrade()` that contains comments explaining the schema shift (useful for `alembic history` storytelling). **Existing reports**: their `content` stays `{"items": [...]}` with no `translations` key; the frontend's fallback in §6.7 handles this. No backfill required for v1.

### 6.4 Translator agent design

**File:** `backend/src/plus_one/agents/translator.py` — **new**.

**Shape:** Module-level async function `translator(items: list[JoinedItem], src_lang: str, dst_lang: str, ctx: AgentContext) -> list[JoinedItem]`. Returns a translated copy of the items list (does NOT mutate original).

**LLM call shape:**
- Model: `translator_agent` role in `llm_factory` (will be configured as Sonnet — cheaper than Opus; translation doesn't need heavy reasoning). Maestro config update is a one-line addition.
- System prompt (`backend/src/plus_one/agents/prompts/translator/v1.md` — new): `"You are a precise translator. Translate the following item from {src_lang} to {dst_lang}, preserving structure (name, area, classification, summary, evidence quotes). Do NOT add or remove information. Return JSON matching the input schema."`
- `response_model = JoinedItem`.

**Per-item vs batch decision:**

| Option | Cost | Token risk | Latency | Verdict |
|---|---|---|---|---|
| Whole-items-array in one call | Cheapest | May exceed token limits on 30-item reports; one bad item poisons batch | Lowest | Reject |
| Per-item with sequential await | Bounded | Safe | Highest (N calls serialized) | Reject |
| **Per-item with `asyncio.Semaphore(5)`** | Bounded | Safe; one bad item only drops that one (kept-original fallback) | Bounded ~N/5 calls of latency | **Choose** |

**Choose per-item, concurrency 5.** Failed-item fallback: keep the original item under the translated-language key (don't drop). Log `translator_item_failed` WARN per failure.

**Trigger point in `trip_runner.py`:** After `_save_report` returns successfully and BEFORE the `trip_complete` SSE event is published. Specifically:

```
report_id = await _save_report(...)
if get_translate_enabled():
    await _run_translations_and_update(report_id, items)
# then existing final_status + trip_complete event
```

`_run_translations_and_update` opens its own short `session_scope`, re-reads `Report.content`, splices `translations[<lang>]` for each target lang, commits. Failure of the translator does NOT flip the trip to aborted (already saved); it logs `translation_failed` and proceeds. The frontend falls back to original items on missing translations.

Why post-`_save_report` (not as part of it): so the user can see the report at all even if translation fails or times out. Translation is enhancement, not core.

### 6.5 Files to change

**Backend:**
- `backend/pyproject.toml` — add `googlemaps>=4.10.0`.
- `backend/src/plus_one/core/tools/google_places.py` — add `_execute_real` branch using `googlemaps.Client.places(query=, location=, language=)`.
- `backend/src/plus_one/agents/translator.py` — **new**.
- `backend/src/plus_one/agents/prompts/translator/v1.md` — **new**.
- `backend/src/plus_one/services/trip_runner.py` — add `_run_translations_and_update` hook; gate on `PLUS_ONE_TRANSLATE_ENABLED`.
- `backend/src/plus_one/core/llm/factory.py` — add `"translator_agent"` role mapping.
- `backend/alembic/versions/20260520_0003_report_content_schema.py` — **new** (no-op migration with documentation comments; serves as schema-history marker).
- `backend/README.md` — document the language toggle env vars.

**Frontend:**
- `frontend/components/trips/LanguageToggle.tsx` — **new**.
- `frontend/components/trips/ReportView.tsx` — honor toggle; resolve `content.translations[lang] ?? content.items` (fallback for old reports / failed translations).
- `frontend/store/reportPrefs.ts` — add `language: "en" | "zh"` field alongside the existing perspective field from Batch 2i.

**Tests:**
- `backend/tests/unit/tools/test_google_places_real.py` — vcrpy cassette OR full mock of `googlemaps.Client` (lighter — pick mock).
- `backend/tests/unit/agents/test_translator.py` — mock LLM provider; verify per-item invocation, semaphore=5, failed-item fallback.
- `backend/tests/unit/services/test_trip_runner_translations.py` — mock translator; verify `Report.content` post-state includes `translations` keys; verify `PLUS_ONE_TRANSLATE_ENABLED=0` skips entirely.
- `frontend/__tests__/LanguageToggle.test.tsx` — toggle round-trip, persists to `reportPrefs`.
- `frontend/__tests__/ReportView.lang.test.tsx` — renders translated content; falls back to original on missing translation key.
- `e2e/tests/trip-language-toggle.spec.ts` — **new** Playwright spec; fixture trip with both translations; toggle visible; clicking flips text. Reuses `signInE2E` helper from `e2e/helpers/`.

### 6.6 Test plan

- **Unit Places**: cache-miss → mock client called → cache write; cache-hit within 30d → no client call. Missing `GOOGLE_PLACES_API_KEY` in mode=real → `RuntimeError` at init.
- **Unit Translator**: 3-item input → 3 LLM calls (mocked); concurrency: assert peak in-flight ≤ 5 via semaphore introspection; one mocked-failure item → original kept under that lang key; output is a NEW list (not mutated input).
- **Unit Trip Runner**: `PLUS_ONE_TRANSLATE_ENABLED=1` (default) → translator called once with items; `Report.content` after commit contains `translations` with both `en` and `zh` keys. `PLUS_ONE_TRANSLATE_ENABLED=0` → translator not called; `content` unchanged from current shape.
- **Frontend**: language toggle visible on report page; clicking persists to `reportPrefs`; renders new content; fallback path renders original items when `translations` key is absent (use a fixture report with no `translations`).
- **E2E**: new spec triggers fixture trip → completes → toggle flips between zh/en views → assert text content differs. Uses `PLUS_ONE_TOOLS_MODE` unset (fixture mode); translator is mocked in e2e by stubbing the Maestro provider with a deterministic "translated:" prefix transform, OR by pre-loading a Report row whose `content.translations` is hard-coded. Pick pre-loaded fixture (avoids LLM mocking complexity in e2e).

### 6.7 Acceptance criteria

1. `pytest` + `vitest` + Playwright all green.
2. `ruff` + `mypy` clean.
3. With `PLUS_ONE_TOOLS_MODE` unset and `PLUS_ONE_TRANSLATE_ENABLED=1` (default), a new trip end-to-end produces a Report whose `content.translations` has both `en` and `zh` keys.
4. With `PLUS_ONE_TRANSLATE_ENABLED=0`, new trips work exactly as before — `Report.content` has no `translations` key; frontend falls back to original.
5. Old reports (created before this PR) render correctly via fallback path — verified by an explicit test fixture without `translations`.
6. Missing `GOOGLE_PLACES_API_KEY` in mode=real → loud startup error.
7. e2e toggle spec passes — text content visibly differs between zh / en views.
8. Cost-budget sanity: for a ≤30-item report at Sonnet pricing, translation adds < $0.15 per report (manual calc, documented in PR description). PRD §10 budget unaffected.

### 6.8 Risks + mitigations

- **Translation cost** — bounded per §6.7. Off-switch `PLUS_ONE_TRANSLATE_ENABLED=0`. v2: cache translations in DB so regenerated reports don't re-translate.
- **Translation latency** adds ~N/5 LLM-call durations to perceived "trip done" time. Mitigation: trip_complete SSE fires AFTER translation, so the spinner stays until translations land. Document this in PR description.
- **Translator hallucination** (adding/removing info) — system prompt forbids, but no enforcement. v1 accepts this as a translation-quality risk. v2: post-translation diff-check on structural fields (name, area, evidence URLs must be byte-identical or absent).
- **Schema migration is a no-op** — could confuse reviewers. Mitigation: extensive docstring + reviewer note in PR description.
- **Frontend fallback complexity** — three states (no translations key / translations present / partial translations). Mitigation: explicit Vitest cases for all three.
- **Google Places quota** — 30d TTL is aggressive enough to keep call volume low; if quota still exhausted, joiner gets empty → cycle aborts per §3.4.

### 6.9 Out of scope (defer)

- Backfilling translations for existing reports (lazy on-view re-translation is a v2 idea; v1 just falls back).
- Translation cache (translate-once-store-forever across reports of similar content).
- More languages beyond `en` + `zh`.
- Per-card retranslation on user edit.
- Quality-check / diff-against-original guardrail.
- Cost dashboard.
- A/B testing different translator prompts.

---

## 7. Non-goals (whole batch)

- Cities beyond Tokyo (`docs/prd.md` §4 v2).
- Anti-bot beyond random UA + cookie + cache fallback.
- Real-time data freshness guarantees (cache-with-TTL is the contract).
- Cost-tracking dashboard (`docs/prd.md` §10 says "monitor manually for v1").
- Cache invalidation API / admin tooling.
- Out-of-process worker for translator (in-process per ADR-006).

---

## 8. Open questions for team lead

1. **Maestro `translator_agent` role config** — is "Sonnet (cheap path)" the right model choice, or should I look at Haiku for ~10× cost reduction? Need a decision before PR C codes the `factory.py` mapping.
2. **`XHS_COOKIE` storage** — env var (current plan) is fine for dev but plaintext-in-process for prod. Acceptable for v1 single-user demo, or want a secret store integration even now?
3. **Cassette/recording posture for Reddit** — OK to commit cassettes (with sanitized credentials per vcrpy `filter_headers`) to the repo, or should they live out-of-tree? (Current plan: commit them, sanitized.)

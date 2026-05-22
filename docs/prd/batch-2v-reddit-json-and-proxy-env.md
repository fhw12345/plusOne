# Batch 2v — Unauthenticated Reddit JSON + OS-level Proxy Env

Status: draft  •  Author: Plan agent  •  Date: 2026-05-22

## 1. Problem statement

Real-mode evidence fetching is blocked on two unrelated infrastructure facts: (a) Reddit's "Responsible Builder Policy" closed self-serve script-app creation at `/prefs/apps`, so PRAW-based real mode can never be brought up without a manual per-developer approval round; (b) local development in China cannot reach reddit.com or googleapis.com without routing through `http://127.0.0.1:10809`, but Xiaohongshu must stay direct. Both problems vanish if we (1) swap the Reddit tool to the unauthenticated `https://www.reddit.com/r/{sub}/search.json` endpoint (verified working, 200 OK, ~183 KB JSON, ~1.4s through the local proxy) and (2) rely on httpx's built-in honoring of `HTTPS_PROXY` / `NO_PROXY` env vars rather than baking proxy logic into Python.

## 2. Goals

- Reddit tool fetches real data with zero credentials and zero PRAW dependency.
- Local-dev GFW bypass works purely via `HTTPS_PROXY=http://127.0.0.1:10809` and `NO_PROXY=localhost,127.0.0.1,xiaohongshu.com,xhscdn.com` set in `backend/.env`; no code-level proxy logic.
- Production behavior unchanged — VM leaves env vars unset → direct connections everywhere.
- Existing 24h `tool_cache` TTL for Reddit preserved (`_TTL_BY_SOURCE` untouched).
- Return shape (`list[RedditPost]` inside a `ToolResult`) matches existing tool exactly so joiner / classifier / report agents need no changes.

## 3. Non-goals

- Logging into Reddit (no cookies, no OAuth, no login wall workaround).
- Per-host proxy routing inside Python (`HTTPX_MOUNTS`, custom transports, etc.).
- Any change to `xiaohongshu.py` or `google_places.py`.
- Fixing the hardcoded subreddit list at `backend/src/plus_one/agents/joiner.py:142-144` (filed as follow-up §9).

## 4. Acceptance criteria

1. `backend/src/plus_one/core/tools/reddit.py` no longer imports `praw`. The async path uses `httpx.AsyncClient` against `https://www.reddit.com/r/{subs}/search.json?q=…&restrict_sr=1&limit=N&raw_json=1` (and `/r/all/search.json` when `subreddits=()`).
2. `praw>=7.8.0` removed from `backend/pyproject.toml` `dependencies`. `uv.lock` regenerated. No remaining `import praw` anywhere under `backend/`.
3. `require_env()` call for `REDDIT_CLIENT_ID` / `_SECRET` / `_USER_AGENT` removed; only `REDDIT_USER_AGENT` is read, with a default of `plus-one/0.1 (+https://github.com/<owner>/plus-one)` if unset.
4. With `PLUS_ONE_TOOLS_MODE=real` and no Reddit env vars, a search returns real results (verified manually per §8).
5. Unit tests in `backend/tests/unit/tools/test_reddit_real.py` use `httpx.MockTransport` and cover: happy-path parse, empty `data.children`, HTTP 429, HTTP 503, network error (`httpx.ConnectError`), malformed JSON. All failure modes return `ToolResult(ok=True, output=[], notes=...)` — never raise — to preserve joiner's empty-evidence fallback.
6. Optional integration test marked `@pytest.mark.live` hits real Reddit with `query="tonkotsu ramen"`, `subreddits=("JapanTravel",)`, asserts `len(result.output) >= 1` and `result.output[0].title != ""`. Skipped by default.
7. `cache_key(args.query, *sorted(args.subreddits))` derivation unchanged — existing cached rows keep matching.
8. `backend/.env.example` gains a commented block documenting local-dev proxy lines with `# local dev only — unset in production`.
9. Module-level `_REDDIT_SEMAPHORE` (3) and `_rate_limit()` (1.0s min interval) preserved verbatim — same back-pressure story.
10. A new ADR-007 supersedes ADR-003's Reddit clause only (XHS + Google Places clauses unchanged).

## 5. Proposed steps (ordered)

1. **Rewrite real path in `reddit.py`** (~80 LOC delta). Replace `_get_reddit_client`, `_fetch_from_praw_sync` with a single async `_fetch_from_json(query, subreddits, limit)` using `httpx.AsyncClient(timeout=15.0, follow_redirects=True)`. Map the JSON: `data.children[*].data.{id,subreddit,title,selftext,author,score,permalink,created_utc}` → existing dict shape. Use `.get(..., default)` for every field.
2. **Loosen `require_env`** (~3 LOC). Drop the three Reddit env names from the call; keep the function itself for XHS/Places.
3. **Add default User-Agent** (~5 LOC). `os.getenv("REDDIT_USER_AGENT", "plus-one/0.1 (+contact via repo)")`.
4. **Remove `praw` dep** (1 line in `pyproject.toml`; regenerate `uv.lock`).
5. **Rewrite `test_reddit_real.py`** (~120 LOC). Use `httpx.MockTransport` to inject canned JSON; one test per acceptance criterion 5 bullet. Drop any `monkeypatch.setenv("REDDIT_CLIENT_ID", …)` setup.
6. **Add `@pytest.mark.live` integration test** (~20 LOC) — guarded by `pytest -m live`; CI default `-m "not live"`.
7. **Edit `backend/.env.example`** (~6 LOC). Add commented `HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY` block.
8. **Startup warning** (~10 LOC) in `backend/src/plus_one/main.py` lifespan: if `PLUS_ONE_TOOLS_MODE=real` and `HTTPS_PROXY` unset, log `structlog.warning("proxy_env_unset", note="real-mode Reddit/Google may fail outside cloud env")`. Lightweight, OS-agnostic — no China detection.
9. **Write ADR-007** at `docs/adr/ADR-007-reddit-unauthenticated-json.md` superseding ADR-003's Reddit-via-PRAW clause; rationale = Responsible Builder Policy + zero-credential simplicity.
10. **Sanity grep**: `grep -r "import praw" backend/` returns empty.

## 6. Files to modify

| File | Change |
|---|---|
| `backend/src/plus_one/core/tools/reddit.py` | Swap PRAW → httpx; drop required env; default UA; keep semaphore/rate-limit/cache. |
| `backend/pyproject.toml` | Remove `praw>=7.8.0` from `dependencies`. |
| `backend/uv.lock` | Regenerated via `uv lock`. |
| `backend/tests/unit/tools/test_reddit_real.py` | Full rewrite against `httpx.MockTransport`. |
| `backend/tests/integration/test_reddit_live.py` (new) | One `@pytest.mark.live` smoke. |
| `backend/.env.example` | Add commented local-dev proxy block. |
| `backend/src/plus_one/main.py` | Add startup proxy-unset warning in real mode. |
| `docs/adr/ADR-007-reddit-unauthenticated-json.md` (new) | Supersedes ADR-003 Reddit clause. |

## 7. Risks

- **Rate-limiting by IP** (~60 req/min unauth). Mitigation: existing 24h `tool_cache` + low natural QPS + `_REDDIT_SEMAPHORE(3)` + 1.0s `_rate_limit()`.
- **Bot detection on `.json`**. Mitigation: descriptive `User-Agent` honoring Reddit's recommended `app/version (+contact)` shape; `raw_json=1` query param avoids HTML-escape quirks.
- **Schema drift**. Mitigation: defensive `.get()` parsing; any missing field collapses to its `RedditPost` default.
- **GFW miss in local dev**. Mitigation: lifespan log line per §5.8; failures already degrade to empty list (acceptance §5).
- **Cache poisoning across modes**. Old PRAW-shaped rows and new JSON-shaped rows have identical dict keys (we map to the same shape) → safe.

## 8. Validation plan

- Unit: `cd backend && uv run pytest tests/unit/tools/test_reddit_real.py -v` — all green.
- Full suite: `uv run pytest -m "not live"` — no regressions.
- Live smoke (opt-in): `uv run pytest -m live tests/integration/test_reddit_live.py -v`.
- Manual (local, GFW): `HTTPS_PROXY=http://127.0.0.1:10809 NO_PROXY=localhost,127.0.0.1,xiaohongshu.com,xhscdn.com PLUS_ONE_TOOLS_MODE=real uv run uvicorn plus_one.main:app --port 18003` → create Tokyo+ramen trip → logs show `reddit_search_real` populating, place cards no longer all `insufficient`.
- Negative (local, no proxy): same command without `HTTPS_PROXY` → backend startup logs `proxy_env_unset` warning; trip still completes; Reddit results empty; XHS/Places paths unaffected.

## 9. Out-of-scope follow-ups

- Hardcoded subreddit list `backend/src/plus_one/agents/joiner.py:142-144` → destination→subreddit map (~5 LOC fix, separate PR).
- XHS cookie auto-rotation strategy.
- Google Places credential signup task (tracked in `docs/handoff/2026-05-22-real-mode-credentials.md` §3b).
- Bump Reddit cache TTL 24h → 7d in `_cache_db.py::_TTL_BY_SOURCE` if rate-limit pressure shows up in logs.

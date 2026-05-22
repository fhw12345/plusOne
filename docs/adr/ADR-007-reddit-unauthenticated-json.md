# ADR-007: Reddit via unauthenticated `.json` endpoint

## Status

Accepted (2026-05-22). Supersedes the Reddit clause of [ADR-003](./ADR-003-data-sources-strategy.md) only — XHS and Google Places clauses are unchanged.

## Context

- Reddit's 2026 [Responsible Builder Policy](https://www.reddit.com/r/redditdev/comments/1oug31u/) closed self-service script-app creation at `/prefs/apps`. Every new developer must submit an application and wait for manual approval; the wait time is unknown and not committed to by Reddit. Existing apps are grandfathered, but Plus One has none.
- ADR-003 mandates Reddit access via PRAW with `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT`. Under the new policy those credentials cannot be obtained on demand, so real-mode evidence fetching is blocked indefinitely.
- The product needs a working real-tools demo today — "voice of redditors" is the strongest English-language evidence signal in the joiner, and the demo loses credibility without it.
- Empirical test (2026-05-22): `https://www.reddit.com/r/{sub}/search.json?q=...&restrict_sr=1&limit=N&raw_json=1` returns identical post data (id, title, selftext, author, score, permalink, created_utc, num_comments) with no credentials. Verified 200 OK, ~183 KB JSON, ~1.4s through the local proxy, 5 well-formed posts.
- IP-based rate limit on the unauthenticated endpoint is ~60 req/min (vs ~600 req/min for authenticated OAuth). With Plus One's 24h `tool_cache` TTL and `_REDDIT_SEMAPHORE(3)` + 1.0s `_rate_limit()` back-pressure, natural QPS sits well under that ceiling.

## Decision

- The Reddit tool at `backend/src/plus_one/core/tools/reddit.py` fetches via `httpx.AsyncClient` against `https://www.reddit.com/r/{subs}/search.json` (and `/r/all/search.json` when `subreddits=()`). No OAuth, no login.
- Drop the `praw>=7.8.0` dependency from `backend/pyproject.toml`. No `import praw` survives anywhere under `backend/`.
- Drop the `require_env()` requirement for `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`. Only `REDDIT_USER_AGENT` is read, and it has a sane default (`plus-one/0.1 (+contact via repo)`) so real mode runs zero-credential out of the box.
- Preserve the existing 24h `tool_cache` TTL (`_TTL_BY_SOURCE` untouched), module-level `Semaphore(3)`, and 1.0s minimum inter-request interval — same back-pressure story as the PRAW path.
- Graceful degradation: every HTTP error (429, 503, etc.), network error (`httpx.ConnectError`, timeout), and parse error returns `ToolResult(ok=True, output=[], notes=...)` rather than raising. The joiner's existing "insufficient evidence" fallback handles empty results cleanly.
- Defensive parsing: every field read via `.get(..., default)` so schema drift on the unofficial endpoint degrades to default-valued `RedditPost` entries rather than exceptions.
- XHS (Playwright 3-tier scrape with rotating accounts) and Google Places (official API) clauses of ADR-003 are unchanged.

## Alternatives considered

### A. Apply for official Reddit API access via the new approval form
- Pros: Contractually supported; higher rate limit; future-proof.
- Cons: Unknown wait time; blocks shipping; no SLA on approval.
- Why rejected: Cannot commit to a launch date on an external manual-review queue.

### B. Login-cookie scrape via Playwright (XHS-style)
- Pros: Reuses existing scraper infra; survives if Reddit blocks public `.json`.
- Cons: Account-ban risk; brittle DOM; introduces account/cookie rotation ops to a source that doesn't need it today.
- Why rejected: Disproportionate operational cost when an anonymous JSON endpoint works.

### C. Drop Reddit as a source
- Pros: Zero Reddit-related infra.
- Cons: Removes the strongest English-voice evidence signal; weakens the cross-source disagreement story that is the product's core differentiator.
- Why rejected: Reddit voice is load-bearing for the joiner.

### D. Pushshift archive
- Pros: Bulk historical data, no per-request rate limit.
- Cons: Moderator-only since 2023; no public access.
- Why rejected: Not available to us.

## Consequences

### Positive

- Zero-credential Reddit access — no approval blocker, ships today.
- Simpler local-dev onboarding: clone, set `PLUS_ONE_TOOLS_MODE=real`, run.
- Smaller dependency tree (drop `praw` and its transitive deps).
- Failure mode is already first-class in the joiner pipeline (empty list → "insufficient evidence"), so resilience cost is near zero.

### Negative / Trade-offs

- Lower per-IP rate ceiling (~60 req/min vs ~600 OAuth). Mitigated by 24h `tool_cache` + `Semaphore(3)` + 1.0s rate-limit, which keep us well under the ceiling at expected QPS.
- Slightly higher schema-drift risk on the unofficial endpoint. Mitigated by defensive `.get()` parsing and empty-list-on-failure return shape.
- Not contractually supported by Reddit. They may break the endpoint, add a CAPTCHA, or IP-block. If that happens, fall back to the official API approval path (Alternative A) — code change isolated to one tool module.

### Follow-ups

- [ ] If rate-limit pressure appears in logs, bump Reddit `tool_cache` TTL from 24h → 7d in `_cache_db.py::_TTL_BY_SOURCE`.
- [ ] If Reddit blocks the `.json` endpoint, file the Responsible Builder Policy application and reintroduce a PRAW-based path behind the same tool interface.
- [ ] Fix hardcoded subreddit list at `backend/src/plus_one/agents/joiner.py:142-144` (destination → subreddits map) — tracked separately.

## References

- Related ADRs: [ADR-003](./ADR-003-data-sources-strategy.md) (data sources strategy — Reddit clause superseded by this ADR).
- PRD: [`docs/prd/batch-2v-reddit-json-and-proxy-env.md`](../prd/batch-2v-reddit-json-and-proxy-env.md).
- External: [Reddit Responsible Builder Policy announcement](https://www.reddit.com/r/redditdev/comments/1oug31u/).

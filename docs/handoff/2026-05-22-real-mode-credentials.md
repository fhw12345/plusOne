# Handoff — 2026-05-22

> Historical note (2026-05-25): this credential handoff has been superseded.
> Current real mode no longer needs Reddit credentials (ADR-007 uses the public
> JSON endpoint) and no longer uses Google Places (ADR-003 addendum replaced it
> with Foursquare Places plus fixture fallback). Keep this file only as context
> for the debugging path that led to the current implementation.

## Where we are

Plus One has all 8 master-PRD feature gaps closed and verified end-to-end on `feat/batch-2n-destination-autocomplete`. The branch contains 8 batches of feature work (2n through 2u) on top of `main`. **Nothing has been merged to `main` yet**; `feat/batch-2l-scrapbook-reskin` is open as PR #26 (separate concern, do not merge into this branch).

The blocker before continuing real-mode evidence fetching: **need API credentials for Reddit + Google Places + Xiaohongshu**. We tried to sign up via Playwright but Reddit blocked the bot session. You're going to do the signups on another computer using a normal browser.

## What's been verified (don't redo)

All 8 batches have official Code Agent implementations on disk PLUS in-session Playwright/API verification:

| Batch | What it does | Evidence |
|---|---|---|
| 2n | destination autocomplete (offline city dataset) | combobox shows top 8 cities; "ky" → Kyiv, Kyoto |
| 2o | dates + budget on TripForm | round-trip via API: Sapporo with 2026-06-15→18, USD 1500 |
| 2p | per-person match scores | Hakone item shows `match339b64b2: 0.5` |
| 2q | report TL;DR | sticky-note "hakone in a day means picking one onsen…" above tabs |
| 2r | perspective wiring | `resolveClassification` + `categorize(items, perspective)` |
| 2s | privacy export + hard-delete | GET /api/me/export 200; DELETE /api/me cascades; admin self-delete 409 |
| 2t | clarifier loop | Marrakech returned `"when are you thinking of going…"` then clarify→running |
| 2u | conversational refinement | RefinePanel "tweak it" rendered; POST /refine 202 |

PRDs all in `docs/prd/batch-2n-...` through `batch-2u-...`. Read those first on the new machine if you need spec detail.

## Outstanding issue (the reason all evidence-fetch failed in your last test)

`backend/.env` has `PLUS_ONE_TOOLS_MODE=fixture` and the only fixture on disk is `tokyo_ramen_tonkotsu.json`. Every other trip → empty evidence → every item classified `insufficient` (thin signal) → "you only" / "them only" tabs stay empty.

Fix: get real-mode credentials and flip the env.

## What you need to do on the new computer

### 1. Pull the work

```bash
cd /path/to/newproject
git fetch origin
git checkout feat/batch-2n-destination-autocomplete
git pull
```

### 2. Re-create backend/.env from your QQ side

`backend/.env` is gitignored. Recreate it on the new machine. The SMTP + admin block you set up before is below — re-add it. **Get the actual SMTP_PASSWORD (QQ authorization code) from your password manager / 1Password / wherever you stored it** — it's NOT in this repo. It was the 16-char string QQ Mail gave you when you enabled SMTP service at <https://mail.qq.com> → Settings → Account → POP3/IMAP/SMTP.

```
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USE_SSL=true
SMTP_USER=361589927@qq.com
SMTP_PASSWORD=<paste the 16-char QQ authorization code>
SMTP_FROM=361589927@qq.com
SMTP_FROM_NAME=plus one

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
ADMIN_EMAIL=361589927@qq.com         # already promoted in DB; admin can log in

EMAIL_CODE_TTL_MINUTES=10
EMAIL_CODE_LENGTH=6
LOGIN_MAX_FAILED_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15
```

(Plus whatever was there originally — DATABASE_URL, REDIS_URL, JWT_SECRET, MAESTRO_BASE_URL/AUTH_TOKEN, APP_ENV, LOG_LEVEL, PLUS_ONE_TOOLS_MODE.)

If you lost the QQ authorization code, regenerate it: log into mail.qq.com → Settings → Account → POP3/IMAP/SMTP service → close + reopen the service → it'll text your phone a new 16-char code.

### 3. Get the 3 sets of credentials (the real reason you're switching computers)

#### 3a. Reddit — easy

Open <https://www.reddit.com/register/> in your normal Chrome/Edge.

1. Email: `361589927@qq.com`
2. Continue → enter 6-digit code from your inbox
3. Pick username (e.g. `plusone_dev_haowen`) + password
4. Once logged in, go to <https://www.reddit.com/prefs/apps>
5. Scroll to bottom → "are you a developer? create an app..."
6. Fill:
   - name: `plus-one-dev`
   - type: **script** (NOT web app)
   - description: `personal travel research`
   - redirect uri: `http://localhost:8080`
7. Click "create app" → copy:
   - **client_id** (the short string under the app name, ~14 chars)
   - **client_secret** (the longer "secret" string)
8. Note your Reddit username

#### 3b. Google Places — needs billing card

1. Open <https://console.cloud.google.com/>
2. New Project → `plus-one-dev`
3. APIs & Services → Library → enable **Places API (New)** AND **Geocoding API**
4. APIs & Services → Credentials → Create credentials → API key
5. Copy the key (starts with `AIza...`)
6. Recommended: edit the key → restrict to those 2 APIs only
7. Add billing card when prompted ($200/month free credit, you won't be charged for testing)

#### 3c. Xiaohongshu — security-sensitive

**Make a throwaway XHS account first.** Don't use your real one — cookies for automated use can get accounts banned.

1. Sign up at <https://www.xiaohongshu.com/> with a fresh email/phone
2. Log in, don't post anything
3. F12 → Network tab → refresh page → click any xiaohongshu.com request → Request Headers → copy the entire `cookie:` value (long string, hundreds of chars)

⚠️ XHS cookies expire every few days. Plan to re-grab periodically.

### 4. Once you have all 3 (or any subset), append to backend/.env

```
PLUS_ONE_TOOLS_MODE=real

REDDIT_CLIENT_ID=<paste>
REDDIT_CLIENT_SECRET=<paste>
REDDIT_USER_AGENT=plus-one/0.1 by /u/<your_reddit_username>

GOOGLE_PLACES_API_KEY=<paste>

XHS_COOKIE=<paste the full cookie string>
```

If you only have some, leave the others blank. Tools without creds will gracefully return empty results (not crash) — but the cycle still completes via the joiner's "no evidence → insufficient" fallback.

### 5. Restart backend + verify

```bash
# kill old backend on 18003 if any
# then:
cd backend
uv run alembic upgrade head    # safety
uv run uvicorn plus_one.main:app --port 18003 --log-level info
```

Then create a fresh trip (e.g. Tokyo + ramen). Watch backend logs — you want to see `reddit_search_real`, `google_places_search`, `xhs_search_real` lines, NOT `cache_miss` warnings.

## Caching is already wired (you don't need to add it)

Per batch-2k there's a Postgres `tool_cache` table with per-source TTLs:
- Reddit: 24h
- XHS: 7 days
- Google Places: 30 days

First call to a destination hits live APIs + writes cache. Second call within TTL hits DB only. This is the safety/cost story for XHS — repeat trips on the same destination are free + zero scrape risk.

If you want longer TTLs (recommended: Reddit 7d, XHS 30d), edit `backend/src/plus_one/core/tools/_cache_db.py` `_TTL_BY_SOURCE`.

## Known bugs to fix later (NOT urgent)

1. **Hardcoded subreddits.** `backend/src/plus_one/agents/joiner.py:142-144` always queries `r/JapanTravel` + `r/ramen` regardless of destination. A trip to Lisbon should hit `r/portugal` + `r/lisbon`. Five-line fix: pick subreddits from a destination→subreddit map.
2. **`/openapi.json` returns 500.** Pydantic ForwardRef issue in batch-2m admin routes. Doesn't break the app, only `/docs`.
3. **Loose PNG screenshots in repo root.** Added to .gitignore this session. Not committed but visible in `git status`.
4. **Match-line shows person_id prefix.** Currently `match  339b64b2: 0.5`. Should show username once `TripDetail.party` data flow is fully threaded by the 2p+2q agent — actually the official agent now does this, just need a fresh trip with companions to verify.
5. **JWT tokens visible in admin log stream.** `/api/admin/logs/stream` logs request URLs verbatim including `?token=` query params. Mask before any prod use.

## How to bring up the stack on the new computer

```bash
# Postgres (Docker)
docker compose -f infra/docker-compose.yml up -d

# Backend
cd backend && uv run alembic upgrade head
uv run uvicorn plus_one.main:app --port 18003 --log-level info

# Frontend  (in another terminal)
cd frontend && pnpm install
pnpm dev
```

Frontend `.env.local` should contain `NEXT_PUBLIC_API_URL=http://localhost:18003`.

## TODO checklist for the new computer

- [ ] Pull `feat/batch-2n-destination-autocomplete`, install deps (`pnpm install` in frontend, `uv sync` in backend)
- [ ] Recreate `backend/.env` (gitignored — contents above)
- [ ] Sign up Reddit + get client_id / client_secret / username
- [ ] Sign up Google Cloud + enable Places + Geocoding APIs + add billing + get API key
- [ ] Sign up throwaway XHS account + grab cookie
- [ ] Append all 3 credential blocks to `backend/.env`
- [ ] Set `PLUS_ONE_TOOLS_MODE=real`
- [ ] Restart backend
- [ ] Create a fresh trip and confirm evidence populates (place cards show real classifications, not all `thin signal`)
- [ ] Optionally bump cache TTLs in `_cache_db.py`
- [ ] Optionally fix hardcoded-subreddit bug in `agents/joiner.py:142-144`

## Branch state at handoff

- Branch: `feat/batch-2n-destination-autocomplete`
- Off main, ~190 files modified across 8 batches
- All tests passing on disk per Code Agent reports (backend pytest, frontend vitest, typecheck, lint, banned-phrase grep)
- Working tree dirty (not committed) — this handoff includes a commit of everything

## How to find more context

- All 8 PRDs: `docs/prd/batch-{2n,2o,2p,2q,2r,2s,2t,2u}-*.md`
- Master product PRD: `docs/prd.md`
- Architecture notes: `ARCHITECTURE.md`
- Earlier batch PRDs: `docs/prds/batch2{f,g,h,i,j,k}-*.md`

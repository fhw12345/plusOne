# Batch-2M — Auth Revamp + Admin Log Panel

## 1. Background

The current auth path is magic-link only: `/api/auth/request-link` writes a `MagicLinkToken`, the `email.py` "console" sender prints the link to stdout (real SMTP was never wired), and `/auth/exchange` consumes the token to mint a JWT. It works for a quick demo but it is hostile to power users — every sign-in is a round-trip to an inbox, there is no username, no recovery story, and no way to tell two accounts apart. We also have no way to watch the system from the inside: when a frontend bug bites in dev there is no shared place to read browser console output next to the uvicorn log.

This batch replaces magic-link entirely with real credential auth (username + password OR email + 6-digit code), wires real SMTP for verification + login codes, seeds a pre-verified admin row, and adds a read-only admin "wire" page that live-tails the backend logger and any browser console events admins choose to post up. After this batch ships, magic-link code paths must be gone — the routes, the email console sender, the `/login` link form, and the `/auth/exchange` page all delete.

Everything user-facing stays in the existing scrapbook voice — lowercase, em-dashes, ellipses ok, no exclamation marks, no status-pill nouns, no "Submitting…" / "Loading…" / "Powered by AI".

## 2. Goals

- Replace magic-link with username + password + 6-digit email-code login.
- Require email verification before first login (except for the seeded admin).
- Wire real SMTP (Gmail/QQ) using existing `SMTP_*` env vars.
- Seed an admin user on first boot so the admin log panel is reachable without bootstrap dance.
- Ship an admin-only `/admin/logs` "the wire" page — SSE-driven live tail of backend + frontend console.
- Keep the scrapbook voice everywhere, including errors.
- Lock down brute-force: lockout after 5 bad password attempts, 1/60s rate-limit on code requests.

## 3. Non-Goals

- Password reset / forgot-password flow.
- Account deletion.
- Social login / OAuth.
- MFA / 2FA / TOTP.
- Admin user management (no list-users, no ban, no impersonate, no kill-sessions).
- Persistent log storage (in-memory ring buffer only — cleared on backend restart).
- Redis-backed rate-limit storage (in-process counters for this batch).
- Admin password-rotation UI.
- JWT refresh tokens.

## 4. User Stories

1. **new user registers** — types username, email, password, confirms password, hits "save the page", lands on `/verify` with email pre-filled.
2. **user verifies email** — opens inbox, copies the 6-digit code, pastes it, hits "let me in", lands on `/app` logged in.
3. **user logs in with password** — visits `/login`, picks the "password" tab, types username-or-email + password, hits "let me in", lands on `/app`.
4. **user requests an email code and logs in with it** — visits `/login`, picks the "by code" tab, types email, hits "send me a code", types the 6-digit code, hits "let me in", lands on `/app`.
5. **admin logs in and views the wire** — signs in as `admin` / `admin`, opens `/admin/logs`, sees a two-pane live tail with backend on the left and frontend on the right.
6. **user signs out** — hits the existing sign-out control, JWT is cleared from the zustand store + cookie, lands on `/`.

## 5. Data Model

### `users` table (modify)

Columns to **ADD**:

| column                    | type           | notes                                                                 |
|---------------------------|----------------|-----------------------------------------------------------------------|
| `username`                | text           | NOT NULL, UNIQUE. 3-32 chars, matches `^[a-z0-9_]+$`.                 |
| `password_hash`           | text           | NOT NULL. Argon2id-encoded hash (PHC string format).                  |
| `is_admin`                | bool           | NOT NULL, default false.                                              |
| `email_verified_at`       | timestamptz    | nullable. Set on successful `POST /api/auth/verify`.                  |
| `failed_login_attempts`   | int            | NOT NULL, default 0. Reset on successful login or after lockout ends. |
| `locked_until`            | timestamptz    | nullable. While `> now()` the account is locked.                      |

Columns to **KEEP**: `id`, `email`, `is_active`, `created_at`, and any other existing audit columns.

Constraints:
- `email` continues to be `UNIQUE` and lowercased on write (email_validator normalized form).
- `username` is stored lowercase. The migration must enforce this.

### `email_codes` table (NEW)

| column        | type        | notes                                                                  |
|---------------|-------------|------------------------------------------------------------------------|
| `id`          | uuid        | PRIMARY KEY, default `gen_random_uuid()`.                              |
| `email`       | text        | NOT NULL. INDEX on `(email)`.                                          |
| `code_hash`   | text        | NOT NULL. Argon2id hash of the 6-digit code.                           |
| `purpose`     | text        | NOT NULL. CHECK (`purpose IN ('verify_email', 'login')`).              |
| `expires_at`  | timestamptz | NOT NULL. `now() + interval '10 minutes'`.                             |
| `consumed_at` | timestamptz | nullable. Set on consume; row not deleted (audit trail in dev memory). |
| `created_at`  | timestamptz | NOT NULL, default `now()`.                                             |

Indexes:
- `ix_email_codes_email` on `(email)`.
- `uq_email_codes_active` UNIQUE on `(email, purpose) WHERE consumed_at IS NULL` — enforces "one active code per (email, purpose)". Re-requesting must first mark the previous row `consumed_at = now()` before inserting the new one.

### `magic_link_tokens` table — **DROP**

The Alembic migration drops the table and any associated indexes/sequences.

### Alembic migration

A single revision (filename: `xxxx_batch_2m_auth_revamp.py`) that, in order:

1. Adds the new columns to `users` (all nullable first, then backfill, then NOT NULL where required).
2. Creates `email_codes` with its indexes.
3. Drops `magic_link_tokens` (with `op.drop_table`).
4. Does **NOT** seed the admin row. Migrations stay env-free and idempotent.

Admin seeding is done at app startup via `ensure_admin_user()` called from the FastAPI lifespan (see § 6 / § 10). It is a no-op if a user with `email = ffffhhhww@qq.com` already exists. Constants used by the seeder:
- `username = "admin"`
- `email = "ffffhhhww@qq.com"`
- `password = "admin"` (hashed with Argon2id at boot)
- `is_admin = True`
- `email_verified_at = now()` (pre-verified — admin can log in on first boot)

## 6. API Surface

All routes live under `/api/auth` and `/api/admin`. JSON in, JSON out, `application/json`. Errors return `{"detail": "..."}` matching existing FastAPI conventions.

### Auth (REPLACES `/api/auth/*`)

**DELETE these existing routes** and the code that backs them:
- `POST /api/auth/request-link`
- `POST /api/auth/exchange`
- `GET  /api/auth/dev/last-link`

Also delete: `plus_one/core/auth/email.py` (console sender), `plus_one/core/auth/tokens.py` (magic-link issue/consume), the `MagicLinkToken` model, and any references to them.

**Keep**: `POST /api/auth/logout`, `GET /api/auth/me`. `me` is extended to return `is_admin`.

**ADD**:

#### `POST /api/auth/register`

Body:
```json
{ "username": "string", "email": "string", "password": "string" }
```

Behavior:
- Validates `username` against `^[a-z0-9_]{3,32}$`. Lowercases input.
- Validates `email` via `email_validator` (same `test_environment=True` shim as today).
- Validates `password`: length >= 10, contains at least one letter (`[A-Za-z]`) AND at least one digit (`\d`). No other complexity rules.
- 409 if a user with that `email` exists. 409 if a user with that `username` exists.
- On success: insert user (`email_verified_at = NULL`, `is_admin = false`), Argon2id-hash the password, issue a fresh `verify_email` code, send it via SMTP, return 201:
  ```json
  { "user_id": "uuid", "email": "string" }
  ```
- 400 on weak password / invalid username / invalid email.

#### `POST /api/auth/verify`

Body: `{ "email": "string", "code": "string" }`.

Behavior:
- Looks up the active `verify_email` code for `email`. Compares `argon2.verify(code_hash, code)`.
- On match: set `consumed_at = now()` on the code row, set `email_verified_at = now()` on the user, return:
  ```json
  { "access_token": "jwt", "token_type": "bearer", "expires_in_minutes": 60, "user": { "id": "...", "email": "...", "username": "...", "is_admin": false } }
  ```
- Also sets the same JWT in the existing httpOnly cookie (keep parity with current exchange handler).
- 400 if code expired / wrong / consumed / no active code.

#### `POST /api/auth/login`

Body: `{ "identifier": "string", "password": "string" }`. `identifier` is either a username OR an email — the handler detects which (presence of `@` is sufficient).

Behavior:
- Look up user by `email == identifier.lower()` OR `username == identifier.lower()`.
- If `locked_until > now()`: return 423 (Locked).
- If user not found OR password mismatch: increment `failed_login_attempts`. If it hits 5: set `locked_until = now() + interval '15 minutes'` and `failed_login_attempts = 0`. Return 401 in either case (do not reveal which user was missed).
- If user is found and password matches BUT `email_verified_at IS NULL`: return 401 with detail `"email_not_verified"` so the frontend can route to `/verify`.
- On success: reset `failed_login_attempts` and `locked_until`, mint JWT, return same shape as `/verify`.

The 5-attempt counter applies to attempts against a **resolved user row** — random unknown identifiers do not increment any counter (otherwise you could lock out anyone). Unknown-identifier attempts still return 401 with the same "wrong password or unknown name" body for non-enumeration.

#### `POST /api/auth/request-code`

Body: `{ "email": "string" }`.

Behavior:
- Rate-limit: per-email in-process counter, **1 request per 60 seconds**. If exceeded: still return 204 (do not leak), but skip sending. Log the throttle event at WARN.
- If a user with that email exists AND `email_verified_at IS NOT NULL`: invalidate the previous active `login` code (set `consumed_at = now()`), insert a new code, send it via SMTP.
- If the user does not exist OR is unverified: do nothing, still return 204 (no enumeration).
- Always returns `204 No Content`.

#### `POST /api/auth/login-with-code`

Body: `{ "email": "string", "code": "string" }`.

Behavior:
- Find the active `login` code for `email`. Verify Argon2id hash.
- The user must exist AND have `email_verified_at IS NOT NULL`. Otherwise 401.
- On match: consume the code (`consumed_at = now()`), reset `failed_login_attempts` + `locked_until`, mint JWT, return same shape as `/verify`.
- 400 if code expired/wrong/consumed/missing.

#### `GET /api/auth/me`

Same handler shape as today, but the response now includes `username` and `is_admin`:
```json
{ "id": "uuid", "email": "string", "username": "string", "is_admin": false }
```

### Admin (NEW)

All admin routes require a valid JWT **and** `is_admin = true`. Otherwise return 403.

#### `GET /api/admin/logs/stream`

Server-Sent Events. `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`.

Each event:
```
event: log
data: {"ts":"2026-05-21T12:34:56.789Z","level":"INFO","source":"backend","message":"...","logger":"uvicorn.access"}
```

- On connect: replay the last 1000 entries from the ring buffer in order, then stream new entries as they arrive.
- Heartbeat: every 15 seconds, send a `: heartbeat\n\n` comment line so proxies don't hang up.
- Disconnect cleanly when the subscriber's queue is GC'd.

#### `POST /api/admin/logs/frontend`

Body:
```json
{
  "entries": [
    { "ts": "2026-05-21T12:34:56.789Z", "level": "log|info|warn|error", "message": "string" }
  ]
}
```

Behavior:
- Admin-only (403 otherwise).
- Body size limit: **4 KB** total request body. Reject 413 if exceeded.
- Batch size limit: **50 entries** per call. Reject 422 if more.
- Per-session rate-limit: **50 requests per second** (in-process token bucket keyed by user_id). Excess returns 429.
- Each entry is pushed into the same in-memory ring buffer as backend logs, tagged `source = "frontend"`.
- Returns 204.

## 7. Logging Architecture

Single module: `plus_one/core/logging/admin_tail.py`.

```
            ┌──────────────────────────┐
 backend ──▶│  AdminTailHandler        │──┐
 logger    │  (logging.Handler)        │  │
            └──────────────────────────┘  │
                                          ▼
 POST /api/admin/logs/frontend ────▶ ring_buffer (deque, maxlen=1000)
                                          │
                                          ▼
                                  fan-out to subscribers
                                  (each = asyncio.Queue)
                                          │
                                          ▼
                              GET /api/admin/logs/stream (SSE)
```

Components:
- `LogEntry` dataclass: `ts: datetime`, `level: str`, `source: Literal["backend","frontend"]`, `message: str`, `logger: str | None`. Serialised with `model_dump_json` (pydantic v2) or a hand-rolled `to_json`.
- `_RING: collections.deque[LogEntry]` with `maxlen=1000`. Single shared instance.
- `_SUBSCRIBERS: set[asyncio.Queue[LogEntry]]`. `subscribe()` / `unsubscribe()` helpers.
- `push(entry)`: append to `_RING`, then `put_nowait` to every subscriber queue. If a queue is full (per-subscriber `maxsize=500`), drop the oldest by popping then putting (best-effort).
- `AdminTailHandler(logging.Handler)`: in `emit()`, build a `LogEntry(source="backend")` and call `push()`. Attached to the root logger AND to `uvicorn`, `uvicorn.access`, `uvicorn.error`, `sqlalchemy.engine` (level WARNING for sqlalchemy to keep volume sane).
- A `SecretRedactingFilter` is installed on the same handler. It scrubs values matching keys: `SMTP_PASSWORD`, `JWT_SECRET`, `password`, `password_hash`, `code`, `code_hash`, `access_token`, `Authorization`. Match is case-insensitive, on JSON-ish substrings (`"key": "value"`, `key=value`). The replacement is `***redacted***`. Raw codes must **never** appear in log output.
- All buffer state is process-local and resets on restart. Documented in the panel UI.

## 8. Frontend Changes

### Pages

**DELETE**:
- `frontend/app/login/page.tsx` (the send-the-link form — replaced).
- `frontend/app/auth/exchange/page.tsx` (no more magic-link exchange).
- `frontend/lib/api/auth.ts` references to `requestLink` / `exchange` — replace with the new client functions below.

**NEW pages** — all use the existing scrapbook substrate (`shell`, `crest`, `hand-xxl`, `scrawl`, `annot`, `btn`, `tape`, `field` classes, paper-2 backgrounds, tape decorations, slight rotations).

#### `/register` — "save your page"
- Heading: `save your page`
- Sub (`scrawl`): `username, email, a password. that's it.`
- Fields:
  - `username` (text, autocomplete=username, hint: `lowercase, letters and numbers. 3 to 32.`)
  - `your email` (email, autocomplete=email, hint: `i'll send a code here. no marketing, no resale.`)
  - `password` (password, autocomplete=new-password, hint: `at least 10. one letter, one number. that's the floor.`)
  - `say it again` (password, autocomplete=new-password, hint: `just to be sure.`)
- CTA: `save the page` (disabled state text: `saving…`)
- On 201: `router.push('/verify?email=' + encoded)`.
- Inline error mapping — see § 8 Voice copy / Errors.

#### `/verify` — "check your inbox"
- Heading: `check your inbox`
- Sub (`scrawl`): `we sent a six-digit code. it's good for ten minutes.`
- Read email from `searchParams.email` and render it small as `annot` text: `sent to friend@somewhere.com`.
- One input: 6-digit code (`inputMode="numeric"`, `autoComplete="one-time-code"`, `maxLength=6`, hint: `just the numbers.`).
- CTA: `let me in` (busy: `letting you in…`)
- Below CTA: `link-hand` button `resend the code` — calls `POST /api/auth/request-code` (purpose handled server-side by route; for register flow specifically, the frontend calls a small wrapper `/api/auth/register-resend` — see note). Disabled for 60s after click, copy when disabled: `hold on… (NN)` where NN counts down.
  - **Note for code agent**: there is no separate register-resend route. The frontend calls `POST /api/auth/register` again with the same body? No — that would 409. Instead, the **backend** `POST /api/auth/request-code` is amended so that for a user whose `email_verified_at IS NULL`, it sends a `verify_email` code instead of a `login` code. This is the only purpose-selection branch in `request-code`. Document this branching clearly in the route docstring.
- On success: store session via existing `setSession`, `router.push('/app')`.

#### `/login` — "let me in"
- Heading: `let me in`
- Sub (`scrawl`): `password, or a code. your call.`
- Segmented control (two tabs, no radio nouns — just two `btn` styled toggles): `password` | `by code`.
- **password tab**:
  - Field 1: `name or email` (text, autocomplete=username, hint: `whichever you remember.`)
  - Field 2: `password` (password, autocomplete=current-password)
  - CTA: `let me in` (busy: `letting you in…`)
- **by code tab**, two phases:
  - Phase A — request:
    - Field: `your email` (email, autocomplete=email)
    - CTA: `send me a code` (busy: `sending…`)
    - On 204: switch to phase B, show `sent to friend@somewhere.com` as `annot`.
  - Phase B — submit:
    - Field: 6-digit code (same input shape as `/verify`)
    - CTA: `let me in`
    - `link-hand`: `send another one` (rate-limit aware: shows `hold on… (NN)`)
- On either success: `setSession`, `router.push('/app')`.

#### `/admin/logs` — "the wire (admin)"
- Heading: `the wire (admin)`
- Sub (`annot`): `live. last 1000. clears on restart.`
- Two columns (CSS grid `1fr 1fr` with 18px gap, each column has its own paper-2 background + kraft border + slight rotation `-0.3deg` / `0.3deg`).
  - Left column header: `backend`
  - Right column header: `frontend`
- Each row: monospaced `ts` (HH:mm:ss.SSS), level chip (color by level), message. NO "status" pills — color via existing kraft/mint/yellow/red tokens.
  - Color mapping: DEBUG → muted ink, INFO → ink, WARN → kraft, ERROR → red.
- Top-right controls (small `link-hand` buttons):
  - `hold the page` (when running) / `let it run` (when paused) — pauses auto-scroll AND incoming-row rendering for that pane; queued rows still buffer up to 1000 and flush on resume.
  - `clear the page` — client-side only, empties the visible list. Does NOT clear the server ring.
- Connect via `EventSource("/api/admin/logs/stream", { withCredentials: true })`.
- Render strategy: keep the last 1000 entries per pane in state. Virtualise only if perf demands it (post-batch follow-up).

### Auth store changes (`frontend/store/auth.ts`)

- Extend the `User` type:
  ```ts
  type User = { id: string; email: string; username: string; is_admin: boolean };
  ```
- No new methods. The existing `setSession(token, user)` / `clearSession()` handle the new shape.

### API client (`frontend/lib/api/auth.ts`)

Replace the existing exports with:
- `register(body: { username; email; password }): Promise<{ user_id; email }>`
- `verify(body: { email; code }): Promise<TokenResponse>`
- `login(body: { identifier; password }): Promise<TokenResponse>`
- `requestCode(body: { email }): Promise<void>` — returns nothing, 204 expected.
- `loginWithCode(body: { email; code }): Promise<TokenResponse>`
- `me(): Promise<MeResponse>` — extend the existing type.

Where `TokenResponse = { access_token: string; token_type: string; expires_in_minutes: number; user: User }`.

### Browser log capture (`frontend/lib/admin/console-tap.ts` — NEW)

Behavior:
- Module exports `installAdminConsoleTap(user)`. Called once from a `useEffect` in the top-level app shell.
- If `!user || !user.is_admin`: return immediately. Never wraps console for non-admins.
- If admin: wraps `console.log` / `console.info` / `console.warn` / `console.error` ONCE (guard with `Symbol.for("plusOne.adminTap")`). Wrappers call the original, then push `{ ts: new Date().toISOString(), level, message }` into a client-side ring (size 200) where `message` is `args.map(serialize).join(" ")`.
  - `serialize`: strings pass through; non-strings via `JSON.stringify` with a circular-safe replacer. Truncate each message to 2000 chars.
- Flushing:
  - Every 1000 ms, if the client ring is non-empty, POST up to 50 entries to `/api/admin/logs/frontend` and drop them from the ring on success.
  - For `level === "error"`: flush immediately (don't wait for the 1s tick).
- On unmount (or when the user clears session): un-wrap (restore originals) and clear the ring.
- Network failures on the POST are swallowed silently — never spam the console (we are the console).

### Voice copy table (exact strings to use)

| Surface                                       | Copy                                                                          |
|-----------------------------------------------|-------------------------------------------------------------------------------|
| `/register` heading                           | `save your page`                                                              |
| `/register` sub                               | `username, email, a password. that's it.`                                     |
| `/register` username label                    | `username`                                                                    |
| `/register` username hint                     | `lowercase, letters and numbers. 3 to 32.`                                    |
| `/register` email label                       | `your email`                                                                  |
| `/register` email hint                        | `i'll send a code here. no marketing, no resale.`                             |
| `/register` password label                    | `password`                                                                    |
| `/register` password hint                     | `at least 10. one letter, one number. that's the floor.`                      |
| `/register` confirm label                     | `say it again`                                                                |
| `/register` confirm hint                      | `just to be sure.`                                                            |
| `/register` CTA                               | `save the page`                                                               |
| `/register` CTA busy                          | `saving…`                                                                     |
| `/verify` heading                             | `check your inbox`                                                            |
| `/verify` sub                                 | `we sent a six-digit code. it's good for ten minutes.`                        |
| `/verify` code label                          | `the code`                                                                    |
| `/verify` code hint                           | `just the numbers.`                                                           |
| `/verify` CTA                                 | `let me in`                                                                   |
| `/verify` CTA busy                            | `letting you in…`                                                             |
| `/verify` resend link                         | `resend the code`                                                             |
| `/verify` resend cooldown                     | `hold on… ({n})`                                                              |
| `/login` heading                              | `let me in`                                                                   |
| `/login` sub                                  | `password, or a code. your call.`                                             |
| `/login` password tab                         | `password`                                                                    |
| `/login` code tab                             | `by code`                                                                     |
| `/login` identifier label (password tab)      | `name or email`                                                               |
| `/login` identifier hint                      | `whichever you remember.`                                                     |
| `/login` password label                       | `password`                                                                    |
| `/login` password CTA                         | `let me in`                                                                   |
| `/login` password CTA busy                    | `letting you in…`                                                             |
| `/login` code request label                   | `your email`                                                                  |
| `/login` code request CTA                     | `send me a code`                                                              |
| `/login` code request busy                    | `sending…`                                                                    |
| `/login` code submit CTA                      | `let me in`                                                                   |
| `/login` resend link                          | `send another one`                                                            |
| `/admin/logs` heading                         | `the wire (admin)`                                                            |
| `/admin/logs` sub                             | `live. last 1000. clears on restart.`                                         |
| `/admin/logs` backend pane                    | `backend`                                                                     |
| `/admin/logs` frontend pane                   | `frontend`                                                                    |
| `/admin/logs` pause (running)                 | `hold the page`                                                               |
| `/admin/logs` pause (paused)                  | `let it run`                                                                  |
| `/admin/logs` clear                           | `clear the page`                                                              |
| Cross-page footer (existing)                  | leave existing footer copy untouched                                          |

Voice for errors (use these exact strings):

| Condition                                          | Copy                                                          |
|----------------------------------------------------|---------------------------------------------------------------|
| 401 on `/login` (wrong creds OR unknown user)      | `wrong password or unknown name. try again?`                  |
| 401 on `/login` with `email_not_verified`          | `your email's still unread. go check the code we sent.`       |
| 423 on `/login`                                    | `you've tried too many times. wait 15 minutes.`               |
| 409 on `/register` — email taken                   | `that email's already in the book.`                           |
| 409 on `/register` — username taken                | `that username's taken.`                                      |
| 400 on `/register` — weak password                 | `password needs ten characters and a number. one more pass?`  |
| 400 on `/register` — bad username                  | `username's lowercase, letters and numbers, three to thirty-two.` |
| 400 on `/register` — bad email                     | `that email doesn't look right. typo?`                        |
| 400 on `/verify` — wrong/expired code              | `the code didn't match. try again?`                           |
| 400 on `/verify` — expired specifically            | `your code timed out. one more time?`                         |
| 400 on `/login-with-code` — wrong code             | `the code didn't match. try again?`                           |
| 503 / network on email send                        | `the inbox door is shut on our end right now. give it a minute and try again.` |
| Generic network / unknown                          | `something snagged on the wire. one more try?`                |
| Resend within cooldown (frontend-side guard)       | `hold on a sec — i just sent one.`                            |

**Banned phrases** (do not appear in any new code): `Submit`, `Submitting…`, `Loading…`, `Powered by AI`, `Our`, status nouns (`Status`, `Pending`, `Success`, `Failure` as user-facing labels), `Login` (use `let me in`), `Logout` (use existing `sign out` if any), `Register` (use `save the page`).

## 9. Email Templates

Two templates, identical body, different subject. From: `{SMTP_FROM_NAME} <{SMTP_FROM}>`. Sent via the new `plus_one/core/auth/smtp.py` module which uses `aiosmtplib` (already a transitive dep of `email-validator`? — if not, add to `pyproject.toml`).

### Plaintext

**Subject** (both templates): `your code, pinned`

**Body**:
```
hello —

here's the code: {CODE}

it's good for 10 minutes. one use, then it's gone.

if this wasn't you, ignore this — nothing happens until someone types it in.

— plus one
```

### HTML

Wrap the same copy in a minimal template — paper-2 background, kraft border, the code rendered large + monospaced. No images, no tracking pixels. Multipart/alternative with plaintext as the fallback.

```html
<!doctype html>
<html><body style="background:#f5efe1;color:#221c14;font-family:Georgia,serif;padding:24px;">
  <p>hello —</p>
  <p>here's the code:</p>
  <p style="font-family:'Courier New',monospace;font-size:32px;letter-spacing:6px;padding:14px 18px;background:#faf5e9;border:1px dashed #b09472;display:inline-block;">{CODE}</p>
  <p>it's good for 10 minutes. one use, then it's gone.</p>
  <p style="color:#7a6a52;font-size:13px;">if this wasn't you, ignore this — nothing happens until someone types it in.</p>
  <p>— plus one</p>
</body></html>
```

## 10. Security Notes

- **Password hashing**: `argon2-cffi` `PasswordHasher` with `time_cost=3`, `memory_cost=65536`, `parallelism=4`, `hash_len=32`, `salt_len=16`. Use the library default (PHC string format) — do not custom-serialise.
- **Code hashing**: same `PasswordHasher` instance is fine for 6-digit codes (Argon2id remains safe at low entropy because of the rate-limit + lockout + 10-min TTL + single-use guarantees). Compare via `verify`.
- **Never log raw codes or passwords**. The `SecretRedactingFilter` (see § 7) covers backend; the frontend tap never inspects form values.
- **JWT**: existing `create_access_token(user.id)` unchanged. TTL stays 60 min via `settings.jwt_ttl_minutes`. Refresh is out of scope.
- **SMTP**: read credentials from env at app startup. Use SSL (`port=465`, `use_tls=True`). Never log `SMTP_PASSWORD`. If SMTP send raises: return 503 from the originating route with `detail="email_sender_unavailable"` and copy `the inbox door is shut on our end right now. give it a minute and try again.`
- **Admin guard**: a single `require_admin` dependency. 403 for any non-admin caller of `/api/admin/*`.
- **SSE**: response headers MUST include `X-Accel-Buffering: no` and `Cache-Control: no-cache`. Heartbeat every 15s. Subscriber queue maxsize 500 — drop oldest on overflow.
- **POST size**: `/api/admin/logs/frontend` enforces 4 KB body limit (FastAPI dependency that reads `Content-Length` and 413s if over).
- **Rate-limits** (all in-process, single-replica deployment assumption):
  - `request-code`: 1 per 60s per email (purpose-agnostic).
  - `/api/admin/logs/frontend`: 50 req/sec per user_id.
  - Login: 5-attempt lockout per user, 15-min window.
- **CORS**: unchanged. Cookie + Bearer continue to coexist.
- **Admin password rotation**: the seeded `admin / admin` credential is acceptable **for local dev only**. This is a follow-up before any deployment beyond a developer machine — see § 11.
- **Migration safety**: the migration is reversible (`downgrade()` recreates `magic_link_tokens` schema and drops new columns). Downgrade does NOT need to restore data — magic-link is dead.
- **`ensure_admin_user()`**: idempotent — on each boot, checks for a user with `email = ffffhhhww@qq.com`. If absent, insert with Argon2id-hashed `"admin"`, `is_admin=true`, `email_verified_at=now()`. If present, do nothing (don't reset the password). Log at INFO: `admin user ensured` or `admin user already present`.

## 11. Out of Scope / Follow-Ups

- Password reset (email-link or code-based) — separate batch.
- Account deletion / soft-delete flow.
- Social login (Google / GitHub / WeChat).
- MFA / TOTP / WebAuthn.
- Admin user management UI (list users, edit roles, ban, impersonate, kill sessions).
- Log persistence beyond the in-memory ring (Loki / OpenSearch / file rotation).
- Rate-limit backing store migration to Redis (for multi-replica).
- **Rotate the admin password** before any non-local deployment. Track as a P0 follow-up.
- JWT refresh tokens / sliding sessions.
- Email i18n (currently English-only voice).
- Webhook to ship logs out of process.

## 12. Acceptance Criteria

All testable; each is the basis of one or more Playwright/pytest cases.

1. `POST /api/auth/register` with a valid `{username, email, password}` returns **201** with `{user_id, email}`, persists the user with `email_verified_at = NULL`, hashes the password with Argon2id, and triggers an SMTP send containing a 6-digit code.
2. `POST /api/auth/verify` with the correct code returns **200** with `{access_token, user}`, sets `users.email_verified_at`, and marks the code `consumed_at`.
3. `POST /api/auth/login` with the right password returns **200 + token**; with the wrong password returns **401**; **5** wrong attempts on the same user returns **423** and sets `locked_until`. After 15 simulated minutes (test clock), the user can attempt again.
4. `POST /api/auth/login` with valid creds but `email_verified_at IS NULL` returns **401** with `detail="email_not_verified"`.
5. `POST /api/auth/request-code` rate-limited at **1 per 60s per email**: the second call within 60s still returns 204 but no second email is sent (verified via SMTP mock call count).
6. `POST /api/auth/login-with-code` with a valid `login` code returns **200 + token**; consumes the code; rejects re-use with 400.
7. `request-code` for a user whose `email_verified_at IS NULL` sends a `verify_email` code (purpose branch) — not a `login` code.
8. The seeded admin (`username=admin`, `password=admin`, `email=ffffhhhww@qq.com`) can log in via `POST /api/auth/login` on a fresh database boot WITHOUT going through `/verify`. `ensure_admin_user()` is idempotent across multiple restarts.
9. `GET /api/admin/logs/stream` returns **403** for a non-admin user, **200** `text/event-stream` for an admin. Heartbeat lines arrive at most 15s apart.
10. `POST /api/admin/logs/frontend` is **403** for non-admins, **204** for admins. A 4 KB+ body returns 413; a 51-entry batch returns 422.
11. The `/admin/logs` page renders two live panes that update in real time when (a) the backend logs a line, (b) the frontend taps a `console.error`. Color-coding matches the level mapping in § 8.
12. Magic-link routes are gone: `POST /api/auth/request-link`, `POST /api/auth/exchange`, `GET /api/auth/dev/last-link` all 404. The `magic_link_tokens` table no longer exists. `MagicLinkToken` model and `core/auth/tokens.py` + `core/auth/email.py` (the console sender) are deleted from the tree.
13. Frontend page `/auth/exchange` is deleted; navigating to it serves a Next.js 404.
14. Frontend tests cover: `/register` form validation (all four field errors), `/login` both tabs happy + sad paths, `/verify` form happy + wrong-code, `/admin/logs` renders both panes and the SSE EventSource is created with `withCredentials: true`.
15. No banned phrases (`Submit`, `Submitting…`, `Loading…`, `Powered by AI`, `Our`, status nouns, `Login`, `Register`) appear in any new or modified file under `frontend/app/(register|verify|login|admin)/**` or `frontend/lib/admin/**`. Enforced by a grep-based unit test.
16. Secret-redacting log filter scrubs `SMTP_PASSWORD`, `JWT_SECRET`, `password`, `password_hash`, `code`, `code_hash`, `access_token`, `Authorization` from any line emitted through the admin-tail handler. Verified with a unit test.
17. `typecheck` (tsc), `lint` (eslint + ruff), `pytest backend`, and `vitest frontend` all pass on the resulting branch.

## 13. Open Questions

_(none — all decisions locked above.)_

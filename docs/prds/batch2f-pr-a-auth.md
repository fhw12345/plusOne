# Batch 2f PR A — Auth Surface + Real E2E Coverage

**Owner:** Frontend  
**Branch:** `feat/batch2f-pr-a-auth` (already cut from clean `main`)  
**Status:** PRD (revised after team-lead pre-commit `29daa08`)  
**Date:** 2026-05-19

> **Revision note (2026-05-19):** Team-lead pre-committed `frontend/e2e/app-shell.spec.ts`
> (3 green tests), `frontend/e2e/auth-login-page.spec.ts` (3 `test.fixme`), and
> `frontend/e2e/auth-flow.spec.ts` (1 `test.fixme`) in commit `29daa08`. Those
> files are now **frozen contracts**: Code Agent activates the fixmes by removing
> `.fixme` and must not create new spec files for the same scenarios. All API
> shapes, route names, accessible-name regexes, and env-var names below are
> reconciled against those files. See §4.3 and §10 for the locked details.

---

## 1. Background

Batches 2a–2e shipped backend infrastructure (magic-link auth, JWT, trips API, SSE
stream, fixture-backed tools). Batch 2e also shipped the frontend stack baseline
(Next 16, React 19, Tailwind 4, zod 4, RHF 7.76, TanStack Query 5, zustand 5) and
a single Playwright smoke spec (`e2e/landing.spec.ts`) that only verifies the
static landing page.

**Pain point (user's binding goal):** "前端 e2e 有更多功能可测" — the e2e suite
today asserts nothing about real product behavior. It cannot catch regressions
in any feature that involves the backend, user state, or navigation, because
no such surface exists in the frontend yet.

This PR creates the first real product surface (magic-link sign-in + an authed
landing) and extends the Playwright suite to exercise it end-to-end against the
**real FastAPI backend** running in Playwright's `webServer` array. Once this
PR lands, every subsequent frontend PR (starting with PR B — trip planning)
inherits a working pattern for adding real-flow e2e specs.

This PR is intentionally narrow: just enough authed surface to make e2e
meaningful, plus the wiring (Providers, API client, store, schemas) that PR B
will reuse.

## 2. Goals

### G1 — Activate the pre-committed e2e contracts (the PR gate)

Commit `29daa08` already added the spec files. After this PR,
`cd frontend && pnpm exec playwright test --project=chromium` runs
**all 4 spec files** (8 test cases total) and they all pass without `.fixme`:

1. `e2e/landing.spec.ts` (existing — 1 case, must remain green; extended by
   one extra assertion: `await expect(page.getByRole("link", { name: /sign in/i })).toBeVisible();`).
2. `e2e/app-shell.spec.ts` (already green — 3 cases; must stay green).
3. `e2e/auth-login-page.spec.ts` — 3 cases, all currently `test.fixme`,
   must be activated:
   - `renders email input and submit button`
   - `submitting a valid email shows confirmation copy`
   - `blocks submission for an obviously invalid email`
4. `e2e/auth-flow.spec.ts` — 1 case, currently `test.fixme`, must be
   activated: `request → verify → authed → sign out`.

**Hard rule:** Code Agent removes the `.fixme` from each test as the
implementation lands. No new spec files for these scenarios. No edits to the
existing test bodies except to drop `.fixme` (and only if a contract
mismatch is unavoidable, in which case Code Agent must SendMessage team-lead
*before* changing a test).

### G2 — All existing gates remain green

- `pnpm build` ✅
- `pnpm lint` ✅
- `pnpm exec prettier --check .` ✅
- `pnpm typecheck` ✅
- `pnpm test` (vitest) ✅ — at minimum one unit test for the auth store and
  one for the API client (mock `fetch`).

### G3 — Backend gates remain green

- `just backend-check` (ruff + mypy + unit) ✅
- New `GET /api/auth/dev/last-link` endpoint covered by an integration test
  asserting `200` in `app_env="development"` and `404` in `app_env="production"`.

## 3. Non-Goals

- **Trip planning UI** — that is PR B (existing pending task #8).
- **SSE consumer** — PR B.
- **PWA / service-worker changes** — separate stack PR #4 (`@serwist/next` v9).
- **Design-system overhaul** — use the same minimal Tailwind utility classes
  already on the landing page (`bg-background`, `text-foreground`,
  `text-muted-foreground`, `mx-auto`, `max-w-2xl`, etc.). No new colors, no
  new spacing scale, no shadcn-style component extraction in this PR.
- **No new fonts, no decorative typography.** Per the user's standing rule:
  "切记不要为了花里跨张把字体弄得不好看清." Use the platform default font stack
  inherited from the existing layout.
- **Real SMTP wiring** — backend dev sender (`_ConsoleEmailSender`) is what
  e2e relies on. SMTP is a separate batch.
- **i18n** — strings are English-only for this PR (matches landing page).
- **Password / OAuth / 2FA** — magic-link is the only auth surface.
- **Session refresh / silent re-auth** — JWT TTL is 60 minutes; expiry handling
  is a follow-up (we'll just bounce the user to `/login` on 401 in this PR).
- **CSRF tokens** — JWT is a Bearer header, not the httpOnly cookie, so
  CSRF doesn't apply to our request path. (Backend still sets the cookie for
  future use; we ignore it.)

## 4. Technical Approach

### 4.1 Backend additions (small, scoped)

Two new endpoints, both in `backend/src/plus_one/api/auth.py`:

**`GET /api/auth/me`**
- Depends on the existing `CurrentUser` dep (already implemented at
  `backend/src/plus_one/core/auth/deps.py:25`).
- Returns `{"id": int, "email": str}`.
- Returns 401 via the existing dep behavior if no/invalid Bearer token.
- Pydantic response model `MeResponse` next to the existing schemas in
  `auth.py`.

**`GET /api/auth/dev/last-link`**
- Returns **`{"token": str}`** — minimum shape locked by `e2e/auth-flow.spec.ts:30`
  which does `const { token } = (await lastLink.json()) as { token: string }`.
  Extra fields are forbidden so the contract stays narrow; if anything else is
  ever needed, expand the contract in a separate PR.
- Accepts query param **`?email=<addr>`** (mandatory in the e2e usage at
  `auth-flow.spec.ts:28`). If no link for that email exists yet, return 404.
- Guarded by `settings.app_env == "development"`. Any other value → 404. The
  guard is checked **at request time**, not import time, so the same binary
  can be reused for both dev and prod images without rebuild.
- Backing store: a module-level `dict[str, str]` (email → most-recent raw
  token) in `backend/src/plus_one/core/auth/email.py`, written by
  `_ConsoleEmailSender.send_magic_link` (parse the token out of the link
  query-string before storing). This couples the dev endpoint to the dev
  sender — appropriate, because if `allow_console_email_sender=False` no
  link is captured and the endpoint returns 404.
- The endpoint **must NOT** be exposed when the sender is `_SmtpEmailSender`.
- **Note on link vs token:** the e2e harness only needs the raw token —
  it then navigates `/auth/verify?token=<>` on the *frontend* origin and
  lets the frontend page POST to `/api/auth/exchange`. Returning the full
  link would leak the frontend origin into the API surface unnecessarily.

Integration test (`backend/tests/integration/api/test_auth_dev.py`):

- With `settings.app_env="development"` + `allow_console_email_sender=True`:
  call `request-link` for `e2e@plusone.test` → call
  `GET /api/auth/dev/last-link?email=e2e@plusone.test` → assert 200, body
  shape `{"token": str}`, token is a non-empty string, and the same token
  successfully exchanges via `POST /api/auth/exchange`.
- With `settings.app_env="development"` but no link issued yet for that
  email → assert 404.
- With `settings.app_env="production"`: call `dev/last-link` → assert 404,
  regardless of query.

### 4.2 Frontend file additions

All paths relative to `frontend/`.

| Path | Purpose |
|------|---------|
| `lib/schemas/auth.ts` | zod schemas: `RequestLinkBody`, `ExchangeBody`, `ExchangeResponse`, `MeResponse`, `DevLastLinkResponse` (`{ token: string }`). Re-export inferred TS types. |
| `lib/api/client.ts` | Thin `apiFetch(path, init)` wrapper. Reads base URL from `process.env.NEXT_PUBLIC_API_BASE_URL` (falling back to `process.env.NEXT_PUBLIC_API_URL`, then `http://localhost:8000`). See §10 for why both names are read. Injects `Authorization: Bearer ${token}` when a token is in the auth store (read via `useAuthStore.getState()`, *not* a hook — this is called from non-component code too). Throws `ApiError` (custom class) with `{status, body}` on non-2xx. |
| `lib/api/auth.ts` | Typed wrappers: `requestLink(email)`, `exchange(token)`, `getMe()`, `logout()`. (`getDevLastLink` is e2e-harness-only — `auth-flow.spec.ts` calls the endpoint directly via Playwright `request.get`; do NOT add it to the app's API client surface.) Each calls `apiFetch` and parses with the matching zod schema. |
| `store/auth.ts` | zustand store. Shape: `{ token: string \| null, user: { id: number, email: string } \| null, setSession(token, user), clearSession() }`. Uses `persist` middleware with `localStorage`, `name: "plus-one-auth"`. **`skipHydration: true`** so the store does not read localStorage during SSR (avoids hydration mismatch — see R1). |
| `hooks/useHasHydrated.ts` | Tiny `useSyncExternalStore`-based hook returning `true` once the persist middleware has finished rehydrating. Components that render based on auth state gate on this. |
| `hooks/useCurrentUser.ts` | Returns `{ user, isAuthenticated, signOut }`. `signOut` calls `apiFetch('/api/auth/logout', {method:'POST'})` (best-effort; ignore errors), then `clearSession()`, then `router.push('/')`. |
| `components/providers.tsx` | Client component (`"use client"`). Wraps children in `<QueryClientProvider client={queryClient}>`. `queryClient` defined at module scope with safe defaults: `staleTime: 30_000`, `refetchOnWindowFocus: false`. |
| `app/login/page.tsx` | Client component. **Heading text must match `/sign in/i`** (h1) per `auth-login-page.spec.ts:14`. RHF + zod resolver. Email input must have a label matching `/email/i`. Submit button accessible name must match `/send.*link\|magic link/i`. Validation message for invalid email must match `/valid email\|invalid email/i` and surface **before any network call**. Success copy must match `/check your inbox\|email sent\|link sent/i`. On 503 (`email_sender_not_configured` from backend) render an inline error. |
| `app/auth/verify/page.tsx` | **Client component**, NOT server. Path **must be `/auth/verify`** per `auth-flow.spec.ts:34`. Reads `?token=...` via `useSearchParams`, calls `exchange(token)` on mount, then `getMe()`, sets session via store, then `router.replace('/app')`. While in flight: `<p>Signing you in…</p>`. On failure: `<p>This sign-in link is invalid or expired. <Link href="/login">Request a new one</Link>.</p>`. (Backend currently builds the email link with path `/auth/exchange` — see §6 R7 for the resolution.) |
| `app/app/page.tsx` | Client component. Gated on `useHasHydrated()`. If hydrated and `!isAuthenticated`, render `<RedirectToLogin />` (returns `null`, calls `router.replace('/login')` in an effect). If authed: must render the user's email string verbatim somewhere visible (e.g. `<h1>Hello, {user.email}</h1>`) so `auth-flow.spec.ts:36` `expect(page.getByText(email)).toBeVisible()` passes. Must include a sign-out control whose accessible name matches `/sign out\|log out/i`. |
| `app/layout.tsx` (modify) | Wrap `{children}` in `<Providers>`. No other changes. |
| `app/page.tsx` (modify) | Add `<Link href="/login">Sign in</Link>` (accessible name matches `/sign in/i`) below the construction notice. Preserve existing heading + tagline copy verbatim. |

### 4.3 E2E fixme to activate

Spec files are already committed at `29daa08`. Code Agent activates them by
removing `.fixme`. **Do not create new spec files for these scenarios.**

| Path | Cases to activate | Notes |
|------|-------------------|-------|
| `e2e/landing.spec.ts` | already green — extend by adding ONE assertion: `await expect(page.getByRole("link", { name: /sign in/i })).toBeVisible();` after the existing 5 assertions. Preserve the console-error allow-list block intact. |
| `e2e/app-shell.spec.ts` | already green — do not modify. |
| `e2e/auth-login-page.spec.ts` | drop `.fixme` from all 3 cases: `renders email input and submit button`, `submitting a valid email shows confirmation copy`, `blocks submission for an obviously invalid email`. |
| `e2e/auth-flow.spec.ts` | drop `.fixme` from `request → verify → authed → sign out`. |

**Contracts the implementation MUST satisfy** (extracted verbatim from the
committed spec bodies — do not change the specs to fit the implementation,
change the implementation):

- `/login` returns 200 and has `<title>` matching `/Plus One/`.
- `/login` `<h1>` text matches `/sign in/i`.
- `/login` has a control reachable via `page.getByLabel(/email/i)`.
- `/login` has a button reachable via `page.getByRole("button", { name: /send.*link|magic link/i })`.
- After valid submit, copy matching `/check your inbox|email sent|link sent/i` is visible within 5s.
- After invalid email submit, copy matching `/valid email|invalid email/i` is visible — **without any network call** (zod resolver fires client-side first).
- `GET /api/auth/dev/last-link?email=<>` returns 200 with JSON `{ token: string }` where token is non-empty.
- After visiting `/auth/verify?token=<encoded>`, URL becomes one matching `/\/app(\/|$)/`.
- On the post-auth page, the email string used during sign-in is visible (`page.getByText(email)`).
- That page has a button matching `/sign out|log out/i`.
- After clicking sign-out, URL becomes `/` exactly and a link matching `/sign in/i` is visible.

**Backend port wiring:** `auth-flow.spec.ts:27` reads
`process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"`. The
Playwright `webServer` for the backend (§4.4) must therefore listen on
`:8000`. The `NEXT_PUBLIC_API_BASE_URL` env var only needs to be set if a
non-default port is used.

### 4.4 Test wiring (`playwright.config.ts`)

Convert single `webServer` object to an array:

```ts
webServer: [
  {
    command: "pnpm start",
    url: "http://localhost:3000",
    reuseExistingServer: !isCI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
    },
  },
  {
    // Run from repo root so `cd ..` lands in newproject/, then into backend/.
    // `uv run` activates the venv created by `uv sync`.
    command:
      "cd ../backend && uv run uvicorn plus_one.main:app --port 8000 --host 127.0.0.1",
    url: "http://localhost:8000/health",
    reuseExistingServer: !isCI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      APP_ENV: "development",
      ALLOW_CONSOLE_EMAIL_SENDER: "true",
      AUTH_COOKIE_SECURE: "false",
      // SQLite in-memory or a temp file is fine — but the easiest path
      // is the existing default Postgres URL if devs already have it up.
      // For CI we'll provide DATABASE_URL via the workflow env.
    },
  },
],
```

Notes:
- `url` for backend points at `/health` (already implemented at
  `backend/src/plus_one/main.py:56`), so Playwright waits for a real ready
  signal, not just port open.
- `cd ../backend` is run inside the Playwright child shell. On Windows this
  works with the same syntax under both Git Bash and `cmd` because there
  are no platform-specific operators.
- `reuseExistingServer: !isCI` lets a dev with `pnpm dev` already running
  skip re-spawn.

### 4.5 CI changes (`.github/workflows/<frontend-e2e>.yml`)

Find the existing frontend-e2e job. Before the `pnpm exec playwright test`
step, add:

1. `uses: astral-sh/setup-uv@v3` (or whatever version the backend job already
   uses — Code Agent should match).
2. `working-directory: backend; run: uv sync`.
3. Bring up Postgres via service container (same image/version as the backend
   integration-test job already uses — copy it verbatim).
4. `working-directory: backend; run: uv run alembic upgrade head` to apply
   migrations.
5. Set the same env vars listed in `playwright.config.ts` `webServer[1].env`
   plus `DATABASE_URL`, `JWT_SECRET`, and any other vars the backend currently
   requires in CI.

Code Agent: read the existing backend CI job in `.github/workflows/` to copy
the service container + env wiring rather than reinventing it.

### 4.6 Schemas (zod)

```ts
// lib/schemas/auth.ts (illustrative — Code Agent owns final form)
export const RequestLinkBody = z.object({ email: z.string().email() });

export const ExchangeBody = z.object({ token: z.string().min(10).max(200) });

export const ExchangeResponse = z.object({
  access_token: z.string(),
  token_type: z.literal("bearer"),
  expires_in_minutes: z.number().int().positive(),
});

export const MeResponse = z.object({
  id: z.number().int().positive(),
  email: z.string().email(),
});

export const DevLastLinkResponse = z.object({
  email: z.string().email(),
  link: z.string().url(),
  issued_at: z.string(),
});
```

## 5. Migration / Implementation Order

Code Agent should implement in this order — each step compiles and runs
independently before the next is started:

1. **Backend `/api/auth/me`** + integration test (1 endpoint, ~20 lines).
2. **Backend `/api/auth/dev/last-link`** + console-sender capture + integration
   test (env-guard test is the key one).
3. **Frontend schemas** (`lib/schemas/auth.ts`) + vitest for one schema.
4. **Frontend auth store** (`store/auth.ts`) + `useHasHydrated` + vitest.
5. **Frontend API client** (`lib/api/client.ts`, `lib/api/auth.ts`) + vitest
   mocking `fetch`.
6. **Providers** (`components/providers.tsx`) and wire into `app/layout.tsx`.
7. **`/login` page** + RHF + zod + submit handler.
8. **`/auth/exchange` page** — verify locally that pasting a console-logged
   link works end-to-end before moving on.
9. **`/app` page** + sign-out flow.
10. **Update landing** (`app/page.tsx`) to add Sign-in link.
11. **Update `playwright.config.ts`** `webServer` array.
12. **Write three e2e specs** — run after each one is added.
13. **Run all gates locally**: build + lint + format:check + typecheck + test +
    e2e + `just backend-check`.
14. **Manual screenshots** of `/login` and `/app` (authed) saved to
    `frontend/e2e/.artifacts/` (already covered by `.gitignore` pattern; add
    `e2e/.artifacts/` explicitly if not).
15. **CI workflow update** (last — least confidence change; iterate via PR
    pushes).

## 6. Risks & Mitigations

| ID | Risk | Mitigation |
|----|------|------------|
| R1 | **SSR/persist hydration mismatch.** zustand's `persist` reads from `localStorage` on first render; server has no localStorage so values differ → React hydration error. | Set `skipHydration: true` on the persist middleware. Provide `useHasHydrated()` hook (via `useSyncExternalStore` on `persist.onFinishHydration`). Auth-dependent UI returns a stable empty placeholder until hydrated. |
| R2 | **Backend not in CI for e2e job.** | Extend the existing frontend-e2e workflow with `uv sync` + service-container Postgres + `alembic upgrade head` (mirror the existing backend job). |
| R3 | **Env-var leaks.** | Frontend only ever reads `NEXT_PUBLIC_API_URL`. No secrets in `NEXT_PUBLIC_*`. JWT lives in localStorage (acknowledged tradeoff for SSE Bearer auth in PR B); XSS hardening is owned by CSP work in a later batch. |
| R4 | **Dev-only `last-link` endpoint accidentally enabled in prod.** | Guard by `settings.app_env == "development"` at request time. Integration test asserts 404 when `app_env="production"`. CI env in prod-like workflows must set `APP_ENV=production` (already standard practice). |
| R5 | **E2E flake from real network.** | No `page.waitForTimeout(...)` allowed. Use `expect.poll()`, `expect(locator).toBeVisible()` (auto-retries), and `page.waitForURL()` for navigation. The dev `last-link` endpoint should be polled with `expect.poll` not slept on, since the backend write happens during the `request-link` HTTP response and may race with the read on first request. |
| R6 | **CORS preflight failures.** Backend currently hard-codes `allow_origins=["http://localhost:3000"]` at `backend/src/plus_one/main.py:46` with `allow_credentials=True`. | Matches our frontend origin exactly. Document in PR description that any change to frontend port requires updating this list — no action needed in this PR. |
| R7 | **Magic-link route mismatch.** Backend builds the link as `${frontend_base_url}/auth/exchange?token=...`. If frontend route is named differently the email link 404s. | This PRD pins the route to `/auth/exchange`. Code Agent must use that exact path, not `/auth/verify`. |
| R8 | **Spec-vs-implementation endpoint names.** Original brief referred to `request_magic_link` / `verify_magic_link`. Real backend uses `request-link` / `exchange`. | This PRD uses the real names. All API client wrappers and tests must follow. |
| R9 | **Postgres in CI startup time** pushes the job above its current budget. | Backend job already does this — copy its setup verbatim. If runtime becomes an issue, follow-up by sharing the Postgres container across jobs (out of scope here). |

## 7. Acceptance Criteria (PR gate — must all pass before merge)

**Order matters — G1 is the binding goal; gate on it first.**

1. **(G1)** `cd frontend && pnpm exec playwright test --project=chromium` runs
   exactly 3 spec files and all pass. Output shows ≥7 test cases passing
   (landing has 1, login-page has ≥1, flow has ≥1; teams may split flow into
   smaller cases).
2. `cd frontend && pnpm build` exits 0 with no warnings about hydration or
   unused exports.
3. `cd frontend && pnpm lint` exits 0.
4. `cd frontend && pnpm exec prettier --check .` exits 0.
5. `cd frontend && pnpm typecheck` exits 0.
6. `cd frontend && pnpm test` — vitest runs, includes at least one test for
   `store/auth.ts` and one for `lib/api/client.ts`, all pass.
7. `just backend-check` exits 0.
8. Backend integration test for `GET /api/auth/dev/last-link`: asserts 200 in
   `app_env="development"`, 404 in `app_env="production"`.
9. CI frontend-e2e job is green on the PR with the backend in the `webServer`
   array.
10. **Manual:** screenshot of `/login` (empty state + post-submit state) and
    `/app` (authed) saved to `frontend/e2e/.artifacts/` locally. Not committed;
    PR description includes the screenshots inline.
11. No `console.log` / `console.warn` / debug code committed; eslint catches
    the former.
12. No new dependency added beyond what's already in `package.json`.

## 8. Rollout

Single PR to `main`, squash merge. No feature flag — the new pages are net-new
routes; landing page only gains one link. Backward compatibility: none required
(no existing users, no existing auth surface).

After merge, Batch 2f PR B (trip-planning UI + SSE consumer) picks up the
authed shell at `/app` and adds the trip-input UI under it.

## 9. Out-of-PRD context for implementers

- **User profile rule:** the user has stated they dislike decorative
  typography ("切记不要为了花里跨张把字体弄得不好看清"). Stick to the existing
  font stack and the minimal Tailwind utilities already used on landing.
- **Code style:** the repo uses Prettier (4-arg pre-existing config at
  `frontend/.prettierrc.json`) and ESLint with `eslint-config-next`. No
  comments unless the *why* is non-obvious.
- **Naming consistency:** the existing `.env.example` uses
  `NEXT_PUBLIC_API_URL`. Do not introduce `NEXT_PUBLIC_API_BASE_URL` as
  originally specced — reuse the existing var.
- **Testing convention:** `e2e/landing.spec.ts` has a console-error
  allow-list pattern that filters favicon/PWA noise. New specs should
  reuse the same pattern (factor into `e2e/_console-errors.ts` if it gets
  copy-pasted to all three).

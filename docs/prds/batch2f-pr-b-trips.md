# Batch 2f PR B — Trip Input + SSE Consumer + Report View + E2E

**Owner:** Frontend
**Branch:** `feat/batch2f-pr-b-trips` (cut from `main` HEAD `c1b6f12`)
**Status:** PRD draft — awaiting team-lead pre-commit of e2e scaffolds (see §10)
**Date:** 2026-05-19
**Predecessor:** PR A (`#14`, merged 2026-05-19). PRD at
`C:\Users\haowenfeng\repo\newproject\docs\prds\batch2f-pr-a-auth.md`.

---

## 1. Background

Batches 2a–2e shipped the entire backend trip surface:

- `POST /api/trips` — creates a trip + spawns the agent cycle as a
  FastAPI `BackgroundTask`
  (`C:\Users\haowenfeng\repo\newproject\backend\src\plus_one\api\trips.py:52-90`).
- `GET /api/trips/{trip_id}/stream` — SSE of cycle progress events
  (`...api\trips.py:93-123`).
- `GET /api/trips/{trip_id}` — fetches the latest persisted report
  (`...api\trips.py:126-152`).

All three require `Authorization: Bearer <jwt>`
(`backend\src\plus_one\core\auth\deps.py:30-44`).

PR A shipped the auth surface (login, exchange, `/app`, JWT in
zustand), the `apiFetch` Bearer-injecting client, Providers wiring, and
the Playwright `webServer` 2-entry array that runs a real backend
alongside the frontend
(`C:\Users\haowenfeng\repo\newproject\frontend\playwright.config.ts:41-77`).

The user's binding goal remains *"前端 e2e 有更多功能可测"*. PR A
moved e2e from 1 → 8 cases by adding the auth surface; **this PR is
the second concrete step** — it adds the first real product surface
(trip creation, live SSE consumption, persisted report rendering) and
extends the Playwright suite by a happy path that exercises all three
backend endpoints against the real FastAPI process.

After this PR, the agentic core of Plus One (one user request →
Producer/Joiner/Controller cycle → persisted report) is end-to-end
exercised by CI on every push.

**Supersedes handoff §"Frontend gotchas to know in advance" on SSE auth**
(`docs/handoff/REMAINING_WORK.md:180-188`). The handoff doc claims (a) the
cookie path is preferred and (b) native `EventSource` to the stream
endpoint works. Both are false against current backend: `current_user`
(`backend/src/plus_one/core/auth/deps.py:30-44`) reads only the
`Authorization: Bearer` header — no cookie path exists, and EventSource
cannot set headers. **This PRD is the v1 source of truth for trip SSE
auth: query-param token (§4.1).** A separate doc PR will append a
"superseded" note to the handoff after merge.

## 2. Goals

### G1 — E2E coverage grows from 8 → at least 12 cases (the PR gate)

After this PR, `cd frontend && pnpm exec playwright test --project=chromium`
runs **at least 12 cases across at least 6 spec files**, all green. The
new cases land in spec files team-lead will pre-commit as `test.fixme`
(see §10) and Code Agent activates by dropping `.fixme`.

Distribution (existing 8 stay green; +4 new minimum):

| Spec file | New / existing | Cases |
|-----------|----------------|-------|
| `e2e/landing.spec.ts` | existing | 1 |
| `e2e/app-shell.spec.ts` | existing | 3 |
| `e2e/auth-login-page.spec.ts` | existing | 3 |
| `e2e/auth-flow.spec.ts` | existing | 1 |
| `e2e/trip-new-page.spec.ts` | **new** | 3 (render, validation, navigate-on-submit) |
| `e2e/trip-flow.spec.ts` | **new** | 1 (full happy path: login → submit → SSE event renders → report) |

**Mandatory happy-path contract** (the load-bearing test in
`e2e/trip-flow.spec.ts`):

1. Sign in via the **PR A** flow — do NOT re-implement; use the same
   `request-link → dev/last-link → /auth/exchange` sequence in a shared
   helper (§4.3).
2. Land on `/app`. Click a link/button leading to `/app/trips/new`.
3. Fill destination (required) + optional free text. Submit.
4. URL navigates to `/app/trips/{trip_id}`.
5. **At least one SSE event with a name from the known set** (`started`,
   `iteration_start`, `producer`, `joiner`, `controller`,
   `cycle_aborted`, `trip_complete`) is rendered in the DOM within
   20 seconds. The assertion is a regex over rendered text, e.g.
   `expect(page.getByTestId("progress-feed")).toContainText(/started|producer|joiner|controller|trip complete/i)`.
6. Wait for `trip_complete` (or `aborted`) terminal state — surfaced
   either as visible copy matching `/complete|aborted|done/i` OR a
   `data-trip-status` attribute on the page root taking value
   `complete`/`aborted` (Code Agent picks one; pre-commit spec uses
   the chosen mechanism — see §10).
7. Report view renders. Assert the page contains text matching
   `/report|items|result/i` AND at least the trip's `destination`
   string is visible (echo-back from `GET /api/trips/{id}`).

If steps 5/7 race the cycle finishing too fast to observe a
mid-cycle event, the assertion in step 5 may match `trip complete` —
both paths satisfy the contract.

### G2 — All existing gates remain green

- `cd frontend && pnpm build` exits 0, no hydration warnings, no
  unused-export warnings.
- `cd frontend && pnpm lint` exits 0.
- `cd frontend && pnpm exec prettier --check .` exits 0.
- `cd frontend && pnpm typecheck` exits 0.
- `cd frontend && pnpm test` (vitest) — at minimum new unit tests for
  `lib/api/trips.ts` (mock `fetch`) and `lib/sse.ts` (mock
  `EventSource`).

### G3 — Backend gates remain green

- `just backend-check` (ruff + mypy + unit) exits 0.
- One new backend integration test (`backend/tests/integration/api/test_trips_sse_auth.py`)
  asserts:
  - `GET /api/trips/{id}/stream` returns 401 with no auth.
  - `GET /api/trips/{id}/stream?access_token=<valid_jwt>` returns 200
    and at least one SSE frame is read before the test cancels.
  - `GET /api/trips/{id}/stream` with a valid `Authorization` header
    (existing behavior) still returns 200 — the query-param fallback
    must not break header auth.
- One new backend unit test (`backend/tests/unit/test_access_log_scrub.py`)
  asserts the `_ScrubAccessTokenFilter` redacts `access_token=<value>`
  in a representative `uvicorn.access` log record and leaves unrelated
  records untouched.

## 3. Non-Goals

- **PWA / service-worker / offline support** — stack PR #4 territory
  (`@serwist/next` v9 migration).
- **OAuth / SSO / refresh tokens** — magic-link from PR A is the only
  auth.
- **Real LLM / Maestro wiring in CI** — domain agents use the existing
  fixture-backed tools from batch 2c (`ramen_basics` skill). Backend
  refuses to construct the real LLM provider unless
  `PLUS_ONE_ALLOW_REAL_LLM=1` is set; CI does NOT set it. Cycles in
  e2e MUST run on the fixture path. If the cycle aborts because no
  fixture path is configured for the destination, the test asserts
  the `cycle_aborted` event instead of `trip_complete` — both satisfy
  G1's mid-cycle-event clause (§2).
- **Design-system overhaul** — same minimal Tailwind utilities PR A
  established. No new colors. No shadcn-style extraction.
- **No decorative typography.** Per the user's standing rule (cited
  verbatim in §9): *"切记不要为了花里跨张把字体弄得不好看清."*
- **Trip history / list** — `GET /api/trips` (list-all) does not exist
  on the backend. Single-trip view only. Listing is a follow-up
  (`docs/handoff/REMAINING_WORK.md:298-302` flags
  `/reports` history as a known follow-up).
- **Profile / companions integration** — backend does not expose the
  endpoints yet; v1 trip query is `destination | free_text` per
  `backend\src\plus_one\api\trips.py:79-83`.
- **Multi-cycle regeneration** — one trip = one cycle in v1.
- **Stream reconnection / retry** — if the SSE connection drops mid-cycle
  the UI shows a single inline error and the user can refresh; auto-retry
  with backoff is a follow-up. See §6 R1.
- **i18n** — English strings only, matches PR A.
- **CORS changes** — backend allow-list at
  `backend\src\plus_one\main.py:46` already covers `http://localhost:3000`.
- **shadcn/ui component extraction** — the handoff doc
  (`docs/handoff/REMAINING_WORK.md:135-138`) suggests pulling in
  shadcn primitives. Out of scope; raw Tailwind utility classes match
  PR A's posture.

## 4. Technical Approach

### 4.1 Backend additions

Three small changes, all scoped to enable browser SSE auth and prevent the
query-param token from leaking into stdout. **No other backend behavior
changes.**

**Change 1 — new dep `current_user_or_sse` in
`backend\src\plus_one\core\auth\deps.py`**

(Naming: `current_user_or_sse` not `current_user_sse` — reads as "header
auth, OR the SSE-fallback path", not "an SSE-specific user".)

Reads the `Authorization: Bearer <jwt>` header first. If absent,
reads `?access_token=<jwt>` from the query string. Decodes via the same
`decode_access_token`. Loads the user. Returns 401 on any failure with
the same shape as the existing `current_user`. Provide a `CurrentUserOrSse`
type alias next to the existing `CurrentUser`.

Skeleton (illustrative — Code Agent owns final form):

```python
async def current_user_or_sse(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    access_token: str | None = None,
    session: Annotated[AsyncSession, Depends(get_request_session)] = ...,
) -> User:
    """Auth dep for SSE endpoints — header preferred, query param fallback.

    Browsers using ``EventSource`` cannot set request headers, so we accept
    the JWT via ``?access_token=`` as a narrow fallback for SSE endpoints
    only. Use the standard ``current_user`` everywhere else.

    SECURITY NOTE: tokens in URLs can leak via access logs and DevTools.
    Mitigated in-process by the uvicorn access-log scrubbing filter
    installed in ``plus_one.main`` (see Change 3). JWT TTL of 60min limits
    blast radius. Production deployments behind a proxy must additionally
    scrub the proxy's access log (out of scope for this PR — operations
    runbook task).
    """
    token: str | None = None
    if creds is not None and creds.scheme.lower() == "bearer":
        token = creds.credentials
    elif access_token:
        token = access_token

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization (header or ?access_token)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # ... rest mirrors current_user
```

**Change 2 — `backend\src\plus_one\api\trips.py:97-101`**

`async def stream_trip(...)` switches `user: Annotated[User, Depends(current_user)]`
→ `user: CurrentUserOrSse`. Add `access_token: str | None = None` to the
function signature so FastAPI surfaces it to the dep. **No other change**
to the endpoint body. `POST /api/trips` and `GET /api/trips/{id}` continue
to use `current_user` (header-only).

**Change 3 — access-log scrubbing filter in
`backend\src\plus_one\main.py`** (recommended approach (a) from team-lead
review)

Install a small `logging.Filter` on the `uvicorn.access` logger that
rewrites any occurrence of `access_token=<value>` in the formatted log
record to `access_token=REDACTED`. Scope is the access log only — does
NOT touch structlog records or other loggers.

Implementation outline (Code Agent owns final form):

```python
import logging
import re

_ACCESS_TOKEN_RE = re.compile(r"access_token=[^&\s\"]+")


class _ScrubAccessTokenFilter(logging.Filter):
    """Redact ``access_token=<jwt>`` from uvicorn access log lines.

    The SSE endpoint accepts the JWT via query param because EventSource
    cannot set headers; default uvicorn access-log format includes the
    full request line, which would otherwise expose the token in stdout.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "access_token=" in record.msg:
            record.msg = _ACCESS_TOKEN_RE.sub("access_token=REDACTED", record.msg)
        if record.args:
            record.args = tuple(
                _ACCESS_TOKEN_RE.sub("access_token=REDACTED", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def _install_access_log_scrubber() -> None:
    logging.getLogger("uvicorn.access").addFilter(_ScrubAccessTokenFilter())
```

Call `_install_access_log_scrubber()` once at app construction in
`main.py` (next to the existing FastAPI / CORS setup). Idempotent —
adding the same filter twice is harmless under `logging.Filter`.

**Integration tests** (`backend/tests/integration/api/test_trips_sse_auth.py`):
the three assertions listed in §G3 above. Test name guidance:
`test_stream_requires_auth`, `test_stream_accepts_query_token`,
`test_stream_accepts_header_token`.

**One unit test** for the scrubber
(`backend/tests/unit/test_access_log_scrub.py`): construct a `LogRecord`
whose `msg` contains a representative uvicorn access line with
`?access_token=eyJ...&foo=bar` in the request line; assert the filter
rewrites it to `?access_token=REDACTED&foo=bar` and that an unrelated
line is left untouched.

**Why no new endpoint for the e2e harness:** unlike PR A's
`/api/auth/dev/last-link`, the existing
`GET /api/trips/{id}` is already a perfect dev/test peek — it returns
the trip status + latest report content. The e2e harness polls it to
confirm report persistence rather than scraping the SSE log.

### 4.2 Frontend file map

All paths relative to `C:\Users\haowenfeng\repo\newproject\frontend\`.

| Path | Purpose |
|------|---------|
| `lib/schemas/trips.ts` | Zod schemas (and inferred TS types): `CreateTripBody` (`{destination: string(1..200), free_text?: string(<=2000)}` matching `backend\src\plus_one\api\trips.py:34-36`); `CreateTripResponse` (`{trip_id: string.uuid(), status: string}`); `TripDetail` (`{trip_id, destination, status: enum("pending"|"running"|"complete"|"aborted"), latest_report_id: string.uuid().nullable(), content: z.object({items: z.array(JoinedItemSchema)}).nullable()}`); `JoinedItemSchema` — keep loose for v1 (`z.object({}).passthrough()`) because the backend's `JoinedItem.model_dump(mode="json")` includes fields whose shape is not yet frozen (see `trip_runner.py:144`). Re-export every inferred type. |
| `lib/schemas/events.ts` | Zod schemas for SSE events. `TripEventName = z.enum(["started","iteration_start","producer","joiner","controller","cycle_aborted","trip_complete"])`. `TripEvent` is a **`z.discriminatedUnion("name", [...])`** (not a plain `z.union`) so TS narrowing on `.name` works in `ProgressFeed.tsx`; each variant is its own object schema with `name: z.literal("...")`. Data shapes mirror `backend\src\plus_one\services\trip_runner.py:164-289` (e.g. `producer.data = {n_candidates, notes}`, `joiner.data = {n_in, n_out, notes}`, `controller.data = {should_continue, reasoning, notes}`, `cycle_aborted.data = {reason}`, `trip_complete = {trip_id, status, report_id}`). Use `passthrough()` on each variant so unknown fields don't break parse. |
| `lib/api/trips.ts` | Typed API wrappers: `createTrip(body: CreateTripBody): Promise<CreateTripResponse>` (POST `/api/trips`); `getTrip(id: string): Promise<TripDetail>` (GET `/api/trips/{id}`). Both go through `apiFetch` (Bearer injection inherited). Parse the response with the matching zod schema before returning. |
| `lib/sse.ts` | Thin `EventSource` wrapper. Exports a single function `openTripStream(tripId, token, handlers)` returning a `{ close(): void }` handle. Builds the URL as `${apiBase}/api/trips/${tripId}/stream?access_token=${encodeURIComponent(token)}`. Wires `onmessage`, `onerror`, and `addEventListener` for each named event in `TripEventName`. Calls `handlers.onEvent(parsedEvent)` for each parsed SSE frame, `handlers.onError(e)` on stream error, `handlers.onClose()` once when the stream is closed (server EOF closes the EventSource by killing the connection; we treat any `readyState === 2` transition as `onClose`). Token is read from the auth store via `useAuthStore.getState().token` at call time — same pattern as `apiFetch` (`lib/api/client.ts:36`). |
| `hooks/useTripStream.ts` | React hook. Inputs: `tripId`. Returns `{ events: TripEvent[], status: "connecting" \| "open" \| "closed" \| "error", lastError: string \| null }`. Internally calls `openTripStream` on mount, appends each event to a ref-backed array (mirrored into state via a `flushSync`-free incremental update to avoid re-render storms — append, not replace), and closes on unmount. **Hard rules: (a) close in cleanup or it leaks; (b) on `onerror` ALSO call `eventSource.close()` explicitly to disable native auto-reconnect — see §6 R1.** Re-opens if `tripId` changes (only relevant if router pushes a new id without unmount). |
| `hooks/useTrip.ts` | TanStack Query wrapper around `getTrip(id)`. `enabled: hydrated && !!token`. `staleTime: 30_000`. Returns the query result; consumers fetch on demand (post-complete poll, manual refresh). |
| `components/trips/TripForm.tsx` | Client component. RHF + zod resolver using `CreateTripBody`. **Both fields are always rendered** — `destination` (required, label `/destination/i`, `<input type="text">`) and `free_text` (optional, label `/notes\|free text\|details/i`, `<textarea>`). Only `destination` is required by zod (`min(1)`); `free_text` is `z.string().max(2000).optional()`. Submit button accessible name matches `/plan\|start\|create/i`. On submit calls `createTrip` then `router.push(\`/app/trips/${trip_id}\`)`. Surfaces `ApiError` as an inline `<p role="alert">` (e.g., 401 → "Session expired. Sign in again."; other → the `detail` from the body). |
| `components/trips/ProgressFeed.tsx` | Client component. Props: `events: TripEvent[]`. Renders an `<ol>` with one `<li>` per event. Each `<li>` shows a human label (`started` → "Cycle started", `producer` → "Generated N candidates", `joiner` → "Joined X → Y items", `controller` → "Decided to {continue\|stop}: {reasoning}", `cycle_aborted` → "Cycle aborted: {reason}", `trip_complete` → "Trip {status}"). Container has `data-testid="progress-feed"` so the e2e can assert text inside it. |
| `components/trips/ReportView.tsx` | Client component. Props: `trip: TripDetail`. If `content?.items?.length` > 0, render `<ul>` of items with their raw JSON-stringified preview (low-design v1; items shape is `passthrough()`). If empty/null, render "No results yet." Header echoes `trip.destination` and shows `trip.status` as a badge. |
| `app/app/page.tsx` (modify) | Add a `<Link href="/app/trips/new">` with accessible name matching `/plan a trip\|new trip\|start/i` somewhere visible. Preserve the existing `Hello, {user.email}` and sign-out button verbatim — those are PR A frozen contracts. |
| `app/app/trips/new/page.tsx` | Client component. Gated on `useHasHydrated()` + token (same gate pattern as `app/app/page.tsx`). Renders `<TripForm />`. `<h1>` text matches `/plan a trip\|new trip/i`. |
| `app/app/trips/[id]/page.tsx` | Client component. Gated identically. Reads `id` from `useParams()`. Wires `useTripStream(id)` for the live feed and `useTrip(id)` for the post-complete report fetch. Logic: while `status !== "complete" && status !== "aborted"` (derived from the latest event), show `<ProgressFeed events={events} />`. Once the latest event is `trip_complete` (or `cycle_aborted`), `refetch()` the query and render `<ReportView trip={data} />` *below* the feed (keep the feed visible — it's the test evidence). Surfaces a top-level inline error if the SSE stream errors. Page root has `data-trip-status={derivedStatus}` so the e2e can `waitFor` `[data-trip-status="complete"]` deterministically. Title (via `useEffect` setting `document.title`) matches `/trip\|plus one/i`. |
| `e2e/_helpers/auth.ts` | NEW shared helper for tests that need an authed page. Exports `async function signInE2E(page, request): Promise<{email: string}>` — generates a fresh email **internally** as `\`e2e+${Date.now()}-${Math.random().toString(36).slice(2, 8)}@plusone.test\`` (timestamp alone is not unique enough under fully-parallel Playwright workers), runs the same `request-link → dev/last-link → /auth/exchange` flow as `e2e/auth-flow.spec.ts:17-37`, waits for the post-exchange redirect to `/\/app(\/|$)/`, and returns the generated email so the caller can assert on it later. **Single source of truth for the e2e sign-in sequence** — `auth-flow.spec.ts` stays as-is (it tests the auth flow itself), but every new spec that needs an authed page uses this helper. |

### 4.3 E2E scaffolds to be pre-committed by team-lead

Code Agent activates these (drop `.fixme`) but does NOT create them.
The exact assertion text below is the contract; team-lead's commit
freezes it (see §10).

**`e2e/trip-new-page.spec.ts`** — 3 cases, all `test.fixme`:

| # | Test name | Assertions |
|---|-----------|------------|
| 1 | `renders the trip form when authed` | `await signInE2E(page, request); await page.goto("/app/trips/new"); await expect(page.getByRole("heading", { level: 1 })).toContainText(/plan a trip\|new trip/i); await expect(page.getByLabel(/destination/i)).toBeVisible(); await expect(page.getByRole("button", { name: /plan\|start\|create/i })).toBeVisible();` |
| 2 | `blocks submit when destination is empty` | sign in, goto `/app/trips/new`, click submit with no destination, `await expect(page.getByText(/required\|destination/i)).toBeVisible();`. Must fire client-side (zod resolver) — no network request needed. |
| 3 | `submitting a valid trip navigates to /app/trips/<id>` | sign in, goto `/app/trips/new`, fill `destination = "Tokyo"`, optionally `free_text = "ramen"`, click submit, `await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i);`. Do NOT assert SSE state here — that's the full happy path's job. |

**`e2e/trip-flow.spec.ts`** — 1 case, `test.fixme`:

| # | Test name | Assertions |
|---|-----------|------------|
| 1 | `submit trip → live event → terminal status → report visible` | `await signInE2E(page, request); await page.goto("/app/trips/new"); await page.getByLabel(/destination/i).fill("Tokyo"); await page.getByRole("button", { name: /plan\|start\|create/i }).click(); await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i, { timeout: 10_000 }); await expect(page.getByTestId("progress-feed")).toContainText(/started\|producer\|joiner\|controller\|cycle aborted\|trip complete/i, { timeout: 20_000 }); await expect(page.locator("[data-trip-status='complete'], [data-trip-status='aborted']")).toBeVisible({ timeout: 60_000 }); await expect(page.getByText(/Tokyo/i)).toBeVisible();` |

**Total new cases:** 4. Combined with existing 8 → **12 cases across 6
spec files**, satisfying G1.

### 4.4 Playwright config

No changes. Current `playwright.config.ts:41-77` already runs frontend
+ backend with the right env vars (`APP_ENV=development`,
`ALLOW_CONSOLE_EMAIL_SENDER=true`, `AUTH_COOKIE_SECURE=false`). The
new specs hit the same backend on `:8000`. **One re-verify for Code
Agent**: confirm `PLUS_ONE_ALLOW_REAL_LLM` is NOT set in the
`webServer[1].env` block — if it ever gets set, fixture-backed tools
stop being the default and the cycle will try to call Maestro. Current
file does not set it (lines 65-74). Leave it that way.

### 4.5 CI

No CI workflow change. PR A already wired Postgres service + `uv sync`
+ `alembic upgrade head` for the frontend-e2e job. Backend tests for
the new SSE auth dep run in the existing backend-check job.

## 5. Migration / Implementation Order

Each step compiles and runs independently before the next is started.

1. **Backend `current_user_or_sse` dep** + the
   `trips.py:97-101` switch + the access-log scrubber install in
   `main.py` — implement and run
   `backend/tests/integration/api/test_trips_sse_auth.py` and
   `backend/tests/unit/test_access_log_scrub.py` first; these are
   the load-bearing prerequisites.
2. **Frontend schemas** — `lib/schemas/trips.ts` + `lib/schemas/events.ts`.
   One vitest each (a happy parse + a malformed-input rejection).
3. **Frontend API client** — `lib/api/trips.ts`. Vitest with mocked
   `fetch` round-trips for both `createTrip` and `getTrip`.
4. **SSE wrapper** — `lib/sse.ts`. Vitest mocking `EventSource` (jsdom
   doesn't ship one; use a small fake class) — assert URL composition,
   event dispatch, and that `close()` actually calls
   `EventSource.close()`.
5. **`useTripStream` hook** — RTL render test asserting events
   accumulate and cleanup closes the stream on unmount.
6. **`useTrip` hook** — RTL test asserting it's disabled pre-hydration
   / pre-token (same pattern as `useCurrentUser` already does).
7. **`TripForm`, `ProgressFeed`, `ReportView`** components — no
   network in unit tests; just snapshot/RTL.
8. **`/app/trips/new` page**.
9. **`/app/trips/[id]` page** — wire everything; smoke locally with a
   real backend + magic link via console.
10. **Update `/app` page** to add the "Plan a trip" link (one-line
    change).
11. **Activate the e2e fixmes** — `trip-new-page.spec.ts` (3 cases)
    then `trip-flow.spec.ts` (1 case). Run after each.
12. **Local full gate**: build + lint + format:check + typecheck + test
    + `pnpm exec playwright test --project=chromium` + `just backend-check`.
13. **Manual screenshots** of `/app/trips/new`, `/app/trips/{id}` mid-stream,
    and `/app/trips/{id}` post-complete saved to
    `frontend/e2e/.artifacts/` (gitignored). Embed in PR description.

## 6. Risks & Mitigations

| ID | Risk | Mitigation |
|----|------|------------|
| R1 | **SSE connection lifecycle.** Open on mount, close on unmount. Forgetting to close leaks an `EventSource` and keeps the backend queue alive longer than needed (the backend handles disconnect cleanly — `trips.py:108-122` — but client leaks are still bad). Mid-cycle 401 / token expiry kills the stream with `onerror` but EventSource will *auto-reconnect by default*, which against a 401 just hammers the backend. | `useTripStream` returns `close()` in `useEffect` cleanup. On any `onerror` we explicitly call `eventSource.close()` (disables auto-reconnect) and surface a status of `"error"` so the page can render the inline error. JWT TTL is 60min vs cycle ~60-90s — expiry mid-cycle is rare but possible; the inline error tells the user to refresh. Auto-retry / refresh-token is a follow-up. |
| R2 | **Token in SSE URL leaks.** `?access_token=<jwt>` is visible in DevTools, browser history (not for EventSource navigations specifically, but the URL is still inspectable), uvicorn access logs (in dev), and any reverse proxy access log in prod. | (a) Scope to SSE endpoint only — every other endpoint stays header-only. (b) JWT TTL is 60min. (c) In-process uvicorn access-log scrubber installed in `plus_one.main` (§4.1 Change 3) redacts `access_token=` in stdout. (d) Out-of-process proxies (prod runbook): operator scrubs the proxy access log — flagged in PR description, not in this PR. The alternative paths (fetch SSE polyfill, cookie auth) all have larger blast radius — see SendMessage decision log. |
| R3 | **Form validation race.** React-hook-form + zod resolver must fire client-side before any network call (e2e test 2 in `trip-new-page.spec.ts` asserts this — no `await page.waitForResponse`). | Mirror PR A's `/login` form pattern. Pass `zodResolver(CreateTripBody)` to `useForm`; let RHF block submit on resolver failure. Backend's 1..200 length on `destination` + zod `min(1)` are equivalent. |
| R4 | **Hydration discipline (re-affirm).** Every new page that reads auth state must gate on `useHasHydrated()`. Otherwise SSR renders without a token, client renders with one, React error. | Same pattern as `app/app/page.tsx:40-46`. Code Agent: copy that gate verbatim into `/app/trips/new` and `/app/trips/[id]`. Until hydrated, return a `Loading…` placeholder. |
| R5 | **Report persistence race.** The e2e reads the report shortly after `trip_complete` arrives. But `trip_runner.py:280-288` publishes `trip_complete` *after* `_save_report` completes (line 261) and *after* the session commit at the end of `session_scope`. So by the time the SSE frame is read by the client, the row IS committed. | The pattern is safe by construction. Add a comment in `useTripStream` referencing `trip_runner.py:260-289` so a future refactor of the runner's publish order doesn't silently break the contract. The e2e's `data-trip-status` gate gives the test up to 60s if the runner ever slips. |
| R6 | **No fixture for the destination.** The e2e uses `"Tokyo"`. If the fixture-backed tool path has no Tokyo data, the cycle aborts with `cycle_aborted`. | G1 explicitly accepts `cycle_aborted` as a valid terminal state for the happy path (the goal is "some real event renders, terminal state is reached, report row exists" — not "every cycle returns 10 items"). The `data-trip-status` gate accepts both `complete` and `aborted`. ReportView's "No results yet." branch renders the empty case cleanly. |
| R7 | **EventSource cross-origin + CORS.** EventSource sends a GET. Backend CORS already allows `http://localhost:3000` (`backend\src\plus_one\main.py:46`). SSE responses do not trigger CORS preflight (simple GET with no custom headers). | No action needed. Verify locally by running the dev backend + frontend and watching the network tab show the stream as 200. |
| R8 | **`EventSource` not in jsdom.** Vitest unit tests of `lib/sse.ts` and `useTripStream` will need a fake. | Provide a small `class FakeEventSource` in the test file; assign to `globalThis.EventSource` in `beforeEach`. No production dep. |
| R9 | **`useTripStream` re-render storms.** Naively `setState([...events, newEvent])` on every SSE frame is fine for ~5-20 events per cycle but would melt for streams of 1000s. | v1 streams emit O(10) events — non-issue. Append-to-array is correct and simple. Document the limit in a one-line comment so future-us doesn't reuse this for 1000-event streams. |
| R10 | **`docs/handoff/REMAINING_WORK.md:180-188` is stale.** It says "prefer the cookie path" and "EventSource directly works". Both are false against current backend (see PRD §1 + §4.1). | This PRD is the authoritative source for PR B's auth approach. After merge, ship a small doc commit appending a "2026-05-19: superseded by `docs/prds/batch2f-pr-b-trips.md` §4.1" note to the handoff doc. Out of scope for the code PR. |

## 7. Acceptance Criteria

Order matters — G1 is the binding goal; gate on it first.

1. **(G1)** `cd frontend && pnpm exec playwright test --project=chromium`
   runs ≥6 spec files with ≥12 cases total and all pass. No `.fixme`
   remains in `trip-new-page.spec.ts` or `trip-flow.spec.ts`. No new
   spec files exist beyond the 6 listed in §2.
2. `cd frontend && pnpm build` exits 0; no hydration warnings.
3. `cd frontend && pnpm lint` exits 0.
4. `cd frontend && pnpm exec prettier --check .` exits 0.
5. `cd frontend && pnpm typecheck` exits 0.
6. `cd frontend && pnpm test` exits 0; covers new
   `lib/api/trips.ts`, `lib/sse.ts`, and the new hooks.
7. `just backend-check` exits 0.
8. `backend/tests/integration/api/test_trips_sse_auth.py` passes — all
   three cases (no auth → 401, query token → 200, header token → 200).
   `backend/tests/unit/test_access_log_scrub.py` passes — scrubber
   redacts `access_token=<value>` in `uvicorn.access` records.
9. CI frontend-e2e job is green on the PR.
10. **Manual:** screenshots of `/app/trips/new`, `/app/trips/{id}`
    mid-stream, and `/app/trips/{id}` post-complete saved locally;
    embedded in PR description.
11. No `console.log` / `console.warn` / debug code committed.
12. No new runtime dependency added beyond what's already in
    `frontend/package.json`. (Test-only fakes don't count.)
13. PR A's auth surface is unchanged: `store/auth.ts`, `lib/api/client.ts`,
    `components/providers.tsx`, `hooks/useHasHydrated.ts`,
    `hooks/useCurrentUser.ts`, `app/login/page.tsx`,
    `app/auth/exchange/page.tsx`, `app/page.tsx`, `app/layout.tsx`
    are not modified (except `app/app/page.tsx` for the one-line
    link addition).

## 8. Out-of-PRD context / Out-of-scope follow-ups

- **`/api/trips` list endpoint** — `docs/handoff/REMAINING_WORK.md:300-301`
  flags this. Trip history UI waits on the backend list endpoint.
- **SSE auto-reconnect / refresh-token** — long-cycle resilience.
- **Per-event detailed cards** — ProgressFeed v1 shows a flat list of
  human labels. Richer per-phase detail panels are follow-up.
- **Cycle abort UX** — v1 shows "Cycle aborted: {reason}" in the feed +
  the report view's "No results yet." branch. A distinct error banner
  + retry CTA is follow-up.
- **Streaming the report itself** — v1 fetches the persisted row once
  on terminal state. Streaming partial items as they're joined is a
  natural v2.
- **Shared sign-in helper coverage** — once `e2e/_helpers/auth.ts`
  exists, refactor `auth-flow.spec.ts` to call it too (currently it
  inlines the flow because it's testing the flow itself; keeping it
  inlined is also defensible). Code Agent: leave `auth-flow.spec.ts`
  alone in this PR.
- **Update the handoff doc** — see R10. Separate doc PR.

## 9. Style / naming

- **Tailwind utilities only** — same posture as PR A. No new colors,
  no new spacing scale, no shadcn extractions.
- **No decorative typography.** Per the user's standing rule, cited
  verbatim: *"切记不要为了花里跨张把字体弄得不好看清."* Use the platform
  default font stack from the existing layout.
- **Naming consistency:** `lib/api/trips.ts` not `lib/api/trip.ts`
  (plural — matches the backend route).
  `useTripStream` not `useStreamTrip`. `ProgressFeed` not `EventFeed`
  (the user-facing concept is "progress", not "events").
- **No comments unless the *why* is non-obvious.** Same as PR A §9.
- **`data-testid` discipline:** only where a stable selector is needed
  for the e2e and no accessible-name/role selector would do. Currently
  one: `progress-feed`. Avoid sprinkling them as a substitute for
  accessible roles.
- **Code style:** Prettier (existing `frontend/.prettierrc.json`) +
  ESLint (`eslint-config-next`).

## 10. Frozen contracts

**Empty until team-lead commits the e2e scaffolds.** Two spec files
must be pre-committed by team-lead before Code Agent dispatch:

- `frontend/e2e/trip-new-page.spec.ts` — 3 cases, all `test.fixme`, exact
  assertion text from §4.3 table.
- `frontend/e2e/trip-flow.spec.ts` — 1 case, `test.fixme`, exact
  assertion text from §4.3 table.
- `frontend/e2e/_helpers/auth.ts` — `signInE2E(page, request)` helper as
  specified in §4.2 (last row). If team-lead chooses to also create the
  helper file in the same commit, Code Agent uses it as-is; otherwise
  Code Agent creates it as the first step of implementation since the
  specs `import` it.

Once those land at a known HEAD, this section will be populated with:

| Surface | Locked value | Source |
|---------|--------------|--------|
| trip-new heading | matches `/plan a trip\|new trip/i` | `trip-new-page.spec.ts:<line>` |
| trip-new destination input | `page.getByLabel(/destination/i)` | `trip-new-page.spec.ts:<line>` |
| trip-new submit button | `getByRole("button", { name: /plan\|start\|create/i })` | `trip-new-page.spec.ts:<line>` |
| trip-new validation copy | matches `/required\|destination/i`, fires client-side | `trip-new-page.spec.ts:<line>` |
| trip-detail URL | matches `/\/app\/trips\/[0-9a-f-]{36}/i` | `trip-new-page.spec.ts:<line>` + `trip-flow.spec.ts:<line>` |
| progress feed testid | `data-testid="progress-feed"` | `trip-flow.spec.ts:<line>` |
| progress feed text | matches `/started\|producer\|joiner\|controller\|cycle aborted\|trip complete/i` (within 20s) | `trip-flow.spec.ts:<line>` |
| terminal status attribute | `data-trip-status="complete"` or `"aborted"` (within 60s) | `trip-flow.spec.ts:<line>` |
| report content visible | destination string echoes back | `trip-flow.spec.ts:<line>` |
| SSE auth wire | `GET /api/trips/{id}/stream?access_token=<jwt>` | this PRD §4.1 |
| Backend addition | new dep `current_user_or_sse` in `backend/src/plus_one/core/auth/deps.py`; `trips.py:97-101` switches to it; uvicorn access-log scrubber filter installed in `backend/src/plus_one/main.py`. No other endpoint changes. | this PRD §4.1 |

If Code Agent finds any of these contracts unworkable, **SendMessage
team-lead BEFORE editing any test or spec file**. The default is to
bend the implementation to fit the test.

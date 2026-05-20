# Batch 2g PR B — Trip History List (`/app` redesign + `GET /api/trips`)

**Owner:** Full-stack (backend endpoint + frontend list UI)
**Branch:** `feat/batch2g-pr-b-trip-list` (cut from `main` after batch 2f PR B merges)
**Status:** PRD draft — ready for Code Agent
**Date:** 2026-05-20
**Predecessors:**
- Batch 2f PR A (auth) — `docs/prds/batch2f-pr-a-auth.md` (merged `#14`)
- Batch 2f PR B (trip surface) — `docs/prds/batch2f-pr-b-trips.md`
  (trip create/SSE/detail; this PR builds the *list* on top)

---

## 1. Context

### 1.1 What's there now

`/app` is the authed landing page. As of `feat/batch2f-pr-b-trips` it
renders a "Hello, {user.email}" header, a sign-out button, a one-line
welcome ("Welcome to Plus One. Trip planning UI lands next."), and a
single `<Link href="/app/trips/new">Plan a trip</Link>` button
(`C:\Users\haowenfeng\repo\newproject\frontend\app\app\page.tsx:49-72`).

Once a user submits a trip, they land on `/app/trips/{id}` and watch the
SSE feed + report. Then they have **no way back to their trips** other
than the URL bar. Refresh `/app` and they're greeted by the welcome
copy as if they've never used the product. PRD §4 explicitly lists *"Save
report to My Trips"* as MVP, and `docs/handoff/REMAINING_WORK.md:298-302`
flags `/reports` history as a known follow-up. This PR closes that gap.

### 1.2 Backend gap

The backend has `POST /api/trips`, `GET /api/trips/{id}/stream`, and
`GET /api/trips/{id}`
(`backend\src\plus_one\api\trips.py:52-159`) but no list-all endpoint.
There is no path to enumerate the current user's trips today.

### 1.3 What this PR delivers

1. Backend `GET /api/trips` — paginated list of the caller's trips,
   newest first.
2. Frontend `/app` redesign — list of trip cards, "Plan a new trip" CTA,
   empty state, loading skeleton, error state, and a "Load more" button
   for pagination.

After this PR, a returning user lands on `/app` and immediately sees
their history; clicking any card jumps straight back to `/app/trips/{id}`.

---

## 2. Goals / Non-Goals

### 2.1 Goals

- **G1 — Backend list endpoint.** `GET /api/trips` returns the current
  user's trips, newest first, paginated by opaque cursor, with per-item
  fields sufficient for the list UI (destination, status, created_at,
  latest_report_id, has_report).
- **G2 — Cross-user isolation.** A user can never see another user's
  trips. Asserted by a dedicated integration test.
- **G3 — `/app` becomes a trip history page.** Cards for each trip, a
  prominent "Plan a new trip" CTA, empty state, loading skeleton, error
  state, and a "Load more" button that appends the next page.
- **G4 — Gates remain green.** Backend `just backend-check`, frontend
  `pnpm build && pnpm lint && pnpm exec prettier --check . && pnpm
  typecheck && pnpm test && pnpm exec playwright test --project=chromium`
  all exit 0.
- **G5 — E2E coverage grows by ≥1 new spec.** Add `e2e/trip-list.spec.ts`
  (create 2 trips via API → navigate to `/app` → assert both render →
  click one → land on detail). Update `e2e/app-shell.spec.ts` only if
  required to keep it passing (the existing `/` route asserts are
  unaffected).

### 2.2 Non-Goals (explicit)

The following are deliberately out of scope for this PR. Do not add them
"because they'd be easy":

- **Trip search / filter / sort by destination.** Backlog.
- **Sort other than `created_at DESC`.** No `?order=` param.
- **Trip deletion.** Batch 2j.
- **Trip rename / edit.** Backlog.
- **Bulk operations** (multi-select, mass-delete, etc.). Backlog.
- **Real-time list updates** (websocket / polling for status changes).
  The list is a snapshot at fetch time; the user can refresh. Adding a
  push channel for status changes is a large follow-up — out of scope.
- **Status auto-refresh on the card** even without a server push (e.g.,
  client-side `setInterval`). Same reason — refresh is user-driven.
- **Schema changes.** The `trips` table as defined in
  `backend\src\plus_one\core\db\models.py:164-208` is sufficient
  (`user_id` is already indexed; status has a CHECK constraint).
- **shadcn/ui primitives.** Despite the original brief mentioning `Card`
  and `Badge` shadcn primitives, the codebase **does not have shadcn
  installed** (no `frontend/components/ui/` directory). PR A and PR B
  explicitly chose Tailwind-utility-only ("no shadcn-style extractions" —
  `docs/prds/batch2f-pr-b-trips.md` §3 + §9). This PR matches that
  posture to avoid landing a new dependency surface in a feature PR.
- **i18n.** English only, matches PR A/B.
- **New runtime dependency.** Date humanization uses `Intl.RelativeTimeFormat`
  (browser built-in) — no `date-fns` / `dayjs`.

---

## 3. Backend API Contract

```
GET /api/trips?limit=20&cursor=<opaque>
Authorization: Bearer <jwt>

200 OK
{
  "trips": TripListItem[],
  "next_cursor": string | null
}

TripListItem = {
  "trip_id":          string,   // UUID
  "destination":      string,
  "status":           string,   // "pending" | "running" | "complete" | "aborted"
  "created_at":       string,   // ISO-8601 UTC, e.g. "2026-05-20T14:30:00+00:00"
  "latest_report_id": string | null,  // UUID or null
  "has_report":       boolean   // convenience: latest_report_id is not null
}
```

### 3.1 Query parameters

| Name | Type | Default | Constraint |
|------|------|---------|------------|
| `limit` | int | `20` | `1 <= limit <= 100`; out-of-range → `422` |
| `cursor` | str (opaque) | omit → first page | base64url; malformed → `400 invalid_cursor` |

### 3.2 Error responses

| Status | Body `detail` | Cause |
|--------|---------------|-------|
| `401` | `Missing or malformed Authorization` | No / bad Bearer (existing dep behavior) |
| `400` | `invalid_cursor` | Cursor is not decodable base64url-JSON or fails Pydantic validation |
| `422` | (FastAPI default) | `limit` out of range or non-integer |

### 3.3 Sort + filter

- Sort: `created_at DESC, id DESC` (id is the tiebreaker — see §4).
- Filter: `user_id == current_user.id`. No other filters.
- Companions / reports / trace are NOT included (heavy; not needed for
  the list view).

### 3.4 Pydantic models

Both live in `backend/src/plus_one/api/trips.py` next to the existing
`TripDetail`:

```python
class TripListItem(BaseModel):
    trip_id: UUID
    destination: str
    status: str
    created_at: datetime
    latest_report_id: UUID | None = None
    has_report: bool


class TripListResponse(BaseModel):
    trips: list[TripListItem]
    next_cursor: str | None = None
```

### 3.5 Auth

`user: Annotated[User, Depends(current_user)]` — same header-only Bearer
auth as `POST /api/trips` and `GET /api/trips/{id}`
(`backend\src\plus_one\core\auth\deps.py`). The SSE-only
`current_user_or_sse` fallback is NOT used here.

---

## 4. Cursor Format

The cursor is opaque to the client. Internally, **base64url-encoded JSON
of the last item from the previous page's sort tuple**:

```
cursor = base64url(json.dumps({"created_at": "2026-05-20T14:30:00+00:00", "id": "<uuid>"}))
```

### 4.1 Why both fields

`created_at` alone is not sufficient because:

1. Two trips created in the same millisecond would share `created_at`
   and the "where created_at < cursor.created_at" filter would
   non-deterministically include or exclude one of them across pages.
2. The DB stores `timestamptz` at microsecond precision in Postgres,
   but tests / dev fixtures often create batches inside a single
   `session_scope` where rows can collide on timestamp.

Including `id` as the secondary key gives a total order; the page
boundary becomes `WHERE (created_at, id) < (cursor.created_at, cursor.id)`
which is stable, repeatable, and unaffected by new inserts at the head
of the list.

### 4.2 Why opaque (not just `created_at` as a query param)

- Hides the implementation: future swap to keyset on `(id,)` or to a
  proper window-function-based cursor doesn't break clients.
- Discourages clients from constructing cursors themselves (no
  "increment by 1 day" hacks).
- Pydantic validates the decoded payload on every request, so a hostile
  client can't inject SQL via the cursor — the only fields read are
  `created_at: datetime` and `id: UUID`, both type-checked.

### 4.3 Encode / decode helpers

Two private module-level functions in `backend/src/plus_one/api/trips.py`:

```python
class _Cursor(BaseModel):
    created_at: datetime
    id: UUID


def _encode_cursor(c: _Cursor) -> str:
    raw = c.model_dump_json().encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(s: str) -> _Cursor:
    # Re-pad before decode (urlsafe_b64encode strips '=' in encode).
    padding = "=" * (-len(s) % 4)
    try:
        raw = base64.urlsafe_b64decode(s + padding)
        return _Cursor.model_validate_json(raw)
    except (binascii.Error, ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_cursor",
        ) from exc
```

---

## 5. Pagination Semantics

### 5.1 First page

Request: `GET /api/trips?limit=20`. No cursor.

Query:
```sql
SELECT id, destination, status, created_at
FROM trips
WHERE user_id = :uid
ORDER BY created_at DESC, id DESC
LIMIT 21         -- limit + 1 to detect "more"
```

If we get `<= limit` rows, `next_cursor = null`. If we get `limit + 1`,
drop the last and set `next_cursor = _encode_cursor({created_at, id})`
of the **last returned** (kept) row.

### 5.2 Subsequent page

Request: `GET /api/trips?limit=20&cursor=<opaque>`. Decode → `(ts, id)`.

Query:
```sql
SELECT id, destination, status, created_at
FROM trips
WHERE user_id = :uid
  AND (created_at, id) < (:ts, :id)
ORDER BY created_at DESC, id DESC
LIMIT 21
```

(SQLAlchemy expresses tuple-comparison via
`sqlalchemy.tuple_(Trip.created_at, Trip.id) < (ts, id)`; Postgres
supports this directly.)

### 5.3 Stability under concurrent inserts

If a new trip is created mid-pagination (between fetching page 1 and
page 2), the new trip has `created_at > cursor.created_at` and is
therefore **excluded** from subsequent pages. The user sees it only on
a fresh load. This is the desired behavior for "load more" — pagination
is over a logical snapshot anchored by the first page's cursor.

### 5.4 Latest-report join

For each trip in the page, also fetch the latest report id. Implemented
as a correlated subquery to avoid an N+1:

```sql
SELECT
  t.id,
  t.destination,
  t.status,
  t.created_at,
  (
    SELECT r.id
    FROM reports r
    WHERE r.trip_id = t.id
    ORDER BY r.created_at DESC
    LIMIT 1
  ) AS latest_report_id
FROM trips t
WHERE t.user_id = :uid
  AND (t.created_at, t.id) < (:ts, :id)   -- omit on first page
ORDER BY t.created_at DESC, t.id DESC
LIMIT 21
```

Set `has_report = latest_report_id is not None` in Python after the
fetch.

---

## 6. Files to Change

All paths absolute under `C:\Users\haowenfeng\repo\newproject\`.

| Path | New? | Purpose |
|------|------|---------|
| `backend\src\plus_one\api\trips.py` | modify | Add `TripListItem` + `TripListResponse` Pydantic models. Add `_Cursor`, `_encode_cursor`, `_decode_cursor` helpers. Add `GET /api/trips` route handler `list_trips(...)`. **Route declaration order matters** — declare `list_trips` BEFORE the existing `get_trip(trip_id)` so FastAPI does not route `/api/trips` to the path-param endpoint as `trip_id=""` (actually FastAPI handles this fine because path params are typed UUID, but explicit order is safer + reads better). |
| `backend\tests\integration\test_trips_list.py` | new | Pytest cases (see §10). Reuses the stub-session pattern from `backend\tests\integration\test_trips_sse_auth.py` where feasible; uses a real ephemeral test DB only if the cursor + tuple-comparison logic can't be exercised with the stub (likely needs the real DB — see §10). |
| `frontend\lib\schemas\trips.ts` | modify | Append zod schemas: `TripListItem`, `TripListResponse`. Export both schema + inferred type, same pattern as existing `TripDetail`. |
| `frontend\lib\api\trips.ts` | modify | Add `listTrips({ limit, cursor })`: builds query string, calls `apiFetch`, parses response with `TripListResponse`. |
| `frontend\hooks\useTrips.ts` | new | `useInfiniteQuery` wrapper from `@tanstack/react-query`. Disabled until `hydrated && !!token`. `queryKey: ["trips", "list"]`. `queryFn: ({ pageParam }) => listTrips({ limit: 20, cursor: pageParam })`. `getNextPageParam: (last) => last.next_cursor ?? undefined`. `initialPageParam: undefined`. Returns the hook result; consumers flatten pages. |
| `frontend\app\app\page.tsx` | rewrite | New list page (see §7). Keeps the existing hydration gate, sign-out button, and "Hello, {email}" greeting; replaces the welcome copy + single "Plan a trip" link with header + trip list + load-more. |
| `frontend\components\trips\TripCard.tsx` | new | Single trip card component. Props: `TripListItem`. Renders destination, humanized date, status badge, and is wrapped in a `<Link href={\`/app/trips/${trip.trip_id}\`}>`. See §8 for design. |
| `frontend\components\trips\TripListEmpty.tsx` | new | Empty state shown when the first page returns `trips: []`. Friendly copy + emphasized "Plan a new trip" CTA. |
| `frontend\components\trips\TripCard.test.tsx` | new | Vitest + RTL. Asserts destination text, status badge text, link `href` attribute, and that the date renders in *one* of the two formats (regex). |
| `frontend\hooks\useTrips.test.ts` | new | Vitest mocking `listTrips`. Asserts the hook is disabled pre-hydration; once enabled, pages flatten correctly; `fetchNextPage` uses the previous `next_cursor`. |
| `frontend\lib\schemas\trips.test.ts` | modify | Add cases: `TripListItem` parses a valid payload; rejects missing `has_report`; `TripListResponse` accepts `next_cursor: null`. |
| `frontend\lib\api\trips.test.ts` | modify | Add cases for `listTrips`: builds query string, parses response, propagates `ApiError` on non-2xx. |
| `frontend\e2e\app-shell.spec.ts` | modify | Add `{ path: "/app", label: "app" }` to `PUBLIC_ROUTES`? **No** — `/app` requires auth so a plain GET will redirect to `/login` (200 from Next, but the asserted body content differs). **Decision: leave `app-shell.spec.ts` unchanged.** The `/` route assertions are unaffected by this PR. Authed `/app` behavior is covered by the new `trip-list.spec.ts`. |
| `frontend\e2e\trip-list.spec.ts` | new | New spec — see §9. |

**Files NOT touched** (frozen, verify in PR diff):
`store/auth.ts`, `lib/api/client.ts`, `lib/sse.ts`, `hooks/useTrip.ts`,
`hooks/useTripStream.ts`, `hooks/useCurrentUser.ts`, `hooks/useHasHydrated.ts`,
`components/providers.tsx`, `app/login/page.tsx`, `app/auth/exchange/page.tsx`,
`app/page.tsx`, `app/layout.tsx`, `app/app/trips/new/page.tsx`,
`app/app/trips/[id]/page.tsx`, `components/trips/TripForm.tsx`,
`components/trips/ProgressFeed.tsx`, `components/trips/ReportView.tsx`,
`backend/src/plus_one/api/trips.py` (existing POST/GET/SSE handlers and
`current_user` dep — additive only), `backend/src/plus_one/core/db/models.py`.

---

## 7. Frontend — `/app` Redesign

### 7.1 Layout

```
<main>
  <header>
    <div>
      <h1>My Trips</h1>
      <p>Hello, {user.email}</p>   ← preserved from current /app
    </div>
    <div>
      <Link href="/app/trips/new">Plan a new trip</Link>
      <button onClick={onSignOut}>Sign out</button>
    </div>
  </header>

  {/* Body */}
  {isLoading             → <SkeletonList /> }
  {isError               → <ErrorState onRetry={refetch} /> }
  {isSuccess && empty    → <TripListEmpty /> }
  {isSuccess && !empty   → (
      <ul>
        {trips.map(t => <TripCard key={t.trip_id} trip={t} />)}
      </ul>
      {hasNextPage && (
        <button onClick={fetchNextPage} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? "Loading…" : "Load more"}
        </button>
      )}
  )}
</main>
```

### 7.2 Hydration gate

Identical to current `/app/page.tsx:23-46` — return `Loading…` until
`hydrated && token && user`. Move the user/sign-out logic verbatim; only
the *body* of the authed branch is rewritten.

### 7.3 Skeleton

Three placeholder cards (gray rectangles) while the first page fetches.
No animation library — `bg-foreground/10 animate-pulse` is enough. The
skeleton MUST NOT be a separate route — it's the body content while
`isLoading` is true.

### 7.4 Error state

`<p role="alert">Couldn't load your trips. <button onClick={onRetry}>
Try again</button></p>`. Simple — same posture as PR B's inline errors.

### 7.5 Pagination affordance

A single `<button>Load more</button>` below the list, visible only when
`hasNextPage`. Clicking calls `fetchNextPage()`. Multiple clicks while
in flight are debounced by the disabled state. No infinite-scroll
sentinel for v1.

---

## 8. Date Formatting + Status Badge

### 8.1 Date strategy (DOCUMENTED CHOICE)

**Hybrid: relative for ≤7 days, absolute YYYY-MM-DD for older.**

| Age | Format | Examples |
|-----|--------|----------|
| `< 60s` | `just now` | "just now" |
| `< 60min` | `N minutes ago` (Intl) | "5 minutes ago" |
| `< 24h` | `N hours ago` (Intl) | "3 hours ago" |
| `< 7d` | `N days ago` (Intl) | "2 days ago" |
| `>= 7d` | absolute `YYYY-MM-DD` | "2026-05-13" |

Rationale: relative is great for recency cues but useless for old trips
("482 days ago" is just noise — you can't book a flight off that). The
cutoff at 7 days matches what GitHub uses for issue lists.

Implementation: a single helper `formatTripDate(iso: string): string` in
`frontend/lib/format.ts` (new file? — actually, place it inline in
`TripCard.tsx` for now since it has exactly one caller; promote to
`lib/format.ts` when the second caller appears). Use `Intl.RelativeTimeFormat("en", { numeric: "auto" })` for the relative branch and `toISOString().slice(0, 10)` for the absolute branch. **No `date-fns` / `dayjs` dependency.**

Hydration risk: `Intl.RelativeTimeFormat` is deterministic given the
same inputs on the same Node/Chromium version. The relative output
depends on `Date.now()`, which differs between SSR and client. To avoid
a hydration mismatch, render the date inside an effect-mounted span:

```tsx
const [label, setLabel] = useState<string>("");
useEffect(() => { setLabel(formatTripDate(trip.created_at)); }, [trip.created_at]);
return <time dateTime={trip.created_at}>{label}</time>;
```

(`label` is empty during SSR so no mismatch. The `<time dateTime>`
attribute keeps the machine-readable timestamp accessible to assistive
tech even while the visible label is computing.)

### 8.2 Status badge

A small inline `<span>` with status-appropriate Tailwind classes (no
shadcn `Badge`). Tone matches PR B's posture: neutral utility, not
decorative.

| Status | Copy | Classes |
|--------|------|---------|
| `pending` | "Pending" | `bg-foreground/10 text-foreground/70` |
| `running` | "Running" | `bg-blue-100 text-blue-800` |
| `complete` | "Complete" | `bg-green-100 text-green-800` |
| `aborted` | "Aborted" | `bg-foreground/10 text-foreground/60` (muted, NOT red — see §12) |

Implementation: a small `<StatusBadge status={trip.status} />` component
inside `TripCard.tsx` (not a separate file). Use a `Record<TripStatus,
{label: string; classes: string}>` lookup.

---

## 9. E2E — `frontend/e2e/trip-list.spec.ts` (new)

```ts
import { test, expect, request as pwRequest } from "@playwright/test";
import { signInE2E } from "./_helpers/auth";

test.describe("trip list (/app)", () => {
  test("empty state shows the plan-a-trip CTA", async ({ page, request }) => {
    await signInE2E(page, request);
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: /my trips/i })).toBeVisible();
    await expect(page.getByText(/no trips yet|your first trip|plan a new trip/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /plan a new trip/i })).toBeVisible();
  });

  test("creating two trips renders both cards; clicking one navigates to detail", async ({
    page, request,
  }) => {
    await signInE2E(page, request);

    // Drive the two trip creations through the UI (so we know the token
    // is already in the page's auth store). Two distinct destinations
    // so the list assertion is unambiguous.
    for (const dest of ["Tokyo", "Osaka"]) {
      await page.goto("/app/trips/new");
      await page.getByLabel(/destination/i).fill(dest);
      await page.getByRole("button", { name: /plan|start|create/i }).click();
      await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i, { timeout: 10_000 });
    }

    await page.goto("/app");
    await expect(page.getByRole("heading", { name: /my trips/i })).toBeVisible();
    // Both destinations render as cards.
    await expect(page.getByText(/Tokyo/)).toBeVisible();
    await expect(page.getByText(/Osaka/)).toBeVisible();

    // Click one and confirm we land on the detail page.
    await page.getByText(/Tokyo/).first().click();
    await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i, { timeout: 10_000 });
  });
});
```

The brief mentioned "create 2 trips via API" — we drive through the UI
instead because each browser-level `signInE2E` user has a unique JWT in
the page's auth store, and minting a second trip via raw `request.post`
would require also injecting the token, doubling the surface. UI
creation re-uses the existing trip form, takes ~2 seconds extra per
trip, and tests one more code path for free.

**Total new e2e cases:** 2. Combined with the 12 from batch 2f → 14
across 7 spec files.

### 9.1 Existing spec touch-ups

- `e2e/app-shell.spec.ts` — leave unchanged. `/` route assertion is
  independent of this PR.
- `e2e/app-page.spec.ts` — **does not exist** in the current tree (the
  brief mentioned it speculatively; current authed `/app` assertions
  live inside `e2e/auth-flow.spec.ts`). Confirmed via `ls
  frontend/e2e/`. Do not create it.

---

## 10. Backend Tests — `backend/tests/integration/test_trips_list.py`

A real ephemeral DB is required for the cursor + tuple-comparison logic
(stub session can't easily emulate `ORDER BY`). Use the same fixtures as
the existing integration suite. If no fixture exists, create one that
spins up a per-test Postgres schema (mirror what `test_trips_sse_auth.py`
does, but with a real session instead of `_StubSession`). Confirm
fixture name during implementation.

Cases (test names verbatim):

| # | Name | What it asserts |
|---|------|-----------------|
| 1 | `test_list_trips_requires_auth` | No `Authorization` header → 401. |
| 2 | `test_list_trips_empty_user` | Authed user with zero trips → 200, `{trips: [], next_cursor: null}`. |
| 3 | `test_list_trips_single_page` | User with 3 trips → 200, `len(trips) == 3`, `next_cursor is None`, ordered by `created_at DESC`. Assert per-item fields are all present (trip_id, destination, status, created_at, latest_report_id, has_report). |
| 4 | `test_list_trips_paginates_with_cursor` | User with 25 trips, `?limit=10` → first page has 10 + `next_cursor`. Decode the cursor, GET again → second page has 10 + `next_cursor`. Third page has 5 + `next_cursor is None`. Assert no row appears on two pages (set-difference). |
| 5 | `test_list_trips_default_limit_20` | User with 25 trips, no `?limit` → first page has 20 items + `next_cursor`. |
| 6 | `test_list_trips_limit_clamped` | `?limit=0` → 422; `?limit=101` → 422; `?limit=100` → 200 with up to 100 items. |
| 7 | `test_list_trips_invalid_cursor` | `?cursor=not-base64` → 400 with `detail == "invalid_cursor"`. `?cursor=<valid-base64-of-garbage>` → 400 same. |
| 8 | `test_list_trips_isolates_users` | Create user A's 3 trips and user B's 2 trips. Auth as A → only A's trips returned. Auth as B → only B's trips. **This is the load-bearing security test.** |
| 9 | `test_list_trips_has_report_flag` | Create trip without report → `has_report is False`, `latest_report_id is None`. Create trip with one report → `has_report is True`, `latest_report_id` is that report's UUID. Create trip with two reports → `latest_report_id` is the most recent (by `created_at`). |
| 10 | `test_list_trips_orders_by_created_at_desc` | Create 5 trips with explicit `created_at` values out of insertion order; assert response order is strictly descending. |

If the cursor's `(created_at, id) < ...` tuple comparison can't be
exercised reliably with the test DB's clock resolution, case 4 should
explicitly stamp `created_at` to controlled values rather than relying
on insertion timing.

---

## 11. Auth / Authorization

`GET /api/trips` depends on `current_user` (header-only Bearer). The
handler filters `WHERE user_id = current_user.id`. There is no admin
override and no team / share semantics in v1.

Test #8 (`test_list_trips_isolates_users`) is the explicit isolation
proof. Without it any future refactor that swaps the `WHERE` clause for
a join could silently leak rows across users.

---

## 12. Race / Consistency Notes

### 12.1 `latest_report_id is null`

A trip that is still `running` (or `pending`) has no persisted report
yet — the runner publishes the report row only on cycle completion
(`trip_runner.py:260-289`). The card renders the *Running* badge (blue);
clicking still navigates to `/app/trips/{id}` where the SSE consumer
(from PR B) takes over and renders the in-progress feed. No special
handling needed in the list — the existing detail page already handles
the in-progress state.

### 12.2 Status changing mid-fetch

If a trip's status flips from `running` → `complete` between the user
loading `/app` and clicking a card, the list view shows the stale
status. The detail page re-fetches and shows the current truth. No
push channel — list is stale by design (§2.2).

### 12.3 New trips created mid-pagination

Covered in §5.3 — pagination is a logical snapshot anchored by the first
page's cursor. New trips appear only on a fresh load.

### 12.4 `PLUS_ONE_ALLOW_REAL_LLM=0` (e2e env)

This is the same gotcha PR B documented. In CI's e2e env, every cycle
aborts because no real LLM provider can be constructed
(`playwright.config.ts:65-74` does not set the flag). All trips created
during `trip-list.spec.ts` will end up `aborted` within seconds — the
list correctly shows them with the *Aborted* badge.

**Copy + color choice for `aborted`:** mute (gray), not red. Rationale:
in the e2e harness, every trip is aborted by design, and a wall of red
badges would be visually alarming and incorrect — abort isn't an error,
it's a terminal state. A user-facing aborted trip in production is also
not catastrophic (the runner caught a soft failure and shut down
cleanly). Reserve red for actual hard errors (network failures, 5xx).

---

## 13. Acceptance Criteria

Order matters — G2 (isolation) is non-negotiable; gate on it first.

1. **(G2)** `pytest backend/tests/integration/test_trips_list.py -k isolates_users -q` passes.
2. **(G1)** All 10 backend test cases in §10 pass.
3. `just backend-check` exits 0 (ruff + mypy + unit + integration).
4. `cd frontend && pnpm exec playwright test --project=chromium`
   passes — 14 cases across 7 spec files; the 12 from batch 2f stay
   green and `trip-list.spec.ts` adds 2.
5. `cd frontend && pnpm build` exits 0; no hydration warnings (esp.
   re: the date formatter — see §8.1).
6. `cd frontend && pnpm lint` exits 0.
7. `cd frontend && pnpm exec prettier --check .` exits 0.
8. `cd frontend && pnpm typecheck` exits 0.
9. `cd frontend && pnpm test` exits 0; new unit tests for
   `lib/api/trips.ts` (`listTrips`), `lib/schemas/trips.ts`
   (`TripListItem` / `TripListResponse`), `hooks/useTrips.ts`, and
   `components/trips/TripCard.tsx` all pass.
10. No `console.log` / `console.warn` / debug code committed.
11. No new runtime dependency in `frontend/package.json` or
    `backend/pyproject.toml` (test-only fakes don't count;
    `Intl.RelativeTimeFormat` is built-in).
12. Manual: screenshots of `/app` empty state, `/app` with ≥2 trips,
    and `/app` with `hasNextPage` (≥21 trips → load-more button visible)
    saved locally and embedded in PR description.
13. PR B's surface unchanged: `app/app/trips/new/page.tsx`,
    `app/app/trips/[id]/page.tsx`, `components/trips/TripForm.tsx`,
    `components/trips/ProgressFeed.tsx`, `components/trips/ReportView.tsx`,
    `hooks/useTrip.ts`, `hooks/useTripStream.ts`, `lib/sse.ts` are
    not modified.

---

## 14. Risks & Mitigations

| ID | Risk | Mitigation |
|----|------|------------|
| R1 | **Cross-user leak via the new endpoint.** A bad `WHERE` clause is the worst possible bug here. | Test #8 (`test_list_trips_isolates_users`) is the load-bearing check; it must run on every backend CI invocation. Code Agent: write the test BEFORE the handler (TDD), and confirm it fails before the handler exists. |
| R2 | **Cursor injection.** Hostile client crafts a cursor that maps to a different user's row. | The cursor only encodes `(created_at, id)` — both fed into a parameterized SQLAlchemy query with `WHERE user_id = current_user.id` ALWAYS in the clause. The `id` from the cursor narrows the keyset window; it cannot widen the user filter. Pydantic validates types on decode, so non-UUID `id` returns 400 before the query. |
| R3 | **Hydration mismatch on the date column.** SSR renders "2 days ago" computed against `Date.now()` on the server; client renders the same against client `Date.now()`; if minute boundaries cross between SSR and hydration, React warns. | Use the effect-mounted span pattern from §8.1 — SSR renders empty `<time>`, client fills in after mount. Verified by manual `pnpm build` + load. |
| R4 | **N+1 on `latest_report_id`.** Naive: for each trip, separate query for its latest report. 20 trips → 21 queries. | Use the correlated subquery in §5.4. Postgres optimizes this well; one round-trip. Add a comment in the handler explaining why it's a subquery, not `joinedload`. |
| R5 | **`PLUS_ONE_ALLOW_REAL_LLM=0` makes every e2e trip abort.** All cards in `trip-list.spec.ts` show the aborted badge. | Documented and intentional — §12.4. Badge copy is "Aborted" (gray), not "Error" (red). E2E spec asserts the destinations are visible, not the status text. |
| R6 | **Load-more button while `hasNextPage` is stale.** Between page 1 and page 2, the user creates a new trip in another tab. Page 2 omits the new trip (it's at the head, > cursor). Refresh fixes it. | Acceptable for v1 — pagination is a snapshot. Document in a code comment on `useTrips.ts` so a future "live" refactor knows the contract. |
| R7 | **TanStack Query devtools accidentally shipped.** Adding `useInfiniteQuery` is a common moment to drop in `@tanstack/react-query-devtools`. | Don't. The Providers tree already has whatever PR A wired; this PR adds zero deps. PR description should grep for `react-query-devtools` and confirm zero hits. |
| R8 | **`base64.urlsafe_b64encode` strips `=` padding inconsistently across implementations.** Frontend never decodes the cursor (opaque), so client-side decoding is not a concern; backend symmetric encode/decode is. | The `_encode_cursor` strips `=`; `_decode_cursor` re-pads to `len % 4`. Round-trip is unit-tested as part of case #4. |
| R9 | **Backend test fixture drift.** If `test_trips_sse_auth.py`'s stub-session pattern is used, the new tests would silently bypass the actual SQL. | The new tests need a real DB (tuple comparison + ORDER BY) — do NOT reuse the `_StubSession` pattern. Use whatever real-DB fixture is established in `backend/tests/conftest.py` / `backend/tests/integration/conftest.py`; if none exists, create a minimal `async_session` fixture that runs against a transactional rollback per test. Confirm during implementation. |
| R10 | **`Intl.RelativeTimeFormat` browser support.** Targets ES2020+ — supported in all evergreen browsers including current Chromium that Playwright runs. | No polyfill needed. If a future target list adds older browsers, swap in a small helper. |
| R11 | **Skeleton flash.** First-page query is fast (single SQL); skeleton might flash for <100ms. | Acceptable — better than blank. If it proves jarring, add a 150ms `min-h` to the skeleton container. Out of scope for v1. |

---

## 15. Style / naming

- **Tailwind utilities only** — same as PR A/B (§9 of both prior PRDs).
- **No new colors** other than the badge palette in §8.2.
- **No decorative typography.** *"切记不要为了花里跨张把字体弄得不好看清."*
- **No comments unless the *why* is non-obvious.**
- **`data-testid` discipline:** prefer accessible roles
  (`getByRole("heading", { name: /my trips/i })`,
  `getByRole("link", { name: /plan a new trip/i })`). Avoid sprinkling
  test ids. The e2e spec relies on role + text only.
- **Naming consistency:** `useTrips` (plural — matches the route);
  `listTrips`; `TripCard`; `TripListEmpty`. NOT `useTripList` or `TripsList`.

---

## 16. Open Questions / Confirmations Before Implementation

None blocking. The following are reviewer-confirm-on-PR items:

1. Date hybrid cutoff at 7 days — happy to bump to 14 if reviewer
   prefers, but 7 matches GitHub.
2. `aborted` badge as gray, not red — see §12.4 rationale. Reviewer can
   push back if they want a softer red (e.g., `text-red-700/60`) instead.
3. Skeleton: 3 placeholder cards — could be 5; pick a number and move on.

# Batch 2j PR A — Post-report actions (Share / Export / Delete)

> Status: PRD-Agent reviewed, ship-ready.
> Depends on: Batch 2g PR B merged (trip list page — needed to host the
> per-row delete affordance; this PR ships the per-trip-detail-page
> affordance regardless).
> Out of this PR: conversational refinement (Batch 2j PR B), share
> analytics, scheduled cleanup, rate-limiting (see §10).

## 1. Context

`docs/prd.md` §4 "Post-report actions (MVP)":

- Save report to "My Trips" — already delivered by Batch 2g PR B
  (trips persist on creation; the list page surfaces them).
- Share via link.
- Export Markdown / PDF.
- Conversational refinement ("change Day 2 to a different area").

This batch covers Share + Export (Markdown + PDF) + Delete.
Refinement is deferred to Batch 2j PR B (separate plan — touches cycle
runner, prompt design, new SSE events).

## 2. Locked product decisions (do not relitigate)

- Share link: signed, opaque token; DB-backed `shared_trips` table;
  30-day TTL; revokable.
- Public unauthed GET endpoint `/api/shared/{token}` + frontend route
  `/share/[token]`.
- Export Markdown: pure client-side, no backend.
- Export PDF: `window.print()` + `@media print` stylesheet, no PDF
  library.
- Delete trip: owner-only, cascade to reports + shared_trips; 409 if
  `status='running'`.
- Confirmation modal via shadcn `AlertDialog`.

## 3. Goals

- Owner can mint a share URL from `/app/trips/[id]`, copy it, see the
  expiry, and revoke it.
- An anonymous visitor opening `/share/<token>` sees the read-only
  report; expired / revoked / unknown tokens get a clean empty state,
  not a stack trace.
- Owner can download a Markdown file of the report from the trip
  detail page (client-only).
- Owner can trigger the browser print dialog from the trip detail
  page and get a readable PDF (Chrome-tested).
- Owner can delete a non-running trip; cascade removes its `reports`
  and `shared_trips` rows; running trips return 409.

## 4. Non-goals (this PR)

- Conversational refinement (Batch 2j PR B).
- Server-side PDF generation.
- Share-link analytics / access logs.
- Scheduled cleanup of expired `shared_trips` rows (lazy 404 instead;
  see §6.1).
- Rate-limiting `/api/shared/{token}` (32-byte random token has ~10^57
  keyspace — brute-force is not credible; see §7).
- Embed widgets, social-card previews (OpenGraph).
- Bulk export / batch operations.
- Multi-region share URL signing.

## 5. Approach

### 5.1 Share link

#### Token strategy

`share_token = secrets.token_urlsafe(24)` → 32 chars of URL-safe
base64, 192 bits of entropy. Stored as the primary key of
`shared_trips`. The token is the *only* secret; resolution is a
single PK lookup. No HMAC over `trip_id`: random is unguessable by
definition and HMAC adds nothing if the token itself isn't shown to
or derivable by clients without server cooperation. Citations:

- entropy floor: `secrets.token_urlsafe(24)` ≥ 192 bits, far above the
  128-bit best-practice threshold for unguessable tokens
- precedent in repo: `MagicLinkToken.token` is similarly an opaque
  string PK (see `backend/src/plus_one/core/db/models.py:290`).

#### DB schema (new table)

```python
# backend/src/plus_one/core/db/models.py — append after Report class
class SharedTrip(Base, TimestampMixin):
    """A revokable public share link for a Trip."""

    __tablename__ = "shared_trips"
    __table_args__ = (
        Index("ix_shared_trips_trip_id", "trip_id"),
        Index("ix_shared_trips_expires_at", "expires_at"),
    )

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
```

Notes:

- `String(64)` is sized for `token_urlsafe(24)` (32 chars) with
  comfortable headroom if we ever bump the entropy.
- `ondelete="CASCADE"` on both FKs means dropping a Trip or User
  automatically drops the share rows at the DB layer (matches
  existing pattern at `models.py:90, 125, 147, 156, 181, 221`).
- The ORM-side `Trip.shared_trips` relationship is declared with
  `cascade="all, delete-orphan"` so `session.delete(trip)` collects
  the children inside the unit-of-work — important because the FastAPI
  test fixture talks to async ORM, not raw SQL. The DB-level
  `ondelete='CASCADE'` is the belt; the ORM cascade is the
  suspenders — both stay.
- No `unique` on `trip_id`: a user may want multiple live links (e.g.
  one for family, one to mail later). Not in scope for v1 UI, but the
  schema doesn't preclude it.

Add to `Trip`:

```python
shared_trips: Mapped[list[SharedTrip]] = relationship(
    "SharedTrip",
    back_populates="trip",
    cascade="all, delete-orphan",
)
```

#### Alembic migration

Filename: `backend/alembic/versions/20260520_0002_shared_trips.py`

- Revision id: `20260520_0002` (date-prefixed counter matches existing
  `20260513_0001_initial_schema.py` convention).
- `down_revision: "20260513_0001"`.
- `upgrade()`: create table with both FKs (`ondelete='CASCADE'`),
  PK on `token`, two indexes (`ix_shared_trips_trip_id`,
  `ix_shared_trips_expires_at`), `created_at`/`updated_at` columns
  with `server_default=sa.text("now()")` to match the
  `TimestampMixin` pattern used in the initial migration
  (`20260513_0001_initial_schema.py:37, 78, 107`).
- `downgrade()`: drop the two indexes then `drop_table("shared_trips")`.
- Constraint names follow `op.f("...")` so they pick up the project's
  naming convention (mirrors initial migration style).

#### Endpoints

All mounted on existing routers; one new router file.

| Method | Path | Auth | Owner-only | Returns |
|---|---|---|---|---|
| POST | `/api/trips/{trip_id}/share` | yes | yes | `{token, share_url, expires_at}` |
| DELETE | `/api/trips/{trip_id}/share/{token}` | yes | yes | 204 |
| GET | `/api/shared/{token}` | **no** | — | read-only trip payload (see §5.1.4) |
| DELETE | `/api/trips/{trip_id}` | yes | yes | 204 (409 if running) |

POST handler (sketch — match style of `backend/src/plus_one/api/trips.py:63`):

- Load Trip; 404 if missing or `trip.user_id != user.id`.
- Generate token, `expires_at = datetime.now(UTC) + timedelta(days=30)`.
- Insert SharedTrip, commit.
- Compose `share_url = f"{settings.frontend_base_url}/share/{token}"`
  (new setting; defaults to `http://localhost:3000` for dev parity
  with the existing CORS origin at `main.py:84`).

DELETE-share handler:

- 404 if SharedTrip not found, owned by another user, or `trip_id`
  in path doesn't match the row's `trip_id` (defensive — defends
  against URL-tampering across one's own trips).
- `session.delete(row); await session.commit()`.

GET shared handler (new file `backend/src/plus_one/api/shared.py`):

- No `Depends(current_user)`.
- Lookup SharedTrip by PK.
- If absent OR `expires_at <= datetime.now(UTC)` → return 404 with
  `detail="share_not_found_or_expired"`. **Do not** distinguish
  "expired" from "never existed" to the unauthed caller — token
  enumeration leakage is already a non-issue but free silence is
  cheaper than free signal.
- Load Trip and latest Report (same query shape as
  `trips.py:148-151`).
- Return a `SharedTripResponse` that **omits** `user_id`,
  `created_by`, `trace`, and token-cost fields. Public payload:
  `{destination, status, content, shared: true, expires_at}`.

#### Backend pagination/race notes

- POST share: no `SELECT FOR UPDATE` needed — there's no read-modify-
  write on Trip itself; we only insert into SharedTrip and the unique
  PK guards against accidental token collision (which is itself a
  cryptographic absurdity at 192 bits).
- DELETE trip: wrap status check + delete in a single transaction
  (default session is already a transaction). Recheck status inside
  the txn:
  ```python
  trip = await session.get(Trip, trip_id, with_for_update=True)
  if trip.status == "running": raise HTTPException(409, "trip_running")
  await session.delete(trip); await session.commit()
  ```
  `with_for_update=True` blocks a concurrent worker UPDATE from
  flipping `pending → running` between our check and the delete.

#### Router registration

In `backend/src/plus_one/main.py:90` (after `trips_router`):

```python
from plus_one.api.shared import router as shared_router
app.include_router(shared_router)
```

The new router uses `APIRouter(prefix="/api/shared", tags=["shared"])`
mirroring `trips.py:31`.

### 5.2 Export Markdown

Pure client-side. New file `frontend/lib/report/exportMarkdown.ts`:

```ts
export function reportToMarkdown(trip: TripDetailT): string
export function downloadMarkdown(trip: TripDetailT): void  // Blob + a.download
```

Layout:

```markdown
# Trip to {destination}

Status: {status} · Generated: {created_at}

---

## Local Gems
- **{title}**: {summary}
  - Sources: [reddit](...), [xhs](...)

## Tourist Traps
...

## Disagreement
...
```

Filename: `${slug(destination)}-${YYYY-MM-DD}.md`. No emoji in
filename (Windows / macOS Finder render them inconsistently); emoji
in body markdown only if `trip.content` already contains them.

Button on `/app/trips/[id]` triggers
`URL.createObjectURL(new Blob([md], {type: "text/markdown"}))` and a
synthetic `<a download>` click; revoke URL on next tick.

### 5.3 Export PDF

`window.print()` + a print stylesheet. Add to `frontend/app/globals.css`
(it's a single small block — no separate `print.css` file):

```css
@media print {
  /* Hide chrome */
  nav, header button, [data-print-hide],
  .progress-feed, [role="alert"] { display: none !important; }
  /* Force readable contrast */
  :root {
    --background: 0 0% 100%;
    --foreground: 0 0% 0%;
    --muted: 0 0% 95%;
    --muted-foreground: 0 0% 20%;
    --border: 0 0% 80%;
  }
  body { background: white !important; color: black !important; }
  /* Single column, page breaks before each tab section */
  main { max-width: none !important; padding: 0 !important; }
  [data-tab-panel] { page-break-before: always; break-before: page; }
  [data-tab-panel]:first-of-type { page-break-before: auto; }
  /* Defeat shadows / gradients */
  * {
    box-shadow: none !important;
    background-image: none !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  a[href]::after { content: " (" attr(href) ")"; font-size: 0.85em; }
}
```

Print-stylesheet checklist (verified during manual test in Chrome):

- [ ] `nav`, header action buttons, `[role="alert"]`, ProgressFeed hidden
- [ ] All tabs visible (tabs flatten to vertical stack — see note below)
- [ ] B&W readable; no dark-mode bleed-through
- [ ] Page breaks separate sections; no orphan headers
- [ ] Anchor URLs printed inline so paper readers can follow sources

**Tabs flattening:** the current `tabs.tsx` component uses Radix
which hides non-active panels with `hidden`. Printing only shows the
active tab unless we override. Two options — pick at code time:
(a) add `@media print { [data-tab-panel] { display: block !important; } }`
to the print block, or (b) duplicate ReportView into a `PrintView`
that renders all panels. Option (a) is one line and matches the
"no PDF library" goal.

### 5.4 Delete trip

`DELETE /api/trips/{trip_id}` — described in §5.1 above.

Frontend:

- New component `frontend/components/trips/DeleteTripDialog.tsx`
  using shadcn `AlertDialog`. **Note:** `AlertDialog` is not yet in
  `frontend/components/ui/` (only `badge.tsx`, `card.tsx`, `tabs.tsx`
  exist — see `frontend/components/ui/`). Code Agent must run
  `npx shadcn@latest add alert-dialog` (and `button`, `dialog`,
  `input` if not already present — also missing) before importing.
- After successful delete from `/app/trips/[id]`: `router.replace("/app")`.
- After successful delete from the trip list (when Batch 2g PR B is
  merged): optimistic removal from React Query cache, rollback on
  error toast.
- 409 response → show inline error "Cannot delete a trip while it's
  running. Wait for it to finish or be aborted, then try again."

## 6. Frontend route + UX details

### 6.1 `/share/[token]` empty state

The page is a server component (no auth gate, no JS-only hooks
needed for the read). On `404`:

- HTTP status 404 from `notFound()` (Next.js) so search engines don't
  index dead links.
- Render a minimal page: heading "Link expired or revoked.",
  paragraph "This share link is no longer active. Ask the person who
  sent it for a new one.", a "Go to Plus One" link to `/`.
- No mention of the trip, the owner, or whether the token ever
  existed.

On success:

- Render `ReportView` in read-only mode (no Share / Delete / Export
  buttons; export Markdown is fine to keep — it's client-only and
  uses only the data on the page).
- Footer note: "Read-only share · expires {relativeTime(expires_at)}".

### 6.2 Trip detail page changes

`frontend/app/app/trips/[id]/page.tsx` (current source at lines 109-135)
gets a header-action cluster between `<header>` and the progress
section:

```tsx
{terminal && trip ? (
  <div className="flex gap-2 print:hidden" data-print-hide>
    <ShareButton tripId={trip.trip_id} />
    <ExportMarkdownButton trip={trip} />
    <ExportPdfButton />        {/* just calls window.print() */}
    <DeleteTripButton tripId={trip.trip_id} status={trip.status} />
  </div>
) : null}
```

Buttons only render when the trip is terminal — sharing a half-baked
report is a foot-gun.

## 7. Threat model — unauthed share GET

| Threat | Likelihood | Mitigation |
|---|---|---|
| Token guessing | negligible (~10^57 keyspace) | 192-bit `token_urlsafe(24)` |
| Token brute-force via crawler | negligible (same) | none for v1; document; revisit if we ever observe DB lookups for non-existent tokens at scale |
| Leaked share URL in shared screenshots / Slack | real, accepted | 30-day TTL + revoke endpoint |
| PII in public payload | real | response schema **strips** `user_id`, `created_by`, `trace`, token-cost; integration test asserts |
| Token logged in uvicorn access log | real | the existing access-log scrubber at `main.py:27-55` only redacts `access_token=`. **Tokens appear in URL path, not query string**, so this is fine for stdout; document in code comment |
| Replay after revoke | real | DELETE-share removes the row; subsequent GETs 404 |
| Replay after trip delete | real | CASCADE removes the share row when trip is deleted |
| Stale row still in DB after `expires_at` | minor | GET handler does `expires_at > now()` check in WHERE; row physically lingers until v2 cleanup job. Acceptable; no privacy impact because the row only contains a token, a UUID, and a timestamp |

Conscious skips (v1):

- **Rate limiting** — Not added. 192-bit entropy means an attacker
  guessing at one-million-RPS would expect their first hit in roughly
  10^45 years. We're not adding ops surface for a non-threat.
- **Scheduled cleanup** — Lazy 404 on expired rows is enough; a
  cleanup job adds Celery / cron surface we don't have yet.

## 8. Files to change

| File | Action | Notes |
|---|---|---|
| `backend/src/plus_one/core/db/models.py` | add `SharedTrip` model + `Trip.shared_trips` relationship | append after `Report` (line 236); reuse imports already present |
| `backend/alembic/versions/20260520_0002_shared_trips.py` | new | revision `20260520_0002`, down_revision `20260513_0001` |
| `backend/src/plus_one/api/trips.py` | add `POST /{trip_id}/share`, `DELETE /{trip_id}/share/{token}`, `DELETE /{trip_id}` | match existing style at `trips.py:52-96, 138-159`; use `current_user` from `core.auth.deps` |
| `backend/src/plus_one/api/shared.py` | new | `APIRouter(prefix="/api/shared")`; GET `/{token}`; no auth |
| `backend/src/plus_one/config.py` | add `frontend_base_url: str = "http://localhost:3000"` | used to compose `share_url` |
| `backend/src/plus_one/main.py` | `app.include_router(shared_router)` after line 90 | one-liner mount |
| `backend/tests/integration/test_share.py` | new | see §9 |
| `backend/tests/integration/test_trips_delete.py` | new | see §9 |
| `frontend/app/share/[token]/page.tsx` | new — public read-only view, server component | calls `/api/shared/{token}`; renders `<ReportView>` in read-only mode; handles 404 via Next.js `notFound()` |
| `frontend/app/app/trips/[id]/page.tsx` | add Share / Export MD / Export PDF / Delete buttons in a `print:hidden` cluster | insert between `<header>` (line 119) and the progress section (line 127) |
| `frontend/components/trips/ShareDialog.tsx` | new | mints token, shows URL + copy button + expiry + revoke |
| `frontend/components/trips/DeleteTripDialog.tsx` | new | shadcn `AlertDialog`; calls `deleteTrip`; routes back to `/app` |
| `frontend/components/trips/ReportView.tsx` | accept `readonly?: boolean` prop | hide Share/Delete/PDF buttons when true; Markdown export stays |
| `frontend/lib/api/trips.ts` | add `createShare`, `revokeShare`, `deleteTrip`, `getSharedTrip` | extend existing wrappers at `frontend/lib/api/trips.ts:11-25` |
| `frontend/lib/schemas/trips.ts` | add Zod schemas for share / shared-trip responses | mirror existing `CreateTripBody`, `TripDetail` patterns |
| `frontend/lib/report/exportMarkdown.ts` | new | `reportToMarkdown(trip)`, `downloadMarkdown(trip)` |
| `frontend/app/globals.css` | append `@media print { ... }` block | see §5.3 |
| `frontend/components/ui/alert-dialog.tsx` (and `button.tsx`, `dialog.tsx`, `input.tsx` as needed) | new via `npx shadcn add` | currently only `badge`, `card`, `tabs` are installed |
| `frontend/e2e/share.spec.ts` | new | create → share → open URL in fresh browser context, expect read-only render |
| `frontend/e2e/delete-trip.spec.ts` | new | create → delete → expect `/app`, no row |

## 9. Tests

### 9.1 Backend (`backend/tests/integration/`)

`test_share.py`:

- `test_create_share_returns_token_and_url` — POST as owner;
  assert response shape `{token: str, share_url: str, expires_at: datetime}`;
  assert token length ≥ 30; assert `share_url.endswith(token)`;
  assert one row exists in `shared_trips`.
- `test_create_share_forbidden_for_non_owner` — second user POSTs;
  expect 404 (not 403 — we deliberately don't reveal existence).
- `test_create_share_404_for_unknown_trip` — random UUID; 404.
- `test_get_shared_anonymous_returns_payload` — no Authorization
  header; expect 200; assert response contains `destination`,
  `content`, `shared=True`, `expires_at`; assert response does **not**
  contain `user_id`, `created_by`, `trace`, `input_tokens`,
  `output_tokens`.
- `test_get_shared_404_for_unknown_token` — random token; 404 with
  `detail="share_not_found_or_expired"`.
- `test_get_shared_404_for_expired_token` — insert row with
  `expires_at = now() - 1 day`; GET → 404.
- `test_revoke_share_removes_row_and_breaks_link` — POST share;
  DELETE share; expect 204; subsequent GET shared → 404; assert no
  rows in `shared_trips`.
- `test_revoke_share_forbidden_for_non_owner` — second user DELETE
  → 404; row still present.
- `test_revoke_share_404_when_trip_id_mismatches_token` — POST share
  on trip A; DELETE with trip B in path → 404.

`test_trips_delete.py`:

- `test_delete_trip_owner_cascade_removes_reports_and_shares` —
  seed trip + 2 reports + 1 share; DELETE; expect 204; assert no
  rows remain in `trips`, `reports`, `shared_trips` for that id.
- `test_delete_trip_forbidden_for_non_owner` — second user DELETE
  → 404; trip still present.
- `test_delete_trip_404_for_unknown_id` — random UUID; 404.
- `test_delete_trip_409_when_running` — seed trip with
  `status='running'`; DELETE → 409 with `detail="trip_running"`;
  trip still present.
- `test_delete_trip_409_does_not_partially_delete` — same as above,
  assert `reports` and `shared_trips` for the trip are intact.

### 9.2 Frontend unit (`frontend/lib/`)

- `lib/report/exportMarkdown.test.ts`:
  - `reportToMarkdown_includes_destination_and_sections` — feed
    canned `TripDetail`, assert output contains `# Trip to Tokyo`,
    `## Local Gems`, source URLs.
  - `reportToMarkdown_escapes_pipe_in_titles` — pipe in title
    doesn't break Markdown formatting downstream.
- `lib/api/trips.test.ts` extensions:
  - `createShare_posts_to_share_endpoint_and_parses`
  - `revokeShare_sends_delete_to_share_token_endpoint`
  - `deleteTrip_sends_delete_to_trip_endpoint`
  - `getSharedTrip_does_not_require_auth_header`

### 9.3 E2E (`frontend/e2e/`)

- `share.spec.ts` — `share_link_round_trip_through_incognito_context`:
  1. Sign in via `signInE2E`; create a trip; wait for terminal.
  2. Click Share; assert dialog shows a URL containing `/share/`.
  3. Open a **new browser context** (no cookies/storage); navigate to
     that URL; assert the destination heading and the report content
     are visible; assert no Share/Delete buttons are visible.
  4. Back in the original context, click Revoke; reopen the URL in
     the incognito context; assert "Link expired or revoked." text.
- `delete-trip.spec.ts` — `delete_trip_redirects_to_app_and_removes_row`:
  1. Sign in, create + wait for terminal.
  2. Click Delete; confirm in `AlertDialog`.
  3. Assert URL is `/app`; assert the deleted trip is not in the
     visible list (when Batch 2g PR B is in main; until then, just
     assert redirect succeeds and a subsequent GET `/api/trips/{id}`
     returns 404 — wire via the test fixture).

## 10. Out of scope (explicit deferrals)

- Batch 2j PR B — conversational refinement
  (`POST /api/trips/{id}/refine`, new Report row, chat UI)
- Rate-limiting `/api/shared/{token}`
- Scheduled cleanup job for expired share rows
- Share analytics (view count, last-accessed-at)
- Multi-link UI (the schema supports it; UI ships one-at-a-time)
- OpenGraph / Twitter Card preview metadata on `/share/[token]`
- PDF generation server-side (always `window.print()` for v1)
- Localization of the Markdown export and the expired-link page

## 11. Acceptance criteria

- `cd backend && uv run pytest` — all existing + new tests green
  (existing 137 + ~14 new)
- `cd backend && uv run ruff check .` — clean
- `cd backend && uv run mypy src` — clean
- `cd frontend && pnpm tsc --noEmit` — clean
- `cd frontend && pnpm lint` — clean
- `cd frontend && pnpm test` — unit tests green incl. new
  `exportMarkdown.test.ts` and the extended `trips.test.ts`
- `cd frontend && pnpm e2e` — 11 existing + 2 new (share, delete)
  green
- Manual smoke (single reviewer, Chrome):
  - mint share URL → open in incognito → read-only report renders
  - revoke share → reopen → "Link expired or revoked."
  - download `.md` → file matches `${slug}-${date}.md`; opens cleanly
    in any Markdown viewer
  - `window.print()` preview → header buttons hidden, all tab panels
    visible, black-on-white, anchors show inline URLs
  - delete a `complete` trip → redirect to `/app`, trip absent
  - try to delete a `running` trip (force via DevTools) → 409 inline
    error, no partial deletion

## 12. Risks & open questions

- **Risk: print-stylesheet drift.** Tab content is Radix-driven and
  hides non-active panels with `hidden`. Mitigation is the
  `[data-tab-panel] { display: block !important }` line in §5.3.
  Code Agent must verify the actual DOM attribute Radix emits matches
  the selector (it may need `[data-state]` instead — confirm at
  implementation time by inspecting `frontend/components/ui/tabs.tsx`).
- **Open Q for team lead (not blocking):** should the `/share/[token]`
  page expose the Markdown export button? Pro: zero extra
  implementation cost, lets readers archive. Con: faint asymmetry
  with the "read-only" framing. **Default: yes, keep the button.**


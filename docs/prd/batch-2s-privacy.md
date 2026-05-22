# PRD: batch-2s — Privacy: Export + Hard-Delete

> Status: draft. Owner: privacy. Depends on: batch-2m (auth), batch-2l (scrapbook reskin).

## 1. Problem (PRD §8 last line unmet; users can't export or delete)

`docs/prd.md` §8 closes with one binding promise:

> *Privacy: full data export + hard-delete on user request.*

Today, no surface exists. A user who wants their data back, or who wants
out, has no path other than emailing an admin. That violates the PRD
commitment and leaves us with no answer to a basic "delete my account"
ask. This batch ships the two minimal endpoints + UI to honor that
promise.

## 2. Goals / Non-Goals

### Goals

- One-click JSON export of everything the system holds about the
  current user (user + profile + companions + trips + reports +
  feedback).
- One-click hard-delete of the current user, with a typed-confirm
  guardrail in the UI.
- Admins cannot self-delete via this path (operational safety —
  prevents an admin from accidentally orphaning the deployment).
- Additive only: no schema change, no migration, no new env vars.

### Non-Goals

- Soft-delete or tombstoning (PRD §8 says **hard-delete**).
- Email-confirmation flow for delete (the typed-confirm dialog is the
  guardrail; email step is deferred).
- Anonymization mode (e.g. keeping anonymized rows for analytics).
- Formal GDPR / DSAR compliance docs — this is functional parity only.
- Export formats other than JSON (no CSV, no ZIP, no per-table files).
- Streaming export. The MVP returns one JSON response; we'll revisit
  if a user's payload ever exceeds ~10 MB.
- Re-confirming the password in the API. The dialog is the gate.
- Self-service "undo" after delete. There is no undo.

## 3. User Scenarios (3: export download; delete with confirm; admin try-self-delete blocked)

### 3.1 Sara wants a copy of her data

Sara opens `/app/profile`, scrolls past "been there", sees a new section
titled **"your data"** with a single button **"download my data"** and a
note *"everything you've pinned, packed up. one click."* She clicks.
The browser saves `plus-one-export-<uuid>-2026-05-22.json`. She opens
it in a viewer and sees her user row, her profile, her two companions,
her three trips with their reports, and one piece of feedback. No data
from any other user. She closes the tab.

### 3.2 Marcus wants to leave

Marcus scrolls to the bottom of `/app/profile`, sees **"the page goes"**
with a button **"tear it all out"** and the caption *"this clears
everything. no putting it back."* He clicks. An AlertDialog opens:

> **tear it all out?**
> this clears everything. no putting it back. last chance.
> type DELETE to confirm

He types `DELET` — the confirm button stays disabled. He completes to
`DELETE` — the button enables. He clicks. The API returns 204. The
client clears the auth store (`useAuthStore.getState().clear()`),
invalidates all react-query caches, and `router.replace("/")` lands him
on the unauthed landing page. His JWT cookie is also cleared (logout
side-effect). Refreshing the landing page does not let him log back in
— his email is no longer in the `users` table.

### 3.3 Admin tries to self-delete

The seeded admin user (`is_admin=true`) opens `/app/profile` out of
curiosity, finds the same "tear it all out" section, types DELETE,
clicks confirm. The API returns **409 Conflict** with
`detail="admin_cannot_self_delete"`. The dialog stays open and shows:

> "admins can't tear out their own page. ask another admin, or remove
> the admin flag first."

The session is untouched.

## 4. Technical Design

### 4.1 Backend

#### Cascade verification — list each child table and confirm ON DELETE CASCADE is set OR add an explicit delete for it

We **rely on PostgreSQL `ON DELETE CASCADE`**. From
`backend/src/plus_one/core/db/models.py`:

| Child table     | FK column         | Points at             | `ondelete`   | Covered? |
|-----------------|-------------------|-----------------------|--------------|----------|
| `profiles`      | `user_id`         | `users.id`            | `CASCADE`    | yes      |
| `companions`    | `user_id`         | `users.id`            | `CASCADE`    | yes      |
| `trips`         | `user_id`         | `users.id`            | `CASCADE`    | yes      |
| `shared_trips`  | `created_by`      | `users.id`            | `CASCADE`    | yes (direct) |
| `shared_trips`  | `trip_id`         | `trips.id`            | `CASCADE`    | yes (via trips) |
| `trip_companions` | `trip_id`       | `trips.id`            | `CASCADE`    | yes (via trips) |
| `trip_companions` | `companion_id`  | `companions.id`       | `CASCADE`    | yes (via companions) |
| `reports`       | `trip_id`         | `trips.id`            | `CASCADE`    | yes (via trips) |
| `feedback`      | `trip_id`         | `trips.id`            | `CASCADE`    | yes (via trips) |
| `feedback`      | `for_companion_id`| `companions.id`       | `SET NULL`   | n/a — column nullable, intentional (feedback survives companion deletion under PRD §8; on user-delete the trip row goes first, taking feedback with it) |
| `email_codes`   | — (matches by `email` string) | not FK     | n/a          | **explicit delete** — see below |
| `tool_cache`    | — (no FK to users) | not FK               | n/a          | not user-scoped; do not touch |

**Two follow-ups:**

1. `email_codes` rows are matched by **email string**, not user_id, and
   carry no FK. Active codes for the user's email must be cleared
   explicitly in the delete handler **before** the user row is
   deleted, so a re-registration of the same email after a delete
   doesn't see stale `consumed_at IS NULL` rows.
2. `tool_cache` is global (per-source/per-key); leave it alone.

**Verification step (required before merge):** the backend agent
implementing this batch MUST inspect the live Alembic schema
(or grep the `alembic/versions/` files) to confirm every FK above
landed with `ON DELETE CASCADE` in the actual SQL — the ORM
`ondelete="CASCADE"` only emits the right DDL if the migration was
generated with it. Recommended check: `grep -n "ON DELETE CASCADE"
backend/alembic/versions/*.py` against the table list above.

If any row is missing, **do not** silently add the cascade in code —
add an explicit `await session.execute(delete(<Table>).where(...))`
in the delete handler and file an ADR for the migration fix.

#### `GET /api/me/export` handler shape

New module `backend/src/plus_one/api/me.py` (route prefix `/api/me`,
tag `me`):

```python
@router.get(
    "/export",
    summary="Download all of the current user's data as JSON",
    response_class=Response,        # raw Response, not response_model
)
async def export_me(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> Response:
    payload = await _build_export_payload(session, user)
    body = json.dumps(payload, default=str, ensure_ascii=False)
    today = datetime.now(UTC).date().isoformat()
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="plus-one-export-{user.id}-{today}.json"'
            ),
            "Cache-Control": "no-store",
        },
    )
```

`_build_export_payload` queries:

- the User row (selected columns — see §5; **no `password_hash`**),
- the Profile row (or `None`),
- all Companions where `user_id == user.id`,
- all Trips where `user_id == user.id`, with `selectin` on
  `reports` + `companions` (companion ids only — full companion
  rows are already in the top-level list),
- all Feedback rows whose `trip_id` is in the trips above (single
  `IN`-query, not N+1).

UUIDs and datetimes serialize via `default=str` → ISO-8601 / canonical
UUID strings. No PII redaction — the user is asking for their own
data.

#### `DELETE /api/me` handler shape (with admin guard)

```python
@router.delete(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hard-delete the current user (idempotent; admin blocked)",
)
async def delete_me(
    user: CurrentUser,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> Response:
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="admin_cannot_self_delete",
        )

    # Clear email_codes for this email (no FK to users.id).
    await session.execute(
        delete(EmailCode).where(EmailCode.email == user.email)
    )

    # Hard-delete the user row. ON DELETE CASCADE handles
    # profiles, companions, trips → reports / shared_trips / trip_companions / feedback.
    await session.execute(delete(User).where(User.id == user.id))

    # Clear the session cookie so the client doesn't keep a dead JWT.
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

Idempotency: `current_user` is the gate — if the user is already
gone, the dependency raises 401 before this handler runs, which is
fine. Re-calling DELETE with a stale cookie returns 401, not 500.
For a successfully-deleted user the response is 204 once; on a
second call the session no longer exists.

Wire in `main.py`:

```python
from plus_one.api.me import router as me_router
...
app.include_router(me_router)
```

#### No new DB columns; no migration

No schema changes. No alembic revision. The whole batch is API +
frontend.

### 4.2 Frontend

#### ProfileForm gets two new `<section>` blocks below "been there"

Both blocks live **outside** the `ProfileForm` save flow — they are
their own write actions and shouldn't be gated by the form's dirty
state. Add them in `frontend/app/app/profile/page.tsx` underneath the
existing form container `<section>`. Visual treatment matches the
scrapbook system: paper-2 card, kraft border, masking-tape decoration.

Order (top → bottom):
1. existing form (about you / loves / hates / been there)
2. **new** "your data" card — neutral tape colour (`tape--mint`)
3. **new** "the page goes" card — red tape (`tape--red` if it exists,
   otherwise inline red border) to telegraph destructive intent

Exact copy in each card:

**"your data" card**

- caption / `hand-lg`: **your data**
- scrawl line: *everything you've pinned, packed up. one click.*
- button (`btn`): **download my data**
- inline error scrawl on failure: *couldn't pack it up. one more try?*

**"the page goes" card**

- caption / `hand-lg`: **the page goes**
- scrawl line: *this clears everything. no putting it back.*
- button (`btn btn--red`): **tear it all out**
- admin-blocked annotation (shown only after a 409 response, replacing
  the scrawl line): *admins can't tear out their own page. ask another
  admin, or remove the admin flag first.*

#### New `useExportMe()` and `useDeleteMe()` hooks

New file `frontend/hooks/useMe.ts`:

```ts
export function useExportMe() {
  return useMutation<void, unknown, void>({
    mutationFn: async () => {
      const res = await fetch("/api/me/export", {
        method: "GET",
        credentials: "include",
      });
      if (!res.ok) throw new ApiError(res.status, "export_failed");
      const blob = await res.blob();
      const filename = parseFilenameFromDisposition(
        res.headers.get("content-disposition"),
      ) ?? `plus-one-export-${new Date().toISOString().slice(0,10)}.json`;
      triggerBrowserDownload(blob, filename);
    },
  });
}

export function useDeleteMe() {
  const qc = useQueryClient();
  const router = useRouter();
  return useMutation<void, unknown, void>({
    mutationFn: async () => {
      const res = await fetch("/api/me", { method: "DELETE", credentials: "include" });
      if (res.status === 409) throw new ApiError(409, "admin_cannot_self_delete");
      if (!res.ok) throw new ApiError(res.status, "delete_failed");
    },
    onSuccess: () => {
      useAuthStore.getState().clear();
      qc.clear();
      router.replace("/");
    },
  });
}
```

Helpers (`triggerBrowserDownload`, `parseFilenameFromDisposition`)
live alongside the hooks; both are pure and unit-testable. `apiFetch`
is **not** used for export because it parses JSON and we want the raw
blob with headers.

Note: the auth store exposes `.clear()` not `clearSession()` (see
`frontend/store/auth.ts`); the locked spec said `clearSession()` —
**use `clear()`** to match the existing store and update the spec
verbally.

#### Confirm dialog component (reuse existing AlertDialog primitive)

New file `frontend/components/profile/DeleteAccountDialog.tsx`,
modeled on `frontend/components/trips/DeleteTripDialog.tsx` but with a
typed-confirm input:

- AlertDialogTrigger: `<button className="btn btn--red">tear it all out</button>`
- AlertDialogTitle (`hand-lg`): **tear it all out?**
- AlertDialogDescription (`scrawl`): *this clears everything. no putting
  it back. last chance.*
- A single text `<input>` with `placeholder="type DELETE to confirm"`
  and `aria-label="type DELETE to confirm"`.
- AlertDialogAction button (`btn btn--red`): label **yes, tear it out**
  (pending state: **tearing&hellip;**). `disabled={input !== "DELETE" || pending}`.
- AlertDialogCancel button (`link-hand`): **never mind**.
- Inline error scrawl reuses the same slot as DeleteTripDialog.
- `data-testid="delete-account-button"` on trigger and
  `data-testid="delete-account-confirm"` on the action.

The dialog calls `useDeleteMe()`; success → hook handles store clear
+ navigation; 409 → set local error to the admin annotation copy
(§4.2 above).

### 4.3 Files modified

**New:**

- `backend/src/plus_one/api/me.py`
- `backend/tests/integration/test_me_export.py`
- `backend/tests/integration/test_me_delete.py`
- `frontend/hooks/useMe.ts`
- `frontend/hooks/useMe.test.ts`
- `frontend/components/profile/DeleteAccountDialog.tsx`
- `frontend/components/profile/DeleteAccountDialog.test.tsx`
- `frontend/components/profile/ExportDataCard.tsx` (small wrapper for the "your data" section so the button + error state can be unit-tested in isolation)
- `frontend/lib/schemas/me.ts` (zod schema for the export payload, used by tests + parsers)

**Modified:**

- `backend/src/plus_one/main.py` — `app.include_router(me_router)`
- `frontend/app/app/profile/page.tsx` — append the two new
  `<section>` cards below the existing form card.

**Not modified:**

- `backend/src/plus_one/core/db/models.py` — no schema change.
- `backend/alembic/versions/` — no migration.
- `frontend/store/auth.ts` — `.clear()` already exists.

### 4.4 No concurrent batch conflicts

Recent batches in flight on this branch are 2l (scrapbook reskin) and
2m (auth revamp). This batch:

- adds a new route module (`api/me.py`) — does not edit `auth.py` or
  `profile.py`.
- adds new frontend files; only touches `profile/page.tsx` by
  **appending** sections after `</section>` of the existing form card
  — no diff inside ProfileForm itself.
- introduces no new env var, no new DB column, no new dependency.

The only file with a non-trivial conflict surface is
`profile/page.tsx`. Resolution rule: if scrapbook reskin commits
land first, rebase by re-appending the two cards after the renamed
form `<section>`.

## 5. API contract (full export JSON shape with example trim of 1 trip + 1 companion)

`GET /api/me/export`

- **Auth:** required (`current_user`).
- **Method:** GET.
- **Response 200:** `Content-Type: application/json`,
  `Content-Disposition: attachment; filename="plus-one-export-<user_id>-<YYYY-MM-DD>.json"`,
  `Cache-Control: no-store`.
- **Body shape (zod schema in `frontend/lib/schemas/me.ts`):**

```json
{
  "generated_at": "2026-05-22T14:03:11.482Z",
  "user": {
    "id": "8c1f0a1e-2c0b-4f1c-9c2a-2c0b4f1c9c2a",
    "email": "sara@example.com",
    "username": "sara",
    "is_admin": false,
    "is_active": true,
    "email_verified_at": "2026-04-01T08:11:00Z",
    "last_login_at": "2026-05-22T13:51:08Z",
    "created_at": "2026-04-01T08:10:30Z",
    "updated_at": "2026-05-10T09:22:14Z"
  },
  "profile": {
    "demographics": {"age_range": "30-39", "language": "zh"},
    "travel_style": {"budget_sensitivity": "mid", "pace": "easy", "comfort": "mid"},
    "explicit_preferences": {"loves": ["ramen", "old bookstores"], "hates": ["queues"]},
    "visited_cities": [
      {"city": "Tokyo", "year": 2024, "rating": 5, "feedback": "loved Yanaka"}
    ]
  },
  "companions": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "name": "Wei",
      "explicit_preferences": {"loves": ["coffee"], "hates": ["seafood"]},
      "constraints": {"dietary": ["pescatarian-no-shellfish"], "mobility": "ok", "max_walking_km": 8},
      "created_at": "2026-04-02T10:00:00Z",
      "updated_at": "2026-04-02T10:00:00Z"
    }
  ],
  "trips": [
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "destination": "Tokyo",
      "date_start": "2026-09-12T00:00:00Z",
      "date_end": "2026-09-20T00:00:00Z",
      "budget_amount": 3200,
      "budget_currency": "USD",
      "free_text": "low-key, lots of food",
      "status": "complete",
      "companion_ids": ["11111111-1111-4111-8111-111111111111"],
      "created_at": "2026-05-10T08:00:00Z",
      "updated_at": "2026-05-10T09:14:00Z",
      "reports": [
        {
          "id": "33333333-3333-4333-8333-333333333333",
          "content": { "tl_dr": "...", "tabs": []  },
          "input_tokens": 12450,
          "output_tokens": 3890,
          "created_at": "2026-05-10T09:13:55Z"
        }
      ]
    }
  ],
  "feedback": [
    {
      "id": "44444444-4444-4444-8444-444444444444",
      "trip_id": "22222222-2222-4222-8222-222222222222",
      "card_id": "tokyo-yanaka-walk",
      "for_companion_id": "11111111-1111-4111-8111-111111111111",
      "signal": "thumb_up",
      "text": "Wei loved this",
      "created_at": "2026-05-11T03:01:00Z"
    }
  ]
}
```

**Excluded fields:** `users.password_hash`, `users.failed_login_attempts`,
`users.locked_until`, anything in `email_codes`, anything in `tool_cache`,
and `report.trace` (verbose internal cycle trace — not the user's data
in any meaningful sense; if a user asks, we'll add it as a follow-up).

`DELETE /api/me`

- **Auth:** required.
- **Method:** DELETE.
- **Responses:**
  - `204 No Content` on success — body empty; session cookie cleared
    via `Set-Cookie` with past expiry.
  - `409 Conflict` with `{"detail": "admin_cannot_self_delete"}` when
    the current user has `is_admin=true`.
  - `401 Unauthorized` when no valid session (current_user dep raises).
- **Idempotency:** once the user is gone, subsequent calls return 401,
  not 500 (because there is no current user to authenticate). From the
  caller's perspective, "delete then delete again" is safe — there is
  nothing to delete the second time, and the API does not error.

## 6. Testing

### Backend pytest

`backend/tests/integration/test_me_export.py`

- `test_export_returns_owned_data` — seed user A with 1 profile, 2
  companions, 2 trips (one with 1 report and 1 feedback). Authenticated
  GET returns 200; body parses; counts match.
- `test_export_excludes_other_users_data` — seed user A and user B
  with disjoint data. GET as A; assert no row id from B appears
  anywhere in the JSON (deep string-contains scan against B's UUIDs).
- `test_export_filename_header` — assert
  `Content-Disposition` matches
  `r'attachment; filename="plus-one-export-{uuid}-\d{4}-\d{2}-\d{2}.json"'`.
- `test_export_excludes_password_hash` — body string does not contain
  the substring `password_hash`.
- `test_export_requires_auth` — anonymous call → 401.

`backend/tests/integration/test_me_delete.py`

- `test_delete_removes_user_and_cascades` — seed user with profile +
  companion + trip + report + feedback + shared_trip. Authenticated
  DELETE returns 204. After: `users`, `profiles`, `companions`,
  `trips`, `reports`, `shared_trips`, `feedback`, `trip_companions`
  rows for this user are all gone. Other users' rows are untouched.
- `test_delete_clears_email_codes` — seed an active `email_codes` row
  for the user's email. After DELETE, that row is gone.
- `test_delete_admin_blocked` — seed admin user, DELETE → 409 with
  `detail == "admin_cannot_self_delete"`; user still present in DB.
- `test_delete_clears_session_cookie` — response includes a
  `Set-Cookie` deletion (past-expiry / Max-Age=0) for
  `settings.auth_cookie_name`.
- `test_delete_requires_auth` — anonymous DELETE → 401.

### Frontend vitest

`frontend/lib/schemas/me.test.ts`

- The zod schema accepts the §5 example payload.
- Rejects payload missing required keys (`generated_at`, `user`).

`frontend/hooks/useMe.test.ts`

- `useExportMe` triggers a download with the filename parsed from
  `Content-Disposition` (mock `fetch`, assert anchor click).
- `useDeleteMe` on 204 calls `useAuthStore.getState().clear()`,
  `queryClient.clear()`, and `router.replace("/")`.
- `useDeleteMe` on 409 throws `ApiError(409, "admin_cannot_self_delete")`
  and does **not** touch the auth store.

### Frontend RTL

`frontend/components/profile/DeleteAccountDialog.test.tsx`

- Renders the trigger button; clicking opens the dialog.
- Confirm button is disabled until the input value is exactly
  `DELETE` (test `DELET`, `delete`, `DELETE ` — all stay disabled;
  only `DELETE` enables).
- Clicking confirm calls the injected mutation.
- Receiving a 409 from the mutation shows the admin-blocked annotation
  text and keeps the dialog open.

## 7. Rollout (additive, no flag, irreversible operation requires user-typed confirmation)

- **Additive deploy:** new route module + new frontend files. No env
  var, no migration, no feature flag.
- **No flag** because the action is gated client-side by an explicit
  typed-confirm and server-side by `current_user`; there's no
  half-rolled state we'd want to hide behind a flag.
- **Irreversibility:** the typed `DELETE` confirm is the only
  client-side guard. We accept this trade-off; an email-confirm step
  is logged as a future enhancement (§8).
- **Order of merge:** backend first (export + delete with admin
  guard), then frontend (cards + dialog wired to the new endpoints).
  Frontend can be merged behind a build-only check — the only user
  surface is the two cards on `/app/profile`, which are inert if the
  routes don't exist (the buttons just show the error scrawl).
- **Demo data:** the demo-mode user is not an admin and can exercise
  both flows end-to-end against the seeded fixtures.

## 8. Open Questions

1. Should we include `report.trace` in the export? Today it's excluded
   (internal cycle trace, not user content). If a user files a
   complaint asking for "literally everything", we'll revisit.
2. Should DELETE invalidate any in-flight SSE streams the user has
   open? Practically the connection drops with the cookie; worth a
   smoke test.
3. Rate-limit on `/api/me/export`? MVP says no — it's a heavy GET but
   only the owner can hit it. If we see abuse from a compromised
   session we can bolt on the existing `MinIntervalLimiter`.
4. Future: email-confirm step before destructive delete (out of scope
   here but the obvious next layer of safety).
5. Future: surface a "download my data" button on a future
   `/app/settings` page if profile gets crowded.
6. Future: include `tool_cache` entries the user's queries seeded?
   Currently excluded as they aren't keyed by user and would leak
   cross-user lookups.

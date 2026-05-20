# Batch 2h Frontend — Profile + Companions UI

**Owner:** Frontend
**Branch:** `feat/batch2h-frontend` (cut from `main` at `b736f4f`)
**Status:** PRD draft
**Date:** 2026-05-20
**Predecessors:**
- Batch 2h Backend (`docs/prds/batch2h-backend-profile-companions.md`,
  shipped as PR #19, merged commit `6ec407f`) — adds
  `GET/PUT /api/profile` and `GET/POST/PUT/DELETE /api/companions`
  with all schemas in `backend/src/plus_one/api/schemas.py`.
- Batch 2f PR B (`docs/prds/batch2f-pr-b-trips.md`) — established the
  authed app shell (`/app`), TanStack Query + zod patterns, the trip
  surface, and the `apiFetch` client.
- Batch 2g PR A/B — trip list + report tabs, layered on the same
  patterns this PRD reuses verbatim.

---

## 1. Context

### What the backend already gives us (cite PR #19)

All in the worktree at `backend/src/plus_one/api/`:

- `profile.py` — `APIRouter(prefix="/api/profile")`, two routes:
  - `GET /api/profile` → `ProfileResponse`; lazy-creates defaults when
    the user has no row.
  - `PUT /api/profile` → `ProfileResponse`; whole-document semantics,
    rejects unknown keys via Pydantic `extra="forbid"`.
- `companions.py` — `APIRouter(prefix="/api/companions")`:
  - `GET /api/companions` → `CompanionsListResponse`.
  - `POST /api/companions` → 201 `CompanionResponse`; 409 with
    `detail: "companion_name_taken"` on case-insensitive duplicate;
    409 with `detail: "companion_limit_reached"` at the per-user cap.
  - `PUT /api/companions/{id}` → `CompanionResponse`; same 409 on
    rename collision; 404 `companion_not_found` on missing/wrong-owner.
  - `DELETE /api/companions/{id}` → 204; 404 if not owned.

Schemas to mirror (`backend/src/plus_one/api/schemas.py`):

| Pydantic model | Used by | Notes |
|---|---|---|
| `Demographics` | Profile | `age_range?: str≤20`, `language?: str≤10` |
| `TravelStyle` | Profile | `budget_sensitivity?`, `pace?`, `comfort?` — all `str≤20` |
| `ExplicitPreferences` | Profile + Companion | `loves: str[]` max 50, `hates: str[]` max 50 |
| `VisitedCity` | Profile only | `city: str 1-100`, `year: int 1900-2100`, `rating?: 1-5`, `feedback?: str≤500` |
| `CompanionConstraints` | Companion only | `dietary: str[]` max 20, `mobility?: str≤50`, `max_walking?: int 0-100` |
| `ProfileResponse` / `ProfileUpdateBody` | `/api/profile` | `implicit_preferences` server-only — neither shape exposes it |
| `CompanionResponse` | list / create / update | adds `id`, `created_at`, `updated_at` (datetimes) |
| `CompanionsListResponse` | `GET /api/companions` | `{ companions: CompanionResponse[] }` |
| `CompanionCreateBody` / `CompanionUpdateBody` | POST / PUT | identical shape, no `id` in body |

All response bodies set `extra="forbid"` server-side; the zod mirrors
do the equivalent via `.strict()` so a forgotten field becomes a typed
error at the boundary rather than `undefined` deep in a component.

### What the frontend lacks today

Inspected at the worktree HEAD (`feat/batch2h-frontend` @ `b736f4f`):

- `frontend/lib/api/` — only `auth.ts`, `client.ts`, `trips.ts`. No
  profile or companions client.
- `frontend/lib/schemas/` — only `auth`, `events`, `trips`. No zod
  mirrors of `ProfileResponse` / `CompanionResponse`.
- `frontend/hooks/` — `useCurrentUser`, `useHasHydrated`, `useTrip`,
  `useTripStream`, `useTrips`. No `useProfile` / `useCompanions`.
- `frontend/app/app/` — only `page.tsx` (trip list) and `trips/`
  (new + detail). No `profile/` or `companions/` route.
- `frontend/components/` — `trips/`, `ui/{badge,card,tabs}.tsx`. No
  `profile/` or `companions/` folders; no `dialog`, `checkbox`, or
  `alert-dialog` shadcn primitives.
- `frontend/components/trips/TripForm.tsx` — captures `destination` +
  `free_text` only. No companion-selection UI exists.
- The header in `frontend/app/app/page.tsx` has only "Plan a new trip"
  + "Sign out"; no link to Profile or Companions.

### Why now

The backend is live and the agent cycle already wires `user_profile`
and `selected_companions` into `AgentContext`, but **a user has no UI
to populate either**. Until this PR, the personalization signal is a
hollow column — a user's "loves Greek street food / hates crowds"
preference cannot be entered anywhere. Shipping this UI closes the
loop: form → backend → JSONB row → `_load_profile_context` →
Producer/Joiner prompts.

---

## 2. Goals / Non-goals

### Goals

- **G1** — Authed user can read and update their full profile at
  `/app/profile` via a single form covering demographics, travel
  style, explicit loves/hates (chip-style add/remove), and a
  visited-cities inline list.
- **G2** — Authed user can list / create / edit / delete companions at
  `/app/companions`, with a 409 `companion_name_taken` shown inline
  on the dialog (no toast), and 409 `companion_limit_reached` shown
  inline above the "Add companion" button when the cap is hit.
- **G3** — From `/app/trips/new` the user can pick which companions
  come on this specific trip via a checkbox list (with "Select all" /
  "None"); the selected IDs are sent in the create-trip body. See
  §4 for the option A/B decision driving this.
- **G4** — Header on `/app` exposes "Profile" + "Companions" links
  alongside the existing "Plan a new trip" + "Sign out" buttons.
- **G5** — Profile PUT is optimistic with rollback on error; companion
  CRUD invalidates the list query (no optimistic for CRUD — the dialog
  closes only after the server returns 2xx so the user has a clear
  confirmation point).
- **G6** — `npm run lint`, `npm run typecheck`, `npm run test`,
  `npm run test:e2e` all green. Backend `pytest` stays green (and
  gains 2 cases if §4 option A is taken).

### Non-goals (explicit)

- **Avatar / profile photo / file upload.** Out of MVP per backend PRD
  non-goals; mirror here.
- **Bulk companion import / CSV.** Defer.
- **Companion-level `visited_cities`.** Backend schema doesn't model
  it; nothing to render.
- **Fancy travel stats** (countries visited counter, map, etc.). The
  visited-cities list is a flat editable list — no aggregation,
  charts, or geocoding.
- **Implicit preferences UI.** Server-only column; the zod schema
  intentionally omits it.
- **Admin / multi-user / role UI.** Single-user surface only.
- **Reordering companions via drag-and-drop.** Server returns
  `created_at` ASC; we render in that order, no reorder UI.
- **Pagination of companions.** Backend caps users at 50 companions
  (`_COMPANION_CAP`); a single list call is fine.
- **Inline editing on the card.** Edit always opens the dialog —
  simpler validation story, same component for create + edit.

---

## 3. API contracts (verbatim)

All paths cited from `backend/src/plus_one/api/schemas.py` and
`backend/src/plus_one/api/{profile,companions}.py` at the worktree
HEAD. Frontend zod mirrors must use `.strict()` to match the backend's
`extra="forbid"`.

### Profile

```
GET /api/profile
  → 200 ProfileResponse {
      demographics: { age_range?: string|null, language?: string|null },
      travel_style: { budget_sensitivity?: string|null, pace?: string|null, comfort?: string|null },
      explicit_preferences: { loves: string[], hates: string[] },
      visited_cities: VisitedCity[]
    }
  → 401 if not authed

PUT /api/profile
  body: ProfileUpdateBody (same shape minus implicit_preferences;
        all top-level fields have server defaults so a partial-looking
        body is legal — but FE always sends the full object)
  → 200 ProfileResponse
  → 401 / 422 (zod-validated client-side first to avoid 422)
```

`VisitedCity = { city: string (1-100), year: int (1900-2100),
rating?: int (1-5)|null, feedback?: string (≤500)|null }`.

### Companions

```
GET /api/companions
  → 200 { companions: CompanionResponse[] }

POST /api/companions
  body: CompanionCreateBody {
    name: string (1-100, required),
    explicit_preferences: { loves: string[]≤50, hates: string[]≤50 },
    constraints: { dietary: string[]≤20, mobility?: string|null, max_walking?: int 0-100|null }
  }
  → 201 CompanionResponse
  → 409 { detail: "companion_name_taken" }     ← FE inline error
  → 409 { detail: "companion_limit_reached" }  ← FE inline error on list

PUT /api/companions/{id}
  body: CompanionUpdateBody (same shape as create)
  → 200 CompanionResponse
  → 404 { detail: "companion_not_found" }
  → 409 { detail: "companion_name_taken" }

DELETE /api/companions/{id}
  → 204
  → 404 { detail: "companion_not_found" }
```

`CompanionResponse = CompanionCreateBody & { id: uuid, created_at: datetime, updated_at: datetime }`.

The existing `apiFetch` in `frontend/lib/api/client.ts` already
surfaces HTTP errors as a typed `ApiError` with `.status` and
`.detail`; the new clients reuse it and map 409 detail strings into
specific error cases the dialogs render.

---

## 4. Companion-selector decision (option A vs B)

### Option A (recommended)

Extend `CreateTripBody` to accept `companion_ids: list[UUID] = []`.
When non-empty, `run_trip` (or its `_load_profile_context` helper)
filters companions by that list rather than loading all-user-companions.
When empty, fall back to today's behavior (all companions).

**Backend changes (small, additive, behind a default-empty list):**

1. `backend/src/plus_one/api/schemas.py` — n/a (CreateTripBody lives
   in `trips.py`).
2. `backend/src/plus_one/api/trips.py` — `CreateTripBody` gains
   `companion_ids: list[UUID] = Field(default_factory=list, max_length=50)`;
   pass it into `run_trip` as a new kwarg.
3. `backend/src/plus_one/services/trip_runner.py` — `_load_profile_context`
   takes optional `companion_ids: list[UUID] | None`; if provided and
   non-empty, the `select(Companion)` query gets a `WHERE id = ANY(:ids)`
   filter (and still `WHERE user_id == user_id` for ownership). If
   `companion_ids` is provided but some IDs don't exist / aren't owned,
   they're silently dropped (see §10 Risks).
4. Two new backend pytest cases:
   - `test_run_trip_filters_to_selected_companions` — only the picked
     companion ends up in `AgentContext.selected_companions`.
   - `test_run_trip_with_unknown_companion_ids_drops_them` — unknown
     IDs are ignored, not 400.

### Option B

Ship the per-trip UI as a Batch 2h-2 PR; for this PR
`CreateTripBody` is unchanged and `CompanionSelector` doesn't get
wired into `TripForm`.

### Recommendation: **Option A**

- The backend change is ~5 lines + 2 tests. Smaller than the FE work
  it unblocks.
- Shipping the selector without the wiring is worse than not shipping
  it — users would set a state that the agent silently ignores.
- The runner already had the per-trip-selection TODO documented
  (`trip_runner.py:192-195` — "v1 contract: selected_companions = all
  of the user's companions… A future PR will introduce per-trip
  selection through the `trip_companions` association table"). We
  scope this PR to the simpler **id-list-on-the-create-body** path —
  the `trip_companions` table population is deferred to a later PR
  (Non-goal: we do not write `trip_companions` rows in this PR; the
  selection lives only in `AgentContext`).
- Backward compatible: empty list → existing behavior, zero migration.

The Code Agent implements option A. The PRD §10 risk table covers the
race where a companion is deleted between trip-create and runner
loading; backend silently drops missing IDs to avoid a 400 surfacing
a UX no one can recover from in-flight.

---

## 5. shadcn primitives needed

Inventory of `frontend/components/ui/`: `badge.tsx`, `card.tsx`,
`tabs.tsx`. Missing primitives to add via `npx shadcn add`:

| Primitive | Purpose | Add command |
|---|---|---|
| `dialog` | `CompanionDialog` (create/edit), `DeleteCompanionDialog` (delete confirm) | `npx shadcn add dialog` |
| `alert-dialog` | Destructive-confirmation pattern for `DeleteCompanionDialog` (preferred over `dialog` for irreversible actions; gives us the right ARIA role) | `npx shadcn add alert-dialog` |
| `checkbox` | Per-companion checkboxes in `CompanionSelector` | `npx shadcn add checkbox` |
| `input` | Profile + companion text fields (avoid hand-rolling a 12th raw `<input>`) | `npx shadcn add input` |
| `label` | Paired with `input` for a11y | `npx shadcn add label` |
| `textarea` | Visited-city `feedback`, optional companion notes | `npx shadcn add textarea` |
| `button` | Standardize buttons across new forms (existing pages use raw `<button>`; we adopt shadcn going forward but **do not** touch existing pages in this PR) | `npx shadcn add button` |

Notes for the Code Agent:

- Run all `npx shadcn add` commands in one shell session at the start
  so the configured Tailwind tokens stay consistent.
- If `npx shadcn add` complains about a missing `components.json`,
  init with `npx shadcn init` first (defaults: TypeScript, RSC: yes,
  style: default, tailwind config: existing). Verify
  `frontend/components/ui/` afterwards — only the new files should
  appear; do not regenerate `badge`, `card`, `tabs`.
- Chip input (loves/hates) is **not** a shadcn primitive — we
  hand-roll a small `<ChipInput>` colocated under
  `frontend/components/profile/ChipInput.tsx` (also reused inside
  `CompanionDialog`). It composes `input` + a wrapping `<ul>` of
  removable chips. Keep it < 80 lines, unit-tested.

---

## 6. Files to change (exhaustive)

### New — frontend

| File | Purpose |
|---|---|
| `frontend/lib/api/profile.ts` | `getProfile()`, `updateProfile(body)` — wrap `apiFetch` + zod parse |
| `frontend/lib/api/companions.ts` | `listCompanions()`, `createCompanion(body)`, `updateCompanion(id, body)`, `deleteCompanion(id)` — wrap `apiFetch`; map 409 `detail` → typed error |
| `frontend/lib/schemas/profile.ts` | zod `.strict()` mirrors of `Demographics`, `TravelStyle`, `ExplicitPreferences`, `VisitedCity`, `ProfileResponse`, `ProfileUpdateBody` |
| `frontend/lib/schemas/companions.ts` | zod mirrors of `CompanionConstraints`, `CompanionResponse`, `CompanionCreateBody`, `CompanionUpdateBody`, `CompanionsListResponse` |
| `frontend/hooks/useProfile.ts` | `useQuery` for GET; `useMutation` for PUT with optimistic update + rollback |
| `frontend/hooks/useCompanions.ts` | `useQuery` for list; `useMutation`s for create/update/delete; `onSuccess` invalidates list |
| `frontend/app/app/profile/page.tsx` | Page shell — auth gate (`useHasHydrated` + `useAuthStore` token check mirrors `app/app/page.tsx`); renders `<ProfileForm>` |
| `frontend/app/app/companions/page.tsx` | Page shell — auth gate; renders list of `<CompanionCard>` + "Add" button + dialogs |
| `frontend/components/profile/ProfileForm.tsx` | RHF + zodResolver, sections: Demographics / TravelStyle / Loves+Hates (ChipInput) / VisitedCities (inline list) |
| `frontend/components/profile/ChipInput.tsx` | Reusable chip-style multi-string input |
| `frontend/components/profile/VisitedCitiesField.tsx` | Inline add/remove rows of `{city, year, rating?, feedback?}` |
| `frontend/components/companions/CompanionCard.tsx` | Name + top-3 loves/hates + constraints summary + Edit/Delete buttons |
| `frontend/components/companions/CompanionDialog.tsx` | shadcn `Dialog`, RHF + zodResolver; create + edit modes; 409 inline error |
| `frontend/components/companions/DeleteCompanionDialog.tsx` | shadcn `AlertDialog`; calls `deleteCompanion` |
| `frontend/components/trips/CompanionSelector.tsx` | List of `Checkbox` rows from `useCompanions`; controlled value `string[]`; "Select all" / "None" actions |
| `frontend/e2e/profile.spec.ts` | Round-trip: navigate → fill → save → reload → values persist |
| `frontend/e2e/companions.spec.ts` | Create → edit → delete; duplicate-name → 409 inline error visible |

### Modified — frontend

| File | Change |
|---|---|
| `frontend/components/trips/TripForm.tsx` | Add `CompanionSelector` below `free_text`; include selected ids in the POST body via the extended `CreateTripBody` (option A) |
| `frontend/lib/schemas/trips.ts` | Extend `CreateTripBody` zod with `companion_ids: z.array(z.string().uuid()).max(50).optional()` — match new backend default |
| `frontend/app/app/page.tsx` | Header: add `<Link href="/app/profile">Profile</Link>` and `<Link href="/app/companions">Companions</Link>` between "Plan a new trip" and "Sign out" — keep existing classes for visual consistency |
| `frontend/components/ui/*` | New shadcn primitives land here via `npx shadcn add` (see §5) |

### New / modified — backend (option A scope)

| File | Change |
|---|---|
| `backend/src/plus_one/api/trips.py` | `CreateTripBody.companion_ids: list[UUID] = Field(default_factory=list, max_length=50)`; pass into `run_trip` |
| `backend/src/plus_one/services/trip_runner.py` | `_load_profile_context(user_id, companion_ids: list[UUID] \| None = None)`; when non-empty, filter `select(Companion)` with `Companion.id.in_(companion_ids)` AND `Companion.user_id == user_id` |
| `backend/tests/services/test_trip_runner.py` (or nearest existing) | +2 cases per §4 |
| `backend/tests/api/test_trips.py` (or nearest existing) | +1 case: `CreateTripBody` accepts `companion_ids` and the body validates |

### Unit test files (vitest, colocated where existing pattern does so)

| File | Covers |
|---|---|
| `frontend/lib/api/profile.test.ts` | get / put happy + 401 + 422 |
| `frontend/lib/api/companions.test.ts` | list / create / update / delete + 409 mapping + 404 |
| `frontend/lib/schemas/profile.test.ts` | zod accepts well-formed payload; rejects unknown keys (strict) |
| `frontend/lib/schemas/companions.test.ts` | same |
| `frontend/hooks/useProfile.test.tsx` | optimistic update + rollback on PUT failure |
| `frontend/hooks/useCompanions.test.tsx` | invalidation on success; 409 surfaces to the caller |
| `frontend/components/profile/ProfileForm.test.tsx` | renders, validation, submit calls `updateProfile`, optimistic UI |
| `frontend/components/profile/ChipInput.test.tsx` | add chip on Enter, remove via X, dedupe, max-length enforcement |
| `frontend/components/companions/CompanionCard.test.tsx` | renders top-3 of each, truncates extras |
| `frontend/components/companions/CompanionDialog.test.tsx` | create mode, edit mode pre-fill, 409 inline error |
| `frontend/components/companions/DeleteCompanionDialog.test.tsx` | confirms, cancels, calls delete |
| `frontend/components/trips/CompanionSelector.test.tsx` | renders list, "Select all" / "None", emits id array |
| `frontend/components/trips/TripForm.test.tsx` | (extend existing if present, else add) — submitting with selections includes `companion_ids` |

---

## 7. Tests

### Unit (vitest + Testing Library)

Mirror the patterns in `frontend/hooks/useTrips.test.tsx` and
`frontend/components/trips/TripCard.test.tsx`:

- Mock `apiFetch` at the client-module level.
- Wrap hook tests in a fresh `QueryClientProvider` per test.
- For optimistic update on Profile PUT: assert the form shows the new
  value immediately, then `apiFetch` rejects → form rolls back to
  prior value + shows an inline error.

### E2E (Playwright)

Reuse `frontend/e2e/_helpers/signInE2E.ts` (added in batch 2f) to seed
an authed session, then:

`frontend/e2e/profile.spec.ts`:
- Visit `/app/profile`.
- Empty initial state renders defaults (empty loves/hates etc.).
- Fill demographics + add 2 loves + 1 hate + 1 visited city.
- Save → success indicator → reload → all values persist (assert
  values, not snapshots).

`frontend/e2e/companions.spec.ts`:
- From `/app/companions`, create "Alex" with 2 loves + 1 dietary
  constraint → card appears.
- Edit "Alex" → change name to "Alex K" + add a hate → card updates.
- Create another "Alex K" → 409 inline error "Name already taken"
  visible in dialog → dialog stays open.
- Delete "Alex K" via the destructive `AlertDialog` → card disappears.

(Per-trip selection E2E lives in the existing `trip-flow.spec.ts` —
extend it to check at least one companion and assert the create-trip
network request body includes `companion_ids`. Use the test-only
network capture pattern already in the helpers.)

### Backend (pytest, option A only)

Two new cases in the existing trip-runner test file:

- `selected_companions` is the filtered subset when `companion_ids`
  is provided.
- Unknown / cross-user `companion_ids` are silently dropped (not
  400), and the cycle still runs.

One new case for `CreateTripBody`:

- Body validates with `companion_ids: [uuid, uuid]`; rejects
  non-UUID strings; rejects > 50 entries.

---

## 8. Acceptance

The PR is ready to merge when **all** of:

- `npm run lint` (frontend) — clean, no new warnings.
- `npm run typecheck` (frontend) — clean.
- `npm run test` (frontend vitest) — all green, coverage doesn't
  regress.
- `npm run test:e2e` (frontend playwright) — all specs green incl.
  the two new ones.
- `pytest` (backend) — green, including the +2/+1 new cases from §4.
- `mypy --strict` (backend) — green.
- `ruff check` (backend) — green.
- Manual smoke against a local backend:
  - Profile round-trips a non-trivial payload.
  - Companion create / edit / delete works; duplicate-name 409 shows
    inline.
  - Trip created from `/app/trips/new` with 1 of 2 companions checked:
    backend logs / DB show the runner filtered correctly (or the
    stream shows the producer prompt mentions only the chosen
    companion's preferences).
- The header on `/app` has a working link to both new pages.

---

## 9. Out-of-scope but worth recording

- Move existing trip-list / trip-new pages to use the shadcn `button`
  primitive. Cosmetic-only; not in this PR.
- A `trip_companions` association-table write path. Backend PRD §11
  flagged it as later; this PR keeps the selection ephemeral
  (in `AgentContext` only, not persisted on the Trip row). A future
  PR can persist it when we need it for analytics or "rerun this trip
  with same crew" UX.
- A profile-completion progress meter / nudge to fill loves/hates.
  Backend prompts already no-op on empty fields, so the cost of an
  empty profile is just weaker personalization — fine for MVP.

---

## 10. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | Companion deleted between trip-create POST and runner loading. `companion_ids` carries a now-dangling UUID. | Low (small time window) | Low (silent ignore = trip runs with subset) | Backend filters by `WHERE id IN (...) AND user_id == user_id` — missing rows just drop out. Documented in §4. No 400 (would corrupt the BackgroundTask path). |
| R2 | Profile PUT race: two tabs save in parallel; last write wins. | Medium | Low (single user, single device typical) | Whole-document PUT is intentional — same semantics as backend. Optimistic update rolls back on 4xx. No ETag in v1; accepted. |
| R3 | Large loves/hates arrays (50 items each is the max) blow out the chip area. | Low | Cosmetic | ChipInput uses `flex-wrap` + `max-h` with overflow-auto. Visual cap is the schema cap; client-side guard prevents `>50` add before round-trip 422. |
| R4 | shadcn init clobbers `tailwind.config` or `components.json` differently than the repo expects. | Low | Medium (style regressions) | Code Agent diffs `tailwind.config.*` after `npx shadcn add` runs; if config drifted, revert and add components manually using shadcn copy-paste source from the docs. |
| R5 | `CreateTripBody` zod and backend Pydantic drift on `companion_ids` (one accepts, other 422s). | Low | Medium | Add a contract test in `frontend/lib/schemas/trips.test.ts`: a fixture payload with `companion_ids: []` and a 2-id list both parse. Backend gets the matching pytest case (§7). |
| R6 | 409 `companion_limit_reached` reached mid-form when another tab created the 50th companion. | Very Low | Low | The list page maps 409 detail to a friendly "You've reached the 50-companion limit." banner; `CompanionDialog` reuses the same mapping. |
| R7 | `useProfile` optimistic update + rollback shows a flicker if the network is fast. | Low | Cosmetic | Use TanStack Query's `onMutate` / `onError` rollback pattern; UI shows a success indicator on `onSuccess` only. |
| R8 | E2E auth helper (`signInE2E`) doesn't seed profile/companions; specs assume "fresh" state. | Medium | Medium (specs become order-dependent) | Each spec opens a new browser context with a fresh email (timestamp-based) via `signInE2E` and seeds via UI only — no test fixture in DB. The companion cap is irrelevant at this size. |

---

## 11. Implementation order suggestion (non-binding)

For the Code Agent only — the Test Agent will block on the full
slice, but landing in this order keeps each commit reviewable:

1. Backend option-A changes + tests (small, isolated, unblocks FE
   contract).
2. `lib/schemas/profile.ts`, `lib/schemas/companions.ts` + their unit
   tests.
3. `lib/api/profile.ts`, `lib/api/companions.ts` + their unit tests.
4. `hooks/useProfile.ts`, `hooks/useCompanions.ts` + their unit tests.
5. shadcn primitives via `npx shadcn add` (§5).
6. `ChipInput`, `VisitedCitiesField`, `ProfileForm`, profile page.
7. `CompanionCard`, `CompanionDialog`, `DeleteCompanionDialog`,
   companions page.
8. `CompanionSelector`, `TripForm` wiring + zod update.
9. `/app/page.tsx` header links.
10. E2E specs (`profile.spec.ts`, `companions.spec.ts`,
    extension to `trip-flow.spec.ts`).

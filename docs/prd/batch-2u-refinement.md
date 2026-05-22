# PRD: batch-2u — Conversational Refinement

**Author:** fhw12345
**Date:** 2026-05-22
**Status:** Draft

---

## 1. Problem

The master PRD (`docs/prd.md` §4 *Post-report actions (MVP)*) lists
**conversational refinement** — *"change Day 2 to a different area"* — as a
required MVP capability. Today the trip detail page
(`frontend/app/app/trips/[id]/page.tsx`) ends at `<ReportView>`: once a cycle
finishes and a Report row is written, the user can read it, share it, or
delete the trip, but there is no path to nudge the output toward what they
actually wanted. If the joiner swapped in the wrong Kyoto temple, the only
options are to re-create the entire trip from scratch (losing context) or
live with the result.

The DB already supports this — `Trip` has-many `Report` (verified:
`backend/src/plus_one/core/db/models.py:211-216` declares
`reports: Mapped[list[Report]]` with `order_by="Report.created_at"`, and
`Report.trip_id` is the only Trip→Report join key). The detail endpoint
already returns `latest_report_id` (`api/trips.py:264-273`). The SSE plumbing
already supports streaming a cycle's events to the client. What's missing is
(a) a way to *trigger* a fresh cycle scoped by an edit hint, (b) a refiner
prompt that consumes the previous report + hint instead of starting from
scratch, and (c) UI to issue the hint and browse past revisions.

This batch closes that gap.

---

## 2. Goals / Non-Goals

### Goals

- New `POST /api/trips/{trip_id}/refine` endpoint, body `{hint: str}`, returns
  `202 Accepted` with `{report_id, status: "running"}`.
- A refinement generates a **new `Report` row** for the same `Trip` —
  never mutates the previous report.
- The refiner reuses the existing agent cycle infrastructure
  (`run_cycle`, the per-trip SSE queue from `services/trip_runner.py`) but
  routes through a new prompt path `prompts/refiner/v1.md` that takes the
  previous report's `content` + the hint and emits a refined items list (and
  `tl_dr` if batch-2q has landed by the time 2u ships — see §4.4 dependency).
- SSE emits the same event names as the initial cycle, plus a new
  `refine_started` event with `{previous_report_id, hint}` so the client
  can render context.
- Trip detail page gets a `<RefinePanel>` (single-line input + send button)
  **below** `<ReportView>`, and a `<RefinementHistory>` list showing all
  past Report rows for the trip in chronological order with a "show this
  version" link to swap the rendered report.
- Permission: only `trip.user_id == current_user.id` can call refine.
  Shared (read-only via `/api/shared/{token}`) trips have no refine path —
  the shared endpoint is unauthed and stays read-only.
- Scrapbook voice (lowercase, plain, no exclamation marks).

### Non-Goals

- No visual diff between report versions (out of scope; user reads the new
  version directly).
- No branching — revisions are a linear chronological list. The latest
  Report is canonical (matches existing `latest_report_id` semantics); older
  Reports are queryable but never become "active" in the
  trip-list / GET-trip sense unless the user clicks "show this version" on
  the detail page (which is a local UI swap, not a backend state change).
- No card-anchored refinement ("not this one" on a specific card). Refine
  takes a free-text hint only.
- No multi-turn refine chat ("again, but quieter" referring to the prior
  refine). Each refine is a standalone hint against the *latest* Report.
- No refining a shared trip via the public token. Read-only stays
  read-only — sharers see what was minted at the time of share-link
  creation, refinements made afterward by the owner *will* show up via the
  same share token (the share renders `latest_report_id`), but the
  recipient has no refine button.
- No client-side polling of revision count. The list is fetched on page
  load + after each refine completes.

---

## 3. User Scenarios

### S1 — Simple swap hint (happy path)

User opens a completed trip ("kyoto, late november"). The report shows
Kiyomizu-dera as a recommended temple but the user wants something in
Arashiyama instead. Below the report they see the tweak-it panel with
placeholder *"swap kyoto temple → arashiyama instead"*. They type
*"swap the kiyomizu temple for something in arashiyama instead"* and
click **off i go again**. Frontend POSTs `/api/trips/{trip_id}/refine`,
gets `202 {report_id: <new>, status: "running"}`, and the page swaps
into the same SSE-streaming view used for a fresh trip — but with a
`refine_started` event at the top of the field log showing
*"working from your last reading — hint: swap the kiyomizu temple…"*.
After ~60–90s the cycle emits `trip_complete` with the new
`report_id`; the page swaps `<ReportView>` to render the new report.
The refinement history list below now has two entries.

### S2 — Latency feedback during refine SSE

While a refine is running, the trip detail page must not feel dead. The
`refine_started` event lands in the field log within ~500ms of the POST,
followed by the same `iteration_start` / `producer` / `joiner` /
`controller` events as a normal cycle. The header stamp flips from
**pinned** to **scribbling** (`derived === "running"`) for the duration.
The user can scroll up to see the *previous* report still rendered while
the new one cooks (deliberate — abandoning the previous render leaves
the page empty for 60–90s). Once `trip_complete` fires the new report
replaces the old in `<ReportView>`.

### S3 — Viewing a past version

The user has refined twice. The history list shows three entries:
*"v1 — original — 2d ago — show this version"*,
*"v2 — swap kiyomizu… — 1d ago — show this version"*,
*"v3 — quieter pace overall — just now — current"*. Clicking
**show this version** on v1 swaps `<ReportView>` to render that Report's
content (frontend-only fetch by report_id; no backend write). A subtle
note under the report header reads *"showing v1 — the original. tweak it
to make a new version."* The latest version is restored by clicking
**show current** at the top of the report, or by submitting a new
refinement (which always works from the latest Report regardless of
which version is being *viewed*).

### S4 — Non-owner refused

User A opens the share link for User B's trip. The shared view
(`/share/{token}`) shows the report read-only — no refine panel rendered.
If a curious User A hand-crafts `POST /api/trips/{B's_trip_id}/refine`
with their own bearer token, the backend returns `404 trip_not_found`
(same opacity as `delete_trip` — never confirm existence of other users'
trips). If User A is logged out, they get `401`. The endpoint is *not*
exposed on the unauthed `/api/shared/...` namespace at all.

### S5 — Refine on a still-running trip

User submits a brand-new trip and, while it's still cooking (status
`pending` or `running`), clicks somewhere stale and hits refine.
Backend returns `409 trip_busy`. Frontend surfaces this as
*"hold on — i'm still on the first pass. try again once the page settles."*
The `<RefinePanel>` send button is also disabled when
`derived === "running"` as a first line of defense — the 409 is the
backstop for race conditions.

### S6 — Refine on an aborted trip

The original cycle aborted (status `aborted`, no completable Report).
Backend returns `409 trip_not_complete` with hint copy. UI disables the
refine input with helper text *"no reading to tweak yet — try a new
reading."* (We require a previous complete Report because the refiner
prompt is delta-style against an existing items list.)

---

## 4. Technical Design

### 4.1 Backend

#### Schema verification — no migration needed

Verified against `backend/src/plus_one/core/db/models.py`:

- `Trip.reports: Mapped[list[Report]]` with `cascade="all, delete-orphan"`
  and `order_by="Report.created_at"` (line 211–216) — Trip has-many Report
  already exists.
- `Report.trip_id` FK to `trips.id`, indexed (line 233–238).
- `Report.content: JSONB`, `Report.trace: JSONB`, token columns — all
  schemaless on the DB side, so a refine-flavored Report writes through
  the same shape.

No new tables, no new columns, no Alembic migration. We do add two
**optional** fields to the `Report.content` dict for refines so they're
self-describing in the DB (queryable without joining anywhere):

```python
# Report.content for a refine
{
  "items": [...],
  "tl_dr": "...",                 # if batch-2q is in (additive, see §4.4)
  "refine": {                      # NEW — present only on refine reports
    "previous_report_id": "<uuid>",
    "hint": "<verbatim user hint, truncated to 500 chars>"
  }
}
```

Initial-cycle reports do not carry `content.refine` (or carry `null`).
Old reports (pre-2u) likewise don't carry it. UI treats absence as
*"this is the original reading"*.

#### New route — `POST /api/trips/{trip_id}/refine`

In `backend/src/plus_one/api/trips.py`, after the existing share/delete
routes:

```python
class RefineTripBody(BaseModel):
    hint: str = Field(min_length=1, max_length=500)


class RefineTripResponse(BaseModel):
    report_id: UUID
    status: str  # always "running" on the 202 path


@router.post(
    "/{trip_id}/refine",
    response_model=RefineTripResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a refinement cycle against the latest Report.",
)
async def refine_trip(
    trip_id: UUID,
    body: RefineTripBody,
    background: BackgroundTasks,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> RefineTripResponse: ...
```

Behavior:

1. Lock the trip row with `with_for_update` (same pattern as `delete_trip`)
   so a concurrent state flip can't sneak past the status check.
2. `if trip is None or trip.user_id != user.id` → `404 trip_not_found`.
3. `if trip.status != "complete"` → `409` with detail `trip_busy` for
   `pending|running` and `trip_not_complete` for `aborted`.
4. Load the latest `Report` for this trip
   (`SELECT * FROM reports WHERE trip_id=? ORDER BY created_at DESC LIMIT 1`).
   If none exists (shouldn't happen for status=complete, but defensive):
   `409 trip_not_complete`.
5. Generate a **new `report_id` UUID up front** (so we can return it on
   the 202 — the SSE client uses this to know which report is the active
   one).
6. Flip `trip.status` back to `running` (same column, same CHECK
   constraint already allows it). Commit.
7. `register(trip_id)` (pre-create SSE queue — same as create).
8. `background.add_task(run_refine, trip_id, previous_report.id,
   body.hint.strip(), user.id, report_id_pre)` where the pre-allocated
   report_id is wired into the runner so the published `trip_complete`
   event matches what we returned.
9. Return `RefineTripResponse(report_id=report_id_pre, status="running")`.

#### Runner — `services/trip_runner.py::run_refine`

A new top-level coroutine alongside `run_trip`. Reuses every helper
(`_set_status`, `_save_report`, `_publish`, `_load_profile_context`,
the producer/joiner/controller pumps). Differences:

- First published event after `started` is:
  ```python
  {"name": "refine_started",
   "previous_report_id": str(previous_report_id),
   "hint": hint}
  ```
- `AgentContext` carries the previous items list + hint. We extend
  `AgentContext` (or thread via a sibling wrapper) so the joiner phase
  knows we're in refine mode and switches to the refiner prompt path.
  Minimal-blast-radius option: add `refine_context: RefineContext | None`
  to `AgentContext` in `core/agents/framework/types.py`; the
  joiner_phase reads it and picks the prompt path.
- `_save_report` is replaced with a sibling `_save_refine_report` that
  threads `previous_report_id` + `hint` into `content["refine"]` and
  also accepts the pre-allocated `report_id` so insert is idempotent
  with the API's 202 contract:

  ```python
  async def _save_refine_report(
      report_id: UUID, trip_id: UUID, items, trace,
      input_tokens, output_tokens, previous_report_id, hint, tl_dr=None
  ) -> UUID: ...
  ```

- `trip_complete` event payload is identical to the initial-cycle one
  (`{name, trip_id, status, report_id}`); the client correlates by the
  `report_id` it got in the 202 response. Same `_EOF` sentinel, same
  queue drop in `finally`.

#### Refiner prompt — `prompts/refiner/v1.md`

New file at `backend/src/plus_one/prompts/refiner/v1.md`. The agent
package's joiner prompt selector (`agents/prompts.py`) gets a branch:
when `ctx.refine_context is not None`, load `refiner/v1.md` instead of
`joiner/v2.md`.

Prompt rules (spec, not the full text — the prompt itself is written
during implementation):

- System: lowercase plain voice, same scrapbook palette as joiner.
- Inputs:
  - `{previous_items_json}` — the previous Report's `content.items`
    pretty-printed.
  - `{previous_tl_dr}` — the previous Report's `content.tl_dr` if
    present, else empty.
  - `{hint}` — the verbatim user hint, fenced.
  - `{candidates_json}` — the producer phase's fresh candidate dump
    for this iteration.
- Task: produce a *new full items list* (not a delta — downstream code
  expects a complete `JoinedItem[]`). For items the hint doesn't touch,
  preserve them verbatim (same name, same evidence count, same scores).
  For items the hint mentions, replace or remove. The hint may also add
  ("more izakayas in nakameguro" → add cards).
- Output: same `JoinedItem` Pydantic schema as joiner v2 — Pydantic
  validation + 3-tier fallback parser at the boundary (existing pattern,
  `core/llm/parsers.py`). Include `tl_dr` if batch-2q has shipped.
- Anti-rules: don't invent sources that weren't in the producer's
  candidate dump. Don't drop *everything* — if the hint is incoherent,
  fall back to preserving the previous list verbatim and log a notes
  field `"hint_ignored=true"` for observability.

#### Agent flow summary

```text
POST /api/trips/{id}/refine
  → load latest Report
  → mint report_id_pre
  → register(trip_id) + BackgroundTask(run_refine)
  → 202 {report_id: pre, status: running}

run_refine:
  → trip.status = running
  → publish "started"
  → publish "refine_started"
  → ctx = AgentContext(..., refine_context=RefineContext(
        previous_items=..., previous_tl_dr=..., hint=...))
  → run_cycle(producer, joiner→refiner-prompt, controller, ctx)
  → _save_refine_report(report_id_pre, ..., previous_report_id, hint)
  → trip.status = complete | aborted
  → publish "trip_complete" {report_id: pre, status}
  → publish _EOF
```

#### SSE — reuse `/api/trips/{trip_id}/stream`

No new endpoint. The existing stream handler
(`api/trips.py:147`) already authorizes by `trip.user_id == user.id`,
already subscribes to the per-trip queue, already handles
`asyncio.CancelledError` on client disconnect. Refine events flow
through the same queue because they're published with the same
`trip_id` key.

New event name documented in §5: `refine_started`.

#### Permission summary

| Caller | Endpoint | Outcome |
|---|---|---|
| Logged-out | `POST /api/trips/{id}/refine` | 401 (current_user dep raises) |
| Logged-in non-owner | `POST /api/trips/{id}/refine` | 404 `trip_not_found` |
| Owner, trip running | `POST /api/trips/{id}/refine` | 409 `trip_busy` |
| Owner, trip aborted | `POST /api/trips/{id}/refine` | 409 `trip_not_complete` |
| Owner, trip complete | `POST /api/trips/{id}/refine` | 202 `{report_id, status: running}` |
| Share-link viewer | `/api/shared/{token}` (read only) | No refine path exposed |

### 4.2 Frontend

#### New components

**`<RefinePanel trip={trip} disabled={...} onSubmitted={() => ...} />`**
`frontend/components/trips/RefinePanel.tsx`

- Renders below `<ReportView>` on the trip detail page (NOT in the
  ReportView itself — keeps batch-2q/2r conflict surface area zero).
- Single `<textarea rows={2}>` input bound to local state `hint`.
- Submit button labeled **off i go again** — disabled when `hint.trim()` is
  empty, when `disabled` prop is true (running cycle), or while the
  internal submit is in-flight.
- On submit: calls `useRefineTrip().mutateAsync({hint})`; clears input on
  success; surfaces 409/404 as inline tickets using the existing
  `.ticket` scrapbook component class.

**`<RefinementHistory trip={trip} onSelectReport={(reportId) => ...} />`**
`frontend/components/trips/RefinementHistory.tsx`

- Renders below `<RefinePanel>`.
- Lists past Reports for the trip in chronological order (oldest →
  newest). Each row shows:
  - version label (`v1`, `v2`, …; the first Report is always `v1` =
    *"the original"*),
  - the hint (or *"the original"* for v1),
  - relative time ("2d ago", "just now") via a small `formatRelativeTime`
    util — we use the same util that ProgressFeed uses today, or write
    a thin one if missing,
  - a *show this version* link (no link for the currently-shown version,
    replaced by *"current"* tag).

#### New hook + API client

**`frontend/lib/api/trips.ts`** gains:

```ts
export async function refineTrip(
  tripId: string,
  body: RefineTripBodyT,
): Promise<RefineTripResponseT> {
  const validBody = RefineTripBody.parse(body);
  const raw = await apiFetch<unknown>(`/api/trips/${tripId}/refine`, {
    method: "POST",
    body: JSON.stringify(validBody),
  });
  return RefineTripResponse.parse(raw);
}

export async function listTripReports(
  tripId: string,
): Promise<TripReportsResponseT> {
  const raw = await apiFetch<unknown>(`/api/trips/${tripId}/reports`, {
    method: "GET",
  });
  return TripReportsResponse.parse(raw);
}

export async function getReport(
  tripId: string,
  reportId: string,
): Promise<ReportDetailT> {
  const raw = await apiFetch<unknown>(`/api/trips/${tripId}/reports/${reportId}`, {
    method: "GET",
  });
  return ReportDetail.parse(raw);
}
```

> Note: `GET /api/trips/{id}/reports` (list) and
> `GET /api/trips/{id}/reports/{report_id}` (detail) are tiny additive
> read endpoints on the backend, mirroring `GET /api/trips/{id}` but
> for non-latest revisions. Implemented in the same `api/trips.py`
> file; auth identical to `get_trip`.

**`frontend/hooks/useRefineTrip.ts`** — TanStack mutation that:

1. POSTs to `/api/trips/{tripId}/refine`.
2. On success, invalidates `useTrip(tripId)` and `useTripReports(tripId)`.
3. Importantly: the EXISTING `useTripStream(tripId)` automatically
   picks up the refine cycle's events because the SSE endpoint is keyed
   by trip_id, not report_id. No new stream hook needed.

**`frontend/hooks/useTripReports.ts`** — TanStack query that fetches
`listTripReports(tripId)`. Refetched after each refine completes
(triggered by the `trip_complete` SSE event landing for a known refine
correlation).

#### Page wiring — `frontend/app/app/trips/[id]/page.tsx`

Add below the existing `<ReportView trip={trip} />`:

```tsx
{terminal && trip ? (
  <>
    <ReportView trip={trip} reportId={shownReportId ?? trip.latest_report_id} />
    <RefinePanel trip={trip} disabled={derived === "running"} />
    <RefinementHistory trip={trip} onSelectReport={setShownReportId} />
  </>
) : null}
```

`<ReportView>` currently takes only `trip` — we add an optional
`reportId` prop. When undefined, it renders `trip.latest_report_id`'s
content (today's behavior). When set, it fetches that specific Report
via `useReport(tripId, reportId)` and renders it. A small banner reads
*"showing v{N} — {hint or 'the original'}"* with a *show current* link.

Local state `shownReportId: string | null` lives in the page and is
reset to `null` whenever a new `trip_complete` SSE event lands (so a
fresh refine snaps back to the latest).

#### Voice copy table

| Surface | Copy |
|---|---|
| Refine panel header | `tweak it` |
| Refine panel subheading | `not quite right? tell me what to change.` |
| Textarea placeholder | `swap kyoto temple → arashiyama instead` |
| Submit button (idle) | `off i go again` |
| Submit button (loading) | `out asking…` |
| 409 `trip_busy` ticket | `hold on — i'm still on the first pass. try again once the page settles.` |
| 409 `trip_not_complete` helper | `no reading to tweak yet — try a new reading.` |
| 404 ticket | `couldn't find this reading. it might have been deleted.` |
| Generic refine failure | `that didn't go through. give me a moment, then try again.` |
| Refinement history header | `past tweaks` |
| Original row label | `v1 — the original` |
| Subsequent row label | `v{N} — {hint truncated to 80 chars}` |
| Row time suffix | `{relative time} ago` (e.g. `2d ago`, `just now`) |
| Row action (other versions) | `show this version` |
| Row action (current) | `current` |
| Showing-past-version banner | `showing v{N} — {hint or "the original"}. ` + link: `show current` |
| New SSE `refine_started` field-log line | `working from your last reading — hint: "{hint}"` |
| New SSE iteration_start line under refine | (unchanged from initial cycle) |

### 4.3 Files modified

| File | Change |
|---|---|
| `backend/src/plus_one/api/trips.py` | + `RefineTripBody`, `RefineTripResponse`, `POST /api/trips/{id}/refine`, `GET /api/trips/{id}/reports`, `GET /api/trips/{id}/reports/{report_id}` |
| `backend/src/plus_one/services/trip_runner.py` | + `run_refine` coroutine, + `_save_refine_report`, share helpers with `run_trip` |
| `backend/src/plus_one/core/agents/framework/types.py` | + `RefineContext` dataclass; `AgentContext.refine_context: RefineContext \| None = None` |
| `backend/src/plus_one/agents/joiner.py` or `prompts.py` | + branch to load `refiner/v1.md` when `ctx.refine_context is not None` |
| `backend/src/plus_one/prompts/refiner/v1.md` | + NEW prompt file |
| `backend/tests/integration/test_refine_trip.py` | + NEW tests (see §6) |
| `backend/tests/unit/services/test_trip_runner_refine.py` | + NEW tests |
| `frontend/components/trips/RefinePanel.tsx` | + NEW |
| `frontend/components/trips/RefinePanel.test.tsx` | + NEW |
| `frontend/components/trips/RefinementHistory.tsx` | + NEW |
| `frontend/components/trips/RefinementHistory.test.tsx` | + NEW |
| `frontend/components/trips/ReportView.tsx` | + optional `reportId` prop; if set, fetch that report instead of latest. **Coexists with batch-2q/2r changes** — see §4.4. |
| `frontend/hooks/useRefineTrip.ts` | + NEW |
| `frontend/hooks/useTripReports.ts` | + NEW |
| `frontend/hooks/useReport.ts` | + NEW (single non-latest report by id) |
| `frontend/lib/api/trips.ts` | + `refineTrip`, `listTripReports`, `getReport` |
| `frontend/lib/schemas/trips.ts` | + `RefineTripBody`, `RefineTripResponse`, `TripReportsResponse`, `ReportDetail` |
| `frontend/lib/schemas/events.ts` | + `refine_started` event in the `TripEvent` discriminated union |
| `frontend/app/app/trips/[id]/page.tsx` | + render `<RefinePanel>` + `<RefinementHistory>` below `<ReportView>`; track `shownReportId` state |

### 4.4 Concurrent-batch warning

`frontend/components/trips/ReportView.tsx` is touched by **batch-2q (tl_dr)**
and **batch-2r (perspective)**. This batch (2u) adds an *optional*
`reportId` prop to `ReportView` and renders a small "showing v{N}" banner;
both are additive to ReportView's surface. The new `<RefinePanel>` and
`<RefinementHistory>` components are rendered **outside** ReportView (as
siblings in the page), so they don't conflict with 2q's TL;DR sticky note
or 2r's perspective toggle wiring inside ReportView.

There is no required merge order between 2q, 2r, and 2u as far as
component-level conflict goes. The only interaction:

- **If 2q lands before 2u**: the refiner prompt outputs `tl_dr` and the
  refine Report carries it through. `<ReportView>` already knows how to
  render it.
- **If 2q lands after 2u**: refine Reports created before 2q ships have
  no `tl_dr`; 2q's "absent tl_dr → render nothing" rule covers them.
  When 2q ships, the refiner prompt is updated in the same patch as the
  joiner prompt to emit `tl_dr`.

**This batch is the largest of the 2q–2u family and depends on the
existing SSE plumbing, the agent cycle framework, AND on `Trip
has-many Report` being correctly wired across the stack. It should be
sequenced LAST in the implementation order — after 2q, 2r, and any
other ReportView reskin tweaks have stabilized.**

---

## 5. API contract

### 5.1 `POST /api/trips/{trip_id}/refine`

**Request**

```http
POST /api/trips/8c0c…/refine HTTP/1.1
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "hint": "swap the kiyomizu temple for something in arashiyama instead"
}
```

Body schema:

| field | type | constraints |
|---|---|---|
| `hint` | `str` | `min_length=1, max_length=500`; whitespace-trimmed |

**Response — 202 Accepted**

```json
{
  "report_id": "9a4f…",
  "status": "running"
}
```

**Errors**

| status | detail | when |
|---|---|---|
| 401 | (auth dep default) | no/expired bearer token |
| 404 | `trip_not_found` | trip missing OR not owned by caller |
| 409 | `trip_busy` | trip.status in `(pending, running)` |
| 409 | `trip_not_complete` | trip.status == `aborted` OR no prior Report row |
| 422 | (FastAPI default) | hint empty / > 500 chars |

### 5.2 `GET /api/trips/{trip_id}/reports`

**Response — 200 OK**

```json
{
  "reports": [
    {
      "report_id": "r1…",
      "created_at": "2026-05-20T12:34:56Z",
      "is_original": true,
      "hint": null,
      "previous_report_id": null
    },
    {
      "report_id": "r2…",
      "created_at": "2026-05-21T09:10:00Z",
      "is_original": false,
      "hint": "swap the kiyomizu temple for something in arashiyama instead",
      "previous_report_id": "r1…"
    }
  ]
}
```

Ordered ASC by `created_at`. Same 404 rules as `GET /api/trips/{id}`.

### 5.3 `GET /api/trips/{trip_id}/reports/{report_id}`

**Response — 200 OK**

```json
{
  "report_id": "r2…",
  "trip_id": "8c0c…",
  "created_at": "...",
  "content": { "items": [...], "tl_dr": "...", "refine": {...} },
  "is_original": false
}
```

`404 report_not_found` if the report_id doesn't exist or doesn't belong
to the trip the caller owns.

### 5.4 SSE — new event `refine_started`

Emitted once at the start of `run_refine`, immediately after `started`.

```text
event: refine_started
data: {
  "name": "refine_started",
  "trip_id": "8c0c…",
  "previous_report_id": "r1…",
  "hint": "swap the kiyomizu temple for something in arashiyama instead"
}
```

All other event names (`iteration_start`, `producer`, `joiner`,
`controller`, `cycle_aborted`, `trip_complete`) are emitted with the
same shape as the initial cycle. The `trip_complete` event's
`report_id` field carries the *new* refine report id (matching the one
returned in the 202 response).

The frontend `TripEvent` union in `frontend/lib/schemas/events.ts` adds:

```ts
const RefineStarted = z.object({
  name: z.literal("refine_started"),
  trip_id: z.string().uuid(),
  previous_report_id: z.string().uuid(),
  hint: z.string(),
});
```

---

## 6. Testing

### 6.1 Backend pytest

`backend/tests/integration/test_refine_trip.py`:

- `test_refine_creates_new_report_row` — POST refine on a completed trip;
  assert 202 with new report_id; poll `/api/trips/{id}/reports` and see
  two rows; assert the new row's `content.refine.previous_report_id`
  matches the original.
- `test_refine_preserves_original` — fetch original report by id after a
  refine; assert content unchanged byte-for-byte.
- `test_refine_403_for_non_owner` — User A's bearer token attempts to
  refine User B's trip; assert 404 `trip_not_found` (we use 404 not 403
  for the same opacity reason as `delete_trip`).
- `test_refine_409_on_running_trip` — refine while status is `running`;
  assert 409 `trip_busy`.
- `test_refine_409_on_aborted_trip` — refine on aborted trip; assert
  409 `trip_not_complete`.
- `test_refine_422_empty_hint` — empty / whitespace-only hint; 422.
- `test_refine_422_long_hint` — 501-char hint; 422.
- `test_refine_unauthed_401` — no bearer token; 401.
- `test_refine_sse_emits_refine_started` — open SSE stream, POST refine,
  assert the first non-`started` event is `refine_started` with the
  correct `previous_report_id` + `hint`.

`backend/tests/unit/services/test_trip_runner_refine.py`:

- `test_run_refine_writes_refine_metadata` — mock the cycle phases,
  call `run_refine`, assert the saved Report's `content.refine` has
  `previous_report_id` + `hint`.
- `test_run_refine_uses_pre_allocated_report_id` — verify the id passed
  in is the id persisted (so the 202 response is accurate).
- `test_run_refine_flips_status_back_to_complete` — start from
  `complete` → during run status is `running` → end status is
  `complete`.
- `test_run_refine_aborted_keeps_previous_latest` — if the refine cycle
  aborts AND the report save fails, ensure the previous report is
  still queryable as the latest (defensive — relies on the new report
  row not being committed if `_save_refine_report` raises).

### 6.2 Frontend vitest

`frontend/components/trips/RefinePanel.test.tsx`:

- renders header `tweak it` and placeholder `swap kyoto temple → arashiyama instead`
- submit button disabled when input empty
- submit button disabled when `disabled` prop true (running cycle)
- typing → enabling → click triggers `refineTrip` API with trimmed hint
- shows error ticket on 409 `trip_busy` with the exact voice copy from §4.2
- clears input on successful submit

`frontend/components/trips/RefinementHistory.test.tsx`:

- given a 3-report list, renders v1 / v2 / v3 in chronological order
- v1 label is `v1 — the original` (no hint)
- subsequent labels are `v{N} — {truncated hint}`
- the row matching `currentReportId` shows `current` instead of
  `show this version`
- clicking `show this version` invokes `onSelectReport(reportId)`

### 6.3 Frontend RTL — end-to-end on the page

`frontend/app/app/trips/[id]/page.test.tsx` (new):

- mount the page with a complete trip + 1 report
- submit refine via `<RefinePanel>` → assert API called, spinner shows
  on submit button (`out asking…`), SSE bus delivers a fake
  `refine_started` then `iteration_start` → `joiner` → `trip_complete`
- after `trip_complete` lands, assert `<ReportView>` re-renders with
  the new content and `<RefinementHistory>` now has 2 entries
- clicking `show this version` on v1 swaps `<ReportView>` content back
  to v1 and shows the *"showing v1 — the original"* banner with
  *show current* link

---

## 7. Rollout

- **Additive.** No schema migration. No new env vars. No feature flag.
- Old trips that have only one Report row show an empty refinement
  history (the original row alone, labeled `v1 — the original`, with
  `current` tag). Refining works normally — the next refine becomes v2.
- Refines on trips created before 2u shipped land normally because the
  `content.refine` block is optional everywhere we read it.
- No client cache invalidation is needed beyond the standard TanStack
  invalidations triggered by the new mutation; the trip-list page's
  `latest_report_id` field already auto-updates on the next fetch.
- Logs: `run_refine` reuses the same structlog logger; we tag events
  with `refine=True` for filtering.

---

## 8. Open Questions

1. **Refine cap per trip.** Should there be a hard cap (e.g. 10
   revisions per trip) to bound storage + abuse? MVP proposal: no cap;
   revisit if a single trip's revision count exceeds 20 in dogfooding.

2. **Translator on refines.** Should `_run_translations_and_update` run
   on refine reports the same way it does on initial reports? Default
   *yes* (same code path inside `run_refine`), but worth confirming
   token budget — refining 5 times triples translator cost.

3. **Companion / profile snapshot.** The original cycle snapshotted
   the user's profile + companions at trip-create time. Should a refine
   re-snapshot at refine-time (picking up profile edits the user made
   in between) or use the original snapshot? MVP proposal: re-snapshot
   at refine-time — matches user intent ("I changed my mind about X
   AND my preferences").

4. **Should `latest_report_id` ever point at a non-newest Report?** No
   for MVP — keeps the schema simple and matches `Trip.reports` order
   semantics. Future "pin this version as canonical" UX would need a
   `Trip.canonical_report_id` column; deferred.

5. **Cancelling an in-flight refine.** The PRD reckons with one refine
   at a time per trip (the 409 guard). Do we want a "cancel" button
   that aborts the in-flight refine and unsticks status? Not in MVP —
   the cycle's own 120s phase timeout is the backstop; user can wait
   it out.

6. **Audit log of hints for safety review.** All hints are stored in
   `Report.content.refine.hint` so they're queryable from the DB.
   Should we additionally log to structlog for ops? Default yes,
   structured field `refine_hint_len` (not the hint text, to avoid
   PII in logs); the full text is in the DB Report row.

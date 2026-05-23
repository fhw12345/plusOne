# PRD: Trip Detail — Day-by-Day Itinerary View

**Status:** Frozen for current implementation wave (2026-05-24)
**Wave:** batch-3a
**Source of truth for visuals:** `docs/design/scrapbook/pages/trip-detail-itinerary.html` + `docs/design/scrapbook/pages-zh/trip-detail-itinerary.html`

---

## Problem statement

Current trip detail (`frontend/app/app/trips/[id]/page.tsx` → `<ReportView>`) renders a flat, tab-grouped list of `JoinedItem`s with no images, no long human-voice descriptions, and no temporal structure. A reader cannot answer "what do I do on Tuesday morning?" — it reads like a research dump, not an itinerary.

## Goals

1. Backend returns `day_plan: DayPlan[]` structuring approved items into days × periods.
2. Every `JoinedItem` carries `image_url` (from Foursquare) and `long_description` (2–4 sentences in human voice).
3. Frontend renders `<ItineraryView>` (day-by-day scrapbook cards) on completed trips with `day_plan` present.
4. Existing in-progress / refinement / SSE / scratchpad paths unchanged.
5. Shared-trip page (`/share/[token]`) also shows the itinerary when present.

## Non-goals

- Multi-language itinerary translation (day_plan is language-neutral; item translations stay separate).
- Editing the day plan from the UI (read-only this wave).
- Back-filling `day_plan` for existing completed trips in the DB.
- Map or calendar visualizations.
- Changing `ReportTabs` / flat view for trips that lack `day_plan` (backward-compat path).

## Acceptance criteria

| # | Criterion |
|---|-----------|
| AC-1 | `GET /api/trips/{id}` response includes `content.day_plan: DayPlan[] \| null`. |
| AC-2 | Each `JoinedItem` has `image_url: str \| null` and `long_description: str`. |
| AC-3 | `<ItineraryView>` renders when `trip.content.day_plan` is non-empty on completed trips. |
| AC-4 | Day sections show heading (`Day N`) and period sub-headings (`morning / afternoon / evening / late_night`). |
| AC-5 | Each card renders `<img>` when `image_url` present; `.is-typed` placeholder otherwise. |
| AC-6 | Each card renders `.scrawl` with `long_description`. |
| AC-7 | Each card renders `.verdict` (reuse existing logic). |
| AC-8 | In-progress trips still show `<ProgressFeed>` only — no `<ItineraryView>`. |
| AC-9 | Older completed trips without `day_plan` fall back to `<ReportView>`. |
| AC-10 | e2e: `[data-testid="itinerary-view"]` visible; day header `/Day \d/i`; `<img>` inside; `.scrawl` + `.verdict` present. |
| AC-11 | `pnpm e2e` passes (Chromium only) end-to-end, including `trip-flow.spec.ts`. |
| AC-12 | Invalid day_plan (out-of-range `item_index`) → scheduler returns `None`, no crash. |
| AC-13 | Shared-trip page shows `day_plan` when present. |

## Frozen decisions (from user 2026-05-24)

- **Image source**: Foursquare `Place.external_url` only. XHS cover not used.
- **Itinerary scheduler model**: `claude-sonnet-4-6` (lighter than joiner; scheduling is lower-stakes).
- **Day count**: hard cap **7 days**. Default 3 if no `date_start`/`date_end`.
- **Shared-trip**: itinerary is exposed on shared endpoint too.

## Data model

### Backend (`backend/src/plus_one/agents/itinerary.py` — NEW)

```python
class DaySlot(BaseModel):
    period: Literal["morning", "afternoon", "evening", "late_night"]
    item_index: int = Field(ge=0)
    note: str | None = None

class DayPlan(BaseModel):
    day_index: int = Field(ge=1)
    date: date | None = None
    theme: str | None = None
    slots: list[DaySlot] = Field(default_factory=list)

class ItineraryPlan(BaseModel):
    days: list[DayPlan] = Field(default_factory=list)
    # validator: no item_index appears in more than one slot
```

### Backend — `joiner.py` `JoinedItem`

Add: `image_url: str | None = None`, `long_description: str = ""`.

### Backend — `api/trips.py` `TripDetail`

Add: `content.day_plan: list[dict] | None = None` (JSONB pass-through).

### Frontend — `lib/schemas/trips.ts`

Add Zod `DaySlot`, `DayPlan`; extend `TripContent` with `day_plan`; extend `JoinedItemView` with `image_url`, `long_description`.

## LLM changes

**Joiner v4 prompt** (`prompts/joiner/v4.md` — copy v3 + add):
> For each item also return `long_description`: 2–4 sentences in the voice of a well-travelled friend. Combine evidence into a coherent paragraph. Do not fabricate. Max 240 words.

**Image propagation** (deterministic, no LLM): in `joiner.py` after tool fan-out, build `_image_by_name: dict[str, str | None]` from Foursquare `Place.external_url`; inject into `JoinedItem.image_url`.

**Itinerary scheduler** (`prompts/itinerary/v1.md` + `_run_itinerary_scheduler` in `trip_runner.py`):
- Inputs: items (filter to `local_gem` + `neutral`), `date_start`, `date_end`
- Day count: `min(7, (date_end - date_start).days)` or default 3
- Prompt: every eligible item appears in exactly one slot; cluster by `candidate.area`; respect opening-hour intuition (breakfast → morning, izakaya/bar → evening)
- Validate with `ItineraryPlan`; on `ValidationError` log warning + return `None` (fall back to flat view)
- Best-effort: failure does NOT flip `final_status`
- Runs in both `run_trip` and `run_refine`

## Files to create / modify

| Path | Kind | Change |
|------|------|--------|
| `backend/src/plus_one/agents/itinerary.py` | new | Pydantic models |
| `backend/src/plus_one/prompts/itinerary/v1.md` | new | Scheduler prompt |
| `backend/src/plus_one/prompts/joiner/v4.md` | new | v3 + long_description |
| `backend/src/plus_one/agents/joiner.py` | edit | new fields, image propagation, bump to v4 |
| `backend/src/plus_one/services/trip_runner.py` | edit | call scheduler post-save; project date_start/end into context |
| `backend/src/plus_one/api/trips.py` | edit | `day_plan` in `TripDetail` |
| `backend/src/plus_one/api/shared.py` | edit | expose `day_plan` in shared response |
| `frontend/lib/schemas/trips.ts` | edit | new Zod types + content extension |
| `frontend/components/trips/ItineraryView.tsx` | new | day-by-day rendering |
| `frontend/app/app/trips/[id]/page.tsx` | edit | conditional ItineraryView vs ReportView |
| `frontend/app/share/[token]/page.tsx` | edit | same conditional |
| `frontend/e2e/trip-flow.spec.ts` | edit | day_plan assertions |
| `frontend/e2e/_helpers/fake-maestro.ts` + integration | new | mock Anthropic-API server so trip-flow runs in CI |

## Implementation waves

- **Wave A (parallel)**: backend schemas; frontend Zod schemas; ItineraryView shell against mocked data
- **Wave B (sequential)**: joiner image propagation → joiner v4 prompt → scheduler → page wiring (owner + shared)
- **Wave C**: fake-maestro server for e2e → e2e spec update → CI green

## Risks

| Risk | Mitigation |
|------|------------|
| LLM emits bad `item_index` | Pydantic validator → scheduler returns None → flat fallback |
| Foursquare `external_url` null | `.is-typed` placeholder card (already in scrapbook.css) |
| Existing trips lack `day_plan` | Frontend backward-compat path |
| Refine cycle doesn't regenerate | `run_refine` also calls scheduler |
| `AgentContext` missing date fields | Add `date_start`/`date_end` to context; scheduler defaults to 3 days |

## Validation plan

- Unit: validate `ItineraryPlan` (duplicate / out-of-range indices), `DaySlot` periods
- Unit: joiner propagates `image_url` from mock Foursquare
- Integration: full `run_trip` against fixture → assert `day_plan` JSONB shape
- e2e (CI): see AC-10, AC-11. Uses fake-maestro server.
- Manual: visual diff against `docs/design/scrapbook/pages/trip-detail-itinerary.html`

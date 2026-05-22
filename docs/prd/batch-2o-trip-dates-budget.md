# PRD: batch-2o — Trip Input: Dates + Budget

## 1. Problem

The Trip create form (`/app/trips/new`) accepts only `destination`, `free_text`, and `companion_ids`. The product PRD (`docs/prd.md` §4 "Mode D — Hybrid") calls for structured inputs alongside the free-text channel: **destination**, **dates**, **party**, **budget**. Party (companions) shipped in batch-2h. Destination already exists. **Dates and budget are still missing from the wire and the UI**, even though the DB already has the columns (`trips.date_start`, `trips.date_end`, `trips.budget_amount`, `trips.budget_currency` — `backend/src/plus_one/core/db/models.py:195-198`).

Users who know their travel window or their budget today have no way to tell us. They either jam it into `free_text` (where the agent may or may not see it) or omit it entirely. This batch closes the gap by exposing the existing columns through the API and the form. The four fields stay **optional** — Mode D is hybrid, not a wizard, and old trips and free-text-only flows must keep working unchanged.

## 2. Goals / Non-Goals

**Goals**
- Add four optional fields to `POST /api/trips`: `date_start`, `date_end`, `budget_amount`, `budget_currency`.
- Persist them onto the existing `trips` columns. No new migration.
- Render two date inputs and a budget (amount + currency) input on `TripForm`.
- Echo the four fields back on `GET /api/trips/{id}` (`TripDetail`) so the detail page (future batch) can render them.
- Validate at the zod boundary: `date_end >= date_start`; `budget_amount >= 0`; currency in a fixed whitelist.

**Non-Goals**
- Rendering dates/budget on the trip detail / report page (follow-up — wire is ready, UI is not in this batch).
- LLM agent using `date_start`, `date_end`, `budget_amount`, `budget_currency` for planning. Stored only; the runner does not pass them into `AgentContext` yet (follow-up).
- Destination autocomplete (batch-2n).
- Clarifier loop / Mode D conversational fallback (batch-2t).
- Date range > 30 days cap. Multi-currency conversion. Per-locale currency formatting.
- A third-party date-picker component. Native `<input type="date">` only.

## 3. User Scenarios

**3.1 Happy path — all four fields**
Mei is planning Tokyo, Oct 12 → Oct 19, around 2,500 USD. She types `tokyo` into "the place", picks `2026-10-12` and `2026-10-19` in the two date inputs, types `2500` in the budget amount, leaves the currency on USD. She submits. `POST /api/trips` returns `202` with a `trip_id`. The `trips` row has all four columns populated. The SSE stream runs as today (no agent change). On `GET /api/trips/{id}` the four fields come back on `TripDetail` unchanged.

**3.2 Optional-skip path — destination + free_text only**
Aiko opens the form, types `kyoto`, writes "tonkotsu ramen, quiet counters" in the mood box, ignores the date and budget inputs entirely, submits. `POST /api/trips` is accepted; `date_start`, `date_end`, `budget_amount`, `budget_currency` are all `null` in the DB. The runner runs as today. `TripDetail` returns `null` for each of the four fields. No warning, no nudge, no error — Mode D is hybrid by design.

**3.3 Validation error path — end before start**
Riku picks `2026-11-05` as start and `2026-11-02` as end. He tabs away from the second input. On submit, zod fails with `the end is before the start. flip them?` attached to `date_end`. Submit is blocked client-side; no network call is made. If a bad client somehow POSTs the same payload, the backend `CreateTripBody` re-runs the same check via a `model_validator` and returns `422` with `{"detail": [{"loc": ["body"], "msg": "date_end must be on or after date_start", ...}]}`.

Bonus validation:
- Negative `budget_amount` → zod error `budget can't be negative.` (client) / `422` (server).
- Currency not in whitelist → zod error `pick one of the listed currencies.` (client) / `422` (server).

## 4. Technical Design

### 4.1 Backend changes

**`backend/src/plus_one/api/trips.py`**

Extend `CreateTripBody` (line 39) with four optional fields and a cross-field validator:

```python
from datetime import datetime
from pydantic import model_validator

_ALLOWED_CURRENCIES = frozenset({"USD", "EUR", "JPY", "CNY", "GBP", "TWD", "KRW", "AUD"})

class CreateTripBody(BaseModel):
    destination: str = Field(min_length=1, max_length=200)
    free_text: str | None = Field(default=None, max_length=2000)
    companion_ids: list[UUID] = Field(default_factory=list, max_length=50)
    date_start: datetime | None = None
    date_end: datetime | None = None
    budget_amount: int | None = Field(default=None, ge=0, le=10_000_000)
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)

    @model_validator(mode="after")
    def _check_ranges(self) -> "CreateTripBody":
        if self.date_start and self.date_end and self.date_end < self.date_start:
            raise ValueError("date_end must be on or after date_start")
        if self.budget_currency is not None and self.budget_currency not in _ALLOWED_CURRENCIES:
            raise ValueError(f"budget_currency must be one of {sorted(_ALLOWED_CURRENCIES)}")
        # If one budget field is set, the other should be too — but per locked
        # decisions all four are independently optional, so we leave the half-
        # filled case alone (currency defaults to USD client-side; if the
        # client omits both, both stay null in DB).
        return self
```

Update `create_trip` handler (line 111) to persist the four fields:

```python
trip = Trip(
    user_id=user.id,
    destination=body.destination,
    free_text=body.free_text,
    date_start=body.date_start,
    date_end=body.date_end,
    budget_amount=body.budget_amount,
    budget_currency=body.budget_currency,
    status="pending",
)
```

Extend `TripDetail` (line 55) with the same four optional fields and populate them in `get_trip` (line 253):

```python
class TripDetail(BaseModel):
    trip_id: UUID
    destination: str
    status: str
    latest_report_id: UUID | None = None
    content: dict[str, object] | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    budget_amount: int | None = None
    budget_currency: str | None = None
```

```python
return TripDetail(
    trip_id=trip.id,
    destination=trip.destination,
    status=trip.status,
    latest_report_id=latest.id if latest else None,
    content=latest.content if latest else None,
    date_start=trip.date_start,
    date_end=trip.date_end,
    budget_amount=trip.budget_amount,
    budget_currency=trip.budget_currency,
)
```

**`backend/src/plus_one/services/trip_runner.py`** — **no code change**. Stored on the Trip row, not yet read by `run_trip`. Add a comment on `run_trip` (~line 313) noting the four columns are persisted but not yet projected into `AgentContext`; follow-up batch will wire them in.

**No migration.** Columns already exist (`models.py:195-198`).

### 4.2 Frontend changes

**`frontend/lib/schemas/trips.ts`** — extend `CreateTripBody` and `TripDetail`:

```ts
export const CURRENCIES = ["USD", "EUR", "JPY", "CNY", "GBP", "TWD", "KRW", "AUD"] as const;
export const Currency = z.enum(CURRENCIES);

export const CreateTripBody = z
  .object({
    destination: z.string().min(1, "destination is required").max(200),
    free_text: z.string().max(2000).optional(),
    companion_ids: z.array(z.string().uuid()).max(50).optional(),
    date_start: z.string().datetime({ offset: true }).optional(),
    date_end: z.string().datetime({ offset: true }).optional(),
    budget_amount: z
      .number()
      .int("whole numbers only.")
      .nonnegative("budget can't be negative.")
      .max(10_000_000)
      .optional(),
    budget_currency: Currency.optional(),
  })
  .superRefine((val, ctx) => {
    if (val.date_start && val.date_end && val.date_end < val.date_start) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["date_end"],
        message: "the end is before the start. flip them?",
      });
    }
  });
```

`TripDetail` gains four matching optional nullable fields (mirror backend).

**`frontend/components/trips/TripForm.tsx`** — add two new `field` blocks between `who you're bringing` and `the mood, the foods, what to avoid`. Form state: convert raw `<input type="date">` value (`YYYY-MM-DD`) to ISO at submit time (`new Date(v + "T00:00:00Z").toISOString()`); convert back the same way when rendering defaults. `budget_amount` is registered with `valueAsNumber: true`; empty string → `undefined` (not 0).

On submit, only include each field in the body if it has a value (mirrors existing `free_text` / `companion_ids` pattern at line 31-39):

```ts
const body: CreateTripBodyT = {
  destination: values.destination,
  ...(values.free_text ? { free_text: values.free_text } : {}),
  ...(values.companion_ids?.length ? { companion_ids: values.companion_ids } : {}),
  ...(values.date_start ? { date_start: values.date_start } : {}),
  ...(values.date_end ? { date_end: values.date_end } : {}),
  ...(typeof values.budget_amount === "number" ? { budget_amount: values.budget_amount } : {}),
  ...(values.budget_currency ? { budget_currency: values.budget_currency } : {}),
};
```

`defaultValues` gains `date_start: ""`, `date_end: ""`, `budget_amount: undefined`, `budget_currency: "USD"` (sensible default; user can change).

**Voice copy table**

| Element | Copy |
|---|---|
| dates section label | `when` |
| date_start label | `from` |
| date_start input | native `<input type="date">`, no placeholder |
| date_start hint | (none — sits inside the shared dates hint below) |
| date_end label | `to` |
| date_end input | native `<input type="date">`, no placeholder |
| dates shared hint | `optional. skip if you haven't picked yet.` |
| date_end validation error | `the end is before the start. flip them?` |
| budget section label | `your budget` |
| budget_amount label | `how much, roughly` |
| budget_amount placeholder | `2500` |
| budget_amount hint | (none — sits inside the shared budget hint below) |
| budget_currency label | `currency` |
| budget_currency options | `USD`, `EUR`, `JPY`, `CNY`, `GBP`, `TWD`, `KRW`, `AUD` |
| budget shared hint | `optional. round numbers are fine — it's a hint, not a ceiling.` |
| budget_amount negative error | `budget can't be negative.` |
| budget_amount non-integer error | `whole numbers only.` |
| budget_currency invalid error | `pick one of the listed currencies.` |
| destination required error (existing — re-lowercased for consistency) | `destination is required` |

All copy lowercase, no exclamation, no banned phrases. No status nouns.

### 4.3 Files modified

| File | Lines (approx) | Change |
|---|---|---|
| `backend/src/plus_one/api/trips.py` | 39-47 | Add 4 optional fields + `model_validator` + `_ALLOWED_CURRENCIES` constant to `CreateTripBody` |
| `backend/src/plus_one/api/trips.py` | 55-60 | Add 4 optional fields to `TripDetail` |
| `backend/src/plus_one/api/trips.py` | 117-122 | Pass 4 fields into `Trip(...)` constructor |
| `backend/src/plus_one/api/trips.py` | 268-274 | Echo 4 fields in `TripDetail` response |
| `backend/src/plus_one/services/trip_runner.py` | ~313 | Comment only: note new fields persisted but not yet used |
| `backend/tests/integration/test_trips_list.py` | n/a (new test in this file or `test_trips_create.py`) | See §6 |
| `frontend/lib/schemas/trips.ts` | 7-11 | Extend `CreateTripBody` with 4 fields + `superRefine` + export `CURRENCIES` / `Currency` |
| `frontend/lib/schemas/trips.ts` | 74-80 | Extend `TripDetail` with 4 optional nullable fields |
| `frontend/components/trips/TripForm.tsx` | 25 | Extend `defaultValues` |
| `frontend/components/trips/TripForm.tsx` | 28-51 | Extend submit body construction |
| `frontend/components/trips/TripForm.tsx` | ~106 (between companions and mood) | Add `when` field block (two date inputs) |
| `frontend/components/trips/TripForm.tsx` | ~106 | Add `your budget` field block (amount + currency select) |

### 4.4 New files

None planned. If the backend tests file grows unwieldy, a new `backend/tests/integration/test_trips_create.py` may be added for the new cases; otherwise the cases live alongside existing trip-create tests.

### 4.5 Concurrent-batch warning

Two other in-flight batches touch the **same** `TripForm.tsx` and `lib/schemas/trips.ts`:

- **batch-2n** — destination autocomplete (replaces the `destination` text input with a combobox).
- **batch-2t** — clarifier loop (adds a conditional follow-up question UI inside the form).

**Merge order: 2n → 2o → 2t.**

- 2n lands first (smallest blast radius on the form: swaps one input).
- 2o lands second (adds two new field blocks; does not touch the destination input).
- 2t lands last (consumes the now-complete structured fields — destination, dates, budget — to decide what to ask).

If 2o lands before 2n, the 2n author rebases their destination-combobox PR on top of the new field ordering. If 2t lands before 2o, 2o is responsible for re-ordering the clarifier slot below the new structured-fields region.

Code Agents implementing 2o **must** rebase on master immediately before opening the PR and re-run the frontend test suite — a stale TripForm.tsx is the single most likely merge-conflict source in this batch.

## 5. API contract

### 5.1 `POST /api/trips` request body — before

```json
{
  "destination": "tokyo",
  "free_text": "tonkotsu ramen, quiet counters",
  "companion_ids": ["8c2d…"]
}
```

### 5.2 `POST /api/trips` request body — after

```json
{
  "destination": "tokyo",
  "free_text": "tonkotsu ramen, quiet counters",
  "companion_ids": ["8c2d…"],
  "date_start": "2026-10-12T00:00:00Z",
  "date_end":   "2026-10-19T00:00:00Z",
  "budget_amount": 2500,
  "budget_currency": "USD"
}
```

All four new fields are **optional**. Any subset (or none) may be omitted. Response shape (`CreateTripResponse`) is unchanged: `{trip_id, status}` with `202 Accepted`.

### 5.3 `GET /api/trips/{id}` response — before

```json
{
  "trip_id": "…",
  "destination": "tokyo",
  "status": "complete",
  "latest_report_id": "…",
  "content": { "items": [/* … */] }
}
```

### 5.4 `GET /api/trips/{id}` response — after

```json
{
  "trip_id": "…",
  "destination": "tokyo",
  "status": "complete",
  "latest_report_id": "…",
  "content": { "items": [/* … */] },
  "date_start": "2026-10-12T00:00:00Z",
  "date_end":   "2026-10-19T00:00:00Z",
  "budget_amount": 2500,
  "budget_currency": "USD"
}
```

Old trips (created before this batch) return `null` for all four new fields. The detail-page renderer (future batch) is responsible for treating `null` as "not provided".

### 5.5 Error shapes

`422 Unprocessable Entity` from FastAPI for: end-before-start; currency outside whitelist; negative budget; non-integer budget; budget over 10,000,000. Error body follows FastAPI's standard `detail: [{loc, msg, type}]` form.

## 6. Testing

### 6.1 Backend pytest

Add to `backend/tests/integration/test_trips_create.py` (or appropriate existing file):

1. **happy path with all four fields** — POST with `date_start`, `date_end`, `budget_amount`, `budget_currency`. Assert `202`, then assert row in DB has the four columns populated (query via session).
2. **omit all four (back-compat)** — POST with only `destination`. Assert `202`, row has `null` for all four.
3. **partial — dates only, no budget** — POST with both dates, no budget. Assert `202`, dates populated, budget columns `null`.
4. **partial — budget only, no dates** — POST with `budget_amount: 1000`, `budget_currency: "JPY"`. Assert `202`, budget populated, date columns `null`.
5. **end before start → 422** — POST with `date_end < date_start`. Assert `422` and `"date_end must be on or after date_start"` in detail.
6. **currency not in whitelist → 422** — POST with `budget_currency: "ZZZ"`. Assert `422`.
7. **negative budget → 422** — POST with `budget_amount: -1`. Assert `422`.
8. **non-integer budget rejected at JSON parse → 422** — POST with `budget_amount: 2.5`. Assert `422`.
9. **trip detail echoes new fields** — POST with all four, then GET `/api/trips/{id}`, assert response contains all four with correct values.
10. **trip detail returns null on legacy trip** — insert a `Trip` row directly via session with all four columns null, GET `/api/trips/{id}`, assert all four fields are `null`.

### 6.2 Frontend vitest — zod schema (`frontend/lib/schemas/trips.test.ts` if exists, else new file)

1. parses minimal `{destination: "tokyo"}` → ok.
2. parses full payload (all 7 fields) → ok.
3. rejects `date_end < date_start` → issue path `["date_end"]`, message matches voice copy.
4. rejects `budget_currency: "ZZZ"` → enum error.
5. rejects `budget_amount: -5` → message `"budget can't be negative."`.
6. rejects `budget_amount: 2.5` → message `"whole numbers only."`.
7. accepts `budget_amount: 0` (zero budget is a valid signal).
8. accepts missing currency when amount is missing (both omitted is valid).

### 6.3 Frontend RTL — `TripForm.test.tsx`

1. **renders both date inputs and the budget block** — by label text `from`, `to`, `how much, roughly`, `currency`.
2. **submits without dates or budget** — fills only destination, submits, asserts `createTrip` was called with a body that **does not** contain `date_start`, `date_end`, `budget_amount`, `budget_currency` keys.
3. **submits with all fields** — fills all, asserts `createTrip` body contains the ISO-formatted dates, numeric `budget_amount`, and `budget_currency`.
4. **shows the end-before-start error inline** — fills dates in reverse order, submits, asserts the voice-copy error appears next to the `to` input and `createTrip` is not called.
5. **defaults currency to USD** — query the `currency` select and assert its default value is `USD`.

## 7. Rollout

- **No feature flag.** Additive only.
- **No DB migration.** Columns exist.
- **Old trips render fine** — backend returns `null` for the four new fields on rows created before this batch; the existing detail page ignores unknown / null fields.
- **Old clients keep working** — request body fields are optional; servers ignoring them is impossible because the same server serves both old and new clients, but clients posting the old 3-field body continue to validate and succeed.
- Ship plan: merge backend + frontend together in one PR (small surface). Run backend pytest + frontend vitest + the existing TripForm RTL suite. Manual smoke: open `/app/trips/new`, submit one trip with all fields, one with none, one with mismatched dates.

## 8. Open Questions

_None._

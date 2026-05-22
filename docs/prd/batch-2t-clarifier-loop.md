# PRD: batch-2t — Clarifier Loop

**Author:** fhw12345
**Date:** 2026-05-22
**Status:** Draft

---

## 1. Problem (PRD §4 promises 0-3 LLM follow-ups; ships as zero)

The canonical product PRD (`docs/prd.md` §4) describes **Mode D — Hybrid** input as:

> structured fields (destination / dates / party / budget) + free text + **0–3 LLM-generated follow-up questions**

Today's `POST /api/trips` (`backend/src/plus_one/api/trips.py:100`) does no such follow-up. It creates the Trip row in `status="pending"`, registers an SSE queue, schedules `run_trip` as a `BackgroundTask`, and the frontend (`frontend/components/trips/TripForm.tsx`) immediately `router.push`es to the detail page. The 90-second agent cycle then runs with whatever the user typed — even if a single clarifier ("fixed dates or flexible?", "any cuisines you've already ruled out?") would have meaningfully tightened the plan.

We are shipping 0% of the promised "0–3" range. This batch closes that gap with a **single-round** clarifier inserted between form submit and agent kickoff.

---

## 2. Goals / Non-Goals

### Goals

- Run **one** clarifier LLM call after `POST /api/trips` and **before** the full agent cycle starts.
- Return 0–3 questions synchronously on the POST response (clarifier budget ≤5s; well under the SSE setup timeout the frontend already tolerates).
- If 0 questions: passthrough — flip status to `running`, kick off `run_trip` exactly as today, frontend redirects immediately.
- If 1–3 questions: park the trip in a new `clarifying` status; surface the questions inline on the new-trip page; only kick off `run_trip` after the user submits answers (or explicitly skips).
- Persist both the LLM-generated questions and the user's answers on the Trip row so the runner / future audit can see what was asked and answered.
- Voice: scrapbook lowercase, conversational, no emoji, no exclamation. Questions are written by the LLM under a tone-locked prompt.
- Single-shot only: there is no second round of clarifiers after the user answers.

### Non-Goals

- **Multi-turn clarifier.** Strictly one round. If the LLM wants to ask again it can't.
- **Per-question skip.** All questions are answered, or none are (skip is all-or-nothing).
- **Clarifier from past trip history.** This batch only reads `destination`, `free_text`, and the trip's resolved companion preferences. No `user.visited_cities`, no past `reports`.
- **Non-English clarifier output.** LLM is instructed to write in English regardless of user locale; localized clarifier is deferred to a later batch.
- **Editing answers after submit.** Once `/clarify` is POSTed, the cycle starts; there is no "go back and re-answer."
- **Showing questions on any page other than the new-trip page.** If the user navigates away mid-clarifier, the trip remains in `clarifying` until they navigate back; we do not auto-skip after a timeout in this batch (see Open Questions).
- **Backfilling clarifier on existing trips.** Pre-deploy trips that are already in `pending` / `running` finish under the old code path.

---

## 3. User Scenarios

### Scenario A — clarifier returns 2 questions (happy path)

1. User on `/app/trips/new` fills in destination "kyoto", picks one companion, types free text "first time, want quiet temples and good coffee, no big crowds."
2. Submits. `POST /api/trips` runs the clarifier prompt synchronously (~3s spinner on submit button — copy "thinking out loud…").
3. Response: `201 {trip_id, status: "clarifying", clarifier_questions: [{id: "q1", text: "fixed dates or flexible?"}, {id: "q2", text: "okay with bus / metro / both?"}]}`.
4. `TripForm` swaps its body for `<ClarifierStep>` showing the two questions with two `<textarea>`s and a "skip these" link.
5. User answers both, presses submit. `POST /api/trips/{id}/clarify` with `{answers: [{id:"q1", text:"…"}, {id:"q2", text:"…"}]}`.
6. Server flips status `clarifying → running`, schedules `run_trip` with the augmented query, returns `{status:"running"}`. Frontend `router.push`es to `/app/trips/{id}`.

### Scenario B — clarifier returns 0 questions (passthrough)

1. User submits a very precise form ("kyoto, may 4–7, two adults, fixed dates, walking only, vegetarian, no temples"). LLM judges nothing material is missing.
2. `POST /api/trips` returns `201 {trip_id, status: "running", clarifier_questions: []}`.
3. `TripForm` sees the empty array — equivalent to the old fast path — and immediately `router.push`es to `/app/trips/{id}`. No `ClarifierStep` ever rendered.
4. `run_trip` is already scheduled server-side (see §4.1). SSE stream picks up.

### Scenario C — user skips clarifier

1. As Scenario A, but at step 4 the user clicks "skip these" instead of typing.
2. `POST /api/trips/{id}/clarify/skip` with empty body. Server flips status `clarifying → running`, schedules `run_trip` with the original query (no augmentation). `clarifier_answers` is stored as `null`. Returns `{status:"running"}`.
3. `router.push` as Scenario A.

### Scenario D — user double-submits clarify (409)

1. User in Scenario A clicks the submit button twice fast (or two tabs open). First request wins.
2. Second `POST /api/trips/{id}/clarify` sees `trip.status != "clarifying"` (it's now `running`). Server returns `409 {detail: "trip_not_clarifying"}`.
3. Frontend `ClarifierStep` catches the 409, shows scrapbook-voiced annotation "already started — opening it for you…" and still navigates to `/app/trips/{id}`.

---

## 4. Technical Design

### 4.1 Backend

#### Alembic migration

New revision: `backend/alembic/versions/20260522_0006_batch_2t_clarifier_loop.py`

- `ADD COLUMN trips.clarifier_questions JSONB NULL` — stores the array `[{id, text}]` produced by the LLM. Nullable because trips created before this deploy and trips that get 0 questions don't need a value.
- `ADD COLUMN trips.clarifier_answers JSONB NULL` — stores `[{id, text}]` from the user. Nullable; `null` means "skipped" or "not yet collected"; an empty list is reserved (do not write `[]` — write `null`).
- Drop and recreate `CheckConstraint("ck_trips_status")` to widen the allowed set:
  - Old: `status IN ('pending', 'running', 'complete', 'aborted')`
  - New: `status IN ('pending', 'clarifying', 'running', 'complete', 'aborted')`
- Downgrade: drop the two columns; restore old CHECK. Downgrade is destructive for any rows in `clarifying` — acceptable, since it requires manually rolling back a production deploy.

`backend/src/plus_one/core/db/models.py`:

- Extend the `_TRIP_STATUSES` tuple: `("pending", "clarifying", "running", "complete", "aborted")`.
- Add two columns to `Trip`:
  - `clarifier_questions: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)`
  - `clarifier_answers: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)`

#### New prompt: `backend/src/plus_one/prompts/clarifier/v1.md`

First file under `prompts/`. Add `prompts/__init__.py` (empty package marker) and `prompts/clarifier/__init__.py`. The prompt is a Markdown file loaded by the clarifier service via `importlib.resources`.

Prompt rules the file MUST encode:

1. **Inputs visible to LLM**: `destination`, `free_text`, the resolved list of `companion_preferences` (loves / hates / constraints) chosen for this trip. Nothing else — no `User.visited_cities`, no past `Report`s.
2. **Output schema**: strict JSON `{"questions": [{"id": "q1", "text": "..."}, ...]}`, 0–3 entries. `id` is `q1` … `q3` in order. No prose, no markdown, no preamble.
3. **When to ask** (the rule that gates count down to 0–3):
   - Ask only when the answer would **meaningfully change the plan**. Examples that justify a question: missing dates when seasonality matters; "vegetarian" said but no severity (preference vs strict); no transit constraint stated for a sprawling city.
   - Do NOT ask flavor questions ("what excites you most?"), validation questions ("is kyoto right?"), or anything already answered in `free_text`.
4. **Voice**: scrapbook lowercase. Conversational. No exclamation marks. Contractions ok. Em-dashes ok. No emoji. Max ~80 chars per question. Examples baked into the prompt:
   - "any restaurants you've already ruled out?"
   - "fixed dates or flexible?"
   - "okay with bus / metro / both?"
5. **Banned phrases**: "Could you please", "I'd love to know", "As an AI", "Help me understand", any title-case sentences.
6. **Fallback**: if the model is unsure, return `{"questions": []}` rather than asking weak questions.

The prompt body explicitly shows the JSON shape and a 1-question, 2-question, and 0-question example.

#### Clarifier service

New module: `backend/src/plus_one/services/clarifier.py`.

```python
async def run_clarifier(
    *,
    destination: str,
    free_text: str | None,
    companion_preferences: list[dict],
) -> list[dict]:
    """Return 0–3 questions [{id, text}]. Bounded by CLARIFIER_TIMEOUT_S (5s).
    On timeout, model error, or invalid JSON → return [] (fail-open: skip clarifier,
    do not block the trip)."""
```

- Reads the prompt via `importlib.resources.files("plus_one.prompts.clarifier") / "v1.md"`.
- Uses the existing LLM client (same one as the producer/joiner agents — share config and credentials).
- Validates LLM output: JSON parse; ensure `questions` is a list of ≤3 dicts each with non-empty `id` and `text`; truncate to 3; assign ids `q1..q3` defensively.
- Logs `clarifier_skipped` with reason if it falls back to `[]` (timeout / parse error / empty).

#### `POST /api/trips` — revised flow

`backend/src/plus_one/api/trips.py:100`

1. Validate body (unchanged).
2. Insert Trip with `status="pending"`. Flush to get id. **Do not commit yet.**
3. Call `await run_clarifier(...)`.
4. If clarifier returns `[]`:
   - Set `trip.status = "running"`, `trip.clarifier_questions = None`.
   - Commit.
   - `register(trip.id)` + `background.add_task(run_trip, ...)` — same as today.
   - Return `201 {trip_id, status: "running", clarifier_questions: []}`.
5. If clarifier returns 1–3 questions:
   - Set `trip.status = "clarifying"`, `trip.clarifier_questions = questions`.
   - Commit.
   - **Do not** register a queue, **do not** schedule `run_trip`. Both happen at `/clarify` time.
   - Return `201 {trip_id, status: "clarifying", clarifier_questions: questions}`.

Response status code changes from `202 Accepted` to **`201 Created`** since we always have the row persisted at return-time now. Update the route decorator and downstream tests.

#### `POST /api/trips/{trip_id}/clarify`

New route. Body:

```json
{"answers": [{"id": "q1", "text": "fixed dates"}, {"id": "q2", "text": "metro mostly"}]}
```

Flow:

1. Load Trip `with_for_update` (same pattern as `delete_trip`).
2. 404 if not found / wrong user.
3. 409 with `detail: "trip_not_clarifying"` if `trip.status != "clarifying"`.
4. Validate `answers`:
   - Length matches `len(trip.clarifier_questions)`.
   - Every `id` in `answers` matches an id in `trip.clarifier_questions`.
   - Every `text` is non-empty after `.strip()` and ≤ 1000 chars.
   - On validation failure → 422.
5. Set `trip.clarifier_answers = answers`, `trip.status = "running"`.
6. Commit.
7. Build query: `destination | free_text | answers as "q1: …; q2: …"`. Pass to `run_trip`.
8. `register(trip.id)` + `background.add_task(run_trip, ...)`.
9. Return `200 {status: "running"}`.

#### `POST /api/trips/{trip_id}/clarify/skip`

New route. Empty body.

Flow:

1. Load Trip `with_for_update`. 404 / 409 as above.
2. Leave `trip.clarifier_answers = None`.
3. Set `trip.status = "running"`. Commit.
4. Build query from `destination | free_text` only (no augmentation). Pass to `run_trip`.
5. `register(trip.id)` + `background.add_task(run_trip, ...)`.
6. Return `200 {status: "running"}`.

#### Trip status transitions

```
pending ──(clarifier returns [])──► running ──► complete | aborted
pending ──(clarifier returns 1–3)──► clarifying ──(POST /clarify)──► running ──► complete | aborted
                                                 ──(POST /clarify/skip)──► running ──► complete | aborted
```

`pending` becomes effectively a transient in-process state inside `POST /api/trips` — never observed externally. Kept in the CHECK constraint for backwards compatibility with the existing migration history and for any in-flight rows at deploy time.

### 4.2 Frontend

#### `TripForm.tsx` submit handler

Replace the unconditional `router.push` with a branch on `res.status`:

```ts
const res = await createTrip(body);
if (res.status === "clarifying" && res.clarifier_questions && res.clarifier_questions.length > 0) {
  setClarifierState({ tripId: res.trip_id, questions: res.clarifier_questions });
  return;
}
router.push(`/app/trips/${res.trip_id}`);
```

`TripForm` gains internal state `clarifierState: {tripId, questions} | null`. When non-null, render `<ClarifierStep />` in place of the form body (preserve the scrapbook frame, tape, and stamp; swap only the inner card).

#### New component: `ClarifierStep`

`frontend/components/trips/ClarifierStep.tsx`.

Props:

```ts
{ tripId: string; questions: { id: string; text: string }[]; }
```

Renders:

- A short header in scrapbook voice: `"a couple more things —"` (1 question) / `"a few more —"` (2–3 questions).
- One `<textarea>` per question, labeled with the question text (rendered as a scrapbook annotation, lowercase as the LLM produced it). Rows=2.
- A primary button `"okay — go look →"` (same scrapbook button style as the form).
- A "skip these" link rendered as an underlined scrawl beneath the button.

Validation: client-side `zod` schema requires every textarea non-empty after trim. On submit:

1. Disable inputs.
2. `POST /api/trips/{tripId}/clarify` with the answers.
3. On 200 → `router.push(/app/trips/{tripId})`.
4. On 409 → show "already started — opening it for you…" and `router.push` anyway.
5. On 422 → show scrapbook error "didn't quite catch that — try again?" and re-enable.
6. On network error → show "something snagged on the wire. one more try?" and re-enable.

Skip link:

1. `POST /api/trips/{tripId}/clarify/skip`.
2. On 200 / 409 → `router.push(/app/trips/{tripId})`.

#### Voice copy table

| UI location | English copy (lowercase, scrapbook) |
|---|---|
| Submit button (form, pending clarifier) | `thinking out loud…` |
| Submit button (form, idle) | `go look →` |
| Clarifier header (1 question) | `a couple more things —` |
| Clarifier header (2–3 questions) | `a few more —` |
| Clarifier primary button (idle) | `okay — go look →` |
| Clarifier primary button (submitting) | `off i go…` |
| Skip link | `skip these` |
| 409 toast | `already started — opening it for you…` |
| 422 inline | `didn't quite catch that — try again?` |
| Network inline | `something snagged on the wire. one more try?` |

Banned in this UI: any title-case, "Please", "Sorry", "Oops", emoji, exclamation marks.

### 4.3 Files modified table

| File | Change |
|---|---|
| `backend/alembic/versions/20260522_0006_batch_2t_clarifier_loop.py` | NEW. Add `clarifier_questions`, `clarifier_answers`, widen status CHECK to include `'clarifying'`. |
| `backend/src/plus_one/core/db/models.py` | Add `'clarifying'` to `_TRIP_STATUSES`; add two JSONB columns to `Trip`. |
| `backend/src/plus_one/api/trips.py` | Revise `POST /api/trips` (clarifier call, 201 + branching response); add `POST /{id}/clarify` and `POST /{id}/clarify/skip`; extend response models. |
| `backend/src/plus_one/services/clarifier.py` | NEW. `run_clarifier(...)` wrapping the LLM call with 5s timeout + fail-open. |
| `backend/src/plus_one/prompts/__init__.py` | NEW. Empty package marker. |
| `backend/src/plus_one/prompts/clarifier/__init__.py` | NEW. Empty package marker. |
| `backend/src/plus_one/prompts/clarifier/v1.md` | NEW. Clarifier prompt (rules above). |
| `backend/tests/unit/services/test_clarifier.py` | NEW. Mocked-LLM tests: 0 / 1 / 3 / >3 / invalid JSON / timeout. |
| `backend/tests/integration/test_clarifier_api.py` | NEW. End-to-end through FastAPI test client. |
| `backend/tests/integration/test_trips_create.py` | Update for new 201 status + new response shape. |
| `frontend/lib/api/trips.ts` | Extend `createTrip` response type; add `clarifyTrip(tripId, answers)` and `skipClarifier(tripId)`. |
| `frontend/lib/schemas/trips.ts` | Add `ClarifierQuestion`, `ClarifierAnswer`, response schemas. |
| `frontend/components/trips/TripForm.tsx` | Branch on `status === "clarifying"`, render `ClarifierStep`. |
| `frontend/components/trips/ClarifierStep.tsx` | NEW. |
| `frontend/components/trips/ClarifierStep.test.tsx` | NEW (vitest + RTL). |
| `frontend/components/trips/TripForm.test.tsx` | Update / extend to cover clarifier branch. |

### 4.4 Concurrent-batch warning

**`frontend/components/trips/TripForm.tsx` is touched by three concurrent batches:**

- **batch-2n** — destination autocomplete combobox replaces the `<input id="dest">`.
- **batch-2o** — adds date pickers and budget field to the form.
- **batch-2t** (this batch) — wraps submit handler in a clarifier branch and renders `ClarifierStep` conditionally.

**Locked merge order: 2n → 2o → 2t.**

The 2t implementer MUST:

1. Wait until both 2n and 2o have merged to `main`.
2. Rebase the `feat/batch-2t-clarifier-loop` branch on `main` immediately before opening the PR.
3. Resolve `TripForm.tsx` by keeping the 2n combobox + 2o date/budget fields in the form body, then wrapping the submit handler with the clarifier branch from this batch.
4. Add a "rebased on latest main, conflicts resolved by hand" line in the PR description so review knows to look.

If 2n or 2o is delayed past this batch's target merge, escalate to team lead before resequencing — do not merge 2t ahead of them silently.

---

## 5. API contract

### POST /api/trips

**Request** (unchanged):

```json
{
  "destination": "kyoto",
  "free_text": "first time, want quiet temples and good coffee, no big crowds",
  "companion_ids": ["c1f7…"]
}
```

**Response 201** — clarifier produced 0 questions (passthrough):

```json
{
  "trip_id": "9a44…",
  "status": "running",
  "clarifier_questions": []
}
```

**Response 201** — clarifier produced 1–3 questions:

```json
{
  "trip_id": "9a44…",
  "status": "clarifying",
  "clarifier_questions": [
    {"id": "q1", "text": "fixed dates or flexible?"},
    {"id": "q2", "text": "okay with bus / metro / both?"}
  ]
}
```

**Errors**: `401` unauth, `422` validation, `500` if LLM client itself throws and the fail-open safety net is also exhausted (should be impossible — `run_clarifier` catches and returns `[]`).

### POST /api/trips/{trip_id}/clarify

**Request**:

```json
{
  "answers": [
    {"id": "q1", "text": "fixed: may 4 to may 7"},
    {"id": "q2", "text": "metro mostly, some walking"}
  ]
}
```

**Response 200**:

```json
{"status": "running"}
```

**Errors**:

- `401` unauth.
- `404 {"detail": "trip_not_found"}` — trip doesn't exist or belongs to another user.
- `409 {"detail": "trip_not_clarifying"}` — trip is in `pending` / `running` / `complete` / `aborted`.
- `422` — answers missing, extra ids, empty text, text > 1000 chars.

### POST /api/trips/{trip_id}/clarify/skip

**Request**: empty body.

**Response 200**:

```json
{"status": "running"}
```

**Errors**:

- `401` unauth.
- `404 {"detail": "trip_not_found"}`.
- `409 {"detail": "trip_not_clarifying"}`.

---

## 6. Testing

### Backend pytest

`backend/tests/unit/services/test_clarifier.py`:

- LLM mock returns 0 questions → `run_clarifier` returns `[]`.
- LLM mock returns 1 question → returned as-is, id normalized to `q1`.
- LLM mock returns 3 questions → returned as-is, ids `q1..q3`.
- LLM mock returns 5 questions → truncated to first 3, ids normalized.
- LLM mock returns invalid JSON → returns `[]`, logs `clarifier_skipped`.
- LLM mock raises `TimeoutError` → returns `[]`, logs `clarifier_skipped`.
- Banned phrases in questions → not enforced server-side at runtime (the prompt enforces; runtime can't string-match without false positives). Spot-checked manually in QA only.

`backend/tests/integration/test_clarifier_api.py`:

- `POST /api/trips` with clarifier mocked to return 0 → response status `"running"`, Trip row `status="running"`, `run_trip` scheduled.
- `POST /api/trips` with clarifier mocked to return 2 → response status `"clarifying"`, Trip row `status="clarifying"`, `clarifier_questions` persisted, `run_trip` NOT scheduled.
- `POST /api/trips/{id}/clarify` happy path → 200, status flips to `running`, `clarifier_answers` persisted, `run_trip` scheduled.
- `POST /api/trips/{id}/clarify` second call → 409 `trip_not_clarifying`.
- `POST /api/trips/{id}/clarify` with mismatched answer ids → 422.
- `POST /api/trips/{id}/clarify` with empty answer text → 422.
- `POST /api/trips/{id}/clarify/skip` happy path → 200, status flips to `running`, `clarifier_answers` stays `null`.
- `POST /api/trips/{id}/clarify/skip` on already-running trip → 409.
- Foreign user calling `/clarify` on someone else's trip → 404.

### Frontend vitest

`frontend/components/trips/ClarifierStep.test.tsx`:

- Renders 1 / 2 / 3 textareas matching `questions.length`.
- Renders the question text as labels.
- Submit disabled until all textareas have non-empty trimmed values.
- Submit calls `clarifyTrip(tripId, answers)` with the typed values; on 200 navigates to `/app/trips/{id}`.
- Submit on 409 shows the "already started" copy and still navigates.
- Submit on 422 shows the "didn't quite catch that" copy and re-enables inputs.
- Skip link calls `skipClarifier(tripId)`; on 200 navigates; on 409 navigates anyway.

### Frontend RTL — TripForm → ClarifierStep transition

`frontend/components/trips/TripForm.test.tsx` (extended):

- Mock `createTrip` to return `{status:"running", clarifier_questions:[]}` → expect `router.push` called immediately, no `ClarifierStep` ever rendered.
- Mock `createTrip` to return `{status:"clarifying", clarifier_questions:[2 items]}` → expect form body replaced with `ClarifierStep` showing 2 textareas; no `router.push` yet.
- After ClarifierStep submit → `router.push` fires.

---

## 7. Rollout

- **Migration is additive.** Two nullable JSONB columns + a CHECK widening. No data backfill. Safe to deploy ahead of code (Postgres accepts the wider CHECK; old code never writes `'clarifying'`).
- **Old in-flight trips finish normally.** Any `pending` / `running` row predating this deploy continues under the unchanged `run_trip` worker. The clarifier path is only entered through the new `POST /api/trips` flow.
- **No feature flag.** The product PRD specifies clarifier as part of Mode D; flagging it would just defer the integration cost. Fail-open in `run_clarifier` (timeout / model error → 0 questions → passthrough) is the production safety valve.
- **Frontend ships in the same release.** A frontend without backend support would treat every trip as passthrough (server still returns `clarifier_questions: []` if the column reads null) — survivable, but pointless.
- **Rollback path**: if the clarifier prompt is producing garbage in prod, set a one-line env override `CLARIFIER_FORCE_SKIP=1` (added in `config.py` as a no-op-by-default boolean) that makes `run_clarifier` return `[]` immediately. This lets us neutralize the feature without redeploying or running the downgrade migration.

---

## 8. Open Questions

1. **Stale `clarifying` trips.** If the user closes the tab on the ClarifierStep, the trip sits in `clarifying` forever. Should the trip list page (`/app/trips`) surface a "still waiting on your answers" affordance? **Proposal:** out of scope for 2t; revisit if support surfaces real complaints. A nightly cleanup job that auto-skips `clarifying` trips older than 24h is a candidate for a later batch.
2. **Companion preference resolution.** The clarifier prompt reads "the resolved list of companion preferences." Today the runner resolves `companion_ids` against `Companion` rows inside `run_trip`. We need to duplicate that resolution in the POST handler (or extract it to a shared helper). **Proposal:** extract `resolve_trip_companion_prefs(user_id, companion_ids) -> list[dict]` to `services/trip_runner.py` and call it from both the clarifier path and `run_trip`.
3. **Logging the clarifier exchange to SSE.** It might be useful for the cycle's first SSE event to echo "you also told me: q1 → …; q2 → …" so the live feed shows the augmented query. **Proposal:** out of scope for 2t; can be added once the SSE event taxonomy stabilizes.
4. **Should `clarifier_questions: []` be returned as the field key at all when status is `running`?** Slight API ergonomics question — clients can rely on `status` alone. **Proposal:** keep the empty array — easier for typed clients (`clarifier_questions: ClarifierQuestion[]` non-optional) and the payload size is negligible.
5. **Prompt versioning.** We're shipping `v1.md`. If we iterate the prompt we'll add `v2.md` and bump a constant in `services/clarifier.py`. Do we persist the prompt version onto the Trip row for audit? **Proposal:** defer; add only if a regression makes us wish we had it.

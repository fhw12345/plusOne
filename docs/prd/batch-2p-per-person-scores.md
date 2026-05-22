# PRD: batch-2p — Per-Card Per-Person Match Scores

**Author:** fhw12345
**Date:** 2026-05-22
**Status:** Draft

---

## 1. Problem

The report layout (PRD §4) ships six tabs: `together`, `you only`, `them only`, `two minds`, `local gems`, `tourist traps`. Two of them — `you only` and `them only` — render today as **empty buckets with an apology** (`frontend/lib/trips/categorize.ts:33-37` literally reads "coming once per-person tastes are wired in"). The wiring never happened.

That breaks PRD §3's headline promise: "*personalized to user + companion preferences*". The user-visible payoff of telling us who's on the trip, and of filling in companion loves/hates, is two empty tabs. PRD §4 also lists "per-person match scores" as a per-card output — but `JoinedItem` (backend) and `JoinedItemView` (frontend) have no score field today.

The inputs already exist: PRD §8 puts `explicit_preferences: {loves, hates}` on both `Profile` and `Companion` (see `backend/src/plus_one/core/db/models.py:107` and `:137`), and `trip_runner._load_profile_context` already loads them into `AgentContext.user_profile` and `AgentContext.selected_companions`. The joiner LLM sees them today via `render_preferences_section` — but only as ambient context for classification. It never emits per-person scores.

This batch closes that gap.

---

## 2. Goals / Non-Goals

### Goals

- Joiner agent emits a `match_scores: dict[person_id, float]` per item, covering the user and every selected companion on the trip.
- Score range is `0.0`–`1.0` (float). `1.0` = strongest match against that person's `loves`/`hates`; `0.0` = unlikely match. `null` = not scored.
- Frontend `categorize.ts` routes items into `you only` / `them only` using the scores (rules in §4.2).
- `ItemCard` shows a one-line score row in the **expanded** view only, in scrapbook voice.
- Old reports (no `match_scores`) gracefully degrade: `together` / `local gems` / `tourist traps` / `two minds` keep working; `you only` and `them only` stay empty (the current state).
- New joiner prompt `prompts/joiner/v3.md` — versioned per PRD §9; prompt change triggers an eval delta.

### Non-Goals

- Implicit preferences (PRD §8: "algorithm deferred to v2").
- Showing score reasoning / explanations to the user.
- Visualizing scores as bars / dots / sparklines — text only for v1.
- Per-person filter widgets inside tabs (e.g. "only show alice's picks" within `together`).
- Scoring against `constraints` (`dietary`, `mobility`, `max_walking`) — those become hard filters in a later batch.
- Mutating the four pre-existing tab buckets' rules: `together`, `disagreement`, `local_gems`, `tourist_traps` are unchanged.

---

## 3. User Scenarios

### S1 — Couple with divergent food taste (the primary motivating case)
The user (likes ramen, hates seafood) is planning Tokyo with companion **alice** (loves spicy food, loves seafood). The joiner picks up "Tsukiji Sushi Stall" and "Tonkotsu Ramen Bar".

- Tsukiji sushi: user_score `0.15`, alice_score `0.85` → bucket `them only` (alice's pick).
- Tonkotsu ramen: user_score `0.75`, alice_score `0.45` → bucket `together` (both fine; user_score not high enough above alice_score to be "you only" exclusive).
- Sichuan hotpot place: user_score `0.30`, alice_score `0.80` → `them only`.

The user sees the `them only` tab populated with actionable picks for the partner — the headline promise lands.

### S2 — Solo trip (no companions)
`companion_ids = []`. Joiner emits `match_scores = {user_id: 0.7}` (user only). `categorize.ts`:
- `you only` rule requires `every companion_score < 0.4` — vacuously true with zero companions. To avoid the entire `together` tab being shadowed into `you only`, the rule **also requires at least one companion present**. With zero companions, `you only` stays empty; everything routes to `together`.
- `them only` stays empty for the same reason.

### S3 — Old report opened post-deploy
A trip completed before this batch lands has `JoinedItem` rows with no `match_scores` field. Backend serializes them with `match_scores = None` (defaulted on the Pydantic model). Frontend `categorize.ts` skips score-based routing when `match_scores` is null/empty for the item. `you only` / `them only` stay empty, exactly as they are today. `TAB_EMPTY_COPY` still reads as "no picks yet" — no broken UI.

---

## 4. Technical Design

### 4.1 Backend changes

**New prompt `backend/src/plus_one/prompts/joiner/v3.md`** — copy `v2.md` then add a scoring section between `## Per-language classification` and `## User and companion preferences`. The prompt MUST receive the person list with their loves/hates AND their IDs so the LLM can key the output map correctly.

Prompt rules (verbatim text for the new section, scrapbook-neutral — this is internal, not user-facing):

```
## Per-person match scores

For each candidate, also emit a `match_scores` object keyed by person_id
(string UUIDs). The person list with IDs + loves/hates is given below in
the {person_roster} block. You MUST emit one score per person in the
roster — no extras, no omissions.

Each score is a float in [0.0, 1.0]:
  - 1.0  = strong match: candidate clearly aligns with that person's
           `loves`; no conflict with their `hates`.
  - 0.7  = good match: at least one love aligns; nothing they hate.
  - 0.5  = neutral / unknown — the person has no relevant preference
           expressed, or evidence is mixed.
  - 0.3  = weak match: nothing they love; one minor conflict with hates.
  - 0.0  = strong anti-match: candidate directly hits something on
           their `hates` list (e.g. "seafood" for a sushi bar).

When a person has empty loves AND empty hates, emit 0.5 (neutral by
default). Never emit null inside the map — null is for the whole map
in the rare case the candidate is so generic (e.g. "transit hub") that
no preference dimension applies; in that case set `match_scores: null`.

Scoring must use only the loves/hates given. Do NOT invent preferences.
Do NOT use the evidence list for scoring beyond confirming the candidate
matches its name and style.
```

The `{person_roster}` placeholder is rendered by a new helper (see §4.4) as:

```
- person_id=<uuid> name=you loves=[ramen] hates=[seafood]
- person_id=<uuid> name=alice loves=[spicy food, seafood] hates=[]
```

Output-format block in v3 gets one new field per item:

```json
"match_scores": { "<person_id>": 0.0, ... }
```

constrained to `dict[str, float] | None` on the schema side.

**Schema change — `JoinedItem` (backend/src/plus_one/agents/joiner.py):**

```python
match_scores: dict[UUID, float] | None = Field(
    default=None,
    description=(
        "Per-person match score in [0.0, 1.0]. Keyed by user.id "
        "(for the requesting user) and companion.id (for each "
        "selected companion). None = not scored (old reports, "
        "or candidates where scoring did not apply)."
    ),
)
```

Validation: a per-field validator clamps each value into `[0.0, 1.0]` and drops keys that don't correspond to a known person on the trip (defense against LLM hallucinated UUIDs). If the map ends up empty after dropping, coerce to `None`.

**Agent wiring — `joiner.py`:**

1. `UserProfileForContext` and `CompanionForContext` gain an `id: UUID` field (currently absent).
2. `trip_runner._load_profile_context` populates the new IDs from the DB rows.
3. `joiner` loads `prompts/joiner/v3.md` (bump from `v2`).
4. A new helper `render_person_roster(profile, companions)` (see §4.4) generates the `{person_roster}` block. `render_preferences_section` stays in place — the LLM still gets human-readable loves/hates for the classification reasoning.
5. The system prompt rendering does **two** `.replace` calls: `{preferences}` and `{person_roster}`.
6. After parse, joiner validates `match_scores` keys against the known person-ID set; unknown keys dropped, missing required keys filled with `0.5` (neutral default) so downstream code can rely on completeness.

**JSON serialization:** `JoinedItem.model_dump(mode="json")` already coerces UUID keys to strings — verify by snapshot test. Frontend reads `match_scores` as `Record<string, number>`.

### 4.2 Frontend changes

**Schema — `frontend/lib/schemas/trips.ts`:**

`JoinedItemView` gains:

```ts
match_scores?: Record<string, number> | null;
```

Plus a passthrough viewer-facing identity helper added to `TripDetail` or sourced from the existing trip context — the frontend needs the **user_id** and **companion_ids + names** for the trip to map scores back to people. Two sub-options, decision in §8:
- **(a)** Backend extends the trip-detail payload with a `party: { user: {id, label}, companions: [{id, name}] }` block (clean, requires new API contract).
- **(b)** Frontend reuses the existing companions list already fetched by `useCompanions()` plus the `whoami`-shaped user id. Cheaper but couples two endpoints.

Locked: **(a)**. `TripDetail` gains `party` so a shared report (which has no auth context) renders score labels correctly.

**`categorize.ts` rules:**

```ts
const USER_HIGH = 0.6;
const COMPANION_HIGH = 0.6;
const USER_LOW = 0.4;
const COMPANION_LOW = 0.4;

function userScore(item): number | null { ... }
function companionScores(item): number[] { ... }

// you only: user clearly wants it, no companion wants it.
// Requires at least one companion on the trip — otherwise the rule
// would shadow all of `together` into `you only` (S2).
function isUserOnly(item, hasCompanions): boolean {
  if (!hasCompanions) return false;
  const u = userScore(item);
  const cs = companionScores(item);
  if (u == null || cs.length === 0) return false;
  return u > USER_HIGH && cs.every((c) => c < COMPANION_LOW);
}

// them only: every companion clearly wants it, user doesn't.
function isPartnerOnly(item, hasCompanions): boolean {
  if (!hasCompanions) return false;
  const u = userScore(item);
  const cs = companionScores(item);
  if (u == null || cs.length === 0) return false;
  return cs.every((c) => c > COMPANION_HIGH) && u < USER_LOW;
}
```

`categorize()` signature gains a `party` arg so the partition function can pull the user_id + companion_id set. `together`, `disagreement`, `local_gems`, `tourist_traps` are untouched.

**`TAB_EMPTY_COPY` update:**

```ts
user_only: "no you-only picks in this reading.",
partner_only: "no them-only picks in this reading.",
```

(Drops the "coming once per-person tastes are wired in" sentinel — the feature ships in this batch.)

**`ItemCard` — expanded view score row.**

Insert a new `<p>` immediately below the existing "where it came up" block and above "why" (rationale). Shown only when `match_scores` is non-null and the trip has at least one companion (otherwise the row carries no signal).

Exact copy (scrapbook voice, lowercase, no exclamation):

- Prefix label: `match` (rendered with the existing `.type` class, like `sources` / `why`)
- Score format per person: `<label>: <score>` where label is `you` for the user and the companion's name lowercased; score is rounded to one decimal place (`0.83` → `0.8`, `0.5` → `0.5`).
- Joiner between people: ` · ` (middot, matches existing `areaStyleLine`).

Example: `match  you: 0.8 · alice: 0.3 · bob: 0.6`

If `match_scores` is null, the row is not rendered. If a person on the party isn't in the map (shouldn't happen — backend fills missing with 0.5), they are omitted from the row.

### 4.3 Files modified

| Path | Change |
|------|--------|
| `backend/src/plus_one/prompts/joiner/v3.md` | **new** — v2 + scoring section + `{person_roster}` placeholder |
| `backend/src/plus_one/agents/joiner.py` | `JoinedItem.match_scores` field; switch `load_prompt("joiner", "v3")`; render `{person_roster}`; post-parse validation |
| `backend/src/plus_one/agents/_scoring.py` | **new** — `render_person_roster`, key-validation helper |
| `backend/src/plus_one/core/agents/framework/types.py` | `UserProfileForContext.id: UUID`; `CompanionForContext.id: UUID` |
| `backend/src/plus_one/services/trip_runner.py` | populate new `id` field in `_load_profile_context`; add `party` block to trip-detail response |
| `backend/src/plus_one/api/trips.py` | extend trip-detail / shared-trip response with `party` |
| `backend/tests/unit/agents/test_joiner.py` | extend fixture; new test for score range + key validation |
| `backend/tests/unit/agents/test_scoring.py` | **new** — `render_person_roster` unit test |
| `backend/tests/integration/test_trips_*.py` | assert `party` shape in trip-detail response |
| `frontend/lib/schemas/trips.ts` | `JoinedItemView.match_scores`; `TripDetail.party` |
| `frontend/lib/trips/categorize.ts` | new score-based rules; `TAB_EMPTY_COPY` strings; signature accepts `party` |
| `frontend/lib/trips/categorize.test.ts` | new score-routing cases (S1, S2, S3) |
| `frontend/components/trips/ItemCard.tsx` | new expanded score row |
| `frontend/components/trips/ItemCard.test.tsx` | score row render test |
| `frontend/app/app/trips/[id]/page.tsx` | thread `party` into `categorize()` + `ItemCard` |

### 4.4 New files

- `backend/src/plus_one/prompts/joiner/v3.md` — prompt v3 (scoped scoring rules).
- `backend/src/plus_one/agents/_scoring.py` — pure helper module:
  - `render_person_roster(profile, companions) -> str` (UUID-keyed roster block).
  - `validate_match_scores(scores, allowed_ids) -> dict[UUID, float] | None` (drops unknown keys, fills missing with 0.5, clamps to [0, 1], coerces empty→None).
- `backend/tests/unit/agents/test_scoring.py` — unit tests for the helper.

### 4.5 Concurrent-batch warning

This batch overlaps two in-flight batches and must sequence carefully:

- **batch-2q (TL;DR)** touches the joiner prompt **and** the `TripContent` schema (adds a top-level `tldr` field). Both batches edit `prompts/joiner/v3.md`-adjacent files and `frontend/lib/schemas/trips.ts`. **Sequence rule:** whichever lands second must rebase, re-version the prompt (`v4.md` if 2p lands first and 2q is forced to bump), and re-run the eval suite. Don't try to merge 2p+2q prompts in one shot — keeps eval deltas attributable.
- **batch-2r (perspective wiring)** slices items by language perspective and edits `categorize.ts`. If 2r ships first, 2p's `categorize.ts` rebase must preserve 2r's perspective filter (apply it before score-based bucketing). If 2p ships first, 2r owns the perspective composition.

**Recommended order:** 2p → 2q → 2r. 2p's prompt change is the bigger eval risk; getting it baselined first means 2q's TL;DR change rides on a stable scoring baseline.

---

## 5. Data shapes

Full `JoinedItem.match_scores` example with 1 user (`u-...`) + 2 companions (`c-alice`, `c-bob`):

```json
{
  "candidate": {
    "name": "Tsukiji Outer Market — Yamachan",
    "area": "Tsukiji",
    "style": "fresh seafood / breakfast bowls",
    "rationale": "high reddit + xhs co-mention, locals call it the still-real corner"
  },
  "classification": "local_gem",
  "classification_en": "local_gem",
  "classification_zh": "local_gem",
  "confidence": 0.82,
  "divergence_score": 0.0,
  "evidence": [
    { "source": "reddit", "url": "https://reddit.com/r/JapanTravel/...", "snippet": "...", "sentiment": 0.8 },
    { "source": "xiaohongshu", "url": "https://xhs/...", "snippet": "...", "sentiment": 0.7 }
  ],
  "summary": "real-feeling tsukiji corner; seafood-heavy menu",
  "match_scores": {
    "u-7c1a4d0b-3e9b-4f1a-9c2d-1f5e8b2a0001": 0.10,
    "c-alice-aaaa-aaaa-aaaa-aaaaaaaaaaaa": 0.90,
    "c-bob-bbbb-bbbb-bbbb-bbbbbbbbbbbb": 0.50
  }
}
```

Routing for the example above (assuming user_id = `u-...`, hasCompanions = true):
- `user_score = 0.10` (< 0.4 ✓ for `partner_only`)
- `every companion_score > 0.6`? alice 0.90 ✓, bob 0.50 ✗ — **fails**, so this item lands in `together` only, not in `partner_only`. Both companions must clear the high bar for `them only`.

If bob's score were `0.70` instead, the item would route to `together` + `partner_only`.

Null-case example (generic / no preference dimension applies):

```json
"match_scores": null
```

Old-report example (pre-2p):

```json
// match_scores field simply absent from the JSON
```

Both are routed identically by `categorize.ts`: the item lands in `together` (and `local_gems` / `tourist_traps` / `disagreement` if applicable), but is invisible to the score-gated tabs.

---

## 6. Testing

### Backend — pytest

- **Unit, `test_scoring.py`:**
  - `render_person_roster` with: empty profile + 0 companions → `"- person_id=<user_id> name=you loves=[] hates=[]"` (still emit the line so the LLM never sees an empty roster).
  - 1 user + 2 companions with loves/hates → exact-string snapshot.
  - `validate_match_scores`: unknown keys dropped; missing keys filled with 0.5; values outside [0, 1] clamped; empty result → `None`.
- **Unit, `test_joiner.py`:**
  - Prompt v3 loads without `KeyError` (no stray unbalanced braces).
  - Mock LLM returns `match_scores` with correct keys → joiner passes through unchanged.
  - Mock LLM returns unknown UUID → dropped; assert it's not in the output.
  - Mock LLM omits a person → filled with 0.5.
  - Mock LLM returns out-of-range score (1.7) → clamped to 1.0.
- **Integration, `test_trips_*.py`:**
  - Trip-detail response includes `party: {user: {id, label}, companions: [...]}`.
  - Shared-trip response also includes `party` (anonymized labels OK; ids remain).

### Frontend — vitest

- `categorize.test.ts`:
  - S1 (couple, divergent taste): item routes to `together` + `partner_only`.
  - S2 (solo): `match_scores = {user: 0.9}`, no companions → routes to `together` only.
  - S3 (old report, `match_scores` undefined): routes to `together` only.
  - Edge: `match_scores = null` → same as undefined.
  - Edge: tie at threshold (user_score = 0.6 exactly) → does not route to `you only` (rule is `> 0.6`, strict).

### Frontend — RTL

- `ItemCard.test.tsx`:
  - Expanded view with `match_scores = {user: 0.83, alice: 0.30}`, party has user + alice → row shows `match you: 0.8 · alice: 0.3` exactly.
  - Expanded view with `match_scores = null` → row not rendered.
  - Collapsed view with `match_scores` populated → row not rendered (expanded only).
  - Party has no companions → row not rendered (no signal worth showing).
  - Lowercase + scrapbook voice assertion (no uppercase, no exclamation).

---

## 7. Rollout

- **Prompt versioning (PRD §9):** `prompts/joiner/v3.md` is a new file; `v2.md` stays in the repo until the next prompt batch (v4) lands, to support quick A/B rollback via env var if eval delta regresses.
- **Eval delta required (PRD §9):** the LLM eval suite must be re-run against v3 before merge. Required deltas to report in the PR:
  - F1 on the 60-place ground truth (target: no regression vs. v2; the scoring section adds load but should not move classification accuracy by more than 2 absolute F1 points).
  - New eval: per-person score sanity — a held-out fixture set with hand-labeled "obvious" matches (e.g. seafood-hater + sushi place → score ≤ 0.3) must score correctly on ≥ 80% of cases.
  - Per-report cost: budget +15% tokens; verify in eval log.
- **Migration safety:** no DB migration. `match_scores` lives only in the JSON `TripContent` blob. Old report rows continue to parse — the field is simply absent.
- **Frontend behavior for old reports:** `you only` / `them only` tabs stay empty (current state). `TAB_EMPTY_COPY` is updated to the post-deploy wording — old reports will read "no you-only picks in this reading" instead of "coming once per-person tastes are wired in". That's the intended state: the feature shipped, this particular report just doesn't have score data.
- **Demo fixtures:** update `backend/tests/fixtures/joiner_demo_*.json` (if any) to include `match_scores` so demo-mode shows the populated tabs.

---

## 8. Open Questions

1. **`party` on the public shared-trip endpoint:** should companion `name` be included, or anonymized as `companion 1` / `companion 2`? PRD §5 strips `user_id` and other PII from shared payloads. Companion names are user-set strings that could be PII ("mom", real names). Default: anonymize to `friend 1`, `friend 2`, ... in the shared response; keep real names in the authenticated trip-detail response. Confirm with PRD review.
2. **Threshold values (`0.6` / `0.4`):** held to PRD-locked numbers. After dogfooding, if `you only` / `them only` end up consistently empty even on couples with strong divergence, we may need to widen (e.g. `0.55` / `0.45`). Track with a frontend telemetry counter "tab_render: you_only_size", "tab_render: partner_only_size" — out of scope here, file as follow-up.
3. **Score row position in the expanded card:** placed between "where it came up" and "why" in this PRD. Alternative: directly under the verdict pill so it's the first thing in the expanded body. Defer to design review.
4. **Label for the user in the score row:** `you` (chosen, per spec). Alternatives considered: profile display name, `me`. `you` reads more naturally in scrapbook voice and avoids needing display-name plumbing on the public shared endpoint.
5. **Multi-companion handling for `them only`:** the rule requires *every* companion to clear `0.6`. Strict by design — we don't want a 3-companion trip where one strong fan drowns out two who'd hate the place. Confirm this matches product intent before merging.
6. **Concurrent-batch ordering with 2q (TL;DR):** if 2q lands first and also bumps the joiner prompt to `v3.md`, 2p must rebase to `v4.md`. Coordinate in #plus-one-batches before opening PR.

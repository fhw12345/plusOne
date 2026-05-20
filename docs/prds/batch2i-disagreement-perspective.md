# Batch 2i — Disagreement detection + perspective toggle

> Status: PRD-Agent reviewed against code (2026-05-20).
> Depends on: Batch 2g PR A (ReportView Tabs shell). Code Agent is blocked
> until 2g PR A merges to `main`. See §10 for the exact coupling points.

## 1. Context

PRD `docs/prd.md` §4 names this product's **core differentiation**:

> Surfaces where Chinese sources vs English sources diverge — with receipts.

Today, the Joiner produces one `Classification` per `Candidate` by reading
all sources together in a single LLM call (`backend/src/plus_one/agents/joiner.py:115-177`).
There is no per-language reasoning, no divergence detection, no disagreement
surface in the UI.

Existing domain shape:

- `Classification = Literal["local_gem", "tourist_trap", "neutral", "insufficient"]`
  — `backend/src/plus_one/agents/types.py:18`
- `Evidence.source ∈ {"reddit", "xiaohongshu", "google_places"}` —
  `backend/src/plus_one/agents/types.py:26`. Source is the only language
  signal we have for v1; we treat `xiaohongshu` as Chinese, `reddit` as
  English, and `google_places` as neutral metadata (it has no language flavor).
- `JoinedItem` is defined in `joiner.py:32-41` (not `types.py` — the draft's
  §5 was wrong about this; see §6 below).
- Report payload is persisted at `trip_runner.py:164` as
  `{"items": [i.model_dump(mode="json") for i in items]}` into a JSONB column
  (`content`), so new optional fields ride along with no DDL change.

ReportView (after Batch 2g PR A) will render Tabs including a
`⚠️ Disagreement` tab whose body is the items list filtered to
`disagreement === true` — a field that doesn't exist yet. This PR makes it
exist end-to-end.

## 2. Goals

- Per-language sub-classification (`classification_en`, `classification_zh`)
  on each `JoinedItem` when source coverage supports it.
- Compute a `divergence_score: float ∈ [0,1]` heuristic on each item,
  deterministically and without an additional LLM call.
- Derive `disagreement: bool` at read time (no persisted column) from the
  rule:
  `divergence_score >= 0.5 AND classification_en is not None AND
   classification_zh is not None AND classification_en != classification_zh`.
- Frontend perspective toggle: `[中文社区] [English community] [Fused (default)]`,
  view-side filter only — never re-runs the cycle.
- Populate the `⚠️ Disagreement` tab with items where `disagreement === true`,
  regardless of the toggle setting.

## 3. Non-goals

- Output language toggle (translation of report text into 中/英) — Batch 2k.
- Re-running the cycle when toggle changes. Toggle is a pure view filter.
- Cross-language semantic alignment beyond the source-as-language-proxy
  approximation. No LLM translation step inside the Joiner.
- A free-text "why they disagree" summary per item — v2 stretch.
- LLM-based per-evidence language detection — v2 (see §9).

## 4. Approach

### 4.1 Joiner output shape (extend, don't fork)

Extend `JoinedItem` **in place** at `joiner.py:32-41`:

```python
class JoinedItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidate: Candidate
    classification: Classification                         # unchanged: fused
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[Evidence, ...] = Field(default=())
    summary: str = Field(default="", max_length=500)
    # NEW (all optional, all defaulted — backward compatible):
    classification_en: Classification | None = None
    classification_zh: Classification | None = None
    divergence_score: float = Field(default=0.0, ge=0.0, le=1.0)
```

**Decision: extend, do NOT introduce `JoinedItemV2` + adapter.** Justification:

- The class is `frozen=True` but additive optional fields with defaults
  don't break any existing constructor call (every existing test in
  `test_domain_agents.py:80-199` constructs without these fields and will
  keep passing). Verified against `_joined()` helper at line 205.
- The model is serialized to JSONB via `model_dump(mode="json")`
  (`trip_runner.py:164`); extra keys are transparent on both write and
  read for JSONB columns — no DB migration needed.
- The class is imported in exactly four places: `trip_runner.py`,
  `controller.py` (read-only), `test_domain_agents.py`, and joiner itself.
  Type checking stays green.
- `JoinedItemV2 + from_v1` would double the surface area, double the
  serialization paths, and force a parallel maintenance burden for
  zero benefit — there's no consumer that needs the strict V1 shape.

### 4.2 Joiner LLM strategy: ONE call, extended schema

The draft PRD said "second LLM call (or extension) — pick later." Pick **now,
in the PRD**: extend the existing call's response schema. Reasoning:

- The existing prompt (`backend/src/plus_one/prompts/joiner/v1.md`, 58 lines)
  and existing user payload already contain the per-source hits (Reddit /
  XHS / Google Places) labelled by source (`joiner.py:130-140`). The LLM
  already has everything it needs to produce per-language verdicts in the
  same turn; nothing new needs to be fetched or re-uploaded.
- The output schema (`_JoinerOutput` at `joiner.py:44-45`) is the only
  thing forcing the LLM to emit just the fused classification. Add two
  optional fields to each item and one short paragraph to the prompt; the
  LLM produces 3 verdicts per item instead of 1.
- **Token cost**: the per-item output goes from ~40 tokens (one `classification`
  + `confidence` + `summary`) to ~50 tokens (two extra enum values). Input
  tokens are unchanged. With our cap of 30 items, output delta is bounded
  at ~300 tokens / cycle — well under a 5% increase on a typical 6-10k
  output, and ~0% input increase. A second LLM call would re-send the full
  evidence payload (~4-8k tokens) — strictly worse.
- One round trip preserves the existing latency profile.

**Prompt change** (`backend/src/plus_one/prompts/joiner/v2.md`, new file):

- Copy `v1.md` verbatim.
- Add a section instructing per-language classification from source subsets:
  *Use only `[reddit]`-labelled hits for `classification_en`; use only
  `[xiaohongshu]`-labelled hits for `classification_zh`. If a language has
  zero hits or only `insufficient`-quality hits for that candidate, return
  `null` for that field. Google Places is language-neutral and should
  inform the fused `classification` only.*
- Update the JSON schema example to include the two new fields and
  document `null` as the "no evidence on this side" sentinel.
- Bump `load_prompt("joiner", "v1")` → `"v2"` at `joiner.py:128`. Keep
  `v1.md` in tree (cheap, lets us A/B compare per ADR's "version flip"
  pattern at `prompts.py:1-7`).

**Computed in Python, not LLM**: `divergence_score` is a pure function of
`(classification_en, classification_zh)`. Keeping it out of the LLM output
removes a class of hallucinations and lets us unit-test the threshold
exhaustively. See §4.3.

### 4.3 `divergence_score` formula and threshold

New module: `backend/src/plus_one/agents/_divergence.py`:

```python
DISAGREEMENT_THRESHOLD: Final = 0.5

_STRONG: frozenset[Classification] = frozenset({"local_gem", "tourist_trap"})

def divergence_score(en: Classification | None, zh: Classification | None) -> float:
    """Pure function. Both-None → 0.0. Either-None → 0.0 (not a candidate)."""
    if en is None or zh is None:
        return 0.0
    if en == zh:
        return 0.0
    pair = frozenset({en, zh})
    # Direct contradiction: gem vs trap.
    if pair == _STRONG:
        return 1.0
    # One side is strong, other side admits no evidence: asymmetric coverage.
    if "insufficient" in pair and (pair - {"insufficient"}) & _STRONG:
        return 0.6
    # Strong vs neutral: meaningful disagreement.
    if "neutral" in pair and pair & _STRONG:
        return 0.5
    # Insufficient vs neutral: weakest signal that still differs.
    return 0.3
```

Threshold rationale:

- `0.5` is the cut-off because it cleanly includes "strong vs neutral"
  (0.5) and "direct contradiction" (1.0), and excludes "weak/weak" noise
  (0.3). This matches the product intent: surface places where one
  community vouches and the other doesn't, plus head-to-head conflicts.
- The `0.6` asymmetric-coverage rule (gem on one side, no usable evidence
  on the other) also surfaces — these are the "Reddit has never heard of
  this but xhs raves" cases, which are exactly the cross-cultural finds
  the product wants to spotlight.

Truth-table (drives the unit test in §4.6):

| en              | zh              | score | disagreement? |
|---|---|---|---|
| `local_gem`     | `local_gem`     | 0.0   | no |
| `tourist_trap`  | `tourist_trap`  | 0.0   | no |
| `neutral`       | `neutral`       | 0.0   | no |
| `insufficient`  | `insufficient`  | 0.0   | no |
| `local_gem`     | `tourist_trap`  | 1.0   | **yes** |
| `tourist_trap`  | `local_gem`     | 1.0   | **yes** |
| `local_gem`     | `insufficient`  | 0.6   | **yes** |
| `insufficient`  | `tourist_trap`  | 0.6   | **yes** |
| `local_gem`     | `neutral`       | 0.5   | **yes** |
| `tourist_trap`  | `neutral`       | 0.5   | **yes** |
| `neutral`       | `insufficient`  | 0.3   | no |
| `None`          | `local_gem`     | 0.0   | no (gate fails) |
| `local_gem`     | `None`          | 0.0   | no (gate fails) |
| `None`          | `None`          | 0.0   | no |

The `disagreement` derivation gate (`en is not None AND zh is not None AND
en != zh AND score >= 0.5`) lives on the API/frontend side, not in the
score function. Document the threshold constant; export it from
`_divergence.py` and reuse on both Python (for backend tests) and TS
(mirror as a constant in the frontend).

### 4.4 Where `divergence_score` is computed

In `joiner.py`, after the `repaired` list is built (around line 168), map
each item through:

```python
from plus_one.agents._divergence import divergence_score

final: list[JoinedItem] = []
for item in repaired:
    score = divergence_score(item.classification_en, item.classification_zh)
    if score != item.divergence_score:
        item = item.model_copy(update={"divergence_score": score})
    final.append(item)
return PhaseResult(payload=final, ...)
```

The LLM never returns `divergence_score` (we strip / overwrite it). This
gives us a single source of truth for the score and keeps prompt drift
from changing thresholds.

### 4.5 Backend API & persistence

No endpoint change. `trip_runner._save_report` (line 148-177) already
serializes via `model_dump(mode="json")` into JSONB; the new optional
fields ride along automatically. No migration, no Alembic revision.

`disagreement` is **not persisted**. We compute it client-side from the
three fields. If we ever want server-side filtering we'll add a derived
field to the API response — out of scope for v1.

### 4.6 Tests

**New: `backend/tests/unit/agents/test_divergence.py`**

```python
import pytest
from plus_one.agents._divergence import divergence_score, DISAGREEMENT_THRESHOLD

@pytest.mark.parametrize("en,zh,expected", [
    ("local_gem", "local_gem", 0.0),
    ("tourist_trap", "tourist_trap", 0.0),
    ("neutral", "neutral", 0.0),
    ("insufficient", "insufficient", 0.0),
    ("local_gem", "tourist_trap", 1.0),
    ("tourist_trap", "local_gem", 1.0),
    ("local_gem", "insufficient", 0.6),
    ("insufficient", "tourist_trap", 0.6),
    ("local_gem", "neutral", 0.5),
    ("tourist_trap", "neutral", 0.5),
    ("neutral", "insufficient", 0.3),
    (None, "local_gem", 0.0),
    ("local_gem", None, 0.0),
    (None, None, 0.0),
])
def test_divergence_score_truth_table(en, zh, expected): ...

def test_threshold_is_documented_constant():
    assert DISAGREEMENT_THRESHOLD == 0.5
```

**Modify: `backend/tests/unit/agents/test_domain_agents.py`**

- Extend `test_joiner_classifies_candidates` (line 80): the mock LLM
  payload at line 82-99 already returns `parsed_data`. Add
  `classification_en: "local_gem"`, `classification_zh: "local_gem"` to
  it and assert `item.divergence_score == 0.0`. This proves end-to-end
  that the new fields pass through `_JoinerOutput` validation and the
  Python-side `divergence_score` overwrite fires.
- Add **new** `test_joiner_computes_divergence_for_disagreement_case`:
  queue a mock LLM response where one item has `classification_en="local_gem"`
  and `classification_zh="tourist_trap"`, then assert
  `item.divergence_score == 1.0` (regardless of what the LLM emitted for
  that field).
- Add **new** `test_joiner_handles_null_per_language_classification`:
  mock returns `classification_en="local_gem", classification_zh=None`;
  assert `divergence_score == 0.0` and `classification_zh is None`.

The mock LLM fixture (`backend/src/plus_one/core/llm/testing.py:101-144`)
already routes responses by role via `_RoleBoundMock`, so the existing
`mock_llm.queue_response(role="joiner_agent", parsed_data=…)` pattern
is all we need — no fixture changes.

**Frontend**:

- `frontend/store/reportPrefs.test.ts` (new): assert default `perspective === "fused"`, setter works, persistence round-trips through the mocked
  `localStorage` exactly like `store/auth.test.ts` does.
- `frontend/components/trips/PerspectiveToggle.test.tsx` (new): renders 3
  buttons, ARIA `role="radiogroup"`, clicking each updates store.
- `frontend/components/trips/ReportView.test.tsx` (modify): three new cases
  — fused-default shows all items; "中文社区" hides items where
  `classification_zh == null`; disagreement tab populates only items with
  `divergence_score >= 0.5 && classifications differ && both non-null`.
- `frontend/e2e/trip-flow.spec.ts`: extend the existing aborted-trip
  fallback spec to assert the perspective toggle and the disagreement
  tab are rendered (the tab will be empty since the fixture trip aborts
  before producing items — that's fine; we're just asserting non-crash
  rendering). Do NOT add a `trip-flow-with-fixture.spec.ts`; seeding
  reports via direct DB writes is out of scope for this PR (defer to a
  future test-infrastructure batch).

### 4.7 Frontend implementation

**Schema** (`frontend/lib/schemas/trips.ts:23`): replace the open
`z.object({}).passthrough()` with a typed schema that keeps `passthrough`
so future fields still ride along but gives us autocomplete on the three
new fields:

```ts
const ClassificationEnum = z.enum(["local_gem", "tourist_trap", "neutral", "insufficient"]);

export const JoinedItemSchema = z
  .object({
    candidate: z.object({ name: z.string() }).passthrough(),
    classification: ClassificationEnum,
    confidence: z.number().min(0).max(1),
    summary: z.string().optional().default(""),
    classification_en: ClassificationEnum.nullish(),
    classification_zh: ClassificationEnum.nullish(),
    divergence_score: z.number().min(0).max(1).optional().default(0),
  })
  .passthrough();
```

Caveat: Batch 2g PR A has not landed in this branch yet — `trips.ts:23`
is still the loose passthrough. If 2g PR A redefines `JoinedItemSchema`
differently, this PR rebases on top and the schema diff is small (just
adding the three new fields). See §10.

**Helper** (new, `frontend/lib/trips/disagreement.ts`):

```ts
export const DISAGREEMENT_THRESHOLD = 0.5; // mirror of backend constant
export function isDisagreement(item: JoinedItem): boolean {
  return (
    item.classification_en != null &&
    item.classification_zh != null &&
    item.classification_en !== item.classification_zh &&
    (item.divergence_score ?? 0) >= DISAGREEMENT_THRESHOLD
  );
}
```

**Store** (new, `frontend/store/reportPrefs.ts`): tiny Zustand slice
mirroring the structure of `frontend/store/auth.ts:23-47` — `persist`
with `skipHydration: true`, default `perspective: "fused"`. Single
exported `useReportPrefsStore`.

**Components**:

- `PerspectiveToggle.tsx` (new): three-button segmented control, ARIA
  `role="radiogroup"`, reads/writes `useReportPrefsStore`. Render labels
  `中文社区`, `English community`, `Fused`. Show `useHasHydrated()`-style
  skeleton until store rehydrates (same pattern as auth gating).
- `ReportView.tsx` (rewrite atop 2g PR A): place `<PerspectiveToggle />`
  above the Tabs. Compute `displayed = items.filter(...)` per toggle
  state; Disagreement tab filter is independent of toggle. Memoize the
  filter on `(items, perspective)`.

### 4.8 Migration & backward-compat

- **Old reports lack the new fields.** Frontend treats `undefined ===
  null === "no data"`; the disagreement gate fails closed (no false
  disagreements). Fused tab works unchanged. "中文社区" / "English
  community" filters will hide all old-report items (because both per-lang
  fields are missing) — show an inline note: *"This report was produced
  before per-language classification; switch to Fused to see results."*
- **No DB migration**. JSONB column accepts new keys silently.
- **No prompt rollback risk**: keep `joiner/v1.md` in tree; revert is
  one-line at `joiner.py:128`.

## 5. Files to change

| File | Action | Why |
|---|---|---|
| `backend/src/plus_one/agents/joiner.py` | modify | `JoinedItem` gains 3 optional fields; bump prompt to v2; post-process to compute `divergence_score` deterministically |
| `backend/src/plus_one/agents/_divergence.py` | new | Pure scoring fn + `DISAGREEMENT_THRESHOLD` constant |
| `backend/src/plus_one/prompts/joiner/v2.md` | new | Adds per-language classification instructions + updates the example JSON schema |
| `backend/src/plus_one/prompts/joiner/v1.md` | keep | Preserved for A/B + cheap rollback |
| `backend/tests/unit/agents/test_divergence.py` | new | Truth-table parametrize |
| `backend/tests/unit/agents/test_domain_agents.py` | modify | Extend existing joiner test; add 2 new joiner tests |
| `frontend/lib/schemas/trips.ts` | modify | Tighten `JoinedItemSchema` with new optional fields (still `.passthrough()`) |
| `frontend/lib/trips/disagreement.ts` | new | `isDisagreement` helper + threshold constant mirror |
| `frontend/store/reportPrefs.ts` | new | Zustand persisted slice for `perspective` |
| `frontend/store/reportPrefs.test.ts` | new | Default/setter/persistence round-trip |
| `frontend/components/trips/PerspectiveToggle.tsx` | new | Segmented control UI |
| `frontend/components/trips/PerspectiveToggle.test.tsx` | new | Renders, clicks update store, ARIA |
| `frontend/components/trips/ReportView.tsx` | modify | Mount toggle; per-tab filtering; disagreement tab |
| `frontend/components/trips/ReportView.test.tsx` | modify | 3 new cases (fused / per-lang / disagreement filter) |
| `frontend/components/trips/ItemCard.tsx` | new-or-extract | Optional: extract a card with per-lang badge row. If 2g PR A introduces ItemCard, just extend; if not, scope minimally inline in ReportView and defer extraction |
| `frontend/e2e/trip-flow.spec.ts` | modify | Assert toggle + disagreement-tab renders without crash |

**Files explicitly NOT touched** (verified):

- `backend/src/plus_one/agents/types.py` — `JoinedItem` lives in `joiner.py`,
  not here. The draft's §5 entry was incorrect.
- `backend/src/plus_one/services/trip_runner.py` — JSONB serialization is
  transparent to new optional fields; `_save_report` at line 148-177 stays
  untouched.
- `backend/src/plus_one/agents/controller.py` — only reads
  `item.classification` (the fused one); doesn't need per-language. No
  change.
- Database migrations — none. JSONB content column already permissive.

## 6. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| LLM ignores prompt instruction and returns `classification_en/zh` for items with no evidence on that side | Medium | Optional `None` in schema; UI gate requires both non-null; doc the expectation in prompt with an explicit example. |
| LLM hallucinates per-language verdicts that contradict the fused `classification` | Low-Medium | Acceptable — fused stays the canonical "single answer". The disagreement signal is by construction a divergence between the two per-lang verdicts, not vs fused. Add a debug log in `joiner.py` when fused ∉ {en, zh} so we can monitor. |
| Token-output budget bloat at the 30-item cap | Low | Bounded ~300-tok delta; well under existing 6-10k output envelope. Monitor via existing `notes` token-totals already plumbed (`trip_runner.py:198-209`). |
| Source-as-language proxy is wrong (Reddit thread in Chinese, etc.) | Medium long-term, Low for Tokyo v1 corpus | Document in `_divergence.py` docstring; flag for v2 LLM language detection (§9). |
| Batch 2g PR A merges with a different `JoinedItemSchema` shape | Medium | Schema diff is mechanical (add 3 fields). Code Agent rebases when 2g PR A lands. See §10. |
| Old reports show empty per-lang tabs and confuse users | Low | Inline notice rendered when active perspective filter would hide all items because per-lang fields are uniformly absent. |
| `frozen=True` + `model_copy(update=...)` allocates extra objects | Negligible | Existing pattern; already used at `joiner.py:166`. |

## 7. Acceptance criteria

- `ruff check` and `mypy` clean on the backend diff.
- `pytest backend/tests` green; coverage stays ≥ 84%.
- `pnpm test` (vitest) green; new tests included.
- `pnpm exec playwright test` 11/11 pre-existing green + 1 new assertion
  block in `trip-flow.spec.ts` for toggle/disagreement-tab presence.
- Manual sanity check (recorded in PR description): trigger a mocked
  cycle in dev where the queued joiner response includes one
  `local_gem` / `tourist_trap` mismatched item; verify the Disagreement
  tab badge count is `1`, the item card shows both verdicts side-by-side,
  and the toggle filters items correctly across all three states.
- `joiner/v2.md` exists; `joiner.py` calls `load_prompt("joiner", "v2")`.

## 8. Out of scope (defer)

- LLM-based language detection per evidence item (replaces source-as-proxy).
- Free-text "Why they disagree" per-item summary (would need either a 2nd
  LLM call or much wider prompt — defer to v2 after we have UX data).
- Cross-trip aggregate disagreement patterns ("places where 中文/English
  always disagree" leaderboard).
- Server-side filtering / pagination by `disagreement` flag — items list
  is bounded at 30 so client-side filter is fine.
- Output-language translation of report text (Batch 2k).
- Backfill of per-language fields onto old reports — old reports remain
  fused-only (acceptable per §4.8 migration notes).

## 9. Open questions

(None blocking. Both are doc-only.)

- **Q1**: Should `divergence_score` be plumbed through the SSE event
  payload (currently `joiner` event at `trip_runner.py:230-240` reports
  only count + notes)? Default answer: no, it's only meaningful per-item
  and the UI reads from the final report. Flag if PM disagrees.
- **Q2**: Localize the toggle labels? Current spec hard-codes `中文社区` /
  `English community` / `Fused`. Consistent with PRD §4 wording. Defer
  any i18n until Batch 2k.

## 10. Dependency on Batch 2g PR A

This PR is **blocked** on Batch 2g PR A merging because:

1. `ReportView.tsx` is currently a stub (`frontend/components/trips/ReportView.tsx:1-37`,
   verified) — it renders a flat `<ul>` with no Tabs. 2g PR A introduces
   the Tabs shell + ItemCard component. This PR rewrites `ReportView`
   atop that shell.
2. `JoinedItemSchema` is currently the open passthrough
   (`frontend/lib/schemas/trips.ts:23`). 2g PR A is planned to tighten
   it; this PR adds three more fields on top.

If 2g PR A is delayed, Code Agent should:

- Either rebase onto the 2g PR A branch and proceed,
- Or land the backend half (Joiner + divergence + tests) as a *separate
  commit on this PR's branch* but not open the PR until the frontend
  half is also ready — we keep this as one PR per the brief, not two.

Backend half is self-contained and testable independent of 2g PR A.

# PRD: batch-2q — Report TL;DR

**Author:** fhw12345
**Date:** 2026-05-22
**Status:** Draft

---

## 1. Problem (top-of-report headline missing; users land on a tab-heavy report with no orientation)

The current report (`frontend/components/trips/ReportView.tsx`) opens with a heading
("the reading"), a one-line scrawl subtitle ("each card has a source…"), then drops
the user straight into perspective/language toggles and `ReportTabs`. There is no
top-of-report synthesis — no answer to *"so what did you find out about this place?"*
The user has to scan tabs and expand cards to construct the headline themselves.

The master PRD (`docs/prd.md` §4 *Output → Layout: Top TL;DR → Tabs → Expandable cards*)
calls for a TL;DR block at the top of the report. Today's `TripContent` shape
(`frontend/lib/schemas/trips.ts:58-72`) carries only `{items, translations?}` — there
is no field for a top-line summary and the joiner (`prompts/joiner/v2.md`) doesn't
emit one. This batch closes that gap.

---

## 2. Goals / Non-Goals

### Goals

- Add `TripContent.tl_dr: str | None` (English by default; one paragraph, 2–4 sentences).
- Per-language `translations[lang].tl_dr` so the language toggle swaps the TL;DR too.
- Joiner generates the TL;DR in the same call that emits items (no new agent step).
- Render TL;DR at the **top** of `ReportView`, **above** perspective/language toggles,
  styled consistently with the scrapbook reskin (paper-2 sticky note + tape accent).
- Scrapbook voice: lowercase, plain language, no exclamation marks, comma-spliced flow.
- Old reports without `tl_dr` (pre-2q): **omit** the section entirely. No fallback copy.

### Non-Goals

- No multiple TL;DR variants (no "for couples" vs "for solo").
- No per-perspective TL;DR — one TL;DR per report, identical across perspective toggle states.
  (Perspective filters items only — see batch-2r.)
- No user-editable TL;DR.
- No streaming / partial TL;DR over SSE — it lands with the final report write.
- No regenerate-TL;DR button.
- No TL;DR for shared / public report endpoint differences — the shared endpoint already
  returns full `TripContent`, so TL;DR rides along for free.

---

## 3. User Scenarios

### S1 — New report with tl_dr (happy path)

User submits a trip for "kyoto, late november". Joiner v3 runs, emits 18 items
plus a `tl_dr` paragraph. `_save_report` persists `content = {items, tl_dr}`.
Translator runs and writes `translations.en.tl_dr` + `translations.zh.tl_dr`.
SSE `trip_complete` fires. Frontend loads the report; `ReportView` renders the
TL;DR sticky note at the top, then the toggles, then the tabs.

### S2 — Language switch updates tl_dr

User toggles language from `original` to `zh`. `resolveItems` already swaps the
items list; the same `language` value also selects
`content.translations.zh.tl_dr` (with fallback to `content.tl_dr` if translator
hadn't run for that language). The sticky note re-renders with the Chinese
TL;DR; the toggle position remains stable (TL;DR is above the toggles, so the
toggle button itself doesn't move).

### S3 — Old report without tl_dr renders without the section

User opens a report created before batch-2q rolled out. `content.tl_dr` is
`undefined`. `ReportView` renders **nothing** in the TL;DR slot — no heading, no
sticky note, no whitespace placeholder. The header ("the reading") sits at the
top, toggles below, tabs below that, exactly like today. No console warning, no
fallback copy.

---

## 4. Technical Design

### 4.1 Backend

**`TripContent` model gains `tl_dr`.** The `Report.content` JSONB column is
already schemaless on the SQLAlchemy side; the joiner output and `_save_report`
both build dicts. The change is purely additive at the dict shape level:

```python
# joiner output
{
  "items": [...],
  "tl_dr": "kyoto's still a place where good tea matters. ..."  # NEW
}
```

`_save_report` (`services/trip_runner.py:157`) currently writes
`content={"items": [...]}`. Update to include `tl_dr` when present:

```python
content: dict[str, Any] = {"items": [i.model_dump(mode="json") for i in items]}
if tl_dr is not None:
    content["tl_dr"] = tl_dr
```

This requires the joiner phase to return `tl_dr` alongside the items list — see
the prompt + return-shape change below.

**`translations[lang]` also gains `tl_dr`.** `_run_translations_and_update`
(`services/trip_runner.py:217-255`) currently builds
`translations: dict[str, list[dict]]` (lang → items list). The shape becomes
heterogeneous to keep both items and tl_dr per-language under one key:

```python
translations: dict[str, dict[str, Any]] = {}
# per lang:
translations[lang] = {
    "items": await translate_items(items, src_lang="original", dst_lang=lang),
    "tl_dr": await translate_tl_dr(tl_dr, src_lang="original", dst_lang=lang),
}
```

The frontend's `resolveItems` reads `content.translations?.[lang]?.items ?? content.items`.
(See §4.2 — this is a breaking shape change inside the translations subtree, but
nothing besides `ReportView` reads it.)

> **Note on translations shape compatibility.** Reports written between batch-2k and
> batch-2q have `translations[lang]: JoinedItem[]` (array). Reports written from
> batch-2q forward have `translations[lang]: {items, tl_dr}` (object). The frontend
> normalizes via `Array.isArray(translations[lang]) ? {items: translations[lang]} : translations[lang]`
> in the zod transform. No DB migration; the union holds.

**Joiner v3 prompt** (extends v2; see §4.4 — single prompt revision spanning 2p+2q):

Replace the output-format block in `prompts/joiner/v2.md` with v3 that adds a
`tl_dr` sibling field next to `items`. New prompt fragment:

> ## Top-of-report TL;DR
>
> After classifying every candidate, write one **TL;DR paragraph** describing
> the destination as the user should think about it. Place it under the `tl_dr`
> key alongside `items`.
>
> **Rules:**
> - 2–4 sentences, one paragraph, plain language.
> - Scrapbook voice: lowercase, no exclamation marks, no headings, no bullet
>   lists. Comma splices and short sentence fragments are encouraged.
> - Reference the city or area at most once by name; assume the reader knows
>   where they're going.
> - Call out what to skip and what to seek, briefly. Mention seasonality only
>   if the user query implies a date range.
> - Do NOT enumerate specific candidate names in the TL;DR — that's the cards'
>   job. Reference neighborhoods or styles instead ("nishijin", "counter
>   ramen", "old-town side").
> - Voice example: *"kyoto's still a place where good tea matters. anywhere
>   central tilts touristy fast, so ginkaku and arashiyama are skip — head to
>   nishijin or southern higashiyama for the actual neighborhoods. counters
>   over chains. november cool. allow an hour of walking between picks."*
>
> Write the TL;DR in English regardless of the user's chosen output language —
> the translator runs after you. Do NOT translate.

The output JSON example in the prompt becomes:

```json
{
  "tl_dr": "...",
  "items": [ ... ]
}
```

**Joiner return shape.** `_JoinerOutput` in `agents/joiner.py:56-57` adds a
field; `joiner()` returns the tl_dr alongside the items. Options:

- **Recommended:** widen `PhaseResult.payload` to a small tuple/namedtuple
  `JoinerPayload(items: list[JoinedItem], tl_dr: str | None)` and update the
  cycle main loop / `_save_report` callers to unpack. The Controller already
  only consumes `items`, so its signature is unchanged at the call site (pass
  `payload.items`).
- Alternative: stash `tl_dr` on `AgentContext.notes` or a side channel. Rejected
  as a hidden contract.

`tl_dr` is overwritten on every joiner round; the **final** round's tl_dr is
what gets persisted. (Earlier rounds run but their tl_dr is discarded — same
lifecycle as `summary` today.)

**Translator extension.** Add `translate_tl_dr(text, src, dst)` to
`agents/translator.py`. A one-shot LLM call (no per-item semaphore needed — it's
one string). Reuses `translator_agent` LLM role. On failure, returns the
original English string (same fail-soft pattern as `_translate_one`). New
prompt addendum in `prompts/translator/v1.md`:

> If the user message is a free-form paragraph (no JSON), translate it directly
> from {SRC_LANG} to {DST_LANG} preserving the scrapbook voice (lowercase,
> no exclamation, plain). Return only the translated paragraph, no quotes, no
> JSON wrapper.

Or simpler — add a sibling prompt `prompts/translator/tldr_v1.md` to avoid
overloading translator v1. Recommendation: **sibling prompt**, since the v1
prompt is structured around JoinedItem JSON I/O and overloading it muddies the
contract.

### 4.2 Frontend

**Zod schema.** `frontend/lib/schemas/trips.ts:58-72`:

```ts
const TripContentTranslation = z.union([
  z.array(JoinedItemSchema),  // legacy (batch-2k..2q boundary)
  z.object({
    items: z.array(JoinedItemSchema).optional(),
    tl_dr: z.string().optional().nullable(),
  }).passthrough(),
]).transform((v) => (Array.isArray(v) ? { items: v } : v));

export const TripContent = z.object({
  items: z.array(JoinedItemSchema),
  tl_dr: z.string().optional().nullable(),  // NEW
  translations: z.object({
    en: TripContentTranslation.optional(),
    zh: TripContentTranslation.optional(),
  }).partial().optional(),
});
```

Existing callers of `content.translations[lang]` (only `resolveItems` in
`ReportView`) update to `content.translations?.[lang]?.items`.

**`ReportView` renders TL;DR block above toggles.** Insert above the header
or just below it, above the toggles row. Recommended placement: above the
header so it's the **first thing** the user reads. The header ("the reading")
then frames the cards section below.

```tsx
function resolveTlDr(content: TripDetail["content"], language: ReportLanguage): string | null {
  if (!content) return null;
  if (language === "original") return content.tl_dr ?? null;
  return content.translations?.[language]?.tl_dr ?? content.tl_dr ?? null;
}

// inside ReportView, before the <header>:
{tlDr ? (
  <aside
    data-testid="report-tldr"
    style={{
      position: "relative",
      marginBottom: 18,
      padding: "22px 26px",
      background: "hsl(var(--paper-2))",
      border: "1px solid hsl(var(--kraft))",
      boxShadow: "0 10px 22px -14px hsl(0 0% 0% / .22)",
    }}
  >
    <span
      className="tape tape--peach"
      style={{ top: -10, right: 40, width: 90, height: 22, transform: "rotate(2deg)" }}
    />
    <p className="hand-lg" style={{ fontSize: 22, lineHeight: 1.45, margin: 0 }}>
      {tlDr}
    </p>
  </aside>
) : null}
```

**Voice / styling.**
- Font: `hand-lg` (same family as headlines, slightly smaller than `hand-xl`).
  Alternative: `scrawl` for a softer feel. Recommendation: `hand-lg` because
  the TL;DR is short and should read like a headline, not a margin note.
- Background: `paper-2` (matches the parent `ReportView` section — visually
  reads as a "card on top of the card").
- Tape accent: `tape--peach` rotated +2° on the right, contrasting the parent
  section's `tape--mint` on the left.
- No heading like "TL;DR" — the styling carries the meaning. Adding a label
  would break the scrapbook voice ("TL;DR" is uppercase abbreviation).

**Markdown export.** `frontend/lib/report/exportMarkdown.ts` prepends the
tl_dr as a single paragraph before the cards section, when present. (Detail
optional; do it if low-effort.)

**Print stylesheet.** TL;DR is visible in print (no `print:hidden`); toggles
are hidden. Print order: TL;DR → header → cards.

### 4.3 Files modified table

| File | Change |
|------|--------|
| `backend/src/plus_one/prompts/joiner/v2.md` → `v3.md` | New prompt file. Adds `tl_dr` to output JSON + the prompt fragment from §4.1. **Single revision spanning batch-2p + batch-2q — see §4.4.** |
| `backend/src/plus_one/agents/joiner.py` | `_JoinerOutput` adds `tl_dr: str | None`. `joiner()` returns both items and tl_dr (via small payload type or tuple). `load_prompt("joiner", "v3")`. |
| `backend/src/plus_one/agents/translator.py` | Add `translate_tl_dr(text, src, dst) -> str`. Fail-soft returns original on error. |
| `backend/src/plus_one/prompts/translator/tldr_v1.md` | NEW. One-paragraph translation prompt, scrapbook voice preserved. |
| `backend/src/plus_one/services/trip_runner.py` | `_save_report` writes `tl_dr` into content dict. `_run_translations_and_update` builds `translations[lang] = {items, tl_dr}` (object), not bare array. Cycle main loop unpacks joiner payload's tl_dr. |
| `frontend/lib/schemas/trips.ts` | `TripContent.tl_dr` (optional, nullable). `translations[lang]` becomes the union `JoinedItem[] \| {items, tl_dr}` with a zod transform normalizing to the object shape. |
| `frontend/components/trips/ReportView.tsx` | `resolveTlDr` helper. New `<aside data-testid="report-tldr">` block above the header. Reads `content.tl_dr` / `content.translations[lang].tl_dr` per the language toggle. |
| `frontend/lib/report/exportMarkdown.ts` (optional) | Prepend TL;DR to the markdown export. |
| `backend/tests/unit/agents/test_joiner.py` | New test: prompt parses; `_JoinerOutput` accepts and returns `tl_dr`. |
| `backend/tests/unit/agents/test_translator.py` | New test: `translate_tl_dr` round-trips; fail-soft returns original on LLM error. |
| `backend/tests/integration/test_trips_sse.py` (or equivalent) | New test: completed report has `content.tl_dr`; `translations.zh.tl_dr` present after translator runs. |
| `frontend/components/trips/ReportView.test.tsx` (new or extended) | Renders TL;DR when present (`getByTestId("report-tldr")`). Omits when null. Language toggle swaps tl_dr text. |

### 4.4 Concurrent-batch warning

**Critical:** **batch-2p (also queued) bumps the joiner prompt to v3 for a different reason.**
Both batches must land **one** joiner v3 prompt revision together — do **NOT** ship
joiner v3 in 2p and then immediately ship joiner v4 in 2q.

Coordination protocol:
1. Whichever batch lands first writes `joiner/v3.md` with **its own** additions only.
2. The second batch **edits the same `v3.md`** and bumps `agents/joiner.py` accordingly.
3. If both batches are in flight simultaneously, consolidate: write a single PR
   that contains the v3 prompt with **both** 2p's and 2q's prompt additions, and
   reference both batch IDs in the commit message.
4. Do NOT create `joiner/v4.md` for the second batch — that would mean two prompt
   versions in two consecutive batches, doubling the prompt-regression surface
   area for no benefit.

**batch-2r (perspective wiring)** does NOT touch tl_dr — tl_dr is **perspective-agnostic**
by locked decision (a single TL;DR per report, identical regardless of the
PerspectiveToggle state). The PerspectiveToggle filters items only, not the TL;DR.
batch-2r should not modify `tl_dr` rendering in `ReportView`; if it does, it's a bug.

---

## 5. Data shapes (JSON before/after)

### Before (current, post-batch-2k)

```json
{
  "trip_id": "...",
  "destination": "kyoto",
  "status": "complete",
  "latest_report_id": "...",
  "content": {
    "items": [
      { "candidate": {...}, "classification": "local_gem", ... }
    ],
    "translations": {
      "zh": [
        { "candidate": {...}, "classification": "local_gem", ... }
      ]
    }
  }
}
```

### After (batch-2q)

```json
{
  "trip_id": "...",
  "destination": "kyoto",
  "status": "complete",
  "latest_report_id": "...",
  "content": {
    "tl_dr": "kyoto's still a place where good tea matters. anywhere central tilts touristy fast, so ginkaku and arashiyama are skip — head to nishijin or southern higashiyama for the actual neighborhoods. counters over chains. november cool. allow an hour of walking between picks.",
    "items": [
      { "candidate": {...}, "classification": "local_gem", ... }
    ],
    "translations": {
      "en": {
        "tl_dr": "kyoto's still a place where good tea matters. ...",
        "items": [ { "candidate": {...}, ... } ]
      },
      "zh": {
        "tl_dr": "京都仍然是好茶讲究的地方。市中心一带很快会变得很游客向...",
        "items": [ { "candidate": {...}, ... } ]
      }
    }
  }
}
```

### Old report (pre-2q) — still valid

```json
{
  "content": {
    "items": [ ... ],
    "translations": { "zh": [ { ... } ] }
  }
}
```

Renders correctly: `tl_dr` is absent → frontend omits the section. `translations.zh`
is an array → zod transform normalizes to `{items: [...]}` → `resolveItems` keeps
working unchanged.

---

## 6. Testing

### Backend pytest

- `test_joiner_v3_emits_tl_dr` — mock LLM returns `{"tl_dr": "...", "items": [...]}`;
  assert `joiner()` returns a payload exposing both fields and that `tl_dr` survives
  to `_save_report`.
- `test_joiner_v3_tl_dr_optional` — mock LLM omits `tl_dr`; `_JoinerOutput` accepts
  `tl_dr=None`; `_save_report` writes content **without** a `tl_dr` key (not `null`).
- `test_translator_copies_tl_dr_per_lang` — given a content dict with `tl_dr`,
  `_run_translations_and_update` writes `translations.en.tl_dr` and
  `translations.zh.tl_dr` (string, non-empty).
- `test_translator_tl_dr_fail_soft` — `translator_agent` LLM raises; result has
  the original English `tl_dr` under the target-lang key (not missing, not null).
- `test_translations_shape_object` — after translator runs, `translations[lang]`
  is an object with `items` + `tl_dr` keys (not a bare array).

### Frontend vitest

- `ReportView renders tl_dr when present` — mount with
  `content={items:[...], tl_dr:"kyoto's still..."}`; assert
  `getByTestId("report-tldr")` shows the paragraph.
- `ReportView omits tl_dr when null/undefined` — mount without `tl_dr`; assert
  `queryByTestId("report-tldr")` is null and the header is the first visible element.
- `ReportView swaps tl_dr on language toggle` — mount with both `content.tl_dr`
  (English) and `content.translations.zh.tl_dr` (Chinese); toggle language to zh
  via the store; assert TL;DR text changes to the Chinese string.
- `ReportView falls back to source tl_dr when translation missing` — mount with
  `content.tl_dr` but no `translations.zh.tl_dr`; toggle to zh; assert the
  English `tl_dr` still renders (no empty block, no crash).
- `TripContent zod schema accepts legacy translations shape` — parse a payload
  with `translations: {zh: [JoinedItem, ...]}` (array); assert result normalizes
  to `{items: [JoinedItem, ...]}` and the schema doesn't throw.

---

## 7. Rollout (additive, no flag)

- New reports get `tl_dr` automatically once joiner v3 + the new save path ship.
- Old reports (no `tl_dr`) render fine — the section is omitted.
- No feature flag — the TL;DR is universally a nicety, never a regression.
- No DB migration — `Report.content` is JSONB.
- Ship order:
  1. Land joiner v3 prompt + `_JoinerOutput` widening + `_save_report` write path
     (backend-only, fully backwards compatible — frontend ignores unknown `tl_dr`
     today).
  2. Land translator `translate_tl_dr` + `_run_translations_and_update` object
     shape — **frontend zod must already accept the union before this lands**, or
     existing users' next report load will fail parsing.
  3. Land frontend zod union + `ReportView` rendering. Safe to ship before step 2
     because the zod union accepts both shapes.
- Recommended sequence: step 3 → step 1 → step 2 (frontend ready, backend rolls
  in, translator last). All three can ship in one PR if reviewer prefers.

---

## 8. Open Questions

1. **Joiner round economics.** Joiner runs once per cycle round (depth 1..N). The
   final round's `tl_dr` is what we keep. Does generating `tl_dr` in every round
   (even discarded ones) waste ~200 output tokens per round? Cheap, but worth a
   note. Alternative: only ask for `tl_dr` on the final round (controller-driven),
   which complicates the prompt selection logic. **Recommendation:** generate every
   round, keep the last. Token cost is negligible vs. evidence payload.
2. **TL;DR for shared/public reports.** `SharedTripResponse.content` is a full
   `TripContent`; the new `tl_dr` field rides along automatically. No endpoint
   change needed. Confirm no PII filtering applies (it doesn't — TL;DR is
   destination-level synthesis).
3. **Markdown export of TL;DR.** Prepend to markdown? Out-of-scope or in-scope?
   Low-effort; recommend in-scope as a one-line addition to
   `exportMarkdown.ts`. Defer to implementer.
4. **Print order.** TL;DR above the header in print is desired. Confirm
   `@page` / print stylesheet doesn't accidentally hide the new `<aside>` (no
   `data-print-hide` attribute on it — should be fine).
5. **i18n fallback when translator hasn't run yet.** Between `trip_complete`
   SSE event and the translator's eventual write, a user toggling to `zh` would
   see the English `tl_dr` (per `resolveTlDr` fallback). Acceptable per the
   current items-translation behavior. Confirm no UI lint complains.
6. **Empty `tl_dr` string vs. null.** If the LLM emits `tl_dr: ""`, do we render
   the empty sticky note or treat it as absent? **Recommendation:** treat
   empty/whitespace-only as absent (`tlDr?.trim() || null` in `resolveTlDr`).

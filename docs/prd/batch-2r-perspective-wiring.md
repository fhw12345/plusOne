# PRD: batch-2r — Perspective Toggle Wiring

## 1. Problem (toggle ships but does nothing visible)

the perspective toggle (`PerspectiveToggle.tsx` — `zh` / `en` / `fused`) ships, persists to the `useReportPrefsStore` zustand store, and renders three radio chips. but flipping the chip is cosmetic: the report payload that flows into `ReportTabs` is the same `items` array either way. tab counts, per-item verdicts, evidence lists — nothing visibly changes.

what little does happen today (in `ReportTabs.filterByPerspective`) is the *wrong* shape: when perspective ≠ `fused`, items lacking `classification_en` / `classification_zh` are dropped entirely. the whole report can blank out on a pre-batch-2i payload, and the user gets the empty-state copy instead of a graceful fused fallback.

meanwhile, the data is already there: per batch-2i, every joined item carries `classification_en` and `classification_zh` alongside the fused `classification`. the frontend just needs to *use* the per-perspective field instead of always reading the fused one.

## 2. Goals / Non-Goals

**goals**
- flipping the perspective toggle visibly changes (a) tab counts in `local gems` / `tourist traps`, (b) the verdict pill on each `ItemCard`, (c) the evidence list inside each unfolded card.
- per-perspective truth is read from `classification_zh` / `classification_en` on each item with a graceful fallback to the fused `classification` when the per-side field is null (pre-2i reports, low-coverage items).
- `disagreement` tab membership is held constant across perspective changes — it is the META view of zh-vs-en divergence and must not be re-sliced by either side.
- no items are *hidden* by switching perspective; items always render in `together`, they just re-classify.

**non-goals**
- no backend changes. the data shape is already correct.
- no per-perspective `tl_dr` (locked single-tl_dr in batch-2q).
- no per-perspective `match_scores` (locked single score set in batch-2p).
- no side-by-side comparison view.
- no copy / voice changes to the toggle chips themselves.

## 3. User Scenarios

**S1 — switch to zh shows different verdicts.**
maya is reading a fused report. an item shows `this one ★` (verdict for fused `classification = local_gem`). she clicks `中文社区`. that same item has `classification_zh = neutral` (xhs was lukewarm even though reddit raved). the card's verdict pill flips to `okay-ish` and the `local gems` tab count drops by one. the `tourist traps` count is unchanged because no item flipped into that bucket. the `two minds` tab count is unchanged.

**S2 — switch to en filters out xhs evidence on each card.**
maya unfolds an item. evidence list shows 2 reddit threads, 3 xhs notes, 1 google places review. she clicks `English community`. the unfolded card now shows 2 reddit threads + 1 google places review (xhs hidden); google places stays because it's neutral. the source count badge in the closed-card header drops from 6 to 3. switching back to `blended` restores all 6.

**S3 — old (pre-2i) report renders cleanly under fused fallback.**
ali opens a trip generated before batch-2i landed. items have no `classification_en` / `classification_zh` — only fused `classification`. ali toggles to `中文社区`. every item's `resolveClassification` falls through to fused, so verdicts and tab counts look identical to `blended`. nothing blanks out, no empty-state copy appears. (this fixes today's regression where `ReportTabs.filterByPerspective` would drop every pre-2i item under non-fused perspectives.)

## 4. Technical Design

### 4.1 No backend changes

stated loud: **this is FRONTEND-ONLY.** the backend (`backend/src/plus_one/agents/_divergence.py` and the trip runner's joiner) already emits `classification_en`, `classification_zh`, and `divergence_score` on every item per batch-2i. no schema migration, no agent change, no api change. zod schemas in `frontend/lib/schemas/trips.ts` already model the optional per-side fields. ship 2r without touching `backend/`.

### 4.2 Frontend changes

**(a) `lib/trips/categorize.ts` — new signature.**
```ts
categorize(items: JoinedItem[], perspective: Perspective): Record<TabKey, JoinedItem[]>
```
all classification reads inside `categorize` go through `resolveClassification(item, perspective)` instead of `view.classification` directly. `disagreement` membership is still computed via `isDisagreement(item)` which reads the raw `classification_en` / `classification_zh` pair — *not* via the resolved field — so the disagreement tab stays perspective-agnostic. `together` continues to include every item.

**(b) new helper: `lib/trips/resolveClassification.ts`.**
```ts
export function resolveClassification(
  item: JoinedItemView,
  perspective: Perspective,
): JoinedItemView["classification"] | undefined {
  if (perspective === "zh") return item.classification_zh ?? item.classification;
  if (perspective === "en") return item.classification_en ?? item.classification;
  return item.classification;
}
```
returns `undefined` when neither the per-side nor the fused field is present (item then has no verdict pill, same as today).

**(c) `ReportTabs.tsx` — pass perspective through, stop pre-filtering.**
- delete `filterByPerspective` and the `allHiddenForPerspective` branch (no longer reachable because we no longer hide items).
- read `perspective` from the store (same hook as today), pass to `categorize(items, perspective)`.
- compute the disagreement bucket once with the same `categorize(items, perspective)` call — disagreement is *inside* `categorize` and is perspective-independent by construction.

**(d) `ItemCard.tsx` — verdict and evidence read perspective.**
- accept `perspective` as a prop (passed by `ReportTabs` from the same store read; avoids each card re-subscribing).
- compute `const effectiveClassification = resolveClassification(view, perspective);` and use it to pick the `VERDICT_BY_CLASS` entry instead of `view.classification`.
- filter `evidence` for the unfolded list and the closed-card source count:
  - `zh`: keep `source ∈ {xiaohongshu, google_places}`.
  - `en`: keep `source ∈ {reddit, google_places}`.
  - `fused`: keep everything (no filter).
  - undefined / unknown source: treat as neutral and keep (defensive; google places is the only "neutral" source today but we don't want to drop unknown future sources).
- the per-language badge strip (the `EN local_gem` / `ZH neutral` row) stays untouched — it's the raw evidence of why the verdict changed and is useful in every perspective.

### 4.3 Files modified table

| file | change |
|---|---|
| `frontend/lib/trips/resolveClassification.ts` | **new** — per-perspective resolution + fused fallback. |
| `frontend/lib/trips/resolveClassification.test.ts` | **new** — vitest for the three perspectives × (per-side present / null / both null) matrix. |
| `frontend/lib/trips/categorize.ts` | add `perspective` param; route classification reads through resolver; disagreement unchanged. |
| `frontend/lib/trips/categorize.test.ts` | update existing cases; add per-perspective cases. |
| `frontend/components/trips/ReportTabs.tsx` | delete `filterByPerspective` + `allHiddenForPerspective`; thread `perspective` into `categorize` and `<ItemCard>`. |
| `frontend/components/trips/ReportTabs.test.tsx` | (existing or new) — RTL test: click toggle, assert tab counts change. |
| `frontend/components/trips/ItemCard.tsx` | accept `perspective` prop; verdict via `resolveClassification`; evidence filtered by perspective. |
| `frontend/components/trips/ItemCard.test.tsx` | (existing or new) — verdict + evidence assertions under each perspective. |

no other files touched. no zustand-store change. no schema change.

### 4.4 Concurrent-batch warning

**batch-2p also touches `categorize.ts`** (it adds match-score-based rules to populate the `user_only` / `partner_only` buckets). sequence is locked:

1. **2p lands first** — adds match-score logic, keeps the single-argument `categorize(items)` signature.
2. **2r builds on top** — adds the `perspective` second argument, routes all classification reads (including 2p's new ones) through `resolveClassification`.

if 2p is still in flight when 2r starts, rebase 2r onto post-2p `main` before opening the PR. do not parallel-merge. the conflict surface is small (signature + classification reads inside the `for (const item of items)` loop) but mechanical, not semantic — the 2p rules continue to apply on the resolved classification.

## 5. Data flow diagram (text-only)

```
[user clicks chip]
        │
        ▼
PerspectiveToggle.onClick
        │
        ▼
useReportPrefsStore.setPerspective("zh" | "en" | "fused")  ── persisted to localStorage
        │
        ▼
(re-render)
        │
        ├──> ReportView reads `perspective` (hydration-aware)
        │           │
        │           ▼
        │     ReportTabs receives items + reads perspective from store
        │           │
        │           ├──> categorize(items, perspective)
        │           │         │
        │           │         ▼
        │           │   resolveClassification(item, perspective) per item
        │           │         │
        │           │         ▼
        │           │   buckets: { together, local_gems, tourist_traps, disagreement, … }
        │           │   (disagreement computed from raw zh/en pair, not resolved)
        │           │
        │           └──> <ItemCard item perspective />
        │                     │
        │                     ▼
        │                resolveClassification(view, perspective) → verdict pill
        │                evidence.filter(by perspective)          → unfolded list + source count
        │
        └──> (no other subscribers; tl_dr & match_scores stay perspective-independent)
```

## 6. Testing

**frontend vitest — pure helpers.**
- `resolveClassification.test.ts`: nine cases — three perspectives × (both per-side present, only fused present, all null). assert correct field returned or `undefined`.
- `categorize.test.ts`: extend existing fixtures. for an item with `classification = local_gem`, `classification_zh = neutral`, `classification_en = local_gem`:
  - `categorize(items, "fused").local_gems` includes it; `tourist_traps` does not.
  - `categorize(items, "zh").local_gems` does NOT include it; `tourist_traps` does not.
  - `categorize(items, "en").local_gems` includes it.
  - `categorize(items, *).disagreement` membership is identical across all three perspectives.

**frontend RTL — integration.**
- `ReportTabs.test.tsx`: render with a fixture containing two items where the zh/en/fused classifications disagree. click `中文社区`, assert the count badge next to `local gems` decreased. click `English community`, assert it changed again. click `blended`, assert it restored.
- `ItemCard.test.tsx`: render with an item whose evidence list has reddit + xhs + google_places. under `perspective="en"`, assert the rendered `<a>` for the xhs evidence is absent and the reddit + google_places anchors are present. under `perspective="zh"`, the inverse. under `perspective="fused"`, all three present.
- pre-2i fallback case: render a fixture item with `classification = local_gem`, `classification_zh = null`, `classification_en = null`. under any perspective, the verdict pill reads `this one ★` and the item appears in `local gems`.

no e2e (playwright) needed — covered by the above; report rendering is already exercised by existing trip-detail e2e.

## 7. Rollout

- **no feature flag.** the change is additive at the component layer; default perspective is `fused` which preserves today's behavior bit-for-bit for any item where the resolver falls through.
- **old reports unaffected.** pre-2i payloads have null `classification_en` / `classification_zh`; the resolver returns the fused `classification` for them under every perspective, and the disagreement gate already fails closed on null per `isDisagreement`.
- **storage.** zustand persist key `plus-one-report-prefs` is unchanged. existing users keep their last perspective. no migration.
- **ship order.** must land after batch-2p (categorize rules for `user_only` / `partner_only`). see §4.4.
- **no user-facing copy changes.** the toggle chip labels stay `中文社区` / `English community` / `blended` (scrapbook lowercase preserved). empty-state copy for tabs is unchanged because we no longer hide items per perspective — the "switch back to blended" line in `ReportTabs` gets deleted along with `allHiddenForPerspective`.

## 8. Open Questions

1. should the per-language badge strip (`EN local_gem` / `ZH neutral`) on each card *also* be perspective-aware (e.g., dim the inactive side)? leaning **no** — the strip is the receipt for *why* the verdict moved, hiding half of it defeats the point. flagging for design review.
2. for an item where `classification_zh = insufficient`: under `zh` perspective, do we show the `thin signal` verdict, or fall through to fused? current spec says **show `thin signal`** (`insufficient` is a real per-side outcome, not missing data — only `null` triggers the fallback). confirm with PM.
3. when perspective is `zh` but an item has zero zh-side evidence (xhs returned nothing, google places returned nothing), the evidence list will be empty inside the unfolded card. acceptable? probably yes — it surfaces "we couldn't verify this from the zh side", which is honest. no extra empty-state copy needed.
4. should `divergence_score` be displayed somewhere when perspective ≠ `fused` (as a hint that "the other side disagrees")? out of scope for 2r, file as a future batch if PM wants it.

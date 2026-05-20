# Batch 2g PR A — ReportView Tabs + Expandable Cards

**Owner:** Frontend
**Branch:** `feat/batch2g-pr-a-report-tabs` (cut from `main` HEAD after batch 2f PR B merges; currently sits on `feat/batch2f-pr-b-trips` @ `de45c2a`)
**Status:** PRD draft — awaiting Code Agent
**Date:** 2026-05-20
**Predecessor:** Batch 2f PR B (`#15`). PRD at
`C:\Users\haowenfeng\repo\newproject\docs\prds\batch2f-pr-b-trips.md`.

---

## 1. Context

Batch 2f PR B shipped the end-to-end trip skeleton — `/app/trips/new` form,
SSE consumer, persisted report fetch, and a happy-path Playwright spec.
To unblock that ship, `ReportView` was intentionally rendered at debug
grade: each `JoinedItem` is dumped as raw JSON inside a `<pre>` block.

Current `frontend\components\trips\ReportView.tsx:9-37`:

```tsx
export function ReportView({ trip }: ReportViewProps) {
  const items = trip.content?.items ?? [];
  return (
    <section className="flex flex-col gap-4" data-testid="report-view">
      <header className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Report</h2>
        <span className="...">{trip.status}</span>
      </header>
      {items.length === 0 ? (
        <p className="text-foreground/70 text-sm">No results yet.</p>
      ) : (
        <ul className="...">
          {items.map((item, idx) => (
            <li key={idx} className="... font-mono text-xs">
              <pre>{JSON.stringify(item, null, 2)}</pre>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

The original product PRD (`docs/prd.md` §4 "Output") specifies the
report should render as a TL;DR plus six tabs (🤝 Together, 🚶 You-only,
🚶‍♀️ Partner-only, ⚠️ Disagreement, 🌟 Local Gems, ⚠️ Tourist Traps),
with expandable cards per item carrying evidence count, match scores,
and source links.

This PR pays back that debt — frontend only, no backend schema change.
Tabs are categorized from the fields that **actually exist** on
persisted `JoinedItem` rows today (§3); fields the original spec assumes
but that aren't on the wire yet degrade to "empty tab" with a friendly
empty-state message.

## 2. Goals

### G1 — `ReportView` renders production-grade, not debug-grade

After this PR:

1. **TL;DR section** sits at the top of the report. v1 is a deterministic,
   data-derived one-liner — no LLM call (deferred). Format:
   `"Report based on N items across M sources."` where `N = items.length`
   and `M = sum(item.evidence.length)`. If `items.length === 0`, render
   the aborted/empty-trip message instead (see G4).
2. **Six tabs** render via shadcn `Tabs` (Radix-backed). Each tab shows
   the cards categorized into it (see §3 for the categorization rules,
   which run off `JoinedItem.classification` — the field that actually
   exists — not the missing `who_for` / `gem` / `trap` booleans).
3. **Expandable cards** per item — header shows name, evidence-count
   badge, classification badge; body (collapsed by default) shows
   summary, confidence, and clickable source links.

### G2 — All existing gates remain green

- `cd frontend && pnpm build` exits 0; no hydration warnings.
- `cd frontend && pnpm lint` exits 0.
- `cd frontend && pnpm exec prettier --check .` exits 0.
- `cd frontend && pnpm typecheck` exits 0.
- `cd frontend && pnpm test` exits 0 — adds component tests for
  `ItemCard` and `ReportView` (see §6).
- `cd frontend && pnpm exec playwright test --project=chromium` —
  **all 12 cases still green**. The existing `trip-flow.spec.ts`
  Tokyo-in-header assertion (`getByText(/Tokyo/i)`) must continue to
  pass; see §11 R1 for why that assertion still holds against the
  aborted-trip empty state.

### G3 — One new e2e assertion that the tabs surface exists

In `e2e/trip-flow.spec.ts` (an existing spec — extend, do not create a
new spec file), append a single soft assertion that
`page.getByRole("tablist")` is visible on the trip-detail page after
the terminal status is reached. The existing 12-case total stays at
12 cases; no new spec files.

### G4 — Aborted / empty-trip state is intentional, not broken-looking

When `items.length === 0` (the today-default in CI because
`PLUS_ONE_ALLOW_REAL_LLM=0` forces `cycle_aborted`), the ReportView
must render:

- The trip header (destination + status badge) — unchanged.
- A friendly empty-state panel: *"This trip didn't produce results — try
  a different destination or check back later."*
- **No tab strip** in the empty case (six empty tabs would look broken).

Backend `trip.status === "aborted"` and `items.length === 0` collapse to
the same empty-state UI in v1; if a future cycle returns 0 items despite
`status === "complete"`, the same empty state renders (with the friendly
copy still accurate — "didn't produce results").

## 3. JoinedItem shape — what we can actually read

**This is the load-bearing research finding for this PRD.** The original
PRD §4 spec assumes fields that do not exist on persisted items today.
Code Agent must render off the real shape, not the aspirational one.

### 3.1 Authoritative source

Persisted via
`backend\src\plus_one\services\trip_runner.py:164`:

```python
content={"items": [i.model_dump(mode="json") for i in items]},
```

Where `items: list[JoinedItem]` comes from
`backend\src\plus_one\agents\joiner.py:32-41`:

```python
class JoinedItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate: Candidate
    classification: Classification
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[Evidence, ...] = Field(default=())
    summary: str = Field(default="", max_length=500)
```

`Candidate` (`backend\src\plus_one\agents\producer.py:23-39`):

```python
class Candidate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    area: str | None = Field(default=None, max_length=100)
    style: str | None = Field(default=None, max_length=100)
    rationale: str = Field(default="", max_length=500)
```

`Classification` and `Evidence` (`backend\src\plus_one\agents\types.py`):

```python
Classification = Literal["local_gem", "tourist_trap", "neutral", "insufficient"]

class Evidence(BaseModel):
    source: Literal["reddit", "xiaohongshu", "google_places"]
    url: str
    snippet: str
    sentiment: float | None  # -1..1, null for factual sources
```

### 3.2 Mapping — original spec vs reality

| Original PRD §4 field | Exists on `JoinedItem` today? | Frontend handling in v1 |
|----------------------|-------------------------------|-------------------------|
| `name` / `title` | Yes — `candidate.name` | Render as card header |
| `who_for: "together" \| "user" \| "partner"` | **No** | Together / You-only / Partner-only tabs are empty in v1 with a friendly empty-state |
| `disagreement: boolean` | **No** | Disagreement tab is empty in v1 (Batch 2i scope) |
| `category: "local_gem" \| "tourist_trap"` or `gem` / `trap` booleans | **Yes** — `classification` enum carries `local_gem` / `tourist_trap` / `neutral` / `insufficient` | Local Gems tab = items where `classification === "local_gem"`; Tourist Traps tab = items where `classification === "tourist_trap"` |
| `sources: Array<...>` for evidence count | **Yes** — `evidence: Evidence[]` (length = evidence count; each has `url`, `snippet`, `source`, `sentiment`) | Card header badge: "N sources" / "N evidence"; card body: list of clickable source URLs |
| `scores: { user, partner }` per-person match scores | **No** — only `confidence: number` (0..1) exists | Show `confidence` as a single "Confidence: 0.NN" line in the card body. No per-person split until upstream agents emit it. |
| `description` | Closest analog: `summary: string` (≤500 chars) | Render in card body. If empty, omit the field rather than rendering a blank line. |
| TL;DR field | **No** | Render the deterministic placeholder per §G1.1; LLM synthesis deferred to a later PR |

### 3.3 Tab categorization rules — final

Run each `JoinedItem` through this function and produce a `Set<TabKey>`:

| Tab key | Label (emoji + text) | Inclusion rule (v1) |
|---------|---------------------|---------------------|
| `together` | `🤝 Together` | Include every item (no `who_for` field; default everyone-relevant). Equivalent to "All" in v1. |
| `user_only` | `🚶 You-only` | None in v1 — empty state. (Inclusion rule once backend lands: `item.who_for === "user"`.) |
| `partner_only` | `🚶‍♀️ Partner-only` | None in v1 — empty state. |
| `disagreement` | `⚠️ Disagreement` | None in v1 — empty state (Batch 2i). |
| `local_gems` | `🌟 Local Gems` | `item.classification === "local_gem"` |
| `tourist_traps` | `⚠️ Tourist Traps` | `item.classification === "tourist_trap"` |

`neutral` and `insufficient` items appear in `together` only (they are
neither gem nor trap, but they are still part of the report).

Empty-tab UI: a short paragraph specific to the tab — e.g. for
`user_only`, "No you-only items yet. Coming in a future update once
per-person preferences are wired in." — so the empty state reads as
*"we know, this is by design"* not *"this is broken"*. Keep copy short,
plain, and consistent.

### 3.4 Defensive parsing

The frontend zod schema for `JoinedItemSchema` is already
`z.object({}).passthrough()` (`frontend\lib\schemas\trips.ts:23`), which
keeps unknown fields. Code Agent must **not** tighten it to validate the
backend shape today — the renderer reads fields defensively
(`item.candidate?.name ?? "Untitled"`, `item.evidence ?? []`, etc.) so a
future backend addition (e.g. `who_for`) doesn't get stripped on its way
through zod, and a missing field in legacy/aborted data doesn't crash
the render. See §5 for the precise schema relax.

## 4. Non-Goals

- **TL;DR LLM synthesis.** v1 ships the deterministic one-liner; LLM
  call is a follow-up PR.
- **Disagreement detection.** Batch 2i owns the agent work. This PR
  only renders an empty Disagreement tab.
- **Perspective toggle / language toggle.** Batch 2i / 2k.
- **Per-card 👍 / 👎 feedback buttons.** No write path exists; deferred.
- **Edit / delete / regenerate trip.** Deferred.
- **Save / share / export report.** Deferred.
- **Any backend changes.** This PR reads
  `Report.content = {"items": JoinedItem[]}` as it is. No schema
  changes, no new endpoints, no new fields requested upstream.
- **Trip history / list page.** Single-trip view only (same as 2f PR B).
- **Design-system overhaul.** Stay on Tailwind utilities + the minimal
  shadcn primitives this PR introduces (§5.2). No global theme rework.
- **Per-tab URL hash / deep-linking** (e.g. `#tab=local-gems`). Tab
  state is component-local in v1.

## 5. Technical Approach

All paths relative to `C:\Users\haowenfeng\repo\newproject\frontend\`.

### 5.1 File map

| Path | Add / Modify | Purpose |
|------|--------------|---------|
| `components/trips/ReportView.tsx` | Modify (rewrite body) | Compose TL;DR + Tabs + ItemCard list per tab. Empty/aborted branch renders the friendly empty state. Preserve `data-testid="report-view"` and the header (destination text, status badge) so the existing e2e Tokyo-in-header assertion keeps working. |
| `components/trips/ItemCard.tsx` | Add | One expandable card. Props: `{ item: JoinedItem }`. Header always visible (name, classification badge, evidence-count badge); body collapsed by default, toggled by a `<button aria-expanded>` (or shadcn `Collapsible`). |
| `components/trips/ReportTabs.tsx` | Add | Wraps shadcn `Tabs`. Props: `{ items: JoinedItem[] }`. Computes per-tab buckets via `categorizeItem(item)` helper (also in this file or a sibling `lib/trips/categorize.ts` — Code Agent's call; pick whichever is easier to unit-test). Renders six `<TabsTrigger>` + six `<TabsContent>` with the ItemCard list (or per-tab empty state) inside each. |
| `components/ui/tabs.tsx` | Add | shadcn `Tabs` primitive (Radix-backed). Install with `npx shadcn@latest add tabs`. `@radix-ui/react-tabs@1.1.1` is already in `package.json:25` — install just wires the styled wrapper. |
| `components/ui/card.tsx` | Add | shadcn `Card`. Install with `npx shadcn@latest add card`. Pure presentational — no extra Radix dep. |
| `components/ui/badge.tsx` | Add | shadcn `Badge`. Install with `npx shadcn@latest add badge`. Pure presentational. |
| `components/ui/collapsible.tsx` | Add | shadcn `Collapsible` (Radix-backed). Install with `npx shadcn@latest add collapsible`. **Brings in `@radix-ui/react-collapsible` as a new runtime dep** — the only new runtime dep introduced by this PR. **Alternative:** Code Agent may skip this and roll a 10-line `useState` toggle inside `ItemCard` instead; either is acceptable. If skipped, document the choice in the PR description and don't install the package. |
| `lib/utils.ts` | Add | `cn(...)` helper — standard shadcn utility: `clsx` + `tailwind-merge`. Both deps are already in `package.json:22, 32`. Required by every shadcn primitive. |
| `components.json` | Add | shadcn config (created automatically by `npx shadcn@latest init`). One-time; commit alongside the first primitive. |
| `lib/schemas/trips.ts` | Modify | See §5.3 — keep `JoinedItemSchema` as `passthrough()` (no change in spirit), but optionally split out a lightly-typed `JoinedItemView` type for `ItemCard` to consume so the categorization logic gets some TS narrowing. |
| `app/globals.css` | Modify if needed | shadcn `init` usually injects CSS vars (`--background`, `--foreground`, `--border`, `--radius`, etc.). Plus One's `tailwind.config.ts:7-25` already references several of these as HSL vars, so this should be additive only. Code Agent verifies no token gets overwritten. |
| `components/trips/__tests__/ItemCard.test.tsx` | Add | Vitest + RTL — see §6. |
| `components/trips/__tests__/ReportView.test.tsx` | Add | Vitest + RTL — see §6. |
| `components/trips/__tests__/ReportTabs.test.tsx` | Add (optional) | If the categorization helper is non-trivial, unit-test it directly here. Otherwise the ReportView test covers it. |
| `e2e/trip-flow.spec.ts` | Modify | Append a single `await expect(page.getByRole("tablist")).toBeVisible();` after the terminal-status assertion. Guarded so it doesn't fail on the aborted/empty path — see §6.3 for the exact wording. |

### 5.2 shadcn install order (one-time)

```bash
cd frontend
npx shadcn@latest init        # creates components.json + lib/utils.ts + globals.css tokens
npx shadcn@latest add tabs    # components/ui/tabs.tsx
npx shadcn@latest add card    # components/ui/card.tsx
npx shadcn@latest add badge   # components/ui/badge.tsx
npx shadcn@latest add collapsible  # OPTIONAL — see file-map row
```

Defaults to pick during `init`:

- Style: `default` (not `new-york`) — matches the modest visual posture.
- Base color: `slate` (or `zinc`; Code Agent picks one and sticks with it).
- CSS variables: yes.
- Path alias for components: `@/components`.
- Path alias for utilities: `@/lib/utils`.
- React Server Components: yes (Next 16 app router).
- Tailwind config: `tailwind.config.ts` (already present).
- Tailwind CSS file: `app/globals.css` (already present).

The generated `components.json` and `lib/utils.ts` must be committed.

### 5.3 Zod schema — `frontend/lib/schemas/trips.ts`

`JoinedItemSchema` is already `z.object({}).passthrough()` (line 23) —
**leave it that way**. The reason it's currently loose is the same reason
it should stay loose: backend `JoinedItem.model_dump(mode="json")` will
grow fields (most likely `who_for`, perhaps `scores`) in future batches,
and we don't want this PR to be the place that strips them.

Optional addition (Code Agent's call): export a *non-validating* view
type used purely for autocomplete inside `ItemCard.tsx`:

```ts
// In lib/schemas/trips.ts, AFTER the passthrough schema.
export type JoinedItemView = {
  candidate?: { name?: string; area?: string | null; style?: string | null; rationale?: string };
  classification?: "local_gem" | "tourist_trap" | "neutral" | "insufficient";
  confidence?: number;
  evidence?: Array<{
    source?: "reddit" | "xiaohongshu" | "google_places";
    url?: string;
    snippet?: string;
    sentiment?: number | null;
  }>;
  summary?: string;
} & Record<string, unknown>;
```

`ItemCard` casts `item as JoinedItemView` at the boundary; everything
downstream is optional-chained. If a field shows up unexpectedly, it's
preserved by the passthrough and ignored by the renderer.

### 5.4 Component tree

```
ReportView
├─ <header>  (destination + status badge — preserved from current impl)
├─ TL;DR section (1 paragraph)
├─ ReportTabs (only rendered when items.length > 0)
│   └─ Tabs (shadcn)
│       ├─ TabsList: 6 × TabsTrigger
│       └─ 6 × TabsContent
│           └─ list of ItemCard | empty-state paragraph
└─ EmptyState (only rendered when items.length === 0)
```

`ReportTabs` always renders all six tab triggers. Within each
TabsContent, if the bucket is empty, render the tab-specific friendly
empty state instead of an `<ul>`. The `together` tab is the default
selected tab (`defaultValue="together"`), since it's the only non-empty
tab in v1.

### 5.5 ItemCard

Header (always visible):
- **Name** — `item.candidate?.name ?? "Untitled"`. Plain text, no
  decorative font (§9). Use the default text size / weight; do not
  scale up beyond `text-base font-medium`.
- **Classification badge** — `Badge` colored by classification:
  - `local_gem` → green-ish (`variant="default"` or shadcn `secondary`
    with a custom hue — Code Agent picks; keep it subtle).
  - `tourist_trap` → red-ish.
  - `neutral` → muted.
  - `insufficient` → outline / muted, label "Low evidence".
  - Missing classification → omit the badge.
- **Evidence-count badge** — `Badge` variant `outline`, text
  `"{n} sources"` where `n = item.evidence?.length ?? 0`. If `n === 0`,
  omit entirely.
- **Confidence chip** — small text, right-aligned: `"~{Math.round(c*100)}%"`
  where `c = item.confidence`. If missing or NaN, omit.
- **Expand toggle button** — `aria-expanded={isOpen}`,
  `aria-controls={bodyId}`. Visible chevron icon (`lucide-react` already
  installed — `ChevronDown` / `ChevronRight`).

Body (collapsed by default, `id={bodyId}`):
- **Area / style** — one-liner: `"{candidate.area} · {candidate.style}"`
  when both present, otherwise either, otherwise omit.
- **Summary** — `item.summary` rendered as `<p>` when non-empty.
- **Sources** — `<ul>` of `<a href={ev.url} target="_blank" rel="noopener noreferrer">`
  links labeled by source + a truncated URL. Each item also shows the
  snippet (max ~140 chars).
- **Rationale** — `candidate.rationale` if non-empty, prefaced with
  "Why this came up:".

All optional fields are conditionally rendered; the card body never
shows blank labels.

### 5.6 TL;DR section

```tsx
function TLDR({ items }: { items: JoinedItem[] }) {
  const evidenceCount = items.reduce((acc, i) => acc + (i.evidence?.length ?? 0), 0);
  return (
    <p className="text-sm text-foreground/80">
      Report based on {items.length} item{items.length === 1 ? "" : "s"}{" "}
      across {evidenceCount} source{evidenceCount === 1 ? "" : "s"}.
    </p>
  );
}
```

Only rendered when `items.length > 0` — the empty-state panel replaces
it otherwise.

### 5.7 Empty-state panel (aborted / no items)

```tsx
<div className="border-foreground/10 rounded border p-4 text-sm" data-testid="report-empty">
  <p className="font-medium">No results for this trip.</p>
  <p className="text-foreground/70 mt-1">
    This trip didn't produce results — try a different destination or check back later.
  </p>
</div>
```

`data-testid="report-empty"` is added so the existing e2e can be extended
in a future PR without grepping for prose copy. (Not asserted in this
PR's e2e.)

## 6. Tests

### 6.1 Vitest — `ItemCard.test.tsx`

| # | Case | Asserts |
|---|------|---------|
| 1 | renders candidate name in the header | `getByText("Some Ramen Shop")` visible |
| 2 | renders evidence-count badge when evidence is non-empty | `getByText(/3 sources/i)` visible |
| 3 | omits evidence-count badge when evidence is empty | `queryByText(/sources/i)` null |
| 4 | renders classification badge for `local_gem` | `getByText(/local gem/i)` visible |
| 5 | body is collapsed by default | `queryByText("summary text")` null; toggle button has `aria-expanded="false"` |
| 6 | clicking the toggle expands the body | after click, `getByText("summary text")` visible, button has `aria-expanded="true"` |
| 7 | source links have `target="_blank"` and `rel="noopener noreferrer"` | `getByRole("link", { name: /reddit/i })` attrs |
| 8 | degrades gracefully on a minimal item (only `candidate.name`) | no crash; renders header only |

### 6.2 Vitest — `ReportView.test.tsx`

| # | Case | Asserts |
|---|------|---------|
| 1 | renders the destination + status badge (preserved from current behavior) | `getByText("Tokyo")`, `getByText(/aborted/i)` (or whatever status) |
| 2 | renders TL;DR with item + source counts when items are present | `getByText(/Report based on 2 items across 5 sources/i)` |
| 3 | renders six tab triggers with their labels | `getAllByRole("tab")` has length 6; labels include `/together/i`, `/local gems/i`, `/tourist traps/i`, etc. |
| 4 | clicking a tab switches the visible TabsContent | RTL `userEvent.click(localGemsTab)` → cards under it visible, together tab cards hidden |
| 5 | tabs with no items show the tab-specific empty-state paragraph | `getByText(/no.*you-only.*yet/i)` etc. |
| 6 | renders the aborted/empty-state panel and no tab list when `items.length === 0` | `getByTestId("report-empty")` visible; `queryByRole("tablist")` null |
| 7 | renders the aborted/empty-state when `trip.content` is null | same as 6 |

### 6.3 Playwright — `e2e/trip-flow.spec.ts` (modify, don't add)

Append after the terminal-status `expect` block, but only when
`status === "complete"` AND items are visible. The simplest defensive
form (Code Agent owns final wording, but this is the contract):

```ts
// Soft check: when the trip produced any items, the tab list is up.
// Aborted trips in CI render the empty-state panel instead.
const tabList = page.getByRole("tablist");
const emptyState = page.getByTestId("report-empty");
await expect(tabList.or(emptyState)).toBeVisible({ timeout: 5_000 });
```

The Tokyo-in-header `getByText(/Tokyo/i)` assertion at
`trip-flow.spec.ts:43` **stays exactly as is**. Per the spec's own
comment at lines 39-43, with `PLUS_ONE_ALLOW_REAL_LLM=0` the cycle
aborts and the destination text comes from the page header, not the
report region. Our refactor preserves the header verbatim (§5.1), so
this assertion continues to pass.

No new spec files; case count stays at 12.

## 7. Accessibility

- **Tabs** — shadcn `Tabs` wraps `@radix-ui/react-tabs`, which is
  keyboard-navigable by default: arrow keys move between triggers,
  `Home`/`End` jump to first/last, focus follows selection. Code Agent
  verifies this in DevTools (no extra wiring needed).
- **ItemCard expand button** — must be a real `<button>` with
  `aria-expanded={isOpen}` and `aria-controls={bodyId}`. The chevron
  icon is decorative (`aria-hidden="true"` on the `<svg>`). The button
  must have an accessible name — either visible text ("Expand" /
  "Collapse") or `aria-label="Show details for {name}"` if icon-only.
- **Source links** — `target="_blank"` requires `rel="noopener noreferrer"`
  (security + perf).
- **Empty-state panel** — plain text inside a `<div>`. No live region
  needed; the report load is page-driven, not push.
- **Color contrast** — classification badges must meet 4.5:1 contrast
  for text against badge fill. shadcn defaults pass this; Code Agent
  spot-checks with browser DevTools' contrast picker if introducing
  custom hues.
- **Focus order** — TL;DR (no interactive) → tab triggers → tab content
  → expand button → source links. Natural DOM order is correct.

## 8. CRITICAL design constraint (per `C:\Users\haowenfeng\repo\CLAUDE.md` standing rule)

> 切记不要为了花里胡哨把字体弄得不好看清。

**Translation:** never sacrifice font legibility for decoration. In
practice for this PR:

- Default to the platform font stack inherited from `app/layout.tsx`. No
  display fonts, no script fonts, no custom font loading.
- Card headers max out at `text-base font-medium`. Tab labels stay at
  `text-sm`. TL;DR is `text-sm`. Body copy is `text-sm`. Source-link
  URLs are `text-xs` and `truncate`.
- Emojis in tab labels (🤝 🚶 🚶‍♀️ ⚠️ 🌟 ⚠️) are fine — they're sized
  via the surrounding text, not as decorative SVGs.
- No `tracking-` or `leading-` overrides that compress legibility.
- Never use `font-thin`, `font-extralight`, or `font-black` for any
  body or label text — keep weight in the normal/medium range.
- Color: text on background must use `text-foreground` or
  `text-foreground/{70,80,90}` (never below 70%). Muted text caps at
  `text-foreground/60` for genuinely-secondary lines only.

## 9. Style / naming

- shadcn primitives live under `components/ui/`. Per-feature components
  (`ItemCard`, `ReportTabs`) live under `components/trips/`.
- Tab keys are the literal strings in §3.3
  (`"together"`, `"user_only"`, `"partner_only"`, `"disagreement"`,
  `"local_gems"`, `"tourist_traps"`). Don't abbreviate further.
- Categorization helper signature: `function categorize(items: JoinedItem[]): Record<TabKey, JoinedItem[]>`.
- `data-testid` discipline: `report-view` (existing — preserve),
  `report-empty` (new, for the empty panel). No per-card or per-tab
  testids — RTL/Playwright queries by role or accessible name.
- No `console.*` calls. No `// TODO` comments — file an issue or just
  leave the deferred work to the PRDs cited in §4.
- Comments only when the *why* is non-obvious (e.g. *"classification is
  the only categorization field that exists today; who_for is Batch
  2i — see PRD §3.2"*).

## 10. Files to change — exhaustive table

| Path | Action | Notes |
|------|--------|-------|
| `frontend/components/trips/ReportView.tsx` | Modify (rewrite render body) | Preserve `data-testid="report-view"`, header destination text, status badge |
| `frontend/components/trips/ItemCard.tsx` | Add | New expandable card |
| `frontend/components/trips/ReportTabs.tsx` | Add | Wraps shadcn `Tabs`; consumes categorize helper |
| `frontend/components/ui/tabs.tsx` | Add | Via `npx shadcn@latest add tabs` |
| `frontend/components/ui/card.tsx` | Add | Via `npx shadcn@latest add card` |
| `frontend/components/ui/badge.tsx` | Add | Via `npx shadcn@latest add badge` |
| `frontend/components/ui/collapsible.tsx` | Add (optional) | Via `npx shadcn@latest add collapsible`. Skip if rolling a `useState` toggle. |
| `frontend/lib/utils.ts` | Add | `cn()` helper (clsx + tailwind-merge) |
| `frontend/components.json` | Add | shadcn config from `init` |
| `frontend/lib/schemas/trips.ts` | Modify (optional) | Add `JoinedItemView` view-only type. **Do NOT tighten `JoinedItemSchema`.** |
| `frontend/app/globals.css` | Modify (additive) | Whatever CSS vars shadcn `init` injects; verify nothing existing is overwritten |
| `frontend/components/trips/__tests__/ItemCard.test.tsx` | Add | §6.1 |
| `frontend/components/trips/__tests__/ReportView.test.tsx` | Add | §6.2 |
| `frontend/components/trips/__tests__/ReportTabs.test.tsx` | Add (optional) | If categorize helper is non-trivial |
| `frontend/e2e/trip-flow.spec.ts` | Modify | Append the soft tablist-or-empty assertion (§6.3). Keep all existing assertions verbatim. |
| `frontend/package.json` | Modify (auto) | shadcn `init` may add `@radix-ui/react-collapsible` if collapsible is installed. No other runtime deps. |
| `frontend/pnpm-lock.yaml` | Modify (auto) | Reflects any new package |

**Backend files:** none touched. **Other frontend files:** none touched.

## 11. Risks & Mitigations

| ID | Risk | Mitigation |
|----|------|------------|
| R1 | **Tokyo-in-header e2e assertion regresses.** `trip-flow.spec.ts:43` asserts `getByText(/Tokyo/i)`. The aborted-trip path renders zero items, so the tabs/cards never carry destination text. The assertion depends entirely on the destination being in the page header (currently the `<h2>Report</h2>` sits next to a parent page that echoes the destination — see `app/app/trips/[id]/page.tsx`). | The rewrite **must keep** the destination text reachable from the trip-detail page render — either in `ReportView`'s header or in the parent page. The spec's own comment (`trip-flow.spec.ts:39-43`) makes this explicit. Don't move destination text out of the header. ReportView already takes the full `TripDetail` (not just `content.items`), so adding `<p>Trip to {trip.destination}</p>` or similar near the existing header is the safest move. |
| R2 | **All non-Together tabs are empty in v1.** With no `who_for` / `disagreement` data, and `classification === "local_gem"` / `"tourist_trap"` requiring the joiner LLM to actually populate those, four of six tabs render empty most of the time (and all six when the trip aborts). The product looks "broken." | The empty-state copy per tab (§3.3 final paragraph) reads as intentional, not erroneous. Vitest test 6.2#5 enforces every empty tab has its specific copy. The aborted-trip path collapses to the §5.7 panel and hides the tab list entirely (G4) — no row of empty tabs ever shows in CI today. |
| R3 | **shadcn `init` overwrites `globals.css` or `tailwind.config.ts`.** `init` is non-destructive in recent versions but has been observed to merge tokens. The existing `tailwind.config.ts:7-25` already declares `--border`, `--background`, `--foreground`, `--primary`, `--muted`, `--radius`. | Run `init` with `--yes` only after diffing the change set. Code Agent inspects the `git diff` after `init` and reverts any unintended override of existing tokens; only the additive primitive component files and the `lib/utils.ts` + `components.json` should be retained as net-new. |
| R4 | **`@radix-ui/react-collapsible` is a new runtime dep.** Frontend posture is "no new runtime deps unless required." | Either accept the dep (it's a 3KB Radix package, in the same family as `react-tabs` already installed) OR skip the shadcn `collapsible` primitive and roll a 10-line `useState` toggle directly inside `ItemCard`. PRD §5.1 marks the row as optional. PR description records which path was taken. |
| R5 | **Hydration mismatch from tabs.** Shadcn `Tabs` is a client component (uses Radix state). `ReportView` is already `"use client"`. The parent trip-detail page (`app/app/trips/[id]/page.tsx`) is gated on `useHasHydrated()` (per PR B §R4). | No new gates needed — the auth-gate already defers render until hydrated. Verify no nested `"use client"` boundary breaks (shadcn primitives all declare `"use client"` themselves). |
| R6 | **Empty `items` count under TL;DR.** `items.length === 0` collapses to the empty-state panel (G4), so TL;DR's "0 items across 0 sources" sentence never renders. | Render order in `ReportView` is `header → if (items.length > 0) {<TLDR /><ReportTabs />} else {<EmptyState />}`. Vitest test 6.2#6 covers this. |
| R7 | **Classification field may be missing on legacy/aborted items.** Aborted cycles persist `items=[]`, so this is moot today. But future schemas might persist partials. | Categorization helper uses `item.classification === "local_gem"` (strict equality on a possibly-undefined field is safe and yields `false`). Items missing classification fall into the `together` bucket only. Vitest test 6.1#8 covers the minimal-item degradation. |
| R8 | **shadcn `Tabs` default value when `together` has no items either.** Pathological case: every item has `classification === "neutral"` AND `items.length > 0` but the user clicks `local_gems` first via keyboard. | `defaultValue="together"` always; `together` always includes every item per §3.3 categorization rules, so it's never empty when `items.length > 0`. Tabs with empty buckets render the friendly per-tab copy — no crash. |
| R9 | **Existing 11 cases (after the 2f PR B 4-case bump) become 12 with R3 — re-verify post-merge of PR B.** Per `docs/prds/batch2f-pr-b-trips.md` §G1, 2f PR B targets 12 cases total. This PR is purely additive on the playwright side (one new assertion in an existing spec, zero new cases). | Total stays at 12. No CI workflow change. |

## 12. Acceptance Criteria

Order matters — G1 is the binding goal; gate on it first.

1. **(G1)** `ReportView` no longer renders raw JSON. Visit
   `/app/trips/{id}` for a non-aborted trip locally: see TL;DR, see
   six tab triggers with their emoji labels, see expandable cards per
   tab. Visit `/app/trips/{id}` for an aborted trip: see the empty-state
   panel and no tab strip.
2. **(G2)** `cd frontend && pnpm build` exits 0; no hydration warnings.
3. `cd frontend && pnpm lint` exits 0.
4. `cd frontend && pnpm exec prettier --check .` exits 0.
5. `cd frontend && pnpm typecheck` exits 0.
6. `cd frontend && pnpm test` exits 0. New Vitest suites
   `components/trips/__tests__/ItemCard.test.tsx` and
   `components/trips/__tests__/ReportView.test.tsx` (and the optional
   `ReportTabs.test.tsx`) all pass; existing suites stay green.
7. **(G2)** `cd frontend && pnpm exec playwright test --project=chromium`
   runs **12 cases across 6 spec files, all green**. No `.fixme`
   reintroduced. No spec files added. The Tokyo-in-header assertion at
   `trip-flow.spec.ts:43` still passes.
8. **(G3)** The new `tablist`-or-`report-empty` assertion in
   `trip-flow.spec.ts` passes against the aborted-trip path on the
   `report-empty` branch (CI default).
9. **Backend:** untouched. `just backend-check` still exits 0 (no PR-A
   change requested or implied).
10. **Manual:** screenshots of `/app/trips/{id}` in two states —
    (a) a trip with items showing the populated `together` tab and an
    expanded card; (b) the aborted/empty state — saved to
    `frontend/e2e/.artifacts/` (gitignored) and embedded in the PR
    description.
11. No `console.*` or debug code committed. No new runtime dependency
    beyond at most `@radix-ui/react-collapsible` (and only if §5.2's
    optional collapsible install is taken).
12. The 2f PR B frozen contracts (`signInE2E`,
    `trip-new-page.spec.ts` 3 cases, `trip-flow.spec.ts:18` test name
    verbatim) are not modified. Only the appended tab-list-or-empty
    assertion at the END of the single existing `trip-flow.spec.ts`
    test is new.
13. The CLAUDE.md typography rule (§8) is honored — no decorative
    fonts, no weights below normal, no contrast below 70% on text.

## 13. Out-of-PRD context / Out-of-scope follow-ups

- **TL;DR LLM synthesis** — drive from `Report.trace` or a dedicated
  summarizer agent. New PR.
- **Backend `who_for` / `scores` / `disagreement` fields** — Batch 2i.
  When these land, this PR's categorize helper just gets stricter
  inclusion rules; the passthrough zod schema already accepts them.
- **Perspective + language toggles** — Batch 2i / 2k.
- **Per-card 👍 / 👎 feedback** — requires a new backend write endpoint.
- **Save / share / export report** — separate PR + backend.
- **Deep-linkable tab state** (`?tab=local-gems`) — straightforward
  follow-up once tab UX is validated.
- **Streaming items into the report as they're joined** — flagged in
  2f PR B §8 as a "natural v2"; still deferred.

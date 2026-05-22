# PRD: batch-2n — Offline Destination Autocomplete

**Author:** fhw12345
**Date:** 2026-05-22
**Status:** Draft

---

## 1. Problem Statement

On `/app/trips/new`, the destination field is a free-text input. Users misspell place names ("kyto", "barceloan") which downstream search tools (Reddit, XHS, Google Places verification) handle poorly — the planner wastes an LLM round and 90 seconds of SSE feed only to come back with weak signal because the canonical place name was wrong.

A typo-tolerant autocomplete on the destination field would catch these mistakes at the form layer, before any LLM call. The constraint: **zero ongoing cost** — no Google Places API, no third-party autocomplete service, no API keys to rotate. Everything must work offline against a static bundled dataset.

---

## 2. Goals & Non-Goals

### Goals

- Replace the plain `<input id="dest">` in `TripForm` with a typeahead combobox.
- Show top 5–8 city suggestions as the user types, ranked by population.
- Show top 8 cities (highest-population worldwide) on focus before any typing, as a discoverability hint.
- Zero API calls. All matching happens client-side against a bundled JSON dataset.
- Free typing still works — if the user ignores suggestions and submits raw text, it goes through unchanged (preserves current backend contract: `destination: str`).
- Keyboard accessible (ARIA combobox pattern: ↑/↓ to move, Enter to pick, Esc to dismiss).
- Scrapbook voice throughout (lowercase, no exclamation, ellipses ok).
- Bundle size budget: ≤ 250KB gzipped for the dataset.

### Non-Goals

- No backend changes. `POST /api/trips` schema unchanged.
- No `destination_place_id` / lat-lng persisted to DB.
- No multi-language city names beyond what the dataset provides (e.g. "Tokyo" yes, "東京" no).
- No regions, neighborhoods, POIs, addresses — **cities only**.
- No fuzzy/Levenshtein matching — leading-substring only (per locked decision; faster and predictable).
- No "must pick from dropdown" — suggestions are optional.
- No LLM-generated follow-up questions (separate batch).
- No dates / budget fields on the form (separate batch, tracked in master PRD `Mode D`).
- No analytics on which suggestions are picked.

---

## 3. User Scenarios

### Scenario 1: Suggestion-picked happy path

**As a** user planning a trip to Kyoto, **I want** to start typing "kyo" and see Kyoto in a dropdown, **so that** I can pick the canonical spelling without thinking.

**Steps:**
1. User clicks the destination input.
2. Dropdown opens showing top 8 cities by population (Tokyo, Delhi, Shanghai, São Paulo, Mexico City, Cairo, Mumbai, Beijing).
3. User types `k`. Dropdown filters to leading-`k` cities ranked by population.
4. User types `yo`. Dropdown narrows to `kyo*` cities (Kyoto, Kyongju, etc.).
5. User presses ↓ and Enter (or clicks Kyoto, Japan).
6. Input value becomes "Kyoto, Japan". Dropdown closes.
7. User submits. `destination: "Kyoto, Japan"` is sent to backend.

**Acceptance:**
- [ ] Dropdown appears on focus, before any typing.
- [ ] Top-8 default list is the 8 highest-population cities globally.
- [ ] Filtering happens within 16ms (60fps) for any input length on a mid-range laptop.
- [ ] Submitted destination is the formatted display string `"Name, Country"`.

### Scenario 2: Free-type override

**As a** user planning a trip to a town not in the dataset, **I want** to type the name freely and submit, **so that** the planner still works on novel destinations.

**Steps:**
1. User types `everywhere quiet`. No matches in dataset.
2. Dropdown shows the no-match state: `doesn't ring a bell — type it anyway, i'll figure it out.`
3. User presses Enter (or clicks elsewhere — dropdown closes).
4. User submits. `destination: "everywhere quiet"` is sent to backend.

**Acceptance:**
- [ ] Pressing Enter with no suggestion highlighted commits the raw input.
- [ ] No-match state shows the exact copy above, lowercase scrapbook voice.
- [ ] Submit is never blocked by lack of suggestion match.

### Scenario 3: Keyboard-only navigation

**As a** keyboard user, **I want** to operate the autocomplete without a mouse.

**Steps:**
1. Focus the input via Tab.
2. Dropdown opens showing top 8.
3. ↓ highlights first option.
4. ↓ ↓ ↓ moves down.
5. ↑ moves back up.
6. Esc closes the dropdown without changing input value.
7. Re-focus, type, ↓, Enter to commit.

**Acceptance:**
- [ ] `aria-activedescendant` updates to the highlighted option's id.
- [ ] `aria-expanded` reflects open/closed state.
- [ ] `role="combobox"` on the input, `role="listbox"` on the dropdown, `role="option"` on each item.
- [ ] Esc closes dropdown; Tab moves focus to the next form field (companions).

### Scenario 4: Dataset hasn't loaded yet

**As a** user on a slow connection, **I want** the form to be usable even before the city JSON has arrived.

**Steps:**
1. User opens `/app/trips/new`. TripForm mounts and kicks off a fetch for `/data/cities.json.gz` (or static import).
2. Before the data is ready, the input accepts text normally.
3. Dropdown does not open on focus until the data is loaded.
4. Once loaded, normal behavior resumes.

**Acceptance:**
- [ ] Input never disabled.
- [ ] No error toast if fetch is slow.
- [ ] If fetch fails entirely, input falls back to plain free-text — no visible error, just no dropdown ever opens.

---

## 4. Technical Design

### Architecture

A client-only feature. No backend, no API endpoint, no schema change.

```
TripForm.tsx
└── DestinationCombobox.tsx        ← new combobox component
    ├── useCityIndex.ts            ← lazy-load hook (singleton fetch + memo)
    └── lib/cities/                ← data + matcher
        ├── cities.json (or .json.gz, served from /public)
        ├── filter.ts              ← leading-substring filter + rank
        └── index.ts               ← public API: searchCities(query, limit)
```

The dataset is fetched once per page session via `useCityIndex()`. Cached in a module-level `Promise<City[]>` so re-mounting TripForm doesn't refetch. Filtering runs synchronously on each keystroke; for 25k items × leading-substring × pop-sort, it's well under 5ms.

### Dataset

**Source:** [SimpleMaps World Cities Database — Basic (free, CC-BY 4.0)](https://simplemaps.com/data/world-cities).

**Filter at build time** to cities with `population >= 15000`. Expected count: ~25k cities. Shape per row:

```ts
type City = {
  n: string;   // name (e.g. "Kyoto")
  c: string;   // country (e.g. "Japan")
  p: number;   // population (used for ranking only)
};
```

Short keys (`n`, `c`, `p` rather than `name`, `country`, `population`) keep the JSON small. The dataset is sorted by population descending at build time so "top 8 default" is just `cities.slice(0, 8)`.

**License/attribution:** SimpleMaps Basic tier requires attribution. We'll add a comment to `lib/cities/README.md` and a credit line in the app footer or about page (out of scope here, captured as follow-up).

**Bundle strategy:** Ship as `frontend/public/data/cities-15k.json` (NOT bundled into the JS chunk — let HTTP gzip handle compression). Loaded via `fetch("/data/cities-15k.json")` inside `useCityIndex()`. Browsers will cache it indefinitely after first load.

**Build pipeline:** add a `scripts/build-cities.ts` script run via `pnpm prebuild` (or one-time and committed). Reads `simplemaps-worldcities-basic.csv` from `scripts/data/` (gitignored — operator downloads it once), filters by population, dedups by (name, country), sorts by population desc, writes to `public/data/cities-15k.json`. The CSV itself is NOT committed (license + size).

### Match logic

**Leading substring** on `name` only (lowercased), with rank by population descending.

```ts
function searchCities(query: string, limit = 8): City[] {
  const q = query.trim().toLowerCase();
  if (q === "") return cities.slice(0, limit);
  const out: City[] = [];
  for (const c of cities) {
    if (c.n.toLowerCase().startsWith(q)) {
      out.push(c);
      if (out.length >= limit) break;
    }
  }
  return out;
}
```

Cities array is pre-sorted by population, so early-exit at `limit` reached is correct.

**No fuzzy matching.** If user types "kyto" (typo), dropdown shows no-match state and lets them submit anyway.

### Key Files to Modify

| File | Change |
|------|--------|
| `frontend/components/trips/TripForm.tsx` | Replace the destination `<input>` + hint block (lines 74–92) with `<DestinationCombobox name="destination" />`. Keep the rest of the form, voice, and submit logic identical. |
| `frontend/.gitignore` | Add `scripts/data/*.csv` to avoid committing the raw SimpleMaps CSV. |

### New Files to Create

| File | Purpose |
|------|---------|
| `frontend/components/trips/DestinationCombobox.tsx` | The combobox component. Self-contained: input + dropdown + ARIA. Integrates with `react-hook-form` via `Controller` or a `ref`-forwarding pattern. |
| `frontend/components/trips/DestinationCombobox.test.tsx` | RTL tests: open on focus, filter on type, ↓/↑/Enter/Esc keyboard nav, no-match state, click-outside closes, free-type submit. |
| `frontend/hooks/useCityIndex.ts` | Lazy fetch + memo of the cities JSON. Returns `{ data, status }` where `status: "idle" \| "loading" \| "ready" \| "error"`. |
| `frontend/lib/cities/filter.ts` | Pure `searchCities(query, cities, limit)` function. Easy to unit-test. |
| `frontend/lib/cities/filter.test.ts` | Unit tests: empty query, leading-substring match, case-insensitive, pop-ranking, limit cap, no-match. |
| `frontend/lib/cities/index.ts` | Re-exports the public API. |
| `frontend/lib/cities/README.md` | Documents data source (SimpleMaps Basic, CC-BY 4.0) + attribution requirement + how to regenerate. |
| `frontend/public/data/cities-15k.json` | The dataset itself. ~25k cities, ~250KB gzipped, ~750KB uncompressed. Committed. |
| `frontend/scripts/build-cities.ts` | One-time build script: reads `scripts/data/simplemaps-worldcities-basic.csv`, filters + sorts, writes `public/data/cities-15k.json`. Documented in lib/cities/README.md. Not run by CI. |

### Dependencies

No new npm packages. Combobox built from scratch with existing tokens (per spec constraint).

### Voice / copy (final, lowercase, scrapbook)

| Surface | Text |
|---------|------|
| Input label (unchanged) | `the place` |
| Placeholder | `kyoto, paris, mendoza…` |
| Helper text (replaces current hint) | `i'll suggest as you type.` |
| No-match state row | `doesn't ring a bell — type it anyway, i'll figure it out.` |
| Dropdown option format | `Kyoto, Japan` (proper case — preserves dataset casing for place names) |

The display-format exception: city names are proper nouns and are shown as the dataset has them (e.g. "São Paulo"). Everything else stays lowercase per scrapbook voice.

---

## 5. API / Interface Changes

### Frontend types

```ts
// lib/cities/index.ts
export type City = { n: string; c: string; p: number };
export function searchCities(q: string, cities: readonly City[], limit?: number): City[];
export function formatCity(c: City): string; // "Kyoto, Japan"

// hooks/useCityIndex.ts
export type CityIndexState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; cities: readonly City[] }
  | { status: "error"; error: Error };
export function useCityIndex(): CityIndexState;

// components/trips/DestinationCombobox.tsx
interface DestinationComboboxProps {
  value: string;
  onChange: (next: string) => void;
  onBlur?: () => void;
  error?: string;
  inputId?: string; // for label htmlFor — defaults to "dest"
}
export function DestinationCombobox(props: DestinationComboboxProps): JSX.Element;
```

### Backend

No changes. `POST /api/trips` continues to accept `{ destination: string, free_text?: string, companion_ids?: string[] }`.

---

## 6. Testing Strategy

### Unit Tests (`frontend/lib/cities/filter.test.ts`)

| Test | Covers |
|------|--------|
| `empty query returns top N by population` | default-on-focus behavior |
| `"k" returns cities starting with K, K-prefix only` | leading-substring |
| `case-insensitive: "KY" and "ky" return same` | normalization |
| `results ranked by population desc` | rank order |
| `result count clamped to limit` | limit cap |
| `query with no match returns empty array` | no-match path |
| `trims surrounding whitespace from query` | input hygiene |
| `does NOT match by country` | "japan" should NOT pull Kyoto |

### Component Tests (`frontend/components/trips/DestinationCombobox.test.tsx`)

| Test | Trigger | Expected |
|------|---------|----------|
| renders input with placeholder | mount | placeholder visible |
| opens dropdown on focus when index ready | focus | listbox visible with top 8 |
| does not open when index still loading | focus during loading state | no listbox |
| filters as user types | type "ky" | dropdown narrows |
| ↓ highlights first option, ↑ wraps to last | keyboard | `aria-activedescendant` updates |
| Enter on highlighted commits | keyboard | input value = formatted city, dropdown closed |
| Enter with no highlight commits raw input | keyboard | input value = raw text |
| click option commits | mouse | input value = formatted city |
| Esc closes dropdown without changing value | keyboard | listbox hidden, input unchanged |
| no-match state shows correct copy | type unmatched | helper row visible |
| click outside closes dropdown | click document body | listbox hidden |

### Integration / E2E (Playwright, existing `e2e/auth-flow.spec.ts` style — not required but nice)

Out of scope for this PRD; if added later, scenario is: register → /app/trips/new → focus destination → type "kyo" → Enter → submit → confirm trip created with destination="Kyoto, Japan".

### Coverage gates

- `pnpm typecheck` clean.
- `pnpm lint` clean.
- `pnpm test` all green including new files.
- Banned-phrase grep across `frontend/app` + `frontend/components` + `frontend/lib`: 0 hits for `Loading…`, `Submitting…`, `Powered by AI`, `Running`/`Complete`/`Pending`/`Aborted` (as status nouns), `Our…`.

---

## 7. Rollout Plan

- No feature flag. This is a pure UI replacement of one input; no risk to existing flows.
- No backend migration.
- No deprecation cycle — the old plain input is dropped in the same PR.
- Rollback: revert the PR.
- Bundle-size budget enforced in PR review (~250KB gzipped for the JSON; verify with `gzip -c public/data/cities-15k.json | wc -c`).

---

## 8. Open Questions

- [ ] **Attribution placement.** SimpleMaps Basic requires attribution. Where does it live — app footer, `/about` route, or just `lib/cities/README.md` for now? Recommend `lib/cities/README.md` only for this batch; a public-facing credit can ship later. *Default if not specified: README only.*
- [ ] **Dataset refresh cadence.** SimpleMaps updates the dataset periodically. For this batch, ship a snapshot and don't auto-refresh. Operator regenerates on demand by re-running `pnpm tsx scripts/build-cities.ts`.
- [ ] **Display format.** "Kyoto, Japan" vs "Kyoto, JP" (ISO code). PRD locks "Kyoto, Japan" since the dataset has full country names and it's friendlier.

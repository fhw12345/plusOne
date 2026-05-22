# cities — destination autocomplete dataset

A small static dataset that powers the offline destination combobox on
`/app/trips/new`. No API calls — everything runs in the browser against
`public/data/cities-15k.json`.

## Shape

```ts
type City = { n: string; c: string; p: number };
```

- `n` — city name (e.g. `"Kyoto"`)
- `c` — country name (e.g. `"Japan"`)
- `p` — population (used for ranking only)

The array is **pre-sorted by `p` descending** so the matcher can early-exit
at `limit` and still return the top-N by population.

## Current snapshot

`frontend/public/data/cities-15k.json` is a hand-curated list of ~400 of
the most-populated / most-recognizable cities worldwide, biased toward
travel-destination relevance (every capital + every metro >1M + a long
tail of well-known travel cities).

### Why not 25k?

The PRD's preferred path was to bundle the full SimpleMaps World Cities
Basic dataset (CC-BY 4.0), filtered to `population >= 15000` (~25k rows,
~250KB gzipped). That requires downloading the SimpleMaps CSV, which
the dev environment that produced this batch could not reach.

The fallback is functionally equivalent for the autocomplete UX —
suggestions for Tokyo / Paris / Mendoza all hit on the first 1-2
keystrokes. The cost is the long tail of small cities (population
15k–100k) which fall back to free-text submission (still works, just
no autocomplete row). Documented as a known trade-off.

## Regenerating from SimpleMaps (preferred path, when network is available)

1. Download "World Cities Database — Basic" (free, CC-BY 4.0) from
   <https://simplemaps.com/data/world-cities>.
2. Drop the CSV at `frontend/scripts/data/simplemaps-worldcities-basic.csv`
   (gitignored — license + size).
3. Run `pnpm tsx scripts/build-cities.ts` from `frontend/`. It will
   filter to `population >= 15000`, dedup by `(name, country)`, sort by
   population desc, and write `public/data/cities-15k.json`.
4. Verify size: `gzip -c public/data/cities-15k.json | wc -c` — should
   be under 250KB.

The build script is not part of CI — it's a one-time refresh step.

## Attribution

If/when the SimpleMaps dataset is bundled in, the SimpleMaps Basic
license (CC-BY 4.0) requires attribution. Track the credit line as a
follow-up — recommended placement is the app footer or an `/about`
route.

The current hand-curated list has no upstream attribution requirement.

## Why short keys (`n`, `c`, `p`)?

JSON key strings are shipped on the wire for every row. With 25k rows,
`"name"` / `"country"` / `"population"` would add ~30% to the gzipped
size for zero behavioral benefit.

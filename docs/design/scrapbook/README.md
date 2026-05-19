# Plus One — Scrapbook design system (Direction D)

Production design system for Direction D (Scrapbook / Handcraft),
chosen after the A/B/C → D-G round (see `../DIRECTION_OPTIONS.md`).

## What's here

```
scrapbook/
├─ index.html            ← start here — visual index of all 8 pages
├─ scrapbook.css         ← single shared stylesheet (drop into the Next.js port)
├─ TOKENS.md             ← design tokens (color, type, motion) + Tailwind v4 @theme block
├─ VOICE.md              ← full copy corpus — all 8 SSE event types + every UI string
└─ pages/                ← static HTML mockups, one per app screen
   ├─ login.html
   ├─ auth-exchange.html
   ├─ index.html          (= app home / latest readings)
   ├─ trip-history.html   (= /trips, browse all)
   ├─ trip-new.html       (= /trips/new)
   ├─ trip-detail.html    (= /trips/[id] — the hero, mid-cycle)
   ├─ profile.html
   └─ companions.html
```

## Open these in a browser

Open `scrapbook/index.html` in any browser. No build step — pure
HTML/CSS + Google Fonts. Try the **switch to printed** toggle in the
top-right of every page.

## What's *not* here (intentional)

- No React / Next port. That's frontend-expert's job in Batch 2f.
- No Tailwind config — the `@theme` block in TOKENS.md is the spec.
- No icons. Direction D uses *no icons whatsoever* — everything is
  hand-drawn (heart, arrows, checks) in Caveat or Kalam at the cursor
  position.

## The previous Editorial Atlas mockups

Archived at `../mockups/_editorial-atlas-archive/`. Not deleted. The
user explicitly chose to evaluate options, not to discard the work.

The B/C/E/F/G one-pagers live at `../mockups/options/` and stay there
as reference.

## Handoff to frontend-expert

When porting:

1. Replace `app/globals.css` `@theme` block with the one from
   `TOKENS.md` (drop-in).
2. Copy `scrapbook.css` into `app/styles/scrapbook.css` and `@import`
   it after Tailwind preflight, before any component css.
3. Re-implement each page's HTML as a React component. The DOM
   structure shown here is intentional and matches the CSS exactly —
   don't refactor selectors.
4. For SSE wiring, use `VOICE.md` event tables verbatim. Round-robin
   when a pool has multiple lines.
5. Tilt: set `--tilt` inline per card-id (stable random in [-2.5°,
   +2.5°]). Don't randomize on every render.
6. Wire the **switch to printed** toggle to localStorage
   `plusone.view`. Initialize from system `prefers-color-scheme: dark`
   only if you want a dark variant later — D doesn't ship one in v1.

That's it. Everything else (auth flow, state mgmt, SSE consumer) is
unchanged from the existing batch 2f handoff in
`docs/handoff/REMAINING_WORK.md`.

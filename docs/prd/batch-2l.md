# Batch 2L — Scrapbook (Direction D) Production Rollout

## Why this PRD exists

Batches 2g–2k shipped features but ignored `docs/design/scrapbook/` entirely.
Frontend today is default shadcn black/white with `🚧 Phase α — under
construction` copy. This batch is a pure re-skin onto Direction D
(Scrapbook), the design system the user picked. No new features, no API
changes, no schema changes.

Code Agent: read `docs/design/scrapbook/` end-to-end as the source of
truth. This PRD names the four PR scopes and the red lines. File-level
changes are derived from the mockups (`pages/*.html`) and CSS
(`scrapbook.css`, `scrapbook-zh.css`) directly.

## Red lines (review fails on any of these)

- **No API endpoint changes, no schema changes, no new features.** Backend
  is untouched.
- **The 5 banned phrases must have ZERO hits in shipped UI** (per
  `VOICE.md` lines 265-277):
  1. `Submitting…`
  2. `Loading…`
  3. `Powered by AI`
  4. Status words as noun-pills: `Running`, `Complete`, `Pending`,
     `Aborted` as standalone labels — use colored dots + hand-written
     verbs instead ("still scribbling", "pinned", "hit a wall")
  5. Any sentence starting with `Our` (`Our agent…`, `Our system…`)
  Also banned by extension: `Sending…` (cousin of `Submitting…`),
  `🚧 Phase α`, `under construction`. Review Agent greps before approval.
- **CJK legibility per `BILINGUAL-NOTES.md` v3.** When the ZH CSS is
  imported (defensive infrastructure in 2L-a), do not compress font
  sizes for visual flair. ZH body/headline = Noto Serif SC printed serif.
  Handwriting CJK (Ma Shan Zheng / Liu Jian Mao Cao / Long Cang) is
  restricted to `.signature` and `.doodle` only — forbidden in `.annot`,
  `.margin-note`, `.scrawl`, buttons, card titles, body, list items,
  placeholders. Decorative glyphs (`★`, `→`, `↓`, `←`) inside ZH must
  be wrapped in `<span class="glyph">`. Preserve the `unicode-range`
  `@font-face` trick from `scrapbook-zh.css` verbatim.
- **Never `--no-verify`. Never `git add .` or `git add -A`. Never
  force-push main.**

## Authoritative design inputs

All under `docs/design/scrapbook/`. Read fully before coding.

| Artifact | Purpose |
|----------|---------|
| `README.md` | Port instructions, tilt strategy, localStorage key |
| `TOKENS.md` | HSL color tokens, fonts, motion, layout, `@theme` drop-in |
| `VOICE.md` | All UI copy, SSE→line pools, 5 banned phrases |
| `VOICE-zh.md` | Chinese translation (not user-facing in 2L) |
| `BILINGUAL-NOTES.md` | CJK font legibility rules (v3, hardened) |
| `scrapbook.css` (893 lines) | Production stylesheet |
| `scrapbook-zh.css` (588 lines) | CJK extension, `:lang(zh)`-scoped |
| `pages/*.html` | DOM structure per surface — the parity targets |
| `pages-zh/*.html` | Reference only — no ZH locale in 2L |

## PR breakdown

Four PRs. 2L-a is load-bearing and must merge first. 2L-b / 2L-c / 2L-d
can be authored in parallel after 2L-a lands, then rebase before ship.

### PR 2L-a — Substrate

Plumbing. No page bodies change here.

- Port `scrapbook.css` → `frontend/app/styles/scrapbook.css` verbatim
  (strip the `@import url(...Google Fonts...)` — fonts come from
  `next/font/google` in `layout.tsx` instead).
- Port `scrapbook-zh.css` → `frontend/app/styles/scrapbook-zh.css`. Same
  font-import strip. Defensive only — `<html lang="en">` stays in 2L, so
  `:lang(zh)` selectors don't match. Forward-compatible.
- Replace `app/globals.css` `:root` block with the `@theme` block from
  `TOKENS.md`. Import scrapbook CSS after Tailwind preflight. Delete
  the `.dark` block (no dark mode in v1, per `README.md` line 64).
  Preserve the `@media print` block from Batch 2j.
- Update `tailwind.config.ts`: drop shadcn token bindings, add scrapbook
  tokens, set `corePlugins.preflight: false` (preflight conflicts with
  the substrate stylesheet per `TOKENS.md` lines 160-164).
- Load fonts via `next/font/google` in `app/layout.tsx`: Caveat (400-700),
  Kalam (400/700), Special Elite, Shippori Mincho (400/500/700), Noto
  Serif JP (400/500/700), Plus Jakarta Sans (400/500/600).
- Add new components: `components/layout/Shell.tsx` (renders `.shell` +
  `.nav-strip` with crest + active-link via `usePathname` + `.type`
  crest footer), `components/layout/ViewToggle.tsx` (renders
  `.view-toggle`, reads/writes `localStorage["plusone.view"]`, toggles
  `.printed-view` on `<html>`).
- Add utilities: `lib/tilt.ts` exports `tiltFor(id: string): number` —
  deterministic hash, range `[-2.5°, +2.5°]`, stable per id.
- Add wrappers for CJK forward-compat: `components/ui/Glyph.tsx`
  (`<span class="glyph">` around `★ → ↓ ← ♥`), `components/ui/Lat.tsx`
  (`<span class="lat">` / `lat-alt` / `lat-type` for Latin tokens
  inside ZH context).
- Preflight isolation for shadcn dialogs: add `.ui-isolate` class to
  `DialogContent` / `AlertDialogContent` wrappers, define it as a
  localized normalize (box-sizing, font inheritance, button reset) so
  the existing Radix dialogs in tree (`DeleteCompanionDialog`,
  `DeleteTripDialog`, `ShareDialog`, `CompanionDialog`) keep working.

Acceptance: paper background visible on every page, view-toggle works
and persists, all existing Vitest + Playwright pass, all existing
dialogs open/close/focus-trap correctly.

### PR 2L-b — Marketing & Auth

Three small surfaces: `/`, `/login`, `/auth/exchange`. Port the JSX to
match `pages/login.html` and `pages/auth-exchange.html`. Keep the existing
React Hook Form + zod + `requestLink` / `exchange` / `me` API calls — only
the JSX shell and copy change.

- `app/page.tsx` — delete `🚧 Phase α — under construction`. Render hero
  per VOICE §Auth (crest + `let me in` headline + CTA to `/login`).
- `app/login/page.tsx` — sticky-note frame on `paper-2`, label `your
  email`, placeholder `friend@somewhere.com`, submit `send the link`.
  Disable visually via `aria-busy` + `.is-pending` class, NOT a text swap
  (`Sending…` is banned-by-extension). Post-submit microcopy
  `check your inbox. the link will look like a sticky note.`. Error
  variants per VOICE §Auth (rate-limited, server).
- `app/auth/exchange/page.tsx` — crest `letting you in`, headline
  `unpacking the link…`, yellow sticky-note `welcome back. pinning your
  notes…`, 3-tick progress with middle tick pulsing. Error branch renders
  ticket variants (`stale link`, `bad link`) per `pages/auth-exchange.html`.

### PR 2L-c — Trip surfaces (incl. SSE)

The biggest PR: `/app`, `/app/trips/new`, `/app/trips/[id]`.

- `/app` — replace header + skeleton with scrapbook hero (`your readings`
  + scrawl sub + stamp + `+ new reading` red btn) wrapped in `<Shell>`.
  Gallery is `<section class="gallery">` with mixed card types per
  `pages/index.html`.
- `TripCard.tsx` — port to `<article class="photo-card">` with
  `--tilt: ${tiltFor(trip.trip_id)}`. Status mapping per the status
  taxonomy below. Aborted trips render as `<article class="ticket">`,
  not `.photo-card`. Photo fallback (typed `.photo` with `data-label`) —
  no cover image data model exists, always use the fallback.
- `TripListEmpty.tsx` — `no readings yet. let's make the first one.` +
  `start one` btn-red linking to `/app/trips/new`.
- `/app/trips/new` — form on `paper-2` with tape, fields per
  `pages/trip-new.html`, submit `go look →`, microcopy `i'll start
  scribbling the moment you press it. takes about 90 seconds.`.
- `/app/trips/[id]` — board layout (`<section class="board">`), hero
  crest `reading no. {n} · in progress`, scratchpad on the right.
  Aborted: red ticket at top.
- **SSE voice (the heaviest lift).** Rewrite `ProgressFeed.tsx` to use
  `VOICE.md` pools verbatim (no more `Cycle started` / `Generated N
  candidates` labels). Add new modules:
  - `lib/voice/sse.ts` — `voiceFor(event, index): { line; annot? }`.
    Pool lookup tables transcribed from `VOICE.md`. Round-robin via
    `pool[index % pool.length]` where index counts prior emissions of
    the same event name in the current cycle. Substitute
    `{destination}`, `{n}`, `{place}`, `{subreddit}`, `{n_out}`, `{k}`,
    `{alt}` from `event.data`. Never render a literal `{...}`.
  - `lib/voice/verdict.ts` — `verdictFor(item): string` from the
    canned allowlist in `VOICE.md` §Place-card verdicts.
  - Heartbeat (frontend-only, no SSE): 3s silence → swap latest `.msg`
    to one of `still reading…` / `…hang on, this thread is dense.` /
    `give me a moment.`. Replaced on next real event.
- `ItemCard.tsx` — port to `.photo-card` or `.ticket` (for contested
  places). Verdict slot uses `verdictFor()`. Match-row bars per mockup.
- `ReportTabs.tsx` — keep Radix Tabs, restyle triggers as `.chip`
  buttons with `.is-on` for active.
- `Share` / `Delete` dialogs — wrap in `.ui-isolate`. Voice the copy
  per VOICE §Trip flow.

### PR 2L-d — Profile & Companions

- `/app/profile` — notebook-page form per `pages/profile.html`: `you go
  by`, `how you eat`, `how you walk`, `quiet or loud` chip-triple,
  `dealbreakers`. Submit `pin it`. Confirm `pinned ★` annot fades over
  1.5s. Right-side aside: `how i use this` + tabs row +
  housekeeping links. Housekeeping `export all my readings` and
  `delete the whole notebook` have no backends — render as placeholders
  that show a `.sticky` note `not yet — coming.` on click. `log out
  everywhere` calls existing `logout` + clears store.
- `/app/companions` — polaroid gallery per `pages/companions.html`.
  Initial-letter photo placeholder. Match-bars for `food` and `pace`
  (data from existing companion schema). `edit` / `take out` links open
  existing dialogs (rewrapped in `.ui-isolate`). Empty state: `nobody
  added yet. it's okay — solo trips are great too.`.

## SSE event → VOICE.md section pointer table

The voice corpus is the source of truth. `ProgressFeed.tsx` reads from
`lib/voice/sse.ts`, which transcribes these pools verbatim. Code Agent:
copy the line pools from `VOICE.md` directly — do not paraphrase.

| Event | VOICE.md lines | Pool selection key | Substitutions |
|-------|----------------|--------------------|---------------|
| `started` | 42-48 | none (1 pool) | `{destination}` |
| `iteration_start` | 50-60 | by iteration number (1, 2, 3, 4+) | none |
| `producer` | 62-73 | by `data.tool` (`reddit*` / `xhs*` / `places*`) | `{n}`, `{subreddit}`, `{place}` |
| `joiner` | 75-83 | by outcome from `data.n_in` / `data.n_out` (see VOICE row labels: healthy / strong / disagreement / weak) | `{n_out}`, `{place}`, `{k}` |
| `controller` | 85-94 | by `data.should_continue` + `data.reasoning` keyword (place / gap / cap / else) | `{place}` |
| `cycle_complete` | 96-102 | not currently emitted by backend (open question) — keep pool as dead code for forward compat | none |
| `trip_complete` | 104-111 | none (1 pool) | none |
| `cycle_aborted` | 113-126 | by `data.reason` prefix (maestro / empty / validation / else) | `{destination}` |
| heartbeat (no SSE) | 128-136 | round-robin on 3s silence | none |

Aux corpus pointers:

| Surface | VOICE.md section | Lines |
|---------|------------------|-------|
| Login | §Auth + onboarding → Login | 140-153 |
| Auth-exchange | §Auth + onboarding → Auth-exchange | 154-162 |
| Profile | §Auth + onboarding → Profile | 163-172 |
| Companions | §Auth + onboarding → Companions | 173-184 |
| Trip-new | §Trip flow → Trip-new | 188-202 |
| Trip-detail | §Trip flow → Trip-detail | 203-213 |
| Trip-history / `/app` | §Trip flow → Trip-history | 214-223 |
| Status taxonomy | §Status taxonomy | 226-234 |
| Place-card verdicts | §Place-card verdicts | 238-251 |
| Out-of-band (404 / 500 / logout / offline banner) | §Out-of-band & system | 255-262 |

## Status taxonomy (color dots only, no labels)

| Status | Color token | Page rendering |
|--------|-------------|----------------|
| pending | `--signal-wait` `36 18% 42%` | photo-card with `arriving by next post` in stamp slot |
| running | `--signal-live` `6 54% 47%` | pulsing red dot in scratchpad, `what i'm doing — live` header |
| complete | `--signal-done` `96 22% 36%` | `pinned ★` verdict, stamp `pinned {date}`, `what i did — saved` header |
| aborted | `--signal-snag` `16 60% 38%` | renders as `.ticket` (not `.photo-card`), red `hit a wall — {reason}` + `try again` link |

Never `<Badge>`-style pills. Never the words `Running` / `Complete` /
`Pending` / `Aborted` as standalone labels.

## Tilt + view-toggle (one-liners)

- **Tilt:** `tiltFor(id)` → deterministic hash → `[-2.5°, +2.5°]`,
  applied as inline `style={{ "--tilt": "..." }}` on `.photo-card` /
  `.ticket` / `.chip`. CSS handles `prefers-reduced-motion` and
  `.printed-view` overrides.
- **View toggle:** localStorage key `plusone.view`. Values
  `"scrapbook"` (default) / `"printed"`. Mounted once at root in
  `app/layout.tsx`. Visible top-right on every route.

## Open questions

1. **`cycle_complete` event mismatch.** `VOICE.md` lists 8 SSE events;
   backend `events.ts` declares only 7 (no `cycle_complete`). Pool ships
   as dead code in `lib/voice/sse.ts` (forward-compatible). Flag if user
   wants backend SSE change later — out of 2L scope.
2. **`producer.data.tool` values not enumerated** in schema. Code Agent
   confirms exact strings at runtime, uses substring prefix match
   (`tool.startsWith("reddit")` → reddit pool) to be robust.
3. **No cover image data model** — always render typed `.photo`
   fallback. Image generation is a future batch.

## Definition of done (goal gate)

Playwright user-agent walks the full flow on a clean Chrome profile:
sign in → magic link exchange → `/app` → new trip → SSE progress feed
in scrapbook voice → trip detail with completed report → profile →
companions → sign out. At every step: visual + UX parity with the
mockups, no literal `{...}` placeholders, view-toggle works and
persists. Plus:

- `grep -rE 'Submitting|Sending…|Loading…|Powered by AI|🚧|Phase α|under construction|\bOur\s+\w+|\b(Running|Complete|Pending|Aborted)\s*<' frontend/app frontend/components` → zero hits.
- `pnpm test && pnpm typecheck && pnpm lint && pnpm e2e` → clean.

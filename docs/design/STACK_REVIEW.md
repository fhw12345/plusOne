# STACK_REVIEW.md — Plus One Frontend

**Author:** frontend-expert
**Date:** 2026-05-14
**Status:** Recommendation, awaiting team-lead sign-off. Design tokens confirmed by designer (DESIGN_SPEC.md §10).
**Scope:** Frontend stack only. Backend (FastAPI + SSE) is fixed by ADR-001.

---

## TL;DR

Upgrade the frontend in one focused PR train (Batch 2f-prep) **before** writing
auth/trip UI on the current 2024-vintage skeleton. The current pins are 12-18
months stale, and the cost of upgrading on an empty app is a fraction of doing
it after Batch 2f ships ~1000 LOC of UI.

> Headline picks: **Next.js 16.2 + React 19.2 + Tailwind v4.3 + Motion (motion/react) + Zustand + TanStack Query + Serwist + RHF/Zod + Vitest + Playwright.**

---

## Executive summary table

| Axis | Today | Recommend | Why (1 line) |
|------|-------|-----------|--------------|
| Framework | Next 14.2.18 (App Router) | **Next 16.2** | Turbopack default + Cache Components; React 19.2 baked in; current line is stale and has CVEs |
| React | 18.3.1 | **19.2** | Actions / `useOptimistic` / `use()` map directly onto SSE + form flows; ref-as-prop kills boilerplate |
| Styling | Tailwind 3.4.14 + CVA + Radix | **Tailwind v4.3** + CVA + Radix | CSS-first `@theme` is a perfect fit for designer's tokens; 5-10x faster builds |
| Animation | none | **Motion (`motion/react`) v12** | Aman/Aesop tier needs real choreography; layout + AnimatePresence + scroll are non-negotiable |
| Data | Zustand 5 only | **Zustand 5 + TanStack Query v5** | Zustand for auth/UI state, TQ for `/api/trips/*` — SSE pushes into TQ cache via `setQueryData` |
| PWA | next-pwa 5.6 | **@serwist/next v9** | next-pwa is unmaintained, no real App Router story; Serwist is the de-facto successor |
| Forms | none | **react-hook-form + zod** | One Zod schema = client validation + type inference; share types with backend Pydantic via codegen later |
| Testing | vitest 2.1.5 | **vitest 3 + Playwright** | Unit in vitest, real E2E in Playwright (HarshJudge in Batch 2g calls Playwright under the hood anyway) |
| Add | — | `next-safe-action` (server actions wrapper), `sonner` (toasts) | Both are 2-line additions, huge UX dividend |
| Drop | — | `next-pwa`, hand-rolled cn() if any | Replaced wholesale |

---

## Per-axis decisions

### 1. Framework — **Next.js 16.2** (stay on Next, upgrade two majors)

Other candidates considered: Vite + React Router 7, TanStack Start.

**Decision:** stay on Next.js, jump 14 → 16.2.

- ADR-001 locks Next.js. Switching framework family needs a new ADR and we have
  *zero* signal that Next is hurting us. The backend SSE proxying, App Router
  layout nesting, and PWA story all work on Next.
- **Why 16, not 15:** Next 16.0 (Oct 2025) made Turbopack the default bundler
  (stable), shipped React Compiler stable, and introduced Cache Components
  (`'use cache'`) which replace the half-baked PPR. 16.2 (Mar 2026) added a
  ~400% faster dev startup and ~50% faster rendering. There is no reason to
  ship a new app on a 2-major-old line.
- **Migration cost:** Async params is the one breaking change that touches our
  `app/trips/[id]/page.tsx` shape — trivial. Middleware moved to Node runtime
  stable in 15.5, no change required for us. ~1 PR.

### 2. React — **19.2**

- React 19.2 is bundled with Next 16 — there is no choice here unless we hold
  back Next, and we are not doing that.
- Concrete wins for *this* product:
  - **Actions + `useFormStatus`** — the magic-link form and trip-input form
    become 10-line components instead of 30. Pending state for free.
  - **`useOptimistic`** — when SSE `producer` event arrives we can paint
    candidate cards optimistically before `joiner` finalises them.
  - **`use()` for promises** — clean handoff from server fetch → suspense
    boundary on the report page.
  - **ref as a prop** — every shadcn-style primitive sheds `forwardRef`.
  - **React Compiler v1.0** (stable Oct 2025, on by default in Next 16) —
    delete most `useMemo`/`useCallback`. Big readability win for the
    SSE-driven progress feed which would otherwise be memo soup.

### 3. Styling — **Tailwind v4.3** (keep Tailwind, jump major)

Other candidates: Tailwind v3 (status quo), Panda CSS.

**Decision:** Tailwind v4.3.

- v4's CSS-first `@theme` directive is **literally the right shape** for what
  the designer is producing — they hand me CSS custom properties, I drop them
  into `@theme` and the utility classes regenerate. No more
  `tailwind.config.ts` pseudo-JSON for color tokens.
- Lightning CSS + Oxide engine: 5-10x faster builds, native CSS nesting,
  container queries built in (we will want these for the report cards).
- v4.3 (May 2026) adds first-party scrollbar styling, zoom, tab-size, mask
  utilities — all things the visual-quality bar will want.
- **Why not Panda CSS:** Panda is excellent but it's a runtime+codegen step on
  top of vanilla-extract semantics. For a single-app PWA with one designer +
  one engineer, Tailwind v4 hits the same outcome with half the toolchain
  surface and zero learning curve for whoever inherits this.
- **Keep CVA + Radix + lucide.** CVA pairs cleanly with v4. Radix is the only
  serious accessible primitive set. lucide is fine.
- **Migration cost:** PostCSS config swap, drop `autoprefixer` (built in),
  drop `tailwindcss-animate` if/when added (use `@starting-style` + Motion
  instead), update `@tailwind` directives to `@import "tailwindcss"`. ~0.5 PR.

### 4. Animation — **Motion (`motion/react`) v12**

Other candidates: CSS-only (`@starting-style` + view transitions), Motion One
(vanilla).

**Decision:** `motion/react` (the artist-formerly-known-as-Framer-Motion).

- The bar in the brief is **Aman / Aesop / Cereal**. That is choreographed,
  layout-aware, gesture-responsive motion. CSS-only gets you 60% of the way
  but loses on shared layout, AnimatePresence-on-exit, and gesture-driven
  drag/swipe (which a mobile-first PWA absolutely wants).
- `motion/react` v12 supports RSC boundaries cleanly — animated components
  are client components, fine.
- **Not Motion One vanilla:** we're a React app, no point dropping the React
  bindings.
- Combine with native View Transitions (now stable cross-browser) for
  page-to-page transitions; use Motion for in-page choreography. Both are
  cheap to add.

### 5. Data layer — **Zustand 5 + TanStack Query v5** (additive)

Other candidates: Zustand-only (status quo), RSC + Server Actions only.

**Decision:** keep Zustand, add TanStack Query.

- Zustand stays for **client-only ephemeral state**: the JWT (memory-backed
  mirror of the httpOnly cookie), UI toggles, the active SSE event buffer for
  the in-progress trip.
- TanStack Query owns **server-state**: `GET /api/trips/{id}`, list of trips,
  profile/companions when those land. Caching, retry, invalidation, suspense,
  devtools — all free.
- **SSE bridge:** the `EventSource` in `lib/sse.ts` calls
  `queryClient.setQueryData(['trip', id], ...)` on each event. The report page
  reads from TQ via `useSuspenseQuery`. No prop-drilling, no race conditions.
- **Why not RSC + Server Actions only:** the SSE stream and JWT-in-cookie
  flows are inherently client-driven. RSC is great for the static report
  shell, fine — we'll use it where it makes sense — but the trip-in-progress
  page is a client island.
- **Cost:** ~50 LOC of provider wiring, 1 PR.

### 6. PWA — **@serwist/next v9**

**Decision:** migrate off `next-pwa`.

- `next-pwa` is unmaintained (last meaningful release 2023) and has no
  first-class App Router support. We're already papering over this in
  `next.config.mjs`.
- Serwist is the named successor, TS-first, App Router native, Turbopack
  compatible. Required for Next 16.
- **Cost:** rewrite `next.config.mjs` wrapper, author `app/sw.ts` (template
  is ~30 lines). Move `manifest.json` into `app/manifest.ts` for type safety.
  ~0.5 PR.

### 7. Forms / validation — **react-hook-form + zod, yes**

**Decision:** add both.

- The product has *real* forms: magic-link request, trip input (destination +
  free text + later companion picker + profile). RHF + Zod is the boring
  correct choice.
- Zod schema doubles as the type contract; we can later codegen Zod from the
  backend's Pydantic models (`datamodel-code-generator` or a small custom
  script) so a backend schema change breaks frontend typecheck. Defer that
  codegen step to when it bites us.
- Pairs with React 19 Actions — RHF v7.55+ has `useFormStatus` interop.

### 8. Testing — **Vitest 3 + Playwright**

**Decision:** add Playwright.

- Vitest 3 (current major) for unit tests of `api.ts`, stores, pure
  components. Keep.
- Playwright for E2E. Even though Batch 2g spec mentions HarshJudge, that
  orchestrator wraps Playwright underneath; having Playwright installed and
  configured locally lets us run the same specs without HarshJudge for fast
  iteration.
- One E2E spec for the golden path (login → request trip → SSE stream →
  report) is enough for v1. Add more as bugs surface.

### 9. Other adds / drops

**Add:**
- **`sonner`** — toast notifications. Needed for "magic link sent",
  "reconnecting", "session expired" cases called out in REMAINING_WORK.md
  gotchas.
- **`next-safe-action`** (optional, evaluate during Batch 2f) — typed wrapper
  around server actions with Zod validation. Pairs with RHF + Zod cleanly.
- **`@tanstack/react-query-devtools`** (dev-only) — the SSE → cache flow
  *will* be hard to debug without it.
- **`eslint`** — bump to v9 flat config + the new `eslint-config-next` for
  Next 16. Drop `@typescript-eslint/*` standalone — `typescript-eslint` v8
  is the canonical entry point now.

**Drop:**
- `next-pwa` (replaced by Serwist).
- `autoprefixer` (built into Tailwind v4 / Lightning CSS).

**Hold for later:**
- `next-intl` — only if/when we ship non-English. Tokyo demo doesn't need it.
- A Storybook / Ladle setup — defer until we have ~10+ components.

---

## Recommended `package.json` diff

```jsonc
{
  "name": "plus-one-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint .",
    "lint:fix": "eslint . --fix",
    "typecheck": "tsc --noEmit",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui"
  },
  "dependencies": {
    "next": "^16.2.0",
    "react": "^19.2.0",
    "react-dom": "^19.2.0",

    "zustand": "^5.0.1",
    "@tanstack/react-query": "^5.62.0",

    "react-hook-form": "^7.55.0",
    "@hookform/resolvers": "^3.10.0",
    "zod": "^3.23.8",

    "motion": "^12.38.0",

    "@serwist/next": "^9.0.0",
    "serwist": "^9.0.0",

    "clsx": "^2.1.1",
    "tailwind-merge": "^2.5.4",
    "class-variance-authority": "^0.7.0",
    "lucide-react": "^0.460.0",
    "sonner": "^1.7.0",

    "@radix-ui/react-slot": "^1.1.0",
    "@radix-ui/react-tabs": "^1.1.1",
    "@radix-ui/react-dialog": "^1.1.2",
    "@radix-ui/react-label": "^2.1.0"
  },
  "devDependencies": {
    "@types/node": "^22.9.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "typescript": "^5.6.3",

    "eslint": "^9.15.0",
    "eslint-config-next": "^16.2.0",
    "typescript-eslint": "^8.14.0",

    "prettier": "^3.3.3",
    "prettier-plugin-tailwindcss": "^0.6.8",

    "tailwindcss": "^4.3.0",
    "@tailwindcss/postcss": "^4.3.0",
    "postcss": "^8.4.49",

    "vitest": "^3.0.0",
    "@vitejs/plugin-react": "^4.3.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.3",
    "jsdom": "^25.0.1",

    "@playwright/test": "^1.49.0",
    "@tanstack/react-query-devtools": "^5.62.0"
  },
  "packageManager": "pnpm@9.12.3",
  "engines": {
    "node": ">=20"
  }
}
```

Removed: `next-pwa`, `autoprefixer`, `@typescript-eslint/eslint-plugin`,
`@typescript-eslint/parser` (replaced by `typescript-eslint` v8 flat preset).

Changed: every dep above the blank line.

---

## Tailwind v4 `@theme` block — locked against `docs/design/mockups/_shared.css`

Designer has confirmed tokens (DESIGN_SPEC.md §10, live in
`docs/design/mockups/_shared.css`). HSL-triplet pattern matches the existing
`tailwind.config.ts` shape, so the migration is mechanical.

**Naming contract (locked):** Tailwind utility names mirror token names 1:1.
`bg-paper`, `text-ink-2`, `border-rule`, `text-display-lg`, `p-editorial-9`,
`bg-status-running-tint`, `text-tab-gem`. No translation layer between spec,
mockup CSS, and shipped utilities.

```css
/* app/globals.css */
@import "tailwindcss";

@theme {
  /* ── Color (HSL triplets, consumed via hsl(var(--…))) ──────────── */
  --color-paper:           hsl(36 22% 96%);
  --color-paper-elevated:  hsl(36 28% 98%);
  --color-ink:             hsl(220 18% 10%);
  --color-ink-2:           hsl(220 12% 28%);
  --color-ink-3:           hsl(220 8%  48%);
  --color-rule:            hsl(30 14% 82%);
  --color-rule-strong:     hsl(30 10% 62%);

  --color-brass:           hsl(36 38% 42%);
  --color-brass-tint:      hsl(36 38% 92%);

  --color-status-pending:        hsl(36 16% 60%);
  --color-status-pending-tint:   hsl(36 16% 92%);
  --color-status-running:        hsl(200 32% 42%);
  --color-status-running-tint:   hsl(200 32% 92%);
  --color-status-complete:       hsl(145 22% 36%);
  --color-status-complete-tint:  hsl(145 22% 92%);
  --color-status-aborted:        hsl(8 38% 40%);
  --color-status-aborted-tint:   hsl(8 38% 92%);

  --color-tab-gem:        hsl(36 38% 42%);
  --color-tab-trap:       hsl(8 38% 40%);
  --color-tab-together:   hsl(145 22% 36%);
  --color-tab-you:        hsl(200 32% 42%);
  --color-tab-partner:    hsl(270 18% 46%);
  --color-tab-disagree:   hsl(220 12% 28%);

  /* ── Typography ────────────────────────────────────────────────── */
  --font-display: "Fraunces", "Cormorant Garamond", Georgia, serif;
  --font-body:    "Inter Tight", system-ui, -apple-system, sans-serif;
  --font-mono:    "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;

  /* Modular scale 1.25, named not numeric */
  --text-display-xl: clamp(48px, 7vw, 72px);
  --text-display-lg: clamp(36px, 5.2vw, 56px);
  --text-display-md: clamp(28px, 3.4vw, 40px);
  --text-display-sm: clamp(24px, 2.6vw, 32px);
  --text-title:      22px;
  --text-body-lg:    18px;
  --text-body:       16px;
  --text-body-sm:    14px;
  --text-caption:    12px;
  --text-micro:      10px;

  /* ── Spacing — 8px base + editorial whitespace tokens ──────────── */
  --spacing: 4px;                    /* base unit; 1..6 = 4/8/12/16/24/32 */
  --spacing-editorial-7:  48px;
  --spacing-editorial-8:  64px;
  --spacing-editorial-9:  96px;
  --spacing-editorial-10: 144px;
  --spacing-editorial-11: 200px;

  /* ── Radii (almost zero — pills are the only full-radius element) */
  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-lg: 8px;

  /* ── Motion ─────────────────────────────────────────────────────── */
  --ease-default: cubic-bezier(0.2, 0.7, 0.2, 1);
  --duration-fast: 180ms;
  --duration:      280ms;
  --duration-slow: 480ms;
  --duration-hero: 720ms;
}
```

**Notes:**
- No `@theme` shadow tokens. Per spec, product surfaces use `border-rule`
  hairlines instead of box-shadows.
- Container queries are native in v4 (`@container`, `@sm:`, `@md:`) — the
  `@tailwindcss/container-queries` plugin from v3 is not needed and not
  installed.
- Fonts ship via `next/font` in `app/layout.tsx`; the `--font-*` vars in
  `@theme` are the family-stack fallback. `next/font` injects
  `--font-fraunces` / `--font-inter-tight` at runtime; root layout sets
  `body { font-family: var(--font-fraunces), var(--font-display); }` so the
  `@theme` chain remains as a safety net.
- JetBrains Mono is loaded only on the trip-detail route via per-route
  `next/font` import — not in the root layout.
- Light only for v1 (designer confirmed). Dark mode is a future PR; v4
  supports `@theme` overrides under `[data-theme="dark"]` when we get
  there.
- Status-pulse animation (1.6s opacity-only ease-in-out, reduced-motion
  honoured) is plain CSS in `globals.css` — not a Motion concern.

---

## Migration cost (in PRs)

| PR | Scope | LOC est. | Risk |
|----|-------|----------|------|
| **0a** | Bump Next 14 → 16, React 18 → 19, ESLint 9 flat config. Fix typecheck. | ~80 (mostly lockfile) | Low — empty app |
| **0b** | Tailwind v3 → v4, move tokens to `@theme`, drop autoprefixer | ~60 | Low |
| **0c** | Replace `next-pwa` with `@serwist/next`, author `app/sw.ts`, move manifest to `app/manifest.ts` | ~80 | Low |
| **0d** | Add TanStack Query, RHF + Zod, Motion, sonner, Playwright scaffolding | ~120 | Low |

**Total: 4 small PRs, ~340 LOC, ~half-day of focused work.** All before any
Batch 2f UI is written. None of these change behavior — the landing page
keeps rendering — so the reviewer load is light.

After 0a-0d, Batch 2f PR A and PR B (per `REMAINING_WORK.md`) proceed on a
modern foundation.

---

## Risks & unknowns

1. **React Compiler quirks** — v1.0 is stable but a few component patterns
   (refs into mutable closures) trip it. We will hit one or two. Easy to
   opt-out per-file with `'use no memo'`.
2. **Serwist + Turbopack** — Serwist v9 supports Turbopack with a known
   caveat: the SW source rebuild is webpack-based even when the app is
   Turbopack. Acceptable, no behavior impact in dev.
3. **Designer dark-mode** — out of scope for v1 (light only, confirmed). When
   added, v4 supports `@theme` overrides under `[data-theme="dark"]`.
4. **Maestro / SSE proxy** — unrelated to stack choices but worth noting:
   `REMAINING_WORK.md` already says "don't proxy SSE through Next
   rewrites" — Next 16 doesn't change that.

---

## What I am explicitly NOT recommending and why

- **Vite + React Router 7** — would mean an ADR. Loses Next's image
  optimisation, RSC, file-system routing, middleware, and the Serwist+SW
  story. No upside for this product.
- **TanStack Start** — interesting but pre-1.0 in May 2026. Not a fit for a
  PWA we want shipping in weeks.
- **Panda CSS / vanilla-extract** — extra toolchain for outcomes Tailwind v4
  already gives us.
- **Effector / Jotai / Valtio** — Zustand is doing the job; do not introduce
  a third state pattern.
- **MSW for API mocking in tests** — overkill at this scale; mock `fetch`
  directly in vitest.
- **Storybook** — premature with one designer + one engineer. Re-evaluate
  when component count > 10.

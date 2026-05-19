# PR2 — Tailwind CSS 3 → 4 Migration

**Branch:** `feat/stack-pr2-tailwind4`
**Scope:** Build pipeline + class compatibility only. No component rewrites, no design changes.
**Author:** PRD Agent
**Date:** 2026-05-19

---

## 1. Background

The Plus One frontend (`frontend/`) currently uses **Tailwind CSS 3.4.14** with the legacy PostCSS plugin and a JS `tailwind.config.ts`. Tailwind 4 (released early 2025, GA stable by 2026) ships:

- A new **Oxide** engine — significantly faster builds (≈10× incremental, ≈3.5× full).
- A **CSS-first** config model (`@theme` in CSS, no JS config required).
- A dedicated **`@tailwindcss/postcss`** plugin and bundled `@import` + autoprefixer handling.
- All theme tokens automatically exposed as CSS variables (`--color-*`, `--breakpoint-*`, etc.).
- A growing v4-only plugin ecosystem (typography, container-queries, animate) that PR3+ will benefit from.

Staying on v3 will increasingly cost us plugin compatibility and is incompatible with the next wave of shadcn updates we plan in PR3.

## 2. Goals

**G1 is the PR-completion gate. All other goals are secondary.**

| # | Goal | Measurement |
|---|------|-------------|
| **G1** | **Playwright e2e gate stays green — primary acceptance criterion for PR2.** | `pnpm --filter plus-one-frontend e2e` (i.e. `pnpm exec playwright test`) exit 0 locally **and** in CI. All five `landing.spec.ts` assertions pass: (a) `GET /` returns HTTP 200, (b) `page.title()` equals `Plus One — AI travel planner`, (c) h1 text equals `Plus One`, (d) tagline element containing `AI travel planner` is visible, (e) zero unexpected console errors and zero `pageerror` events (allow-list unchanged: favicon/icon/manifest only). |
| G2 | Frontend builds green on Tailwind 4. | `pnpm --filter plus-one-frontend build` exit 0. |
| G3 | Landing page renders pixel-equivalent typography and layout. | Manual eyeball diff of `/` against pre-merge screenshot; h1 "Plus One", tagline, "🚧 Phase α" all legible, centered, same vertical rhythm. |
| G4 | Lint, typecheck, unit tests stay green. | `pnpm lint && pnpm typecheck && pnpm test` all exit 0. |
| G5 | Build pipeline retains `--webpack` flag (PR4 owns the serwist swap). | `package.json` scripts unchanged in shape. |
| G6 | Bundle size delta within ±5 kB gzipped on the landing route. | `next build` output before/after recorded in PR description. |

## 3. Non-Goals

- ❌ **No shadcn/ui component scaffolding** — Button/Card/Dialog/etc. wait for PR3.
- ❌ **No new pages, components, or copy changes.**
- ❌ **No scrapbook design-system edits** — `docs/design/scrapbook/scrapbook-zh.css` stays untouched (it is hand-authored, not Tailwind-driven, but any Tailwind utility on a wrapper around it must keep working).
- ❌ **No Turbopack switch** — PR1 already chose webpack for compatibility with next-pwa; that stays until PR4.
- ❌ **No dark-mode UI work** — the `.dark` CSS-var block in `globals.css` is migrated as-is; no toggle is added.
- ❌ **No font/typography redesign** — per the standing rule (切记不要为了花里胡哨把字体弄得不好看清), legibility wins. Defaults stay defaults.
- ❌ **No ESLint config changes** beyond what tailwindcss/postcss package renames force.
- ❌ **No serwist / next-pwa pipeline changes** — PR4 territory.
- ❌ **No new Playwright specs.** This PR does not add e2e cases; it only guarantees the existing five assertions in `frontend/e2e/landing.spec.ts` keep passing. New coverage (forms, navigation, etc.) belongs to PR3+.
- ❌ **No removal of `tailwind.config.ts`** — kept and reached via `@config` (see §6) to minimize semantic diff. CSS-first `@theme` migration is deferred to a later cleanup PR.

## 4. Current State

### Versions (`frontend/package.json`)

| Package | Version |
|---------|---------|
| `tailwindcss` | `3.4.14` (devDep) |
| `postcss` | `8.4.49` (devDep) |
| `autoprefixer` | `10.4.20` (devDep) |
| `prettier-plugin-tailwindcss` | `0.6.8` (devDep) |

### Config files

- `frontend/tailwind.config.ts` — minimal:
  - `content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"]`
  - `theme.extend.colors`: `border`, `background`, `foreground`, `primary.{DEFAULT,foreground}`, `muted.{DEFAULT,foreground}` — all `hsl(var(--...))`.
  - `theme.extend.borderRadius`: `lg = var(--radius)`, `md = calc(var(--radius) - 2px)`, `sm = calc(var(--radius) - 4px)`.
  - `plugins: []`, no `darkMode` key (defaults to `media`), no `safelist`, no `corePlugins`.
- `frontend/postcss.config.cjs` — `{ tailwindcss: {}, autoprefixer: {} }`.
- `frontend/app/globals.css` — `@tailwind base; @tailwind components; @tailwind utilities;` followed by one `@layer base { :root { --background … --radius } .dark { … } }` block defining HSL CSS variables.

### Codebase usage (greps over `frontend/`, excluding `node_modules`)

| Pattern | Hits |
|---------|------|
| `@apply` | 0 |
| `theme(` | 0 |
| `screen(` | 0 |
| Arbitrary values `bg-[…]` / `text-[…]` / `w-[…]` etc. | 0 |
| `darkMode:` config | 0 |
| `@layer` | 1 (`@layer base` in `globals.css`) |
| Tailwind plugins | 0 |

Utility surface area is just two files: `app/page.tsx` (layout/text utilities) and `app/layout.tsx` (`min-h-screen bg-background text-foreground antialiased`). No renamed/removed v4 utilities are in use (no `shadow`, no `rounded` alone, no `bg-opacity-*`, no `flex-shrink-*`, no `ring` alone, no `outline-none`).

## 5. Target State

### Versions (post-PR)

| Package | Action | Target |
|---------|--------|--------|
| `tailwindcss` | upgrade | `^4.0.0` (latest minor) |
| `@tailwindcss/postcss` | **add** | `^4.0.0` |
| `postcss` | keep | `8.4.49` (or whatever upgrade tool pins) |
| `autoprefixer` | **remove** | — (v4 ships its own prefixing) |
| `prettier-plugin-tailwindcss` | upgrade | `^0.6.x` matching v4 (latest patch) |

### Config approach

- **Keep `tailwind.config.ts`** for now; reference it explicitly via `@config "../tailwind.config.ts";` at the top of `globals.css`. This preserves the exact theme-extend semantics with zero rewrite risk and avoids any chance of color/radius drift on the landing page.
- A follow-up cleanup ticket may later migrate the same tokens to a CSS-first `@theme` block; explicitly out of scope here.

### CSS directive change in `globals.css`

```css
/* v3 (current) */
@tailwind base;
@tailwind components;
@tailwind utilities;

/* v4 (target) */
@import "tailwindcss";
@config "../tailwind.config.ts";
```

The `@layer base { :root {…} .dark {…} }` block stays as-is — it defines plain CSS custom properties and does not depend on Tailwind utilities. Native CSS cascade layers handle it correctly in v4.

### PostCSS config

```js
// frontend/postcss.config.cjs (target)
module.exports = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
```

`autoprefixer` entry removed.

## 6. Migration Plan (step-by-step)

1. **Snapshot baseline.** Run `pnpm --filter plus-one-frontend build` and record bundle output (`.next/build-manifest.json` size, first-load JS for `/`). Take a manual screenshot of `/` at desktop + mobile widths.
2. **Run the official codemod first.** From `frontend/`:
   ```bash
   npx @tailwindcss/upgrade@latest
   ```
   Requires Node 20+ (we are on Node ≥20 per `engines`). Review the diff — the codemod is expected to:
   - swap `tailwindcss` → `tailwindcss@^4` and add `@tailwindcss/postcss`,
   - remove `autoprefixer`,
   - rewrite `postcss.config.cjs`,
   - convert `@tailwind` directives to `@import "tailwindcss"`,
   - emit an `@config` reference to the existing JS config.
3. **Manual reconciliation.** Compare codemod output against §5 target; correct any drift (especially: ensure `autoprefixer` is fully removed from `package.json`, ensure `prettier-plugin-tailwindcss` is bumped to a v4-compatible release).
4. **Install + lockfile.** `pnpm install` from repo root; commit updated `pnpm-lock.yaml`.
5. **Local sanity checks.**
   - `pnpm --filter plus-one-frontend typecheck` — expect green (no TS surface changed).
   - `pnpm --filter plus-one-frontend lint` — expect green.
   - `pnpm --filter plus-one-frontend test` — expect green (vitest `--passWithNoTests`).
   - `pnpm --filter plus-one-frontend build` — expect green; capture bundle delta.
6. **Dev-server smoke.** `pnpm --filter plus-one-frontend dev` (still `next dev --webpack`), open `http://localhost:3000`, eyeball h1 "Plus One", tagline, "🚧 Phase α" line. Verify font weight, sizing, centering, and color of `text-muted-foreground` paragraphs all match the baseline screenshot.
7. **Playwright gate (FINAL STEP — gating).** From `frontend/`:
   ```bash
   pnpm exec playwright test
   ```
   Must exit 0 with all five `landing.spec.ts` assertions green. Capture an HTML report screenshot (or the `playwright-report/` summary line) for the PR description as evidence. **Only after this passes** is the branch ready to hand off to Test Agent for an independent re-run on a clean checkout.
8. **Bundle size diff** recorded in PR body (per G6).
9. **Open PR** to `main` with the Problem/Solution/Test-evidence template, including the e2e evidence from step 7.

If any step fails, stop and report — do **not** attempt to "fix forward" by editing utility classes or component markup; that would breach the scope guardrail.

## 7. Risks & Mitigations

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|------------|--------|------------|
| **R1** | Arbitrary-value syntax change (`[--var]` → `(--var)`) breaks a class. | **Very Low** — codebase grep found zero arbitrary-value classes. | Build fails. | Pre-flight grep already done; re-run after merge of any concurrent PR before starting. |
| **R2** | `@apply` of a v3-only utility breaks compile. | **None** — zero `@apply` in code. | n/a | n/a. |
| **R3** | `theme(...)` function calls break (v4 prefers CSS vars). | **None** — zero hits. | n/a | n/a. |
| **R4** | PostCSS plugin order conflicts with `next-pwa` workbox CSS pipeline. | **Low** — next-pwa wraps the Next config but does not inject PostCSS plugins; CSS is handled by Next's own pipeline using `postcss.config.cjs`. | Build fails or service worker emits broken CSS. | Verify `pnpm build` succeeds and the generated `public/sw.js` and precache manifest still reference the same CSS asset hashes pattern. If breakage occurs, fall back to explicit plugin ordering with `postcss-import` first; document and escalate. |
| **R5** | Browser baseline drop (v4 requires Safari 16.4+, Chrome 111+, Firefox 128+). | **Low** for Plus One target users; no stated baseline below this exists in the repo (`README`, `docs/prd.md`). | Users on iOS < 16.4 / very old Android Chrome see broken styling. | Document the baseline in PR description and `docs/prd.md` "Compatibility" section follow-up. Plus One is a PWA targeting modern phones; the bar is acceptable. If a stricter baseline surfaces from product later, the documented escape hatch is staying on v3.4 (LTS-equivalent). |
| **R6** | v4 changes how `globals.css` is loaded (`@import "tailwindcss"` + `@config`) and shifts the cascade order of the `@layer base { :root { --background … --radius } }` HSL custom-property block. If those variables get redefined or stripped, `bg-background` / `text-foreground` / `text-muted-foreground` on the landing page resolve to wrong colors, and any tagline/h1 font-size token can drift. The five text-only assertions in `landing.spec.ts` would still pass, but a future `expect(...).toHaveCSS(...)` assertion would fail, and the visual landing breaks. | **Low–Medium** — this is the most likely v4-specific regression vector for this codebase. | Visual drift on landing; future CSS assertions fail. | (a) Mandatory manual screenshot diff in migration plan step 6 (eyeball every utility used by `app/page.tsx` and `app/layout.tsx`); (b) keep the CSS variable **names** (`--background`, `--foreground`, `--muted-foreground`, `--primary`, `--border`, `--radius`) and the **HSL channel syntax** byte-for-byte identical — do not let the codemod rewrite them to `oklch()` or rename them; (c) keep the `@layer base { :root {…} .dark {…} }` wrapper exactly where it is, after the `@import "tailwindcss"` line, so native cascade layers preserve precedence; (d) if drift is observed, fall back to inlining the same vars in `:root` outside `@layer base` and re-run e2e. |
| **R7** | `prettier-plugin-tailwindcss` v3-line doesn't understand v4 class sorting → format churn in CI. | **Low–Medium** — plugin had a v4-aware release in 2025. | Format diff noise. | Bump to latest patch in lockstep with tailwindcss; run `pnpm format:check` as part of pre-PR. |
| **R8** | The `@config` directive can't find `tailwind.config.ts` due to relative path. | **Low** — `globals.css` lives at `frontend/app/globals.css`, config at `frontend/tailwind.config.ts`, so `@config "../tailwind.config.ts"` is correct. | Build fails with explicit error. | Verified at planning time; build will fail fast and loudly if path is wrong. |
| **R9** | HSL CSS-variable color syntax `hsl(var(--background))` in `tailwind.config.ts` behaves differently under Oxide. | **Low** — Oxide treats the JS config's color callbacks the same way; values are emitted into the same CSS-var-backed utilities. | Landing page background/text color drift. | Step 6 eyeball check; the colors used (`bg-background`, `text-foreground`, `text-muted-foreground`) cover the surface. |
| **R10** | Scrapbook stylesheet (`docs/design/scrapbook/scrapbook-zh.css`) conflict — not Tailwind, but bundled / imported alongside. | **None** — that file is referenced only inside `docs/design/` design references, not imported into the Next app. Grep `frontend/` confirms no import. | n/a | If a future scrapbook integration ships, re-evaluate then. |

No risk warrants splitting or deferring PR2. **Recommendation: proceed.**

## 8. Acceptance Criteria

A reviewer should be able to verify each. **Criterion #1 is the gate — if it fails, the PR is not mergeable regardless of the other items.**

1. **`pnpm --filter plus-one-frontend e2e` exits 0** locally and in CI. All five `landing.spec.ts` assertions pass: HTTP 200 on `/`, title `Plus One — AI travel planner`, h1 `Plus One`, tagline contains `AI travel planner`, zero unexpected console errors / pageerrors (allow-list unchanged). E2E run output (or `playwright-report/` summary) attached to the PR description.
2. `pnpm --filter plus-one-frontend build` exits 0; build log contains no Tailwind/PostCSS warnings.
3. `pnpm --filter plus-one-frontend lint` exits 0 (ESLint 9 flat config unchanged).
4. `pnpm --filter plus-one-frontend typecheck` exits 0.
5. `pnpm --filter plus-one-frontend test` exits 0.
6. Manual eyeball: `/` renders the same heading size/weight, same body sizing, same centering, same muted-foreground paragraph color as the pre-PR screenshot. No font-weight or font-family regressions ("不花里胡哨" rule honored).
7. `package.json` diff contains only: `tailwindcss` bumped to `^4`, `@tailwindcss/postcss` added, `autoprefixer` removed, `prettier-plugin-tailwindcss` patch-bumped if needed. **No** changes to `next-pwa`, `next`, `react`, `eslint*` lines.
8. `next.config.mjs` is **unchanged**.
9. `frontend/app/page.tsx` and `frontend/app/layout.tsx` are **unchanged** (utility classes untouched).
10. Bundle size for `/` route reported in PR body; delta within ±5 kB gzipped.
11. The `--webpack` flag is still present in `dev` and `build` scripts.
12. `docs/design/scrapbook/scrapbook-zh.css` is **unchanged**.
13. No new files under `frontend/e2e/` (per non-goal: this PR adds zero e2e specs).

## 9. Rollout

- **Single PR**, squash-merged into `main`.
- **No feature flag** — Tailwind is a build-time concern; the artifact is either v3 or v4.
- **No staged rollout** — frontend is still pre-production (Phase α).
- **Rollback** — `git revert` the merge commit; lockfile reverts cleanly because no runtime dependency in `dependencies` changed (only `devDependencies`).
- **Follow-up tickets to file post-merge:**
  - "Migrate `tailwind.config.ts` theme tokens into CSS-first `@theme` block in `globals.css`" (purely a code-style cleanup; no behavior change).
  - "Document browser baseline (Safari 16.4+, Chrome 111+, Firefox 128+) in `docs/prd.md` Compatibility section."

---

**End of PRD.**

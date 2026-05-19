# PRD: Stack PR3 — Zustand 5 + react-hook-form + zod + TanStack Query v5

- **Branch:** `feat/stack-pr3-state-forms-query`
- **Author:** PRD Agent
- **Date:** 2026-05-19
- **Status:** Draft → Ready for Code Agent
- **Predecessor:** PR2 (Tailwind 3→4, shadcn-style components) merged on `main`
- **Successor:** PR4 (`next-pwa` → `@serwist/next` v9)

---

## 1. Background

After PR1 (Next 14→16, React 18→19) and PR2 (Tailwind 3→4), the Plus One frontend stack is on modern framework rails but the *application* libraries — state, forms, validation, server-state — are either missing or pinned at versions that predate the React 19 era. We need to align these four dependencies before product work begins in Batch 2f / PR4, so future feature PRs don't drag in a stack-bump and a feature change in the same diff.

The four targets:

1. **Zustand** — already declared at `5.0.1` but unused; bump to the latest 5.x patch so future state stores start on the current line.
2. **react-hook-form** — not installed; add with the official `@hookform/resolvers` companion so we get a single forms idiom across the app.
3. **zod** — present only as a transitive (`zod@4.4.3` via `zod-validation-error`); promote to a direct dependency so import resolution is stable and the version is owned by us.
4. **TanStack Query v5** — not installed; add so SSE-adjacent UI (Batch 2e produced server-side; PR4+ will consume it on the client) has a server-cache layer ready.

There is no source code that uses any of these four packages today (see §4), so the bump is mechanical. Doing it now means the e2e gate stays the only acceptance signal, and PR4 / Batch 2f can focus purely on feature work.

## 2. Goals

- **G1 (highest priority):** `pnpm exec playwright test` on `frontend/e2e/landing.spec.ts` returns **1/1 PASS** after the bump. This is the PR completion gate, identical to PR2.
- **G2:** `pnpm build`, `pnpm lint`, `pnpm test`, `pnpm format:check` all stay green.
- **G3:** No visual regression on the landing page (covered by the post-migration screenshot diff that landing.spec.ts captures).
- **G4:** Versions pinned to exact strings (no `^` floats) so future installs are deterministic, matching the existing style for `@radix-ui/*`, `clsx`, `tailwind-merge`, etc.
- **G5:** `pnpm-lock.yaml` reflects the new resolutions cleanly (no duplicate zod copies — direct dep takes the same `4.4.3` the transitive resolved to).

## 3. Non-goals

- No new pages, routes, components, or feature work.
- No new Zustand stores, no new RHF forms, no new TanStack queries — adding the libs is the deliverable; consuming them belongs to Batch 2f / PR4+.
- No SSE client wiring (the producer/SSE endpoint shipped in PR `595a55a`, but the consumer is out of scope here).
- No PWA / service-worker changes — `--webpack` flag stays on dev/build scripts; PR4 will handle the swap to `@serwist/next`.
- No changes to user-facing strings, fonts, scrapbook CSS, or the e2e specs themselves.
- No new class-sorting rewrites or component refactors.
- No introduction of QueryClientProvider into `app/layout.tsx` — provider wiring lands when the first consumer ships.
- No Zustand devtools middleware in this PR (zero stores to attach it to).

> User rule preserved: 切记不要为了花里跨张把字体弄得不好看清 — this PR touches zero typography/CSS, so it is observed by construction.

## 4. Current state

### 4.1 Installed versions

From `frontend/package.json:21-52`:

| Package | Current | Type |
|---|---|---|
| `zustand` | `5.0.1` | dep (already declared) |
| `react-hook-form` | — | not installed |
| `@hookform/resolvers` | — | not installed |
| `zod` | — (transitive `4.4.3` via `zod-validation-error`, see `frontend/pnpm-lock.yaml:4071-4080`) | not a direct dep |
| `@tanstack/react-query` | — | not installed |
| `@tanstack/react-query-devtools` | — | not installed |

No other `@tanstack/*` companions (no `react-query-persist-client`, no `query-sync-storage-persister`, no `query-async-storage-persister`) are present.

### 4.2 Usage in source

Recursive grep across `frontend/` for the canonical import patterns yielded **zero matches in any `.ts` / `.tsx` file**:

| Pattern | Hits in source |
|---|---|
| `from "zustand"` / `create(` / `useStore(` / persist middleware | 0 |
| `from "react-hook-form"` / `useForm` / `Controller` / `useFieldArray` | 0 |
| `from "zod"` / `z.object` / `z.infer` | 0 |
| `from "@tanstack/react-query"` / `useQuery` / `useMutation` / `QueryClient` | 0 |

The only references to these names anywhere in `frontend/` are:

- `frontend/package.json:33` — `zustand` declaration.
- `frontend/pnpm-lock.yaml:44`, `:4071-4080`, `:6555-6556`, `:8406-8412` — lockfile entries for `zustand@5.0.1`, `zod@4.4.3`, `zod-validation-error@4.0.2`.

The current `frontend/app/` tree contains only `layout.tsx`, `page.tsx`, `globals.css`. There is no `lib/`, `hooks/`, or `components/` directory yet.

**Conclusion:** the bump is a pure dependency-graph change. There are no call sites to migrate.

### 4.3 Toolchain context

- Next.js `^16.2.0`, React `^19.2.0`, TypeScript `5.6.3`, ESLint `^9.16.0`, Tailwind `4.3.0`, Vitest `2.1.5`, Playwright `1.55.0`, pnpm `9.12.3`, Node `>=20`.
- Dev/build scripts retain `--webpack` (PR4 swaps to serwist).

## 5. Target state

### 5.1 Pinned target versions (as of 2026-05-19, verified via `pnpm view`)

| Package | Target | Section |
|---|---|---|
| `zustand` | `5.0.13` | `dependencies` |
| `react-hook-form` | `7.76.0` | `dependencies` |
| `@hookform/resolvers` | `5.2.2` | `dependencies` |
| `zod` | `4.4.3` | `dependencies` (promote from transitive) |
| `@tanstack/react-query` | `5.100.11` | `dependencies` |
| `@tanstack/react-query-devtools` | `5.100.11` | `devDependencies` |

All versions pinned without `^` to match the surrounding style.

### 5.2 PR shape — combined, not split

**Recommendation: one combined PR.** Justification:

- Source usage of all four packages is zero, so per-package risk surfaces are equal and tiny.
- Splitting into 4 sub-PRs would require 4 separate green e2e runs and 4 review rounds for what is effectively `pnpm add` + lockfile churn.
- The dependency relationships (`@hookform/resolvers` bridges RHF + zod) mean a split-PR ordering would still require landing them as a quasi-atomic group.
- Combined PR keeps reviewers focused on the lockfile diff, which is the only place mistakes can hide.

## 6. Migration plan

Execute in this order — zod is first because `@hookform/resolvers` and any future RHF schema consumes it.

### Step 1 — zod (promote transitive to direct)

```bash
pnpm add -E zod@4.4.3 --filter ./frontend
```

- `-E` pins exact version (no `^`).
- The transitive resolution is already `4.4.3`, so the lockfile change should be limited to promoting the entry to a top-level dependency record; `zod-validation-error@4.0.2` keeps resolving to the same `zod@4.4.3` instance.

### Step 2 — react-hook-form + resolvers

```bash
pnpm add -E react-hook-form@7.76.0 @hookform/resolvers@5.2.2 --filter ./frontend
```

- `@hookform/resolvers@5.2.2` declares `zod` as a peer — already satisfied by Step 1.
- React peer dep `^16.8 || ^17 || ^18 || ^19` — React 19 satisfied.

### Step 3 — Zustand (patch bump only)

```bash
pnpm update -E zustand@5.0.13 --filter ./frontend
```

- Same major as the currently-installed `5.0.1`. Per Zustand v5 release notes (default-export removal, `createWithEqualityFn`, persist init-state behavior, etc.) — all are v4→v5 concerns, **not** intra-v5 concerns, so they do not apply.
- React peer dep already satisfied (Zustand 5 requires React ≥ 18).

### Step 4 — TanStack Query v5

```bash
pnpm add -E @tanstack/react-query@5.100.11 --filter ./frontend
pnpm add -DE @tanstack/react-query-devtools@5.100.11 --filter ./frontend
```

- React peer dep ≥ 18 — satisfied.
- TypeScript ≥ 4.7 — satisfied (we are on 5.6.3).
- **Do not** add `<QueryClientProvider>` to `app/layout.tsx` in this PR. The provider lands with the first consumer (PR4+ / Batch 2f) so we don't add dead infrastructure.

### Step 5 — Verification gates (run in this order)

```bash
cd frontend
pnpm install                  # idempotency check after manual edits, if any
pnpm format:check             # prettier — must be clean
pnpm lint                     # eslint flat config
pnpm typecheck                # tsc --noEmit
pnpm test                     # vitest (passWithNoTests)
pnpm build                    # next build --webpack
pnpm exec playwright test     # acceptance gate — landing.spec.ts must be 1/1 PASS
```

If `pnpm build` produces a bundle-size warning, record `.next/analyze` or build summary delta in the PR description but do not block on it (no JS is shipped from these libs yet — zero call sites).

## 7. Risks & mitigations

| ID | Risk | Likelihood | Mitigation |
|---|---|---|---|
| **R1** | TanStack Query v5 removes `onSuccess` / `onError` / `onSettled` callbacks on `useQuery`. | **N/A** — grep confirms zero `useQuery` usage. Mitigation is preventive: Code Agent must reject any future PR that adds these on a `useQuery`; use `useMutation` (still supports them) or `useEffect` against `data` / `error`. |
| **R2** | Zustand 5 drops default export and changes the `create<T>()(...)` curry. | **N/A** — repo already runs `zustand@5.0.1` and has zero `create()` call sites. Future-store code should follow the named-export + curry style from `zustand@5` docs. |
| **R3** | Jumping to Zod v4 changes inference and deprecates `z.string().email()` style. | **Low.** No existing schemas. Code Agent guideline: write new schemas with v4 top-level format funcs (`z.email()`, `z.url()`, `z.uuid()`) and the `error` option (not `message`). |
| **R4** | `react-hook-form` latest bumps React peer to 19. | **None** — peer dep is `^16.8 || ^17 || ^18 || ^19`; we are on `^19.2.0`. |
| **R5** | Indirect breakage of `landing.spec.ts` via CSS / runtime side-effect from a new dep. | **Very low.** None of these four libs touch CSS or auto-instantiate at import; landing page has no consumers. Mitigated by Step 5 e2e gate — if it fails we revert, do not patch the spec. |
| **R6** | Lockfile drift — two `zod` versions resolved if pnpm sees a conflict. | **Low.** Pin both the direct dep and trust pnpm's hoisting; verify `pnpm-lock.yaml` shows a single `zod@4.4.3` block after install. Manual check is part of Code Agent's "before report done" list. |
| **R7** | Bundle size regression visible to Lighthouse / future perf budget. | **Low.** Tree-shaking will eliminate all four libs because there are zero imports. Build output JS size should be unchanged within rounding. If the Next build report shows a non-trivial delta (>2KB on First Load), investigate before merging. |
| **R8** | `@tanstack/react-query-devtools` accidentally shipped to prod. | **Low.** Pinned to `devDependencies`; the canonical consumer pattern (`process.env.NODE_ENV !== 'production' && <ReactQueryDevtools />`) is not introduced in this PR. Reviewer to confirm placement in `devDependencies` block. |

## 8. Acceptance criteria

In priority order — **A1 is the gate.**

1. **A1 (PR completion gate):** `pnpm exec playwright test` against `frontend/e2e/landing.spec.ts` reports **1/1 PASS**, run from a fresh `pnpm install` on `feat/stack-pr3-state-forms-query`. Evidence: terminal output snippet in PR description.
2. **A2:** `pnpm build` exits 0 on the same branch. No new warnings beyond the existing baseline.
3. **A3:** `pnpm lint` exits 0 (no new ESLint warnings or errors).
4. **A4:** `pnpm format:check` exits 0 (prettier clean — note: `package.json` formatting is prettier-controlled, so the version-bump edits must round-trip cleanly).
5. **A5:** `pnpm test` exits 0 (`vitest run --passWithNoTests` — no test files exist yet, so the pass is structural).
6. **A6:** `pnpm typecheck` exits 0.
7. **A7:** Bundle delta on the landing route's First Load JS is within ±2KB of the pre-PR baseline (sanity check, not blocking unless gross).
8. **A8:** Zero new files added under `frontend/e2e/` — the spec set is unchanged.
9. **A9:** Diff is restricted to `frontend/package.json` + `frontend/pnpm-lock.yaml`. No source code in `frontend/app/`, `frontend/lib/`, `frontend/components/`, no Next config, no Tailwind config, no postcss/prettier/eslint config touched.
10. **A10:** `frontend/package.json` has all six packages at the exact pinned versions in §5.1, `zustand` / `react-hook-form` / `@hookform/resolvers` / `zod` / `@tanstack/react-query` under `dependencies`, `@tanstack/react-query-devtools` under `devDependencies`.
11. **A11:** `frontend/pnpm-lock.yaml` contains exactly one `zod@4.4.3` resolution block (no duplicates).
12. **A12:** Dev/build scripts in `frontend/package.json` still contain `--webpack` flags; PWA / serwist untouched.

## 9. Rollout

- **Strategy:** single squash-merged PR from `feat/stack-pr3-state-forms-query` → `main`.
- **Feature flag:** none — pure dependency change, no runtime behaviour exposed.
- **Reviewer focus:** the lockfile diff, the absence of source-code changes, and the e2e evidence snippet.
- **Rollback:** revert the merge commit. No data, no migrations, no infra coupling.
- **Post-merge unblocks:** PR4 (serwist) can proceed in parallel; Batch 2f UI consumers (forms, query, stores) can land on the new versions immediately.

## 10. Open questions

None blocking. If the user wants `<QueryClientProvider>` wired into `app/layout.tsx` in this PR (with a stub `QueryClient`) to save a future round-trip, that is a one-line scope expansion the Code Agent can add — flag and confirm with team lead before doing so.

---

## Appendix A — Reference links consulted

- TanStack Query v4→v5 migration: <https://tanstack.com/query/v5/docs/framework/react/guides/migrating-to-v5>
- Zustand v5 migration: <https://github.com/pmndrs/zustand/blob/v5.0.0/docs/migrations/migrating-to-v5.md>
- Zod v4 release notes: <https://zod.dev/v4>
- react-hook-form changelog: <https://github.com/react-hook-form/react-hook-form/blob/master/CHANGELOG.md>
- react-hook-form React 19 peer dep: <https://github.com/react-hook-form/react-hook-form/blob/master/package.json>

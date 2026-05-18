# PRD: E2E Bootstrap — Playwright + Landing Smoke + CI Gate

**Owner:** Plus One frontend
**Branch:** `feat/e2e-playwright-bootstrap`
**Status:** Draft → ready for Code Agent
**Depends on:** PR #10 (Next 16.2 / React 19.2 / ESLint 9 stack bump) merged to `main`

---

## 1. Background

Plus One has zero browser-level test coverage today.

- **Backend** has 123 unit tests via `pytest` and a passing CI lane (see `.github/workflows/ci.yml` `backend` job). No integration tests yet (the `Integration tests` step is gated `if: false`).
- **Frontend** has only `vitest run --passWithNoTests` as its test command — i.e., literally no tests run. The `frontend` CI job covers `format:check`, `lint`, `typecheck`, `build`. No runtime verification of the rendered page.
- The frontend is currently a single landing page (`frontend/app/page.tsx` + `frontend/app/layout.tsx`) with the title `"Plus One — AI travel planner"` and an `<h1>Plus One</h1>`. No auth UI, no trip creation UI — those land in Batch 2f.
- PR #10 just bumped Next 14→16.2 and React 18→19.2. The Test agent for that PR observed that production build emits **pre-existing favicon/icon 404s** at runtime (no `/favicon.ico`, no PWA icons yet). Those are tracked separately and should not block e2e.

**Why now:** before any UI work (auth flow, trip creation, SSE consumption) lands, we need a runtime gate so a single regression doesn't ship silently. Bootstrapping with a thin landing smoke spec is the minimal investment that lets every subsequent PR add specs incrementally.

---

## 2. Goals

1. **Playwright installed** in `frontend/` with a pinned version and committed lockfile updates.
2. **`playwright.config.ts`** at `frontend/` with sensible defaults: chromium-only in CI for speed, all three browsers available locally on demand, baseURL `http://localhost:3000`, `webServer` boots `pnpm start` against the production build.
3. **`frontend/e2e/landing.spec.ts`** green, covering:
   - GET `/` returns HTTP 200.
   - `<title>` is `"Plus One — AI travel planner"` (exact match from `app/layout.tsx`).
   - `<h1>` text is `"Plus One"`.
   - Body contains the tagline substring `"AI travel planner"`.
   - No console **errors** during page load, except an allow-listed pattern for the pre-existing favicon/PWA icon 404s.
4. **pnpm scripts** added: `e2e`, `e2e:ui`, `e2e:install`, `e2e:report`.
5. **`justfile` targets** added: `frontend-e2e`, `frontend-e2e-install`, `frontend-e2e-ui`. Naming matches existing `frontend-*` convention.
6. **CI gate live**: new `frontend-e2e` job in `.github/workflows/ci.yml` runs on PRs touching `frontend/**` or the workflow file itself; included in the `ci-pass` aggregate gate. Failure artifacts (HTML report, traces, screenshots, videos on failure) uploaded.
7. **Local dev ergonomics**: README snippet (or addition to existing README) shows the 3 commands a contributor needs.
8. **`.gitignore`** updated for Playwright output directories.

---

## 3. Non-goals

Explicit list of what this PR will **not** do:

- ❌ No business-path specs (login, magic-link consume, trip creation, SSE stream, report rendering). Those land in Batch 2f and later under their own PRDs.
- ❌ No backend boot in CI for e2e (no postgres, no redis, no Maestro). The landing page is fully static — it does not call the API.
- ❌ No visual regression / screenshot diffing (Playwright supports it, but adds flake surface and reviewer cost; defer).
- ❌ No `auth.setup.ts` / storage state fixtures (no auth yet to capture).
- ❌ No matrix across browsers in CI (chromium only). Webkit/Firefox available locally.
- ❌ No matrix across Node versions (frontend CI already pins Node 20).
- ❌ No mobile viewport projects yet (add when responsive specs exist).
- ❌ No fixing the pre-existing favicon 404s — track separately; this PR only filters them out.
- ❌ No HarshJudge integration. Plain Playwright reporter is sufficient at this scale.
- ❌ No Playwright MCP wiring for the agent (Test agent already uses VS Debugger MCP for backend; frontend e2e is invoked via `pnpm e2e` directly).

---

## 4. Technical approach

### 4.1 Playwright config (`frontend/playwright.config.ts`)

```ts
import { defineConfig, devices } from "@playwright/test";

const isCI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: isCI ? 2 : undefined,
  reporter: isCI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    // Local-only browsers — opt in via PLAYWRIGHT_ALL_BROWSERS=1
    ...(process.env.PLAYWRIGHT_ALL_BROWSERS
      ? [
          { name: "firefox", use: { ...devices["Desktop Firefox"] } },
          { name: "webkit",  use: { ...devices["Desktop Safari"]  } },
        ]
      : []),
  ],
  webServer: {
    command: "pnpm start",
    url: "http://localhost:3000",
    reuseExistingServer: !isCI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
```

**Decisions and rationale:**

- **Chromium only in CI** — single browser ≈ 3× faster, ≈ 3× smaller cache. Adding Firefox/WebKit is one-line opt-in once a real flake budget exists.
- **`pnpm start` (production build)** — matches `pnpm build` artifact CI already produces. Dev server has different error boundaries and hot-reload noise; not representative.
- **`reuseExistingServer: !isCI`** — local devs running `pnpm dev` separately don't get a port collision.
- **`retries: 2` in CI, `0` local** — landing page is static so flakes will be infra (cold start, network). Local devs want fast feedback.
- **`workers: 2` in CI** — GitHub free runners have 2 vCPUs; more workers = thrash.
- **`trace: "on-first-retry"`** + **`screenshot: "only-on-failure"`** + **`video: "retain-on-failure"`** — debuggable failures, near-zero overhead on green runs.
- **`forbidOnly: isCI`** — accidental `test.only` in CI fails the build.

### 4.2 Spec (`frontend/e2e/landing.spec.ts`)

Shape:

```ts
import { test, expect, type ConsoleMessage } from "@playwright/test";

// Allow-listed console errors that are pre-existing and tracked separately.
// These come from missing favicon/PWA icons and will be removed once the
// icon set lands. Until then, do not fail the e2e on them.
const ALLOWED_CONSOLE_ERROR_PATTERNS: RegExp[] = [
  /Failed to load resource.*favicon\.ico/i,
  /Failed to load resource.*icon-\d+x\d+\.png/i,
  /Failed to load resource.*apple-touch-icon/i,
  /Failed to load resource.*manifest\.json/i,
];

function isAllowed(msg: ConsoleMessage): boolean {
  const text = msg.text();
  return ALLOWED_CONSOLE_ERROR_PATTERNS.some((re) => re.test(text));
}

test.describe("landing page", () => {
  test("renders with correct title, heading, and tagline", async ({ page }) => {
    const unexpectedErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error" && !isAllowed(msg)) {
        unexpectedErrors.push(msg.text());
      }
    });
    // Network-level 404s also surface as page errors; ignore allow-listed paths.
    page.on("pageerror", (err) => unexpectedErrors.push(err.message));

    const response = await page.goto("/");
    expect(response?.status(), "GET / should return 200").toBe(200);

    await expect(page).toHaveTitle("Plus One — AI travel planner");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Plus One");
    await expect(page.getByText("AI travel planner", { exact: false })).toBeVisible();

    expect(unexpectedErrors, `unexpected console errors:\n${unexpectedErrors.join("\n")}`).toEqual([]);
  });
});
```

**Filter strategy decision:** allow-list **specific patterns** rather than disabling all console-error checks. This preserves the ability to catch real regressions (e.g., uncaught render errors, hydration mismatches) while accepting the known favicon noise. When favicons land, the allow-list shrinks; eventually it goes to `[]`.

### 4.3 `package.json` scripts

Add:

```json
"e2e": "playwright test",
"e2e:ui": "playwright test --ui",
"e2e:install": "playwright install --with-deps chromium",
"e2e:report": "playwright show-report"
```

Add to `devDependencies`:

```json
"@playwright/test": "1.49.0"
```

Pin the major; Playwright bumps are usually fine but breakages do happen.

### 4.4 `justfile` additions

Append to the `# === Frontend ===` section:

```make
# Install Playwright browser binaries (chromium only by default)
frontend-e2e-install:
    cd frontend && pnpm e2e:install

# Run Playwright e2e tests headless (against pnpm start)
frontend-e2e:
    cd frontend && pnpm e2e

# Run Playwright UI mode for local debugging
frontend-e2e-ui:
    cd frontend && pnpm e2e:ui
```

`frontend-check` stays as `lint + typecheck` (e2e is heavier — don't gate the fast feedback loop on it). Top-level `check` likewise unchanged.

### 4.5 CI workflow

Modify `.github/workflows/ci.yml`. Two changes:

**1. Extend the `changes` filter to expose an `e2e` output.** (Use the same `frontend` filter — anything that changes `frontend/**` should also trigger e2e.)

**2. Add a `frontend-e2e` job:**

```yaml
  frontend-e2e:
    needs: changes
    if: needs.changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    defaults:
      run:
        working-directory: frontend
    env:
      NEXT_PUBLIC_API_URL: http://localhost:8000
      CI: "true"
    steps:
      - uses: actions/checkout@v4

      - name: Setup pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 9.12.3

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Cache Playwright browsers
        uses: actions/cache@v4
        id: playwright-cache
        with:
          path: ~/.cache/ms-playwright
          key: playwright-${{ runner.os }}-${{ hashFiles('frontend/pnpm-lock.yaml') }}

      - name: Install Playwright browsers
        if: steps.playwright-cache.outputs.cache-hit != 'true'
        run: pnpm exec playwright install --with-deps chromium

      - name: Install Playwright system deps (cache hit path)
        if: steps.playwright-cache.outputs.cache-hit == 'true'
        run: pnpm exec playwright install-deps chromium

      - name: Build
        run: pnpm build

      - name: Run e2e
        run: pnpm e2e

      - name: Upload Playwright report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 7

      - name: Upload test results (traces, screenshots, videos)
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-test-results
          path: frontend/test-results/
          retention-days: 7
```

**3. Update `ci-pass` to include `frontend-e2e`:**

```yaml
  ci-pass:
    needs: [backend, frontend, frontend-e2e]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Verify all required jobs passed
        run: |
          if [ "${{ needs.backend.result }}" = "failure" ] || \
             [ "${{ needs.frontend.result }}" = "failure" ] || \
             [ "${{ needs.frontend-e2e.result }}" = "failure" ]; then
            echo "❌ A required job failed"
            exit 1
          fi
          echo "✅ All required jobs passed (or skipped)"
```

**Cache strategy:** browser binaries cached by `pnpm-lock.yaml` hash (proxy for Playwright version). System deps (`libnss3`, etc.) still need re-install on cache hit since they live in `/usr/lib`, not `~/.cache`. Cold install ≈ 90s; warm ≈ 15s. Acceptable for a single-spec smoke.

**Concurrency:** existing `concurrency` block at workflow level already cancels superseded runs.

### 4.6 `.gitignore` additions

Append under a `# Playwright` section:

```
# Playwright
frontend/test-results/
frontend/playwright-report/
frontend/playwright/.cache/
frontend/blob-report/
```

### 4.7 Documentation

Add to the existing top-level `README.md` (or create one in `frontend/` if it does not exist — Code Agent should check). Snippet:

```markdown
### E2E (Playwright)

```bash
just frontend-e2e-install   # one-time: download chromium binary
just frontend-build         # build for production (e2e runs against pnpm start)
just frontend-e2e           # run headless
just frontend-e2e-ui        # interactive UI mode for debugging

# All browsers locally:
cd frontend && PLAYWRIGHT_ALL_BROWSERS=1 pnpm e2e
```
```

---

## 5. Acceptance criteria

Code Agent and Test Agent verify the following before Ship:

### Files exist and are well-formed
- [ ] `frontend/playwright.config.ts` exists, exports a valid `defineConfig(...)`.
- [ ] `frontend/e2e/landing.spec.ts` exists.
- [ ] `frontend/package.json` contains `@playwright/test` in `devDependencies` and the 4 new scripts.
- [ ] `frontend/pnpm-lock.yaml` regenerated and committed.
- [ ] `justfile` contains `frontend-e2e`, `frontend-e2e-install`, `frontend-e2e-ui`.
- [ ] `.github/workflows/ci.yml` contains `frontend-e2e` job and `ci-pass` lists it in `needs`.
- [ ] `.gitignore` contains the 4 Playwright entries.

### Behavior — local
- [ ] `just frontend-e2e-install` exits 0; chromium binary present under `~/.cache/ms-playwright`.
- [ ] `just frontend-build` exits 0.
- [ ] `just frontend-e2e` exits 0; 1 spec, 1 test passes against chromium.
- [ ] Spec **fails** if the `<h1>` text is changed (sanity check that the assertion is real, not a no-op).
- [ ] Spec **does not fail** on the known favicon 404 console errors.
- [ ] Spec **does fail** if an unrelated `console.error("boom")` is added to `app/page.tsx`.

### Behavior — CI
- [ ] PR triggers `frontend-e2e` job (visible in PR checks).
- [ ] Job completes green on first run.
- [ ] `ci-pass` requires it.
- [ ] On a deliberately broken spec (Test Agent verifies locally then reverts), the failing run uploads `playwright-report` and `playwright-test-results` artifacts.

### Hygiene
- [ ] `pnpm format:check`, `pnpm lint`, `pnpm typecheck` all pass with the new files.
- [ ] No `test.only` left in spec.
- [ ] No new uncommitted files outside the gitignored Playwright dirs after a full local run.

---

## 6. Risk + rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| CI cold-start flake (chromium fails to boot under cold runner) | Medium | Single PR retry | `retries: 2` in CI config absorbs single transient failures |
| Playwright browser download adds 30–90s to PR cycle | High | +1 min PR feedback | Cache keyed on lockfile; warm path ~15s; only runs when `frontend/**` changes (paths-filter already handles this) |
| `pnpm start` doesn't bind to `:3000` in time | Low | Timeout failure | `webServer.timeout: 120_000` (2 min) gives ample headroom on slow runners |
| Allow-list filter masks a real regression | Low | Missed bug | Patterns are narrow (favicon / icon / apple-touch / manifest); any other error type still fails. Allow-list is documented and meant to shrink as icons land |
| Playwright version drift surprises us on next bump | Medium | Spec breakage | Pin exact version (`1.49.0`, not `^1.49.0`); browser cache key includes lockfile so version bumps invalidate cache cleanly |
| `pnpm e2e` runs before backend exists in CI and accidentally calls the API | n/a | Would 404/hang | Landing page makes no API calls — verified by reading `app/page.tsx`. If a future change adds a call, the spec will surface it (different failure mode) |
| Job becomes a chronic flake source | Medium (long-term) | Team disables the gate | If `frontend-e2e` is the top source of red builds for 2 sprints, escalate: tighten allow-list, raise retries, or split into a non-blocking lane |

### Rollback

If the gate proves intolerable in CI:

1. **Soft disable**: remove `frontend-e2e` from `ci-pass.needs`. Job still runs and reports, but PRs are not blocked. One-line change.
2. **Hard disable**: set the job's `if:` to `false`. Keeps the YAML for fast re-enable.
3. **Full revert**: `git revert` this PR's merge commit. Files are additive only (no edits to existing specs, no removed steps), so revert is mechanical.

All three preserve the spec file and config — future re-enable is configuration-only.

---

## 7. Open questions for team-lead

None blocking. Two notes for awareness:

- **README placement.** Repo has no top-level `README.md` snippet for the frontend that I can see in this branch's scope. Code Agent should either append to an existing README or add a short `frontend/README.md` if none exists.
- **Playwright version.** Picked `1.49.0` as a recent stable; Code Agent may bump to whatever is current at implementation time if there's no breaking changelog entry against our pinned Next 16.2.

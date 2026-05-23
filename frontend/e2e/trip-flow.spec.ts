import { test, expect } from "@playwright/test";
import { signInE2E } from "./_helpers/auth";

// Batch 2f PR B — full trip happy path.
// Scaffolded as fixme until the trip surface lands. Once the trip form,
// SSE consumer, and report view ship, drop `.fixme` to activate.
//
// Contract source: docs/prds/batch2f-pr-b-trips.md §4.3 + §6 R5 + skills
// fixture (`backend/src/plus_one/skills/ramen_basics.md` — Tokyo is the
// canonical happy-path destination, so this should reach `complete`,
// not `aborted`).
//
// Generous timeouts: SSE event surface within 20s, terminal status within
// 60s — the producer/joiner/controller cycle plus report persistence
// dominates, and CI is slow.

test.describe("trip flow (happy path)", () => {
  test("submit trip → live event → terminal status → report visible", async ({ page, request }) => {
    await signInE2E(page, request);

    await page.goto("/app/trips/new");
    await page.getByLabel(/the place|destination/i).fill("Tokyo");
    await page.getByRole("button", { name: /go look|plan|start|create/i }).click();

    await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i, { timeout: 10_000 });

    // At least one progress event surfaces in the live feed
    await expect(page.getByTestId("progress-feed")).toContainText(
      /started|producer|joiner|controller|cycle aborted|trip complete/i,
      { timeout: 20_000 },
    );

    // Trip lands on a terminal status (complete or aborted). Either is a
    // success for *this* spec — content correctness is asserted next.
    await expect(
      page.locator("[data-trip-status='complete'], [data-trip-status='aborted']"),
    ).toBeVisible({ timeout: 60_000 });

    // In this e2e environment PLUS_ONE_ALLOW_REAL_LLM=0 forces the cycle to
    // abort with an empty report (see playwright.config.ts). So the most
    // meaningful destination check is that the page header still reflects
    // the trip we created — the report region itself is empty by design.
    await expect(page.getByText(/Tokyo/i)).toBeVisible();

    // Batch 2i — perspective toggle and disagreement tab render without
    // crashing even when the report is empty (the disagreement bucket is
    // empty too — that's fine; we're just asserting non-crash rendering).
    await expect(page.getByTestId("perspective-toggle")).toBeVisible();
    await expect(page.getByRole("tab", { name: /two minds|disagreement/i })).toBeVisible();

    // Batch 2k — output language toggle is present alongside the
    // perspective toggle. PLUS_ONE_TRANSLATE_ENABLED=0 in e2e so the
    // report has no translations key; clicking the toggle must not
    // crash (assertion is mechanical, not content-based).
    const languageToggle = page.getByTestId("language-toggle");
    await expect(languageToggle).toBeVisible();
    await languageToggle.getByRole("radio", { name: /english/i }).click();
    await expect(languageToggle).toBeVisible();
  });
});

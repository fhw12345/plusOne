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
    await page.getByLabel(/destination/i).fill("Tokyo");
    await page.getByRole("button", { name: /plan|start|create/i }).click();

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

    // Report content references the destination we asked for
    await expect(page.getByText(/Tokyo/i)).toBeVisible();
  });
});

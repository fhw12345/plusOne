import { test, expect } from "@playwright/test";

import { signInE2E } from "./_helpers/auth";

test.describe("trip list (/app)", () => {
  test("empty state shows the plan-a-trip CTA", async ({ page, request }) => {
    await signInE2E(page, request);
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: /my trips/i })).toBeVisible();
    // Empty-state copy uses one of these phrases.
    await expect(page.getByText(/no trips yet|first trip|plan a new trip/i).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /plan a new trip/i }).first()).toBeVisible();
  });

  test("creating two trips renders both cards; clicking one navigates to detail", async ({
    page,
    request,
  }) => {
    await signInE2E(page, request);

    // Drive the two trip creations through the UI (so we know the token
    // is already in the page's auth store). Two distinct destinations
    // so the list assertion is unambiguous.
    for (const dest of ["Tokyo", "Osaka"]) {
      await page.goto("/app/trips/new");
      await page.getByLabel(/destination/i).fill(dest);
      await page.getByRole("button", { name: /plan|start|create/i }).click();
      await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i, { timeout: 10_000 });
    }

    await page.goto("/app");
    await expect(page.getByRole("heading", { name: /my trips/i })).toBeVisible();
    // Both destinations render as cards.
    await expect(page.getByText(/Tokyo/).first()).toBeVisible();
    await expect(page.getByText(/Osaka/).first()).toBeVisible();

    // Click one and confirm we land on the detail page.
    await page.getByText(/Tokyo/).first().click();
    await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i, { timeout: 10_000 });
  });
});

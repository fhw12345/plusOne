import { test, expect } from "@playwright/test";
import { signInE2E } from "./_helpers/auth";

// Batch 2f PR B — /app/trips/new page.
// Scaffolded ahead of implementation so the e2e surface grows now.
// Each `test.fixme(...)` is a contract the upcoming PR must satisfy.
// When the page lands, drop `.fixme` to activate the assertion.
//
// Contract source: docs/prds/batch2f-pr-b-trips.md §4.3 + §4.2 TripForm row.
// Form spec: both fields rendered, only `destination` required (zod min(1));
// `free_text` is optional (textarea, zod max(2000)). This file asserts only
// the required-label contract — `free_text`'s presence is covered by the
// happy path in `trip-flow.spec.ts`.

test.describe("trip new page", () => {
  test("renders the trip form when authed", async ({ page, request }) => {
    await signInE2E(page, request);
    await page.goto("/app/trips/new");

    await expect(page.getByRole("heading", { level: 1 })).toContainText(/plan a trip|new trip/i);
    await expect(page.getByLabel(/destination/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /plan|start|create/i })).toBeVisible();
  });

  test("blocks submission when destination is empty", async ({ page, request }) => {
    await signInE2E(page, request);
    await page.goto("/app/trips/new");

    // leave both fields untouched, just click submit
    await page.getByRole("button", { name: /plan|start|create/i }).click();

    // zod resolver should surface a validation message before any network call
    await expect(page.getByText(/required|destination/i)).toBeVisible();
  });

  test("submitting a valid trip navigates to /app/trips/<id>", async ({ page, request }) => {
    await signInE2E(page, request);
    await page.goto("/app/trips/new");

    await page.getByLabel(/destination/i).fill("Tokyo");
    await page.getByRole("button", { name: /plan|start|create/i }).click();

    await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i);
  });
});

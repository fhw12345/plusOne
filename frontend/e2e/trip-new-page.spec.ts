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

    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      /where are you headed|plan a trip|new trip/i,
    );
    await expect(page.getByLabel(/the place|destination/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /go look|plan|start|create/i })).toBeVisible();
  });

  test("blocks submission when destination is empty", async ({ page, request }) => {
    await signInE2E(page, request);
    await page.goto("/app/trips/new");

    // leave both fields untouched, just click submit
    await page.getByRole("button", { name: /go look|plan|start|create/i }).click();

    // zod resolver surfaces a validation message before any network call.
    // Accept any of the scrapbook-voice required messages or generic copy.
    await expect(
      page.getByText(/where to|required|destination|pick a place|need a place/i).first(),
    ).toBeVisible();
  });

  test("submitting a valid trip navigates to /app/trips/<id>", async ({ page, request }) => {
    await signInE2E(page, request);
    await page.goto("/app/trips/new");

    await page.getByLabel(/the place|destination/i).fill("Tokyo");
    await page.getByRole("button", { name: /go look|plan|start|create/i }).click();

    await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i);
  });
});

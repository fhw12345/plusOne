import { test, expect } from "@playwright/test";

import { signInE2E } from "./_helpers/auth";

// Batch 2j PR A — delete trip round trip: create → confirm in
// AlertDialog → land back on /app → GET /api/trips/{id} returns 404.

test.describe("delete trip", () => {
  test("delete from detail page → redirect to /app → backend returns 404", async ({
    page,
    request,
  }) => {
    await signInE2E(page, request);

    await page.goto("/app/trips/new");
    await page.getByLabel(/destination/i).fill("Osaka");
    await page.getByRole("button", { name: /plan|start|create/i }).click();
    await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i, { timeout: 10_000 });
    await expect(
      page.locator("[data-trip-status='complete'], [data-trip-status='aborted']"),
    ).toBeVisible({ timeout: 60_000 });

    // Capture the trip id from the URL for a back-end follow-up GET.
    const tripIdMatch = page.url().match(/\/app\/trips\/([0-9a-f-]{36})/i);
    expect(tripIdMatch).not.toBeNull();
    const tripId = tripIdMatch?.[1] ?? "";
    expect(tripId).not.toBe("");

    await page.getByTestId("delete-trip-button").click();
    await page.getByTestId("delete-trip-confirm").click();

    await expect(page).toHaveURL(/\/app(\/|$)/, { timeout: 10_000 });

    // The backend should now 404 the deleted trip. Use the in-page
    // fetch so the request inherits the same JWT the UI uses.
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const status = await page.evaluate(
      async ({ url, id }: { url: string; id: string }) => {
        const persisted = window.localStorage.getItem("plus-one-auth");
        const token = persisted
          ? (JSON.parse(persisted) as { state: { token: string } }).state.token
          : null;
        const r = await fetch(`${url}/api/trips/${id}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        return r.status;
      },
      { url: apiBase, id: tripId },
    );
    expect(status).toBe(404);
  });
});

import { test, expect } from "@playwright/test";

import { signInE2E } from "./_helpers/auth";

// Batch 2j PR A — share-link round trip through an incognito context.
// The PLUS_ONE_ALLOW_REAL_LLM=0 env in playwright.config.ts forces the
// cycle to abort, so the trip lands on `aborted` quickly; sharing still
// works (terminal status is the only gate).

test.describe("share link", () => {
  test("create trip → share → open in fresh context → revoke → expired", async ({
    page,
    request,
    browser,
  }) => {
    await signInE2E(page, request);

    // Create a trip and wait for it to land on a terminal status.
    await page.goto("/app/trips/new");
    await page.getByLabel(/destination/i).fill("Tokyo");
    await page.getByRole("button", { name: /plan|start|create/i }).click();
    await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i, { timeout: 10_000 });
    await expect(
      page.locator("[data-trip-status='complete'], [data-trip-status='aborted']"),
    ).toBeVisible({ timeout: 60_000 });

    // Open the share dialog and mint a link.
    await page.getByTestId("share-button").click();
    await expect(page.getByTestId("share-dialog")).toBeVisible();
    await page.getByTestId("share-create").click();
    const urlInput = page.getByTestId("share-url");
    await expect(urlInput).toBeVisible();
    const shareUrl = await urlInput.inputValue();
    expect(shareUrl).toContain("/share/");

    // Open the URL in a fresh browser context (no cookies / storage).
    const incognito = await browser.newContext();
    const guest = await incognito.newPage();
    await guest.goto(shareUrl);

    await expect(guest.getByText(/Tokyo/i).first()).toBeVisible();
    await expect(guest.getByText(/Read-only share/i)).toBeVisible();
    // Owner-only affordances must be absent on the public view.
    await expect(guest.getByTestId("share-button")).toHaveCount(0);
    await expect(guest.getByTestId("delete-trip-button")).toHaveCount(0);

    // Back in the owner context: revoke the link.
    await page.getByTestId("share-revoke").click();
    // Dialog state resets — the create button should be available again.
    await expect(page.getByTestId("share-create")).toBeVisible();

    // Re-fetch the share URL in the incognito context — should now 404.
    await guest.goto(shareUrl);
    await expect(guest.getByText(/Link expired or revoked/i)).toBeVisible();

    await incognito.close();
  });
});

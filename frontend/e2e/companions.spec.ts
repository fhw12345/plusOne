import { test, expect } from "@playwright/test";

import { signInE2E } from "./_helpers/auth";

test.describe("companions page (/app/companions)", () => {
  test("create → edit → duplicate-name 409 → delete", async ({ page, request }) => {
    await signInE2E(page, request);
    await page.goto("/app/companions");

    await expect(page.getByRole("heading", { name: /who you bring|companions/i })).toBeVisible();
    await expect(page.getByText(/no one in the book|no companions yet/i)).toBeVisible();

    // Create "Alex"
    await page
      .getByRole("button", { name: /add the first one|add companion/i })
      .click();
    await page.getByLabel(/^Name$/i).fill("Alex");
    const loves = page.getByRole("textbox", { name: "Loves" });
    await loves.fill("matcha");
    await loves.press("Enter");
    await loves.fill("ramen");
    await loves.press("Enter");
    const dietary = page.getByRole("textbox", { name: "Dietary" });
    await dietary.fill("vegetarian");
    await dietary.press("Enter");

    await page.getByRole("button", { name: /^Add$/ }).click();

    await expect(page.getByText("Alex").first()).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("matcha").first()).toBeVisible();
    await expect(page.getByText("vegetarian").first()).toBeVisible();

    // Edit "Alex" → "Alex K" + add a hate
    await page.getByRole("button", { name: /Edit Alex/i }).click();
    const nameInput = page.getByLabel(/^Name$/i);
    await nameInput.fill("Alex K");
    const hates = page.getByRole("textbox", { name: "Hates" });
    await hates.fill("crowds");
    await hates.press("Enter");
    await page.getByRole("button", { name: /^Save$/ }).click();
    await expect(page.getByText("Alex K").first()).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("crowds").first()).toBeVisible();

    // Create another "Alex K" → 409 inline
    await page
      .getByRole("button", { name: /add the first one|add companion/i })
      .click();
    await page.getByLabel(/^Name$/i).fill("Alex K");
    await page.getByRole("button", { name: /^Add$/ }).click();
    await expect(page.getByText(/name already taken/i)).toBeVisible({ timeout: 5_000 });
    // Dialog stays open — the Name input is still in the DOM.
    await expect(page.getByLabel(/^Name$/i)).toBeVisible();
    await page.getByRole("button", { name: /cancel/i }).click();
    // Wait for the dialog overlay to actually unmount before clicking buttons
    // behind it (the radix portal teardown is async and the next click can
    // otherwise land on a stale overlay).
    await expect(page.getByRole("dialog")).toHaveCount(0);

    // Delete "Alex K" via AlertDialog
    await page.getByRole("button", { name: /Delete Alex K/i }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: /^Delete$/ })
      .click();
    await expect(page.getByText("Alex K")).toHaveCount(0, { timeout: 10_000 });
  });
});

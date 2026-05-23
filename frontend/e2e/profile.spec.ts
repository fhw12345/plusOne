import { test, expect } from "@playwright/test";

import { signInE2E } from "./_helpers/auth";

test.describe("profile page (/app/profile)", () => {
  test("empty initial state, save, reload — values persist", async ({ page, request }) => {
    await signInE2E(page, request);
    await page.goto("/app/profile");

    await expect(page.getByRole("heading", { name: /about you|profile/i }).first()).toBeVisible();
    await expect(page.getByLabel(/age range/i)).toBeVisible();
    // Empty-state defaults — no chips rendered yet.
    await expect(page.getByLabel(/Remove ramen/i)).toHaveCount(0);

    await page.getByLabel(/age range/i).fill("30-39");

    // Add a love chip via the dedicated input.
    const loves = page.getByRole("textbox", { name: "Loves" });
    await loves.fill("ramen");
    await loves.press("Enter");
    await loves.fill("kissaten");
    await loves.press("Enter");

    // Add a hate.
    const hates = page.getByRole("textbox", { name: "Hates" });
    await hates.fill("crowds");
    await hates.press("Enter");

    // Add a visited city.
    await page.getByRole("button", { name: /^\+?\s*add (a )?city$/i }).click();
    await page.getByLabel(/^City$/i).fill("Tokyo");

    await page.getByRole("button", { name: /pin it|save profile/i }).click();
    await expect(page.getByRole("status")).toHaveText(/pinned|saved/i, { timeout: 10_000 });

    await page.reload();
    await expect(page.getByLabel(/age range/i)).toHaveValue("30-39");
    await expect(page.getByLabel(/Remove ramen/i)).toBeVisible();
    await expect(page.getByLabel(/Remove kissaten/i)).toBeVisible();
    await expect(page.getByLabel(/Remove crowds/i)).toBeVisible();
    await expect(page.getByLabel(/^City$/i)).toHaveValue("Tokyo");
  });
});

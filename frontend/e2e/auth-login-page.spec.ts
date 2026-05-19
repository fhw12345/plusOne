import { test, expect } from "@playwright/test";

// Batch 2f PR A — /login page.
// Scaffolded ahead of implementation so the e2e surface grows now.
// Each `test.fixme(...)` is a contract the upcoming PR must satisfy.
// When the page lands, drop `.fixme` to activate the assertion.

test.describe("login page", () => {
  test("renders email input and submit button", async ({ page }) => {
    const response = await page.goto("/login");
    expect(response?.status(), "GET /login should return 200").toBe(200);

    await expect(page).toHaveTitle(/Plus One/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/sign in/i);
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /send.*link|magic link/i })).toBeVisible();
  });

  test("submitting a valid email shows confirmation copy", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("e2e@plusone.test");
    await page.getByRole("button", { name: /send.*link|magic link/i }).click();

    // backend returns 204 regardless — UI must show a generic confirmation
    await expect(page.getByText(/check your inbox|email sent|link sent/i)).toBeVisible({
      timeout: 5_000,
    });
  });

  test("blocks submission for an obviously invalid email", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("not-an-email");
    await page.getByRole("button", { name: /send.*link|magic link/i }).click();

    // zod resolver should surface a validation message before any network call
    await expect(page.getByText(/valid email|invalid email/i)).toBeVisible();
  });
});

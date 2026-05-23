import { test, expect } from "@playwright/test";

// Batch 2f PR A — /login page.
// Batch 2m swapped the magic-link surface for a tabbed password/code login.
// These specs target the "by code" tab — equivalent contract to the old
// magic-link flow (email in, code-request out).

test.describe("login page", () => {
  test("renders email input and submit button", async ({ page }) => {
    const response = await page.goto("/login");
    expect(response?.status(), "GET /login should return 200").toBe(200);

    await expect(page).toHaveTitle(/Plus One/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/let me in|sign in/i);

    // Switch to the code-request tab so the email-only form is visible.
    await page.getByRole("tab", { name: /by code/i }).click();

    await expect(page.getByLabel(/your email|email/i)).toBeVisible();
    await expect(
      page.getByRole("button", { name: /send me a code|send.*link|magic link/i }),
    ).toBeVisible();
  });

  test("submitting a valid email shows confirmation copy", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("tab", { name: /by code/i }).click();
    await page.getByLabel(/your email|email/i).fill("e2e@plusone.test");
    await page.getByRole("button", { name: /send me a code|send.*link|magic link/i }).click();

    // Code-tab flips to the "sent to {email}" phase once the backend accepts.
    await expect(page.getByText(/sent to|check your inbox|email sent|link sent/i)).toBeVisible({
      timeout: 5_000,
    });
  });

  test("blocks submission for an obviously invalid email", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("tab", { name: /by code/i }).click();
    await page.getByLabel(/your email|email/i).fill("not-an-email");
    await page.getByRole("button", { name: /send me a code|send.*link|magic link/i }).click();

    // zod resolver surfaces the inline validation message before any network call.
    await expect(page.getByText(/doesn'?t look right|valid email|invalid email/i)).toBeVisible();
  });
});

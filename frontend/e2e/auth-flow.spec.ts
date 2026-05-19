import { test, expect } from "@playwright/test";

// Batch 2f PR A — full magic-link happy path.
// Backend already ships POST /api/auth/request-link + POST /api/auth/exchange
// (see backend/src/plus_one/api/auth.py). The flow exercised here:
//
//   1.  visit /login, submit email
//   2.  test harness reads the latest magic-link token (dev-only endpoint
//       to be added by Code Agent: GET /api/auth/dev/last-link?email=...)
//   3.  open /auth/exchange?token=...  (matches the URL backend emails)
//   4.  land on /app, see authed-state UI
//   5.  sign out -> back at landing
//
// Scaffolded as fixme until those pages land.

test.describe("auth flow (magic link, happy path)", () => {
  test.fixme("request → verify → authed → sign out", async ({ page, request }) => {
    const email = `e2e+${Date.now()}@plusone.test`;

    // Step 1: request a link
    await page.goto("/login");
    await page.getByLabel(/email/i).fill(email);
    await page.getByRole("button", { name: /send.*link|magic link/i }).click();
    await expect(page.getByText(/check your inbox|email sent|link sent/i)).toBeVisible();

    // Step 2: harness fetches the token (dev-only endpoint)
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const lastLink = await request.get(
      `${apiBase}/api/auth/dev/last-link?email=${encodeURIComponent(email)}`,
    );
    expect(lastLink.status(), "dev last-link endpoint must respond").toBe(200);
    const { token } = (await lastLink.json()) as { token: string };
    expect(token, "magic-link token must be non-empty").toBeTruthy();

    // Step 3+4: exchange and land in the authed area
    await page.goto(`/auth/exchange?token=${encodeURIComponent(token)}`);
    await expect(page).toHaveURL(/\/app(\/|$)/);
    await expect(page.getByText(email)).toBeVisible();

    // Step 5: sign out
    await page.getByRole("button", { name: /sign out|log out/i }).click();
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("link", { name: /sign in/i })).toBeVisible();
  });
});

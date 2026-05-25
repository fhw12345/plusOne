import { test, expect, type APIRequestContext } from "@playwright/test";

// Batch 2m — full credential auth happy path.
// Replaces the magic-link flow that batch 2f PR A originally exercised.
//
//   1.  visit /register, submit username + email + password
//   2.  test harness reads the latest verify code (dev-only endpoint:
//       GET /api/auth/dev/last-code?email=...)
//   3.  visit /verify?email=... and submit the code
//   4.  land on /app, see authed-state UI
//   5.  sign out -> back at landing

test.describe("auth flow (credential, happy path)", () => {
  test("register → verify → authed → sign out", async ({ page, request }) => {
    const suffix = `${Date.now()}${Math.random().toString(36).slice(2, 8)}`;
    const email = `e2e${suffix}@plusone.test`;
    const username = `e2e${suffix}`.toLowerCase().slice(0, 30);
    const password = "e2epassword1";

    // Step 1: register
    await page.goto("/register");
    await page.getByLabel(/^username$/i).fill(username);
    await page.getByLabel(/your email/i).fill(email);
    await page.getByLabel(/^password$/i).fill(password);
    await page.getByLabel(/say it again/i).fill(password);
    await page.getByRole("button", { name: /save the page/i }).click();
    await expect(page).toHaveURL(/\/verify/);

    // Step 2: harness fetches the verify code (dev-only endpoint)
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const lastCode = await pollLastCode(apiBase, email, request);
    expect(lastCode.status(), "dev last-code endpoint must respond").toBe(200);
    const { code } = (await lastCode.json()) as { code: string };
    expect(code, "verify code must be non-empty").toBeTruthy();

    // Step 3+4: submit the code and land in the authed area
    await page.getByLabel(/the code/i).fill(code);
    await page.getByRole("button", { name: /^let me in$/i }).click();
    await expect(page).toHaveURL(/\/app(\/|$)/);
    await expect(page.getByText(email.split("@")[0] ?? email)).toBeVisible();

    // Step 5: sign out
    await page.getByRole("button", { name: /sign out|log out/i }).click();
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("link", { name: /let me in|sign in/i })).toBeVisible();
  });
});

async function pollLastCode(
  apiBase: string,
  email: string,
  request: APIRequestContext,
) {
  const url = `${apiBase}/api/auth/dev/last-code?email=${encodeURIComponent(email)}`;
  let response = await request.get(url);
  for (let attempt = 0; response.status() === 404 && attempt < 10; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 100));
    response = await request.get(url);
  }
  return response;
}

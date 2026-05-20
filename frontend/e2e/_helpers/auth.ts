import { expect, type Page, type APIRequestContext } from "@playwright/test";

// Single source of truth for the e2e sign-in sequence used by every spec
// that needs an authed page. Mirrors `e2e/auth-flow.spec.ts:17-37`, but
// auth-flow.spec.ts stays inline because it *is* the auth flow under test.
//
// Generates a fresh email internally — `Date.now()` alone is not unique
// across `playwright.config.ts:18` (`fullyParallel: true`), so a base36
// suffix kills the collision risk.
export async function signInE2E(
  page: Page,
  request: APIRequestContext,
): Promise<{ email: string }> {
  const email = `e2e+${Date.now()}-${Math.random().toString(36).slice(2, 8)}@plusone.test`;

  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByRole("button", { name: /send.*link|magic link/i }).click();
  await expect(page.getByText(/check your inbox|email sent|link sent/i)).toBeVisible();

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const lastLink = await request.get(
    `${apiBase}/api/auth/dev/last-link?email=${encodeURIComponent(email)}`,
  );
  expect(lastLink.status(), "dev last-link endpoint must respond").toBe(200);
  const { token } = (await lastLink.json()) as { token: string };
  expect(token, "magic-link token must be non-empty").toBeTruthy();

  await page.goto(`/auth/exchange?token=${encodeURIComponent(token)}`);
  await expect(page).toHaveURL(/\/app(\/|$)/);

  return { email };
}
